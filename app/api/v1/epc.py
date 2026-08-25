"""EPC API endpoint."""

from __future__ import annotations

from collections import Counter
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.schemas.epc import EPCAreaResponse, EPCAreaSummary, EPCRecordResponse
from property_core.address_matching import parse_address
from property_core.epc_client import EPCClient, EPCUpstreamError
from property_core.models.epc import EPCData

router = APIRouter(prefix="/epc", tags=["epc"])
_client = EPCClient()


def _upstream_unavailable(exc: EPCUpstreamError) -> HTTPException:
    """Map an EPC outage to 503, never to 404 or an empty 200.

    Reporting an outage as "not found" (or as a zero-count area summary) states
    a falsehood about the property, which is worse than failing.
    """
    return HTTPException(status_code=503, detail=f"EPC service unavailable: {exc}")


def _build_area_summary(certs: list[EPCData]) -> EPCAreaSummary:
    """Compute aggregate stats for a list of EPC certificates."""
    ratings = Counter(c.rating for c in certs if c.rating)
    types = Counter(c.property_type for c in certs if c.property_type)
    areas = [c.floor_area for c in certs if c.floor_area]

    return EPCAreaSummary(
        count=len(certs),
        rating_distribution=dict(sorted(ratings.items())),
        property_type_breakdown=dict(sorted(types.items())),
        floor_area_min=min(areas) if areas else None,
        floor_area_max=max(areas) if areas else None,
        floor_area_avg=round(sum(areas) / len(areas), 1) if areas else None,
    )


@router.get("/certificate/{certificate_hash}", response_model=EPCRecordResponse)
async def get_certificate(
    certificate_hash: str,
    include_raw: bool = Query(False, description="Include raw EPC API JSON"),
) -> EPCRecordResponse:
    """Get EPC certificate by lmk-key (certificate hash)."""
    if not _client.is_configured():
        raise HTTPException(status_code=501, detail="EPC client not configured")

    try:
        result = await _client.get_certificate(certificate_hash)
    except EPCUpstreamError as exc:
        raise _upstream_unavailable(exc) from exc
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

    try:
        result = await _client.search_by_postcode(postcode, address=address)
    except EPCUpstreamError as exc:
        raise _upstream_unavailable(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="No EPC certificate found")
    return EPCRecordResponse(record=result, raw=result.raw if include_raw else None)


@router.get("/search-area", response_model=EPCAreaResponse)
async def search_area(
    postcode: str = Query(..., min_length=2, description="UK postcode"),
) -> EPCAreaResponse:
    """List all EPC certificates for a postcode with area summary statistics.

    Returns every certificate at the given postcode plus aggregate stats
    (rating distribution, floor area range, property type breakdown).
    Use /epc/search when you have a specific street address to match.
    """
    if not _client.is_configured():
        raise HTTPException(status_code=501, detail="EPC client not configured")

    try:
        certs = await _client.search_all_by_postcode(postcode)
    except EPCUpstreamError as exc:
        # Never return a zero-count summary for an outage: it is indistinguishable
        # from a postcode that genuinely has no certificates.
        raise _upstream_unavailable(exc) from exc
    return EPCAreaResponse(
        postcode=postcode,
        summary=_build_area_summary(certs),
        certificates=certs,
    )
