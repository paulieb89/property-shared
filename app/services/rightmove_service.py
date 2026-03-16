"""Rightmove service wrapper.

Wraps the pure-python Rightmove helpers with:
- politeness defaults (delay + low concurrency)
- async-friendly execution (runs sync network code in a thread)
"""

from __future__ import annotations

from functools import partial
from typing import Optional

import anyio

from app.core.config import get_settings
from app.schemas.rightmove import RightmoveListing, RightmoveListingDetail
from app.utils.polite import PoliteLimiter
from property_core.rightmove_location import RightmoveLocationAPI
from property_core.rightmove_scraper import fetch_listing, fetch_listings


class RightmoveService:
    def __init__(
        self,
        *,
        location_api: Optional[RightmoveLocationAPI] = None,
        limiter: Optional[PoliteLimiter] = None,
    ):
        settings = get_settings()
        self.location_api = location_api or RightmoveLocationAPI(
            rate_limit_delay=settings.rightmove_delay_seconds,
        )
        # Concurrency guard is useful even if per-request delays are handled in core.
        self.limiter = limiter or PoliteLimiter(
            max_concurrency=settings.rightmove_max_concurrency,
            min_delay_seconds=0.0,
        )
        self._delay = settings.rightmove_delay_seconds

    async def build_search_url(
        self,
        *,
        postcode: str,
        property_type: str,
        min_price: int | None = None,
        max_price: int | None = None,
        min_bedrooms: int | None = None,
        max_bedrooms: int | None = None,
        radius: float | None = None,
    ) -> str:
        async with self.limiter:
            fn = partial(
                self.location_api.build_search_url,
                postcode,
                property_type=property_type,
                min_price=min_price,
                max_price=max_price,
                min_bedrooms=min_bedrooms,
                max_bedrooms=max_bedrooms,
                radius=radius,
            )
            return await anyio.to_thread.run_sync(fn)

    async def listings(
        self,
        *,
        search_url: str,
        max_pages: int | None = None,
        include_raw: bool = False,
    ) -> list[RightmoveListing]:
        async with self.limiter:
            fn = partial(
                fetch_listings,
                search_url,
                max_pages=max_pages,
                rate_limit_seconds=self._delay,
                include_raw=include_raw,
            )
            results = await anyio.to_thread.run_sync(fn)
        return results

    async def listing_detail(
        self,
        *,
        property_url_or_id: str,
        include_raw: bool = False,
    ) -> RightmoveListingDetail:
        async with self.limiter:
            fn = partial(
                fetch_listing,
                property_url_or_id,
                include_raw=include_raw,
            )
            result = await anyio.to_thread.run_sync(fn)
        return result
