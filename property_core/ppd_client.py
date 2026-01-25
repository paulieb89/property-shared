"""
Lightweight wrapper for the HM Land Registry Price Paid Data (PPD) APIs.

This module provides access to UK property transaction data via three methods:

1. **Bulk Downloads** - CSV/TXT files from the S3-backed public data host
   - Complete dataset (~5GB, 28M+ transactions since 1995)
   - Yearly files (with part1/part2 variants for recent years)
   - Monthly change files (additions/changes/deletions)

2. **Linked Data API** - JSON endpoints for individual lookups
   - Transaction records by UUID
   - Address details by URI or ID

3. **SPARQL Search** - Filtered queries against the RDF dataset
   - Uses official Land Registry query patterns (VALUES, OPTIONAL blocks)
   - Returns full address details (paon, saon, street, town, county)
   - Note: Property type filtering done client-side to avoid 503 errors

Key endpoints:
- S3: prod2.publicdata.landregistry.gov.uk
- Linked Data: landregistry.data.gov.uk/data/ppi/
- SPARQL: landregistry.data.gov.uk/landregistry/sparql

Reference: https://www.gov.uk/guidance/about-the-price-paid-data
"""

from __future__ import annotations

import json
import pathlib
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean, median, quantiles
from typing import Any, Dict, List, Optional

S3_BASE = "http://prod2.publicdata.landregistry.gov.uk.s3-website-eu-west-1.amazonaws.com"
LINKED_DATA_BASE = "https://landregistry.data.gov.uk"
SPARQL_ENDPOINT = "https://landregistry.data.gov.uk/landregistry/sparql"

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

