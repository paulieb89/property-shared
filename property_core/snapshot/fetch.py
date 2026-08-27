"""Streamed, verified bundle download.

The bundle body is NEVER held in memory. It is streamed to a temporary file in
fixed-size chunks while SHA-256 is computed incrementally, so peak memory is
independent of bundle size. (Measured at full scale during design: a 945 MiB
bundle booted at ~200 MB peak RSS, versus ~+24 MB over baseline for a buffered
25 MB bundle.)
"""

from __future__ import annotations

import hashlib
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from property_core.snapshot.errors import (
    BundleVerificationError,
    DownloadDeadlineExceeded,
    InsufficientDiskSpaceError,
)
from property_core.snapshot.models import SnapshotManifest

DEFAULT_CHUNK_SIZE = 1024 * 1024
#: Hard ceiling regardless of what a manifest claims. A manifest is data from
#: outside this process; it does not get to size our disk usage. An 11-partition
#: snapshot is ~214 MiB, so this leaves roughly 4.8x margin.
DEFAULT_MAX_BUNDLE_BYTES = 1 * 1024 ** 3

#: Whole-transfer budget. A download that never finishes is a boot that never
#: finishes, and readiness would hang instead of falling back to the live source.
DEFAULT_TOTAL_DEADLINE_SECONDS = 300.0

#: Longest a single read may go without returning data. The transport's own
#: socket timeout covers a silent connection; this covers one that dribbles.
DEFAULT_STALL_SECONDS = 60.0

#: Free space required before the transfer starts: the bundle, plus room to
#: unpack it, plus headroom. Filling the filesystem would take the live path
#: down alongside the snapshot.
DISK_HEADROOM_MULTIPLIER = 2.5


@dataclass(frozen=True)
class DownloadResult:
    bytes_written: int
    sha256: str
    path: Path


def preflight_disk_space(dest: Path, bundle_bytes: int, *,
                         multiplier: float = DISK_HEADROOM_MULTIPLIER) -> None:
    """Refuse to start a transfer that cannot fit. Raises InsufficientDiskSpaceError."""
    required = int(bundle_bytes * multiplier)
    target = Path(dest)
    probe = target if target.is_dir() else target.parent
    available = shutil.disk_usage(probe).free
    if available < required:
        raise InsufficientDiskSpaceError(required, available, str(probe))


def download_verified(source, manifest: SnapshotManifest, dest: Path, *,
                      chunk_size: int = DEFAULT_CHUNK_SIZE,
                      max_bytes: Optional[int] = None,
                      total_deadline: float = DEFAULT_TOTAL_DEADLINE_SECONDS,
                      stall_seconds: float = DEFAULT_STALL_SECONDS,
                      check_disk: bool = True) -> DownloadResult:
    """Stream `manifest.bundle_object` to `dest`, verifying size and digest.

    On any failure the partial file is removed, so a rejected download can never
    be mistaken for a usable bundle.
    """
    cap = DEFAULT_MAX_BUNDLE_BYTES if max_bytes is None else max_bytes
    if manifest.bundle_bytes > cap:
        raise BundleVerificationError(
            f"manifest declares {manifest.bundle_bytes} bytes, above the "
            f"{cap}-byte maximum"
        )

    dest = Path(dest)
    if check_disk:
        # Before the transfer, not after: a full filesystem is worse than a
        # missing snapshot.
        preflight_disk_space(dest, manifest.bundle_bytes)

    digest = hashlib.sha256()
    written = 0
    started = time.monotonic()
    try:
        with source.open_stream(manifest.bundle_object) as stream, \
                open(dest, "wb") as out:
            while True:
                read_started = time.monotonic()
                chunk = stream.read(chunk_size)
                waited = time.monotonic() - read_started
                if waited > stall_seconds:
                    raise DownloadDeadlineExceeded(
                        f"transfer stalled: no data for {waited:.1f}s "
                        f"(limit {stall_seconds}s)"
                    )
                if not chunk:
                    break
                if time.monotonic() - started > total_deadline:
                    raise DownloadDeadlineExceeded(
                        f"transfer exceeded its {total_deadline}s budget after "
                        f"{written} bytes"
                    )
                written += len(chunk)
                if written > cap:
                    # Abort the transfer rather than discovering the overrun
                    # after paying for all of it.
                    raise BundleVerificationError(
                        f"bundle exceeds the {cap}-byte maximum; transfer aborted"
                    )
                out.write(chunk)
                digest.update(chunk)
            out.flush()
            os.fsync(out.fileno())

        declared = getattr(stream, "declared_length", None)
        if declared is not None and declared != written:
            raise BundleVerificationError(
                f"short read: transport declared {declared} bytes, got {written}"
            )
        if written != manifest.bundle_bytes:
            raise BundleVerificationError(
                f"bundle length {written} != manifest {manifest.bundle_bytes}"
            )
        actual = digest.hexdigest()
        if actual != manifest.bundle_sha256:
            raise BundleVerificationError(
                f"sha256 mismatch: got {actual[:16]}..., "
                f"manifest {manifest.bundle_sha256[:16]}..."
            )
    except Exception:
        dest.unlink(missing_ok=True)
        raise

    return DownloadResult(bytes_written=written, sha256=actual, path=dest)
