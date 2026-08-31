"""Boot-only verifier tests; loopback only, never Tigris or PPD.

Reuses `tests/snapshot/image_smoke.py`'s synthetic snapshot fixture rather
than building a second one.
"""

from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import Mock
import importlib.util
import time

import pytest

from property_core.snapshot.models import BootReport, Readiness
from tests.snapshot.image_smoke import fixture as build_snapshot_fixture
from tools.ppd_snapshot.boot_only_verify import (
    VerificationRefused,
    _is_cold_run_valid,
    _prepare_verification_directory,
    assert_disk_backed,
    run_boot_only_verification,
)

requires_sdk = pytest.mark.skipif(
    importlib.util.find_spec("botocore") is None
    or importlib.util.find_spec("duckdb") is None
    or importlib.util.find_spec("zstandard") is None,
    reason="boot-only verification needs the snapshot extra",
)


@contextmanager
def fixture_object_server(directory: Path, delays: dict | None = None):
    """Serves files from `directory` by basename -- a minimal S3-shaped GET.

    `delays` (object name -> seconds) sleeps before responding to that one
    object, so tests can make a specific phase (e.g. the bundle transfer)
    deliberately slow without touching the runtime being verified.
    """
    delays = delays or {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            name = self.path.rsplit("/", 1)[-1].split("?")[0]
            time.sleep(delays.get(name, 0))
            file_path = directory / name
            if not file_path.is_file():
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def _ext4_mounts_for(path: Path) -> str:
    return f"none {path} ext4 rw 0 0\n"


def _tmpfs_mounts_for(path: Path) -> str:
    return f"none {path} tmpfs rw 0 0\n"


def _tigris_source(endpoint: str, **overrides):
    from property_core.snapshot.s3_source import TigrisObjectSource

    kwargs = dict(access_key="test-key", secret_key="test-secret",
                 endpoint=endpoint, prefix="")
    kwargs.update(overrides)
    return TigrisObjectSource("ppd-test", **kwargs)


def _build_fixture(tmp_path: Path) -> Path:
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir()
    build_snapshot_fixture(fixture_dir)
    return fixture_dir


# -- disk-backed assertion ---------------------------------------------------

def test_disk_backed_assertion_refuses_tmpfs(tmp_path):
    with pytest.raises(VerificationRefused, match="tmpfs"):
        assert_disk_backed(tmp_path, _tmpfs_mounts_for(tmp_path))


def test_disk_backed_assertion_accepts_ext4(tmp_path):
    assert assert_disk_backed(tmp_path, _ext4_mounts_for(tmp_path)) == "ext4"


def test_disk_backed_assertion_refuses_when_nothing_matches(tmp_path):
    with pytest.raises(VerificationRefused, match="no mount entry"):
        assert_disk_backed(tmp_path, "none /completely/unrelated ext4 rw 0 0\n")


# -- verification-directory preparation --------------------------------------

def test_verification_directory_must_not_nest_inside_the_app_cache(tmp_path):
    cache_dir = tmp_path / "app-cache"
    cache_dir.mkdir()
    with pytest.raises(VerificationRefused, match="sibling directories"):
        _prepare_verification_directory(cache_dir / "nested" / "verify", cache_dir)


def test_app_cache_must_not_nest_inside_the_verification_directory(tmp_path):
    """The reverse direction: an app cache configured beneath the
    verification directory must also be refused -- otherwise this module's
    unconditional `rmtree(verify_dir)` would delete the application's store."""
    verify_dir = tmp_path / "verify"
    cache_dir = verify_dir / "nested-cache"
    with pytest.raises(VerificationRefused, match="sibling directories"):
        _prepare_verification_directory(verify_dir, cache_dir)


def test_verification_directory_must_not_already_exist(tmp_path):
    existing = tmp_path / "already-here"
    existing.mkdir()
    with pytest.raises(VerificationRefused, match="already exists"):
        _prepare_verification_directory(existing, tmp_path / "cache")


# -- cold-run validity --------------------------------------------------------

def _report(*, reused_existing=False, bytes_downloaded=0) -> BootReport:
    return BootReport(readiness=Readiness.READY, version="v1",
                      fallback_to_live=False, reused_existing=reused_existing,
                      bytes_downloaded=bytes_downloaded)


def test_cold_run_invalid_when_reused():
    report = _report(reused_existing=True, bytes_downloaded=1000)
    assert _is_cold_run_valid(report, expected_bundle_bytes=1000) is False


def test_cold_run_invalid_when_bytes_mismatch():
    report = _report(reused_existing=False, bytes_downloaded=999)
    assert _is_cold_run_valid(report, expected_bundle_bytes=1000) is False


def test_cold_run_valid_when_matching():
    report = _report(reused_existing=False, bytes_downloaded=1000)
    assert _is_cold_run_valid(report, expected_bundle_bytes=1000) is True


def test_cold_run_valid_without_an_expected_size_if_something_downloaded():
    report = _report(reused_existing=False, bytes_downloaded=1)
    assert _is_cold_run_valid(report, expected_bundle_bytes=None) is True


def test_cli_exposes_no_expected_bundle_bytes_escape_hatch():
    """The deployed CLI must always require the declared bundle size --
    confirmed by the parser itself accepting no such flag, not just by
    convention."""
    from tools.ppd_snapshot.boot_only_verify import build_parser

    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--verify-dir", "/tmp/x", "--expected-bundle-bytes", "0"])


# -- every result carries explicit evidence-scope labelling -------------------

def test_refusal_result_carries_evidence_scope_labels(tmp_path):
    """Even a refusal before anything is materialized must say what this
    tool can never provide -- not just a generic label."""
    from tools.ppd_snapshot.boot_only_verify import _base_result

    result = _base_result()
    assert result["evidence_scope"] == "partial_g1a"
    assert result["g1a_complete"] is False
    assert result["stage_1_evidence"] is False


# -- end-to-end against a loopback fixture -----------------------------------

@requires_sdk
def test_successful_run_validates_and_reports_a_cold_run(tmp_path):
    fixture_dir = _build_fixture(tmp_path)

    verify_dir = tmp_path / "verify-root" / "run"
    verify_dir.parent.mkdir()
    cache_dir = tmp_path / "app-cache"

    with fixture_object_server(fixture_dir) as endpoint:
        source = _tigris_source(endpoint)
        result = run_boot_only_verification(
            source, verify_dir=verify_dir, cache_dir=cache_dir,
            expected_bundle_bytes=None, sample_interval=0.01,
            mounts_text=_ext4_mounts_for(verify_dir.parent),
        )

    assert result["evidence_scope"] == "partial_g1a"
    assert result["g1a_complete"] is False
    assert result["stage_1_evidence"] is False
    assert result["readiness"] == "ready"
    assert result["validated"] is True
    assert result["reused_existing"] is False
    assert result["bytes_downloaded"] > 0
    assert result["cold_run_valid"] is True
    assert result["coverage_from"] == "2016-01-01"
    assert result["coverage_to"] == "2026-06-30"
    assert result["materialization_ms"] >= 0
    assert result["validation_ms"] >= 0
    assert result["fetch_ms"] is not None and result["fetch_ms"] >= 0
    assert result["extraction_ms"] is not None and result["extraction_ms"] >= 0
    assert result["overlap_window_ms"] == result["extraction_ms"]
    assert result["peak_transient_disk_bytes"] > 0
    assert result["process_peak_rss_bytes"] > 0
    assert result["cleanup_ok"] is True
    assert result["cleanup_error"] is None


@requires_sdk
def test_run_cleans_up_the_verification_directory_on_success(tmp_path):
    fixture_dir = _build_fixture(tmp_path)

    verify_dir = tmp_path / "verify-root" / "run"
    verify_dir.parent.mkdir()

    with fixture_object_server(fixture_dir) as endpoint:
        source = _tigris_source(endpoint)
        run_boot_only_verification(
            source, verify_dir=verify_dir, cache_dir=tmp_path / "app-cache",
            sample_interval=0.01, mounts_text=_ext4_mounts_for(verify_dir.parent),
        )

    assert not verify_dir.exists()


def test_run_cleans_up_the_verification_directory_on_failure(tmp_path):
    """An unreachable source degrades to UNREADY; cleanup still runs, and
    every field the base result carries is still present."""
    verify_dir = tmp_path / "verify-root" / "run"
    verify_dir.parent.mkdir()

    with fixture_object_server(tmp_path / "empty-does-not-exist") as endpoint:
        source = _tigris_source(endpoint)
        result = run_boot_only_verification(
            source, verify_dir=verify_dir, cache_dir=tmp_path / "app-cache",
            sample_interval=0.01, mounts_text=_ext4_mounts_for(verify_dir.parent),
        )

    assert result["validated"] is False
    assert result["evidence_scope"] == "partial_g1a"
    assert result["cleanup_ok"] is True
    assert not verify_dir.exists()
    # Nothing was ever fetched or extracted -- both phases correctly absent,
    # not a stale zero.
    assert result["fetch_ms"] is None
    assert result["extraction_ms"] is None


def test_cleanup_failure_is_recorded_explicitly_not_swallowed(tmp_path, monkeypatch):
    """A removal failure must surface in the result, never be hidden behind
    `ignore_errors=True` while the run is still reported as validated."""
    import tools.ppd_snapshot.boot_only_verify as module

    verify_dir = tmp_path / "verify-root" / "run"
    verify_dir.parent.mkdir()

    def failing_rmtree(_path, **_kwargs):
        raise OSError("simulated: device busy")

    monkeypatch.setattr(module.shutil, "rmtree", failing_rmtree)

    with fixture_object_server(tmp_path / "empty-does-not-exist") as endpoint:
        source = _tigris_source(endpoint)
        result = run_boot_only_verification(
            source, verify_dir=verify_dir, cache_dir=tmp_path / "app-cache",
            sample_interval=0.01, mounts_text=_ext4_mounts_for(verify_dir.parent),
        )

    assert result["cleanup_ok"] is False
    assert "simulated: device busy" in result["cleanup_error"]
    # The directory the failed rmtree was supposed to remove is exactly the
    # one this run created -- prove the tool is not silently pointed
    # elsewhere by asserting it still exists (the mock never removed it).
    assert verify_dir.exists()


@requires_sdk
def test_run_never_installs_into_process_state(tmp_path, monkeypatch):
    """Confirms non-interference with `state` behaviourally, not just by
    absence of an import: a successful run must never call `state.install`."""
    import property_core.snapshot.state as state

    install_spy = Mock(wraps=state.install)
    monkeypatch.setattr(state, "install", install_spy)

    fixture_dir = _build_fixture(tmp_path)

    verify_dir = tmp_path / "verify-root" / "run"
    verify_dir.parent.mkdir()

    with fixture_object_server(fixture_dir) as endpoint:
        source = _tigris_source(endpoint)
        result = run_boot_only_verification(
            source, verify_dir=verify_dir, cache_dir=tmp_path / "app-cache",
            sample_interval=0.01, mounts_text=_ext4_mounts_for(verify_dir.parent),
        )

    assert result["validated"] is True
    install_spy.assert_not_called()


@requires_sdk
def test_process_rss_is_sampled_after_adapter_validation_not_before(tmp_path, monkeypatch):
    """DuckDB validation memory must be included in process_peak_rss_bytes --
    proven by ordering (getrusage called after _validate), since a magnitude
    assertion against a KB-scale fixture would be unreliable."""
    import property_core.snapshot.adapter as adapter_module
    import tools.ppd_snapshot.boot_only_verify as module

    call_order = []

    original_validate = adapter_module.SnapshotAdapter._validate

    def recording_validate(self):
        call_order.append("validate")
        return original_validate(self)

    original_getrusage = module.resource.getrusage

    def recording_getrusage(*args, **kwargs):
        call_order.append("getrusage")
        return original_getrusage(*args, **kwargs)

    monkeypatch.setattr(adapter_module.SnapshotAdapter, "_validate", recording_validate)
    monkeypatch.setattr(module.resource, "getrusage", recording_getrusage)

    fixture_dir = _build_fixture(tmp_path)
    verify_dir = tmp_path / "verify-root" / "run"
    verify_dir.parent.mkdir()

    with fixture_object_server(fixture_dir) as endpoint:
        source = _tigris_source(endpoint)
        result = run_boot_only_verification(
            source, verify_dir=verify_dir, cache_dir=tmp_path / "app-cache",
            sample_interval=0.01, mounts_text=_ext4_mounts_for(verify_dir.parent),
        )

    assert result["validated"] is True
    assert "validate" in call_order and "getrusage" in call_order
    assert call_order.index("validate") < call_order.index("getrusage"), (
        "process_peak_rss_bytes must be read after adapter validation, "
        f"not before: {call_order}"
    )


@requires_sdk
def test_phase_timings_bind_to_the_correct_phase(tmp_path, monkeypatch):
    """Deliberately slows fetch, extraction and adapter-validation by
    different, distinguishable amounts, and proves each reported timing
    binds to its own phase rather than to the run as a whole."""
    import property_core.snapshot.adapter as adapter_module

    fixture_dir = _build_fixture(tmp_path)
    bundle_name = "fixture.tar.zst"

    original_validate = adapter_module.SnapshotAdapter._validate

    def slow_validate(self):
        time.sleep(0.10)
        return original_validate(self)

    monkeypatch.setattr(adapter_module.SnapshotAdapter, "_validate", slow_validate)

    verify_dir = tmp_path / "verify-root" / "run"
    verify_dir.parent.mkdir()

    with fixture_object_server(fixture_dir, delays={bundle_name: 0.30}) as endpoint:
        source = _tigris_source(endpoint)
        result = run_boot_only_verification(
            source, verify_dir=verify_dir, cache_dir=tmp_path / "app-cache",
            expected_bundle_bytes=None, sample_interval=0.01,
            mounts_text=_ext4_mounts_for(verify_dir.parent),
        )

    assert result["validated"] is True

    # Fetch was slowed by 0.30s -- must dominate.
    assert result["fetch_ms"] >= 250
    # Extraction was not slowed (only the download response was delayed);
    # it must be well below the injected fetch delay, not smeared across it.
    assert result["extraction_ms"] is not None
    assert result["extraction_ms"] < 150
    # Validation was slowed by 0.10s, independently of fetch/extraction.
    assert result["validation_ms"] >= 80
    assert result["validation_ms"] < result["fetch_ms"]

    # materialization_ms wraps only runtime.boot() (fetch + extract), and
    # must NOT include the adapter-validation delay that happens afterward.
    assert result["materialization_ms"] >= result["fetch_ms"]
    assert result["materialization_ms"] < result["fetch_ms"] + 150

    # overlap_window_ms is defined as exactly extraction_ms.
    assert result["overlap_window_ms"] == result["extraction_ms"]
