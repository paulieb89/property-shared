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


#: Validators for the synthetic "release". `Last-Modified` in July implies a
#: coverage end of 30 June, which is what the coverage gate checks against.
LAST_MODIFIED = "Tue, 28 Jul 2026 05:16:16 GMT"


def prepare(tmp_path: Path, *, content_length: int | None = None,
            etag: str = '"a-release-etag"') -> Path:
    """A source CSV bound to an observed release by a receipt."""
    csv_path = write_source_csv(tmp_path / "pp.csv", ROWS)
    state = tmp_path / "release-state.json"
    state.write_text(json.dumps({
        "url": "https://example.invalid/pp-complete.csv",
        "etag": etag,
        "last_modified": LAST_MODIFIED,
        "content_length": (csv_path.stat().st_size if content_length is None
                           else content_length),
        "first_observed_utc": "2026-08-28T09:00:00+00:00",
    }))
    return csv_path


def argv(tmp_path: Path, **over) -> list[str]:
    args = {
        "--csv": str(tmp_path / "pp.csv"),
        "--work": str(tmp_path / "work"),
        "--dist": str(tmp_path / "dist"),
        "--coverage-to": "2026-06-30",
        "--source-coverage-end": "2026-06-30",
        "--today": "2026-07-15",
        "--version": "v20260828T101500Z",
        "--release-state": str(tmp_path / "release-state.json"),
        "--source-receipt": str(tmp_path / "receipt.json"),
    }
    args.update(over)
    flat: list[str] = []
    for key, value in args.items():
        flat += [key, value]
    return flat


def bound(tmp_path: Path, **over) -> list[str]:
    """`prepare` plus a written receipt: the ordinary, authorised flow."""
    prepare(tmp_path, **over)
    assert main(["receipt", "--csv", str(tmp_path / "pp.csv"),
                 "--release-state", str(tmp_path / "release-state.json"),
                 "--receipt", str(tmp_path / "receipt.json")]) == 0
    return argv(tmp_path)


def test_the_all_command_builds_validates_packages_and_boots(tmp_path, capsys):
    assert main(["all", *bound(tmp_path)]) == 0
    dist = tmp_path / "dist"
    assert (dist / "current.json").is_file()
    assert (dist / "manifest-v20260828T101500Z.json").is_file()
    assert (dist / "snapshot-v20260828T101500Z.tar.zst").is_file()
    assert (dist / "build-report-v20260828T101500Z.json").is_file()
    assert "READY" in capsys.readouterr().out


def test_a_failing_gate_stops_before_anything_is_packaged(tmp_path, capsys):
    # The snapshot claims a window the source release does not cover.
    bound(tmp_path)
    code = main(["all", *argv(tmp_path,
                              **{"--source-coverage-end": "2026-05-31"})])
    assert code != 0
    assert list((tmp_path / "dist").glob("*.tar.zst")) == []
    assert "coverage" in capsys.readouterr().out


def test_the_build_report_records_what_was_measured(tmp_path):
    assert main(["all", *bound(tmp_path)]) == 0
    report = json.loads(
        (tmp_path / "dist" / "build-report-v20260828T101500Z.json").read_text())
    assert report["rows"] == 2
    assert report["parquet_files"] == 11
    assert report["gates"] == "passed"
    assert report["rows_per_year"]["2024"] == 1
    assert report["boot_check"]["readiness"] == "ready"


def test_validate_alone_reports_every_gate(tmp_path, capsys):
    bound(tmp_path)
    assert main(["build", *argv(tmp_path)]) == 0
    code = main(["validate", "--snapshot", str(tmp_path / "work" / "snapshot"),
                 "--coverage-to", "2026-06-30",
                 "--source-coverage-end", "2026-06-30", "--today", "2026-07-15",
                 "--rows", "2", "--eligible-source-rows", "2"])
    assert code == 0
    out = capsys.readouterr().out
    for gate in ("partitions", "schema", "rows", "uniqueness", "coverage",
                 "guarantee", "provisional", "ordering", "required_values",
                 "reconciliation"):
        assert gate in out


