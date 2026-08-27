"""
Lightweight wrapper for the HM Land Registry Price Paid Data (PPD) APIs.

This module provides access to UK property transaction data via:

1. **Download URLs** - S3-backed bulk dataset URLs (complete, yearly, monthly)

2. **Linked Data API** - JSON endpoint for individual transaction lookups by UUID

3. **SPARQL Search** - Unified query function supporting:
   - Postcode exact match (VALUES) or prefix/sector search (STRSTARTS)
   - Date range, price range filters
   - Address text matching (paon, street, town, etc.) via CONTAINS/LCASE
   - URI-based filters (property_type, estate_type, etc.) applied client-side
     to avoid 503 timeouts from the Land Registry endpoint

Key endpoints:
- S3: prod2.publicdata.landregistry.gov.uk
- Linked Data: landregistry.data.gov.uk/data/ppi/
- SPARQL: landregistry.data.gov.uk/landregistry/sparql

Reference: https://www.gov.uk/guidance/about-the-price-paid-data
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Dict, Optional

from property_core.models.ppd import PPDTransaction, PPDTransactionRecord
from property_core.postcode_rules import (
    matches_prefix,
    normalise_postcode,
    normalise_prefix,
    sparql_prefix,
)
from property_core.provenance import TransportEvidence

S3_BASE = "http://prod2.publicdata.landregistry.gov.uk.s3-website-eu-west-1.amazonaws.com"
LINKED_DATA_BASE = "https://landregistry.data.gov.uk"
SPARQL_ENDPOINT = "https://landregistry.data.gov.uk/landregistry/sparql"

SPARQL_RETRY_ATTEMPTS = 3
SPARQL_RETRY_BACKOFF_SECONDS = 0.5

# Property type codes match the CSV column values.
PROPERTY_TYPE_URIS: Dict[str, str] = {
    "D": "http://landregistry.data.gov.uk/def/common/detached",
    "S": "http://landregistry.data.gov.uk/def/common/semi-detached",
    "T": "http://landregistry.data.gov.uk/def/common/terraced",
    "F": "http://landregistry.data.gov.uk/def/common/flat-maisonette",
    "O": "http://landregistry.data.gov.uk/def/common/otherPropertyType",
}

ESTATE_TYPE_URIS: Dict[str, str] = {
    "F": "http://landregistry.data.gov.uk/def/common/freehold",
    "L": "http://landregistry.data.gov.uk/def/common/leasehold",
}

TRANSACTION_CATEGORY_URIS: Dict[str, str] = {
    "A": "http://landregistry.data.gov.uk/def/ppi/standardPricePaidTransaction",
    "B": "http://landregistry.data.gov.uk/def/ppi/additionalPricePaidTransaction",
}

RECORD_STATUS_URIS: Dict[str, str] = {
    "A": "http://landregistry.data.gov.uk/def/ppi/add",
    "C": "http://landregistry.data.gov.uk/def/ppi/change",
    "D": "http://landregistry.data.gov.uk/def/ppi/delete",
}


class UnsupportedRecordStatusFilterError(ValueError):
    """Raised when record_status filtering is requested on the SPARQL search path.

    SPARQL search returns PPDTransaction rows, which carry no record_status
    field. Filtering previously dereferenced the missing attribute and crashed
    with AttributeError on the first returned row.

    **Honest reason it stays disabled.** An earlier version of this docstring
    said the predicate exists only on the Linked Data endpoint and that the URI
    mapping was an unverified guess. Both claims were wrong: live evidence showed
    ``lrppi:recordStatus`` does exist on the SPARQL transaction and binds to
    ``.../ppi/add``. It remains rejected because it is not yet supported under
    the verified search and performance contract — the binding is not part of the
    required-binding chain this query is tuned around, and adding it has not been
    validated for the 503/timeout behaviour the rest of the filter set was shaped
    by. Rejecting is a scope decision, not an ontology unknown.
    """

# The Land Registry site currently splits some recent years into two files.
YEARS_WITH_PARTS = {2018, 2019, 2020, 2021, 2022, 2023}

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class SearchPage:
    """One page of results plus the evidence needed to judge completeness.

    Internal to the transport and service layers for now: deliberately NOT in
    ``property_core.__all__`` and not advertised as a stable library contract.
    ``sparql_search`` remains the compatibility list-returning method.
    """

    transactions: list["PPDTransaction"]
    evidence: "TransportEvidence"
    #: Rows the upstream returned that did not belong to the requested geography.
    #: Non-zero means the upstream filter was looser than our containment rule.
    contained_out: int = 0


def _validate_iso_date(s: str) -> str:
    """Validate that *s* looks like an ISO date (YYYY-MM-DD). Raises ValueError."""
    if not _ISO_DATE_RE.match(s):
        raise ValueError(f"Invalid ISO date: {s!r}")
    return s


def _validate_positive_int(n: int) -> int:
    """Validate that *n* is a non-negative integer. Raises ValueError/TypeError."""
    if not isinstance(n, int) or n < 0:
        raise ValueError(f"Expected non-negative int, got {n!r}")
    return n


def _clean(value: str) -> str:
    """Sanitize user input for SPARQL string literals."""
    return value.strip().lower().replace('"', "").replace("\\", "")


@dataclass
class PricePaidDataClient:
    s3_base: str = S3_BASE
    linked_data_base: str = LINKED_DATA_BASE
    sparql_endpoint: str = SPARQL_ENDPOINT
    user_agent: str = "ppd-wrapper/0.1"
    timeout: int = 120

    # --------
    # Download URLs
    # --------
    def complete_url(self, fmt: str = "csv") -> str:
        return f"{self.s3_base}/pp-complete.{fmt}"

    def monthly_change_url(self, fmt: str = "csv") -> str:
        return f"{self.s3_base}/pp-monthly-update-new-version.{fmt}"

    def year_url(self, year: int, *, part: Optional[int] = None, fmt: str = "csv") -> str:
        if part is not None and part not in (1, 2):
            raise ValueError("part must be 1 or 2 when provided")
        suffix = ""
        if part:
            suffix = f"-part{part}"
        return f"{self.s3_base}/pp-{year}{suffix}.{fmt}"

    # --------
    # Linked data helpers
    # --------
    def get_transaction_record(self, transaction_id: str, view: str = "all") -> PPDTransactionRecord:
        """Fetch a transaction record by its UUID from the Linked Data API.

        Three outcomes, kept strictly distinct:

        * ``primaryTopic`` is an object -> the record.
        * ``primaryTopic`` is a bare string URI -> the API's stub for an unknown
          id: ``TransactionNotFoundError``. Previously this reached
          ``primary.get(...)`` on a ``str`` and leaked ``AttributeError``.
        * transport or parse failure -> ``UpstreamUnavailableError``.

        A failed lookup is never reported as an absent record.
        """
        from property_core.exceptions import (
            TransactionNotFoundError,
            UpstreamShapeError,
            UpstreamUnavailableError,
        )

        endpoint = f"{self.linked_data_base}/data/ppi/transaction/{transaction_id}/current.json"
        url = f"{endpoint}?{urllib.parse.urlencode({'_view': view})}"
        try:
            raw = self._fetch_json(url)
        except Exception as exc:  # transport, timeout, or unparseable body
            raise UpstreamUnavailableError(
                f"transaction lookup failed: {type(exc).__name__}: {exc}"
            ) from exc

        if not isinstance(raw, dict):
            raise UpstreamShapeError(
                f"upstream returned {type(raw).__name__}, expected a JSON object"
            )
        result = raw.get("result")
        if not isinstance(result, dict):
            raise UpstreamShapeError(
                f"upstream 'result' is {type(result).__name__}, expected an object"
            )
        if "primaryTopic" not in result:
            raise UpstreamShapeError("upstream response has no 'primaryTopic'")

        primary = result["primaryTopic"]
        if isinstance(primary, str):
            # The ONE shape observed to mean "no such record": a bare URI stub
            # naming the transaction we asked for. An arbitrary string -- "",
            # "garbage", or a URI for a DIFFERENT transaction -- proves nothing
            # about this record's existence and must not become an absence.
            # PARSE the URI. A substring check accepted
            # https://evil.example/landregistry/data/ppi/transaction/<id>/current
            # and turned an attacker- or proxy-supplied string into "this record
            # does not exist" -- a false statement about the world.
            #
            # The Linked Data URI namespace is http:// even though the API is
            # served over https, so scheme is allowed to differ; nothing else is.
            if self._is_not_found_stub(primary, transaction_id):
                raise TransactionNotFoundError(transaction_id)
            raise UpstreamShapeError(
                "'primaryTopic' is a string but not the not-found stub for the "
                "requested transaction"
            )
        if not isinstance(primary, dict):
            raise UpstreamShapeError(
                f"'primaryTopic' is {type(primary).__name__}, expected an object or the "
                "bare-URI not-found stub"
            )

        try:
            return PPDTransactionRecord.from_linked_data(raw)
        except (AttributeError, TypeError, ValueError) as exc:
            # A parse failure on a well-shaped object is our problem, never an
            # absence. AttributeError in particular must never become a 404.
            raise UpstreamShapeError(
                f"unusable record shape: {type(exc).__name__}: {exc}"
            ) from exc

    # --------
    # SPARQL search
    # --------
    def search_with_evidence(
        self,
        *,
        postcode: Optional[str] = None,
        postcode_prefix: Optional[str] = None,
        paon: Optional[str] = None,
        saon: Optional[str] = None,
        street: Optional[str] = None,
        town: Optional[str] = None,
        county: Optional[str] = None,
        locality: Optional[str] = None,
        district: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        property_type: Optional[str] = None,
        estate_type: Optional[str] = None,
        transaction_category: Optional[str] = None,
        record_status: Optional[str] = None,  # deprecated: raises if not None
        new_build: Optional[bool] = None,
        limit: int = 20,
        offset: int = 0,
        order_desc: bool = True,
    ) -> SearchPage:
        """
        Search Price Paid transactions via SPARQL, with completeness evidence.

        Supports postcode exact/prefix search, date/price ranges, address text
        matching (CONTAINS/LCASE), and URI-based filters (applied client-side
        to avoid 503 timeouts). Core transaction fields use required bindings
        (semicolon chain) — OPTIONAL bindings cause full table scans.

        Args:
            record_status: **Not supported here.** Passing a value raises
                UnsupportedRecordStatusFilterError. This search returns
                PPDTransaction rows, which carry no record status — that field
                exists only on PPDTransactionRecord, from the Linked Data
                endpoint. The parameter is kept so callers get this explanation
                rather than an opaque TypeError.

        Raises:
            UnsupportedRecordStatusFilterError: If record_status is not None.
        """
        if record_status is not None:
            raise UnsupportedRecordStatusFilterError(
                "record_status filtering is not supported on SPARQL search: results are "
                "PPDTransaction rows, which do not carry a record status. The predicate "
                "does exist upstream (lrppi:recordStatus), but is not yet supported under "
                "this search's verified binding and performance contract. Use "
                "PricePaidDataClient.get_transaction_record(transaction_id) / "
                "PPDService.transaction_record() to read record_status for a known transaction."
            )

        values_clauses = []
        filters = []

        # --- SPARQL-safe filters (postcode, date, price) ---

        # Use VALUES for exact postcode (more efficient than FILTER)
        if postcode is not None:
            safe_pc = normalise_postcode(postcode)
            values_clauses.append(f'VALUES ?postcode {{"{safe_pc}"^^xsd:string}}')

        # Use STRSTARTS filter for prefix search (VALUES can't do prefix).
        # An outcode carries its trailing space -- "B5" alone matches "B50 4AA",
        # which is Alcester, ~20 miles from inner Birmingham.
        normalised_prefix = None
        if postcode_prefix is not None:
            normalised_prefix = normalise_prefix(postcode_prefix)
            filters.append(
                f'FILTER(STRSTARTS(?postcode, "{sparql_prefix(normalised_prefix)}"))'
            )

        if from_date:
            _validate_iso_date(from_date)
            filters.append(f'FILTER(?transactionDate >= "{from_date}"^^xsd:date)')
        if to_date:
            _validate_iso_date(to_date)
            filters.append(f'FILTER(?transactionDate <= "{to_date}"^^xsd:date)')

        if min_price is not None:
            _validate_positive_int(min_price)
            filters.append(f"FILTER(?pricePaid >= {min_price})")
        if max_price is not None:
            _validate_positive_int(max_price)
            filters.append(f"FILTER(?pricePaid <= {max_price})")

        # --- Address text filters (CONTAINS/LCASE — fast with required bindings) ---
        if paon:
            filters.append(f'FILTER(CONTAINS(LCASE(?paon), "{_clean(paon)}"))')
        if saon:
            filters.append(f'FILTER(CONTAINS(LCASE(?saon), "{_clean(saon)}"))')
        if street:
            filters.append(f'FILTER(CONTAINS(LCASE(?street), "{_clean(street)}"))')
        if town:
            filters.append(f'FILTER(CONTAINS(LCASE(?town), "{_clean(town)}"))')
        if county:
            filters.append(f'FILTER(CONTAINS(LCASE(?county), "{_clean(county)}"))')
        if locality:
            filters.append(f'FILTER(CONTAINS(LCASE(?locality), "{_clean(locality)}"))')
        if district:
            filters.append(f'FILTER(CONTAINS(LCASE(?district), "{_clean(district)}"))')

        # --- Client-side filters (URI-based — cause 503 in SPARQL) ---
        has_client_filters = any([
            property_type, estate_type, transaction_category,
            new_build is not None,
        ])
        fetch_limit = limit * 3 if has_client_filters else limit

        order_clause = "ORDER BY DESC(?transactionDate)" if order_desc else "ORDER BY ?transactionDate"

        # Build query using official Land Registry pattern
        query = "\n".join(
            [
                "PREFIX lrppi: <http://landregistry.data.gov.uk/def/ppi/>",
                "PREFIX lrcommon: <http://landregistry.data.gov.uk/def/common/>",
                "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>",
                "",
                "SELECT ?transactionId ?pricePaid ?transactionDate ?postcode "
                "?propertyType ?estateType ?transactionCategory ?newBuild "
                "?paon ?saon ?street ?town ?county ?locality ?district",
                "WHERE {",
                # VALUES clauses first (most efficient)
                *values_clauses,
                "",
                # Core transaction binding
                "  ?transx lrppi:transactionId ?transactionId ;",
                "          lrppi:pricePaid ?pricePaid ;",
                "          lrppi:transactionDate ?transactionDate ;",
                "          lrppi:propertyAddress ?addr ;",
                "          lrppi:propertyType ?propertyType ;",
                "          lrppi:estateType ?estateType ;",
                "          lrppi:transactionCategory ?transactionCategory ;",
                "          lrppi:newBuild ?newBuild .",
                "",
                # Address - postcode required, others optional
                "  ?addr lrcommon:postcode ?postcode .",
                "  OPTIONAL { ?addr lrcommon:paon ?paon }",
                "  OPTIONAL { ?addr lrcommon:saon ?saon }",
                "  OPTIONAL { ?addr lrcommon:street ?street }",
                "  OPTIONAL { ?addr lrcommon:town ?town }",
                "  OPTIONAL { ?addr lrcommon:county ?county }",
                "  OPTIONAL { ?addr lrcommon:locality ?locality }",
                "  OPTIONAL { ?addr lrcommon:district ?district }",
                "",
                # Only SPARQL-safe filters (postcode, date, price)
                *filters,
                "}",
                order_clause,
                f"LIMIT {fetch_limit}",
                f"OFFSET {offset}",
            ]
        )

        encoded = urllib.parse.urlencode({"query": query}).encode()
        raw = self._fetch_sparql(encoded)
        bindings = raw.get("results", {}).get("bindings", [])
        results = [PPDTransaction.from_sparql_binding(b) for b in bindings]

        # Apply client-side filters (URI-based fields that cause 503 in SPARQL)
        if property_type:
            pt = property_type.upper()
            results = [t for t in results if t.property_type == pt]
        if estate_type:
            et = estate_type.upper()
            results = [t for t in results if t.estate_type == et]
        if transaction_category:
            tc = transaction_category.upper()
            results = [t for t in results if t.transaction_category == tc]
        # record_status is rejected up front (see the guard at the top of this
        # method) — PPDTransaction has no such field, so there is nothing to
        # filter on here.
        if new_build is not None:
            results = [t for t in results if t.new_build == new_build]

        # Defence in depth: even with the delimiter pushed upstream, verify
        # membership by PARSED geography. A permissive or changed upstream must
        # not be able to leak a neighbouring outcode into these results.
        contained_out = 0
        if normalised_prefix is not None:
            kept = [t for t in results if matches_prefix(t.postcode, normalised_prefix)]
            contained_out = len(results) - len(kept)
            results = kept

        return SearchPage(
            transactions=results[:limit],
            evidence=TransportEvidence(
                raw_bindings_returned=len(bindings), fetch_limit=fetch_limit
            ),
            contained_out=contained_out,
        )

    def sparql_search(self, **kwargs) -> list[PPDTransaction]:
        """Compatibility wrapper: the rows only.

        Kept as the stable list-returning method for existing callers. The
        service layer uses :meth:`search_with_evidence`, which additionally
        reports whether the upstream window was exhausted.
        """
        return self.search_with_evidence(**kwargs).transactions

    #: The one host whose not-found stub we honour.
    LINKED_DATA_HOST = "landregistry.data.gov.uk"

    @classmethod
    def _is_not_found_stub(cls, value: str, transaction_id: str) -> bool:
        """Whether `value` is the Linked Data not-found stub for this transaction.

        Strict by construction: anything we cannot fully account for is not a
        stub, because the cost of a false positive is telling a caller a
        transaction does not exist when we do not know that.
        """
        try:
            parts = urllib.parse.urlsplit(value.strip())
        except ValueError:
            return False
        if parts.scheme not in ("http", "https"):
            return False
        if parts.username or parts.password:
            return False
        if parts.query or parts.fragment:
            return False
        if (parts.hostname or "").lower() != cls.LINKED_DATA_HOST:
            return False
        try:
            port = parts.port
        except ValueError:
            return False
        if port not in (None, 80, 443):
            return False
        return parts.path == f"/data/ppi/transaction/{transaction_id}/current"

    # --------
    # Internals
    # --------
    def _fetch_json(self, url: str) -> Dict:
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.load(resp)

    def _fetch_sparql(self, encoded_query: bytes) -> Dict:
        last_exc: Exception | None = None
        for attempt in range(1, SPARQL_RETRY_ATTEMPTS + 1):
            req = urllib.request.Request(
                self.sparql_endpoint,
                data=encoded_query,
                headers={"Accept": "application/sparql-results+json", "User-Agent": self.user_agent},
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.load(resp)
            except urllib.error.HTTPError as exc:
                if exc.code not in {503}:
                    raise
                last_exc = exc
            except (TimeoutError, urllib.error.URLError) as exc:
                last_exc = exc

            if attempt < SPARQL_RETRY_ATTEMPTS:
                backoff = SPARQL_RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
                time.sleep(backoff)

        if last_exc:
            raise last_exc
        raise RuntimeError("SPARQL request failed without a captured exception.")
