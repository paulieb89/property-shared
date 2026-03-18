"""UK Stamp Duty Land Tax (SDLT) calculator.

April 2025 rates with additional property surcharge (+5%, Oct 2024),
non-resident surcharge (+2%), and first-time buyer relief.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class StampDutyBand(BaseModel):
    """A single SDLT band in the calculation breakdown."""
    band: str
    amount: int
    rate: float
    tax: float


class StampDutyResult(BaseModel):
    """Complete SDLT calculation result."""
    total_sdlt: float
    effective_rate: float
    price: int
    additional_property: bool
    first_time_buyer: bool
    non_resident: bool
    surcharges_applied: float
    breakdown: list[StampDutyBand] = Field(default_factory=list)


# April 2025 SDLT bands: (threshold, base rate %)
_STANDARD_BANDS: list[tuple[float, float]] = [
    (125_000, 0),
    (250_000, 2),
    (925_000, 5),
    (1_500_000, 10),
    (float("inf"), 12),
]

# First-time buyer bands (properties up to £500k only)
_FTB_BANDS: list[tuple[float, float]] = [
    (300_000, 0),
    (500_000, 5),
]


def calculate_stamp_duty(
    price: int,
    additional_property: bool = True,
    first_time_buyer: bool = False,
    non_resident: bool = False,
) -> StampDutyResult:
    """Calculate UK Stamp Duty Land Tax for a residential property.

    Args:
        price: Purchase price in £.
        additional_property: True if buying additional property (+5% surcharge).
            Defaults to True (investor-focused).
        first_time_buyer: True for first-time buyer relief (up to £300k nil rate).
        non_resident: True if buyer not UK resident (+2% surcharge).

    Returns:
        StampDutyResult with total SDLT, effective rate, and band breakdown.

    Raises:
        ValueError: If price is negative.
    """
    if price < 0:
        raise ValueError("Price cannot be negative")

    if price == 0:
        return StampDutyResult(
            total_sdlt=0,
            effective_rate=0,
            price=0,
            additional_property=additional_property,
            first_time_buyer=first_time_buyer,
            non_resident=non_resident,
            surcharges_applied=0,
            breakdown=[],
        )

    # Surcharges
    surcharge = 0.0
    if additional_property:
        surcharge += 5  # Increased from 3% to 5% (Oct 2024)
    if non_resident:
        surcharge += 2

    # FTB relief: only if price ≤ 500k and not additional property
    if first_time_buyer and price <= 500_000 and not additional_property:
        bands = _FTB_BANDS
    else:
        bands = _STANDARD_BANDS

    total_sdlt = 0.0
    breakdown: list[StampDutyBand] = []
    remaining = price
    prev_threshold = 0

    for threshold, rate in bands:
        if remaining <= 0:
            break

        if threshold == float("inf"):
            band_amount = remaining
        else:
            band_amount = min(remaining, int(threshold) - prev_threshold)
        effective_rate = rate + surcharge
        band_tax = band_amount * (effective_rate / 100)

        if band_amount > 0:
            if threshold == float("inf"):
                band_label = f"Above £{prev_threshold:,}"
            else:
                band_label = f"£{prev_threshold:,} - £{int(threshold):,}"

            breakdown.append(StampDutyBand(
                band=band_label,
                amount=band_amount,
                rate=effective_rate,
                tax=round(band_tax, 2),
            ))

        total_sdlt += band_tax
        remaining -= band_amount
        if threshold != float("inf"):
            prev_threshold = int(threshold)

    effective_rate_pct = round((total_sdlt / price) * 100, 2) if price > 0 else 0

    return StampDutyResult(
        total_sdlt=round(total_sdlt, 2),
        effective_rate=effective_rate_pct,
        price=price,
        additional_property=additional_property,
        first_time_buyer=first_time_buyer,
        non_resident=non_resident,
        surcharges_applied=surcharge,
        breakdown=breakdown,
    )
