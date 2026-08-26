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
    def test_the_other_warnings_are_preserved_in_order(self, name):
        """Only the currency warning moves; the rest keep their sequence."""
        warnings = _warnings(name)
        others = [w for w in warnings if not _is_currency(w)]
        assert warnings == [warnings[0]] + others, "reordering disturbed the other warnings"


class TestObjectSchemasUnchanged:
    @pytest.mark.parametrize("name", OBJECT_SCHEMAS)
    def test_no_currency_warning_at_all(self, name):
        assert [w for w in _warnings(name) if _is_currency(w)] == []

    @pytest.mark.parametrize("name", OBJECT_SCHEMAS)
    def test_first_warning_is_not_a_currency_one(self, name):
        warnings = _warnings(name)
        if warnings:
            assert not _is_currency(warnings[0])
