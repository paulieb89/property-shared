"""EPC API endpoint."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.schemas.epc import EPCRecordResponse
from app.services.epc_service import EPCService
from property_core.address_matching import parse_address

router = APIRouter(prefix="/epc", tags=["epc"])
service = EPCService()


@router.get("/certificate/{certificate_hash}", response_model=EPCRecordResponse)
async def get_certificate(
    certificate_hash: str,
    include_raw: bool = Query(False, description="Include raw EPC API JSON"),
) -> EPCRecordResponse:
    """Get EPC certificate by lmk-key (certificate hash)."""
    if not service.is_configured():
        raise HTTPException(status_code=501, detail="EPC client not configured")

    result = await service.get_certificate(
        certificate_hash=certificate_hash, include_raw=include_raw
    )
    if result is None:
        raise HTTPException(status_code=404, detail="No EPC certificate found")
    return result


@router.get("/search", response_model=EPCRecordResponse)
async def search(
    postcode: Optional[str] = Query(None, min_length=2),
    address: Optional[str] = None,
    q: Optional[str] = Query(None, description="Combined address query, e.g. '10 Downing Street, SW1A 2AA'"),
    include_raw: bool = Query(False, description="Include raw EPC API JSON"),
) -> EPCRecordResponse:
    """Search for an EPC certificate by postcode (optional address match).

    Supports two modes:
    1. Explicit: postcode=SW1A+2AA&address=10+Downing+Street
    2. Combined: q=10+Downing+Street,+SW1A+2AA (postcode parsed from end)
    """
    if not service.is_configured():
        raise HTTPException(status_code=501, detail="EPC client not configured")

    # Parse combined query if provided
    if q:
        parsed_postcode, parsed_address = parse_address(q)
        if not parsed_postcode:
            raise HTTPException(
                status_code=422,
                detail="Could not parse postcode from query. Use format: '10 Downing Street, SW1A 2AA'",
            )
        postcode = parsed_postcode
        address = parsed_address or address

    if not postcode:
        raise HTTPException(status_code=422, detail="postcode or q parameter required")

    result = await service.search(postcode=postcode, address=address, include_raw=include_raw)
    if result is None:
        raise HTTPException(status_code=404, detail="No EPC certificate found")
    return result
