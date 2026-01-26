"""Rightmove scraper (pure Python).

Scrapes both search results (``fetch_listings``) and individual property detail
pages (``fetch_listing``).

Search results use the embedded ``__NEXT_DATA__`` payload.
Property detail pages use the embedded ``window.PAGE_MODEL`` payload.

Intentionally conservative:
- polite delay between page fetches (``rate_limit_seconds``)
- retry on transient errors (429/5xx)
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from requests import Response, Session
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}


class RetryableError(Exception):
    """Raised for transient errors that should trigger a retry."""


class RightmoveError(Exception):
    """Raised when Rightmove data cannot be fetched or parsed."""


@dataclass
class Listing:
    id: Any
    url: str
    price: Optional[int]
    currency: Optional[str]
    bedrooms: Optional[int]
    bathrooms: Optional[int]
    address: Optional[str]
    summary: Optional[str]
    property_type: Optional[str]
    agent_name: Optional[str]
    agent_branch: Optional[str]
    first_visible_date: Optional[str]
    images: List[str]
    # Rental-specific fields (None for sales)
    let_available_date: Optional[str] = None
    price_frequency: Optional[str] = None  # "monthly", "weekly"
    students: Optional[bool] = None
    transaction_type: Optional[str] = None  # "rent" or "buy"
    # Raw __NEXT_DATA__ property dict (populated when include_raw=True)
    raw: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ListingDetail:
    """Full property detail from an individual Rightmove listing page."""

    id: Any
    url: str
    price: Optional[int]
    currency: Optional[str]
    bedrooms: Optional[int]
    bathrooms: Optional[int]
    address: Optional[str]
    description: Optional[str]
    property_type: Optional[str]
    property_sub_type: Optional[str]
    agent_name: Optional[str]
    agent_branch: Optional[str]
    first_visible_date: Optional[str]
    images: List[str]
    floorplans: List[str]
    # Location
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
    key_features: List[str] = field(default_factory=list)
    # Listing history
    listing_update_reason: Optional[str] = None
    # Transport
    nearest_stations: List[Dict[str, Any]] = field(default_factory=list)
    # Rental-specific
    let_available_date: Optional[str] = None
    price_frequency: Optional[str] = None
    transaction_type: Optional[str] = None
    # Raw PAGE_MODEL.propertyData dict (populated when include_raw=True)
    raw: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def fetch_listing(
    property_url_or_id: str,
    *,
    timeout: float = 15.0,
    retry_attempts: int = 3,
    retry_backoff: float = 1.5,
    include_raw: bool = False,
) -> ListingDetail:
    """Fetch full property details from an individual Rightmove listing page.

    Args:
        property_url_or_id: Full Rightmove URL or just the numeric property ID.
        timeout: HTTP request timeout in seconds.
        retry_attempts: Number of retries on transient errors.
        retry_backoff: Exponential backoff multiplier.
        include_raw: If True, include the full PAGE_MODEL propertyData dict.

    Returns:
        ListingDetail with all available fields from the detail page.
    """
    url = _normalize_property_url(property_url_or_id)
    session = Session()
    response = _get_with_retries(
        session=session,
        url=url,
        timeout=timeout,
        retry_attempts=retry_attempts,
        retry_backoff=retry_backoff,
    )
    property_data = _extract_page_model(response.text)
    return _to_listing_detail(property_data, url=url, include_raw=include_raw)


def fetch_listings(
    search_url: str,
    *,
    timeout: float = 15.0,
    max_pages: Optional[int] = None,
    rate_limit_seconds: float = 0.6,
    retry_attempts: int = 3,
    retry_backoff: float = 1.5,
    include_raw: bool = False,
) -> List[Listing]:
    """Fetch listings from a Rightmove search URL across pages."""
    listings: List[Listing] = []
    next_url = search_url
    page_counter = 0
    seen_indices: set[str] = set()
    session = Session()

    while next_url:
        if rate_limit_seconds and page_counter > 0:
            time.sleep(rate_limit_seconds)
        page_counter += 1

        search_results = _get_search_results(
            session=session,
            url=next_url,
            timeout=timeout,
            retry_attempts=retry_attempts,
            retry_backoff=retry_backoff,
        )
        properties = search_results.get("properties") or []
        listings.extend(_to_listing(prop, include_raw=include_raw) for prop in properties)

        pagination = search_results.get("pagination") or {}
        next_index = pagination.get("next")

        if max_pages is not None and page_counter >= max_pages:
            break

        if not next_index or str(next_index) in seen_indices:
            break

        seen_indices.add(str(next_index))
        next_url = _url_with_index(search_url, next_index)

    return listings


def _get_search_results(
    *, session: Session, url: str, timeout: float, retry_attempts: int, retry_backoff: float
) -> Dict[str, Any]:
    response = _get_with_retries(
        session=session,
        url=url,
        timeout=timeout,
        retry_attempts=retry_attempts,
        retry_backoff=retry_backoff,
    )
    soup = BeautifulSoup(response.text, "html.parser")
    return _extract_search_results(soup)


def _extract_search_results(soup: BeautifulSoup) -> Dict[str, Any]:
    data_script = soup.find("script", id="__NEXT_DATA__")
    if not data_script or not data_script.string:
        raise RightmoveError("Could not locate embedded search data on the page")
    try:
        parsed = json.loads(data_script.string)
    except json.JSONDecodeError as exc:
        raise RightmoveError(f"Page contained invalid JSON: {exc}") from exc
    try:
        return parsed["props"]["pageProps"]["searchResults"]
    except KeyError as exc:
        raise RightmoveError("Search results were not present in the page payload") from exc


def _to_listing(data: Dict[str, Any], *, include_raw: bool = False) -> Listing:
    price_info = data.get("price") or {}
    property_url = data.get("propertyUrl") or ""
    customer = data.get("customer") or {}
    return Listing(
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
        # Rental-specific fields
        let_available_date=data.get("letAvailableDate"),
        price_frequency=price_info.get("frequency"),
        students=data.get("students"),
        transaction_type=data.get("transactionType"),
        raw=data if include_raw else None,
    )


def _url_with_index(url: str, index: str | int) -> str:
    parsed = urlparse(url)
    query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_items["index"] = str(index)
    new_query = urlencode(query_items, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


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


def _make_request(session: Session, url: str, timeout: float) -> Response:
    try:
        response = session.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
    except requests.RequestException as exc:
        raise RetryableError(f"Network error: {exc}") from exc

    if response.status_code == 429 or response.status_code >= 500:
        raise RetryableError(f"Server responded with {response.status_code}")
    if response.status_code >= 400:
        raise RightmoveError(f"Request failed with status code {response.status_code}")
    return response


def _get_with_retries(
    *,
    session: Session,
    url: str,
    timeout: float,
    retry_attempts: int = 3,
    retry_backoff: float = 1.5,
) -> Response:
    @retry(
        stop=stop_after_attempt(retry_attempts),
        wait=wait_exponential(multiplier=retry_backoff, min=1, max=30),
        retry=retry_if_exception_type(RetryableError),
        reraise=True,
    )
    def _fetch() -> Response:
        return _make_request(session, url, timeout)

    try:
        return _fetch()
    except RetryableError as exc:
        raise RightmoveError(f"Request failed after {retry_attempts} retries: {exc}") from exc


# --- Listing detail helpers ---

_PAGE_MODEL_RE = re.compile(r"window\.PAGE_MODEL\s*=\s*(\{.+?\})\s*\n", re.DOTALL)


def _normalize_property_url(url_or_id: str) -> str:
    """Accept a full Rightmove URL or numeric ID, return a canonical detail URL."""
    url_or_id = url_or_id.strip()
    if url_or_id.startswith("http"):
        return url_or_id
    return f"https://www.rightmove.co.uk/properties/{url_or_id}"


def _extract_page_model(html: str) -> Dict[str, Any]:
    """Extract PAGE_MODEL JSON from a Rightmove property detail page."""
    match = _PAGE_MODEL_RE.search(html)
    if not match:
        raise RightmoveError("Could not locate PAGE_MODEL data on the property page")
    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise RightmoveError(f"PAGE_MODEL contained invalid JSON: {exc}") from exc
    property_data = parsed.get("propertyData")
    if not property_data:
        raise RightmoveError("propertyData not found in PAGE_MODEL")
    return property_data


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


def _to_listing_detail(
    data: Dict[str, Any], *, url: str, include_raw: bool = False
) -> ListingDetail:
    """Map PAGE_MODEL propertyData to a ListingDetail dataclass."""
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

    # Text/description
    text = data.get("text") or {}
    description = text.get("description") or text.get("propertyPhrase")

    # Channel / transaction type
    channel = (data.get("channel") or "").lower()  # "BUY" or "RENT"
    transaction_type = "rent" if channel == "rent" else "buy" if channel == "buy" else None

    # Listing history
    listing_history = data.get("listingHistory") or {}

    # Nearest stations
    stations_raw = data.get("nearestStations") or []
    nearest_stations = [
        {"name": s.get("name"), "types": s.get("types", []),
         "distance": s.get("distance"), "unit": s.get("unit")}
        for s in stations_raw if isinstance(s, dict)
    ]

    return ListingDetail(
        id=data.get("id"),
        url=url,
        price=price_amount,
        currency=currency,
        bedrooms=_safe_int(data.get("bedrooms")),
        bathrooms=_safe_int(data.get("bathrooms")),
        address=display_address,
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
        nearest_stations=nearest_stations,
        let_available_date=data.get("letAvailableDate"),
        price_frequency=frequency,
        transaction_type=transaction_type,
        raw=data if include_raw else None,
    )

