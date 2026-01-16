"""Location assessment endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.schemas.location import LocationAssessment
from app.services.location_service import LocationService

router = APIRouter(prefix="/location", tags=["location"])
service = LocationService()


@router.get("/assess", response_model=LocationAssessment)
async def assess(
    postcode: str = Query(..., min_length=2, description="Full postcode or outcode"),
    address: Optional[str] = Query(None, description="Optional full address context"),
) -> LocationAssessment:
    """Return a lightweight location assessment for a postcode."""
    try:
        return await service.assess(postcode=postcode, address=address)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
