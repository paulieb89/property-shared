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
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from property_core.snapshot.errors import BundleVerificationError
from property_core.snapshot.models import SnapshotManifest

DEFAULT_CHUNK_SIZE = 1024 * 1024
#: Hard ceiling regardless of what a manifest claims. A manifest is data from
#: outside this process; it does not get to size our disk usage.
DEFAULT_MAX_BUNDLE_BYTES = 2 * 1024 ** 3


@dataclass(frozen=True)
class DownloadResult:
    bytes_written: int
    sha256: str
    path: Path


def download_verified(source, manifest: SnapshotManifest, dest: Path, *,
                      chunk_size: int = DEFAULT_CHUNK_SIZE,
                      max_bytes: Optional[int] = None) -> DownloadResult:
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
    digest = hashlib.sha256()
    written = 0
    try:
        with source.open_stream(manifest.bundle_object) as stream, \
                open(dest, "wb") as out:
            while True:
                chunk = stream.read(chunk_size)
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
