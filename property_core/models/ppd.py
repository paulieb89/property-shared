"""Domain models for Price Paid Data."""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field


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
    min: Optional[int] = None
    max: Optional[int] = None
    thin_market: bool
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
