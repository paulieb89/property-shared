"""Domain models for Rightmove data."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# --- Pure mapping helpers (moved from rightmove_scraper.py) ---

def _safe_int(val: Any) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _safe_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _round_distance(val: Any, decimals: int = 1) -> Optional[float]:
    """Round a distance value to specified decimal places."""
    if val is None:
        return None
    try:
        return round(float(val), decimals)
    except (ValueError, TypeError):
        return None


def _extract_images(data: Dict[str, Any]) -> List[str]:
    images: List[str] = []
    image_sources = data.get("propertyImages") or data.get("images") or []
    if isinstance(image_sources, dict):
        image_sources = image_sources.get("images") or []
    for img in image_sources:
        if isinstance(img, dict):
            url = img.get("srcUrl") or img.get("url")
            if url:
                images.append(url)
    if not images:
        primary = data.get("displayImageUrl") or data.get("displayImage")
        if primary:
            images.append(primary)
    return images


def _extract_floorplans(data: Dict[str, Any]) -> List[str]:
    """Extract floorplan image URLs from propertyData."""
    floorplans: List[str] = []
    for fp in data.get("floorplans") or []:
        if isinstance(fp, dict):
            url = fp.get("url") or fp.get("src")
            if url:
                floorplans.append(url)
    return floorplans


def _extract_display_size(data: Dict[str, Any]) -> Optional[str]:
    """Extract display size string from propertyData."""
    # Direct string field
    ds = data.get("displaySize")
    if isinstance(ds, str) and ds:
        return ds
    # Try infoReelItems first (nicely formatted): [{"type": "SIZE", "primaryText": "1,195 sq ft"}]
    info_reel = data.get("infoReelItems")
    if isinstance(info_reel, list):
        for item in info_reel:
            if isinstance(item, dict) and item.get("type") == "SIZE":
                primary = item.get("primaryText")
                if primary:
                    return primary
    # Sizings list: [{"unit": "sqft", "minimumSize": 1195, "maximumSize": 1195, "displayUnit": "sq. ft."}]
    sizings = data.get("sizings")
    if isinstance(sizings, list) and sizings:
        # Prefer sqft, fallback to first available
        for preferred_unit in ["sqft", "sqm"]:
            for s in sizings:
                if isinstance(s, dict) and s.get("unit") == preferred_unit:
                    size_val = s.get("minimumSize") or s.get("maximumSize") or s.get("displaySize")
                    display_unit = s.get("displayUnit", preferred_unit)
                    if size_val:
                        # Format with commas for readability
                        if isinstance(size_val, (int, float)) and size_val >= 1000:
                            return f"{size_val:,.0f} {display_unit}".strip()
                        return f"{size_val} {display_unit}".strip()
    return None


def _extract_key_features(data: Dict[str, Any]) -> List[str]:
    """Extract key features list from propertyData."""
    features: List[str] = []
    for item in data.get("keyFeatures") or []:
        if isinstance(item, dict):
            desc = item.get("description") or item.get("htmlDescription")
            if desc:
                features.append(desc)
        elif isinstance(item, str):
            features.append(item)
    return features


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
    # Status tags (SOLD_STC, UNDER_OFFER, LET_AGREED, etc.)
    listing_status: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    # Rental-specific fields (None for sales)
    let_available_date: Optional[str] = None
    price_frequency: Optional[str] = None  # "monthly", "weekly" for rentals
    students: Optional[bool] = None
    transaction_type: Optional[str] = None  # "rent" or "buy"
    # Raw __NEXT_DATA__ property dict (populated when include_raw=True)
    raw: Optional[dict[str, Any]] = None

    @classmethod
    def from_next_data(cls, data: Dict[str, Any]) -> RightmoveListing:
        """Construct a RightmoveListing from a __NEXT_DATA__ property dict.

        Always stores the raw data.
        """
        price_info = data.get("price") or {}
        property_url = data.get("propertyUrl") or ""
        customer = data.get("customer") or {}
        location = data.get("location") or {}
        tags = data.get("tags") or []
        return cls(
            id=data.get("id"),
            url=f"https://www.rightmove.co.uk{property_url}",
            price=price_info.get("amount"),
            currency=price_info.get("currencyCode"),
            bedrooms=data.get("bedrooms"),
            bathrooms=data.get("bathrooms"),
            address=data.get("displayAddress"),
            summary=data.get("summary"),
            property_type=data.get("propertyTypeFullDescription") or data.get("propertySubType"),
            agent_name=customer.get("branchDisplayName"),
            agent_branch=customer.get("branchLandingPageUrl"),
            first_visible_date=data.get("firstVisibleDate"),
            images=_extract_images(data),
            latitude=_safe_float(location.get("latitude")),
            longitude=_safe_float(location.get("longitude")),
            listing_status=tags[0] if tags else None,
            tags=tags,
            # Rental-specific fields
            let_available_date=data.get("letAvailableDate"),
            price_frequency=price_info.get("frequency"),
            students=data.get("students"),
            transaction_type=data.get("transactionType"),
            raw=data,
        )


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
    # Status tags (SOLD_STC, UNDER_OFFER, LET_AGREED, etc.)
    listing_status: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    # Transport
    nearest_stations: List[dict[str, Any]] = Field(default_factory=list)
    # Rental-specific
    let_available_date: Optional[str] = None
    price_frequency: Optional[str] = None
    transaction_type: Optional[str] = None
    # Raw PAGE_MODEL.propertyData dict (populated when include_raw=True)
    raw: Optional[dict[str, Any]] = None

    @classmethod
    def from_page_model(cls, data: Dict[str, Any], url: str) -> RightmoveListingDetail:
        """Construct a RightmoveListingDetail from PAGE_MODEL propertyData.

        Always stores the raw data.
        """
        price_info = data.get("prices") or {}
        primary_price = (price_info.get("primaryPrice") or price_info.get("displayPrice") or "")
        # Try to get numeric price
        price_amount = _safe_int(price_info.get("amount"))
        if price_amount is None:
            # Parse from primaryPrice string (e.g. "£1,500,000")
            digits = re.sub(r"[^\d]", "", primary_price)
            price_amount = int(digits) if digits else None
        currency = price_info.get("currencyCode") or "GBP"
        frequency = price_info.get("frequency")

        # Location
        location = data.get("location") or {}

        # Tenure
        tenure = data.get("tenure") or {}
        tenure_type = tenure.get("tenureType")
        years_remaining = _safe_int(tenure.get("yearsRemainingOnLease"))

        # Living costs
        living_costs = data.get("livingCosts") or {}

        # Customer / agent
        customer = data.get("customer") or {}

        # Address
        address_info = data.get("address") or {}
        display_address = address_info.get("displayAddress") or data.get("displayAddress")
        outcode = address_info.get("outcode")
        incode = address_info.get("incode")
        postcode = f"{outcode} {incode}" if outcode and incode else None

        # Text/description
        text = data.get("text") or {}
        description = text.get("description") or text.get("propertyPhrase")

        # Channel / transaction type
        channel = (data.get("channel") or "").lower()  # "BUY" or "RENT"
        transaction_type = "rent" if channel == "rent" else "buy" if channel == "buy" else None

        # Listing history
        listing_history = data.get("listingHistory") or {}

        # Status tags (SOLD_STC, UNDER_OFFER, LET_AGREED, etc.)
        tags = data.get("tags") or []

        # Nearest stations
        stations_raw = data.get("nearestStations") or []
        nearest_stations = [
            {"name": s.get("name"), "types": s.get("types", []),
             "distance": _round_distance(s.get("distance")), "unit": s.get("unit")}
            for s in stations_raw if isinstance(s, dict)
        ]

        return cls(
            id=data.get("id"),
            url=url,
            price=price_amount,
            currency=currency,
            bedrooms=_safe_int(data.get("bedrooms")),
            bathrooms=_safe_int(data.get("bathrooms")),
            address=display_address,
            postcode=postcode,
            description=description,
            property_type=data.get("propertyType") or data.get("propertySubType"),
            property_sub_type=data.get("propertySubType"),
            agent_name=customer.get("branchName") or customer.get("companyName"),
            agent_branch=customer.get("branchDisplayName"),
            first_visible_date=data.get("firstVisibleDate"),
            images=_extract_images(data),
            floorplans=_extract_floorplans(data),
            latitude=_safe_float(location.get("latitude")),
            longitude=_safe_float(location.get("longitude")),
            tenure_type=tenure_type,
            years_remaining_on_lease=years_remaining,
            annual_service_charge=_safe_int(living_costs.get("annualServiceCharge")),
            annual_ground_rent=_safe_int(living_costs.get("annualGroundRent")),
            ground_rent_review_period_years=_safe_int(
                living_costs.get("groundRentReviewPeriodInYears")
            ),
            ground_rent_percentage_increase=_safe_float(
                living_costs.get("groundRentPercentageIncrease")
            ),
            council_tax_band=living_costs.get("councilTaxBand"),
            display_size=_extract_display_size(data),
            price_per_sqft=price_info.get("pricePerSqFt"),
            key_features=_extract_key_features(data),
            listing_update_reason=listing_history.get("listingUpdateReason"),
            listing_status=tags[0] if tags else None,
            tags=tags,
            nearest_stations=nearest_stations,
            let_available_date=data.get("letAvailableDate"),
            price_frequency=frequency,
            transaction_type=transaction_type,
            raw=data,
        )
