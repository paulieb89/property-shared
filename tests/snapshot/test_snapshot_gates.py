"""Red-first tests for the build's validation gates.

Every negative case corrupts a **real** built snapshot in exactly one way and
asserts that exactly one gate fires. Asserting the set of failed gates -- not
merely that validation failed -- is what stops a test passing because some other
gate happened to trip on the same fixture.

The load-bearing gates additionally get a narrow mutation check: with that one
gate neutralised the corrupt artifact passes, which proves the gate is what
rejects it.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb", reason="needs the optional 'snapshot' extra")

from tools.ppd_snapshot import validate as gates  # noqa: E402
from tools.ppd_snapshot.build import (  # noqa: E402
    BuildRequest,
    build_snapshot,
)
from tools.ppd_snapshot.validate import (  # noqa: E402
    DeclaredSnapshot,
    validate_snapshot,
)
from tests.snapshot.build_fixtures import csv_row, write_source_csv  # noqa: E402

COVERAGE_TO = date(2026, 6, 30)
TODAY = date(2026, 7, 15)

#: Rows in 2016, three in 2024 and one in 2026, so 2017-2023 and 2025 are empty
#: partitions. An empty partition is what lets a test remove one file without
#: also changing the row count.
SOURCE_ROWS = [
    csv_row("{T-2016}", "B5 7AA", "2016-01-04 00:00", 150_000),
    csv_row("{T-2024-A}", "B5 7AB", "2024-03-01 00:00", 210_000),
    csv_row("{T-2024-B}", "B50 4AA", "2024-05-20 00:00", 400_000),
    csv_row("{T-2024-C}", "M3 7AA", "2024-11-11 00:00", 260_000),
    csv_row("{T-2026}", "M3 7AB", "2026-06-30 00:00", 250_000),
    csv_row("{T-OLD}", "B5 7AC", "2015-12-31 00:00", 100_000),
]


@pytest.fixture
def snapshot(tmp_path: Path):
    csv_path = write_source_csv(tmp_path / "pp.csv", SOURCE_ROWS)
    result = build_snapshot(BuildRequest(
        csv_path=csv_path,
        out_dir=tmp_path / "snapshot",
        coverage_to=COVERAGE_TO,
        temp_dir=tmp_path / "tmp",
    ))
    declared = DeclaredSnapshot(
        directory=result.snapshot_dir,
        coverage_from=result.coverage_from,
        coverage_to=result.coverage_to,
        provisional_from=result.provisional_from,
        rows=result.rows,
        parquet_files=result.parquet_files,
    )
    return result, declared


def failed(report) -> set[str]:
    return {failure.gate for failure in report.failures}


def rewrite(path: Path, projection: str = "*", clause: str = "") -> None:
    """Rewrite one partition file from a query over itself."""
    con = duckdb.connect()
    try:
        con.execute(f"CREATE TABLE t AS SELECT * FROM read_parquet('{path}')")
        con.execute(f"COPY (SELECT {projection} FROM t {clause}) TO '{path}' "
                    f"(FORMAT parquet)")
    finally:
        con.close()


def run(declared: DeclaredSnapshot, **over):
    kwargs = {"source_coverage_end": COVERAGE_TO, "today": TODAY}
    kwargs.update(over)
    return validate_snapshot(declared, **kwargs)


# -- the artifact the build actually produces passes ------------------------

def test_a_freshly_built_snapshot_passes_every_gate(snapshot):
    _, declared = snapshot
    report = run(declared)
    assert report.failures == ()
    assert report.passed


def test_every_declared_gate_reports_a_result(snapshot):
    _, declared = snapshot
    report = run(declared)
    assert {g.name for g in report.gates} == {
        "schema", "partitions", "rows", "uniqueness", "coverage", "guarantee",
        "provisional", "ordering",
    }


# -- schema -----------------------------------------------------------------

def test_schema_gate_rejects_a_partition_missing_a_required_column(snapshot):
    result, declared = snapshot
    rewrite(result.snapshot_dir / "year=2024" / "data.parquet",
            projection="* EXCLUDE (sector)")
    report = run(declared)
    assert failed(report) == {"schema"}
    assert "sector" in report.failures[0].detail


def test_schema_gate_rejects_a_date_column_stored_as_text(snapshot):
    result, declared = snapshot
    rewrite(result.snapshot_dir / "year=2024" / "data.parquet",
            projection="* REPLACE (CAST(transfer_date AS VARCHAR) AS transfer_date)")
    report = run(declared)
    assert failed(report) == {"schema"}
    assert "transfer_date" in report.failures[0].detail


def test_schema_gate_checks_every_partition_not_only_the_first(snapshot):
    result, declared = snapshot
    rewrite(result.snapshot_dir / "year=2026" / "data.parquet",
            projection="* EXCLUDE (outcode)")
    report = run(declared)
    assert failed(report) == {"schema"}
    assert "year=2026" in report.failures[0].detail


# -- partitions -------------------------------------------------------------

def test_partitions_gate_rejects_a_missing_year(snapshot):
    result, declared = snapshot
    (result.snapshot_dir / "year=2020" / "data.parquet").unlink()
    report = run(declared)
    assert failed(report) == {"partitions"}
    assert "2020" in report.failures[0].detail


def test_partitions_gate_rejects_a_file_that_is_not_a_partition(snapshot):
    result, declared = snapshot
    (result.snapshot_dir / "year=2024" / "notes.txt").write_text("stray")
    report = run(declared)
    assert failed(report) == {"partitions"}
    assert "notes.txt" in report.failures[0].detail


def test_partitions_gate_rejects_a_declared_file_count_that_disagrees(snapshot):
    _, declared = snapshot
    report = run(declared.replace(parquet_files=10))
    assert failed(report) == {"partitions"}


# -- rows -------------------------------------------------------------------

def test_rows_gate_rejects_a_declared_count_the_data_does_not_hold(snapshot):
    _, declared = snapshot
    report = run(declared.replace(rows=declared.rows + 1))
    assert failed(report) == {"rows"}
    assert str(declared.rows + 1) in report.failures[0].detail


def test_rows_gate_is_what_rejects_a_wrong_declared_count(snapshot, monkeypatch):
    # Mutation check: neutralise this gate alone and the same artifact passes.
    _, declared = snapshot
    monkeypatch.setattr(gates, "_gate_rows", lambda *a, **k: None)
    assert run(declared.replace(rows=declared.rows + 1)).failures == ()


# -- uniqueness -------------------------------------------------------------

def test_uniqueness_gate_rejects_a_repeated_transaction_id(snapshot):
    result, declared = snapshot
    # One id overwritten with another's: the row count is untouched, so only
    # uniqueness can fire.
    rewrite(result.snapshot_dir / "year=2024" / "data.parquet",
            projection="* REPLACE ('T-2024-A' AS transaction_id)")
    report = run(declared)
    assert failed(report) == {"uniqueness"}


def test_uniqueness_gate_is_what_rejects_a_repeated_id(snapshot, monkeypatch):
    result, declared = snapshot
    rewrite(result.snapshot_dir / "year=2024" / "data.parquet",
            projection="* REPLACE ('T-2024-A' AS transaction_id)")
    monkeypatch.setattr(gates, "_gate_uniqueness", lambda *a, **k: None)
    assert run(declared).failures == ()


# -- coverage ---------------------------------------------------------------

def test_coverage_gate_rejects_a_row_after_the_declared_end(snapshot):
    result, declared = snapshot
    rewrite(result.snapshot_dir / "year=2026" / "data.parquet",
            projection="* REPLACE (DATE '2026-12-01' AS transfer_date)")
    report = run(declared)
    assert failed(report) == {"coverage"}


def test_coverage_gate_rejects_a_row_before_the_declared_start(snapshot):
    result, declared = snapshot
    rewrite(result.snapshot_dir / "year=2016" / "data.parquet",
            projection="* REPLACE (DATE '2015-06-01' AS transfer_date, "
                       "2016 AS year)")
    report = run(declared)
    assert failed(report) == {"coverage"}


def test_coverage_gate_rejects_a_row_filed_under_the_wrong_year(snapshot):
    result, declared = snapshot
    rewrite(result.snapshot_dir / "year=2024" / "data.parquet",
            projection="* REPLACE (DATE '2023-04-04' AS transfer_date)",
            clause="ORDER BY transaction_id ASC")
    report = run(declared)
    assert failed(report) == {"coverage"}
    assert "year=2024" in report.failures[0].detail


def test_coverage_gate_rejects_a_start_that_is_not_the_partition_boundary(snapshot):
    _, declared = snapshot
    report = run(declared.replace(coverage_from=date(2016, 2, 1)))
    assert failed(report) == {"coverage"}


def test_coverage_gate_rejects_an_end_the_source_release_does_not_declare(snapshot):
    _, declared = snapshot
    # The snapshot claims a window the release it was built from never covered.
    report = run(declared, source_coverage_end=date(2026, 5, 31))
    assert failed(report) == {"coverage"}


def test_coverage_gate_does_not_require_data_at_the_window_edges(snapshot):
    # The window is a declaration about the release, not a measurement of the
    # rows: no sale on 2016-01-01 or 2026-06-30 is required for it to hold.
    result, declared = snapshot
    con = duckdb.connect()
    bounds = con.execute(
        f"SELECT min(transfer_date), max(transfer_date) FROM read_parquet("
        f"'{result.snapshot_dir}/**/*.parquet')").fetchone()
    con.close()
    assert bounds[0] > declared.coverage_from or bounds[1] < declared.coverage_to
    assert run(declared).failures == ()


def test_coverage_gate_is_what_rejects_an_out_of_window_row(snapshot, monkeypatch):
    result, declared = snapshot
    rewrite(result.snapshot_dir / "year=2026" / "data.parquet",
            projection="* REPLACE (DATE '2026-12-01' AS transfer_date)")
    monkeypatch.setattr(gates, "_gate_coverage", lambda *a, **k: None)
    assert run(declared).failures == ()


# -- guarantee --------------------------------------------------------------

def test_guarantee_gate_rejects_a_window_that_does_not_reach_back_120_months(snapshot):
    _, declared = snapshot
    # The shape a shortened partition count produces: the window opens later
    # than `today - 120 months`, so the largest legal request falls outside it.
    # Nothing else in the report reads `today`, so only this gate can fire.
    report = run(declared, today=date(2025, 1, 1))
    assert failed(report) == {"guarantee"}


def test_guarantee_gate_passes_once_the_window_reaches_back_far_enough(snapshot):
    _, declared = snapshot
    assert run(declared, today=date(2025, 11, 15)).failures == ()


# -- provisional ------------------------------------------------------------

def test_provisional_gate_rejects_a_boundary_that_is_not_the_computed_month(snapshot):
    _, declared = snapshot
    report = run(declared.replace(provisional_from=date(2026, 4, 1)))
    assert failed(report) == {"provisional"}


def test_provisional_gate_rejects_a_boundary_outside_the_coverage_window(snapshot):
    _, declared = snapshot
    report = run(declared.replace(provisional_from=date(2026, 9, 1)))
    assert failed(report) == {"provisional"}


# -- ordering ---------------------------------------------------------------

def test_ordering_gate_rejects_a_partition_written_in_the_wrong_order(snapshot):
    result, declared = snapshot
    rewrite(result.snapshot_dir / "year=2024" / "data.parquet",
            clause="ORDER BY transfer_date ASC")
    report = run(declared)
    assert failed(report) == {"ordering"}
    assert "year=2024" in report.failures[0].detail


def test_ordering_gate_is_what_rejects_a_misordered_partition(snapshot, monkeypatch):
    result, declared = snapshot
    rewrite(result.snapshot_dir / "year=2024" / "data.parquet",
            clause="ORDER BY transfer_date ASC")
    monkeypatch.setattr(gates, "_gate_ordering", lambda *a, **k: None)
    assert run(declared).failures == ()


# -- deterministic content --------------------------------------------------

def test_the_content_digest_is_stable_across_a_rebuild(tmp_path: Path):
    """Rebuilding the same source must yield the same rows in the same order.

    Deliberately a *logical* check. Byte-identical Parquet across rebuilds is a
    property of the writer, and DuckDB 1.5.5 makes no such guarantee -- asserting
    it would be testing an assumption rather than the pipeline.
    """
    from tools.ppd_snapshot.validate import content_digests

    csv_path = write_source_csv(tmp_path / "pp.csv", SOURCE_ROWS)
    first = build_snapshot(BuildRequest(
        csv_path=csv_path, out_dir=tmp_path / "a", coverage_to=COVERAGE_TO,
        temp_dir=tmp_path / "tmp-a"))
    second = build_snapshot(BuildRequest(
        csv_path=csv_path, out_dir=tmp_path / "b", coverage_to=COVERAGE_TO,
        temp_dir=tmp_path / "tmp-b"))
    assert content_digests(first.snapshot_dir) == content_digests(second.snapshot_dir)


def test_the_content_digest_moves_when_a_single_value_changes(tmp_path: Path):
    from tools.ppd_snapshot.validate import content_digests

    csv_path = write_source_csv(tmp_path / "pp.csv", SOURCE_ROWS)
    built = build_snapshot(BuildRequest(
        csv_path=csv_path, out_dir=tmp_path / "a", coverage_to=COVERAGE_TO,
        temp_dir=tmp_path / "tmp-a"))
    before = content_digests(built.snapshot_dir)
    rewrite(built.snapshot_dir / "year=2024" / "data.parquet",
            projection="* REPLACE (price + 1 AS price)")
    after = content_digests(built.snapshot_dir)
    assert after["2024"] != before["2024"]
    assert after["2026"] == before["2026"]


def test_the_content_digest_moves_when_only_the_order_changes(tmp_path: Path):
    # Order is part of the artifact, so a reordered partition is different
    # content even though it holds exactly the same rows.
    from tools.ppd_snapshot.validate import content_digests

    csv_path = write_source_csv(tmp_path / "pp.csv", SOURCE_ROWS)
    built = build_snapshot(BuildRequest(
        csv_path=csv_path, out_dir=tmp_path / "a", coverage_to=COVERAGE_TO,
        temp_dir=tmp_path / "tmp-a"))
    before = content_digests(built.snapshot_dir)
    rewrite(built.snapshot_dir / "year=2024" / "data.parquet",
            clause="ORDER BY transfer_date ASC")
    assert content_digests(built.snapshot_dir)["2024"] != before["2024"]


def test_validation_records_the_content_digest_as_a_fact(snapshot):
    _, declared = snapshot
    report = run(declared)
    assert set(report.facts["content_digest_per_year"]) == {
        str(y) for y in range(2016, 2027)}


def test_the_build_records_its_peak_memory(snapshot):
    built, _ = snapshot
    assert built.peak_rss_mb > 0
