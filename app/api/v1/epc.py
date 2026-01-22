"""EPC API endpoint."""

from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.schemas.epc import EPCRecordResponse
from app.services.epc_service import EPCService

router = APIRouter(prefix="/epc", tags=["epc"])
service = EPCService()

# UK postcode regex for parsing combined address strings
UK_POSTCODE_RE = re.compile(
    r"([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\s*$",
    re.IGNORECASE,
)


def _parse_address_query(q: str) -> tuple[Optional[str], Optional[str]]:
    """Parse a combined address string into (postcode, address).

    Examples:
        "10 Downing Street, SW1A 2AA" -> ("SW1A 2AA", "10 Downing Street")
        "SW1A 2AA" -> ("SW1A 2AA", None)
    """
    q = q.strip()
    match = UK_POSTCODE_RE.search(q)
    if match:
        postcode = match.group(1).upper()
        # Everything before the postcode is the address
        address_part = q[: match.start()].strip().rstrip(",").strip()
        return (postcode, address_part if address_part else None)
    return (None, None)


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
        parsed_postcode, parsed_address = _parse_address_query(q)
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
