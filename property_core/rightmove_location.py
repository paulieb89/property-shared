"""Rightmove location lookup and URL builder (pure Python).

Rightmove uses internal location identifiers (e.g. ``OUTCODE^620``) in search URLs.
This module wraps their (undocumented) typeahead endpoint to convert postcodes/outcodes
to those identifiers and then build search URLs.
"""

from __future__ import annotations

import time
from typing import Optional
from urllib.parse import urlencode

import requests


class LocationLookupError(Exception):
    """Raised when Rightmove location lookup fails."""


class RightmoveLocationAPI:
    """Client for Rightmove's location autocomplete API."""

    API_BASE = "https://los.rightmove.co.uk"
    TYPEAHEAD_ENDPOINT = "/typeahead"

    PROPERTY_TYPES = {
        "sale": "property-for-sale",
        "rent": "property-to-rent",
    }

    def __init__(
        self,
        *,
        timeout: float = 10.0,
        rate_limit_delay: float = 0.2,
        cache_enabled: bool = True,
    ):
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay
        self._cache: dict[str, str] | None = {} if cache_enabled else None
        self._last_request_time = 0.0

    def _rate_limit(self) -> None:
        if self.rate_limit_delay <= 0:
            return
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def lookup_postcode(self, postcode: str) -> Optional[str]:
        """Return Rightmove location identifier for a postcode/outcode."""
        postcode_upper = postcode.upper().strip()
        if self._cache is not None and postcode_upper in self._cache:
            return self._cache[postcode_upper]

        self._rate_limit()
        url = f"{self.API_BASE}{self.TYPEAHEAD_ENDPOINT}"
        params = {"query": postcode_upper, "limit": 10, "exclude": "STREET"}

        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            raise LocationLookupError(f"Failed to lookup postcode '{postcode}': {exc}") from exc

        matches = data.get("matches", [])
        if not matches:
            return None

        first_match = matches[0]
        location_id = first_match.get("id")
        location_type = first_match.get("type", "OUTCODE")
        if not location_id:
            return None

        identifier = f"{location_type}^{location_id}"
        if self._cache is not None:
            self._cache[postcode_upper] = identifier
        return identifier

    def build_search_url(
        self,
        postcode: str,
        *,
        property_type: str = "sale",
        min_price: int | None = None,
        max_price: int | None = None,
        min_bedrooms: int | None = None,
        max_bedrooms: int | None = None,
        radius: float | None = None,
        **extra_params,
    ) -> str:
        """Build a Rightmove search URL from a postcode/outcode."""
        location_identifier = self.lookup_postcode(postcode)
        if not location_identifier:
            raise LocationLookupError(
                f"Could not find location identifier for postcode '{postcode}'."
            )

        property_path = self.PROPERTY_TYPES.get(property_type, "property-for-sale")
        base_url = f"https://www.rightmove.co.uk/{property_path}/find.html"

        params: dict[str, object] = {"locationIdentifier": location_identifier}
        if min_price is not None:
            params["minPrice"] = min_price
        if max_price is not None:
            params["maxPrice"] = max_price
        if min_bedrooms is not None:
            params["minBedrooms"] = min_bedrooms
        if max_bedrooms is not None:
            params["maxBedrooms"] = max_bedrooms
        if radius is not None:
            params["radius"] = radius

        params.update(extra_params)
        return f"{base_url}?{urlencode(params)}"

