"""EPC API endpoint."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.schemas.epc import EPCRecordResponse
from property_core.address_matching import parse_address
from property_core.epc_client import EPCClient

router = APIRouter(prefix="/epc", tags=["epc"])
_client = EPCClient()


@router.get("/certificate/{certificate_hash}", response_model=EPCRecordResponse)
async def get_certificate(
    certificate_hash: str,
    include_raw: bool = Query(False, description="Include raw EPC API JSON"),
) -> EPCRecordResponse:
    """Get EPC certificate by lmk-key (certificate hash)."""
    if not _client.is_configured():
        raise HTTPException(status_code=501, detail="EPC client not configured")

    result = await _client.get_certificate(certificate_hash)
    if result is None:
        raise HTTPException(status_code=404, detail="No EPC certificate found")
    return EPCRecordResponse(record=result, raw=result.raw if include_raw else None)


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
    if not _client.is_configured():
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

    result = await _client.search_by_postcode(postcode, address=address)
    if result is None:
        raise HTTPException(status_code=404, detail="No EPC certificate found")
    return EPCRecordResponse(record=result, raw=result.raw if include_raw else None)
