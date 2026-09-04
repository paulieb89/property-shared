"""Source models matching the observed GOV.UK EPC API.

Two adapters, deliberately separate — the live API uses different naming
conventions for each, proven by probe:

    search      camelCase   certificateNumber, addressLine1, currentEnergyEfficiencyBand
    certificate snake_case  address_line_1,    current_energy_efficiency_band

A shared mapping would silently yield all-None from one of them.

Requiredness follows the OAS, not observation: the certificate schema is
`additionalProperties: true` with no declared fields, and the search-result
schema has no `required:` block. Everything here is therefore Optional;
"observed always present" is asserted in tests instead.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from pydantic import BaseModel, Field

from property_core.epc.errors import EPCUpstreamShapeError

# Fields that identify which adapter a payload belongs to.
_SEARCH_MARKERS = {"certificateNumber", "addressLine1", "currentEnergyEfficiencyBand", "schemaType"}
_CERT_MARKERS = {"address_line_1", "current_energy_efficiency_band", "schema_type", "assessment_type"}

# Coded fields resolvable via /api/codes in v1.14.0. The key space is STRING,
# not integer: alongside the numeric keys the tables carry `ND` ("unknown") and
# `NR` ("Not Recorded"), and certificates do return them — measured 2026-09-05,
# 8 of 133 live certificates (6.0%) carried one. Typing these int made every
# such certificate unfetchable. Six further coded fields
# (conservatory_type, language_code, measurement_type, multiple_glazing_type,
# region_code, report_type) have no table upstream at all — see
# UNRESOLVED_CODE_TABLES.
RESOLVABLE_CODES = ("built_form", "property_type", "tenure")
UNRESOLVED_CODE_TABLES = (
    "conservatory_type", "language_code", "measurement_type",
    "multiple_glazing_type", "region_code", "report_type",
)

_QUANTITY_FIELDS = ("co2_emissions_current", "co2_emissions_potential")

_MONEY_FIELDS = (
    "heating_cost_current", "heating_cost_potential",
    "hot_water_cost_current", "hot_water_cost_potential",
    "lighting_cost_current", "lighting_cost_potential",
)


def _str_or_none(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _finite(raw: Any, field: str) -> Decimal:
    """Decimal or EPCUpstreamShapeError — never a bare pydantic ValidationError.

    json.loads accepts the literals NaN, Infinity and -Infinity, and pydantic
    rejects non-finite Decimals with a ValidationError. That would escape the EPC
    error taxonomy and surface as an unhandled 500 instead of a typed failure.
    """
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise EPCUpstreamShapeError(f"{field}: value is not numeric: {raw!r}") from exc
    if not value.is_finite():
        raise EPCUpstreamShapeError(f"{field}: value is not finite: {raw!r}")
    return value


class EPCMoney(BaseModel):
    """A currency amount. Decimal, because these are money.

    Two shapes are observed upstream, and which one appears is a property of the
    SCHEMA, not of the field — all six cost fields move together:

        RdSAP 17.0/17.1/18.0/19.0/20.0.0, SAP 16.0/16.2 -> {"value", "currency"}
        SAP 13.0/14.0/14.2/15.0                         -> a bare number

    A bare number states no currency, so ``currency`` stays None and
    ``currency_stated`` is False. The raw shape is deliberately NOT rewritten
    into a fabricated {"currency": "GBP"} object here: inferring the
    denomination is a compatibility-layer decision, and this layer's job is to
    report what upstream actually said. See compat.to_epcdata().
    """

    value: Decimal
    currency: Optional[str] = None

    @property
    def currency_stated(self) -> bool:
        """Whether upstream stated a currency.

        DERIVED, never stored. As a settable field it could be constructed to
        contradict `currency` — EPCMoney(value=1) yielded currency=None with
        currency_stated=True, i.e. "a currency was stated" and "there is no
        currency" at once. Provenance that can disagree with the data it
        describes is worse than no provenance, so the invariant is structural:
        a currency is stated exactly when there is one.
        """
        return self.currency is not None

    @classmethod
    def from_source(cls, raw: Any, field: str) -> "EPCMoney":
        # bool BEFORE the number check: isinstance(True, int) is True in Python,
        # so a bare `True` would otherwise validate as the amount 1.
        if isinstance(raw, bool):
            raise EPCUpstreamShapeError(
                f"{field}: expected a number or {{value, currency}}, got bool {raw!r}"
            )

        if isinstance(raw, (int, float)):
            # Legacy SAP scalar: an amount with no stated currency.
            return cls(value=_finite(raw, field), currency=None)

        if not isinstance(raw, dict) or "value" not in raw or "currency" not in raw:
            raise EPCUpstreamShapeError(
                f"{field}: expected a number or {{value, currency}}, "
                f"got {type(raw).__name__} {raw!r:.60}"
            )
        if isinstance(raw["value"], bool):
            raise EPCUpstreamShapeError(f"{field}: value is not numeric: {raw['value']!r}")
        value = _finite(raw["value"], field)
        currency = _str_or_none(raw["currency"])
        if not currency:
            raise EPCUpstreamShapeError(f"{field}: missing currency")
        return cls(value=value, currency=currency)


class EPCQuantity(BaseModel):
    """A measured amount with an optionally-stated unit.

    Same dual shape as EPCMoney, and for the same reason — which one appears is a
    property of the SCHEMA, not of the field. Measured 2026-09-05:

        RdSAP 17.x-21.x, SAP 16.x-19.x  ->  a bare number
        SAP-Schema-13.0                 ->  {"value", "quantity"}

    A bare number states no unit, so `unit` stays None and `unit_stated` is
    False. The unit is never fabricated: "tonnes per year" is not written in
    where upstream said nothing, because a stated unit and an assumed one are
    not the same claim. `"quantity": ""` was observed and is a stated nothing.
    """

    value: Decimal
    unit: Optional[str] = None

    @property
    def unit_stated(self) -> bool:
        """DERIVED, never stored — see EPCMoney.currency_stated for the reasoning."""
        return self.unit is not None

    @classmethod
    def from_source(cls, raw: Any, field: str) -> "EPCQuantity":
        # bool BEFORE the number check: isinstance(True, int) is True in Python.
        if isinstance(raw, bool):
            raise EPCUpstreamShapeError(
                f"{field}: expected a number or {{value, quantity}}, got bool {raw!r}"
            )
        if isinstance(raw, (int, float)):
            return cls(value=_finite(raw, field), unit=None)
        if not isinstance(raw, dict) or "value" not in raw:
            raise EPCUpstreamShapeError(
                f"{field}: expected a number or {{value, quantity}}, "
                f"got {type(raw).__name__} {raw!r:.60}"
            )
        if isinstance(raw["value"], bool):
            raise EPCUpstreamShapeError(f"{field}: value is not numeric: {raw['value']!r}")
        # Unlike currency, an absent or empty unit is NOT an error: it is the
        # bare-number case wearing an object, and the amount is still usable.
        return cls(value=_finite(raw["value"], field), unit=_str_or_none(raw.get("quantity")))


class EPCPagination(BaseModel):
    total_records: Optional[int] = None
    current_page: Optional[int] = None
    total_pages: Optional[int] = None
    page_size: Optional[int] = None
    next_page: Optional[int] = None
    prev_page: Optional[int] = None

    @property
    def usable(self) -> bool:
        return self.total_records is not None

    @classmethod
    def from_source(cls, raw: Any) -> "EPCPagination":
        if not isinstance(raw, dict):
            raise EPCUpstreamShapeError("pagination: expected an object")
        return cls(
            total_records=raw.get("totalRecords"),
            current_page=raw.get("currentPage"),
            total_pages=raw.get("totalPages"),
            page_size=raw.get("pageSize"),
            next_page=raw.get("nextPage"),
            prev_page=raw.get("prevPage"),
        )


class EPCSearchRow(BaseModel):
    """One summary row. Carries no score, floor area, costs or construction detail."""

    certificate_number: Optional[str] = None
    uprn: Optional[str] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    address_line_3: Optional[str] = None
    address_line_4: Optional[str] = None
    postcode: Optional[str] = None
    post_town: Optional[str] = None
    council: Optional[str] = None
    constituency: Optional[str] = None
    current_energy_efficiency_band: Optional[str] = None
    registration_date: Optional[str] = None
    schema_type: Optional[str] = None
    raw: Optional[dict] = Field(default=None, exclude=True)

    @property
    def address(self) -> Optional[str]:
        """Composed from the non-null lines. address_matching depends on this."""
        parts = [p for p in (self.address_line_1, self.address_line_2,
                             self.address_line_3, self.address_line_4) if p]
        return ", ".join(parts) or None

    @property
    def usable(self) -> bool:
        """A row without a certificate number cannot be chained to a fetch."""
        return bool(self.certificate_number)

    @classmethod
    def from_source(cls, raw: Any) -> "EPCSearchRow":
        if not isinstance(raw, dict):
            raise EPCUpstreamShapeError("search row: expected an object")
        if _CERT_MARKERS & raw.keys() and not (_SEARCH_MARKERS & raw.keys()):
            raise EPCUpstreamShapeError(
                "search row: payload looks like a certificate document "
                "(snake_case fields) — wrong adapter"
            )
        return cls(
            certificate_number=_str_or_none(raw.get("certificateNumber")),
            uprn=_str_or_none(raw.get("uprn")),
            address_line_1=_str_or_none(raw.get("addressLine1")),
            address_line_2=_str_or_none(raw.get("addressLine2")),
            address_line_3=_str_or_none(raw.get("addressLine3")),
            address_line_4=_str_or_none(raw.get("addressLine4")),
            postcode=_str_or_none(raw.get("postcode")),
            post_town=_str_or_none(raw.get("postTown")),
            council=_str_or_none(raw.get("council")),
            constituency=_str_or_none(raw.get("constituency")),
            current_energy_efficiency_band=_str_or_none(raw.get("currentEnergyEfficiencyBand")),
            registration_date=_str_or_none(raw.get("registrationDate")),
            schema_type=_str_or_none(raw.get("schemaType")),
            raw=raw,
        )


class EPCSearchPage(BaseModel):
    """A bounded page of summaries with explicit completeness state.

    Page-number traversal upstream is page-size-dependent and not a stable
    snapshot: in one measured 200-row comparison, 7 records (3.5%) were absent
    from the paged union and 7 positions were duplicated, all sharing the
    boundary registrationDate. So `complete` is never inferred optimistically.
    """

    results: list[EPCSearchRow] = Field(default_factory=list)
    pagination: EPCPagination
    returned_distinct_count: int = 0
    unusable_rows: int = 0
    duplicates_removed: int = 0
    complete: bool = False
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_source(cls, body: Any) -> "EPCSearchPage":
        if not isinstance(body, dict) or "data" not in body:
            raise EPCUpstreamShapeError("search response: missing 'data'")
        if "pagination" not in body:
            raise EPCUpstreamShapeError(
                "search response: missing 'pagination' — completeness cannot be determined"
            )
        rows_raw = body.get("data")
        if not isinstance(rows_raw, list):
            raise EPCUpstreamShapeError("search response: 'data' is not a list")

        pagination = EPCPagination.from_source(body["pagination"])
        warnings: list[str] = []

        parsed = [EPCSearchRow.from_source(r) for r in rows_raw]
        usable = [r for r in parsed if r.usable]
        unusable = len(parsed) - len(usable)

        seen: set[str] = set()
        deduped: list[EPCSearchRow] = []
        for row in usable:
            if row.certificate_number in seen:
                continue
            seen.add(row.certificate_number)
            deduped.append(row)
        duplicates = len(usable) - len(deduped)

        if unusable:
            warnings.append(
                f"{unusable} unusable row(s) quarantined: no certificateNumber, "
                "so they cannot be chained to a certificate fetch"
            )
        if duplicates:
            warnings.append(f"{duplicates} duplicate row(s) removed within this page")

        if not pagination.usable:
            complete = False
            warnings.append(
                "upstream pagination metadata unusable — completeness cannot be determined"
            )
        else:
            complete = (pagination.total_records == len(deduped)) and not unusable
            if not complete:
                warnings.append(
                    f"returned {len(deduped)} of {pagination.total_records} record(s); "
                    "upstream page-number traversal is not snapshot-stable, so this "
                    "response is a bounded page, not a complete set"
                )

        return cls(
            results=deduped,
            pagination=pagination,
            returned_distinct_count=len(deduped),
            unusable_rows=unusable,
            duplicates_removed=duplicates,
            complete=complete,
            warnings=warnings,
        )


class EPCCertificateDoc(BaseModel):
    """A full certificate. Field set varies by schema (72-83 observed)."""

    model_config = {"extra": "allow"}

    certificate_number: str
    schema_type: Optional[str] = None
    assessment_type: Optional[str] = None

    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    address_line_3: Optional[str] = None
    postcode: Optional[str] = None
    uprn: Optional[str] = None

    current_energy_efficiency_band: Optional[str] = None
    potential_energy_efficiency_band: Optional[str] = None
    energy_rating_current: Optional[int] = None
    energy_rating_potential: Optional[int] = None
    total_floor_area: Optional[float] = None
    habitable_room_count: Optional[int] = None
    inspection_date: Optional[str] = None
    registration_date: Optional[str] = None
    completion_date: Optional[str] = None

    co2_emissions_current: Optional[EPCQuantity] = None
    co2_emissions_potential: Optional[EPCQuantity] = None

    # Raw codes always preserved verbatim in the upstream key space (string —
    # `4` and `ND` are both keys); labels resolved separately by the codebook.
    built_form_code: Optional[str] = None
    property_type_code: Optional[str] = None
    tenure_code: Optional[str] = None

    # Schema-variant field sampled by tests.
    photovoltaic_supply: Optional[Any] = None

    heating_cost_current: Optional[EPCMoney] = None
    heating_cost_potential: Optional[EPCMoney] = None
    hot_water_cost_current: Optional[EPCMoney] = None
    hot_water_cost_potential: Optional[EPCMoney] = None
    lighting_cost_current: Optional[EPCMoney] = None
    lighting_cost_potential: Optional[EPCMoney] = None

    unmodelled_fields: dict[str, Any] = Field(default_factory=dict, exclude=True)
    raw: Optional[dict] = Field(default=None, exclude=True)

    @property
    def address(self) -> Optional[str]:
        parts = [p for p in (self.address_line_1, self.address_line_2, self.address_line_3) if p]
        return ", ".join(parts) or None

    @classmethod
    def from_source(
        cls,
        raw: Any,
        *,
        certificate_number: str,
        schema_type: Optional[str] = None,
    ) -> "EPCCertificateDoc":
        """Build from a certificate body.

        ``certificate_number`` must be supplied by the caller: the certificate
        body does not echo its own number (verified by probe).
        """
        if not isinstance(raw, dict):
            raise EPCUpstreamShapeError("certificate: expected an object")
        if _SEARCH_MARKERS & raw.keys() and not (_CERT_MARKERS & raw.keys()):
            raise EPCUpstreamShapeError(
                "certificate: payload looks like a search summary (camelCase fields) "
                "— wrong adapter"
            )

        money = {f: EPCMoney.from_source(raw[f], f) for f in _MONEY_FIELDS if raw.get(f) is not None}
        quantities = {f: EPCQuantity.from_source(raw[f], f)
                      for f in _QUANTITY_FIELDS if raw.get(f) is not None}

        known = {
            "certificate_number": certificate_number,
            "schema_type": _str_or_none(raw.get("schema_type")) or schema_type,
            "assessment_type": _str_or_none(raw.get("assessment_type")),
            "address_line_1": _str_or_none(raw.get("address_line_1")),
            "address_line_2": _str_or_none(raw.get("address_line_2")),
            "address_line_3": _str_or_none(raw.get("address_line_3")),
            "postcode": _str_or_none(raw.get("postcode")),
            "uprn": _str_or_none(raw.get("uprn")),
            "current_energy_efficiency_band": _str_or_none(raw.get("current_energy_efficiency_band")),
            "potential_energy_efficiency_band": _str_or_none(raw.get("potential_energy_efficiency_band")),
            "energy_rating_current": raw.get("energy_rating_current"),
            "energy_rating_potential": raw.get("energy_rating_potential"),
            "total_floor_area": raw.get("total_floor_area"),
            "habitable_room_count": raw.get("habitable_room_count"),
            "inspection_date": _str_or_none(raw.get("inspection_date")),
            "registration_date": _str_or_none(raw.get("registration_date")),
            "completion_date": _str_or_none(raw.get("completion_date")),
            # _str_or_none, not str(): keeps an absent code distinct from the
            # stated-unknown code `ND`, which is a real key with a real label.
            "built_form_code": _str_or_none(raw.get("built_form")),
            "property_type_code": _str_or_none(raw.get("property_type")),
            "tenure_code": _str_or_none(raw.get("tenure")),
            "photovoltaic_supply": raw.get("photovoltaic_supply"),
            **quantities,
            **money,
        }

        consumed = {
            "schema_type", "assessment_type", "address_line_1", "address_line_2",
            "address_line_3", "postcode", "uprn", "current_energy_efficiency_band",
            "potential_energy_efficiency_band", "energy_rating_current",
            "energy_rating_potential", "total_floor_area", "habitable_room_count",
            "inspection_date", "registration_date", "completion_date",
            "co2_emissions_current", "co2_emissions_potential", "built_form",
            "property_type", "tenure", "photovoltaic_supply", *_MONEY_FIELDS,
        }
        # Retained, not discarded: the OAS declares additionalProperties: true,
        # so silently dropping an unknown field would hide an upstream change.
        unmodelled = {k: v for k, v in raw.items() if k not in consumed}

        return cls(**known, unmodelled_fields=unmodelled, raw=raw)
