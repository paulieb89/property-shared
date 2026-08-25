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

# Coded integers resolvable via /api/codes in v1.14.0. Six further coded fields
# (conservatory_type, language_code, measurement_type, multiple_glazing_type,
# region_code, report_type) have no table upstream at all — see
# UNRESOLVED_CODE_TABLES.
RESOLVABLE_CODES = ("built_form", "property_type", "tenure")
UNRESOLVED_CODE_TABLES = (
    "conservatory_type", "language_code", "measurement_type",
    "multiple_glazing_type", "region_code", "report_type",
)

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


class EPCMoney(BaseModel):
    """A currency amount. Decimal, because these are money."""

    value: Decimal
    currency: str

    @classmethod
    def from_source(cls, raw: Any, field: str) -> "EPCMoney":
        if not isinstance(raw, dict) or "value" not in raw or "currency" not in raw:
            raise EPCUpstreamShapeError(
                f"{field}: expected {{value, currency}}, got {type(raw).__name__} {raw!r:.60}"
            )
        try:
            value = Decimal(str(raw["value"]))
        except (InvalidOperation, TypeError) as exc:
            raise EPCUpstreamShapeError(f"{field}: value is not numeric: {raw['value']!r}") from exc
        currency = _str_or_none(raw["currency"])
        if not currency:
            raise EPCUpstreamShapeError(f"{field}: missing currency")
        return cls(value=value, currency=currency)


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

    co2_emissions_current: Optional[float] = None
    co2_emissions_potential: Optional[float] = None

    # Raw codes always preserved; labels resolved separately by the codebook.
    built_form_code: Optional[int] = None
    property_type_code: Optional[int] = None
    tenure_code: Optional[int] = None

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
            "co2_emissions_current": raw.get("co2_emissions_current"),
            "co2_emissions_potential": raw.get("co2_emissions_potential"),
            "built_form_code": raw.get("built_form"),
            "property_type_code": raw.get("property_type"),
            "tenure_code": raw.get("tenure"),
            "photovoltaic_supply": raw.get("photovoltaic_supply"),
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
