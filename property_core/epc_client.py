"""EPC Register client (pure Python).

Fetches domestic EPC certificates for UK postcodes and returns typed EPCData models.
"""

from __future__ import annotations

import base64
import os
from typing import Optional

import httpx

from property_core.address_matching import match_epc_address
from property_core.models.epc import EPCData


class EPCClient:
    """Client for UK EPC Register API."""

    BASE_URL = "https://epc.opendatacommunities.org/api/v1"

    def __init__(
        self,
        email: str | None = None,
        api_key: str | None = None,
        timeout: float = 15.0,
    ):
        self.email = email or os.getenv("EPC_API_EMAIL")
        self.api_key = api_key or os.getenv("EPC_API_KEY")
        self.timeout = timeout

    def is_configured(self) -> bool:
        return bool(self.email and self.api_key)

    def _auth_header(self) -> dict[str, str]:
        if not self.email or not self.api_key:
            return {}
        creds = base64.b64encode(f"{self.email}:{self.api_key}".encode()).decode()
        return {"Authorization": f"Basic {creds}"}

    async def get_certificate(
        self, certificate_hash: str
    ) -> Optional[EPCData]:
        """Get EPC certificate by lmk-key (certificate hash).

        Returns:
            EPCData model or None.
        """
        if not self.is_configured():
            return None

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.get(
                    f"{self.BASE_URL}/domestic/certificate/{certificate_hash}",
                    headers={"Accept": "application/json", **self._auth_header()},
                )
                resp.raise_for_status()
                data = resp.json()

                rows = data.get("rows", [])
                if not rows:
                    return None

                return EPCData.from_api_row(rows[0])

            except (httpx.HTTPError, KeyError, ValueError):
                return None

    async def search_all_by_postcode(
        self, postcode: str
    ) -> list[EPCData]:
        """Return all parsed EPC certificates for a postcode.

        Useful for batch-matching multiple addresses against a single postcode's
        certificates (e.g. enriching PPD comparables with floor area).

        Returns:
            List of EPCData models (may be empty).
        """
        if not self.is_configured():
            return []

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.get(
                    f"{self.BASE_URL}/domestic/search",
                    params={"postcode": postcode.replace(" ", "")},
                    headers={"Accept": "application/json", **self._auth_header()},
                )
                resp.raise_for_status()
                data = resp.json()
                rows = data.get("rows", [])
                return [EPCData.from_api_row(row) for row in rows]
            except (httpx.HTTPError, KeyError, ValueError):
                return []

    def match_address(
        self, certificates: list[EPCData], address: str, min_score: int = 30
    ) -> Optional[tuple[EPCData, int]]:
        """Find the best-matching certificate for an address from a pre-fetched list.

        Delegates to address_matching.match_epc_address().

        Args:
            certificates: List of EPCData models (from search_all_by_postcode).
            address: Address to match against.
            min_score: Minimum match score (0-100) to accept.

        Returns:
            Tuple of (EPCData, match_score) or None if no match meets threshold.
        """
        return match_epc_address(certificates, address, min_score=min_score)

    async def search_by_postcode(
        self, postcode: str, address: str | None = None
    ) -> Optional[EPCData]:
        """Search for EPC by postcode, optionally matching address.

        Returns:
            EPCData model or None.
        """
        if not self.is_configured():
            return None

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.get(
                    f"{self.BASE_URL}/domestic/search",
                    params={"postcode": postcode.replace(" ", "")},
                    headers={"Accept": "application/json", **self._auth_header()},
                )
                resp.raise_for_status()
                data = resp.json()

                rows = data.get("rows", [])
                if not rows:
                    return None

                if address:
                    certs = [EPCData.from_api_row(row) for row in rows]
                    result = match_epc_address(certs, address, min_score=30)
                    if result:
                        return result[0]  # return the EPCData
                    return None  # BUG FIX: was falling through to rows[0]

                return EPCData.from_api_row(rows[0])

            except (httpx.HTTPError, KeyError, ValueError):
                return None
