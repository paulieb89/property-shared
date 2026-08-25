"""The one bounded normalization: a LEADING "Flat n" / "Apartment n" designator.

Measured, not assumed. Across 210 PPD cases against 1,063 live EPC rows, every
one of the 58 matches that exact-address equality gave up differed by exactly
this token, with all numeric components identical and no designator-swapped
rival certificate in any of the 12 postcodes.

The rule is safe in a way the removed structured matcher was not: canonicalizing
can only ever make two addresses COLLIDE, and a collision is refused as
ambiguous. It cannot select a winner from partial evidence. These tests pin that
boundary — the designator is the only thing rewritten, and only when leading and
followed by a unit.
"""

from __future__ import annotations

import pytest

from property_core.epc.errors import EPCAmbiguousMatchError
from property_core.epc.selection import _canon, select_candidate
from property_core.epc.source_models import EPCSearchRow


def _row(cert_no: str, address: str, uprn: str | None = None) -> EPCSearchRow:
    return EPCSearchRow.from_source({
        "certificateNumber": cert_no, "addressLine1": address, "addressLine2": None,
        "uprn": uprn, "postcode": "AA1 1AA", "currentEnergyEfficiencyBand": "D",
        "registrationDate": "2023-01-01", "schemaType": "RdSAP-Schema-20.0.0",
    })


class TestDesignatorIsCanonicalized:
    def test_flat_matches_apartment_same_unit(self):
        got = select_candidate([_row("1", "Apartment 2, 24 Alexandra Road")],
                               address="Flat 2, 24 Alexandra Road")
        assert got.row.certificate_number == "1"
        assert got.method == "address_designator_normalized"
        assert got.confidence == 100

    def test_apartment_matches_flat_same_unit(self):
        """The register and PPD disagree in BOTH directions (29 each way)."""
        got = select_candidate([_row("1", "Flat 2, 24 Alexandra Road")],
                               address="Apartment 2, 24 Alexandra Road")
        assert got.method == "address_designator_normalized"

    def test_ppd_spacing_and_case_still_reach_the_rule(self):
        """PPD composes "FLAT 34 5 FLEET STREET" — space-joined and uppercase."""
        got = select_candidate([_row("1", "Apartment 34, 5, Fleet Street")],
                               address="FLAT 34 5 FLEET STREET")
        assert got.method == "address_designator_normalized"

    def test_literal_equality_still_reports_exact_address(self):
        got = select_candidate([_row("1", "Flat 2, 24 Alexandra Road")],
                               address="Flat 2, 24 Alexandra Road")
        assert got.method == "exact_address", "the designator rule must not shadow equality"


class TestUnitIdentifiersStayExact:
    def test_different_unit_is_refused(self):
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate([_row("1", "Apartment 3, 24 Alexandra Road")],
                             address="Flat 2, 24 Alexandra Road")

    def test_unit_suffix_is_part_of_the_unit(self):
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate([_row("1", "Apartment 2a, 24 Alexandra Road")],
                             address="Flat 2, 24 Alexandra Road")


class TestEverythingElseStillMustMatch:
    def test_different_building_is_refused_despite_shared_unit(self):
        """The round-4 defect must not return through the designator rule."""
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate([_row("1", "Apartment 2, 99 Alexandra Road")],
                             address="Flat 2, 24 Alexandra Road")

    def test_different_street_is_refused(self):
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate([_row("1", "Apartment 2, 24 Alexandra Close")],
                             address="Flat 2, 24 Alexandra Road")

    def test_extra_component_is_refused(self):
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate([_row("1", "Apartment 2, 24 Alexandra Road, Nottingham")],
                             address="Flat 2, 24 Alexandra Road")

    def test_reordered_components_are_refused(self):
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate([_row("1", "Apartment 2, Alexandra Road 24")],
                             address="Flat 2, 24 Alexandra Road")

    def test_abbreviation_is_still_not_normalized(self):
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate([_row("1", "Apartment 2, 24 Alexandra Rd")],
                             address="Flat 2, 24 Alexandra Road")


class TestCollisionsRefuse:
    def test_two_rows_collapsing_to_one_canonical_address_are_ambiguous(self):
        """Fail-safe: canonicalization can only ever create a duplicate."""
        rows = [_row("1", "Flat 2, 24 Alexandra Road"),
                _row("2", "Apartment 2, 24 Alexandra Road")]
        with pytest.raises(EPCAmbiguousMatchError) as exc:
            select_candidate(rows, address="Flat 2, 24 Alexandra Road")
        # The query matches row 1 literally, so ambiguity must be detected on
        # the canonical pass rather than row 1 silently winning the exact pass.
        assert len(exc.value.candidates) == 2

    def test_collision_is_refused_when_neither_row_matches_literally(self):
        rows = [_row("1", "Flat 2, 24 Alexandra Road"),
                _row("2", "Apartment 2, 24 Alexandra Road")]
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate(rows, address="APARTMENT 2 24 ALEXANDRA ROAD")


class TestNonDesignatorUseIsNotRewritten:
    @pytest.mark.parametrize("text", [
        "Apartment Road",                 # designator word, but no unit follows
        "Flat Street",
        "24 Apartment Road",              # designator word, but not leading
        "The Apartment, 24 High Street",  # not followed by a unit identifier
    ])
    def test_canon_leaves_non_designator_text_alone(self, text):
        from property_core.epc.selection import _norm
        assert _canon(text) == _norm(text), f"{text!r} was rewritten"

    def test_apartment_road_does_not_match_flat_road(self):
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate([_row("1", "12 Flat Road")], address="12 Apartment Road")

    def test_non_leading_designator_does_not_match(self):
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate([_row("1", "24 Apartment 2 Road")],
                             address="24 Flat 2 Road")

    def test_apt_is_not_a_synonym_until_observed(self):
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate([_row("1", "Apt 2, 24 Alexandra Road")],
                             address="Flat 2, 24 Alexandra Road")


class TestRemovedHelpersStayRemoved:
    def test_structured_matchers_are_still_absent(self):
        import property_core.epc.selection as sel

        for gone in ("_building", "_unit", "_street_words", "_numbers"):
            assert not hasattr(sel, gone), f"{gone} reappeared — partial matching path"
