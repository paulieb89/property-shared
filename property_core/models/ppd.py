"""Domain models for Price Paid Data."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# --- URI-to-code reverse mappings ---

_PROPERTY_TYPE_BY_URI: Dict[str, str] = {
    "http://landregistry.data.gov.uk/def/common/detached": "D",
    "http://landregistry.data.gov.uk/def/common/semi-detached": "S",
    "http://landregistry.data.gov.uk/def/common/terraced": "T",
    "http://landregistry.data.gov.uk/def/common/flat-maisonette": "F",
    "http://landregistry.data.gov.uk/def/common/otherPropertyType": "O",
}
_ESTATE_TYPE_BY_URI: Dict[str, str] = {
    "http://landregistry.data.gov.uk/def/common/freehold": "F",
    "http://landregistry.data.gov.uk/def/common/leasehold": "L",
}
_TRANSACTION_CATEGORY_BY_URI: Dict[str, str] = {
    "http://landregistry.data.gov.uk/def/ppi/standardPricePaidTransaction": "A",
    "http://landregistry.data.gov.uk/def/ppi/additionalPricePaidTransaction": "B",
}


# --- Helpers ---

def _binding_val(binding: Dict[str, Any], key: str) -> Optional[str]:
    """Extract a SPARQL binding value (or None)."""
    item = binding.get(key)
    if not isinstance(item, dict):
        return None
    return item.get("value")


def _safe_int(val: Any) -> Optional[int]:
    """Coerce val to int, or None if empty/missing/invalid."""
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _label_from(node: Any) -> Optional[str]:
    """Get the first English label from a linked-data node."""
    if not isinstance(node, dict):
        return None
    labels = node.get("label")
    if isinstance(labels, list) and labels:
        first = labels[0]
        if isinstance(first, dict):
            return first.get("_value")
    return None


def _about_from(node: Any) -> Optional[str]:
    """Get the _about URI from a linked-data node or URI string."""
    if isinstance(node, dict):
        return node.get("_about")
    if isinstance(node, str):
        return node
    return None


class PPDTransaction(BaseModel):
    """Flat transaction row for PPD search/comps."""
    transaction_id: Optional[str] = None
    price: Optional[int] = None
    date: Optional[str] = None
    postcode: Optional[str] = None
    property_type: Optional[str] = None
    estate_type: Optional[str] = None
    transaction_category: Optional[str] = None
    new_build: Optional[bool] = None
    paon: Optional[str] = None
    saon: Optional[str] = None
    street: Optional[str] = None
    town: Optional[str] = None
    county: Optional[str] = None
    locality: Optional[str] = None
    district: Optional[str] = None
    # EPC enrichment fields (populated when enrich_epc=True on comps endpoint)
    epc_match: Optional[dict[str, Any]] = None
    epc_match_score: Optional[int] = None
    epc_floor_area_sqm: Optional[float] = None
    epc_floor_area_sqft: Optional[int] = None
    price_per_sqm: Optional[int] = None
    price_per_sqft: Optional[int] = None
    epc_rating: Optional[str] = None
    epc_score: Optional[int] = None
    epc_construction_age: Optional[str] = None
    epc_built_form: Optional[str] = None
    # Raw SPARQL binding dict (populated by from_sparql_binding)
    raw: Optional[dict[str, Any]] = None

    @classmethod
    def from_sparql_binding(cls, binding: Dict[str, Any]) -> PPDTransaction:
        """Construct a PPDTransaction from a SPARQL result binding.

        Each field in the binding dict is shaped like:
        ``{"type": "literal", "value": "..."}``
        """
        price_raw = _binding_val(binding, "pricePaid")
        new_build_raw = _binding_val(binding, "newBuild")
        property_type_uri = _binding_val(binding, "propertyType")
        estate_type_uri = _binding_val(binding, "estateType")
        transaction_category_uri = _binding_val(binding, "transactionCategory")

        return cls(
            transaction_id=_binding_val(binding, "transactionId"),
            price=int(price_raw) if price_raw and price_raw.isdigit() else None,
            date=_binding_val(binding, "transactionDate"),
            postcode=_binding_val(binding, "postcode"),
            property_type=_PROPERTY_TYPE_BY_URI.get(property_type_uri) if property_type_uri else None,
            estate_type=_ESTATE_TYPE_BY_URI.get(estate_type_uri) if estate_type_uri else None,
            transaction_category=_TRANSACTION_CATEGORY_BY_URI.get(transaction_category_uri) if transaction_category_uri else None,
            new_build=(new_build_raw == "true") if new_build_raw is not None else None,
            paon=_binding_val(binding, "paon"),
            saon=_binding_val(binding, "saon"),
            street=_binding_val(binding, "street"),
            town=_binding_val(binding, "town"),
            county=_binding_val(binding, "county"),
            locality=_binding_val(binding, "locality"),
            district=_binding_val(binding, "district"),
            raw=binding,
        )


class PPDCompsQuery(BaseModel):
    """Echo of comps query parameters."""
    postcode: str
    property_type: Optional[str] = None
    months: int
    search_level: str
    address: Optional[str] = None


class SubjectProperty(BaseModel):
    """Subject property details for comps context."""
    address: str
    postcode: str
    last_sale: Optional[PPDTransaction] = None
    transaction_count: int = 0
    transaction_history: List[PPDTransaction] = Field(default_factory=list)


class PPDCompsResponse(BaseModel):
    """Comps summary with transactions list."""
    query: PPDCompsQuery
    count: int
    median: Optional[int] = None
    mean: Optional[int] = None
    percentile_25: Optional[int] = None
    percentile_75: Optional[int] = None
    min: Optional[int] = None
    max: Optional[int] = None
    thin_market: bool
    # EPC-enriched stats (populated when enrich_epc=True on callers)
    median_price_per_sqft: Optional[int] = None
    epc_match_rate: Optional[float] = None
    # Subject comparison (populated when address provided and subject found)
    subject_price_percentile: Optional[int] = None
    subject_vs_median_pct: Optional[float] = None
    transactions: List[PPDTransaction] = Field(default_factory=list)
    subject_property: Optional[SubjectProperty] = None


class PPDTransactionRecord(BaseModel):
    """Normalized transaction record from the Linked Data API."""
    transaction_id: Optional[str] = None
    transaction_uri: Optional[str] = None
    transaction_date: Optional[str] = None
    price_paid: Optional[int] = None
    new_build: Optional[bool] = None
    property_address_uri: Optional[str] = None
    property_type: Optional[str] = None
    property_type_uri: Optional[str] = None
    estate_type: Optional[str] = None
    estate_type_uri: Optional[str] = None
    transaction_category: Optional[str] = None
    transaction_category_uri: Optional[str] = None
    record_status: Optional[str] = None
    record_status_uri: Optional[str] = None
    source_url: Optional[str] = None
    # Raw Linked Data API response dict (populated by from_linked_data)
    raw: Optional[dict[str, Any]] = None

    @classmethod
    def from_linked_data(cls, raw: Dict[str, Any]) -> PPDTransactionRecord:
        """Construct a PPDTransactionRecord from a Linked Data API response.

        Encapsulates the normalization logic for linked-data JSON, extracting
        property_type, estate_type, transaction_category from nested nodes.
        """
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

        return cls(
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
            raw=raw,
        )
