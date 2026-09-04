"""CO2 emissions carry the same dual shape the cost fields already model.

`co2_emissions_current` / `_potential` were typed `Optional[float]`. Observed at
the live boundary on 2026-09-05, SAP-Schema-13.0 certificates return an object
instead:

    RdSAP 17.x-21.x, SAP 16.x-19.x   3.4
    SAP-Schema-13.0                  {"value": 1.8, "quantity": "tonnes per year"}

Six of 133 sampled certificates (4.5%) took the object form, and every one of
them failed validation outright — the whole certificate was unfetchable, the
same user-visible failure as the non-numeric code keys in
test_epc_non_numeric_codes.py, found by the same audit.

This is the shape EPCMoney already documents for the six cost fields ("which one
appears is a property of the SCHEMA, not of the field"). CO2 is modelled the
same way, and for the same reason: the unit is reported when upstream states it
and is never fabricated when it does not. One sampled certificate returned
`"quantity": ""` — a stated-nothing, which is not a unit.

The legacy `EPCData.co2_emissions_current` stays `float | None`; the projection
takes the scalar. A caller wanting the unit reads the source model.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from property_core.epc.compat import to_epcdata
from property_core.epc.errors import EPCUpstreamShapeError
from property_core.epc.source_models import EPCCertificateDoc, EPCQuantity

from tests.test_epc_source_models import CERT_DOC

TONNES = "tonnes per year"


def _doc(**overrides) -> EPCCertificateDoc:
    return EPCCertificateDoc.from_source(
        {**CERT_DOC, **overrides}, certificate_number="1111-2222-3333-4444-5555")


class TestBothShapesParse:
    def test_the_object_shape_does_not_fail_validation(self):
        doc = _doc(co2_emissions_current={"value": 1.8, "quantity": TONNES})
        assert doc.co2_emissions_current.value == Decimal("1.8")
        assert doc.co2_emissions_current.unit == TONNES

    def test_the_bare_number_shape_still_parses(self):
        doc = _doc(co2_emissions_current=3.4)
        assert doc.co2_emissions_current.value == Decimal("3.4")
        assert doc.co2_emissions_current.unit is None

    def test_an_integer_is_a_valid_bare_number(self):
        assert _doc(co2_emissions_current=3).co2_emissions_current.value == Decimal("3")

    def test_an_absent_field_stays_none(self):
        raw = {k: v for k, v in CERT_DOC.items() if not k.startswith("co2_")}
        doc = EPCCertificateDoc.from_source(raw, certificate_number="1")
        assert doc.co2_emissions_current is None and doc.co2_emissions_potential is None

    def test_both_co2_fields_are_modelled(self):
        doc = _doc(co2_emissions_current={"value": 1.8, "quantity": TONNES},
                   co2_emissions_potential={"value": 1.6, "quantity": TONNES})
        assert doc.co2_emissions_potential.value == Decimal("1.6")


class TestTheUnitIsNeverFabricated:
    def test_a_bare_number_states_no_unit(self):
        assert _doc(co2_emissions_current=3.4).co2_emissions_current.unit_stated is False

    def test_an_empty_quantity_string_is_not_a_unit(self):
        """One sampled certificate returned `"quantity": ""`."""
        q = _doc(co2_emissions_current={"value": 4.5, "quantity": ""}).co2_emissions_current
        assert q.unit is None and q.unit_stated is False
        assert q.value == Decimal("4.5")

    def test_unit_stated_cannot_contradict_the_unit(self):
        assert EPCQuantity(value=Decimal("1")).unit_stated is False
        assert EPCQuantity(value=Decimal("1"), unit=TONNES).unit_stated is True


class TestMalformedShapesStayTyped:
    """A bad payload must raise the EPC taxonomy, never a bare ValidationError."""

    @pytest.mark.parametrize("bad", [
        {"value": "abc", "quantity": TONNES},
        {"quantity": TONNES},
        {"value": float("nan"), "quantity": TONNES},
        {"value": True, "quantity": TONNES},
        True,
        "3.4 tonnes",
        [1.8],
    ])
    def test_malformed_co2_raises_the_epc_shape_error(self, bad):
        with pytest.raises(EPCUpstreamShapeError):
            _doc(co2_emissions_current=bad)


class TestLegacyProjection:
    def test_the_legacy_field_stays_a_bare_float(self):
        d = to_epcdata(_doc(co2_emissions_current={"value": 1.8, "quantity": TONNES}),
                       codebook=None)
        assert d.co2_emissions_current == pytest.approx(1.8)
        assert isinstance(d.co2_emissions_current, float)

    def test_the_bare_number_projection_is_unchanged(self):
        d = to_epcdata(_doc(co2_emissions_current=3.4), codebook=None)
        assert d.co2_emissions_current == pytest.approx(3.4)

    def test_an_absent_co2_projects_to_none(self):
        raw = {k: v for k, v in CERT_DOC.items() if not k.startswith("co2_")}
        d = to_epcdata(EPCCertificateDoc.from_source(raw, certificate_number="1"), codebook=None)
        assert d.co2_emissions_current is None
