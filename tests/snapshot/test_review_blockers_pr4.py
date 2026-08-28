"""Five defects found reviewing PR 4, each reproduced before it was fixed.

They share one shape: **the snapshot answered, and said the answer was
complete, when it was not.** That is the single worst thing this design can do,
because a caller cannot tell a confidently wrong answer from a right one.

1. `union_by_name=true` validated the combined view, so a partition missing a
   required column passed the schema gate and silently contributed no matching
   rows -- while the response claimed exhaustion.
2. `offset` was accepted, echoed back, and ignored, so paging returned the same
   row forever.
3. Coverage was checked only at its lower bound, so a window entirely *after*
   `coverage_to` returned an empty, "complete" snapshot answer.
4. Coverage metadata was optional at the routing gate, so a record with no
   bounds answered a 1995 request from an 11-year snapshot with null bounds and
   no warning.
5. The attribution statement substituted the current year. HM Land Registry
   prescribes a fixed 2021 statement.
"""

from __future__ import annotations

import pytest

pytest.importorskip("duckdb", reason="needs the optional 'snapshot' extra")

from property_core.exceptions import PPDCoverageError, SnapshotFailure  # noqa: E402
from property_core.ppd_service import PPDService  # noqa: E402
from property_core.snapshot.adapter import SnapshotAdapter  # noqa: E402
from property_core.snapshot.models import VerificationRecord  # noqa: E402
from property_core.snapshot.store import VERIFIED_RECORD, SnapshotStore  # noqa: E402
from tests.snapshot.snapshot_fixtures import (  # noqa: E402
    build_snapshot,
    default_rows,
    row,
    write_parquet_snapshot,
)


def _record(directory, **over) -> VerificationRecord:
    payload = dict(
        version="v20260101T000000Z", bundle_sha256="0" * 64, bundle_bytes=1024,
        bundle_object="b.tar",
        parquet_files=len(list(directory.rglob("*.parquet"))),
        rows=0, verified_at="2026-01-01T00:00:00Z",
        coverage_from="2016-01-01", coverage_to="2026-06-30",
        provisional_from="2026-04-01", layout="year", duckdb_version="1.5.5",
        inventory=SnapshotStore.inventory(directory),
    )
    payload.update(over)
    return VerificationRecord(**payload)


def _materialize(tmp_path, partitions, **over):
    """Write partitions into one snapshot directory and return (dir, record)."""
    store = SnapshotStore(tmp_path)
    directory = store.snapshots_dir / "v20260101T000000Z"
    total = 0
    for rows, drop in partitions:
        write_parquet_snapshot(directory, rows, drop_columns=drop)
        total += len(rows)
    record = _record(directory, rows=total, **over)
    (directory / VERIFIED_RECORD).write_text(record.model_dump_json())
    store.set_current(record.version)
    return directory, record


# ---------------------------------------------------------------------------
# 1. Per-partition schema validation
# ---------------------------------------------------------------------------


def test_a_partition_missing_a_required_column_is_rejected(tmp_path):
    """`union_by_name` fills the gap with NULLs, so the union view looks fine.

    The 2023 partition has no `outcode`. Under the union it reads as NULL, so
    an outcode search matches nothing from that year -- and the adapter, having
    seen fewer than `limit + 1` rows, reports the result COMPLETE. A whole year
    of sales vanishes and the response says nothing is missing.
    """
    directory, record = _materialize(tmp_path, [
        ([row("T-2024", "B5 7AA", "2024-03-01")], ()),
        ([row("T-2023", "B5 7AB", "2023-03-01")], ("outcode",)),
    ])
    with pytest.raises(SnapshotFailure) as exc:
        SnapshotAdapter.open(directory, record)
    assert "outcode" in str(exc.value)
    # The message must name the offending file, or an operator cannot act on it.
    assert "2023" in str(exc.value)


def test_a_partition_with_a_wrong_column_type_is_rejected(tmp_path):
    directory, record = _materialize(tmp_path, [
        ([row("T-2024", "B5 7AA", "2024-03-01")], ()),
    ])
    write_parquet_snapshot(directory / "extra", [row("T-2023", "B5 7AB", "2023-03-01")],
                           types={"price": "VARCHAR"})
    record = _record(directory, rows=2)
    with pytest.raises(SnapshotFailure) as exc:
        SnapshotAdapter.open(directory, record)
    assert "price" in str(exc.value)


