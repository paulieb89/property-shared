"""PPD domain service: orchestration over the typed transport client.

The transport client (PricePaidDataClient) now returns typed Pydantic models
directly. This service layer handles guardrails, search-level prefix logic,
stats computation, and subject-property matching. Sync throughout.
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import mean, median, quantiles
from typing import Any, Dict, List, Optional

from property_core.models.ppd import (
    PPDCompsQuery,
    PPDCompsResponse,
    PPDTransaction,
    SubjectProperty,
)
from property_core.ppd_client import PricePaidDataClient

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
FORM_MAX_LIMIT = 50

# Residential property type codes used for the default comps() residential filter.
# F=Flat, D=Detached, S=Semi, T=Terraced. O=Other (commercial/non-standard) is excluded
# unless the caller opts in via property_type="O" or property_type="ALL".
_RESIDENTIAL_TYPES = {"F", "D", "S", "T"}

# Sentinel for property_type meaning "no filter at all" — the raw firehose.
_PROPERTY_TYPE_ALL = "ALL"


class PPDService:
    """Domain service for PPD operations.

    Orchestrates PricePaidDataClient (which returns typed models) and adds
    guardrails, stats computation, and subject-property matching.
    All methods are synchronous.
    """
    def __init__(self, client: Optional[PricePaidDataClient] = None):
        self.client = client or PricePaidDataClient()

    def download_url(
        self,
        *,
        kind: str,
        year: Optional[int],
        part: Optional[int],
        fmt: str,
    ) -> str:
        """Resolve download URL for bulk PPD datasets. Returns the URL string."""
        if kind == "complete":
            return self.client.complete_url(fmt=fmt)
        elif kind == "monthly":
            return self.client.monthly_change_url(fmt=fmt)
        elif kind == "year":
            if year is None:
                raise ValueError("year is required when kind=year")
            return self.client.year_url(year, part=part, fmt=fmt)
        else:
            raise ValueError("kind must be one of: complete, monthly, year")

    def search_transactions(
        self,
        *,
        postcode: Optional[str],
        postcode_prefix: Optional[str],
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        property_type: Optional[str] = None,
        estate_type: Optional[str] = None,
        transaction_category: Optional[str] = None,
        record_status: Optional[str] = None,
        new_build: Optional[bool] = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
        order_desc: bool = True,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        """Search PPD via SPARQL with guardrails on limit/offset.

        Returns a dict with keys: count, limit, offset, results, warnings, raw.
        """
        warnings: List[str] = []

        if limit <= 0:
            limit = DEFAULT_LIMIT
        if limit > MAX_LIMIT:
            warnings.append(f"limit capped to {MAX_LIMIT}")
            limit = MAX_LIMIT

        results = self.client.sparql_search(
            postcode=postcode,
            postcode_prefix=postcode_prefix,
            from_date=from_date,
            to_date=to_date,
            min_price=min_price,
            max_price=max_price,
            property_type=property_type,
            estate_type=estate_type,
            transaction_category=transaction_category,
            record_status=record_status,
            new_build=new_build,
            limit=limit,
            offset=offset,
            order_desc=order_desc,
        )

        return {
            "count": len(results),
            "limit": limit,
            "offset": offset,
            "results": results,
            "warnings": warnings,
            "raw": [t.raw for t in results] if include_raw else None,
        }

    def address_search(
        self,
        *,
        paon: Optional[str] = None,
        saon: Optional[str] = None,
        street: Optional[str] = None,
        town: Optional[str] = None,
        county: Optional[str] = None,
        locality: Optional[str] = None,
        district: Optional[str] = None,
        postcode: Optional[str] = None,
        postcode_prefix: Optional[str] = None,
        limit: int = 25,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        """Address-form search with strict limits.

        Returns a dict with keys: count, limit, offset, results, warnings, raw.
        """
        warnings: List[str] = []
        if limit <= 0:
            limit = 25
        if limit > FORM_MAX_LIMIT:
            warnings.append(f"limit capped to {FORM_MAX_LIMIT}")
            limit = FORM_MAX_LIMIT

        def _run_search(search_town: Optional[str]) -> list[PPDTransaction]:
            return self.client.sparql_search(
                paon=paon,
                saon=saon,
                street=street,
                town=search_town,
                county=county,
                locality=locality,
                district=district,
                postcode=postcode,
                postcode_prefix=postcode_prefix,
                limit=limit,
                order_desc=True,
            )

        results: list[PPDTransaction] = []
        try:
            results = _run_search(town)
        except Exception:  # noqa: BLE001
            if town:
                warnings.append("town filter failed; retrying without town")
                results = _run_search(None)
            else:
                raise

        if town and not results:
            warnings.append("town filter returned no results; retrying without town")
            results = _run_search(None)

        return {
            "count": len(results),
            "limit": limit,
            "offset": 0,
            "results": results,
            "warnings": warnings,
            "raw": [t.raw for t in results] if include_raw else None,
        }

    def comps(
        self,
        *,
        postcode: str,
        property_type: Optional[str] = None,
        transaction_category: Optional[str] = "A",
        filter_outliers: bool = False,
        months: int = 24,
        limit: int = DEFAULT_LIMIT,
        search_level: str = "sector",
        address: Optional[str] = None,
        auto_escalate: bool = True,
        thin_market_threshold: int = 5,
    ) -> PPDCompsResponse:
        """Return comparable sales and summary stats for a postcode.

        Defaults are tuned for residential investment use cases:

        * ``transaction_category="A"`` — standard residential sales only.
          Pass ``None`` to include category-B (bulk transfers, non-standard
          conveyances) as well.
        * ``property_type=None`` — residential set (F/D/S/T). Pass a single
          code ("F"/"D"/"S"/"T"/"O") to filter to that one type, or the
          sentinel ``"ALL"`` to disable type filtering entirely (firehose).
        * ``filter_outliers=False`` — opt in to a 1.5*IQR price filter; when
          enabled, outlier transactions are dropped from BOTH the stats and
          the returned transaction list (needs >=4 prices, otherwise no-op).
        * ``auto_escalate=True`` — widen postcode→sector→district when the
          result set is below ``thin_market_threshold``.

        If address is provided, also returns subject_property with its
        transaction history.

        All stats (median, mean, percentiles, min, max) are computed from the
        final filtered transaction list — after property-type filtering,
        subject-property removal, and optional outlier filtering — so they
        are always consistent with the returned ``transactions``.
        """
        if limit <= 0:
            limit = DEFAULT_LIMIT
        if limit > MAX_LIMIT:
            limit = MAX_LIMIT

        # 1. Derive search prefix from postcode
        pc = postcode.upper().strip()
        if search_level == "postcode":
            prefix = None
            exact_postcode = pc
        elif search_level == "sector":
            parts = pc.split()
            if len(parts) == 2 and len(parts[1]) >= 1:
                prefix = f"{parts[0]} {parts[1][0]}"
            else:
                prefix = pc.split()[0] if pc else pc
            exact_postcode = None
        else:  # district
            prefix = pc.split()[0] if " " in pc else pc
            exact_postcode = None

        # 2. Resolve the property_type argument into a SPARQL filter value
        # and a post-fetch residential filter flag.
        #
        #   None       -> fetch all types, post-filter to F/D/S/T
        #   "ALL"      -> fetch all types, no post-filter (firehose)
        #   "F"/"D"/"S"/"T"/"O" -> push down to SPARQL, no post-filter
        if property_type is None:
            sparql_property_type: Optional[str] = None
            apply_residential_filter = True
        elif property_type == _PROPERTY_TYPE_ALL:
            sparql_property_type = None
            apply_residential_filter = False
        else:
            sparql_property_type = property_type
            apply_residential_filter = False

        # 3. Fetch transactions via SPARQL (client handles post-fetch filtering)
        from_date = (date.today() - timedelta(days=months * 30)).isoformat()

        transactions = self.client.sparql_search(
            postcode=exact_postcode,
            postcode_prefix=prefix,
            from_date=from_date,
            property_type=sparql_property_type,
            transaction_category=transaction_category,
            limit=limit,
            order_desc=True,
        )

        # 4. Apply residential post-filter when property_type=None.
        # transaction_category filtering happens server-side via SPARQL above.
        if apply_residential_filter:
            transactions = [t for t in transactions if t.property_type in _RESIDENTIAL_TYPES]

        # 5. Subject property matching
        subject_property = None
        if address:
            subject_property = self._find_subject_property(postcode, address)
            if subject_property and subject_property.transaction_history:
                subject_ids = {t.transaction_id for t in subject_property.transaction_history}
                transactions = [t for t in transactions if t.transaction_id not in subject_ids]

        # 6. Drop priceless rows before stats / outlier filtering.
        transactions = [t for t in transactions if t.price is not None]

        # 7. Optional IQR outlier filter (1.5 * IQR rule, needs >= 4 prices).
        # Filter both the stats list and the returned transactions, so the
        # response remains internally consistent.
        if filter_outliers and len(transactions) >= 4:
            prices_for_iqr = [t.price for t in transactions]
            q = quantiles(prices_for_iqr, n=4)
            q1, q3 = q[0], q[2]
            iqr = q3 - q1
            lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            transactions = [t for t in transactions if lo <= t.price <= hi]

        prices = [t.price for t in transactions]
        count = len(transactions)

        # 8. Compute ALL stats from the final filtered list (fixes stats bug)
        computed_median = int(median(prices)) if prices else None
        computed_mean = int(round(mean(prices))) if prices else None
        p25 = None
        p75 = None
        if len(prices) >= 4:
            q = quantiles(prices, n=4)
            p25 = int(round(q[0]))
            p75 = int(round(q[2]))

        # 9. Subject comparison
        subject_price_percentile = None
        subject_vs_median_pct = None
        last_sale_price = (
            subject_property.last_sale.price
            if subject_property and subject_property.last_sale
            else None
        )
        if last_sale_price is not None and prices:
            below = sum(1 for p in prices if p < last_sale_price)
            subject_price_percentile = int((below / len(prices)) * 100)
            if isinstance(computed_median, int) and computed_median > 0:
                subject_vs_median_pct = round(
                    ((last_sale_price - computed_median) / computed_median) * 100, 1
                )

        query = PPDCompsQuery(
            postcode=postcode,
            property_type=property_type,
            months=months,
            search_level=search_level,
            address=address,
        )

        response = PPDCompsResponse(
            query=query,
            count=count,
            median=computed_median,
            mean=computed_mean,
            percentile_25=p25,
            percentile_75=p75,
            min=min(prices) if prices else None,
            max=max(prices) if prices else None,
            thin_market=count < thin_market_threshold,
            transactions=transactions,
            subject_property=subject_property,
            subject_price_percentile=subject_price_percentile,
            subject_vs_median_pct=subject_vs_median_pct,
        )

        # Auto-escalate to wider search area if thin market.
        # Preserve caller's intent for property_type / transaction_category /
        # filter_outliers — pass them through verbatim.
        if auto_escalate and response.thin_market:
            next_level = {"postcode": "sector", "sector": "district"}.get(search_level)
            if next_level:
                wider = self.comps(
                    postcode=postcode,
                    property_type=property_type,
                    transaction_category=transaction_category,
                    filter_outliers=filter_outliers,
                    months=months,
                    limit=limit,
                    search_level=next_level,
                    address=address,
                    auto_escalate=True,
                    thin_market_threshold=thin_market_threshold,
                )
                wider.escalated_from = search_level
                wider.escalated_to = wider.query.search_level
                return wider

        return response

    def _find_subject_property(
        self, postcode: str, address: str
    ) -> Optional[SubjectProperty]:
        """Search for a specific property by postcode and address.

        Returns None rather than an ambiguous guess when:
          - the address lacks a parseable PAON (house number), or
          - the query returns transactions spanning multiple buildings, or
          - the SPARQL search fails for any reason.

        This is deliberate: a SubjectProperty represents one specific
        building. Callers that pass vague input (e.g. just a street name)
        get None, not the most-recent sale on the street labelled as "theirs".
        """
        paon = self._parse_paon(address)
        if paon is None:
            # No house number → can't identify a specific property
            return None

        # Use the part of the address after the PAON as the street filter
        address_clean = address.strip().split(",")[0].strip()
        words = address_clean.split()
        street = " ".join(words[1:]) if len(words) > 1 else None

        try:
            transactions = self.client.sparql_search(
                postcode=postcode,
                paon=paon,
                street=street,
                limit=50,
                order_desc=True,
            )
        except Exception:
            # Upstream failure — don't break the whole comps request
            return None

        if not transactions:
            return None

        # Uniqueness check: all matched transactions must represent the same
        # building. If CONTAINS matching returned multiple distinct houses,
        # the input was ambiguous and we should not guess.
        identities = {(t.paon, t.street) for t in transactions}
        if len(identities) != 1:
            return None

        # Sort by date desc — most recent sale first
        transactions.sort(key=lambda t: t.date or "", reverse=True)
        first = transactions[0]

        addr_parts: list[str] = []
        if first.paon:
            addr_parts.append(first.paon)
        if first.saon:
            addr_parts.append(first.saon)
        if first.street:
            addr_parts.append(first.street)
        if first.town:
            addr_parts.append(first.town)
        formatted_address = ", ".join(addr_parts) if addr_parts else address_clean

        return SubjectProperty(
            address=formatted_address,
            postcode=first.postcode or postcode,
            last_sale=first,
            transaction_count=len(transactions),
            transaction_history=transactions,
        )

    @staticmethod
    def _parse_paon(address: str) -> Optional[str]:
        """Extract a house number (PAON) from the start of an address.

        Returns None for addresses without a leading numeric token — i.e.
        bare street names, substrings, or building-name-only inputs. This
        is the parse-gate that prevents ambiguous queries.

        Examples:
            "39 Havenwood Rise"     -> "39"
            "42a High Street"       -> "42a"
            "Flat 4, 39 High St"    -> "39"  (falls through to second token)
            "Havenwood Rise"        -> None
            "Rose Cottage"          -> None
            "haven"                 -> None
        """
        parts = [p.strip() for p in address.strip().split(",")]
        # Walk through comma-separated parts looking for one starting with a digit.
        # This handles "Flat 4, 39 High Street" where the first part is the flat
        # and the second part has the PAON.
        for part in parts:
            if not part:
                continue
            words = part.split()
            if not words:
                continue
            first = words[0]
            # Accept: "39", "42a", "1b" — leading digit, short, alphanumeric
            if first[0].isdigit():
                return first
        return None

    def transaction_record(
        self,
        transaction_id: str,
        view: str = "all",
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        """Fetch a single transaction record and normalize the result.

        Returns dict with keys: record (PPDTransactionRecord), raw (optional).
        """
        record = self.client.get_transaction_record(transaction_id, view=view)
        return {"record": record, "raw": record.raw if include_raw else None}
