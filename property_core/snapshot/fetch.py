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
#: outside this process; it does not get to size our disk usage.
#:
#: Raised from 1 GiB when coverage went to the full PPD history. The measured
#: 32-partition snapshot is 1,189,365,783 B (1.108 GiB), which the old ceiling
#: refused at boot -- correctly, and before a byte transferred. 2 GiB leaves
#: ~1.8x margin, and the register grows by roughly a million rows a year, so
#: this should not need revisiting for a decade.
#:
#: Checked against the whole stack rather than in isolation:
#:   preflight    bundle * 2.5 = 5.37 GiB at the cap, vs 8.32 GB free on the
#:                Machine (2.97 GiB at the actual 1.108 GiB bundle)
#:   extraction   ExtractionLimits.max_total_bytes raised to 4 GiB in step, or
#:                a bundle near this cap would unpack into a smaller one
DEFAULT_MAX_BUNDLE_BYTES = 2 * 1024 ** 3

#: Whole-transfer budget, evaluated BETWEEN reads. A download that never
#: finishes is a boot that never finishes, and readiness would hang instead of
#: falling back to the live source.
#:
#: This bounds total wall time only as tightly as the reads are themselves
#: bounded. `HttpObjectSource` uses `read1`, which returns after one underlying
#: socket read, so the budget is evaluated at real intervals. A source whose
#: `read()` loops internally -- plain `HTTPResponse.read(n)` does -- could keep a
#: single call active past this budget, and it would then be detected on return
#: rather than enforced at the limit.
DEFAULT_TOTAL_DEADLINE_SECONDS = 300.0

#: Post-read stall DETECTION budget.
#:
#: Not an interrupt, and it does not bound how long a read may block:
#: ``stream.read()`` is synchronous, so elapsed time can only be inspected once
#: it returns. A read that blocks for ten minutes is detected after ten minutes,
#: not aborted at this limit.
#:
#: **What actually bounds a blocked read is the transport's socket timeout**
#: (`HttpObjectSource(socket_timeout=...)`), which the OS enforces per socket
#: operation and which the stream translates into DownloadDeadlineExceeded. This
#: value is the backstop for sources that cannot honour one -- a local file, a
#: test double -- and for a connection that dribbles rather than going silent.
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

    ``total_deadline`` and ``stall_seconds`` are checked after every read,
    including the one that returns EOF. Neither interrupts a blocked read --
    see DEFAULT_STALL_SECONDS for what actually bounds one.
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
                now = time.monotonic()

                # Both checks run after EVERY read, EOF included. Breaking on an
                # empty chunk first let a read that blocked past the budget and
                # then returned EOF finish successfully.
                if now - started > total_deadline:
                    raise DownloadDeadlineExceeded(
                        f"transfer exceeded its {total_deadline}s budget after "
                        f"{written} bytes"
                    )
                waited = now - read_started
                if waited > stall_seconds:
                    raise DownloadDeadlineExceeded(
                        f"transfer stalled: a single read took {waited:.1f}s "
                        f"(detection budget {stall_seconds}s)"
                    )
                if not chunk:
                    break
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
