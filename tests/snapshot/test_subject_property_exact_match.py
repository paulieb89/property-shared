"""An exact house-number match is not ambiguous, and must not be refused.

`paon`/`street` are matched by substring on both sources, so asking for
"5 Alexandra Road" also returns 15 Alexandra Road. The uniqueness guard then saw
two buildings and refused — correctly, given what it was shown, but the question
was never actually ambiguous: `5` is *exactly* one of the candidates, and it is
the one that was asked for.

Measured across six outcodes of the real artifact: **14% of addresses (1 in 7)**
were unresolvable this way — 5/15, 1/11/21, 7/17. In every case of that class the
exact match is present, because its presence is *why* the collision happened.

This does not weaken the refusal to guess. It narrows to the exact match first
and applies the same guard afterwards, so genuine ambiguity — asking for "5"
where the street holds only 15 and 25 — still refuses.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.snapshot.snapshot_fixtures import build_snapshot, row

pytest.importorskip("duckdb", reason="needs the optional 'snapshot' extra")

POSTCODE = "B5 7AA"
STREET = "ALEXANDRA ROAD"


def _rows() -> list[dict[str, Any]]:
    return [
        row("T-5-2024", POSTCODE, "2024-03-01", 225_000, paon="5", street=STREET),
        row("T-5-2008", POSTCODE, "2008-04-30", 120_000, paon="5", street=STREET),
        row("T-15", POSTCODE, "2001-11-30", 90_000, paon="15", street=STREET),
        row("T-25", POSTCODE, "2003-01-01", 95_000, paon="25", street=STREET),
        row("T-5A", POSTCODE, "2019-06-01", 180_000, paon="5A", street=STREET),
        row("T-OTHER-5", POSTCODE, "2015-01-01", 200_000, paon="5", street="BEECH LANE"),
    ]


@pytest.fixture
def routed(tmp_path, monkeypatch):
    from property_core.snapshot import state
    from property_core.snapshot.adapter import SnapshotAdapter

    monkeypatch.setenv("PPD_SNAPSHOT_ENABLED", "1")
    directory, record = build_snapshot(tmp_path / "s", _rows())
    a = SnapshotAdapter.open(directory, record)
    state.clear()
    state.install(a)
    yield a
    state.clear()


def _subject(address: str, postcode: str = POSTCODE):
    from property_core.ppd_service import PPDService

    return PPDService()._subject_property_lookup(postcode, address)


# --- the 14% case ------------------------------------------------------------


def test_an_exact_house_number_resolves_despite_a_longer_neighbour(routed, fake_live):
    """`5` collides with `15`, `25` and `5A`, and is still exactly one of them."""
    subject = _subject("5 Alexandra Road")
    assert subject is not None, "the exact match was present and was refused"
    assert {t.transaction_id for t in subject.transaction_history} == {
        "T-5-2024", "T-5-2008"}
    assert subject.last_sale.transaction_id == "T-5-2024"


def test_the_neighbours_history_is_not_attached(routed, fake_live):
    """The failure that matters: 15's sale price presented as 5's."""
    history = {t.transaction_id for t in _subject("5 Alexandra Road").transaction_history}
    assert not history & {"T-15", "T-25", "T-5A", "T-OTHER-5"}


def test_the_suffixed_number_is_a_different_property(routed, fake_live):
    subject = _subject("5A Alexandra Road")
    assert subject is not None
    assert {t.transaction_id for t in subject.transaction_history} == {"T-5A"}


def test_a_longer_number_still_resolves_to_itself(routed, fake_live):
    assert {t.transaction_id for t in _subject("15 Alexandra Road").transaction_history} == {
        "T-15"}


def test_the_street_still_discriminates(routed, fake_live):
    """Exact `paon` alone is not identity: 5 exists on two streets here."""
    subject = _subject("5 Beech Lane")
    assert subject is not None
    assert {t.transaction_id for t in subject.transaction_history} == {"T-OTHER-5"}


# --- and genuine ambiguity still refuses --------------------------------------


def test_no_exact_match_among_partial_ones_still_refuses(routed, fake_live):
    """Asking for `2` where the street holds none: 25 is not what was asked for."""
    assert _subject("2 Alexandra Road") is None


def test_a_number_that_exists_nowhere_still_returns_none(routed, fake_live):
    assert _subject("9999 Alexandra Road") is None


def test_an_address_with_no_house_number_still_returns_none(routed, fake_live):
    assert _subject("Alexandra Road") is None


def test_an_exact_number_on_a_street_that_does_not_match_returns_none(routed, fake_live):
    assert _subject("5 Nonexistent Way") is None


# --- the narrowing must not become a silent guess -----------------------------


def test_matching_is_case_and_space_insensitive_like_the_filter(routed, fake_live):
    for spelling in ("5 alexandra road", "5  ALEXANDRA  ROAD", " 5 Alexandra Road "):
        subject = _subject(spelling)
        assert subject is not None, f"{spelling!r} did not resolve"
        assert {t.transaction_id for t in subject.transaction_history} == {
            "T-5-2024", "T-5-2008"}
