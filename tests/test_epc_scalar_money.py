"""Legacy SAP schemas return cost fields as bare integers, not {value, currency}.

Found by production dogfooding of v1.14.0: every certificate on SAP-Schema-13.0,
14.0, 14.2 and 15.0 returned

    503  "heating_cost_current: expected {value, currency}, got int 267"

because EPCMoney.from_source hard-raised on any non-dict. That broke certificate
lookup, exact-address search, comps enrichment, the report service and both MCP
surfaces for those schemas. Area summaries were unaffected (no certificate fetch).

The evidence was in the probe captures all along: an audit of ALL SIX cost fields
across the 11 saved schema captures shows the shape is per-SCHEMA, not per-field —
all six move together.

    RdSAP 17.0/17.1/18.0/19.0/20.0.0, SAP 16.0/16.2  -> {value, currency}
    SAP 13.0/14.0/14.2/15.0                          -> bare int

Contract:
  * a bare number is accepted, and the source model records that upstream stated
    NO currency (currency stays None) — the raw shape is not rewritten into a
    fabricated {"currency": "GBP"} object;
  * the v1 projection keeps the amount and reads it as GBP, emitting ONE
    aggregated warning per certificate, not one per field;
  * bool, str, list and malformed objects are still rejected. bool is checked
    explicitly because in Python `isinstance(True, int)` is True.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from property_core.epc.compat import to_epcdata
from property_core.epc.errors import EPCUpstreamShapeError
from property_core.epc.source_models import EPCCertificateDoc, EPCMoney

FIXTURES = Path(__file__).parent / "fixtures" / "epc"

COST_FIELDS = [
    "heating_cost_current", "heating_cost_potential",
    "hot_water_cost_current", "hot_water_cost_potential",
    "lighting_cost_current", "lighting_cost_potential",
]

SCALAR_SCHEMAS = ["sap_schema_13_0", "sap_schema_14_0", "sap_schema_14_2", "sap_schema_15_0"]
OBJECT_SCHEMAS = [
    "rdsap_schema_17_0", "rdsap_schema_17_1", "rdsap_schema_18_0",
    "rdsap_schema_19_0", "rdsap_schema_20_0_0", "sap_schema_16_0", "sap_schema_16_2",
]


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())["data"]


def doc(name: str) -> EPCCertificateDoc:
    raw = load(name)
    return EPCCertificateDoc.from_source(
        raw, certificate_number=raw["certificate_number"],
        schema_type=raw.get("schema_type"))


class TestFixturesPinTheObservedShapes:
    """If upstream changes shape, these fail before anything else does."""

    @pytest.mark.parametrize("name", SCALAR_SCHEMAS)
    def test_scalar_schemas_carry_bare_ints_on_every_cost_field(self, name):
        raw = load(name)
        for f in COST_FIELDS:
            assert isinstance(raw[f], int) and not isinstance(raw[f], bool), \
                f"{name}.{f} is not a bare int: {raw[f]!r}"

    @pytest.mark.parametrize("name", OBJECT_SCHEMAS)
    def test_object_schemas_carry_value_currency_on_every_cost_field(self, name):
        raw = load(name)
        for f in COST_FIELDS:
            assert isinstance(raw[f], dict) and {"value", "currency"} <= raw[f].keys(), \
                f"{name}.{f} is not an object: {raw[f]!r}"


class TestScalarSchemasParse:
    """The production 503, at the layer that raised it."""

    @pytest.mark.parametrize("name", SCALAR_SCHEMAS)
    def test_certificate_parses(self, name):
        d = doc(name)
        assert d.certificate_number
        for f in COST_FIELDS:
            assert getattr(d, f) is not None, f"{f} was dropped"

    @pytest.mark.parametrize("name", SCALAR_SCHEMAS)
    def test_missing_currency_is_preserved_not_invented(self, name):
        """The source layer must not rewrite the raw shape into GBP."""
        d = doc(name)
        for f in COST_FIELDS:
            money = getattr(d, f)
            assert money.currency is None, \
                f"{f}: upstream stated no currency; source model invented {money.currency!r}"
            assert money.currency_stated is False

    @pytest.mark.parametrize("name", OBJECT_SCHEMAS)
    def test_object_schemas_keep_their_stated_currency(self, name):
        d = doc(name)
        for f in COST_FIELDS:
            money = getattr(d, f)
            assert money.currency == "GBP"
            assert money.currency_stated is True


class TestV1ProjectionKeepsTheAmount:
    @pytest.mark.parametrize("name", SCALAR_SCHEMAS)
    def test_amount_is_retained_and_read_as_gbp(self, name):
        raw, d = load(name), doc(name)
        data = to_epcdata(d)
        for f in COST_FIELDS:
            assert getattr(data, f) == raw[f], f"{f} amount lost or altered"

    @pytest.mark.parametrize("name", SCALAR_SCHEMAS)
    def test_exactly_one_aggregated_inference_warning(self, name):
        data = to_epcdata(doc(name))
        inferred = [w for w in (data.warnings or []) if "currenc" in w.lower()]
        assert len(inferred) == 1, \
            f"expected ONE aggregated warning, got {len(inferred)}: {inferred}"
        w = inferred[0].lower()
        assert "gbp" in w and ("infer" in w or "assum" in w), inferred[0]
        for f in COST_FIELDS:
            assert f not in inferred[0], "warning names individual fields — that is per-field spam"

    @pytest.mark.parametrize("name", OBJECT_SCHEMAS)
    def test_object_schemas_emit_no_currency_warning(self, name):
        data = to_epcdata(doc(name))
        assert not [w for w in (data.warnings or []) if "currenc" in w.lower()]


class TestMalformedMoneyIsStillRejected:
    @pytest.mark.parametrize("bad", [
        True, False,                       # bool is an int in Python — must NOT pass
        "625", "", "abc",                  # strings, including numeric-looking ones
        [625], [], {},                     # lists and empty objects
        {"value": 625},                    # missing currency key
        {"currency": "GBP"},               # missing value key
        {"value": "abc", "currency": "GBP"},
        {"value": 625, "currency": ""},
        {"value": None, "currency": "GBP"},
    ])
    def test_rejected(self, bad):
        with pytest.raises(EPCUpstreamShapeError):
            EPCMoney.from_source(bad, "heating_cost_current")

    def test_bool_is_not_accepted_as_a_number(self):
        """isinstance(True, int) is True — the check must be explicit."""
        with pytest.raises(EPCUpstreamShapeError) as exc:
            EPCMoney.from_source(True, "heating_cost_current")
        assert "bool" in str(exc.value).lower()

    @pytest.mark.parametrize("nonfinite", ["NaN", "Infinity", "-Infinity"])
    def test_non_finite_numbers_are_typed_failures_not_500s(self, nonfinite):
        """json.loads accepts these literals; pydantic would raise a bare
        ValidationError that escapes the EPC taxonomy as an unhandled 500."""
        import json as _json

        value = _json.loads(nonfinite)
        with pytest.raises(EPCUpstreamShapeError) as exc:
            EPCMoney.from_source(value, "heating_cost_current")
        assert "finite" in str(exc.value).lower()
        with pytest.raises(EPCUpstreamShapeError):
            EPCMoney.from_source({"value": value, "currency": "GBP"},
                                 "heating_cost_current")

    def test_currency_flag_cannot_desync_the_projection(self):
        """A directly constructed EPCMoney with no currency must still be
        treated as unstated, whatever the flag says."""
        from property_core.epc.compat import _money

        warnings, inferred = [], []
        assert _money(EPCMoney(value=Decimal("625")), "heating_cost_current",
                      warnings, inferred) == 625
        assert inferred == ["heating_cost_current"]
        assert warnings == []

    @pytest.mark.parametrize("good", [625, 0, 1771, 625.5])
    def test_bare_numbers_accepted(self, good):
        m = EPCMoney.from_source(good, "heating_cost_current")
        assert m.value == Decimal(str(good)) and m.currency is None

    def test_a_stated_non_gbp_currency_still_suppresses_the_legacy_scalar(self):
        raw = load("sap_schema_13_0")
        raw = {**raw, "heating_cost_current": {"value": 500, "currency": "EUR"}}
        d = EPCCertificateDoc.from_source(
            raw, certificate_number=raw["certificate_number"],
            schema_type=raw.get("schema_type"))
        data = to_epcdata(d)
        assert data.heating_cost_current is None
        assert any("EUR" in w for w in (data.warnings or []))
