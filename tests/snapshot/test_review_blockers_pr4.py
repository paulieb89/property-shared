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
