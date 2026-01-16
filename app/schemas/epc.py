"""Pydantic schema for EPC responses."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class EPCData(BaseModel):
    # Core ratings
    rating: str
    score: int
    potential_rating: str | None = None
    potential_score: int | None = None

    # Property details
    address: str | None = None
    floor_area: float | None = None
    built_form: str | None = None
    property_type: str | None = None
    construction_age: str | None = None

    # Running costs
    heating_cost_current: int | None = None
    heating_cost_potential: int | None = None
    hot_water_cost_current: int | None = None
    hot_water_cost_potential: int | None = None
    lighting_cost_current: int | None = None
    lighting_cost_potential: int | None = None

    # Heating system
    main_fuel: str | None = None
    main_heating: str | None = None
    hot_water: str | None = None

    # Component efficiency
    walls_efficiency: str | None = None
    roof_efficiency: str | None = None
    floor_efficiency: str | None = None
    windows_efficiency: str | None = None
    windows_description: str | None = None

    # Environmental
    co2_emissions_current: float | None = None
    co2_emissions_potential: float | None = None

    # Metadata
    inspection_date: str | None = None
    certificate_hash: str | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class EPCRecordResponse(BaseModel):
    """Normalized EPC record with optional raw payload."""

    record: EPCData
    raw: Optional[dict[str, Any]] = None
