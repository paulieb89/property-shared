"""Service wrapper for Land Registry PPD helpers."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from property_core.ppd_client import (
    ESTATE_TYPE_URIS,
    PROPERTY_TYPE_URIS,
    TRANSACTION_CATEGORY_URIS,
    PricePaidDataClient,
)

from app.schemas.ppd import (
    PPDCompsQuery,
    PPDCompsResponse,
    PPDDownloadURLResponse,
    PPDSearchResponse,
    PPDTransaction,
    PPDTransactionRecord,
    PPDTransactionRecordResponse,
)

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

PROPERTY_TYPE_BY_URI = {v: k for k, v in PROPERTY_TYPE_URIS.items()}
ESTATE_TYPE_BY_URI = {v: k for k, v in ESTATE_TYPE_URIS.items()}
TRANSACTION_CATEGORY_BY_URI = {v: k for k, v in TRANSACTION_CATEGORY_URIS.items()}


def _binding_value(binding: Dict[str, Any], key: str) -> Optional[str]:
    item = binding.get(key)
    if not isinstance(item, dict):
        return None
    return item.get("value")


def _parse_sparql_bindings(bindings: Iterable[Dict[str, Any]]) -> List[PPDTransaction]:
    results: List[PPDTransaction] = []
    for binding in bindings:
        price_raw = _binding_value(binding, "pricePaid")
        new_build_raw = _binding_value(binding, "newBuild")
        property_type_uri = _binding_value(binding, "propertyType")
        estate_type_uri = _binding_value(binding, "estateType")
        transaction_category_uri = _binding_value(binding, "transactionCategory")

        transaction = PPDTransaction(
            transaction_id=_binding_value(binding, "transactionId"),
            price=int(price_raw) if price_raw and price_raw.isdigit() else None,
            date=_binding_value(binding, "transactionDate"),
            postcode=_binding_value(binding, "postcode"),
            property_type=PROPERTY_TYPE_BY_URI.get(property_type_uri),
            estate_type=ESTATE_TYPE_BY_URI.get(estate_type_uri),
            transaction_category=TRANSACTION_CATEGORY_BY_URI.get(transaction_category_uri),
            new_build=(new_build_raw == "true") if new_build_raw is not None else None,
            paon=_binding_value(binding, "paon"),
            saon=_binding_value(binding, "saon"),
            street=_binding_value(binding, "street"),
            town=_binding_value(binding, "town"),
            county=_binding_value(binding, "county"),
        )
        results.append(transaction)
    return results


def _parse_comps_transactions(rows: Iterable[Dict[str, Any]]) -> List[PPDTransaction]:
    results: List[PPDTransaction] = []
    for row in rows:
        results.append(
            PPDTransaction(
                transaction_id=row.get("transaction_id"),
                price=row.get("price"),
                date=row.get("date"),
                postcode=row.get("postcode"),
                property_type=row.get("property_type"),
                estate_type=row.get("estate_type"),
                transaction_category=None,
                new_build=row.get("new_build"),
                paon=row.get("paon"),
                saon=row.get("saon"),
                street=row.get("street"),
                town=row.get("town"),
                county=row.get("county"),
            )
        )
    return results


def _label_from(node: Any) -> Optional[str]:
    if not isinstance(node, dict):
        return None
    labels = node.get("label")
    if isinstance(labels, list) and labels:
        first = labels[0]
        if isinstance(first, dict):
            return first.get("_value")
    return None


def _about_from(node: Any) -> Optional[str]:
    if isinstance(node, dict):
        return node.get("_about")
    if isinstance(node, str):
        return node
    return None


def _safe_int(value: Any) -> Optional[int]:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _normalize_transaction_record(raw: Dict[str, Any]) -> PPDTransactionRecord:
    result = raw.get("result", {}) if isinstance(raw, dict) else {}
    primary = result.get("primaryTopic", {}) if isinstance(result, dict) else {}

    property_type_node = primary.get("propertyType")
    estate_type_node = primary.get("estateType")
    category_node = primary.get("transactionCategory")
    record_status_node = primary.get("recordStatus")

    new_build_raw = primary.get("newBuild")
    if isinstance(new_build_raw, bool):
        new_build = new_build_raw
    elif isinstance(new_build_raw, str):
        new_build = new_build_raw.lower() == "true"
    else:
        new_build = None

    return PPDTransactionRecord(
        transaction_id=primary.get("transactionId"),
        transaction_uri=_about_from(primary),
        transaction_date=primary.get("transactionDate"),
        price_paid=_safe_int(primary.get("pricePaid")),
        new_build=new_build,
        property_address_uri=_about_from(primary.get("propertyAddress")),
        property_type=_label_from(property_type_node),
        property_type_uri=_about_from(property_type_node),
        estate_type=_label_from(estate_type_node),
        estate_type_uri=_about_from(estate_type_node),
        transaction_category=_label_from(category_node),
        transaction_category_uri=_about_from(category_node),
        record_status=_label_from(record_status_node),
        record_status_uri=_about_from(record_status_node),
        source_url=result.get("_about"),
    )


class PPDService:
    def __init__(self, client: Optional[PricePaidDataClient] = None):
        self.client = client or PricePaidDataClient()

    def download_url(
        self,
        *,
        kind: str,
        year: Optional[int],
        part: Optional[int],
        fmt: str,
    ) -> PPDDownloadURLResponse:
        if kind == "complete":
            url = self.client.complete_url(fmt=fmt)
        elif kind == "monthly":
            url = self.client.monthly_change_url(fmt=fmt)
        elif kind == "year":
            if year is None:
                raise ValueError("year is required when kind=year")
            url = self.client.year_url(year, part=part, fmt=fmt)
        else:
            raise ValueError("kind must be one of: complete, monthly, year")
        return PPDDownloadURLResponse(url=url)

    def search_transactions(
        self,
        *,
        postcode: Optional[str],
        postcode_prefix: Optional[str],
        from_date: Optional[str],
        to_date: Optional[str],
        min_price: Optional[int],
        max_price: Optional[int],
        property_type: Optional[str],
        estate_type: Optional[str],
        transaction_category: Optional[str],
        record_status: Optional[str],
        new_build: Optional[bool],
        limit: int,
        offset: int,
        order_desc: bool,
    ) -> PPDSearchResponse:
        warnings: List[str] = []

        if limit <= 0:
            limit = DEFAULT_LIMIT
        if limit > MAX_LIMIT:
            warnings.append(f"limit capped to {MAX_LIMIT}")
            limit = MAX_LIMIT

        raw = self.client.sparql_search(
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

        bindings = raw.get("results", {}).get("bindings", [])
        results = _parse_sparql_bindings(bindings)

        return PPDSearchResponse(
            count=len(results),
            limit=limit,
            offset=offset,
            results=results,
            warnings=warnings,
        )

    def comps(
        self,
        *,
        postcode: str,
        property_type: Optional[str],
        months: int,
        limit: int,
        search_level: str,
    ) -> PPDCompsResponse:
        if limit <= 0:
            limit = DEFAULT_LIMIT
        if limit > MAX_LIMIT:
            limit = MAX_LIMIT

        raw = self.client.get_comps_summary(
            postcode=postcode,
            property_type=property_type,
            months=months,
            limit=limit,
            search_level=search_level,
        )

        query = PPDCompsQuery(
            postcode=raw["query"]["postcode"],
            property_type=raw["query"]["property_type"],
            months=raw["query"]["months"],
            search_level=raw["query"]["search_level"],
        )
        transactions = _parse_comps_transactions(raw.get("transactions", []))

        return PPDCompsResponse(
            query=query,
            count=raw["count"],
            median=raw["median"],
            mean=raw["mean"],
            min=raw["min"],
            max=raw["max"],
            thin_market=raw["thin_market"],
            transactions=transactions,
        )

    def transaction_record(
        self,
        transaction_id: str,
        view: str = "all",
        include_raw: bool = False,
    ) -> PPDTransactionRecordResponse:
        raw = self.client.get_transaction_record(transaction_id, view=view)
        record = _normalize_transaction_record(raw)
        return PPDTransactionRecordResponse(record=record, raw=raw if include_raw else None)
