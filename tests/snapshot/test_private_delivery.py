"""Private-delivery boundary tests; loopback only, never Tigris or PPD."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import importlib.util
import subprocess
import sys
import time

from property_core.snapshot.errors import DownloadDeadlineExceeded

import pytest

from property_core.snapshot.bootstrap import _build_source
from property_core.snapshot.s3_source import SnapshotSourceError, TigrisObjectSource

requires_sdk = pytest.mark.skipif(importlib.util.find_spec("botocore") is None,
                                  reason="private delivery needs the snapshot extra")

@contextmanager
def object_server(body=b'{"current_manifest":"manifest-v1.json"}', *, redirect=None,
                  delay=0, status=200):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append((self.path, dict(self.headers)))
            if redirect is not None:
                self.send_response(302)
                self.send_header("Location", redirect)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            time.sleep(delay)
            if status != 200:
                self.send_response(status)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except BrokenPipeError:
                pass  # a timeout test deliberately closed the client

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", calls
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


@requires_sdk
def test_signed_control_get_reads_through_http_boundary():
    with object_server() as (endpoint, calls):
        source = TigrisObjectSource(
            "ppd-test", access_key="test-key", secret_key="test-secret",
            endpoint=endpoint,
        )
        assert source.read_bytes("current.json") == b'{"current_manifest":"manifest-v1.json"}'
    assert len(calls) == 1
    path, headers = calls[0]
    assert path == "/ppd-test/ppd/current.json"
    assert headers["Authorization"].startswith("AWS4-HMAC-SHA256 ")
    assert "Credential=test-key/" in headers["Authorization"]
    assert "/auto/s3/aws4_request" in headers["Authorization"]
    assert "test-secret" not in str(calls)
    assert "?" not in path  # credentials/signatures are never URL parameters


@requires_sdk
def test_boot_selects_private_source_without_credential_discovery(monkeypatch):
    monkeypatch.delenv("PPD_SNAPSHOT_URL", raising=False)
    monkeypatch.delenv("PPD_SNAPSHOT_DIR", raising=False)
    monkeypatch.setenv("PPD_SNAPSHOT_S3_BUCKET", "ppd-test")
    monkeypatch.setenv("PPD_SNAPSHOT_S3_ACCESS_KEY_ID", "test-key")
    monkeypatch.setenv("PPD_SNAPSHOT_S3_SECRET_ACCESS_KEY", "test-secret")
    source = _build_source()
    assert isinstance(source, TigrisObjectSource)
    assert source.base_url == "https://t3.storage.dev/ppd-test/ppd"


@requires_sdk
def test_boot_treats_blank_prefix_as_unset(monkeypatch):
    monkeypatch.delenv("PPD_SNAPSHOT_URL", raising=False)
    monkeypatch.delenv("PPD_SNAPSHOT_DIR", raising=False)
    monkeypatch.setenv("PPD_SNAPSHOT_S3_BUCKET", "ppd-test")
    monkeypatch.setenv("PPD_SNAPSHOT_S3_ACCESS_KEY_ID", "test-key")
    monkeypatch.setenv("PPD_SNAPSHOT_S3_SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.setenv("PPD_SNAPSHOT_S3_PREFIX", "")
    source = _build_source()
    assert isinstance(source, TigrisObjectSource)
    assert source.base_url == "https://t3.storage.dev/ppd-test/ppd"


@pytest.mark.parametrize("name", ["../secret", "/secret", "x/y", "x?token=y", "", "x#frag"])
@requires_sdk
def test_manifest_names_cannot_escape_signed_source(name):
    with object_server() as (endpoint, calls):
        source = TigrisObjectSource("ppd-test", access_key="test-key",
                                    secret_key="test-secret", endpoint=endpoint)
        with pytest.raises(SnapshotSourceError):
            source.read_bytes(name)
    assert calls == []


@requires_sdk
def test_redirect_never_forwards_signed_credentials():
    with object_server() as (target, target_calls):
        with object_server(redirect=target + "/stolen") as (endpoint, calls):
            source = TigrisObjectSource("ppd-test", access_key="test-key",
                                        secret_key="test-secret", endpoint=endpoint)
            with pytest.raises(SnapshotSourceError, match="credentials not forwarded"):
                source.read_bytes("current.json")
    assert len(calls) == 1
    assert target_calls == []


@requires_sdk
def test_bundle_stream_is_chunked_and_exposes_length():
    payload = b"01234567" * 131072
    with object_server(body=payload) as (endpoint, calls):
        source = TigrisObjectSource("ppd-test", access_key="test-key",
                                    secret_key="test-secret", endpoint=endpoint)
        with source.open_stream("snapshot-v1.tar.zst") as stream:
            assert stream.declared_length == len(payload)
            chunks = []
            while chunk := stream.read(16384):
                assert len(chunk) <= 16384
                chunks.append(chunk)
    assert b"".join(chunks) == payload
    assert len(calls) == 1


@requires_sdk
@pytest.mark.parametrize("method", ["read_bytes", "open_stream"])
def test_signed_header_timeout_is_typed_and_not_retried(method):
    with object_server(delay=0.2) as (endpoint, calls):
        source = TigrisObjectSource("ppd-test", access_key="test-key",
                                    secret_key="test-secret", endpoint=endpoint,
                                    socket_timeout=0.04)
        with pytest.raises(DownloadDeadlineExceeded) as caught:
            getattr(source, method)("current.json")
    assert len(calls) == 1
    assert "test-key" not in str(caught.value)
    assert "test-secret" not in str(caught.value)


@requires_sdk
@pytest.mark.parametrize("method", ["read_bytes", "open_stream"])
def test_signed_http_error_is_typed_and_preserves_cause(method):
    import urllib.error

    with object_server(status=403) as (endpoint, calls):
        source = TigrisObjectSource("ppd-test", access_key="test-key",
                                    secret_key="test-secret", endpoint=endpoint)
        with pytest.raises(SnapshotSourceError) as caught:
            getattr(source, method)("current.json")
    assert len(calls) == 1
    assert "403" in str(caught.value)
    assert isinstance(caught.value.__cause__, urllib.error.HTTPError)
    assert caught.value.__cause__.code == 403


@requires_sdk
def test_control_body_has_the_existing_size_limit():
    with object_server(body=b"123456789") as (endpoint, calls):
        source = TigrisObjectSource("ppd-test", access_key="test-key",
                                    secret_key="test-secret", endpoint=endpoint)
        with pytest.raises(ValueError, match="exceeds 8 bytes"):
            source.read_bytes("current.json", max_bytes=8)
    assert len(calls) == 1


@pytest.mark.parametrize("missing", ["PPD_SNAPSHOT_S3_ACCESS_KEY_ID",
                                     "PPD_SNAPSHOT_S3_SECRET_ACCESS_KEY"])
def test_missing_explicit_credentials_do_not_fall_back_to_aws_environment(monkeypatch, missing):
    for name in ("PPD_SNAPSHOT_DIR", "PPD_SNAPSHOT_URL", missing):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PPD_SNAPSHOT_S3_BUCKET", "ppd-test")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "ambient-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "ambient-secret")
    with pytest.raises(SnapshotSourceError, match="access key and secret are required"):
        _build_source()


def test_ambiguous_source_configuration_is_refused(monkeypatch):
    monkeypatch.setenv("PPD_SNAPSHOT_URL", "https://example.invalid")
    monkeypatch.setenv("PPD_SNAPSHOT_S3_BUCKET", "ppd-test")
    with pytest.raises(RuntimeError, match="exactly one"):
        _build_source()


def test_dir_and_url_together_keeps_legacy_directory_precedence(monkeypatch, tmp_path):
    from property_core.snapshot.source import LocalDirectorySource

    monkeypatch.delenv("PPD_SNAPSHOT_S3_BUCKET", raising=False)
    monkeypatch.setenv("PPD_SNAPSHOT_DIR", str(tmp_path))
    monkeypatch.setenv("PPD_SNAPSHOT_URL", "https://example.invalid")
    source = _build_source()
    assert isinstance(source, LocalDirectorySource)
    assert source.root == tmp_path


def test_dir_and_bucket_together_is_refused(monkeypatch, tmp_path):
    monkeypatch.delenv("PPD_SNAPSHOT_URL", raising=False)
    monkeypatch.setenv("PPD_SNAPSHOT_DIR", str(tmp_path))
    monkeypatch.setenv("PPD_SNAPSHOT_S3_BUCKET", "ppd-test")
    with pytest.raises(RuntimeError, match="cannot be combined"):
        _build_source()


def test_no_sdk_installed_is_actionable_and_flag_off_is_inert():
    code = '''
import importlib.abc, sys, os, socket
class BlockSDK(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname == "botocore" or fullname.startswith("botocore."):
            raise ModuleNotFoundError("blocked botocore")
sys.meta_path.insert(0, BlockSDK())
try:
    import botocore
except ModuleNotFoundError:
    pass
else:
    raise AssertionError("blocker not armed")
from property_core.snapshot.s3_source import TigrisObjectSource
from property_core.snapshot.errors import SnapshotExtraMissingError
try:
    TigrisObjectSource("ppd-test", access_key="test-key", secret_key="test-secret")
except SnapshotExtraMissingError as exc:
    assert exc.code == "snapshot_extra_missing"
    assert exc.package == "botocore"
else:
    raise AssertionError("missing SDK accepted")
from property_core.snapshot.bootstrap import boot_once, snapshot_status
os.environ["PPD_SNAPSHOT_ENABLED"] = "0"
def no_network(*args, **kwargs):
    raise AssertionError("network attempted with flag off")
socket.socket = no_network
boot_once()
assert snapshot_status()["routable"] is False
assert not any(n == "botocore" or n.startswith("botocore.") for n in sys.modules)
'''
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_redirect_closes_the_rejected_response():
    import io
    from property_core.snapshot.s3_source import _NoRedirect
    body = io.BytesIO(b"redirect response")
    with pytest.raises(SnapshotSourceError):
        _NoRedirect().redirect_request(None, body, 302, "Found", {}, "https://other.invalid")
    assert body.closed


def test_public_source_and_error_are_exported():
    import property_core.snapshot as snapshot
    for name, expected in (("TigrisObjectSource", TigrisObjectSource),
                           ("SnapshotSourceError", SnapshotSourceError)):
        assert name in snapshot.__all__
        assert getattr(snapshot, name) is expected
