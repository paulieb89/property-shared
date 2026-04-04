"""Rightmove API endpoints: search URL, listings, and listing detail."""

from __future__ import annotations

from functools import partial
from typing import Literal, Optional

import anyio
from fastapi import APIRouter, HTTPException, Query

from app.schemas.rightmove import (
    RightmoveListingDetailResponse,
    RightmoveListingsResponse,
    RightmoveSearchURLResponse,
)
from property_core.rightmove_location import RightmoveLocationAPI
from property_core.rightmove_scraper import fetch_listing, fetch_listings

router = APIRouter(prefix="/rightmove", tags=["rightmove"])


@router.get("/search-url", response_model=RightmoveSearchURLResponse)
async def search_url(
    postcode: str = Query(..., min_length=2),
    property_type: Literal["sale", "rent"] = "sale",
    building_type: Optional[str] = Query(None, description="F=flat, D=detached, S=semi, T=terraced"),
    min_price: Optional[int] = Query(None, ge=0),
    max_price: Optional[int] = Query(None, ge=0),
    min_bedrooms: Optional[int] = Query(None, ge=0),
    max_bedrooms: Optional[int] = Query(None, ge=0),
    radius: Optional[float] = Query(None, ge=0),
    sort_by: Optional[str] = Query(None, description="newest|oldest|price_low|price_high|most_reduced"),
) -> RightmoveSearchURLResponse:
    """Build a Rightmove search URL from a postcode/outcode."""
    try:
        url = await anyio.to_thread.run_sync(
            partial(
                RightmoveLocationAPI().build_search_url,
                postcode,
                property_type=property_type,
                building_type=building_type,
                min_price=min_price,
                max_price=max_price,
                min_bedrooms=min_bedrooms,
                max_bedrooms=max_bedrooms,
                radius=radius,
                sort_by=sort_by,
            )
        )
        return RightmoveSearchURLResponse(url=url)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Rightmove lookup failed: {exc}") from exc


@router.get("/listings", response_model=RightmoveListingsResponse)
async def listings(
    search_url: str = Query(..., min_length=10),
    max_pages: Optional[int] = Query(None, ge=1, le=20),
    include_raw: bool = Query(False, description="Ignored (raw is always included in v2)"),
) -> RightmoveListingsResponse:
    """Fetch listing results from a Rightmove search URL."""
    try:
        results = await anyio.to_thread.run_sync(
            partial(fetch_listings, search_url, max_pages=max_pages)
        )
        return RightmoveListingsResponse(count=len(results), results=results)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Rightmove listings failed: {exc}") from exc


@router.get("/listing/{property_id}", response_model=RightmoveListingDetailResponse)
async def listing_detail(
    property_id: str,
    include_raw: bool = Query(False, description="Ignored (raw is always included in v2)"),
) -> RightmoveListingDetailResponse:
    """Fetch full details for an individual Rightmove property listing."""
    try:
        result = await anyio.to_thread.run_sync(
            partial(fetch_listing, property_id)
        )
        return RightmoveListingDetailResponse(result=result)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Rightmove listing detail failed: {exc}") from exc
