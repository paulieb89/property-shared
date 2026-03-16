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
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from requests import Response, Session
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from property_core.models.rightmove import RightmoveListing, RightmoveListingDetail


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


def fetch_listing(
    property_url_or_id: str,
    *,
    timeout: float = 15.0,
    retry_attempts: int = 3,
    retry_backoff: float = 1.5,
    include_raw: bool = False,
) -> RightmoveListingDetail:
    """Fetch full property details from an individual Rightmove listing page.

    Args:
        property_url_or_id: Full Rightmove URL or just the numeric property ID.
        timeout: HTTP request timeout in seconds.
        retry_attempts: Number of retries on transient errors.
        retry_backoff: Exponential backoff multiplier.
        include_raw: Kept for backward compatibility (raw is always populated).

    Returns:
        RightmoveListingDetail with all available fields from the detail page.
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
    return RightmoveListingDetail.from_page_model(property_data, url=url)


def fetch_listings(
    search_url: str,
    *,
    timeout: float = 15.0,
    max_pages: Optional[int] = None,
    rate_limit_seconds: float = 0.6,
    retry_attempts: int = 3,
    retry_backoff: float = 1.5,
    include_raw: bool = False,
) -> list[RightmoveListing]:
    """Fetch listings from a Rightmove search URL across pages."""
    listings: list[RightmoveListing] = []
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
        listings.extend(RightmoveListing.from_next_data(prop) for prop in properties)

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


def _url_with_index(url: str, index: str | int) -> str:
    parsed = urlparse(url)
    query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_items["index"] = str(index)
    new_query = urlencode(query_items, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


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
