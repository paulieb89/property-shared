"""Shared fixtures for the snapshot runtime tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tests.snapshot.archive_fixtures import good_bundle_bytes


@pytest.fixture
def bundle() -> bytes:
    return good_bundle_bytes()


@pytest.fixture
def manifest_for():
    def _make(blob: bytes, version: str = "v20260101T000000Z", **over):
        payload = {
            "snapshot_version": version,
            "bundle_object": f"snapshot-{version}.tar",
            "bundle_sha256": hashlib.sha256(blob).hexdigest(),
            "bundle_bytes": len(blob),
            "parquet_files": 1,
            "rows": 3,
        }
        payload.update(over)
        return payload
    return _make


@pytest.fixture
def store_root(tmp_path: Path) -> Path:
    return tmp_path / "snapshots"
