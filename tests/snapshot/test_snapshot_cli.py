"""The operator entry point, exercised end to end on a synthetic source file.

The important behaviour under test is the ordering: a snapshot that fails a gate
must never reach the packaging step. A bundle that exists is a bundle someone
can publish, and "we knew it was bad" is not a control.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb", reason="needs the optional 'snapshot' extra")
zstandard = pytest.importorskip("zstandard",
                                reason="needs the optional 'snapshot' extra")

from tools.ppd_snapshot.__main__ import main  # noqa: E402
from tests.snapshot.build_fixtures import csv_row, write_source_csv  # noqa: E402

ROWS = [
    csv_row("{T-2024}", "B5 7AA", "2024-03-01 00:00", 210_000),
    csv_row("{T-2026}", "M3 7AA", "2026-06-30 00:00", 250_000),
]


def argv(tmp_path: Path, **over) -> list[str]:
    args = {
        "--csv": str(write_source_csv(tmp_path / "pp.csv", ROWS)),
        "--work": str(tmp_path / "work"),
        "--dist": str(tmp_path / "dist"),
        "--coverage-to": "2026-06-30",
        "--source-coverage-end": "2026-06-30",
        "--today": "2026-07-15",
        "--version": "v20260828T101500Z",
    }
    args.update(over)
    flat: list[str] = []
    for key, value in args.items():
        flat += [key, value]
    return flat


def test_the_all_command_builds_validates_packages_and_boots(tmp_path, capsys):
    assert main(["all", *argv(tmp_path)]) == 0
    dist = tmp_path / "dist"
    assert (dist / "current.json").is_file()
    assert (dist / "manifest-v20260828T101500Z.json").is_file()
    assert (dist / "snapshot-v20260828T101500Z.tar.zst").is_file()
    assert (dist / "build-report-v20260828T101500Z.json").is_file()
    assert "READY" in capsys.readouterr().out


def test_a_failing_gate_stops_before_anything_is_packaged(tmp_path, capsys):
    # The snapshot claims a window the source release does not cover.
    code = main(["all", *argv(tmp_path, **{"--source-coverage-end": "2026-05-31"})])
    assert code != 0
    assert list((tmp_path / "dist").glob("*.tar.zst")) == []
    assert "coverage" in capsys.readouterr().out


def test_the_build_report_records_what_was_measured(tmp_path):
    assert main(["all", *argv(tmp_path)]) == 0
    report = json.loads(
        (tmp_path / "dist" / "build-report-v20260828T101500Z.json").read_text())
    assert report["rows"] == 2
    assert report["parquet_files"] == 11
    assert report["gates"] == "passed"
    assert report["rows_per_year"]["2024"] == 1
    assert report["boot_check"]["readiness"] == "ready"


def test_validate_alone_reports_every_gate(tmp_path, capsys):
    assert main(["build", *argv(tmp_path)]) == 0
    code = main(["validate", "--snapshot", str(tmp_path / "work" / "snapshot"),
                 "--coverage-to", "2026-06-30",
                 "--source-coverage-end", "2026-06-30", "--today", "2026-07-15"])
    assert code == 0
    out = capsys.readouterr().out
    for gate in ("partitions", "schema", "rows", "uniqueness", "coverage",
                 "guarantee", "provisional", "ordering"):
        assert gate in out
