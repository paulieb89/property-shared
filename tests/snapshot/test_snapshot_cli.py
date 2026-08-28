"""The operator entry point, exercised end to end on a synthetic source file.

The important behaviour under test is the ordering: a snapshot that fails a gate
must never reach the packaging step. A bundle that exists is a bundle someone
can publish, and "we knew it was bad" is not a control.
"""

from __future__ import annotations

import hashlib
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
    """`prepare` plus a written receipt: the ordinary, authorised flow.

    The digest stands in for the one recorded when the file was downloaded --
    the receipt refuses to be minted without it.
    """
    csv_path = prepare(tmp_path, **over)
    recorded = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    assert main(["receipt", "--csv", str(csv_path),
                 "--release-state", str(tmp_path / "release-state.json"),
                 "--receipt", str(tmp_path / "receipt.json"),
                 "--expected-sha256", recorded]) == 0
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
    # The declared window disagrees with the release the receipt binds to.
    code = main(["all", *argv(tmp_path, **{"--coverage-to": "2026-05-31"})])
    assert code != 0
    assert not (tmp_path / "dist").exists() or \
        list((tmp_path / "dist").glob("*.tar.zst")) == []
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
    # Nothing is in the publishing directory at all -- not even a subdirectory
    # someone could mistake for a release.
    assert not dist.exists() or list(dist.iterdir()) == []
    # The candidate is kept for diagnosis, outside dist.
    assert (tmp_path / "work" / "candidates" /
            "candidate-v20260828T101500Z").is_dir()


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
    csv_path = prepare(tmp_path, content_length=999_999_999)
    code = main(["receipt", "--csv", str(csv_path),
                 "--release-state", str(tmp_path / "release-state.json"),
                 "--receipt", str(tmp_path / "receipt.json"),
                 "--expected-sha256",
                 hashlib.sha256(csv_path.read_bytes()).hexdigest()])
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


# -- the declared window cannot be talked past ------------------------------

def test_the_all_command_does_not_accept_a_source_coverage_end_override(tmp_path):
    """The reproduction: a 28 July release was published as covering 31 July by
    setting both date arguments to agree with each other."""
    bound(tmp_path)
    with pytest.raises(SystemExit):
        main(["all", *argv(tmp_path), "--source-coverage-end", "2026-07-31"])


def test_a_window_the_release_does_not_cover_is_refused(tmp_path, capsys):
    bound(tmp_path)
    code = main(["all", *argv(tmp_path, **{"--coverage-to": "2026-07-31"})])
    assert code != 0
    out = capsys.readouterr().out
    assert "coverage" in out and "2026-06-30" in out
    assert not (tmp_path / "dist").exists() or \
        list((tmp_path / "dist").glob("*.tar.zst")) == []


def test_the_expected_end_comes_from_the_receipt_not_the_command_line(tmp_path,
                                                                     capsys):
    bound(tmp_path)
    assert main(["all", *argv(tmp_path)]) == 0
    assert "2026-06-30" in capsys.readouterr().out


def test_the_build_command_refuses_a_window_the_release_does_not_cover(
        tmp_path, capsys):
    """`build` writes the artifact `validate` later blesses, so the declaration
    has to be checked before anything is written -- not by a gate afterwards."""
    bound(tmp_path)
    code = main(["build", *argv(tmp_path, **{"--coverage-to": "2026-07-31"})])
    assert code != 0
    out = capsys.readouterr().out
    assert "2026-06-30" in out and "2026-07-31" in out
    assert not (tmp_path / "work" / "snapshot").exists()
    assert list((tmp_path / "work").rglob("*.parquet")) == []


def test_a_mismatched_window_writes_no_snapshot_at_all(tmp_path):
    # `all` fails the same way, and fails before the build rather than after it.
    bound(tmp_path)
    assert main(["all", *argv(tmp_path, **{"--coverage-to": "2026-07-31"})]) != 0
    assert list((tmp_path / "work").rglob("*.parquet")) == []


def test_the_source_is_verified_once_per_run(tmp_path, monkeypatch):
    """Verification digests the whole CSV. Doing it twice is a second full pass
    over 5.5 GB for no additional evidence."""
    from tools.ppd_snapshot import __main__ as cli

    bound(tmp_path)
    calls = []
    real = cli.verify_source
    monkeypatch.setattr(cli, "verify_source",
                        lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    assert main(["all", *argv(tmp_path)]) == 0
    assert len(calls) == 1


def test_a_retained_backup_is_reported_to_the_operator(tmp_path, monkeypatch,
                                                       capsys):
    """A rollback failure leaves the only copy of the previous release in a
    temporary file. Its path is the whole recovery instruction."""
    from tools.ppd_snapshot import __main__ as cli
    from tools.ppd_snapshot.source_receipt import ReceiptRollbackFailed

    backup = tmp_path / ".pp.csv.xyz.prev"

    def _boom(*args, **kwargs):
        raise ReceiptRollbackFailed(f"retained at {backup}", backup_path=backup)

    monkeypatch.setattr(cli, "download_with_receipt", _boom)
    code = cli.main(["download", "--url", "http://example.invalid/pp.csv",
                     "--dest", str(tmp_path / "pp.csv"),
                     "--receipt", str(tmp_path / "receipt.json")])
    assert code != 0
    assert str(backup) in capsys.readouterr().out
