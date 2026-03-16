"""Postcode lookup client using postcodes.io API.

Free API for UK postcode lookups - no authentication required.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from property_core.models.postcode import PostcodeResult


class PostcodeClient:
    """Client for postcodes.io API."""

    BASE_URL = "https://api.postcodes.io"

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def lookup(self, postcode: str) -> Optional[PostcodeResult]:
        """Look up a UK postcode.

        Returns:
            PostcodeResult with postcode info including admin_district
            (local authority), or None if not found.
        """
        # Normalize postcode (remove spaces, uppercase)
        postcode_clean = postcode.replace(" ", "").upper()

        with httpx.Client(timeout=self.timeout) as client:
            try:
                resp = client.get(f"{self.BASE_URL}/postcodes/{postcode_clean}")
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                data = resp.json()
                result = data.get("result")
                if not result:
                    return None
                return PostcodeResult.from_api_response(result)
            except httpx.HTTPError:
                return None

    def get_local_authority(
        self, postcode: str, *, include_raw: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Get local authority info for a postcode.

        Returns:
            Dict with name, code, region, etc. or None if not found.
            When include_raw=True, includes the full postcodes.io response
            under the 'raw' key.
        """
        result = self.lookup(postcode)
        if not result:
            return None

        data: Dict[str, Any] = {
            "name": result.admin_district,
            "code": result.codes.get("admin_district") if result.codes else None,
            "county": result.admin_county,
            "region": result.region,
            "country": result.country,
            "postcode": result.postcode,
            "latitude": result.latitude,
            "longitude": result.longitude,
            "rural_urban": result.rural_urban,
        }
        if include_raw:
            data["raw"] = result.raw
        return data
