"""Rightmove search scraper (pure Python).

This scrapes listing results from a Rightmove search URL by extracting the embedded
``__NEXT_DATA__`` payload. It is intentionally conservative:
- polite delay between page fetches (``rate_limit_seconds``)
- retry on transient errors (429/5xx)
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
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

