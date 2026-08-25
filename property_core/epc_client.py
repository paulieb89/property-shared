"""EPC Register client (pure Python).

Fetches domestic EPC certificates for UK postcodes and returns typed EPCData models.
"""

from __future__ import annotations

import base64
import os
from typing import Optional

import httpx

from property_core.address_matching import match_epc_address
from property_core.models.epc import EPCData


class EPCUpstreamError(RuntimeError):
    """The EPC service could not be consulted, so absence cannot be concluded.

    Deliberately NOT a ValueError: this is an upstream/configuration fault, not
    caller error, and must not be mapped to a 4xx or reported to an LLM as
    "no certificate exists for this property".

    Raised for: unreachable or erroring upstream (including redirects — the
    original API host was retired and now 301s), unparseable responses, an
    unrecognised response envelope, and missing credentials. A reachable
    upstream that genuinely holds no certificate still returns None/[].
    """


class EPCClient:
    """Client for UK EPC Register API."""

    BASE_URL = "https://epc.opendatacommunities.org/api/v1"

    def __init__(
        self,
        email: str | None = None,
        api_key: str | None = None,
        timeout: float = 15.0,
    ):
        self.email = email or os.getenv("EPC_API_EMAIL")
        self.api_key = api_key or os.getenv("EPC_API_KEY")
        self.timeout = timeout
        # Overridable transport, so failure modes can be exercised in tests.
        self._transport: httpx.AsyncBaseTransport | None = None

    def is_configured(self) -> bool:
        return bool(self.email and self.api_key)

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout, transport=self._transport)

    def _require_configured(self) -> None:
        if not self.is_configured():
            raise EPCUpstreamError(
                "EPC service is not configured (set EPC_API_EMAIL and EPC_API_KEY). "
                "Absence of a certificate cannot be concluded."
            )

    async def _get_rows(self, url: str, params: dict | None = None) -> list[dict]:
        """Fetch and unwrap an EPC response, raising rather than degrading.

        Any non-success status (redirects included), transport error, parse
        failure, or unrecognised envelope raises EPCUpstreamError. Only a
        successful response whose envelope is understood yields rows — which
        may legitimately be empty.
        """
        self._require_configured()
        try:
            async with self._client() as client:
                resp = await client.get(
                    url,
                    params=params,
                    headers={"Accept": "application/json", **self._auth_header()},
                )
        except httpx.HTTPError as exc:
            raise EPCUpstreamError(f"EPC request to {url} failed: {exc}") from exc

        if resp.is_redirect or resp.status_code >= 300:
            raise EPCUpstreamError(
                f"EPC upstream returned HTTP {resp.status_code} for {url}"
                + (
                    f" (redirect to {resp.headers.get('Location')!r} — the API host may have moved)"
                    if resp.is_redirect
                    else ""
                )
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise EPCUpstreamError(
                f"EPC upstream returned a non-JSON body for {url}: {exc}"
            ) from exc

        if not isinstance(data, dict) or "rows" not in data:
            raise EPCUpstreamError(
                f"EPC upstream returned an unrecognised response envelope for {url} "
                f"(expected a 'rows' key, got keys: {sorted(data)[:6] if isinstance(data, dict) else type(data).__name__}). "
                "The upstream contract may have changed."
            )

        rows = data.get("rows") or []
        if not isinstance(rows, list):
            raise EPCUpstreamError(f"EPC upstream returned a non-list 'rows' for {url}")
        return rows

    def _auth_header(self) -> dict[str, str]:
        if not self.email or not self.api_key:
            return {}
        creds = base64.b64encode(f"{self.email}:{self.api_key}".encode()).decode()
        return {"Authorization": f"Basic {creds}"}

    async def get_certificate(
        self, certificate_hash: str
    ) -> Optional[EPCData]:
        """Get EPC certificate by lmk-key (certificate hash).

        Returns:
            EPCData, or None if the certificate genuinely does not exist.

        Raises:
            EPCUpstreamError: If the EPC service could not be consulted, so
                absence cannot be concluded.
        """
        rows = await self._get_rows(f"{self.BASE_URL}/domestic/certificate/{certificate_hash}")
        if not rows:
            return None
        return EPCData.from_api_row(rows[0])

    async def search_all_by_postcode(
        self, postcode: str
    ) -> list[EPCData]:
        """Return all parsed EPC certificates for a postcode.

        Useful for batch-matching multiple addresses against a single postcode's
        certificates (e.g. enriching PPD comparables with floor area).

        Returns:
            List of EPCData models. Empty means the postcode genuinely has no
            certificates lodged — never that the lookup failed.

        Raises:
            EPCUpstreamError: If the EPC service could not be consulted.
        """
        rows = await self._get_rows(
            f"{self.BASE_URL}/domestic/search",
            params={"postcode": postcode.replace(" ", "")},
        )
        return [EPCData.from_api_row(row) for row in rows]

    def match_address(
        self, certificates: list[EPCData], address: str, min_score: int = 30
    ) -> Optional[tuple[EPCData, int]]:
        """Find the best-matching certificate for an address from a pre-fetched list.

        Delegates to address_matching.match_epc_address().

        Args:
            certificates: List of EPCData models (from search_all_by_postcode).
            address: Address to match against.
            min_score: Minimum match score (0-100) to accept.

        Returns:
            Tuple of (EPCData, match_score) or None if no match meets threshold.
        """
        return match_epc_address(certificates, address, min_score=min_score)

    async def search_by_postcode(
        self, postcode: str, address: str | None = None
    ) -> Optional[EPCData]:
        """Search for EPC by postcode, optionally matching address.

        Returns:
            EPCData, or None if the postcode genuinely has no certificates (or
            none matched ``address``).

        Raises:
            EPCUpstreamError: If the EPC service could not be consulted.
        """
        rows = await self._get_rows(
            f"{self.BASE_URL}/domestic/search",
            params={"postcode": postcode.replace(" ", "")},
        )
        if not rows:
            return None

        if address:
            certs = [EPCData.from_api_row(row) for row in rows]
            result = match_epc_address(certs, address, min_score=30)
            if result:
                return result[0]  # return the EPCData
            return None  # BUG FIX: was falling through to rows[0]

        return EPCData.from_api_row(rows[0])
