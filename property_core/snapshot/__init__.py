"""Snapshot boot runtime.

Fetches, verifies and activates a PPD snapshot bundle at process start. It does
NOT query the snapshot, route any request, or change any response: reading data
from an activated snapshot is a later piece of work.

Disabled by default -- see `property_core.config.ppd_snapshot_enabled`.
"""

from __future__ import annotations

from property_core.snapshot.archive import ExtractionLimits, ExtractionStats, safe_extract
from property_core.snapshot.errors import (
    ArchiveRejected,
    BundleVerificationError,
    DownloadDeadlineExceeded,
    InsufficientDiskSpaceError,
    SnapshotExtraMissingError,
)
from property_core.snapshot.fetch import DownloadResult, download_verified
from property_core.snapshot.lock import LockTimeout, single_flight
from property_core.snapshot.models import (
    BootReport,
    Readiness,
    SnapshotManifest,
    VerificationRecord,
)
from property_core.snapshot.source import (
    HttpObjectSource,
    LocalDirectorySource,
    ObjectSource,
)
from property_core.snapshot.store import SnapshotStore

__all__ = [
    "ArchiveRejected",
    "BootReport",
    "BundleVerificationError",
    "DownloadDeadlineExceeded",
    "DownloadResult",
    "ExtractionLimits",
    "ExtractionStats",
    "HttpObjectSource",
    "InsufficientDiskSpaceError",
    "LocalDirectorySource",
    "LockTimeout",
    "ObjectSource",
    "Readiness",
    "SnapshotExtraMissingError",
    "SnapshotManifest",
    "SnapshotStore",
    "VerificationRecord",
    "download_verified",
    "safe_extract",
    "single_flight",
]
