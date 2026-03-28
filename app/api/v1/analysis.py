"""Yield and rental analysis endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from property_core.models.report import RentalAnalysis, YieldAnalysis

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/yield", response_model=YieldAnalysis)
async def yield_analysis(
    postcode: str = Query(..., min_length=2, description="UK postcode"),
    months: int = Query(24, ge=1, le=120, description="PPD lookback months"),
    search_level: str = Query("sector", description="postcode|sector|district"),
    property_type: Optional[str] = Query(None, description="D/S/T/F/O"),
    radius: float = Query(0.5, ge=0.1, description="Rental search radius (miles)"),
) -> YieldAnalysis:
    """Calculate gross rental yield for a UK postcode.

    Combines Land Registry sales (median price) with Rightmove rentals (median rent).
    """
    from property_core import calculate_yield

    try:
        return await calculate_yield(
            postcode=postcode,
            months=months,
            search_level=search_level,
            property_type=property_type,
            radius=radius,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Yield analysis failed: {exc}") from exc


@router.get("/rental", response_model=RentalAnalysis)
async def rental_analysis(
    postcode: str = Query(..., min_length=2, description="UK postcode"),
    radius: float = Query(0.5, ge=0.1, description="Search radius (miles)"),
    purchase_price: Optional[int] = Query(None, ge=0, description="Purchase price for yield calc"),
) -> RentalAnalysis:
    """Rental market analysis for a UK postcode.

    Returns median/average rent, listing count, and rent range.
    Optionally calculates gross yield from a given purchase price.
    """
    from property_core.rental_service import analyze_rentals

    try:
        return await analyze_rentals(
            postcode,
            radius=radius,
            purchase_price=purchase_price,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Rental analysis failed: {exc}") from exc
