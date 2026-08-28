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

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tools.ppd_snapshot.release_check import ReleaseObservation
from tools.ppd_snapshot.source_receipt import (
    SourceMismatch,
    load_receipt,
    verify_source,
    write_receipt,
)

NOW = datetime(2026, 8, 28, 9, 0, tzinfo=timezone.utc)
BODY = b"a,b,c\n" * 40


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
                            now=NOW)
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
                      tmp_path / "receipt.json", now=NOW)
    assert not (tmp_path / "receipt.json").exists()


def test_writing_a_receipt_refuses_a_release_that_declares_no_length(
        csv_path, tmp_path):
    with pytest.raises(SourceMismatch, match="no Content-Length"):
        write_receipt(csv_path, observation(content_length=None),
                      tmp_path / "receipt.json", now=NOW)


def test_verification_accepts_a_file_that_still_matches(csv_path, tmp_path):
    receipt = write_receipt(csv_path, observation(), tmp_path / "receipt.json",
                            now=NOW)
    verify_source(csv_path, receipt, observation())


def test_verification_refuses_a_file_that_changed_since_the_receipt(
        csv_path, tmp_path):
    receipt = write_receipt(csv_path, observation(), tmp_path / "receipt.json",
                            now=NOW)
    csv_path.write_bytes(BODY + b"one more row\n")
    with pytest.raises(SourceMismatch, match="bytes"):
        verify_source(csv_path, receipt, observation())


def test_verification_refuses_a_file_edited_without_changing_its_length(
        csv_path, tmp_path):
    receipt = write_receipt(csv_path, observation(), tmp_path / "receipt.json",
                            now=NOW)
    edited = bytearray(BODY)
    edited[0] = ord("z")
    csv_path.write_bytes(bytes(edited))
    with pytest.raises(SourceMismatch, match="sha256"):
        verify_source(csv_path, receipt, observation())


def test_verification_refuses_when_the_release_has_moved_on(csv_path, tmp_path):
    receipt = write_receipt(csv_path, observation(), tmp_path / "receipt.json",
                            now=NOW)
    with pytest.raises(SourceMismatch, match="ETag"):
        verify_source(csv_path, receipt, observation(etag='"a-newer-etag"'))


def test_verification_refuses_when_the_publication_date_has_moved(
        csv_path, tmp_path):
    receipt = write_receipt(csv_path, observation(), tmp_path / "receipt.json",
                            now=NOW)
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
                            now=NOW)
    assert load_receipt(tmp_path / "receipt.json") == written