def test_every_partition_is_described_individually(tmp_path, monkeypatch):
    """Proof the check is per file, not one DESCRIBE over the union."""
    directory, record = _materialize(tmp_path, [
        ([row("T-2024", "B5 7AA", "2024-03-01")], ()),
        ([row("T-2023", "B5 7AB", "2023-03-01")], ()),
    ])
    seen: list[str] = []
    original = SnapshotAdapter._execute

    def _record_sql(self, sql, params=()):
        seen.append(sql)
        return original(self, sql, params)

    monkeypatch.setattr(SnapshotAdapter, "_execute", _record_sql)
    SnapshotAdapter.open(directory, record).close()

    described = [s for s in seen if s.upper().startswith("DESCRIBE")]
    assert sum("year=2024" in s for s in described) == 1
    assert sum("year=2023" in s for s in described) == 1


# ---------------------------------------------------------------------------
# 2. Offset
# ---------------------------------------------------------------------------


def test_offset_advances_the_snapshot_page(snapshot_routing):
    """A parameter that is accepted and echoed must do something."""
    svc = PPDService()
    first = svc.search_transactions(postcode=None, postcode_prefix="B5",
                                    from_date="2016-01-01", to_date="2026-06-30",
                                    limit=1, offset=0)
    second = svc.search_transactions(postcode=None, postcode_prefix="B5",
                                     from_date="2016-01-01", to_date="2026-06-30",
                                     limit=1, offset=1)
    assert first["results"][0].transaction_id != second["results"][0].transaction_id
    assert second["offset"] == 1


def test_offset_walks_the_whole_result_set_without_repeats(snapshot_routing):
    """The adapter's order is total, so paging must be exact -- no gaps, no dupes."""
    svc = PPDService()
    paged = []
    for offset in range(6):
        page = svc.search_transactions(postcode=None, postcode_prefix="B5",
                                       from_date="2016-01-01", to_date="2026-06-30",
                                       limit=1, offset=offset)
        paged.extend(t.transaction_id for t in page["results"])
    whole = [t.transaction_id for t in
             svc.search_transactions(postcode=None, postcode_prefix="B5",
                                     from_date="2016-01-01", to_date="2026-06-30",
                                     limit=50)["results"]]
    assert paged == whole


def test_a_deep_page_never_claims_whole_sample_completeness(snapshot_routing):
    """`limit + 1` on page three proves page three ended, not that we saw page one.

    `sample_complete` is a claim about the whole matching set, so an offset page
    can never establish it however short the final page is.
    """
    svc = PPDService()
    result = svc.search_transactions(postcode=None, postcode_prefix="B5",
                                     from_date="2016-01-01", to_date="2026-06-30",
                                     limit=50, offset=1)
    assert result["count"] > 0
    assert result["provenance"].sample_complete is False
    assert result["provenance"].completeness_basis is None


# ---------------------------------------------------------------------------
# 3. The upper coverage boundary
# ---------------------------------------------------------------------------


def test_a_window_entirely_after_coverage_is_refused(snapshot_routing):
    """Nothing in this window is in the snapshot, so an empty answer is a lie."""
    svc = PPDService()
    with pytest.raises(PPDCoverageError) as exc:
        svc.search_transactions(postcode=None, postcode_prefix="B5",
                                from_date="2026-07-01", to_date="2026-08-01",
                                limit=10)
    payload = exc.value.to_dict()
    assert payload["requested"]["from_date"] == "2026-07-01"
    assert payload["available"]["coverage_to"] == "2026-06-30"
    assert "2026-06-30" in payload["remedy"]


def test_a_window_entirely_before_coverage_is_refused(snapshot_routing):
    svc = PPDService()
    with pytest.raises(PPDCoverageError):
        svc.search_transactions(postcode=None, postcode_prefix="B5",
                                from_date="2001-01-01", to_date="2002-01-01",
                                limit=10)


