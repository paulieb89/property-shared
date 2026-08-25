"""EPC client for the GOV.UK Bearer API (pure Python).

The previous host, epc.opendatacommunities.org, was retired and now 301s. This
client targets the replacement service, which differs in auth, envelope, field
naming and identifiers — it is a migration, not a base-URL change.

Scope note: the service covers England and Wales. Scotland, Northern Ireland
and the Channel Islands return "no certificates found" (verified by probe), so
absence there is a coverage boundary, not evidence about a property.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

from property_core.epc.codebook import EPCCodebook
from property_core.epc.compat import to_epcdata
from property_core.epc.errors import (
    EPCAmbiguousMatchError,  # noqa: F401  (re-exported for callers)
    EPCAuthenticationError,
    EPCInvalidQueryError,
    EPCConfigurationError,
    EPCRateLimitError,
    EPCUnsupportedOperationError,
    EPCUpstreamError,
    EPCUpstreamShapeError,
)
from property_core.epc.selection import select_candidate
from property_core.epc.source_models import EPCCertificateDoc, EPCSearchPage
from property_core.models.epc import EPCData

BASE_URL = "https://api.get-energy-performance-data.communities.gov.uk"


class EPCClient:
    """Client for the GOV.UK EPC API.

    Authentication taxonomy — the adapter knows whether it supplied a token, so
    it can distinguish cases the upstream cannot (missing and invalid
    credentials both return an identical plain-text 403):

        no token configured        -> EPCConfigurationError, no request made
        token sent, 401/403        -> EPCAuthenticationError
        429                        -> EPCRateLimitError
        timeout / 5xx / bad body   -> EPCUpstreamError
        400                        -> EPCUpstreamError (invalid query)
        404                        -> genuine absence: None / empty page
    """

    BASE_URL = BASE_URL

    def __init__(
        self,
        token: str | None = None,
        timeout: float = 15.0,
        *,
        email: str | None = None,
        api_key: str | None = None,
    ):
        self.token = token or os.getenv("EPC_API_TOKEN")
        # Retained only to produce an actionable error. The retired Basic-auth
        # route is not a supported fallback and is never used to make a request.
        self._legacy_email = email or os.getenv("EPC_API_EMAIL")
        self._legacy_api_key = api_key or os.getenv("EPC_API_KEY")
        self.timeout = timeout
        self._transport: httpx.AsyncBaseTransport | None = None
        self._codebook: EPCCodebook | None = None

    # -- configuration ----------------------------------------------------

    def is_configured(self) -> bool:
        """True only when a Bearer token is present.

        Legacy credentials do not count: reporting the integration as
        configured while silently ignoring them is what produced false
        "no certificate found" answers in the first place.
        """
        return bool(self.token)

    def _require_configured(self) -> None:
        if self.token:
            return
        if self._legacy_email or self._legacy_api_key:
            raise EPCConfigurationError(
                "EPC_API_EMAIL/EPC_API_KEY are deprecated and unsupported: the API they "
                "authenticated against has been retired. Set EPC_API_TOKEN with a token "
                "from https://get-energy-performance-data.communities.gov.uk/."
            )
        raise EPCConfigurationError(
            "EPC service is not configured. Set EPC_API_TOKEN. Absence of a certificate "
            "cannot be concluded without consulting the service."
        )

    @property
    def codebook(self) -> EPCCodebook:
        if self._codebook is None:
            self._codebook = EPCCodebook(token=self.token, transport=self._transport)
        return self._codebook

    # -- transport --------------------------------------------------------

    async def _get(self, path: str, params: dict | None = None) -> tuple[int, Any]:
        self._require_configured()
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as c:
                resp = await c.get(f"{self.BASE_URL}{path}", params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise EPCUpstreamError(f"EPC request to {path} failed: {exc}") from exc
        finally:
            del headers

        status = resp.status_code
        if status in (401, 403):
            raise EPCAuthenticationError(
                f"EPC upstream rejected the supplied token (HTTP {status})"
            )
        if status == 429:
            raise EPCRateLimitError("EPC upstream rate limit reached (HTTP 429)")
        if status == 404:
            return status, None            # genuine absence
        if status >= 500 or status in (301, 302):
            raise EPCUpstreamError(f"EPC upstream returned HTTP {status} for {path}")
        if status == 400:
            detail = _error_text(resp)
            # Caller error, not an outage: a 503 would tell an operator to retry
            # something that can never succeed.
            raise EPCInvalidQueryError(f"EPC upstream rejected the query: {detail}")
        if status != 200:
            raise EPCUpstreamError(f"EPC upstream returned HTTP {status} for {path}")

        try:
            return status, resp.json()
        except ValueError as exc:
            raise EPCUpstreamShapeError(
                f"EPC upstream returned a non-JSON body for {path}"
            ) from exc

    # -- summary-native surface -------------------------------------------

    async def search_summaries(
        self,
        postcode: str,
        *,
        current_page: int = 1,
        page_size: int | None = None,
    ) -> EPCSearchPage:
        """One bounded page of certificate summaries. Makes no detail requests.

        Upstream page-number traversal is page-size-dependent and not a stable
        snapshot, so the returned page reports its own completeness rather than
        implying an area-wide set.
        """
        params: dict[str, Any] = {"postcode": postcode, "current_page": current_page}
        if page_size is not None:
            params["page_size"] = page_size
        status, body = await self._get("/api/domestic/search", params)
        if status == 404 or body is None:
            return EPCSearchPage.from_source({"data": [], "pagination": {"totalRecords": 0}})
        return EPCSearchPage.from_source(body)

    async def area_summary(self, postcode: str) -> dict:
        """Area statistics derivable from summaries alone. No certificate fan-out.

        property_type_breakdown and floor-area statistics are unavailable: they
        live only on full certificates, and fetching one per row would be an
        N+1 against an interactive path.
        """
        page = await self.search_summaries(postcode)
        bands: dict[str, int] = {}
        for row in page.results:
            b = row.current_energy_efficiency_band
            if b:
                bands[b] = bands.get(b, 0) + 1

        warnings = list(page.warnings)
        warnings.append(
            "property_type_breakdown and floor-area statistics are unavailable: the "
            "replacement EPC API exposes them only on full certificates, and computing "
            "them would require one request per certificate"
        )
        return {
            "postcode": postcode,
            "total_records": page.pagination.total_records,
            "returned_distinct_count": page.returned_distinct_count,
            "complete": page.complete,
            # Only an area-wide distribution when every matching summary is present.
            "rating_distribution": bands if page.complete else None,
            "rating_distribution_sample": None if page.complete else bands,
            "rating_distribution_sample_size": None if page.complete else page.returned_distinct_count,
            "property_type_breakdown": None,
            "floor_area_min": None,
            "floor_area_max": None,
            "floor_area_avg": None,
            "warnings": warnings,
        }

    # -- certificate ------------------------------------------------------

    async def get_certificate_doc(self, certificate_number: str) -> Optional[EPCCertificateDoc]:
        """Fetch one certificate as a source model, or None if it does not exist."""
        status, body = await self._get(
            "/api/certificate", {"certificate_number": certificate_number})
        if status == 404 or body is None:
            return None
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            raise EPCUpstreamShapeError("certificate response: missing 'data' object")
        return EPCCertificateDoc.from_source(data, certificate_number=certificate_number)

    async def get_certificate(self, certificate_hash: str) -> Optional[EPCData]:
        """v1-compatible certificate fetch by certificate number (formerly lmk-key).

        The codebook is warmed asynchronously first so the projection itself
        performs no network I/O — a synchronous lookup inside this async path
        would block the event loop on every uncached code.
        """
        doc = await self.get_certificate_doc(certificate_hash)
        if doc is None:
            return None
        warm_warnings = await self.codebook.warm(doc.schema_type)
        data = to_epcdata(doc, codebook=self.codebook)
        # Budget/missing-schema warnings explain WHY labels are absent; without
        # them a caller sees only a null field.
        data.warnings = list(warm_warnings) + list(data.warnings)
        return data

    async def search_by_postcode(
        self, postcode: str, address: str | None = None, *, uprn: str | None = None
    ) -> Optional[EPCData]:
        """Find one certificate at a postcode.

        Raises EPCAmbiguousMatchError rather than fetching an arbitrary
        certificate when a unique candidate cannot be established.
        """
        page = await self.search_summaries(postcode)
        if not page.results:
            return None
        selected = select_candidate(page.results, uprn=uprn, address=address)
        return await self.get_certificate(selected.row.certificate_number)

    # -- deprecated -------------------------------------------------------

    async def search_all_by_postcode(self, postcode: str) -> list[EPCData]:
        """Removed: the replacement upstream cannot support this honestly.

        Search now returns summaries, which carry no numeric score. EPCData.score
        is a non-Optional int, so every row would need its own certificate fetch
        or a fabricated 0. Neither is acceptable, and the bare list return type
        has nowhere to report that it is incomplete.
        """
        raise EPCUnsupportedOperationError(
            "search_all_by_postcode() is no longer supported: the EPC API returns "
            "summary rows that contain no energy score or floor area, so full EPCData "
            "records cannot be produced without one certificate request per row. "
            "Use search_summaries(postcode) for candidate discovery, then "
            "get_certificate(certificate_number) for the certificate you need. "
            "This method will be removed in the next breaking release."
        )

    def match_address(self, certificates, address, min_score: int = 30):
        """Retained for compatibility with the legacy matching helper."""
        from property_core.address_matching import match_epc_address

        return match_epc_address(certificates, address, min_score=min_score)


def _error_text(resp: httpx.Response) -> str:
    """Best-effort error text across the three observed envelopes.

    Observed live: {"data": {"error": ...}}, {"error": ...}, and plain text.
    """
    try:
        body = resp.json()
    except ValueError:
        return resp.text[:200]
    if isinstance(body, dict):
        inner = body.get("data")
        if isinstance(inner, dict) and "error" in inner:
            return str(inner["error"])
        if "error" in body:
            return str(body["error"])
    return str(body)[:200]
