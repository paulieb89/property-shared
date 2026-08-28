"""Red-first tests binding the local CSV to the release it claims to be.

The defect this closes: a 131-byte stale CSV built cleanly while the release
record claimed 999,999,999 bytes under a new ETag, and the result booted READY.
Nothing compared the file with the release, so every downstream gate was
checking an artifact that was internally consistent and about the wrong data.

A receipt is the binding: it records the digest and length **computed from the
file** alongside the validators of the release it was fetched for, and the build
refuses unless the receipt, the file on disk and the latest observation all
still agree.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from tools.ppd_snapshot.release_check import ReleaseObservation
from tools.ppd_snapshot.source_receipt import (
    SourceMismatch,
    download_with_receipt,
    load_receipt,
    verify_source,
    write_receipt,
)

NOW = datetime(2026, 8, 28, 9, 0, tzinfo=timezone.utc)
BODY = b"a,b,c\n" * 40
BODY_SHA = hashlib.sha256(BODY).hexdigest()


def observation(**over) -> ReleaseObservation:
    fields = {"etag": '"an-etag"', "last_modified": "Tue, 28 Jul 2026 05:16:16 GMT",
              "content_length": len(BODY)}
    fields.update(over)
    return ReleaseObservation(**fields)


@pytest.fixture
def csv_path(tmp_path: Path) -> Path:
    path = tmp_path / "pp-complete.csv"
    path.write_bytes(BODY)
    return path


def test_a_receipt_records_the_digest_and_length_it_computed(csv_path, tmp_path):
    receipt = write_receipt(csv_path, observation(), tmp_path / "receipt.json",
                            expected_sha256=BODY_SHA, now=NOW)
    assert receipt.sha256 == hashlib.sha256(BODY).hexdigest()
    assert receipt.bytes == len(BODY)
    assert receipt.etag == '"an-etag"'
    assert json.loads((tmp_path / "receipt.json").read_text())["sha256"] == \
        receipt.sha256


def test_writing_a_receipt_refuses_a_file_the_release_says_is_a_different_size(
        csv_path, tmp_path):
    # The reproduction: a stale local file under a release that describes
    # something else entirely.
    with pytest.raises(SourceMismatch, match="999999999"):
        write_receipt(csv_path, observation(content_length=999_999_999),
                      tmp_path / "receipt.json", expected_sha256=BODY_SHA,
                      now=NOW)
    assert not (tmp_path / "receipt.json").exists()


def test_writing_a_receipt_refuses_a_release_that_declares_no_length(
        csv_path, tmp_path):
    with pytest.raises(SourceMismatch, match="no Content-Length"):
        write_receipt(csv_path, observation(content_length=None),
                      tmp_path / "receipt.json", expected_sha256=BODY_SHA,
                      now=NOW)


def test_verification_accepts_a_file_that_still_matches(csv_path, tmp_path):
    receipt = write_receipt(csv_path, observation(), tmp_path / "receipt.json",
                            expected_sha256=BODY_SHA, now=NOW)
    verify_source(csv_path, receipt, observation())


def test_verification_refuses_a_file_that_changed_since_the_receipt(
        csv_path, tmp_path):
    receipt = write_receipt(csv_path, observation(), tmp_path / "receipt.json",
                            expected_sha256=BODY_SHA, now=NOW)
    csv_path.write_bytes(BODY + b"one more row\n")
    with pytest.raises(SourceMismatch, match="bytes"):
        verify_source(csv_path, receipt, observation())


def test_verification_refuses_a_file_edited_without_changing_its_length(
        csv_path, tmp_path):
    receipt = write_receipt(csv_path, observation(), tmp_path / "receipt.json",
                            expected_sha256=BODY_SHA, now=NOW)
    edited = bytearray(BODY)
    edited[0] = ord("z")
    csv_path.write_bytes(bytes(edited))
    with pytest.raises(SourceMismatch, match="sha256"):
        verify_source(csv_path, receipt, observation())


def test_verification_refuses_when_the_release_has_moved_on(csv_path, tmp_path):
    receipt = write_receipt(csv_path, observation(), tmp_path / "receipt.json",
                            expected_sha256=BODY_SHA, now=NOW)
    with pytest.raises(SourceMismatch, match="ETag"):
        verify_source(csv_path, receipt, observation(etag='"a-newer-etag"'))


def test_verification_refuses_when_the_publication_date_has_moved(
        csv_path, tmp_path):
    receipt = write_receipt(csv_path, observation(), tmp_path / "receipt.json",
                            expected_sha256=BODY_SHA, now=NOW)
    with pytest.raises(SourceMismatch, match="Last-Modified"):
        verify_source(csv_path, receipt,
                      observation(last_modified="Fri, 28 Aug 2026 05:16:16 GMT"))


def test_a_missing_receipt_is_refused_rather_than_defaulted(tmp_path):
    with pytest.raises(SourceMismatch, match="no source receipt"):
        load_receipt(tmp_path / "absent.json")


def test_a_corrupt_receipt_is_refused(tmp_path):
    (tmp_path / "receipt.json").write_text("{not json")
    with pytest.raises(SourceMismatch):
        load_receipt(tmp_path / "receipt.json")


def test_a_receipt_round_trips(csv_path, tmp_path):
    written = write_receipt(csv_path, observation(), tmp_path / "receipt.json",
                            expected_sha256=BODY_SHA, now=NOW)
    assert load_receipt(tmp_path / "receipt.json") == written


# -- a receipt must be grounded in independent download evidence ------------

def test_minting_a_receipt_requires_the_digest_recorded_at_download(
        csv_path, tmp_path):
    """Same length, any ETag: without a recorded digest the receipt binds
    whatever happens to be on disk to whatever the release claims to be."""
    with pytest.raises(SourceMismatch, match="sha256"):
        write_receipt(csv_path, observation(), tmp_path / "receipt.json",
                      expected_sha256="0" * 64, now=NOW)
    assert not (tmp_path / "receipt.json").exists()


def test_a_receipt_records_where_its_digest_came_from(csv_path, tmp_path):
    receipt = write_receipt(csv_path, observation(), tmp_path / "receipt.json",
                            expected_sha256=BODY_SHA, now=NOW)
    assert receipt.evidence == "recorded-checksum"


def test_swapping_the_file_for_same_length_bytes_is_refused(csv_path, tmp_path):
    swapped = bytearray(BODY)
    swapped[0] = ord("z")
    csv_path.write_bytes(bytes(swapped))
    with pytest.raises(SourceMismatch, match="sha256"):
        write_receipt(csv_path, observation(), tmp_path / "receipt.json",
                      expected_sha256=BODY_SHA, now=NOW)


def test_a_streamed_download_mints_its_own_receipt(tmp_path):
    """The intended way to obtain a receipt: digest the bytes as they arrive,
    from the same response the validators come from."""
    served = _serve(BODY, {"ETag": '"served-etag"',
                           "Last-Modified": "Tue, 28 Jul 2026 05:16:16 GMT",
                           "Content-Length": str(len(BODY))})
    with served as url:
        receipt = download_with_receipt(url, tmp_path / "pp.csv",
                                        tmp_path / "receipt.json", now=NOW)
    assert (tmp_path / "pp.csv").read_bytes() == BODY
    assert receipt.sha256 == BODY_SHA
    assert receipt.etag == '"served-etag"'
    assert receipt.evidence == "streamed-download"


def test_a_download_that_does_not_match_its_declared_length_is_refused(tmp_path):
    served = _serve(BODY, {"ETag": '"served-etag"',
                           "Last-Modified": "Tue, 28 Jul 2026 05:16:16 GMT",
                           "Content-Length": str(len(BODY) + 10)})
    with served as url:
        with pytest.raises(SourceMismatch, match="Content-Length"):
            download_with_receipt(url, tmp_path / "pp.csv",
                                  tmp_path / "receipt.json", now=NOW)
    assert not (tmp_path / "pp.csv").exists()
    assert not (tmp_path / "receipt.json").exists()


@contextlib.contextmanager
def _serve(body: bytes, headers: dict, *, drop: bool = False):
    """A loopback HTTP server. Local only -- no external host is contacted.

    `drop` closes the connection after the body, modelling a transfer that dies
    part way through rather than one that merely disagrees about its length.
    """
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):  # noqa: N802 - stdlib naming
            self.send_response(200)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)
            if drop:
                self.close_connection = True
                self.wfile.flush()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/pp-complete.csv"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# -- a failed refresh must not destroy the release already held -------------

def _seed(tmp_path: Path) -> tuple[Path, Path, bytes, bytes]:
    """A known-good CSV and its receipt, as a previous run would leave them."""
    csv_path = tmp_path / "pp.csv"
    csv_path.write_bytes(BODY)
    receipt_path = tmp_path / "receipt.json"
    write_receipt(csv_path, observation(), receipt_path,
                  expected_sha256=BODY_SHA, now=NOW)
    return csv_path, receipt_path, csv_path.read_bytes(), receipt_path.read_bytes()


def test_a_download_that_disagrees_with_its_length_preserves_what_was_held(
        tmp_path):
    csv_path, receipt_path, csv_before, receipt_before = _seed(tmp_path)
    served = _serve(b"new but truncated\n", {
        "ETag": '"newer-etag"',
        "Last-Modified": "Fri, 28 Aug 2026 05:16:16 GMT",
        "Content-Length": "999999"})
    with served as url:
        with pytest.raises(SourceMismatch):
            download_with_receipt(url, csv_path, receipt_path, now=NOW)

    assert csv_path.read_bytes() == csv_before
    assert receipt_path.read_bytes() == receipt_before


def test_a_download_dropped_mid_stream_preserves_what_was_held(tmp_path):
    csv_path, receipt_path, csv_before, receipt_before = _seed(tmp_path)
    served = _serve(b"x" * 32, {"ETag": '"newer-etag"',
                                "Last-Modified": "Fri, 28 Aug 2026 05:16:16 GMT",
                                "Content-Length": "100000"}, drop=True)
    with served as url:
        with pytest.raises(Exception):
            download_with_receipt(url, csv_path, receipt_path, now=NOW)

    assert csv_path.read_bytes() == csv_before
    assert receipt_path.read_bytes() == receipt_before


def test_a_failed_download_leaves_no_partial_file_behind(tmp_path):
    csv_path, receipt_path, _, _ = _seed(tmp_path)
    served = _serve(b"short", {"ETag": '"newer-etag"',
                               "Last-Modified": "Fri, 28 Aug 2026 05:16:16 GMT",
                               "Content-Length": "999999"})
    with served as url:
        with pytest.raises(SourceMismatch):
            download_with_receipt(url, csv_path, receipt_path, now=NOW)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["pp.csv", "receipt.json"]


def test_a_successful_download_replaces_both_the_file_and_its_receipt(tmp_path):
    csv_path, receipt_path, _, _ = _seed(tmp_path)
    fresh = b"newer,release,rows\n" * 3
    served = _serve(fresh, {"ETag": '"newer-etag"',
                            "Last-Modified": "Fri, 28 Aug 2026 05:16:16 GMT",
                            "Content-Length": str(len(fresh))})
    with served as url:
        receipt = download_with_receipt(url, csv_path, receipt_path, now=NOW)

    assert csv_path.read_bytes() == fresh
    assert receipt.sha256 == hashlib.sha256(fresh).hexdigest()
    assert load_receipt(receipt_path).etag == '"newer-etag"'
    assert sorted(p.name for p in tmp_path.iterdir()) == ["pp.csv", "receipt.json"]


def test_a_streamed_receipt_names_the_destination_not_the_temporary_file(
        tmp_path):
    fresh = b"newer,release\n"
    served = _serve(fresh, {"ETag": '"newer-etag"',
                            "Last-Modified": "Fri, 28 Aug 2026 05:16:16 GMT",
                            "Content-Length": str(len(fresh))})
    with served as url:
        download_with_receipt(url, tmp_path / "pp-complete.csv",
                              tmp_path / "receipt.json", now=NOW)
    assert load_receipt(tmp_path / "receipt.json").file == "pp-complete.csv"


def test_a_streamed_download_digests_the_file_only_once(tmp_path, monkeypatch):
    """Re-reading to build the receipt would mean a second pass over 5.5 GB."""
    from tools.ppd_snapshot import source_receipt as sr

    calls = []
    real = sr.digest_file
    monkeypatch.setattr(sr, "digest_file",
                        lambda path: (calls.append(path), real(path))[1])

    fresh = b"newer,release\n"
    served = _serve(fresh, {"ETag": '"newer-etag"',
                            "Last-Modified": "Fri, 28 Aug 2026 05:16:16 GMT",
                            "Content-Length": str(len(fresh))})
    with served as url:
        download_with_receipt(url, tmp_path / "pp.csv",
                              tmp_path / "receipt.json", now=NOW)
    assert calls == []