def test_a_guaranteed_surface_falls_back_when_coverage_cannot_reach(tmp_path,
                                                                    monkeypatch,
                                                                    fake_live):
    """comps must still answer. A snapshot too stale for the window is a failure.

    A refusal would be wrong here -- `months` is bounded and the caller was
    promised an answer -- and an empty "complete" result would be worse. The
    snapshot steps aside and live answers, exactly as for any other typed
    snapshot failure.
    """
    from property_core.snapshot import state

    monkeypatch.setenv("PPD_SNAPSHOT_ENABLED", "1")
    directory, record = build_snapshot(
        tmp_path, default_rows(), coverage_from="2001-01-01",
        coverage_to="2002-12-31", provisional_from="2002-10-01")
    state.clear()
    state.install(SnapshotAdapter.open(directory, record))
    try:
        result = PPDService().comps(postcode="B5 7AA", months=24,
                                    search_level="district")
    finally:
        state.clear()

    assert result.provenance.source.value == "sparql"
    assert any("snapshot" in w and "live" in w for w in result.warnings)


def test_a_window_extending_past_coverage_is_clamped_and_not_complete(snapshot_routing):
    """Partial overlap: serve the intersection, say what was cut, claim nothing.

    The caller asked for a period the snapshot only partly holds. Answering the
    overlap is useful; calling it complete is false.
    """
    svc = PPDService()
    result = svc.search_transactions(postcode=None, postcode_prefix="B5",
                                     from_date="2020-01-01", to_date="2026-12-31",
                                     limit=50)
    provenance = result["provenance"]
    assert result["count"] > 0
    assert provenance.sample_complete is False
    assert provenance.completeness_basis is None
    assert any("2026-06-30" in w and "coverage" in w for w in result["warnings"])


def test_an_open_ended_window_is_not_complete(snapshot_routing):
    """No `to_date` means "up to now", and now is past `coverage_to`."""
    svc = PPDService()
    result = svc.search_transactions(postcode=None, postcode_prefix="B5",
                                     from_date="2020-01-01", limit=50)
    assert result["provenance"].sample_complete is False


def test_a_fully_contained_window_is_still_complete(snapshot_routing):
    """The gate must not swallow the case completeness exists for."""
    svc = PPDService()
    result = svc.search_transactions(postcode=None, postcode_prefix="M3 7",
                                     from_date="2016-01-01", to_date="2026-06-30",
                                     limit=50)
    assert result["provenance"].sample_complete is True


# ---------------------------------------------------------------------------
# 4. Coverage metadata at the routing gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "override, why",
    [
        ({"coverage_from": None, "coverage_to": None}, "no bounds at all"),
        ({"coverage_from": None}, "half a range is not a range"),
        ({"coverage_from": "not-a-date"}, "unparseable lower bound"),
        ({"coverage_to": "2026-13-45"}, "unparseable upper bound"),
        ({"coverage_from": "2026-06-30", "coverage_to": "2016-01-01"},
         "bounds inverted"),
        ({"provisional_from": "2030-01-01"}, "provisional boundary outside coverage"),
        ({"provisional_from": "2015-01-01"}, "provisional boundary before coverage"),
        ({"provisional_from": "nonsense"}, "unparseable provisional boundary"),
    ],
)
def test_unusable_coverage_metadata_is_a_typed_failure(tmp_path, override, why):
    """Routing answers coverage questions from this metadata. It must be sound.

    Without the check, a record with no bounds answered a 1995 request from an
    11-year snapshot, reported null coverage, claimed completeness, and warned
    about nothing.
    """
    directory, _ = _materialize(tmp_path, [
        ([row("T-2024", "B5 7AA", "2024-03-01")], ()),
    ])
    record = _record(directory, rows=1, **override)
    with pytest.raises(SnapshotFailure, match="coverage|provisional"):
        SnapshotAdapter.open(directory, record)


def test_a_snapshot_with_unusable_coverage_falls_back_to_live(tmp_path, monkeypatch,
                                                              fake_live):
    """The boot leaves nothing installed, so requests go to live -- not to a lie."""
    from property_core.snapshot import bootstrap, state

    monkeypatch.setenv("PPD_SNAPSHOT_ENABLED", "1")
    directory, _ = _materialize(tmp_path, [
        ([row("T-2024", "B5 7AA", "2024-03-01")], ()),
    ])
    record = _record(directory, rows=1, coverage_from=None, coverage_to=None)
    with pytest.raises(SnapshotFailure):
        SnapshotAdapter.open(directory, record)

    bootstrap.reset_for_tests()
    assert state.active_adapter() is None
    result = PPDService().search_transactions(postcode=None, postcode_prefix="B5",
                                              limit=10)
    assert result["provenance"].source.value == "sparql"


