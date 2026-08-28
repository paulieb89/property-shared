"""A real socket timeout must reach the caller as the typed failure.

Driven against a loopback HTTP server that sends valid headers and then stalls
the body — the production boundary, not a mock. A mocked test can only show that
a timeout value reaches urlopen; it cannot show what the caller receives when the
socket actually times out, which is where `builtins.TimeoutError` was escaping.
"""

from __future__ import annotations

import hashlib
import socket
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


# --------------------------------------------------------------------------
# Every seam where a socket operation can time out, not only the bundle body.
#
# The previous version of the control-object test allowed
# `pytest.raises((DownloadDeadlineExceeded, OSError))`. TimeoutError subclasses
# OSError, so that tuple accepted precisely the raw escape the test was named
# for. Every assertion below admits DownloadDeadlineExceeded and nothing else.
# --------------------------------------------------------------------------


class WithholdsHeaders:
    """A raw socket server that accepts the connection and never responds.

    The timeout then happens while waiting for response headers -- before any
    stream object exists, so a translation living only in `_HttpStream.read`
    cannot catch it.
    """

    def __init__(self):
        self._sock = socket.socket()
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(5)
        self.port = self._sock.getsockname()[1]
        self._held: list = []
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                conn, _addr = self._sock.accept()
            except OSError:
                return
            self._held.append(conn)          # accepted, never answered

    def close(self):
        for conn in self._held:
            conn.close()
        self._sock.close()


@pytest.fixture
def headerless():
    server = WithholdsHeaders()
    yield f"http://127.0.0.1:{server.port}"
    server.close()


def test_control_read_timeout_is_typed_when_the_body_stalls(stalling):
    """Headers arrive, then the body stalls: the timeout is in the body read."""
    source = HttpObjectSource(stalling, socket_timeout=0.05)
    with pytest.raises(DownloadDeadlineExceeded) as ei:
        source.read_bytes("current.json")
    assert isinstance(ei.value.__cause__, (TimeoutError, OSError))


def test_control_request_timeout_is_typed_when_headers_are_withheld(headerless):
    """No headers ever arrive: the timeout is in opening the response."""
    source = HttpObjectSource(headerless, socket_timeout=0.05)
    with pytest.raises(DownloadDeadlineExceeded) as ei:
        source.read_bytes("current.json")
    assert ei.value.__cause__ is not None


def test_open_stream_timeout_is_typed_when_headers_are_withheld(headerless):
    """The seam a stream-level translation cannot reach: no stream exists yet."""
    source = HttpObjectSource(headerless, socket_timeout=0.05)
    with pytest.raises(DownloadDeadlineExceeded) as ei:
        source.open_stream("snapshot.tar")
    assert ei.value.__cause__ is not None


@pytest.mark.parametrize(
    "call",
    [
        lambda src: src.read_bytes("current.json"),
        lambda src: src.open_stream("snapshot.tar"),
    ],
    ids=["read_bytes", "open_stream"],
)
def test_no_untyped_timeout_escapes_from_any_entry_point(headerless, call):
    source = HttpObjectSource(headerless, socket_timeout=0.05)
    try:
        call(source)
    except DownloadDeadlineExceeded:
        pass
    except BaseException as exc:  # pragma: no cover - the defect
        pytest.fail(f"untyped {type(exc).__module__}.{type(exc).__name__} escaped: {exc}")


def test_a_boot_over_a_headerless_source_falls_back_to_live(headerless, tmp_path):
    """End to end: the typed failure is what the runtime degrades on."""
    from property_core.snapshot.models import Readiness
    from property_core.snapshot.runtime import SnapshotRuntime
    from property_core.snapshot.store import SnapshotStore

    runtime = SnapshotRuntime(
        source=HttpObjectSource(headerless, socket_timeout=0.05),
        store=SnapshotStore(tmp_path))
    report = runtime.boot()
    assert report.readiness is Readiness.UNREADY
    assert report.fallback_to_live is True


# --- unrelated failures must NOT be relabelled as deadlines ----------------

def test_a_connection_refusal_is_not_reported_as_a_deadline(tmp_path):
    """Losing a connection-refused behind a deadline error is its own
    misdiagnosis, so the translation is narrow by design."""
    # Port 1 on loopback: refused immediately, not a timeout.
    source = HttpObjectSource("http://127.0.0.1:1", socket_timeout=5.0)
    with pytest.raises(Exception) as ei:
        source.read_bytes("current.json")
    assert not isinstance(ei.value, DownloadDeadlineExceeded), (
        "a refused connection was relabelled as a timeout"
    )


def test_an_http_error_status_is_not_reported_as_a_deadline():
    """HTTPError subclasses URLError; a 504 is the server's answer, not ours."""
    import urllib.error

    from property_core.snapshot.source import _is_timeout

    gateway_timeout = urllib.error.HTTPError(
        "http://x.invalid", 504, "Gateway Timeout", {}, None)
    assert _is_timeout(gateway_timeout) is False


def test_a_connect_phase_timeout_wrapped_in_urlerror_is_recognised():
    """urllib wraps a connect timeout in URLError; the reason must be unwrapped."""
    import urllib.error

    from property_core.snapshot.source import _is_timeout

    assert _is_timeout(urllib.error.URLError(TimeoutError("timed out"))) is True
    assert _is_timeout(urllib.error.URLError(ConnectionRefusedError())) is False
