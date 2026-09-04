"""v1 compatibility projection, honest degradation, and safe candidate selection.

Compatibility means: every existing v1 field remains present with its type and
meaning; existing tool parameters remain accepted; additions are permitted.
It does NOT mean fabricating values the upstream no longer supplies.

EPCData.rating is `str` and EPCData.score is `int` — both non-Optional. That is
precisely why the retired-API code wrote rating="" and score=0. Those defaults
are forbidden here, so a summary-only row simply cannot become an EPCData.
"""

from __future__ import annotations

import pytest

from property_core.epc.compat import to_epcdata
from property_core.epc.errors import (
    EPCAmbiguousMatchError,
    EPCUnsupportedOperationError,
)
from property_core.epc.source_models import EPCCertificateDoc, EPCSearchRow
from property_core.models.epc import EPCData

from tests.test_epc_source_models import CERT_DOC, SEARCH_ROW


class _StubCodebook:
    """Resolves only the three labels v1.14.0 needs."""

    def __init__(self, available=True):
        self.available = available
        self.calls: list[tuple] = []

    def label_sync(self, code: str, key: str, schema_version: str | None):
        self.calls.append((code, key, schema_version))
        if not self.available:
            return None
        return {("built_form", "4"): "Mid-Terrace",
                ("property_type", "2"): "Flat",
                ("tenure", "3"): "rented (private)"}.get((code, key))


class TestLegacyProjection:
    def test_legacy_field_subset_preserved_with_types(self):
        doc = EPCCertificateDoc.from_source(CERT_DOC, certificate_number="1111-2222-3333-4444-5555")
        d = to_epcdata(doc, codebook=_StubCodebook())
        assert isinstance(d, EPCData)
        assert d.rating == "D" and isinstance(d.rating, str)
        assert d.score == 62 and isinstance(d.score, int)
        assert d.floor_area == 27
        assert d.lmk_key == "1111-2222-3333-4444-5555"
        assert d.certificate_hash == d.lmk_key
        assert d.address == "Flat 2, 42 Example Boulevard"

    def test_coded_fields_become_labels_never_integers(self):
        d = to_epcdata(EPCCertificateDoc.from_source(CERT_DOC, certificate_number="1"),
                       codebook=_StubCodebook())
        assert d.built_form == "Mid-Terrace"
        assert d.property_type == "Flat"
        assert d.tenure == "rented (private)"
        for v in (d.built_form, d.property_type, d.tenure):
            assert not isinstance(v, int), "an integer must never masquerade as a label"

    def test_unresolvable_label_is_none_with_warning_never_an_integer(self):
        doc = EPCCertificateDoc.from_source(CERT_DOC, certificate_number="1")
        d, warnings = to_epcdata(doc, codebook=_StubCodebook(available=False), return_warnings=True)
        assert d.built_form is None and d.property_type is None and d.tenure is None
        assert any("code" in w.lower() for w in warnings)

    def test_gbp_cost_projects_to_legacy_scalar(self):
        d = to_epcdata(EPCCertificateDoc.from_source(CERT_DOC, certificate_number="1"),
                       codebook=_StubCodebook())
        assert d.heating_cost_current == 785
        assert not isinstance(d.heating_cost_current, dict), "the object must not reach legacy arithmetic"

    def test_non_gbp_cost_is_missing_plus_warning_not_silently_dropped(self):
        doc = EPCCertificateDoc.from_source(
            {**CERT_DOC, "heating_cost_current": {"value": 900, "currency": "EUR"}},
            certificate_number="1")
        d, warnings = to_epcdata(doc, codebook=_StubCodebook(), return_warnings=True)
        assert d.heating_cost_current is None
        assert any("EUR" in w for w in warnings)


class TestNoFabrication:
    """The three defaults the retired-API code produced are now forbidden."""

    def test_missing_rating_never_becomes_empty_string(self):
        doc = EPCCertificateDoc.from_source(
            {k: v for k, v in CERT_DOC.items() if k != "current_energy_efficiency_band"},
            certificate_number="1")
        with pytest.raises(EPCUnsupportedOperationError):
            to_epcdata(doc, codebook=_StubCodebook())

    def test_missing_score_never_becomes_zero(self):
        doc = EPCCertificateDoc.from_source(
            {k: v for k, v in CERT_DOC.items() if k != "energy_rating_current"},
            certificate_number="1")
        with pytest.raises(EPCUnsupportedOperationError):
            to_epcdata(doc, codebook=_StubCodebook())

    def test_missing_floor_area_is_none_never_zero(self):
        doc = EPCCertificateDoc.from_source(
            {k: v for k, v in CERT_DOC.items() if k != "total_floor_area"},
            certificate_number="1")
        d = to_epcdata(doc, codebook=_StubCodebook())
        assert d.floor_area is None and d.floor_area != 0

    def test_fields_with_no_demonstrated_source_are_none_with_warning(self):
        """lodgement_date, construction_age, floor_level: absent from all 11 schemas."""
        doc = EPCCertificateDoc.from_source(CERT_DOC, certificate_number="1")
        d, warnings = to_epcdata(doc, codebook=_StubCodebook(), return_warnings=True)
        assert d.lodgement_date is None
        assert d.construction_age is None
        assert d.floor_level is None
        joined = " ".join(warnings).lower()
        for f in ("lodgement", "construction", "floor_level"):
            assert f in joined, f"{f} must be explained, not silently dropped"