# ---------------------------------------------------------------------------
# 5. Attribution
# ---------------------------------------------------------------------------


# The literal itself is pinned in tests/test_ppd_spec_and_attribution.py, which
# now checks the runtime constant as well as the specification. What is tested
# here is the mechanism that produced the wrong statement.


def test_the_attribution_never_consults_the_calendar():
    """The statement is fixed, so nothing may derive it from today's date.

    Checked over the parsed AST rather than by calling it: a call-based test
    passes today and starts failing on 1 January, which is precisely how the
    defect reached review.
    """
    import ast
    import inspect

    import property_core.attribution as attribution

    tree = ast.parse(inspect.getsource(attribution))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in {"today", "now", "utcnow"}:
            raise AssertionError(
                "attribution derives the statement from the current date")
        if isinstance(node, ast.Name) and node.id in {"date", "datetime"}:
            raise AssertionError("attribution still imports a date type")


def test_the_runtime_statement_matches_the_frozen_specification():
    """The spec quotes it in section 6; drift between them is a defect either way."""
    from pathlib import Path

    from property_core.attribution import hmlr_attribution

    spec = Path(__file__).resolve().parents[2] / "docs/design/ppd-source-routing.md"
    # The spec quotes it as a two-line markdown blockquote, so the "> " markers
    # come out mid-sentence unless they are stripped first.
    body = " ".join(
        line.lstrip("> ") for line in spec.read_text().splitlines()
    )
    assert " ".join(hmlr_attribution().split()) in " ".join(body.split())


# ---------------------------------------------------------------------------
# 6. Date inputs are validated before anything compares them
# ---------------------------------------------------------------------------
#
# `resolve_coverage` compares date strings lexically, which is only meaningful
# for well-formed ISO dates. Fed anything else it produced confident nonsense:
# "nonsense" sorts after "2026-06-30", so a garbage `to_date` was read as
# "beyond coverage" and silently clamped; an inverted range passed both bound
# checks, queried `date >= 2025-01-01 AND date <= 2024-01-01`, matched nothing,
# and -- being entirely "inside" coverage -- was reported COMPLETE.
#
# The live path shares the defect from the other side: a garbage date reached
# SPARQL's own validator and surfaced as an upstream failure rather than a
# caller error, and an inverted range returned an empty 200. Validation
# therefore belongs before routing, where it covers both sources.


@pytest.mark.parametrize("bad", ["nonsense", "2026-13-01", "2026-02-30", "", "20260101"])
def test_a_malformed_date_is_a_caller_error_not_a_clamp(snapshot_routing, bad):
    from property_core.exceptions import InvalidDateRangeError

    with pytest.raises(InvalidDateRangeError) as exc:
        PPDService().search_transactions(postcode=None, postcode_prefix="B5",
                                         to_date=bad, limit=10)
    payload = exc.value.to_dict()
    assert payload["error"] == "invalid_date_range"
    assert payload["field"] == "to_date"
    assert payload["value"] == bad


def test_a_malformed_from_date_names_that_field(snapshot_routing):
    from property_core.exceptions import InvalidDateRangeError

    with pytest.raises(InvalidDateRangeError) as exc:
        PPDService().search_transactions(postcode=None, postcode_prefix="B5",
                                         from_date="not-a-date", limit=10)
    assert exc.value.to_dict()["field"] == "from_date"


def test_an_inverted_range_is_refused_rather_than_answered_completely(snapshot_routing):
    """The worst of the two: an empty result asserted to be complete."""
    from property_core.exceptions import InvalidDateRangeError

    with pytest.raises(InvalidDateRangeError) as exc:
        PPDService().search_transactions(postcode=None, postcode_prefix="B5",
                                         from_date="2025-01-01", to_date="2024-01-01",
                                         limit=10)
    payload = exc.value.to_dict()
    assert payload["requested"] == {"from_date": "2025-01-01", "to_date": "2024-01-01"}


def test_an_equal_range_is_valid(snapshot_routing):
    """A single day is a legitimate window; only from > to is not."""
    result = PPDService().search_transactions(postcode=None, postcode_prefix="B5",
                                              from_date="2024-03-01",
                                              to_date="2024-03-01", limit=10)
    assert result["count"] >= 1


