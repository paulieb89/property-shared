"""Project a source certificate onto the v1 EPCData contract.

Compatibility means every existing v1 field remains present with its type and
meaning. It does not mean inventing values the upstream no longer supplies.

EPCData.rating is `str` and EPCData.score is `int`, both non-Optional. That is
exactly why the retired-API code wrote rating="" and score=0 — the model cannot
represent missing. Those defaults are forbidden now, so a certificate lacking
either cannot be projected and raises instead.

Three legacy fields have no demonstrated source anywhere in the new API and are
returned as None with an explicit warning rather than guessed:
  * lodgement_date    — no old-API capture exists to prove equivalence with
                        registration_date or completion_date
  * construction_age  — absent from all 11 observed schemas
  * floor_level       — absent from all 11 observed schemas
"""

from __future__ import annotations

from typing import Any, Optional

from property_core.epc.errors import EPCUnsupportedOperationError
from property_core.epc.source_models import UNRESOLVED_CODE_TABLES, EPCCertificateDoc
from property_core.models.epc import EPCData

LEGACY_CURRENCY = "GBP"

_NO_DEMONSTRATED_SOURCE = (
    "lodgement_date, construction_age and floor_level have no demonstrated "
    "equivalent in the replacement EPC API and are reported as missing rather "
    "than inferred"
)


def _money(value, field: str, warnings: list[str], inferred: list[str]) -> Optional[int]:
    """Legacy scalar, when the currency is the expected one or was never stated.

    The legacy field is typed `int | None`, so the projection must stay int —
    widening it to float would itself be a contract change.

    Legacy SAP schemas (13.0, 14.0, 14.2, 15.0) return a bare number with no
    currency. That is precisely the shape the retired v1 API used, and the
    register covers England and Wales only, so the amount is read as GBP rather
    than discarded — but the inference is recorded in `inferred` so the caller
    can disclose it ONCE per certificate instead of once per field. All six cost
    fields share a schema's shape, so per-field warnings would be six copies of
    the same sentence.
    """
    if value is None:
        return None
    # Keyed off the currency itself rather than the flag, so a directly
    # constructed EPCMoney cannot desync the two and change behaviour.
    if value.currency is None:
        inferred.append(field)
    elif value.currency != LEGACY_CURRENCY:
        warnings.append(
            f"{field} is denominated in {value.currency}; the legacy scalar field "
            f"expects {LEGACY_CURRENCY} and is reported as missing. The structured "
            f"value is available on the source model."
        )
        return None
    rounded = int(value.value.to_integral_value())
    if value.value != rounded:
        warnings.append(
            f"{field} {value.value} was rounded to {rounded} for the legacy integer "
            f"field; the exact value is on the source model"
        )
    return rounded


def to_epcdata(
    doc: EPCCertificateDoc,
    *,
    codebook: Any = None,
    return_warnings: bool = False,
):
    """Build a v1 EPCData from a source certificate.

    Raises:
        EPCUnsupportedOperationError: If the certificate lacks a band or numeric
            score. Those are non-Optional on EPCData, and fabricating "" or 0 is
            not compatibility.
    """
    warnings: list[str] = []
    # Cost fields whose currency upstream never stated (legacy SAP scalar
    # shape). Collected so the inference is disclosed once, not six times.
    inferred_currency: list[str] = []

    if not doc.current_energy_efficiency_band:
        raise EPCUnsupportedOperationError(
            f"certificate {doc.certificate_number} has no energy band; EPCData.rating "
            "is non-Optional and a placeholder would misrepresent the property"
        )
    if doc.energy_rating_current is None:
        raise EPCUnsupportedOperationError(
            f"certificate {doc.certificate_number} has no numeric energy score; "
            "EPCData.score is non-Optional and 0 is a plausible band-G value, so a "
            "placeholder would be indistinguishable from real data"
        )

    def label(code: str, key: Optional[int]) -> Optional[str]:
        if key is None:
            return None
        resolved = codebook.label_sync(code, key, doc.schema_type) if codebook else None
        if resolved is None:
            warnings.append(
                f"{code} code {key} could not be resolved to a label; the raw code is "
                f"preserved on the source model and the legacy field is reported as missing"
            )
        return resolved

    warnings.append(_NO_DEMONSTRATED_SOURCE)
    if UNRESOLVED_CODE_TABLES:
        warnings.append(
            "no upstream code table exists for: " + ", ".join(UNRESOLVED_CODE_TABLES)
        )

    data = EPCData(
        rating=doc.current_energy_efficiency_band,
        score=doc.energy_rating_current,
        potential_rating=doc.potential_energy_efficiency_band,
        potential_score=doc.energy_rating_potential,
        address=doc.address,
        floor_area=doc.total_floor_area,
        built_form=label("built_form", doc.built_form_code),
        property_type=label("property_type", doc.property_type_code),
        tenure=label("tenure", doc.tenure_code),
        construction_age=None,     # no demonstrated source
        floor_level=None,          # no demonstrated source
        lodgement_date=None,       # equivalence not demonstrated
        heating_cost_current=_money(doc.heating_cost_current, "heating_cost_current", warnings, inferred_currency),
        heating_cost_potential=_money(doc.heating_cost_potential, "heating_cost_potential", warnings, inferred_currency),
        hot_water_cost_current=_money(doc.hot_water_cost_current, "hot_water_cost_current", warnings, inferred_currency),
        hot_water_cost_potential=_money(doc.hot_water_cost_potential, "hot_water_cost_potential", warnings, inferred_currency),
        lighting_cost_current=_money(doc.lighting_cost_current, "lighting_cost_current", warnings, inferred_currency),
        lighting_cost_potential=_money(doc.lighting_cost_potential, "lighting_cost_potential", warnings, inferred_currency),
        co2_emissions_current=doc.co2_emissions_current,
        co2_emissions_potential=doc.co2_emissions_potential,
        inspection_date=doc.inspection_date,
        certificate_hash=doc.certificate_number,
        lmk_key=doc.certificate_number,
        postcode=doc.postcode,
        uprn=doc.uprn,
        habitable_rooms=doc.habitable_room_count,
        raw=doc.raw,
    )

    if inferred_currency:
        # One sentence per certificate. Naming the fields would repeat the
        # same disclosure six times, since a schema's cost fields share a shape.
        #
        # INSERTED FIRST, not appended. Every other warning here explains why
        # something is ABSENT; this one qualifies a number that is present and
        # that the reader is looking at. Buried behind the missing-field notes it
        # read as boilerplate, so a cost could be taken as measured when only its
        # amount was. Ordering is pinned by tests/test_epc_warning_order.py.
        warnings.insert(
            0,
            "cost amounts were returned by upstream as bare numbers with no "
            f"currency (the legacy {doc.schema_type or 'SAP'} scalar shape); they are "
            "interpreted as GBP, inferred from that shape and the England and "
            "Wales scope of the register, not stated by the source",
        )
    data.warnings = warnings
    return (data, warnings) if return_warnings else data
