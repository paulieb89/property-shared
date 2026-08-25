"""Domain models for EPC data."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


# --- Helpers ---

_EPC_DIRTY = frozenset({"NO DATA!", "INVALID!", "NO DATA", "INVALID", "VARIOUS", "UNKNOWN"})


def _str_or_none(val: Any) -> Optional[str]:
    """Return val as str, or None if empty/missing/dirty EPC sentinel."""
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.upper() in _EPC_DIRTY:
        return None
    return s


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

    # Additive (v1.14.0): source-migration provenance — unresolved code labels,
    # non-GBP costs, and fields with no demonstrated source in the new API.
    warnings: list[str] = Field(default_factory=list)

    # Raw API response dict (populated by from_api_row)
    raw: dict[str, Any] | None = Field(default=None, exclude=True)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def from_api_row(cls, row: Dict[str, Any]) -> EPCData:
        """DEPRECATED — parses the RETIRED kebab-case EPC API response.

        The host this parsed (epc.opendatacommunities.org) has been retired. No
        production path calls this: `property_core/epc/compat.to_epcdata()` is
        the only constructor used, and it refuses to fabricate.

        It is retained for third-party callers holding archived kebab-case rows,
        but it will no longer invent values. Missing `current-energy-rating` or
        `current-energy-efficiency` raises instead of writing `""` and `0` — a
        score of 0 is a plausible band-G value, so the old default was
        indistinguishable from real data.

        Raises:
            ValueError: If the row lacks a rating or a numeric efficiency score.
        """
        rating = _str_or_none(row.get("current-energy-rating"))
        score = _int_or_none(row.get("current-energy-efficiency"))
        if rating is None:
            raise ValueError(
                "EPCData.from_api_row: row has no 'current-energy-rating'. This "
                "constructor parses the retired EPC API and no longer substitutes "
                'an empty rating. Use property_core.epc.compat.to_epcdata() instead.'
            )
        if score is None:
            raise ValueError(
                "EPCData.from_api_row: row has no 'current-energy-efficiency'. A "
                "score of 0 is a plausible band-G value, so it is not a safe "
                "placeholder. Use property_core.epc.compat.to_epcdata() instead."
            )
        return cls(
            # Core ratings
            rating=rating,
            score=score,
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