class TestDeprecatedFullRowSearch:
    def test_search_all_by_postcode_raises_without_any_request(self):
        """Structurally impossible: summaries carry no score, and score is non-Optional."""
        from property_core.epc_client import EPCClient

        client = EPCClient(token="unused")

        class _Boom:
            def handle_request(self, *a, **k):
                raise AssertionError("no upstream request may be made")

        client._transport = _Boom()
        with pytest.raises(EPCUnsupportedOperationError) as exc:
            import asyncio
            asyncio.run(client.search_all_by_postcode("AA1 1AA"))
        msg = str(exc.value).lower()
        assert "summary" in msg and "certificate" in msg, "must tell the caller what to do instead"

    def test_error_is_not_a_generic_upstream_failure(self):
        from property_core.epc.errors import EPCUpstreamError
        assert not issubclass(EPCUnsupportedOperationError, EPCUpstreamError)


class TestSafeCandidateSelection:
    """Regression cases proven by the audit's address-matching probe.

    Previously: wrong house on the same street scored 36 and was ACCEPTED;
    flats in a block all tied at 62; a nonexistent flat matched an arbitrary
    neighbour, order-dependent.
    """

    def _rows(self, *addresses):
        out = []
        for i, a in enumerate(addresses):
            parts = a.split(", ")
            out.append(EPCSearchRow.from_source({
                **SEARCH_ROW,
                "certificateNumber": f"{i:04d}-0000-0000-0000-0000",
                "addressLine1": parts[0],
                "addressLine2": parts[1] if len(parts) > 1 else None,
                "uprn": None,
            }))
        return out

    def _select(self, rows, **kw):
        from property_core.epc.selection import select_candidate
        return select_candidate(rows, **kw)

    def test_exact_uprn_wins_when_exactly_one_matches(self):
        rows = self._rows("12 Elm Road", "14 Elm Road")
        rows[1].uprn = "100000000042"
        got = self._select(rows, uprn="100000000042")
        assert got.row.certificate_number == rows[1].certificate_number
        assert got.method == "uprn" and got.confidence == 100

    def test_ambiguous_uprn_does_not_pick_arbitrarily(self):
        rows = self._rows("12 Elm Road", "14 Elm Road")
        rows[0].uprn = rows[1].uprn = "100000000042"
        with pytest.raises(EPCAmbiguousMatchError):
            self._select(rows, uprn="100000000042")

    def test_wrong_house_same_street_is_not_selected(self):
        rows = self._rows("12 Elm Road", "14 Elm Road")
        with pytest.raises(EPCAmbiguousMatchError):
            self._select(rows, address="99 ELM ROAD")

    def test_wrong_street_same_number_is_not_selected(self):
        rows = self._rows("12 Elm Road")
        with pytest.raises(EPCAmbiguousMatchError):
            self._select(rows, address="12 OAK AVENUE")

    def test_multiple_flats_in_a_block_are_ambiguous(self):
        rows = self._rows("Flat 1, 24 Alexandra Road", "Flat 3, 24 Alexandra Road")
        with pytest.raises(EPCAmbiguousMatchError):
            self._select(rows, address="24 ALEXANDRA ROAD")

    def test_nonexistent_flat_does_not_tie_break_to_a_neighbour(self):
        rows = self._rows("Flat 1, 24 Alexandra Road", "Flat 3, 24 Alexandra Road")
        with pytest.raises(EPCAmbiguousMatchError):
            self._select(rows, address="FLAT 9 24 ALEXANDRA ROAD")

    def test_selection_is_order_independent(self):
        a = self._rows("Flat 1, 24 Alexandra Road", "Flat 3, 24 Alexandra Road")
        b = list(reversed(self._rows("Flat 1, 24 Alexandra Road", "Flat 3, 24 Alexandra Road")))
        with pytest.raises(EPCAmbiguousMatchError):
            self._select(a, address="FLAT 9 24 ALEXANDRA ROAD")
        with pytest.raises(EPCAmbiguousMatchError):
            self._select(b, address="FLAT 9 24 ALEXANDRA ROAD")

    def test_unambiguous_exact_flat_is_selected(self):
        rows = self._rows("Flat 2, 42 Example Boulevard", "Flat 7, 42 Example Boulevard")
        got = self._select(rows, address="FLAT 2, 42 EXAMPLE BOULEVARD")
        assert got.row.certificate_number == rows[0].certificate_number
        assert got.method == "exact_address" and got.confidence == 100
