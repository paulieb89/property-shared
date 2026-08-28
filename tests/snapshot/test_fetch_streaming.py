"""Streamed download with incremental SHA-256. The bundle is never buffered."""

from __future__ import annotations

import hashlib

import pytest

from property_core.snapshot.errors import BundleVerificationError
from property_core.snapshot.fetch import download_verified
from property_core.snapshot.models import SnapshotManifest


class RecordingSource:
    """An object source that records the largest single read it was asked for."""

    def __init__(self, blob: bytes, *, truncate_at: int | None = None,
                 corrupt: bool = False):
        self.blob = blob
        self.truncate_at = truncate_at
        self.corrupt = corrupt
        self.max_chunk = 0
        self.declared_length = len(blob)

    def read_bytes(self, name, *, max_bytes=None):
        return self.blob

    def open_stream(self, name):
        blob = self.blob
        if self.corrupt:
            mid = len(blob) // 2
            blob = blob[:mid] + bytes(b ^ 0xFF for b in blob[mid:mid + 8]) + blob[mid + 8:]
        limit = self.truncate_at if self.truncate_at is not None else len(blob)
        source = self

        class _Stream:
            def __init__(self):
                self.pos = 0
                self.declared_length = source.declared_length

            def read(self, n):
                source.max_chunk = max(source.max_chunk, n)
                if self.pos >= limit:
                    return b""
                out = blob[self.pos:min(self.pos + n, limit)]
                self.pos += len(out)
                return out

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        return _Stream()


def _manifest(blob: bytes, **over) -> SnapshotManifest:
    payload = {
        "snapshot_version": "v1", "bundle_object": "b.tar",
        "bundle_sha256": hashlib.sha256(blob).hexdigest(),
        "bundle_bytes": len(blob), "parquet_files": 1, "rows": 3,
    }
    payload.update(over)
    return SnapshotManifest(**payload)


def test_download_streams_and_verifies(tmp_path, bundle):
    dest = tmp_path / "b.tar"
    result = download_verified(RecordingSource(bundle), _manifest(bundle), dest)
    assert result.bytes_written == len(bundle)
    assert result.sha256 == hashlib.sha256(bundle).hexdigest()
    assert dest.read_bytes() == bundle


def test_reads_are_bounded_by_the_chunk_size(tmp_path, bundle):
    """Bounded memory: the runtime must never ask for the whole body at once."""
    src = RecordingSource(bundle)
    download_verified(src, _manifest(bundle), tmp_path / "b.tar", chunk_size=16)
    assert src.max_chunk <= 16, f"asked for {src.max_chunk} bytes in one read"


def test_checksum_mismatch_is_rejected_and_the_temp_file_removed(tmp_path, bundle):
    dest = tmp_path / "b.tar"
    with pytest.raises(BundleVerificationError) as ei:
        download_verified(RecordingSource(bundle, corrupt=True), _manifest(bundle), dest)
    assert "sha256" in str(ei.value).lower()
    assert not dest.exists(), "a rejected download must leave no partial file"


def test_truncated_transfer_is_rejected(tmp_path, bundle):
    dest = tmp_path / "b.tar"
    with pytest.raises(BundleVerificationError) as ei:
        download_verified(RecordingSource(bundle, truncate_at=len(bundle) // 2),
                          _manifest(bundle), dest)
    assert "length" in str(ei.value).lower() or "short" in str(ei.value).lower()
    assert not dest.exists()


def test_declared_length_mismatch_is_rejected(tmp_path, bundle):
    with pytest.raises(BundleVerificationError):
        download_verified(RecordingSource(bundle),
                          _manifest(bundle, bundle_bytes=len(bundle) + 10),
                          tmp_path / "b.tar")


def test_oversize_bundle_is_aborted_during_streaming(tmp_path, bundle):
    """The cap must stop the transfer, not merely reject it afterwards."""
    src = RecordingSource(bundle)
    with pytest.raises(BundleVerificationError) as ei:
        download_verified(src, _manifest(bundle), tmp_path / "b.tar",
                          max_bytes=8, chunk_size=4)
    assert "max" in str(ei.value).lower() or "too large" in str(ei.value).lower()


def test_manifest_rejects_a_missing_required_field():
    with pytest.raises(Exception):
        SnapshotManifest(snapshot_version="v1", bundle_object="b.tar")


def test_manifest_rejects_a_malformed_digest(bundle):
    with pytest.raises(Exception):
        _manifest(bundle, bundle_sha256="not-a-digest")
