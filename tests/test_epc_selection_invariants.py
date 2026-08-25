"""Selector invariants — not examples.

The structured street/building/unit matcher was repaired four times and each
round found a new way for partial evidence to look sufficient. Enumerating
counter-examples was never going to terminate, so v1.14 accepts only identity
evidence: an exact UPRN match, or exact normalized full-address equality.

These tests assert the PROPERTY rather than a list of known-bad cases: mutate
any address component and selection must stop; normalize only case and
punctuation and it may still match.
"""

from __future__ import annotations

import itertools

import pytest

from property_core.epc.errors import EPCAmbiguousMatchError
from property_core.epc.selection import select_candidate
from property_core.epc.source_models import EPCSearchRow

# Components deliberately span the shapes that previously broke the matcher:
# a unit, a block number, a building number, an ordinal street, a street type.
BASE = ["Flat 2", "Block 3", "24", "1st Avenue"]


def _row(cert_no: str, address: str, uprn: str | None = None) -> EPCSearchRow:
    return EPCSearchRow.from_source({
        "certificateNumber": cert_no, "addressLine1": address, "addressLine2": None,
        "uprn": uprn, "postcode": "AA1 1AA", "currentEnergyEfficiencyBand": "D",
        "registrationDate": "2023-01-01", "schemaType": "RdSAP-Schema-20.0.0",
    })


def _addr(parts) -> str:
    return ", ".join(parts)


class TestAnyComponentChangePreventsSelection:
    """Mutating any component of the address must stop selection."""

    MUTATIONS = {
        "unit": ("Flat 2", "Flat 7"),
        "block": ("Block 3", "Block 8"),
        "building": ("24", "99"),
        "street_ordinal": ("1st Avenue", "2nd Avenue"),
        "street_type": ("1st Avenue", "1st Road"),
        "street_name": ("1st Avenue", "1st Crescent"),
    }

    @pytest.mark.parametrize("label", list(MUTATIONS))
    def test_changed_component_is_refused(self, label):
        original, replacement = self.MUTATIONS[label]
        candidate_parts = [replacement if p == original else p for p in BASE]
        assert candidate_parts != BASE, f"{label}: mutation did not change the address"

        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate([_row("1", _addr(candidate_parts))], address=_addr(BASE))

    def test_unchanged_address_is_selected(self):
        got = select_candidate([_row("1", _addr(BASE))], address=_addr(BASE))
        assert got.row.certificate_number == "1"
        assert got.method == "exact_address" and got.confidence == 100


class TestStructuralRearrangementNeverMatches:
    def test_dropping_any_component_is_refused(self):
        for i in range(len(BASE)):
            shortened = BASE[:i] + BASE[i + 1:]
            with pytest.raises(EPCAmbiguousMatchError):
                select_candidate([_row("1", _addr(BASE))], address=_addr(shortened))
            with pytest.raises(EPCAmbiguousMatchError):
                select_candidate([_row("1", _addr(shortened))], address=_addr(BASE))

    def test_reordering_components_is_refused(self):
        for perm in itertools.permutations(BASE):
            if list(perm) == BASE:
                continue
            with pytest.raises(EPCAmbiguousMatchError):
                select_candidate([_row("1", _addr(perm))], address=_addr(BASE))

    def test_extra_component_is_refused(self):
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate([_row("1", _addr(BASE + ["Nottingham"]))], address=_addr(BASE))


class TestPunctuationAndCaseOnlyStillMatches:
    @pytest.mark.parametrize("variant", [
        "FLAT 2, BLOCK 3, 24, 1ST AVENUE",
        "flat 2, block 3, 24, 1st avenue",
        "Flat 2 Block 3 24 1st Avenue",
        "Flat 2,  Block 3,  24,  1st Avenue",
        "Flat 2. Block 3. 24. 1st Avenue",
        "  Flat 2, Block 3, 24, 1st Avenue  ",
    ])
    def test_normalization_only_differences_still_match(self, variant):
        got = select_candidate([_row("1", _addr(BASE))], address=variant)
        assert got.method == "exact_address"

    def test_abbreviation_is_not_normalization(self):
        """'Ave' for 'Avenue' is an inference, not a formatting difference."""
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate([_row("1", _addr(BASE))],
                             address="Flat 2, Block 3, 24, 1st Ave")


class TestDuplicatesAndUprn:
    def test_duplicate_exact_addresses_remain_ambiguous(self):
        rows = [_row("1", _addr(BASE)), _row("2", _addr(BASE))]
        with pytest.raises(EPCAmbiguousMatchError) as exc:
            select_candidate(rows, address=_addr(BASE))
        assert len(exc.value.candidates) == 2

    def test_uprn_selects_regardless_of_address_text(self):
        rows = [_row("1", "Totally Different Address", uprn="100000000001")]
        got = select_candidate(rows, uprn="100000000001")
        assert got.method == "uprn" and got.confidence == 100

    def test_duplicate_uprn_is_ambiguous(self):
        rows = [_row("1", "A", uprn="100000000001"), _row("2", "B", uprn="100000000001")]
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate(rows, uprn="100000000001")

    def test_uprn_miss_does_not_fall_back(self):
        rows = [_row("1", _addr(BASE), uprn="100000000001")]
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate(rows, uprn="999999999999", address=_addr(BASE))


class TestNoStructuredAcceptancePathRemains:
    def test_partial_agreement_never_selects(self):
        """A near-miss sharing street, building and unit must still refuse."""
        near = "Flat 2, Block 3, 24, 1st Avenue, Nottingham"
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate([_row("1", near)], address=_addr(BASE))

    def test_confidence_is_only_ever_identity(self):
        for kwargs in ({"address": _addr(BASE)}, {"uprn": "100000000001"}):
            rows = [_row("1", _addr(BASE), uprn="100000000001")]
            assert select_candidate(rows, **kwargs).confidence == 100

    def test_selection_module_exposes_no_partial_matchers(self):
        """Pin the removal: the helpers that produced the defects are gone."""
        import property_core.epc.selection as sel

        for gone in ("_building", "_unit", "_street_words", "_numbers"):
            assert not hasattr(sel, gone), f"{gone} still present — partial matching path"
