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
def fixture_object_server(directory: Path):
    """Serves files from `directory` by basename -- a minimal S3-shaped GET."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            name = self.path.rsplit("/", 1)[-1].split("?")[0]
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

def test_verification_directory_must_not_collide_with_app_cache(tmp_path):
    cache_dir = tmp_path / "app-cache"
    cache_dir.mkdir()
    with pytest.raises(VerificationRefused, match="PPD_SNAPSHOT_CACHE_DIR"):
        _prepare_verification_directory(cache_dir / "nested" / "verify", cache_dir)


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


# -- end-to-end against a loopback fixture -----------------------------------

@requires_sdk
def test_successful_run_validates_and_reports_a_cold_run(tmp_path):
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir()
    build_snapshot_fixture(fixture_dir)

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

    assert result["label"] == "boot-only verification measurement"
    assert result["readiness"] == "ready"
    assert result["validated"] is True
    assert result["reused_existing"] is False
    assert result["bytes_downloaded"] > 0
    assert result["cold_run_valid"] is True
    assert result["coverage_from"] == "2016-01-01"
    assert result["coverage_to"] == "2026-06-30"
    assert result["materialization_ms"] >= 0
    assert result["validation_ms"] >= 0
    assert result["peak_transient_disk_bytes"] > 0
    assert result["process_peak_rss_bytes"] > 0


@requires_sdk
def test_run_cleans_up_the_verification_directory_on_success(tmp_path):
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir()
    build_snapshot_fixture(fixture_dir)

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
    """An unreachable source degrades to UNREADY; cleanup still runs."""
    verify_dir = tmp_path / "verify-root" / "run"
    verify_dir.parent.mkdir()

    with fixture_object_server(tmp_path / "empty-does-not-exist") as endpoint:
        source = _tigris_source(endpoint)
        result = run_boot_only_verification(
            source, verify_dir=verify_dir, cache_dir=tmp_path / "app-cache",
            sample_interval=0.01, mounts_text=_ext4_mounts_for(verify_dir.parent),
        )

    assert result["validated"] is False
    assert not verify_dir.exists()


@requires_sdk
def test_run_never_installs_into_process_state(tmp_path, monkeypatch):
    """Confirms non-interference with `state` behaviourally, not just by
    absence of an import: a successful run must never call `state.install`."""
    import property_core.snapshot.state as state

    install_spy = Mock(wraps=state.install)
    monkeypatch.setattr(state, "install", install_spy)

    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir()
    build_snapshot_fixture(fixture_dir)

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
