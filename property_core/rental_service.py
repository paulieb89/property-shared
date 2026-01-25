"""Standalone rental market analysis over Rightmove listings.

This module exposes a small helper for consumer apps that want rental benchmarks
without generating a full property report.
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional

from property_core.models.report import RentalAnalysis
from property_core.rightmove_location import RightmoveLocationAPI
from property_core.rightmove_scraper import fetch_listings


def _calculate_yield(rental: RentalAnalysis, purchase_price: int) -> None:
    """Calculate gross yield based on rental and purchase price."""
    if rental.median_rent_monthly and purchase_price > 0:
        annual_rent = rental.median_rent_monthly * 12
        rental.estimated_annual_rent = annual_rent
        gross_yield = (annual_rent / purchase_price) * 100
        rental.gross_yield_pct = round(gross_yield, 2)

        if gross_yield >= 6:
            rental.yield_assessment = "strong"
        elif gross_yield >= 4:
            rental.yield_assessment = "average"
        else:
            rental.yield_assessment = "weak"


async def analyze_rentals(
    postcode: str,
    radius: float = 0.5,
    *,
    purchase_price: Optional[int] = None,
    rightmove_delay: Optional[float] = None,
    rightmove_location: Optional[RightmoveLocationAPI] = None,
) -> RentalAnalysis:
    """Analyze rental listings for a postcode with optional yield calculation.

    Args:
        postcode: UK postcode (or outcode).
        radius: Rightmove radius in miles.
        purchase_price: Optional purchase price to compute gross yield.
        rightmove_delay: Per-request politeness delay in seconds. Defaults to
            `RIGHTMOVE_DELAY_SECONDS` env var (or 0.6).
        rightmove_location: Optional injected RightmoveLocationAPI.

    Returns:
        RentalAnalysis with median/average rent and optional yield fields.
    """
    delay = rightmove_delay
    if delay is None:
        delay = float(os.environ.get("RIGHTMOVE_DELAY_SECONDS", "0.6"))

    location_api = rightmove_location or RightmoveLocationAPI(rate_limit_delay=delay)

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
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Rental analysis failed: {exc}") from exc

    prices = sorted([l.price for l in listings if l.price and l.price > 0])
    median_rent = prices[len(prices) // 2] if prices else None
    avg_rent = int(sum(prices) / len(prices)) if prices else None

    rental = RentalAnalysis(
        search_radius_miles=radius,
        rental_listings_count=len(listings),
        average_rent_monthly=avg_rent,
        median_rent_monthly=median_rent,
        rent_range_low=min(prices) if prices else None,
        rent_range_high=max(prices) if prices else None,
    )

    if purchase_price is not None:
        _calculate_yield(rental, purchase_price)

    return rental