def test_a_failed_boot_check_leaves_the_dist_root_empty(tmp_path, monkeypatch):
    """A bundle in `dist` is a bundle someone can publish.

    Reproduction: with the boot check forced to fail, the pipeline used to leave
    the bundle, the manifest and `current.json` sitting in the final directory.
    """
    from tools.ppd_snapshot import __main__ as cli

    monkeypatch.setattr(cli, "_boot_check", lambda *a, **k: {
        "readiness": "unready", "version": None, "activated": False,
        "bytes_downloaded": 0, "source_error": "forced", "timings_ms": {}})
    assert main(["all", *bound(tmp_path)]) != 0

    dist = tmp_path / "dist"
    assert not (dist / "current.json").exists()
    assert list(dist.glob("*.tar.zst")) == []
    assert list(dist.glob("manifest-*.json")) == []
    # The candidate is kept for diagnosis, and is not a published release.
    assert [p.name for p in dist.iterdir()] == ["candidate-v20260828T101500Z"]


# -- the source must be bound to a release ----------------------------------

def test_the_all_command_refuses_without_a_source_receipt(tmp_path, capsys):
    prepare(tmp_path)
    assert main(["all", *argv(tmp_path)]) != 0
    assert "no source receipt" in capsys.readouterr().out
    assert not (tmp_path / "dist").exists() or \
        list((tmp_path / "dist").iterdir()) == []


def test_a_receipt_is_refused_for_a_file_the_release_contradicts(tmp_path, capsys):
    """The reproduction: a stale local CSV under a release describing something
    far larger. It used to build, validate and boot READY."""
    prepare(tmp_path, content_length=999_999_999)
    code = main(["receipt", "--csv", str(tmp_path / "pp.csv"),
                 "--release-state", str(tmp_path / "release-state.json"),
                 "--receipt", str(tmp_path / "receipt.json")])
    assert code != 0
    assert "999999999" in capsys.readouterr().out
    assert not (tmp_path / "receipt.json").exists()


def test_the_all_command_refuses_once_the_release_has_moved_on(tmp_path, capsys):
    bound(tmp_path)
    # HMLR publishes again: the CSV on disk is now the previous release.
    state = tmp_path / "release-state.json"
    payload = json.loads(state.read_text())
    payload["etag"] = '"a-newer-etag"'
    payload["content_length"] = 999_999_999
    state.write_text(json.dumps(payload))

    assert main(["all", *argv(tmp_path)]) != 0
    out = capsys.readouterr().out
    assert "refusing to build" in out and "moved" in out
    assert list((tmp_path / "dist").glob("*.tar.zst")) == []


def test_the_all_command_refuses_a_csv_edited_since_its_receipt(tmp_path, capsys):
    bound(tmp_path)
    (tmp_path / "pp.csv").write_text("\"{X}\",\"1\",\"2024-01-01 00:00\"\n")
    assert main(["all", *argv(tmp_path)]) != 0
    assert "refusing to build" in capsys.readouterr().out


def test_validate_without_a_source_count_does_not_report_success(tmp_path, capsys):
    # Reconciliation cannot run, and an unrunnable gate is not a passing one.
    bound(tmp_path)
    assert main(["build", *argv(tmp_path)]) == 0
    code = main(["validate", "--snapshot", str(tmp_path / "work" / "snapshot"),
                 "--coverage-to", "2026-06-30",
                 "--source-coverage-end", "2026-06-30", "--today", "2026-07-15"])
    assert code != 0
    assert "skip" in capsys.readouterr().out


def test_the_build_command_also_refuses_an_unbound_source(tmp_path, capsys):
    # `build` writes the artifact that `validate` then blesses, so it applies
    # the same binding as `all` rather than being a way around it.
    prepare(tmp_path)
    assert main(["build", *argv(tmp_path)]) != 0
    assert "no source receipt" in capsys.readouterr().out
    assert not (tmp_path / "work" / "snapshot").exists()