# The Land Registry site currently splits some recent years into two files.
YEARS_WITH_PARTS = {2018, 2019, 2020, 2021, 2022, 2023}


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
    # Downloads
    # --------
    def download_to_file(self, url: str, dest_path: str | pathlib.Path, chunk_size: int = 1024 * 1024) -> pathlib.Path:
        dest = pathlib.Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp, dest.open("wb") as handle:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                handle.write(chunk)
        return dest

    # --------
    # Linked data helpers
    # --------
    def get_transaction_record(self, transaction_id: str, view: str = "all") -> Dict:
        """Fetch a transaction record by its UUID from the Linked Data API."""
        endpoint = f"{self.linked_data_base}/data/ppi/transaction/{transaction_id}/current.json"
        url = f"{endpoint}?{urllib.parse.urlencode({'_view': view})}"
        return self._fetch_json(url)

    def get_address(self, address_id_or_uri: str, view: str = "all") -> Dict:
        """Fetch address details by URI or ID. Returns paon, saon, street, town, etc."""
        if address_id_or_uri.startswith("http"):
            endpoint = address_id_or_uri
            if not endpoint.endswith(".json"):
                endpoint = endpoint + ".json"
        else:
            endpoint = f"{self.linked_data_base}/data/ppi/address/{address_id_or_uri}.json"
        url = f"{endpoint}?{urllib.parse.urlencode({'_view': view})}"
        return self._fetch_json(url)

    # --------
    # SPARQL search
    # --------
    def sparql_search(
        self,
        *,
        postcode: Optional[str] = None,
        postcode_prefix: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        property_type: Optional[str] = None,
        estate_type: Optional[str] = None,
        transaction_category: Optional[str] = None,
        record_status: Optional[str] = None,
        new_build: Optional[bool] = None,
        limit: int = 20,
        offset: int = 0,
        order_desc: bool = True,
    ) -> Dict:
        """
        Search Price Paid transactions via SPARQL.

        Uses official Land Registry query patterns with VALUES clause for exact matches
        and OPTIONAL blocks for address fields.
        """
        values_clauses = []
        filters = []

        # Use VALUES for exact postcode (more efficient than FILTER)
        if postcode:
            safe_pc = postcode.upper().replace('"', '').replace('\\', '')
            values_clauses.append(f'VALUES ?postcode {{"{safe_pc}"^^xsd:string}}')

        # Use STRSTARTS filter for prefix search (VALUES can't do prefix)
        if postcode_prefix:
            safe_prefix = postcode_prefix.upper().replace('"', '').replace('\\', '')
            filters.append(f'FILTER(STRSTARTS(?postcode, "{safe_prefix}"))')

        if from_date:
            filters.append(f'FILTER(?transactionDate >= "{from_date}"^^xsd:date)')
        if to_date:
            filters.append(f'FILTER(?transactionDate <= "{to_date}"^^xsd:date)')

        if min_price is not None:
            filters.append(f"FILTER(?pricePaid >= {min_price})")
        if max_price is not None:
            filters.append(f"FILTER(?pricePaid <= {max_price})")

        if property_type:
            uri = self._resolve_uri(property_type, PROPERTY_TYPE_URIS)
            if uri:
                filters.append(f"FILTER(?propertyType = <{uri}>)")

        if estate_type:
            uri = self._resolve_uri(estate_type, ESTATE_TYPE_URIS)
            if uri:
                filters.append(f"FILTER(?estateType = <{uri}>)")

        if transaction_category:
            uri = self._resolve_uri(transaction_category, TRANSACTION_CATEGORY_URIS)
            if uri:
                filters.append(f"FILTER(?transactionCategory = <{uri}>)")

        if record_status:
            uri = self._resolve_uri(record_status, RECORD_STATUS_URIS)
            if uri:
                filters.append(f"FILTER(?recordStatus = <{uri}>)")

        if new_build is not None:
            filters.append(f"FILTER(?newBuild = {'true' if new_build else 'false'})")

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
                # Filters
                *filters,
                "}",
                order_clause,
                f"LIMIT {limit}",
                f"OFFSET {offset}",
            ]
        )

        encoded = urllib.parse.urlencode({"query": query}).encode()
        req = urllib.request.Request(
            self.sparql_endpoint,
            data=encoded,
            headers={"Accept": "application/sparql-results+json", "User-Agent": self.user_agent},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.load(resp)

    # --------
    # Address-form search (web-form style)
    # --------
    def form_search(
        self,
        *,
        paon: Optional[str] = None,
        saon: Optional[str] = None,
        street: Optional[str] = None,
        town: Optional[str] = None,
        county: Optional[str] = None,
        postcode: Optional[str] = None,
        postcode_prefix: Optional[str] = None,
        limit: int = 25,
    ) -> Dict:
        """
        Search PPD using web-form style address filters.

        Requires at least two non-empty fields to avoid broad scans.
        Caps limit at 50 to protect the upstream service.
        """
        fields = {
            "paon": paon,
            "saon": saon,
            "street": street,
            "town": town,
            "county": county,
            "postcode": postcode,
            "postcode_prefix": postcode_prefix,
        }
        provided = {k: v for k, v in fields.items() if v}
        if len(provided) < 2:
            raise ValueError("Provide at least two address fields (e.g., postcode + street)")

        if limit <= 0:
            limit = 25
        limit = min(limit, 50)

        def _clean(value: str) -> str:
            return value.strip().lower().replace('"', "").replace("\\", "")

        filters: list[str] = []
        values_clauses: list[str] = []

        if postcode:
            safe_pc = _clean(postcode).upper()
            values_clauses.append(f'VALUES ?postcode {{"{safe_pc}"^^xsd:string}}')
        elif postcode_prefix:
            safe_prefix = _clean(postcode_prefix).upper()
            filters.append(f'FILTER(STRSTARTS(?postcode, "{safe_prefix}"))')

        if paon:
            safe = _clean(paon)
            filters.append(f'FILTER(CONTAINS(LCASE(?paon), "{safe}"))')
        if saon:
            safe = _clean(saon)
            filters.append(f'FILTER(CONTAINS(LCASE(?saon), "{safe}"))')
        if street:
            safe = _clean(street)
            filters.append(f'FILTER(CONTAINS(LCASE(?street), "{safe}"))')
        if town:
            safe = _clean(town)
            filters.append(f'FILTER(CONTAINS(LCASE(?town), "{safe}"))')
        if county:
            safe = _clean(county)
            filters.append(f'FILTER(CONTAINS(LCASE(?county), "{safe}"))')

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
                *values_clauses,
                "  ?transaction lrppi:pricePaid ?pricePaid .",
                "  ?transaction lrppi:transactionDate ?transactionDate .",
                "  ?transaction lrppi:propertyAddress ?addr .",
                "  OPTIONAL { ?transaction lrppi:propertyType ?propertyType }",
                "  OPTIONAL { ?transaction lrppi:estateType ?estateType }",
                "  OPTIONAL { ?transaction lrppi:transactionCategory ?transactionCategory }",
                "  OPTIONAL { ?transaction lrppi:newBuild ?newBuild }",
                "  ?addr lrcommon:postcode ?postcode .",
                "  OPTIONAL { ?addr lrcommon:paon ?paon }",
                "  OPTIONAL { ?addr lrcommon:saon ?saon }",
                "  OPTIONAL { ?addr lrcommon:street ?street }",
                "  OPTIONAL { ?addr lrcommon:town ?town }",
                "  OPTIONAL { ?addr lrcommon:county ?county }",
                "  OPTIONAL { ?addr lrcommon:locality ?locality }",
                "  OPTIONAL { ?addr lrcommon:district ?district }",
                *filters,
                "  BIND(STRAFTER(STR(?transaction), \"transaction/\") AS ?transactionId)",
                "}",
                "ORDER BY DESC(?transactionDate)",
                f"LIMIT {limit}",
                "OFFSET 0",
            ]
        )

        encoded = urllib.parse.urlencode({"query": query}).encode()
        req = urllib.request.Request(
            self.sparql_endpoint,
            data=encoded,
            headers={"Accept": "application/sparql-results+json", "User-Agent": self.user_agent},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.load(resp)

    # --------
    # Comps helper
    # --------
    def get_comps_summary(
        self,
        postcode: str,
        property_type: Optional[str] = None,
        months: int = 24,
        limit: int = 50,
        search_level: str = "sector",
    ) -> Dict[str, Any]:
        """
        Get comparable sales with summary statistics.

        Args:
            postcode: Target postcode (e.g., "DE12 6DZ")
            property_type: Filter by D/S/T/F/O (None = all types)
            months: Lookback period in months (default 24)
            limit: Max transactions to return (default 50)
            search_level: "postcode" (exact), "sector" (DE12 6), or "district" (DE12)

        Returns:
            Dict with keys:
                - query: search parameters used
                - count: number of transactions found
                - median: median price (None if no results)
                - mean: mean price (None if no results)
                - percentile_25: 25th percentile price (None if insufficient results)
                - percentile_75: 75th percentile price (None if insufficient results)
                - min: minimum price
                - max: maximum price
                - transactions: list of transaction dicts
                - thin_market: True if count < 5 (low confidence)
        """
        # Derive search prefix from postcode
        pc = postcode.upper().strip()
        if search_level == "postcode":
            prefix = None
            exact_postcode = pc
        elif search_level == "sector":
            # "DE12 6DZ" -> "DE12 6"
            parts = pc.split()
            if len(parts) == 2 and len(parts[1]) >= 1:
                prefix = f"{parts[0]} {parts[1][0]}"
            else:
                prefix = pc.split()[0] if pc else pc
            exact_postcode = None
        else:  # district
            prefix = pc.split()[0] if " " in pc else pc
            exact_postcode = None

        from_date = (date.today() - timedelta(days=months * 30)).isoformat()

        # Fetch transactions - DON'T filter property_type in SPARQL (causes 503)
        # Instead, fetch more results and filter client-side
        fetch_limit = limit * 3 if property_type else limit

        raw = self.sparql_search(
            postcode=exact_postcode,
            postcode_prefix=prefix,
            property_type=None,  # Filter in Python to avoid 503
            from_date=from_date,
            limit=fetch_limit,
            order_desc=True,
        )

        bindings = raw.get("results", {}).get("bindings", [])

        # Parse transactions
        transactions: List[Dict[str, Any]] = []
        prices: List[int] = []

        for b in bindings:
            # Extract property type code from URI
            pt_uri = b.get("propertyType", {}).get("value", "")
            pt_code = None
            for code, uri in PROPERTY_TYPE_URIS.items():
                if uri == pt_uri:
                    pt_code = code
                    break

            # Client-side filter for property_type (SPARQL filter causes 503)
            if property_type and pt_code != property_type.upper():
                continue

            # Stop if we've collected enough
            if len(transactions) >= limit:
                break

            price = int(b["pricePaid"]["value"])
            prices.append(price)

            # Extract estate type code from URI
            et_uri = b.get("estateType", {}).get("value", "")
            et_code = None
            for code, uri in ESTATE_TYPE_URIS.items():
                if uri == et_uri:
                    et_code = code
                    break

            # Build address from optional fields
            paon = b.get("paon", {}).get("value")
            saon = b.get("saon", {}).get("value")
            street = b.get("street", {}).get("value")
            town = b.get("town", {}).get("value")
            county = b.get("county", {}).get("value")

            transactions.append({
                "transaction_id": b["transactionId"]["value"],
                "price": price,
                "date": b["transactionDate"]["value"],
                "postcode": b["postcode"]["value"],
                "property_type": pt_code,
                "estate_type": et_code,
                "new_build": b.get("newBuild", {}).get("value") == "true",
                "paon": paon,
                "saon": saon,
                "street": street,
                "town": town,
                "county": county,
            })

        # Calculate stats
        count = len(prices)
        percentile_25 = None
        percentile_75 = None
        if len(prices) >= 4:
            q = quantiles(prices, n=4)
            percentile_25 = int(round(q[0]))
            percentile_75 = int(round(q[2]))
        result: Dict[str, Any] = {
            "query": {
                "postcode": postcode,
                "property_type": property_type,
                "months": months,
                "search_level": search_level,
                "from_date": from_date,
            },
            "count": count,
            "median": median(prices) if prices else None,
            "mean": round(mean(prices)) if prices else None,
            "percentile_25": percentile_25,
            "percentile_75": percentile_75,
            "min": min(prices) if prices else None,
            "max": max(prices) if prices else None,
            "transactions": transactions,
            "thin_market": count < 5,
        }

        return result

    # --------
    # Internals
    # --------
    def _fetch_json(self, url: str) -> Dict:
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.load(resp)

    @staticmethod
    def _resolve_uri(value: str, mapping: Dict[str, str]) -> Optional[str]:
        if value.startswith("http://") or value.startswith("https://"):
            return value
        key = value.upper()
        if key in mapping:
            return mapping[key]
        # Fall back to matching trailing fragment of the URI for convenience.
        lower = value.lower()
        for uri in mapping.values():
            if uri.rsplit("/", 1)[-1].lower() == lower:
                return uri
        return None
