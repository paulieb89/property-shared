"""Stamp duty calculator endpoint."""

from fastapi import APIRouter, Query

from property_core.stamp_duty import StampDutyResult, calculate_stamp_duty

router = APIRouter(prefix="/calculators", tags=["calculators"])


@router.get("/stamp-duty", response_model=StampDutyResult)
async def stamp_duty(
    price: int = Query(..., ge=0, description="Purchase price in £"),
    additional_property: bool = Query(True, description="Additional property surcharge (+5%)"),
    first_time_buyer: bool = Query(False, description="First-time buyer relief"),
    non_resident: bool = Query(False, description="Non-UK resident surcharge (+2%)"),
) -> StampDutyResult:
    """Calculate UK Stamp Duty Land Tax (SDLT) for a residential property."""
    return calculate_stamp_duty(
        price=price,
        additional_property=additional_property,
        first_time_buyer=first_time_buyer,
        non_resident=non_resident,
    )
