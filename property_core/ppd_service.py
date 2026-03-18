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
            return self.client.form_search(
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
        months: int = 24,
        limit: int = DEFAULT_LIMIT,
        search_level: str = "sector",
        address: Optional[str] = None,
        auto_escalate: bool = False,
    ) -> PPDCompsResponse:
        """Return comparable sales and summary stats for a postcode.

        If address is provided, also returns subject_property with its transaction history.

        All stats (median, mean, percentiles, min, max) are computed from the
        final filtered transaction list — after property-type filtering and
        subject-property removal — so they are always consistent.
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

        # 2. Fetch transactions via SPARQL
        from_date = (date.today() - timedelta(days=months * 30)).isoformat()
        fetch_limit = limit * 3 if property_type else limit

        all_transactions = self.client.sparql_search(
            postcode=exact_postcode,
            postcode_prefix=prefix,
            from_date=from_date,
            limit=fetch_limit,
            order_desc=True,
        )

        # 3. Client-side property_type filter (SPARQL filter causes 503)
        if property_type:
            pt = property_type.upper()
            all_transactions = [t for t in all_transactions if t.property_type == pt]
        transactions = all_transactions[:limit]

        # 4. Subject property matching
        subject_property = None
        if address:
            subject_property = self._find_subject_property(postcode, address)
            if subject_property and subject_property.transaction_history:
                subject_ids = {t.transaction_id for t in subject_property.transaction_history}
                transactions = [t for t in transactions if t.transaction_id not in subject_ids]

        # 5. Compute ALL stats from the final filtered list (fixes stats bug)
        transactions = [t for t in transactions if t.price is not None]
        prices = [t.price for t in transactions]
        count = len(transactions)

        computed_median = int(median(prices)) if prices else None
        computed_mean = int(round(mean(prices))) if prices else None
        p25 = None
        p75 = None
        if len(prices) >= 4:
            q = quantiles(prices, n=4)
            p25 = int(round(q[0]))
            p75 = int(round(q[2]))

        # 6. Subject comparison
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
            thin_market=count < 5,
            transactions=transactions,
            subject_property=subject_property,
            subject_price_percentile=subject_price_percentile,
            subject_vs_median_pct=subject_vs_median_pct,
        )

        # Auto-escalate to wider search area if thin market
        if auto_escalate and response.thin_market and response.count < 5:
            next_level = {"postcode": "sector", "sector": "district"}.get(search_level)
            if next_level:
                wider = self.comps(
                    postcode=postcode,
                    property_type=property_type,
                    months=months,
                    limit=limit,
                    search_level=next_level,
                    address=address,
                    auto_escalate=True,
                )
                wider.escalated_from = search_level
                wider.escalated_to = wider.query.search_level
                return wider

        return response

    def _find_subject_property(
        self, postcode: str, address: str
    ) -> Optional[SubjectProperty]:
        """Search for a specific property by postcode and address."""
        address_clean = address.strip()

        # Try to extract PAON (building number/name) from start of address
        parts = address_clean.split(",")
        first_part = parts[0].strip()

        # Split first part into potential PAON and street
        words = first_part.split()
        paon = None
        street = None

        if words:
            # If first word is a number or looks like a building number, use it as PAON
            if words[0].isdigit() or (len(words[0]) <= 4 and any(c.isdigit() for c in words[0])):
                paon = words[0]
                street = " ".join(words[1:]) if len(words) > 1 else None
            else:
                # Might be a building name like "Rose Cottage"
                street = first_part

        try:
            # Search for this specific property
            transactions = self.client.form_search(
                postcode=postcode,
                paon=paon,
                street=street,
                limit=50,  # Get full history
            )

            if not transactions:
                # Try with just postcode and full address as street
                transactions = self.client.form_search(
                    postcode=postcode,
                    street=address_clean,
                    limit=50,
                )

            if transactions:
                # Sort by date descending
                transactions.sort(key=lambda t: t.date or "", reverse=True)

                # Build formatted address from first transaction
                first = transactions[0]
                addr_parts = []
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
                    last_sale=transactions[0] if transactions else None,
                    transaction_count=len(transactions),
                    transaction_history=transactions,
                )
        except Exception:
            # If search fails, return None (don't fail the whole comps request)
            pass

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
