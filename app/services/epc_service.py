"""Service wrapper for EPC lookups."""

from __future__ import annotations

from typing import Optional

from app.core.config import get_settings
from app.schemas.epc import EPCData
from property_core.epc_client import EPCClient


class EPCService:
    """High-level EPC operations used by the API layer."""

    def __init__(self, client: Optional[EPCClient] = None):
        if client is not None:
            self.client = client
        else:
            settings = get_settings()
            self.client = EPCClient(
                email=settings.epc_api_email,
                api_key=settings.epc_api_key,
            )

    def is_configured(self) -> bool:
        return self.client.is_configured()

    async def search(self, postcode: str, address: str | None = None) -> EPCData | None:
        payload = await self.client.search_by_postcode(postcode, address=address)
        if payload is None:
            return None
        return EPCData.model_validate(payload)
