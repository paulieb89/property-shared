"""Yield analysis: combines PPD sale comps with Rightmove rental data.

Provides a single async function that returns gross rental yield for a postcode
by joining Land Registry transaction data with current rental listings.
"""

from __future__ import annotations

import asyncio
import os
from statistics import median as stat_median
from typing import Optional

from property_core.models.report import YieldAnalysis
from property_core.ppd_service import PPDService
from property_core.rental_service import to_monthly
from property_core.rightmove_location import RightmoveLocationAPI
from property_core.rightmove_scraper import fetch_listings


async def calculate_yield(
    postcode: str,
    *,
    months: int = 24,
    search_level: str = "sector",
    radius: float = 0.5,
    rightmove_delay: Optional[float] = None,
) -> YieldAnalysis:
    """Calculate gross rental yield for a postcode.

    Combines PPD comparable sales (median sale price) with Rightmove rental
    listings (median monthly rent) to produce a gross yield figure.

    Returns raw numbers only. Use property_core.interpret.classify_yield()
    and classify_data_quality() for human-readable labels.

    Args:
        postcode: UK postcode to analyse.
        months: Lookback period for PPD sales data.
        search_level: PPD search granularity ("postcode", "sector", "district").
        radius: Rightmove rental search radius in miles.
        rightmove_delay: Per-request delay in seconds (default from env or 0.6).

    Returns:
        YieldAnalysis with combined sale/rental data and yield calculation.
    """
    delay = rightmove_delay
    if delay is None:
        delay = float(os.environ.get("RIGHTMOVE_DELAY_SECONDS", "0.6"))

    # Fetch PPD comps (sync → thread)
    ppd = PPDService()
    comps = await asyncio.to_thread(
        ppd.comps,
        postcode=postcode,
        months=months,
        search_level=search_level,
    )

    if not comps.median or comps.thin_market:
        return YieldAnalysis(
            postcode=postcode,
            median_sale_price=comps.median,
            sale_count=comps.count,
            thin_market=comps.thin_market,
        )

    # Fetch rental listings (sync → thread)
    location_api = RightmoveLocationAPI(rate_limit_delay=delay)
    try:
        url = await asyncio.to_thread(
            location_api.build_search_url,
            postcode,
            property_type="rent",
            radius=radius,
        )
        listings = await asyncio.to_thread(
            fetch_listings,
            url,
            max_pages=1,
            rate_limit_seconds=delay,
        )
    except Exception:
        return YieldAnalysis(
            postcode=postcode,
            median_sale_price=comps.median,
            sale_count=comps.count,
            thin_market=comps.thin_market,
        )

    # Keep all listings with valid prices - LET_AGREED are confirmed
    # deals and arguably better data than aspirational asking rents
    active = [l for l in listings if l.price and l.price > 0]

    if not active:
        return YieldAnalysis(
            postcode=postcode,
            median_sale_price=comps.median,
            sale_count=comps.count,
            thin_market=comps.thin_market,
        )

    # Calculate median rent (normalize weekly → monthly)
    prices = sorted([to_monthly(l) for l in active])
    median_rent = int(stat_median(prices))

    # Calculate yield
    annual_rent = median_rent * 12
    gross_yield = round((annual_rent / comps.median) * 100, 2)

    return YieldAnalysis(
        postcode=postcode,
        median_sale_price=comps.median,
        sale_count=comps.count,
        median_monthly_rent=median_rent,
        rental_count=len(active),
        gross_yield_pct=gross_yield,
        thin_market=comps.thin_market,
    )
