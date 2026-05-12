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
    property_type: Optional[str] = Query(None, description="D/S/T/F/O, or ALL for firehose"),
    radius: float = Query(0.5, ge=0.1, description="Rental search radius (miles)"),
    auto_escalate: bool = Query(True, description="Widen PPD search on thin markets (default true)"),
) -> YieldAnalysis:
    """Calculate gross rental yield for a UK postcode.

    Combines Land Registry sales (median price) with Rightmove rentals (median rent).
    Auto-escalates the PPD search from postcode→sector→district on thin markets so
    thin postcodes still return useful data. Pass auto_escalate=false to opt out.
    """
    from property_core import calculate_yield

    try:
        return await calculate_yield(
            postcode=postcode,
            months=months,
            search_level=search_level,
            property_type=property_type,
            radius=radius,
            auto_escalate=auto_escalate,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Yield analysis failed: {exc}") from exc


@router.get("/rental", response_model=RentalAnalysis)
async def rental_analysis(
    postcode: str = Query(..., min_length=2, description="UK postcode"),
    radius: float = Query(0.5, ge=0.1, description="Search radius (miles)"),
    purchase_price: Optional[int] = Query(None, ge=0, description="Purchase price for yield calc"),
    building_type: Optional[str] = Query(None, description="F=flat, D=detached, S=semi, T=terraced"),
    auto_escalate: bool = Query(True, description="Widen rental search on thin markets (default true)"),
) -> RentalAnalysis:
    """Rental market analysis for a UK postcode.

    Returns median/average rent, listing count, and rent range.
    Optionally calculates gross yield from a given purchase price.
    Auto-escalates the rental search radius on thin markets (0.5 → 1.0 mi).
    Pass auto_escalate=false to opt out.
    """
    from property_core.rental_service import analyze_rentals

    try:
        return await analyze_rentals(
            postcode,
            radius=radius,
            purchase_price=purchase_price,
            building_type=building_type,
            auto_escalate=auto_escalate,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Rental analysis failed: {exc}") from exc
