"""Standalone rental market analysis over Rightmove listings.

This module exposes a small helper for consumer apps that want rental benchmarks
without generating a full property report.
"""

from __future__ import annotations

import asyncio
import os
from statistics import median, quantiles
from typing import Optional

from property_core.models.report import RentalAnalysis
from property_core.rightmove_location import RightmoveLocationAPI
from property_core.rightmove_scraper import fetch_listings


def _filter_outliers(prices: list[int]) -> list[int]:
    """Remove outliers using IQR method.

    Filters values outside 1.5 * IQR from Q1/Q3 quartiles.
    Returns original list if too few values for meaningful filtering.
    """
    if len(prices) < 4:
        return prices
    q = quantiles(sorted(prices), n=4)
    iqr = q[2] - q[0]  # Q3 - Q1
    lower = q[0] - 1.5 * iqr
    upper = q[2] + 1.5 * iqr
    return [p for p in prices if lower <= p <= upper]


def to_monthly(listing) -> int:
    """Normalize a listing's price to monthly (handles weekly frequency)."""
    if listing.price_frequency == "weekly":
        return int(listing.price * 52 / 12)
    return listing.price


def _calculate_yield(
    rental: RentalAnalysis,
    purchase_price: int,
    *,
    strong_yield_pct: float = 6.0,
    average_yield_pct: float = 4.0,
) -> None:
    """Calculate gross yield based on rental and purchase price."""
    if rental.median_rent_monthly and purchase_price > 0:
        annual_rent = rental.median_rent_monthly * 12
        rental.estimated_annual_rent = annual_rent
        gross_yield = (annual_rent / purchase_price) * 100
        rental.gross_yield_pct = round(gross_yield, 2)

        if gross_yield >= strong_yield_pct:
            rental.yield_assessment = "strong"
        elif gross_yield >= average_yield_pct:
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
    filter_outliers: bool = True,
    strong_yield_pct: float = 6.0,
    average_yield_pct: float = 4.0,
) -> RentalAnalysis:
    """Analyze rental listings for a postcode with optional yield calculation.

    Args:
        postcode: UK postcode (or outcode).
        radius: Rightmove radius in miles.
        purchase_price: Optional purchase price to compute gross yield.
        rightmove_delay: Per-request politeness delay in seconds. Defaults to
            `RIGHTMOVE_DELAY_SECONDS` env var (or 0.6).
        rightmove_location: Optional injected RightmoveLocationAPI.
        filter_outliers: Apply IQR filtering to rent range display (default True).
            Median and average are always computed on the full dataset.
        strong_yield_pct: Yield >= this is "strong" (default 6.0).
        average_yield_pct: Yield >= this is "average" (default 4.0).

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

    # Normalize all prices to monthly (weekly × 52/12 ≈ 4.33)
    prices = sorted([to_monthly(l) for l in listings if l.price and l.price > 0])
    median_rent = int(median(prices)) if prices else None
    avg_rent = int(sum(prices) / len(prices)) if prices else None

    # Optionally filter outliers for range display (keeps median/avg on full dataset)
    filtered_prices = _filter_outliers(prices) if filter_outliers else prices

    rental = RentalAnalysis(
        search_radius_miles=radius,
        rental_listings_count=len(listings),
        average_rent_monthly=avg_rent,
        median_rent_monthly=median_rent,
        rent_range_low=min(filtered_prices) if filtered_prices else None,
        rent_range_high=max(filtered_prices) if filtered_prices else None,
    )

    if purchase_price is not None:
        _calculate_yield(
            rental,
            purchase_price,
            strong_yield_pct=strong_yield_pct,
            average_yield_pct=average_yield_pct,
        )

    return rental

