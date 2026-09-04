"""Rightmove API endpoints: search URL, listings, and listing detail."""

from __future__ import annotations

from functools import partial
from typing import Literal, Optional

import anyio
from fastapi import APIRouter, HTTPException, Path, Query

from app.schemas.rightmove import (
    RightmoveListingDetailResponse,
    RightmoveListingsResponse,
    RightmoveSearchURLResponse,
)
from property_core.exceptions import (
    InvalidPostcodeError,
    LocationLookupError,
    LocationNotFoundError,
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
    # Raised inside the worker thread; exceptions propagate unchanged out of
    # anyio.to_thread.run_sync, so these map exactly as they would inline.
    except InvalidPostcodeError as exc:
        raise HTTPException(status_code=422, detail=exc.to_dict()) from exc
    except LocationNotFoundError as exc:
        # 404, not 422: the input is well-formed; what does not exist is a
        # Rightmove location for it. Same line as GET /ppd/transaction.
        raise HTTPException(status_code=404, detail=exc.to_dict()) from exc
    except LocationLookupError as exc:
        raise HTTPException(status_code=502, detail=exc.to_dict()) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Rightmove lookup failed: {exc}") from exc


@router.get("/listings", response_model=RightmoveListingsResponse)
async def listings(
    postcode: str = Query(..., min_length=2),
    property_type: Literal["sale", "rent"] = "sale",
    building_type: Optional[str] = Query(None, description="F=flat, D=detached, S=semi, T=terraced"),
    min_price: Optional[int] = Query(None, ge=0),
    max_price: Optional[int] = Query(None, ge=0),
    min_bedrooms: Optional[int] = Query(None, ge=0),
    max_bedrooms: Optional[int] = Query(None, ge=0),
    radius: Optional[float] = Query(None, ge=0),
    sort_by: Optional[str] = Query(None, description="newest|oldest|price_low|price_high|most_reduced"),
    max_pages: Optional[int] = Query(None, ge=1, le=20),
    include_raw: bool = Query(False, description="Ignored (raw is always included in v2)"),
) -> RightmoveListingsResponse:
    """Fetch listing results for a postcode.

    Takes the same structured filters as ``/search-url`` and builds the Rightmove
    URL server-side. This endpoint previously accepted an arbitrary ``search_url``
    and fetched it, which was an SSRF vector; raw URLs are no longer accepted.
    """
    try:
        search_url = await anyio.to_thread.run_sync(
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
        results = await anyio.to_thread.run_sync(
            partial(fetch_listings, search_url, max_pages=max_pages)
        )
        return RightmoveListingsResponse(count=len(results), results=results)
    # This endpoint builds its own search URL, so it needs the same mapping as
    # /search-url. Without it a sector returned 502 here while returning 422
    # there, for identical input.
    except InvalidPostcodeError as exc:
        raise HTTPException(status_code=422, detail=exc.to_dict()) from exc
    except LocationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.to_dict()) from exc
    except LocationLookupError as exc:
        raise HTTPException(status_code=502, detail=exc.to_dict()) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Rightmove listings failed: {exc}") from exc


@router.get("/listing/{property_id}", response_model=RightmoveListingDetailResponse)
async def listing_detail(
    property_id: str = Path(
        ..., pattern=r"^[0-9]{1,12}$", description="Numeric Rightmove property ID"
    ),
    include_raw: bool = Query(False, description="Ignored (raw is always included in v2)"),
) -> RightmoveListingDetailResponse:
    """Fetch full details for an individual Rightmove property listing.

    ``property_id`` must be the numeric Rightmove ID. Full URLs are rejected at
    the routing layer (422) — they were previously fetched server-side.
    """
    try:
        result = await anyio.to_thread.run_sync(
            partial(fetch_listing, property_id)
        )
        return RightmoveListingDetailResponse(result=result)
    # No `except ValueError -> 422` here: the Path regex above is the only ID
    # gate needed, and pydantic's ValidationError subclasses ValueError, so
    # catching it would report an upstream page-shape change as caller error
    # (and leak internal field names) instead of paging on a 502.
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Rightmove listing detail failed: {exc}") from exc
