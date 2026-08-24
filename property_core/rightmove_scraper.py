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
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlsplit, urlunparse

import requests
from bs4 import BeautifulSoup
from requests import Session
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from property_core.models.rightmove import RightmoveListing, RightmoveListingDetail
from property_core.url_safety import validate_allowed_url

# Only these hosts may be fetched server-side. Exact matches only — see
# property_core/url_safety.py for why suffix matching is not accepted.
_RIGHTMOVE_HOSTS = frozenset({"www.rightmove.co.uk"})

# Rightmove property IDs are numeric and far shorter than this; the bound just
# keeps pathological input out of the URL builder.
# [0-9] rather than \d: Python's \d also matches non-ASCII digits (e.g.
# Arabic-Indic), which would be interpolated straight into the fetch URL.
_PROPERTY_ID_RE = re.compile(r"^[0-9]{1,12}$")

# The only URL path shape a listing ID may be recovered from.
_PROPERTY_PATH_RE = re.compile(r"^/properties/([0-9]{1,12})/?$")

# Guards against a malicious or misbehaving upstream streaming an unbounded body.
_MAX_RESPONSE_BYTES = 10 * 1024 * 1024
_MAX_REDIRECTS = 5
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


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


@dataclass(frozen=True)
class _Page:
    """A fetched page: size-capped body text plus the final (post-redirect) URL.

    Callers only ever used ``response.text``, so exposing ``.text`` keeps the
    downstream parsers unchanged while letting the fetch layer enforce a byte cap.
    """

    text: str
    url: str


def extract_property_id(property_id_or_url: str) -> str:
    """Resolve a Rightmove listing reference to its numeric property ID.

    Accepts either a bare numeric ID, or a canonical Rightmove listing URL of
    the exact form ``https://www.rightmove.co.uk/properties/<digits>``.

    A URL is only ever used as a *source of digits*. It is validated against the
    Rightmove host allowlist and then discarded — the caller's URL is never
    fetched, so this cannot be used to reach an arbitrary host. Any other path
    on the allowlisted host (``/search``, ``/redirect?to=...``) is rejected too.

    Raises:
        ValueError: If the value is neither a numeric ID nor a canonical
            Rightmove listing URL. UnsafeURLError (a ValueError) is raised for a
            URL that fails host/scheme validation.
    """
    value = (property_id_or_url or "").strip()

    if _PROPERTY_ID_RE.match(value):
        return value

    if "//" in value or value.lower().startswith(("http:", "https:")):
        # Raises UnsafeURLError for a non-Rightmove host, userinfo trick,
        # lookalike host, non-https scheme, or non-default port.
        canonical = validate_allowed_url(value, allowed_hosts=_RIGHTMOVE_HOSTS)
        match = _PROPERTY_PATH_RE.match(urlsplit(canonical).path)
        if match:
            return match.group(1)
        raise ValueError(
            f"Not a Rightmove listing URL: {property_id_or_url!r}. Expected "
            "https://www.rightmove.co.uk/properties/<numeric id>."
        )

    raise ValueError(
        f"Expected a numeric Rightmove property ID (1-12 digits) or a "
        f"https://www.rightmove.co.uk/properties/<id> URL, got {property_id_or_url!r}."
    )


def fetch_listing(
    property_url_or_id: str,
    *,
    timeout: float = 15.0,
    retry_attempts: int = 3,
    retry_backoff: float = 1.5,
) -> RightmoveListingDetail:
    """Fetch full property details from an individual Rightmove listing page.

    Args:
        property_url_or_id: Numeric Rightmove property ID, or a canonical
            Rightmove listing URL (``https://www.rightmove.co.uk/properties/<id>``).
            A URL is used only to extract the numeric ID — the fetched URL is
            always rebuilt internally, so a caller-supplied URL is never
            requested. This previously fetched any string starting with "http",
            which was an SSRF vector reachable from unauthenticated surfaces.

            The parameter name is retained from earlier releases so that
            existing keyword callers (``fetch_listing(property_url_or_id=...)``)
            keep working; the name has no bearing on validation.
        timeout: HTTP request timeout in seconds.
        retry_attempts: Number of retries on transient errors.
        retry_backoff: Exponential backoff multiplier.

    Returns:
        RightmoveListingDetail with all available fields from the detail page.

    Raises:
        ValueError: If the reference is neither a numeric ID nor a canonical
            Rightmove listing URL (UnsafeURLError, a ValueError, for a URL that
            fails host/scheme validation).
    """
    pid = extract_property_id(property_url_or_id)
    url = f"https://www.rightmove.co.uk/properties/{pid}"

    with Session() as session:
        page = _get_with_retries(
            session=session,
            url=url,
            timeout=timeout,
            retry_attempts=retry_attempts,
            retry_backoff=retry_backoff,
        )
    property_data = _extract_page_model(page.text)
    return RightmoveListingDetail.from_page_model(property_data, url=page.url)


