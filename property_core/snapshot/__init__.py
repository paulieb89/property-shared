"""Snapshot boot runtime and query adapter.

Two layers with deliberately different claims:

* the **boot runtime** fetches, verifies and activates a bundle at process
  start, establishing *structural* facts only -- digest, member safety, file
  inventory. It never opens the snapshot;
* the **adapter** turns that into a routable source, and only after it has
  checked the schema, the row count, and an executed query. That gap is the
  point: a well-formed archive can still be unusable, and reporting the weaker
  claim as the stronger one would serve nonsense.

Disabled by default -- see `property_core.config.ppd_snapshot_enabled`.
"""

from __future__ import annotations

from property_core.snapshot.adapter import SnapshotAdapter, SnapshotPage
from property_core.snapshot.archive import ExtractionLimits, ExtractionStats, safe_extract
from property_core.snapshot.errors import (
    ArchiveRejected,
    BundleVerificationError,
    DownloadDeadlineExceeded,
    InsufficientDiskSpaceError,
    SnapshotExtraMissingError,
    SnapshotNotQueryableError,
    SnapshotQueryError,
    SnapshotRowCountError,
    SnapshotSchemaError,
    SnapshotSourceError,
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
from property_core.snapshot.s3_source import TigrisObjectSource

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
    "SnapshotAdapter",
    "SnapshotExtraMissingError",
    "SnapshotManifest",
    "SnapshotNotQueryableError",
    "SnapshotPage",
    "SnapshotQueryError",
    "SnapshotRowCountError",
    "SnapshotSchemaError",
    "SnapshotStore",
    "SnapshotSourceError",
    "TigrisObjectSource",
    "VerificationRecord",
    "download_verified",
    "safe_extract",
    "single_flight",
]
