"""The inferred-GBP warning leads, for scalar SAP certificates only.

Every other warning on an EPC certificate explains why something is ABSENT
(no demonstrated source, no code table, unresolved code). The currency one is
different in kind: it qualifies a number that IS present and that the reader is
looking at. Rendered fifth of five in the HTML report it read as boilerplate,
so a cost could be taken as measured when only its amount was.

Modern object-shaped certificates state their currency and must be unchanged —
no such warning at all, and their existing warning order untouched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from property_core.epc.compat import to_epcdata
from property_core.epc.source_models import EPCCertificateDoc

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


def _warnings(name: str) -> list[str]:
    raw = json.loads((FIXTURES / f"{name}.json").read_text())["data"]
    doc = EPCCertificateDoc.from_source(
        raw, certificate_number=raw["certificate_number"], schema_type=raw.get("schema_type"))
    return to_epcdata(doc).warnings or []


def _warnings_with_explicit_gbp(name: str) -> list[str]:
    """The same fixture with only its cost fields rewritten to {value, currency}.

    Everything else — schema_type, codes, dates, absent fields — is untouched, so
    the control's warnings are exactly what this certificate would produce if
    upstream had stated the currency.
    """
    raw = json.loads((FIXTURES / f"{name}.json").read_text())["data"]
    raw = dict(raw)
    for field in COST_FIELDS:
        if raw.get(field) is not None:
            raw[field] = {"value": raw[field], "currency": "GBP"}
    doc = EPCCertificateDoc.from_source(
        raw, certificate_number=raw["certificate_number"], schema_type=raw.get("schema_type"))
    return to_epcdata(doc).warnings or []


def _is_currency(w: str) -> bool:
    return "currenc" in w.lower()


class TestScalarSchemasLeadWithTheInference:
    @pytest.mark.parametrize("name", SCALAR_SCHEMAS)
    def test_currency_warning_is_first(self, name):
        warnings = _warnings(name)
        assert warnings, f"{name} produced no warnings at all"
        assert _is_currency(warnings[0]), (
            f"{name}: the inferred-GBP warning is at index "
            f"{[i for i, w in enumerate(warnings) if _is_currency(w)]}, not 0. "
            f"First warning was: {warnings[0][:80]!r}"
        )

    @pytest.mark.parametrize("name", SCALAR_SCHEMAS)
    def test_still_exactly_one(self, name):
        """Reordering must not duplicate it."""
        assert len([w for w in _warnings(name) if _is_currency(w)]) == 1

    @pytest.mark.parametrize("name", SCALAR_SCHEMAS)
    def test_remaining_warnings_match_an_explicit_gbp_control_exactly(self, name):
        """The rest of the list must be byte-identical to the same certificate
        with explicit GBP costs.

        The previous version of this test compared the scalar result against a
        list rebuilt from itself, which is true by construction whatever the code
        does. The control is built by rewriting only the six cost fields of the
        SAME fixture into {value, currency} objects — so the two runs differ in
        exactly one input dimension, and any warning the reordering added,
        dropped, altered or moved shows up as a mismatch.
        """
        scalar = _warnings(name)
        control = _warnings_with_explicit_gbp(name)

        assert _is_currency(scalar[0]), "precondition: inference warning is not first"
        assert not any(_is_currency(w) for w in control), \
            "control still infers a currency — it is not a valid control"
        assert scalar[1:] == control, (
            "after the leading inference warning the lists diverge\n"
            f"  scalar[1:] = {scalar[1:]}\n"
            f"  control    = {control}"
        )


class TestObjectSchemasUnchanged:
    @pytest.mark.parametrize("name", OBJECT_SCHEMAS)
    def test_no_currency_warning_at_all(self, name):
        assert [w for w in _warnings(name) if _is_currency(w)] == []

    @pytest.mark.parametrize("name", OBJECT_SCHEMAS)
    def test_first_warning_is_not_a_currency_one(self, name):
        warnings = _warnings(name)
        if warnings:
            assert not _is_currency(warnings[0])
