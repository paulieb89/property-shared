"""Subject-property history answers from the snapshot, with live semantics intact.

`_subject_property_lookup` called the live client directly, bypassing routing.
The reason was real: an eleven-year snapshot would truncate a property's history,
and a truncated history is indistinguishable from a complete one. Full coverage
removes that reason, and leaving it live left the feature broken whenever the
live source was — which is how `5 Alexandra Road` came back empty while the
record sat in the artifact.

The risk in moving it is not the routing, it is the **matching**. Live filters
`paon`/`street` with `CONTAINS(LCASE(...))`, i.e. substring. Exact equality would
look like a tightening and silently change behaviour: the uniqueness guard exists
*because* CONTAINS is over-broad, so making the filter strict would stop that
guard ever firing, and "havenwood" would resolve to a single property instead of
being refused.

Measured at the boundary before implementing (DuckDB 1.5.5):

    contains(lower(paon), lower('27'))  -> ['127', '27', '27A']   like live
    contains(...) with '%'              -> []          literal
    LIKE      with '%'                  -> everything   wildcard

So `contains()` is the equivalent and `LIKE` would be actively wrong.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.snapshot.snapshot_fixtures import build_snapshot, row

pytest.importorskip("duckdb", reason="needs the optional 'snapshot' extra")

POSTCODE = "B5 7AA"


def _street_rows() -> list[dict[str, Any]]:
    """One street, several buildings, and the substring traps that matter.

    `127` is the unambiguous one: no other house number on the street contains
    it, so it resolves. `27` is deliberately ambiguous -- it is a substring of
    both `127` and `27A` -- because that is what the uniqueness guard is for,
    and the live source behaves identically.
    """
    return [
        row("T-127-2024", POSTCODE, "2024-03-01", 300_000, paon="127", street="HAVENWOOD RISE"),
        row("T-127-2019", POSTCODE, "2019-05-02", 200_000, paon="127", street="HAVENWOOD RISE"),
        row("T-27", POSTCODE, "2023-01-10", 400_000, paon="27", street="HAVENWOOD RISE"),
        row("T-27A", POSTCODE, "2022-07-04", 250_000, paon="27A", street="HAVENWOOD RISE"),
        row("T-5", POSTCODE, "2021-02-02", 150_000, paon="5", street="HAVENWOOD RISE"),
        row("T-OTHER", POSTCODE, "2020-02-02", 175_000, paon="5", street="OTHER LANE"),
    ]


@pytest.fixture
def adapter(tmp_path):
    from property_core.snapshot.adapter import SnapshotAdapter

    directory, record = build_snapshot(tmp_path / "store", _street_rows())
    a = SnapshotAdapter.open(directory, record)
    yield a
    a.close()


# --- the adapter filter must be the live filter -----------------------------


def test_paon_matches_as_a_substring_exactly_as_the_live_source_does(adapter):
    """'27' matching '127' is not a bug to fix here.

    It is the behaviour the uniqueness guard downstream is written against. A
    stricter filter would make that guard unreachable and change what vague
    input returns.
    """
    ids = {t.transaction_id for t in adapter.search(postcode=POSTCODE, paon="27", limit=50).transactions}
    assert ids == {"T-27", "T-27A", "T-127-2024", "T-127-2019"}


def test_street_matches_as_a_substring_too(adapter):
    ids = {t.transaction_id for t in
           adapter.search(postcode=POSTCODE, street="HAVENWOOD", limit=50).transactions}
    assert "T-OTHER" not in ids and "T-5" in ids


def test_paon_and_street_are_combined_not_alternatives(adapter):
    page = adapter.search(postcode=POSTCODE, paon="5", street="OTHER", limit=50)
    assert {t.transaction_id for t in page.transactions} == {"T-OTHER"}


def test_matching_is_case_insensitive_like_lcase(adapter):
    lower = adapter.search(postcode=POSTCODE, street="havenwood rise", limit=50)
    upper = adapter.search(postcode=POSTCODE, street="HAVENWOOD RISE", limit=50)
    assert {t.transaction_id for t in lower.transactions} == {
        t.transaction_id for t in upper.transactions}
    assert lower.transactions, "case-insensitive matching returned nothing at all"


@pytest.mark.parametrize("metachar", ["%", "_", "%%"])
def test_like_metacharacters_are_literal_not_wildcards(adapter, metachar):
    """A string-built LIKE would make `%` match every row on the street."""
    page = adapter.search(postcode=POSTCODE, paon=metachar, limit=50)
    assert page.transactions == [], (
        f"{metachar!r} behaved as a wildcard; the filter must be parameterised "
        f"contains(), never a LIKE built from caller text"
    )


def test_the_filter_is_pushed_into_sql_so_limit_plus_one_stays_honest(adapter):
    """Filtering after the fact would make a short page mean nothing.

    Four rows match `27`; asking for three must report NOT exhausted, which is
    only true if the database applied the filter before the limit.
    """
    assert adapter.search(postcode=POSTCODE, paon="27", limit=3).exhausted is False
    assert adapter.search(postcode=POSTCODE, paon="27", limit=50).exhausted is True


def test_an_unmatched_paon_returns_nothing_rather_than_everything(adapter):
    assert adapter.search(postcode=POSTCODE, paon="99999", limit=50).transactions == []


# --- the service routes, and keeps every guard it had -----------------------


@pytest.fixture
def routed(tmp_path, monkeypatch):
    """Snapshot installed and routable, holding the street corpus."""
    from property_core.snapshot import state
    from property_core.snapshot.adapter import SnapshotAdapter

    monkeypatch.setenv("PPD_SNAPSHOT_ENABLED", "1")
    directory, record = build_snapshot(tmp_path / "routed", _street_rows())
    a = SnapshotAdapter.open(directory, record)
    state.clear()
    state.install(a)
    yield a
    state.clear()


def _subject(**kw):
    from property_core.ppd_service import PPDService

    return PPDService()._subject_property_lookup(POSTCODE, kw.pop("address"), **kw)


def test_the_subject_property_is_answered_from_the_snapshot(routed, fake_live):
    subject = _subject(address="127 Havenwood Rise")
    assert subject is not None, "the record is in the snapshot and must be found"
    assert subject.provenance.source.value == "snapshot"
    assert fake_live.calls == 0, "the live source must not be consulted at all"


def test_the_snapshot_answer_declares_its_coverage(routed, fake_live):
    prov = _subject(address="127 Havenwood Rise").provenance
    assert prov.coverage_from and prov.coverage_to
    assert prov.source_release


def test_the_whole_history_of_the_property_is_returned_not_only_the_latest(routed, fake_live):
    subject = _subject(address="127 Havenwood Rise")
    assert {t.transaction_id for t in subject.transaction_history} == {
        "T-127-2024", "T-127-2019"}
    assert subject.last_sale.transaction_id == "T-127-2024", "most recent first"


def test_vague_input_spanning_buildings_still_returns_none(routed, fake_live):
    """The uniqueness guard must survive the move.

    `27` is a substring of 27, 27A and 127 -- three distinct buildings. Refusing
    is the documented behaviour, the live source does the same, and it only
    works because the filter stayed a substring match. Exact equality would
    resolve this to one property and quietly answer a question nobody asked.
    """
    assert _subject(address="27 Havenwood Rise") is None


def test_an_address_with_no_house_number_still_returns_none(routed, fake_live):
    assert _subject(address="Havenwood Rise") is None


def test_a_house_number_that_does_not_exist_returns_none(routed, fake_live):
    assert _subject(address="99999 Havenwood Rise") is None
