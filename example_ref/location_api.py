"""Rightmove location lookup API client.

This module provides utilities to convert UK postcodes into Rightmove search URLs
using Rightmove's undocumented location autocomplete API.
"""

from __future__ import annotations

import time
from typing import Optional
from urllib.parse import urlencode

import requests


class LocationLookupError(Exception):
    """Raised when location lookup fails."""


class RightmoveLocationAPI:
    """Client for Rightmove's location autocomplete API.
    
    This API allows converting UK postcodes (e.g., "DE12", "WD4") into
    Rightmove's internal location identifiers needed for search URLs.
    
    Example:
        >>> api = RightmoveLocationAPI()
        >>> location_id = api.lookup_postcode("DE12")
        >>> print(location_id)
        'OUTCODE^620'
        >>> url = api.build_search_url("DE12", property_type="sale")
        >>> print(url)
        'https://www.rightmove.co.uk/property-for-sale/find.html?locationIdentifier=OUTCODE^620'
    """
    
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
        rate_limit_delay: float = 0.1,
        cache_enabled: bool = True,
    ):
        """Initialize the location API client.
        
        Args:
            timeout: Request timeout in seconds (default: 10.0)
            rate_limit_delay: Delay between requests in seconds (default: 0.1)
            cache_enabled: Whether to cache successful lookups (default: True)
        """
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay
        self._cache: dict[str, str] = {} if cache_enabled else None
        self._last_request_time = 0.0
    
    def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        if self.rate_limit_delay > 0:
            elapsed = time.time() - self._last_request_time
            if elapsed < self.rate_limit_delay:
                time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()
    
    def lookup_postcode(self, postcode: str) -> Optional[str]:
        """Look up a postcode and return its Rightmove location identifier.
        
        Args:
            postcode: UK postcode (e.g., "DE12", "WD4", "B1")
            
        Returns:
            Location identifier string (e.g., "OUTCODE^620") or None if not found
            
        Raises:
            LocationLookupError: If the API request fails
            
        Example:
            >>> api = RightmoveLocationAPI()
            >>> api.lookup_postcode("DE12")
            'OUTCODE^620'
        """
        postcode_upper = postcode.upper().strip()
        
        # Check cache first
        if self._cache is not None and postcode_upper in self._cache:
            return self._cache[postcode_upper]
        
        # Rate limiting
        self._rate_limit()
        
        # Call API
        url = f"{self.API_BASE}{self.TYPEAHEAD_ENDPOINT}"
        params = {
            "query": postcode_upper,
            "limit": 10,
            "exclude": "STREET",
        }
        
        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            matches = data.get("matches", [])
            
            if not matches:
                return None
            
            # Return first match (usually exact match)
            first_match = matches[0]
            location_id = first_match.get("id")
            location_type = first_match.get("type", "OUTCODE")
            
            if not location_id:
                return None
            
            # Format: OUTCODE^{id}
            identifier = f"{location_type}^{location_id}"
            
            # Cache the result
            if self._cache is not None:
                self._cache[postcode_upper] = identifier
            
            return identifier
            
        except requests.exceptions.RequestException as e:
            raise LocationLookupError(f"Failed to lookup postcode '{postcode}': {e}") from e
    
    def build_search_url(
        self,
        postcode: str,
        *,
        property_type: str = "sale",
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        min_bedrooms: Optional[int] = None,
        max_bedrooms: Optional[int] = None,
        radius: Optional[float] = None,
        **extra_params,
    ) -> str:
        """Build a complete Rightmove search URL from a postcode.
        
        Args:
            postcode: UK postcode (e.g., "DE12")
            property_type: "sale" or "rent" (default: "sale")
            min_price: Minimum price filter
            max_price: Maximum price filter
            min_bedrooms: Minimum bedrooms filter
            max_bedrooms: Maximum bedrooms filter
            radius: Search radius in miles
            **extra_params: Additional URL parameters
            
        Returns:
            Complete Rightmove search URL
            
        Raises:
            LocationLookupError: If postcode lookup fails
            
        Example:
            >>> api = RightmoveLocationAPI()
            >>> url = api.build_search_url(
            ...     "DE12",
            ...     property_type="sale",
            ...     min_price=100000,
            ...     max_price=300000,
            ...     min_bedrooms=3
            ... )
            >>> print(url)
            'https://www.rightmove.co.uk/property-for-sale/find.html?locationIdentifier=OUTCODE^620&minPrice=100000&maxPrice=300000&minBedrooms=3'
        """
        # Lookup location identifier
        location_id = self.lookup_postcode(postcode)
        
        if not location_id:
            raise LocationLookupError(
                f"Could not find location identifier for postcode '{postcode}'. "
                f"The postcode may not exist or may not be recognized by Rightmove."
            )
        
        # Build base URL
        property_path = self.PROPERTY_TYPES.get(property_type, "property-for-sale")
        base_url = f"https://www.rightmove.co.uk/{property_path}/find.html"
        
        # Build query parameters
        params = {"locationIdentifier": location_id}
        
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
        
        # Add any extra parameters
        params.update(extra_params)
        
        # Build final URL
        query_string = urlencode(params)
        return f"{base_url}?{query_string}"
    
    def clear_cache(self) -> None:
        """Clear the location lookup cache."""
        if self._cache is not None:
            self._cache.clear()
    
    def get_cache_stats(self) -> dict[str, int]:
        """Get cache statistics.
        
        Returns:
            Dictionary with cache size and hit count
        """
        if self._cache is None:
            return {"enabled": False, "size": 0}
        
        return {
            "enabled": True,
            "size": len(self._cache),
        }


# Convenience functions for simple use cases

_default_api: Optional[RightmoveLocationAPI] = None


def get_api() -> RightmoveLocationAPI:
    """Get or create the default API client instance."""
    global _default_api
    if _default_api is None:
        _default_api = RightmoveLocationAPI()
    return _default_api


def lookup_postcode(postcode: str) -> Optional[str]:
    """Convenience function to lookup a postcode using the default API client.
    
    Example:
        >>> from rightmove_scraper import lookup_postcode
        >>> lookup_postcode("DE12")
        'OUTCODE^620'
    """
    return get_api().lookup_postcode(postcode)


def build_search_url(postcode: str, **kwargs) -> str:
    """Convenience function to build a search URL using the default API client.
    
    Example:
        >>> from rightmove_scraper import build_search_url
        >>> build_search_url("DE12", property_type="sale", min_price=100000)
        'https://www.rightmove.co.uk/property-for-sale/find.html?locationIdentifier=OUTCODE^620&minPrice=100000'
    """
    return get_api().build_search_url(postcode, **kwargs)
