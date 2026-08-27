"""Caps and deadlines are runtime behaviour, not documentation.

Every value here is also published in the governing specification section 4.
The tests assert the *behaviour*, and one test asserts the constants match the
spec, so the two cannot drift apart again.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pytest

from property_core.snapshot.archive import ExtractionLimits
from property_core.snapshot.errors import (
    BundleVerificationError,
    DownloadDeadlineExceeded,
    InsufficientDiskSpaceError,
)
from property_core.snapshot.fetch import (
    DEFAULT_MAX_BUNDLE_BYTES,
    DEFAULT_STALL_SECONDS,
    DEFAULT_TOTAL_DEADLINE_SECONDS,
    DISK_HEADROOM_MULTIPLIER,
    download_verified,
    preflight_disk_space,
)
from property_core.snapshot.models import SnapshotManifest
from property_core.snapshot.source import DEFAULT_TIMEOUT


class Stream:
    """A controllable byte stream: per-read delay, optional early stop."""

    def __init__(self, blob: bytes, *, delay: float = 0.0, chunk: int = 8):
        self.blob, self.delay, self.chunk = blob, delay, chunk
        self.pos = 0
        self.declared_length = len(blob)

    def read(self, n):
        if self.delay:
            time.sleep(self.delay)
        size = min(n, self.chunk)
        out = self.blob[self.pos:self.pos + size]
        self.pos += len(out)
        return out

    def __enter__(self):
        return self

    def __exit__(self, *e):
        return False


class Source:
    def __init__(self, blob: bytes, **kw):
        self.blob, self.kw = blob, kw

    def read_bytes(self, name, *, max_bytes=None):
        return self.blob

    def open_stream(self, name):
        return Stream(self.blob, **self.kw)


def _manifest(blob: bytes, **over) -> SnapshotManifest:
    payload = {"snapshot_version": "v1", "bundle_object": "b.tar",
               "bundle_sha256": hashlib.sha256(blob).hexdigest(),
               "bundle_bytes": len(blob), "parquet_files": 1, "rows": 1}
    payload.update(over)
    return SnapshotManifest(**payload)


# --- the published constants ----------------------------------------------

def test_constants_match_the_governing_specification():
    """Section 4 publishes these. Drift between spec and code is what this
    reconciliation existed to fix, so pin them."""
    assert DEFAULT_MAX_BUNDLE_BYTES == 1 * 1024 ** 3          # 4.1: 1 GiB
    assert DEFAULT_TOTAL_DEADLINE_SECONDS == 300.0            # 4.1: 300 s
    assert DEFAULT_STALL_SECONDS == 60.0                      # 4.1: 60 s
    assert DEFAULT_TIMEOUT == 10.0                            # 4.1: 10 s connect
    assert DISK_HEADROOM_MULTIPLIER == 2.5                    # 4.7: bundle * 2.5
    limits = ExtractionLimits()
    assert limits.max_members == 5_000                        # 4.3
    assert limits.max_total_bytes == 2 * 1024 ** 3            # 4.3
    assert limits.max_member_bytes == 2 * 1024 ** 3           # 4.3


# --- disk preflight --------------------------------------------------------

def test_preflight_refuses_a_bundle_that_cannot_fit(tmp_path, monkeypatch):
    import shutil as shutil_mod

    from property_core.snapshot import fetch as fetch_mod

    monkeypatch.setattr(
        fetch_mod.shutil, "disk_usage",
        lambda p: shutil_mod._ntuple_diskusage(total=100, used=99, free=1))
    with pytest.raises(InsufficientDiskSpaceError) as ei:
        preflight_disk_space(tmp_path / "b.tar", bundle_bytes=1000)
    payload = ei.value.to_dict()
    assert payload["error"] == "snapshot_insufficient_disk"
    assert payload["required_bytes"] == 2500          # 1000 * 2.5
    assert payload["available_bytes"] == 1


def test_preflight_allows_a_bundle_that_fits(tmp_path):
    preflight_disk_space(tmp_path / "b.tar", bundle_bytes=1)  # must not raise


def test_the_transfer_does_not_start_when_disk_is_short(tmp_path, monkeypatch):
    """Checked BEFORE any bytes move: a full filesystem takes the live path down."""
    import shutil as shutil_mod

    from property_core.snapshot import fetch as fetch_mod

    blob = b"x" * 64
    source = Source(blob)
    monkeypatch.setattr(
        fetch_mod.shutil, "disk_usage",
        lambda p: shutil_mod._ntuple_diskusage(total=100, used=100, free=0))
    dest = tmp_path / "b.tar"
    with pytest.raises(InsufficientDiskSpaceError):
        download_verified(source, _manifest(blob), dest)
    assert not dest.exists(), "no partial file may be written"


def test_preflight_can_be_disabled_for_tests_only(tmp_path):
    blob = b"y" * 32
    result = download_verified(Source(blob), _manifest(blob), tmp_path / "b.tar",
                               check_disk=False)
    assert result.bytes_written == 32


# --- deadlines -------------------------------------------------------------

def test_a_stalled_read_is_aborted(tmp_path):
    """A read that returns nothing for longer than the stall budget."""
    blob = b"z" * 64
    with pytest.raises(DownloadDeadlineExceeded) as ei:
        download_verified(Source(blob, delay=0.15, chunk=8), _manifest(blob),
                          tmp_path / "b.tar", stall_seconds=0.02, check_disk=False)
    assert "stall" in str(ei.value).lower()
    assert not (tmp_path / "b.tar").exists()


def test_a_transfer_exceeding_its_total_budget_is_aborted(tmp_path):
    """Slow but progressing still has to finish inside the whole-transfer budget."""
    blob = b"w" * 400
    with pytest.raises(DownloadDeadlineExceeded) as ei:
        download_verified(Source(blob, delay=0.01, chunk=8), _manifest(blob),
                          tmp_path / "b.tar", total_deadline=0.05,
                          stall_seconds=5.0, check_disk=False)
    assert "budget" in str(ei.value).lower()
    assert not (tmp_path / "b.tar").exists()


def test_a_prompt_transfer_is_unaffected_by_the_deadlines(tmp_path):
    blob = b"q" * 128
    result = download_verified(Source(blob), _manifest(blob), tmp_path / "b.tar",
                               total_deadline=30.0, stall_seconds=5.0,
                               check_disk=False)
    assert result.bytes_written == 128


def test_the_deadline_error_is_typed_and_retryable():
    err = DownloadDeadlineExceeded("stalled")
    payload = err.to_dict()
    assert payload["error"] == "snapshot_download_deadline"
    assert payload["retryable"] is True


# --- the bundle cap --------------------------------------------------------

def test_a_manifest_above_the_bundle_cap_is_refused_before_transfer(tmp_path):
    blob = b"a" * 16
    with pytest.raises(BundleVerificationError) as ei:
        download_verified(Source(blob), _manifest(blob, bundle_bytes=DEFAULT_MAX_BUNDLE_BYTES + 1),
                          tmp_path / "b.tar", check_disk=False)
    assert "maximum" in str(ei.value).lower()
    assert not (tmp_path / "b.tar").exists()


# --- the record PR 4 will route from --------------------------------------

def test_the_record_persists_the_validated_manifest_metadata(tmp_path):
    """Routing must be able to answer coverage questions offline, from the
    materialized snapshot alone -- not by re-fetching a manifest that may have
    rotated since."""
    import io
    import json
    import tarfile

    from property_core.snapshot.runtime import SnapshotRuntime
    from property_core.snapshot.store import SnapshotStore

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        ti = tarfile.TarInfo("data.parquet"); ti.size = 4
        tar.addfile(ti, io.BytesIO(b"PAR1"))
    blob = buf.getvalue()

    manifest = {
        "snapshot_version": "v1", "bundle_object": "s.tar",
        "bundle_sha256": hashlib.sha256(blob).hexdigest(),
        "bundle_bytes": len(blob), "parquet_files": 1, "rows": 42,
        "coverage_from": "2016-01-01", "coverage_to": "2026-06-30",
        "provisional_from": "2026-04-01", "layout": "year",
        "duckdb_version": "v1.5.5",
    }
    objects = {
        "current.json": json.dumps({"current_manifest": "m.json"}).encode(),
        "m.json": json.dumps(manifest).encode(),
        "s.tar": blob,
    }

    class Src:
        def read_bytes(self, name, *, max_bytes=None):
            return objects[name]

        def open_stream(self, name):
            return Stream(objects[name], chunk=1024)

    SnapshotRuntime(source=Src(), store=SnapshotStore(tmp_path)).boot()
    record = SnapshotStore(tmp_path).verified_record("v1")

    assert record is not None
    assert record.coverage_from == "2016-01-01"
    assert record.coverage_to == "2026-06-30"
    assert record.provisional_from == "2026-04-01"
    assert record.layout == "year"
    assert record.duckdb_version == "v1.5.5"
    assert record.rows == 42
    assert record.bundle_object == "s.tar"
    # And it says what was actually established.
    assert record.verification == "structural"


def test_readiness_is_structural_not_queryable():
    """PR 3 must not claim the snapshot opens; PR 4 establishes that."""
    import inspect

    from property_core.snapshot import runtime as mod

    doc = (mod.__doc__ or "").lower()
    assert "structurally verified" in doc
    assert "not queryable" in doc or "not a claim" in doc or "weaker claim" in doc
    src = inspect.getsource(mod)
    for banned in ("duckdb.connect", "read_parquet", "SELECT "):
        assert banned not in src


@pytest.mark.parametrize("bad", ["../m.json", "a/m.json", "", "  ", ".", ".."])
def test_the_current_manifest_pointer_is_validated(tmp_path, bad):
    """current.json names an object we then fetch, so it gets the same
    single-component treatment as every other externally supplied name."""
    import json

    from property_core.snapshot.models import Readiness
    from property_core.snapshot.runtime import SnapshotRuntime
    from property_core.snapshot.store import SnapshotStore

    class Src:
        def read_bytes(self, name, *, max_bytes=None):
            if name == "current.json":
                return json.dumps({"current_manifest": bad}).encode()
            raise AssertionError(f"fetched {name!r} despite an invalid pointer")

        def open_stream(self, name):
            raise AssertionError("streamed despite an invalid pointer")

    report = SnapshotRuntime(source=Src(), store=SnapshotStore(tmp_path)).boot()
    assert report.readiness is Readiness.UNREADY
    assert report.fallback_to_live is True
