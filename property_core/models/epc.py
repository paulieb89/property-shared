"""Domain models for EPC data."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict


# --- Helpers ---

def _str_or_none(val: Any) -> Optional[str]:
    """Return val as str, or None if empty/missing."""
    if val is None:
        return None
    s = str(val)
    return s if s else None


def _int_or_none(val: Any) -> Optional[int]:
    """Coerce val to int, or None if empty/missing/invalid."""
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _float_or_none(val: Any) -> Optional[float]:
    """Coerce val to float, or None if empty/missing/invalid."""
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


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

    # Additional fields
    lmk_key: str | None = None
    postcode: str | None = None
    uprn: str | None = None
    tenure: str | None = None
    habitable_rooms: int | None = None
    floor_level: str | None = None
    lodgement_date: str | None = None
    mains_gas: str | None = None

    # Raw API response dict (populated by from_api_row)
    raw: dict[str, Any] | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def from_api_row(cls, row: Dict[str, Any]) -> EPCData:
        """Construct an EPCData from an EPC API response row.

        The EPC API returns kebab-case keys which are mapped to model fields.
        Empty strings are converted to None for optional fields.
        """
        return cls(
            # Core ratings
            rating=row.get("current-energy-rating", ""),
            score=_int_or_none(row.get("current-energy-efficiency")) or 0,
            potential_rating=_str_or_none(row.get("potential-energy-rating")),
            potential_score=_int_or_none(row.get("potential-energy-efficiency")),
            # Property details
            address=_str_or_none(row.get("address")),
            floor_area=_float_or_none(row.get("total-floor-area")),
            built_form=_str_or_none(row.get("built-form")),
            property_type=_str_or_none(row.get("property-type")),
            construction_age=_str_or_none(row.get("construction-age-band")),
            # Running costs
            heating_cost_current=_int_or_none(row.get("heating-cost-current")),
            heating_cost_potential=_int_or_none(row.get("heating-cost-potential")),
            hot_water_cost_current=_int_or_none(row.get("hot-water-cost-current")),
            hot_water_cost_potential=_int_or_none(row.get("hot-water-cost-potential")),
            lighting_cost_current=_int_or_none(row.get("lighting-cost-current")),
            lighting_cost_potential=_int_or_none(row.get("lighting-cost-potential")),
            # Heating system
            main_fuel=_str_or_none(row.get("main-fuel")),
            main_heating=_str_or_none(row.get("mainheat-description")),
            hot_water=_str_or_none(row.get("hotwater-description")),
            # Component efficiency
            walls_efficiency=_str_or_none(row.get("walls-energy-eff")),
            roof_efficiency=_str_or_none(row.get("roof-energy-eff")),
            floor_efficiency=_str_or_none(row.get("floor-energy-eff")),
            windows_efficiency=_str_or_none(row.get("windows-energy-eff")),
            windows_description=_str_or_none(row.get("windows-description")),
            # Environmental
            co2_emissions_current=_float_or_none(row.get("co2-emissions-current")),
            co2_emissions_potential=_float_or_none(row.get("co2-emissions-potential")),
            # Metadata
            inspection_date=_str_or_none(row.get("inspection-date")),
            certificate_hash=_str_or_none(row.get("lmk-key")),
            # Additional fields
            lmk_key=_str_or_none(row.get("lmk-key")),
            postcode=_str_or_none(row.get("postcode")),
            uprn=_str_or_none(row.get("uprn")),
            tenure=_str_or_none(row.get("tenure")),
            habitable_rooms=_int_or_none(row.get("number-habitable-rooms")),
            floor_level=_str_or_none(row.get("floor-level")),
            lodgement_date=_str_or_none(row.get("lodgement-date")),
            mains_gas=_str_or_none(row.get("mains-gas-flag")),
            # Raw
            raw=row,
        )
