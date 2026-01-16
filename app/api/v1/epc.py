"""EPC API endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas.epc import EPCData
from app.services.epc_service import EPCService

router = APIRouter(prefix="/epc", tags=["epc"])
service = EPCService()


@router.get("/search", response_model=EPCData)
async def search(
    postcode: str = Query(..., min_length=2),
    address: str | None = None,
) -> EPCData:
    """Search for an EPC certificate by postcode (optional address match)."""
    if not service.is_configured():
        raise HTTPException(status_code=501, detail="EPC client not configured")

    result = await service.search(postcode=postcode, address=address)
    if result is None:
        raise HTTPException(status_code=404, detail="No EPC certificate found")
    return result
