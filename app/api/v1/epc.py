"""EPC API endpoint."""

from __future__ import annotations

from collections import Counter
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.schemas.epc import EPCAreaResponse, EPCAreaSummary, EPCRecordResponse
from property_core.address_matching import parse_address
from property_core.epc.errors import (
    EPCAmbiguousMatchError,
    EPCError,
    EPCAuthenticationError,
    EPCConfigurationError,
    EPCInvalidQueryError,
    EPCRateLimitError,
    EPCUnsupportedOperationError,
    EPCUpstreamError,
)
from property_core.epc_client import EPCClient
from property_core.models.epc import EPCData

router = APIRouter(prefix="/epc", tags=["epc"])
_client = EPCClient()


# Complete EPC failure taxonomy. Every typed failure gets a status that means
# what it says: an outage is not "not found", a malformed query is not an
# outage, and a refusal to guess is not a server crash.
_EPC_STATUS: tuple[tuple[type, int, str], ...] = (
    (EPCConfigurationError, 501, "EPC service not configured"),
    (EPCAuthenticationError, 502, "EPC upstream rejected our credentials"),
    (EPCRateLimitError, 429, "EPC upstream rate limit reached"),
    (EPCInvalidQueryError, 400, "EPC query rejected"),
    (EPCAmbiguousMatchError, 409, "EPC candidate could not be uniquely identified"),
    (EPCUnsupportedOperationError, 410, "EPC operation no longer supported"),
    (EPCUpstreamError, 503, "EPC service unavailable"),
)


def _epc_http_error(exc: Exception) -> HTTPException:
    """Translate a typed EPC failure to the status that describes it."""
    for cls, status, label in _EPC_STATUS:
        if isinstance(exc, cls):
            return HTTPException(status_code=status, detail=f"{label}: {exc}")
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
    """Get an EPC certificate by its GOV.UK certificate number.

    An optional shortcut for a certificate number already in hand — from the
    GOV.UK EPC register or an MCP summary-listing tool. `/search-area` does NOT
    supply one: it returns aggregate statistics with `certificates: null`. To
    fetch a certificate without knowing its number, use `/search` with an exact
    address, which returns the full certificate directly.

    The `{certificate_hash}` path parameter is a compatibility alias kept from
    the retired API; the value to pass is the certificate number.
    """
    if not _client.is_configured():
        raise HTTPException(status_code=501, detail="EPC client not configured")

    try:
        result = await _client.get_certificate(certificate_hash)
    except EPCError as exc:
        raise _epc_http_error(exc) from exc
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
    """Find ONE property's EPC certificate. Returns the full certificate.

    An address is required in practice: a postcode identifies an area, not a
    property, so a postcode alone cannot single one out and returns 409.

    Two ways to supply it:
    1. Explicit: postcode=SW1A+2AA&address=10+Downing+Street
    2. Combined: q=10+Downing+Street,+SW1A+2AA (postcode parsed from end)

    The address must match a certificate exactly, allowing only for case,
    punctuation and a leading Flat/Apartment designator.

    404 = the postcode holds no certificates at all. 409 = candidates exist but
    none or several matched; the service refuses rather than guessing. For a
    postcode's aggregate statistics use /search-area instead.
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
    except EPCError as exc:
        raise _epc_http_error(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="No EPC certificate found")
    return EPCRecordResponse(record=result, raw=result.raw if include_raw else None)


@router.get("/search-area", response_model=EPCAreaResponse)
async def search_area(
    postcode: str = Query(..., min_length=2, description="UK postcode"),
) -> EPCAreaResponse:
    """List EPC certificate statistics for a postcode.

    Returns the record count and, when the bounded response contains every
    matching summary, the rating distribution. Property-type breakdown and
    floor-area statistics are NOT available: the EPC service exposes them only
    on individual certificates. `certificates` is null — per-certificate detail
    is not returned by a summary search. Use /epc/search with a street address,
    or fetch a specific certificate.
    """
    if not _client.is_configured():
        raise HTTPException(status_code=501, detail="EPC client not configured")

    try:
        area = await _client.area_summary(postcode)
    except EPCError as exc:
        # Never return a zero-count summary for an outage: it is indistinguishable
        # from a postcode that genuinely has no certificates.
        raise _epc_http_error(exc) from exc

    return EPCAreaResponse(
        postcode=postcode,
        summary=EPCAreaSummary(
            # None means "unknown", never 0 — an unknown total must not read as empty.
            count=area.get("total_records"),
            rating_distribution=area.get("rating_distribution"),
            rating_distribution_sample=area.get("rating_distribution_sample"),
            rating_distribution_sample_size=area.get("rating_distribution_sample_size"),
            # Unavailable from summaries; None, never {} or 0.
            property_type_breakdown=None,
            floor_area_min=None,
            floor_area_max=None,
            floor_area_avg=None,
        ),
        # None (not []) — per-certificate detail is not returned by a summary search.
        certificates=None,
        complete=bool(area.get("complete")),
        warnings=area.get("warnings") or [],
    )