def test_bad_dates_are_rejected_on_the_live_path_too(live_only, fake_live):
    """Same defect, other source: SPARQL reported a caller error as an outage."""
    from property_core.exceptions import InvalidDateRangeError

    with pytest.raises(InvalidDateRangeError):
        PPDService().search_transactions(postcode=None, postcode_prefix="B5",
                                         to_date="nonsense", limit=10)
    with pytest.raises(InvalidDateRangeError):
        PPDService().search_transactions(postcode=None, postcode_prefix="B5",
                                         from_date="2025-01-01", to_date="2024-01-01",
                                         limit=10)
    assert fake_live.calls == 0, "neither source may be queried on invalid input"


def test_neither_source_is_queried_on_invalid_input(snapshot_routing, monkeypatch,
                                                    fake_live):
    from property_core.exceptions import InvalidDateRangeError

    def _must_not_run(*a, **k):
        raise AssertionError("the snapshot was queried with an invalid date range")

    monkeypatch.setattr(type(snapshot_routing.adapter), "search", _must_not_run)
    with pytest.raises(InvalidDateRangeError):
        PPDService().search_transactions(postcode=None, postcode_prefix="B5",
                                         from_date="2025-01-01", to_date="2024-01-01",
                                         limit=10)
    assert fake_live.calls == 0


@pytest.mark.parametrize("params, expected", [
    ({"to_date": "nonsense"}, 422),
    ({"from_date": "2025-01-01", "to_date": "2024-01-01"}, 422),
])
def test_rest_reports_a_bad_range_as_a_caller_error(snapshot_routing, params, expected):
    """Previously 502 (an upstream outage) and 200 (an empty complete answer)."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as client:
        response = client.get("/v1/ppd/transactions",
                              params={"postcode_prefix": "B5", **params})
    assert response.status_code == expected
    assert response.json()["detail"]["error"] == "invalid_date_range"


def test_resolve_coverage_validates_before_comparing(snapshot_routing):
    """Defence in depth: the comparison itself refuses unvalidated input.

    `resolve_coverage` is where the lexical comparisons live, so it must not
    depend on a caller having checked first.
    """
    from property_core.exceptions import InvalidDateRangeError
    from property_core.ppd_source import CoveragePolicy, resolve_coverage

    with pytest.raises(InvalidDateRangeError):
        resolve_coverage(snapshot_routing.adapter, from_date="2025-01-01",
                         to_date="2024-01-01", policy=CoveragePolicy.EXPLICIT)
    with pytest.raises(InvalidDateRangeError):
        resolve_coverage(snapshot_routing.adapter, from_date=None,
                         to_date="nonsense", policy=CoveragePolicy.EXPLICIT)


# ---------------------------------------------------------------------------
# 7. The adapter's own evidence must not contradict its documentation
# ---------------------------------------------------------------------------


def test_an_offset_page_carries_no_completeness_basis(tmp_path):
    """`SnapshotPage` is exported, and says a basis means everything was seen.

    The service withdrew the basis afterwards, so no response was wrong -- but
    the adapter still handed out a page whose own evidence contradicted its
    documented meaning, and it is a public type. Fixed at the source; the
    central withdrawal stays as defence in depth.
    """
    directory, record = build_snapshot(tmp_path, default_rows())
    with SnapshotAdapter.open(directory, record) as adapter:
        page = adapter.search(postcode_prefix="B5", offset=1, limit=50)
        assert page.completeness_basis is None
        # `exhausted` is a fact about the page that was fetched and stays true.
        assert page.exhausted is True
        assert page.offset == 1

        first = adapter.search(postcode_prefix="B5", offset=0, limit=50)
        assert first.completeness_basis is not None


def test_the_central_withdrawal_is_retained(snapshot_routing):
    """Belt and braces: provenance drops a basis at an offset regardless."""
    from property_core.provenance import CompletenessBasis
    from property_core.ppd_source import CoverageDecision, snapshot_provenance

    decision = CoverageDecision(
        from_date="2016-01-01", to_date="2026-06-30", warnings=(),
        from_narrowed=False, to_clamped=False, recent_period_provisional=False,
        fully_contained=True,
    )
    provenance = snapshot_provenance(
        snapshot_routing.adapter, decision=decision, sample_count=1, sample_limit=50,
        completeness_basis=CompletenessBasis.LIMIT_PLUS_ONE, offset=3,
    )
    assert provenance.sample_complete is False
    assert provenance.completeness_basis is None