def fetch_listings(
    search_url: str,
    *,
    timeout: float = 15.0,
    max_pages: Optional[int] = None,
    rate_limit_seconds: float = 0.6,
    retry_attempts: int = 3,
    retry_backoff: float = 1.5,
) -> list[RightmoveListing]:
    """Fetch listings from a Rightmove search URL across pages.

    ``search_url`` is validated against the Rightmove host allowlist and
    canonicalised before any request is made; the canonical value is what gets
    fetched. Callers should build this URL with
    :meth:`property_core.rightmove_location.RightmoveLocationAPI.build_search_url`
    rather than accepting one from an end user.

    Raises:
        UnsafeURLError: If search_url is not an allowlisted https Rightmove URL.
    """
    # Rebind to the canonical form — everything below fetches this, never the
    # raw input, so the validated and requested URLs cannot diverge.
    search_url = validate_allowed_url(search_url, allowed_hosts=_RIGHTMOVE_HOSTS)

    listings: list[RightmoveListing] = []
    next_url = search_url
    page_counter = 0
    seen_indices: set[str] = set()

    with Session() as session:
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
            # Rewrites only the `index` query param on the already-validated
            # canonical URL, so the host cannot change; re-validated anyway.
            next_url = validate_allowed_url(
                _url_with_index(search_url, next_index), allowed_hosts=_RIGHTMOVE_HOSTS
            )

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


def _read_capped(response: Any) -> bytes:
    """Read a response body, refusing anything over _MAX_RESPONSE_BYTES.

    Two layers: an up-front Content-Length check (cheap, avoids reading at all)
    and a running cap while streaming (covers a missing, chunked, or spoofed
    Content-Length).
    """
    declared = (response.headers or {}).get("Content-Length")
    if declared:
        try:
            declared_bytes: Optional[int] = int(declared)
        except (TypeError, ValueError):
            declared_bytes = None
        if declared_bytes is not None and declared_bytes > _MAX_RESPONSE_BYTES:
            raise RightmoveError(
                f"Response declares {declared_bytes} bytes, over the "
                f"{_MAX_RESPONSE_BYTES} byte limit"
            )

    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        total += len(chunk)
        if total > _MAX_RESPONSE_BYTES:
            raise RightmoveError(
                f"Response exceeded the {_MAX_RESPONSE_BYTES} byte limit while streaming"
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _make_request(
    session: Session,
    url: str,
    timeout: float,
    *,
    allowed_hosts: frozenset[str] = _RIGHTMOVE_HOSTS,
) -> _Page:
    """Fetch ``url``, following only redirects that stay inside ``allowed_hosts``.

    Redirects are resolved and re-validated manually rather than delegated to
    the HTTP client: automatic following would let an allowlisted host bounce us
    to an arbitrary internal address, which would reopen the SSRF hole that
    validating the initial URL closes.
    """
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        try:
            response = session.get(
                current,
                headers=DEFAULT_HEADERS,
                timeout=timeout,
                allow_redirects=False,
                stream=True,
            )
        except requests.RequestException as exc:
            raise RetryableError(f"Network error: {exc}") from exc

        try:
            status = response.status_code

            if status in _REDIRECT_STATUSES:
                location = (response.headers or {}).get("Location")
                if not location:
                    raise RightmoveError(f"Redirect {status} with no Location header")
                # Resolve relative/protocol-relative targets against the current
                # URL, then re-validate: '//evil.example/x' resolves to a
                # different host and is rejected here.
                current = validate_allowed_url(
                    urljoin(current, location), allowed_hosts=allowed_hosts
                )
                continue

            if status == 429 or status >= 500:
                raise RetryableError(f"Server responded with {status}")
            if status >= 400:
                raise RightmoveError(f"Request failed with status code {status}")

            body = _read_capped(response)
            encoding = getattr(response, "encoding", None) or "utf-8"
        finally:
            response.close()

        return _Page(text=body.decode(encoding, errors="replace"), url=current)

    raise RightmoveError(f"Exceeded {_MAX_REDIRECTS} redirects starting from {url}")


def _get_with_retries(
    *,
    session: Session,
    url: str,
    timeout: float,
    retry_attempts: int = 3,
    retry_backoff: float = 1.5,
) -> _Page:
    @retry(
        stop=stop_after_attempt(retry_attempts),
        wait=wait_exponential(multiplier=retry_backoff, min=1, max=30),
        retry=retry_if_exception_type(RetryableError),
        reraise=True,
    )
    def _fetch() -> _Page:
        return _make_request(session, url, timeout)

    try:
        return _fetch()
    except RetryableError as exc:
        raise RightmoveError(f"Request failed after {retry_attempts} retries: {exc}") from exc


# --- Listing detail helpers ---

_PAGE_MODEL_RE = re.compile(r"window\.__PAGE_MODEL\s*=\s*(.+);")


def _decode_graph(nodes: list, idx: int, seen: frozenset = frozenset()) -> Any:
    """Recursively dereference Rightmove's pointer-graph encoding.

    Each node is either a primitive (returned as-is) or a dict/list whose
    values are integer indices into the same nodes array.
    """
    if idx in seen:
        return None
    val = nodes[idx]
    seen = seen | {idx}
    if isinstance(val, dict):
        return {k: _decode_graph(nodes, v, seen) for k, v in val.items()}
    if isinstance(val, list):
        return [_decode_graph(nodes, i, seen) for i in val]
    return val


def _extract_page_model(html: str) -> Dict[str, Any]:
    """Extract PAGE_MODEL JSON from a Rightmove property detail page."""
    match = _PAGE_MODEL_RE.search(html)
    if not match:
        raise RightmoveError("Could not locate PAGE_MODEL data on the property page")
    try:
        outer = json.loads(match.group(1))
        nodes = json.loads(outer["data"])
    except (json.JSONDecodeError, KeyError) as exc:
        raise RightmoveError(f"PAGE_MODEL contained invalid JSON: {exc}") from exc
    root = _decode_graph(nodes, 0)
    property_data = root.get("propertyData")
    if not property_data:
        raise RightmoveError("propertyData not found in PAGE_MODEL")
    return property_data
