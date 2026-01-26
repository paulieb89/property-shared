"""Domain models for Rightmove data."""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field


class RightmoveListing(BaseModel):
    """Normalized Rightmove listing row."""

    id: Any
    url: str
    price: Optional[int] = None
    currency: Optional[str] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    address: Optional[str] = None
    summary: Optional[str] = None
    property_type: Optional[str] = None
    agent_name: Optional[str] = None
    agent_branch: Optional[str] = None
    first_visible_date: Optional[str] = None
    images: List[str] = Field(default_factory=list)
    # Location
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    # Rental-specific fields (None for sales)
    let_available_date: Optional[str] = None
    price_frequency: Optional[str] = None  # "monthly", "weekly" for rentals
    students: Optional[bool] = None
    transaction_type: Optional[str] = None  # "rent" or "buy"
    # Raw __NEXT_DATA__ property dict (populated when include_raw=True)
    raw: Optional[dict[str, Any]] = None


class RightmoveListingDetail(BaseModel):
    """Full property detail from an individual Rightmove listing page."""

    id: Any
    url: str
    price: Optional[int] = None
    currency: Optional[str] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    address: Optional[str] = None
    description: Optional[str] = None
    property_type: Optional[str] = None
    property_sub_type: Optional[str] = None
    agent_name: Optional[str] = None
    agent_branch: Optional[str] = None
    first_visible_date: Optional[str] = None
    images: List[str] = Field(default_factory=list)
    floorplans: List[str] = Field(default_factory=list)
    # Location
    postcode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    # Tenure
    tenure_type: Optional[str] = None  # "FREEHOLD" / "LEASEHOLD"
    years_remaining_on_lease: Optional[int] = None
    # Living costs
    annual_service_charge: Optional[int] = None
    annual_ground_rent: Optional[int] = None
    ground_rent_review_period_years: Optional[int] = None
    ground_rent_percentage_increase: Optional[float] = None
    council_tax_band: Optional[str] = None
    # Size
    display_size: Optional[str] = None
    price_per_sqft: Optional[str] = None
    # Key features
    key_features: List[str] = Field(default_factory=list)
    # Listing history
    listing_update_reason: Optional[str] = None
    # Transport
    nearest_stations: List[dict[str, Any]] = Field(default_factory=list)
    # Rental-specific
    let_available_date: Optional[str] = None
    price_frequency: Optional[str] = None
    transaction_type: Optional[str] = None
    # Raw PAGE_MODEL.propertyData dict (populated when include_raw=True)
    raw: Optional[dict[str, Any]] = None
