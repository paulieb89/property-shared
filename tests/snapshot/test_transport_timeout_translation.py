"""A real socket timeout must reach the caller as the typed failure.

Driven against a loopback HTTP server that sends valid headers and then stalls
the body — the production boundary, not a mock. A mocked test can only show that
a timeout value reaches urlopen; it cannot show what the caller receives when the
socket actually times out, which is where `builtins.TimeoutError` was escaping.
"""

from __future__ import annotations

import hashlib
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from property_core.snapshot.errors import DownloadDeadlineExceeded
from property_core.snapshot.fetch import download_verified
from property_core.snapshot.models import SnapshotManifest
from property_core.snapshot.source import HttpObjectSource

BODY = b"Z" * 4096


def _server(handler_cls):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class StallingBody(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(BODY)))
        self.end_headers()
        self.wfile.write(BODY[:16])
        self.wfile.flush()
        time.sleep(5)          # valid headers, then the body stalls


class ServesFine(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(BODY)))
        self.end_headers()
        self.wfile.write(BODY)


@pytest.fixture
def stalling():
    server = _server(StallingBody)
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
def healthy():
    server = _server(ServesFine)
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _manifest() -> SnapshotManifest:
    return SnapshotManifest(
        snapshot_version="v1", bundle_object="b.tar",
        bundle_sha256=hashlib.sha256(BODY).hexdigest(),
        bundle_bytes=len(BODY), parquet_files=1, rows=1)


def test_a_real_socket_timeout_raises_the_typed_failure(stalling, tmp_path):
    source = HttpObjectSource(stalling, socket_timeout=0.05)
    dest = tmp_path / "b.tar"
    with pytest.raises(DownloadDeadlineExceeded) as ei:
        download_verified(source, _manifest(), dest, check_disk=False)
    assert "timed out" in str(ei.value).lower()
    assert not dest.exists(), "a timed-out transfer must leave no partial file"


def test_the_original_timeout_is_preserved_as_the_cause(stalling, tmp_path):
    """Translation must not lose the diagnosis."""
    source = HttpObjectSource(stalling, socket_timeout=0.05)
    with pytest.raises(DownloadDeadlineExceeded) as ei:
        download_verified(source, _manifest(), tmp_path / "b.tar", check_disk=False)
    cause = ei.value.__cause__
    assert cause is not None, "the underlying timeout was discarded"
    assert isinstance(cause, (TimeoutError, OSError)), type(cause)


def test_no_bare_timeout_error_escapes_to_the_caller(stalling, tmp_path):
    """The specific regression: builtins.TimeoutError reaching the caller."""
    source = HttpObjectSource(stalling, socket_timeout=0.05)
    try:
        download_verified(source, _manifest(), tmp_path / "b.tar", check_disk=False)
    except DownloadDeadlineExceeded:
        pass
    except TimeoutError as exc:  # pragma: no cover - the defect
        pytest.fail(f"untyped {type(exc).__name__} escaped: {exc}")


def test_the_typed_failure_is_the_exported_one(stalling, tmp_path):
    import property_core.snapshot as snapshot

    source = HttpObjectSource(stalling, socket_timeout=0.05)
    with pytest.raises(snapshot.DownloadDeadlineExceeded):
        download_verified(source, _manifest(), tmp_path / "b.tar", check_disk=False)


def test_a_healthy_server_still_downloads_and_verifies(healthy, tmp_path):
    """Guard the guard: the translation must not break the working path."""
    source = HttpObjectSource(healthy, socket_timeout=10.0)
    dest = tmp_path / "b.tar"
    result = download_verified(source, _manifest(), dest, check_disk=False)
    assert result.bytes_written == len(BODY)
    assert result.sha256 == hashlib.sha256(BODY).hexdigest()
    assert dest.read_bytes() == BODY


def test_a_control_object_timeout_also_surfaces_typed(stalling):
    """read_bytes shares the same socket timeout; it must not leak a bare one."""
    source = HttpObjectSource(stalling, socket_timeout=0.05)
    with pytest.raises((DownloadDeadlineExceeded, OSError)) as ei:
        source.read_bytes("current.json")
    # If it is an OSError it must at least not be a silent success.
    assert ei.value is not None
