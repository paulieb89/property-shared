"""Adapter query semantics: geography, filters, ordering, completeness.

Spec section 7.1 tests 1-4 and 20/21b, asserted against the snapshot adapter.
Geography is the load-bearing one: `B5` and `B50` are ~20 miles apart, and a
text-prefix match conflates them. The adapter filters on the *derived* outcode
and sector columns, so the class of bug that produced `STRSTARTS("B5")` cannot
be expressed here at all.
"""

from __future__ import annotations

import pytest

pytest.importorskip("duckdb", reason="needs the optional 'snapshot' extra")

from property_core.provenance import CompletenessBasis  # noqa: E402
from property_core.snapshot.adapter import SnapshotAdapter  # noqa: E402
from tests.snapshot.snapshot_fixtures import (  # noqa: E402
    build_snapshot,
    default_rows,
    row,
)


@pytest.fixture
def adapter(tmp_path):
    directory, record = build_snapshot(tmp_path, default_rows())
    with SnapshotAdapter.open(directory, record) as a:
        yield a


def ids(page) -> set[str]:
    return {t.transaction_id for t in page.transactions}


def test_outcode_search_never_matches_a_longer_outcode(adapter):
    """Spec test 1. B5 must never return B50."""
    page = adapter.search(postcode_prefix="B5", limit=50)
    assert ids(page) == {"T-B57-2024", "T-B57-2023", "T-B56-2024",
                         "T-B57-CATB", "T-B57-OTHER"}
    assert not any(t.postcode.startswith("B50") for t in page.transactions)


def test_sector_search_is_isolated(adapter):
    """Spec test 2. M3 7 returns only M3 7, never M3 8."""
    page = adapter.search(postcode_prefix="M3 7", limit=50)
    assert ids(page) == {"T-M37-2024"}


def test_exact_postcode_search(adapter):
    page = adapter.search(postcode="B5 7AA", limit=50)
    assert ids(page) == {"T-B57-2024"}


def test_property_type_and_category_filters_are_exact(adapter):
    """Spec test 4. Filters are pushed into the query, not applied afterwards."""
    page = adapter.search(postcode_prefix="B5", property_types={"F"}, limit=50)
    assert ids(page) == {"T-B57-2024", "T-B56-2024", "T-B57-CATB"}

    page = adapter.search(postcode_prefix="B5", transaction_category="A", limit=50)
    assert "T-B57-CATB" not in ids(page)

    page = adapter.search(postcode_prefix="B5", property_types={"F", "D", "S", "T"},
                          transaction_category="A", limit=50)
    assert ids(page) == {"T-B57-2024", "T-B57-2023", "T-B56-2024"}


def test_date_range_filters(adapter):
    page = adapter.search(postcode_prefix="B5", from_date="2024-01-01", limit=50)
    assert "T-B57-2023" not in ids(page)
    page = adapter.search(postcode_prefix="B5", to_date="2023-12-31", limit=50)
    assert ids(page) == {"T-B57-2023"}


def test_ordering_is_deterministic_across_same_date_ties(tmp_path):
    """Spec test 3. Ties broken canonically, so paging cannot repeat or omit."""
    rows = [row(f"T-{i:02d}", "B5 7AA", "2024-03-01", 100_000 + i) for i in range(10)]
    directory, record = build_snapshot(tmp_path, rows)
    with SnapshotAdapter.open(directory, record) as a:
        first = [t.transaction_id for t in a.search(postcode_prefix="B5", limit=10).transactions]
        second = [t.transaction_id for t in a.search(postcode_prefix="B5", limit=10).transactions]
    assert first == second
    assert first == sorted(first)


def test_rows_map_onto_the_transaction_model(adapter):
    page = adapter.search(postcode="B5 7AB", limit=5)
    t = page.transactions[0]
    assert t.transaction_id == "T-B57-2023"
    assert t.price == 210_000
    assert t.date == "2023-06-15"
    assert t.postcode == "B5 7AB"
    assert t.property_type == "T"
    assert t.estate_type == "L"
    assert t.transaction_category == "A"
    assert t.new_build is False
    assert t.street == "HIGH STREET"
    assert t.town == "BIRMINGHAM"


def test_result_below_limit_is_proven_complete(adapter):
    """Spec test 21b. limit+1 came back short, so nothing was truncated."""
    page = adapter.search(postcode_prefix="M3 7", limit=10)
    assert page.exhausted is True
    assert page.completeness_basis is CompletenessBasis.LIMIT_PLUS_ONE


def test_result_at_the_limit_is_not_complete(adapter):
    """Spec test 20. A full page proves nothing about what was left behind."""
    page = adapter.search(postcode_prefix="B5", limit=2)
    assert len(page.transactions) == 2
    assert page.exhausted is False
    assert page.completeness_basis is None


def test_limit_plus_one_row_is_never_returned(adapter):
    """The probe row is evidence, not data. Returning it would break the limit."""
    page = adapter.search(postcode_prefix="B5", limit=3)
    assert len(page.transactions) == 3


def test_geography_is_never_widened_by_the_adapter(adapter):
    """A thin result stays thin. Escalation is a caller decision, never a query one."""
    page = adapter.search(postcode_prefix="B5 6", limit=50)
    assert ids(page) == {"T-B56-2024"}


def test_malformed_prefix_is_rejected_before_any_query(adapter):
    from property_core.exceptions import InvalidPostcodeError

    with pytest.raises(InvalidPostcodeError):
        adapter.search(postcode_prefix="'; DROP TABLE ppd; --", limit=5)


def test_geography_arguments_reach_the_query_as_parameters(adapter, monkeypatch):
    """String interpolation of caller input into SQL is not available here."""
    captured: list[tuple[str, tuple]] = []
    original = SnapshotAdapter._execute

    def _record(self, sql, params=()):
        captured.append((sql, tuple(params)))
        return original(self, sql, params)

    monkeypatch.setattr(SnapshotAdapter, "_execute", _record)
    adapter.search(postcode_prefix="B5 7", limit=5)
    sql, params = captured[-1]
    assert "B5 7" not in sql
    assert "B5 7" in params
