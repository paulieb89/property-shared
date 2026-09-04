"""Acceptance: the artifact this pipeline builds is booted by the merged runtime.

Nothing here re-implements verification. The bundle goes through
`SnapshotRuntime` -- streamed fetch, digest and length check, member-validated
extraction, exact Parquet-file count, full file inventory, atomic activation --
and is then opened by `SnapshotAdapter`, which runs its own schema, row-count and
queryability validation before it will answer anything. That is the only
statement worth making about a build: not "our gates were happy", but "the code
that has to serve it accepted it".

The object source is a local directory. No network, no bucket, no upload.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb", reason="needs the optional 'snapshot' extra")
zstandard = pytest.importorskip("zstandard",
                                reason="needs the optional 'snapshot' extra")

from property_core.provenance import CompletenessBasis  # noqa: E402
from property_core.snapshot.adapter import SnapshotAdapter  # noqa: E402
from property_core.snapshot.models import Readiness  # noqa: E402
from property_core.snapshot.runtime import SnapshotRuntime  # noqa: E402
from property_core.snapshot.source import LocalDirectorySource  # noqa: E402
from property_core.snapshot.store import SnapshotStore  # noqa: E402
from tools.ppd_snapshot.build import BuildRequest, build_snapshot  # noqa: E402
from tools.ppd_snapshot.package import (  # noqa: E402
    package_release,
    promote_release,
    snapshot_version,
)
from tests.snapshot.build_fixtures import csv_row, write_source_csv  # noqa: E402

COVERAGE_TO = date(2026, 6, 30)

ROWS = [
    csv_row("{T-B57-2024}", "B5 7AA", "2024-03-01 00:00", 200_000),
    csv_row("{T-B57-2023}", "B5 7AB", "2023-06-15 00:00", 210_000),
    csv_row("{T-B56-2024}", "B5 6QQ", "2024-03-01 00:00", 300_000),
    csv_row("{T-B50-2024}", "B50 4AA", "2024-05-01 00:00", 400_000),
    csv_row("{T-M37-2026}", "M3 7AA", "2026-06-30 00:00", 250_000),
]


@pytest.fixture
def published(tmp_path: Path):
    csv_path = write_source_csv(tmp_path / "pp.csv", ROWS)
    built = build_snapshot(BuildRequest(
        csv_path=csv_path, out_dir=tmp_path / "snapshot",
        coverage_to=COVERAGE_TO, temp_dir=tmp_path / "tmp"))
    release = package_release(
        built, dist_dir=tmp_path / "dist", candidate_root=tmp_path / "work",
        version=snapshot_version(datetime(2026, 8, 28, 10, 15, tzinfo=timezone.utc)),
        source={"file": "pp.csv"}, facts={})
    # Promoted, because a published release is what the runtime is pointed at.
    # The candidate stage is exercised by the CLI tests.
    return promote_release(release)


def boot(release, tmp_path: Path):
    runtime = SnapshotRuntime(
        source=LocalDirectorySource(release.dist_dir),
        store=SnapshotStore(tmp_path / "store"))
    return runtime, runtime.boot()


def test_the_published_bundle_boots_through_the_real_runtime(published, tmp_path):
    _, report = boot(published, tmp_path)
    assert report.readiness is Readiness.READY, report.source_error
    assert report.activated is True
    assert report.fallback_to_live is False
    assert report.version == published.version
    assert report.bytes_downloaded == published.bundle_bytes


def test_the_materialized_snapshot_holds_exactly_the_published_partitions(
        published, tmp_path):
    _, report = boot(published, tmp_path)
    directory = Path(report.snapshot_dir)
    written = sorted(p.relative_to(directory).as_posix()
                     for p in directory.rglob("*.parquet"))
    assert written == [f"year={y}/data.parquet" for y in range(1995, 2027)]


def test_the_verification_record_carries_the_declared_coverage(published, tmp_path):
    runtime, report = boot(published, tmp_path)
    record = runtime.store.verified_record(report.version)
    assert record.coverage_from == "1995-01-01"
    assert record.coverage_to == "2026-06-30"
    assert record.provisional_from == "2026-03-01"
    assert record.layout == "year"
    assert record.rows == published.rows


def test_the_booted_snapshot_opens_through_the_real_adapter(published, tmp_path):
    runtime, report = boot(published, tmp_path)
    record = runtime.store.verified_record(report.version)
    with SnapshotAdapter.open(Path(report.snapshot_dir), record) as adapter:
        assert adapter.coverage_from == "1995-01-01"
        assert adapter.version == published.version


def test_the_adapter_answers_a_sector_query_without_bleeding_into_b50(
        published, tmp_path):
    runtime, report = boot(published, tmp_path)
    record = runtime.store.verified_record(report.version)
    with SnapshotAdapter.open(Path(report.snapshot_dir), record) as adapter:
        page = adapter.search(postcode_prefix="B5 7", limit=10)
    assert [t.transaction_id for t in page.transactions] == [
        "T-B57-2024", "T-B57-2023"]


def test_the_adapter_reports_limit_independent_completeness(published, tmp_path):
    runtime, report = boot(published, tmp_path)
    record = runtime.store.verified_record(report.version)
    with SnapshotAdapter.open(Path(report.snapshot_dir), record) as adapter:
        page = adapter.search(postcode_prefix="B5", limit=10)
    assert page.exhausted is True
    assert page.completeness_basis is CompletenessBasis.LIMIT_PLUS_ONE


def test_a_manifest_understating_the_parquet_count_is_refused(published, tmp_path):
    payload = json.loads(published.manifest_path.read_text())
    payload["parquet_files"] = 10
    published.manifest_path.write_text(json.dumps(payload))
    _, report = boot(published, tmp_path)
    assert report.readiness is Readiness.UNREADY
    assert report.fallback_to_live is True
    assert "parquet" in (report.source_error or "")


def test_a_bundle_whose_digest_moved_is_refused(published, tmp_path):
    blob = bytearray(published.bundle_path.read_bytes())
    blob[len(blob) // 2] ^= 0x01
    published.bundle_path.write_bytes(bytes(blob))
    _, report = boot(published, tmp_path)
    assert report.readiness is Readiness.UNREADY
    assert report.fallback_to_live is True
