"""Boot-time snapshot orchestration.

One job: at process start, obtain a verified snapshot and make it available, or
fail closed with a typed error. It fetches, verifies, extracts, activates and
prunes. It does NOT open, query or route to the snapshot -- reading data from it
is separate work.

**No hot refresh in v1.** Activation happens at process start only. There is
deliberately no refresh/reload/watch entry point: swapping a live snapshot under
load is untested and out of scope.

**The materialization is ephemeral.** Both Machines run on Fly's default root
filesystem with no Volume and no `persist_rootfs`, so nothing here survives a
restart or deploy. A snapshot is therefore not a cache to fall back on: after a
restart there is none. The fallback for an unavailable boot-fetch is the **live
SPARQL source**.

Failure policy:

1. a verified snapshot matching the advertised release                -> READY
2. the advertised release cannot be fetched, but a snapshot was already
   materialized on THIS Machine (typically by another worker)         -> READY,
   flagged `behind_advertised_release` -- not a durability guarantee
3. nothing materialized                                               -> UNREADY,
   `fallback_to_live=True`; the caller uses the live source

Serving something unverified never happens.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from property_core.exceptions import SnapshotUnavailableError
from property_core.snapshot.archive import ExtractionLimits, safe_extract
from property_core.snapshot.fetch import DEFAULT_MAX_BUNDLE_BYTES, download_verified
from property_core.snapshot.lock import DEFAULT_TIMEOUT as LOCK_TIMEOUT
from property_core.snapshot.lock import LockTimeout, single_flight
from property_core.snapshot.models import BootReport, Readiness, SnapshotManifest
from property_core.snapshot.store import DEFAULT_KEEP, SnapshotStore

CURRENT_POINTER_OBJECT = "current.json"


class SnapshotRuntime:
    """Owns one snapshot store and the boot sequence that fills it."""

    def __init__(self, *, source, store: SnapshotStore,
                 extraction_limits: Optional[ExtractionLimits] = None,
                 max_bundle_bytes: int = DEFAULT_MAX_BUNDLE_BYTES,
                 lock_timeout: float = LOCK_TIMEOUT,
                 keep_versions: int = DEFAULT_KEEP):
        self.source = source
        self.store = store
        self.extraction_limits = extraction_limits or ExtractionLimits()
        self.max_bundle_bytes = max_bundle_bytes
        self.lock_timeout = lock_timeout
        self.keep_versions = keep_versions
        self._report = BootReport()

    # -- state ----------------------------------------------------------
    @property
    def readiness(self) -> Readiness:
        return self._report.readiness

    @property
    def report(self) -> BootReport:
        return self._report

    def require_ready(self) -> str:
        """The active snapshot directory, or a typed error.

        The typed error is the caller's signal to use the **live source**, not to
        return nothing: "no snapshot" and "no matching rows" are different facts,
        and only one of them is about the data.
        """
        if not self._report.ready or not self._report.snapshot_dir:
            raise SnapshotUnavailableError(
                self._report.source_error or "no verified snapshot is open"
            )
        return self._report.snapshot_dir

    # -- boot -----------------------------------------------------------
    def boot(self) -> BootReport:
        started = time.perf_counter()
        warnings: list[str] = []
        materialized = self.store.current_version()

        try:
            manifest = self._load_manifest()
        except Exception as exc:
            self._report = self._degrade(
                materialized, self._describe(exc), warnings, started)
            return self._report

        # This Machine already materialized exactly this release: nothing to fetch.
        if (materialized == manifest.snapshot_version
                and self.store.is_verified(materialized)):
            self._report = self._ready(materialized, reused_existing=True,
                                       warnings=warnings, started=started)
            return self._report

        try:
            with single_flight(self.store.root / ".boot.lock",
                               timeout=self.lock_timeout):
                # Re-check under the lock: another starter may have activated
                # this release while we were waiting, in which case fetching
                # again would be pure waste.
                current = self.store.current_version()
                if current == manifest.snapshot_version and self.store.is_verified(current):
                    self._report = self._ready(current, reused_existing=True,
                                               warnings=warnings, started=started)
                    return self._report

                downloaded = self._install(manifest)
        except (LockTimeout, Exception) as exc:
            self._report = self._degrade(
                self.store.current_version(), self._describe(exc), warnings, started)
            return self._report

        self.store.prune(self.keep_versions)
        self._report = self._ready(manifest.snapshot_version, activated=True,
                                   bytes_downloaded=downloaded, warnings=warnings,
                                   started=started)
        return self._report

    # -- steps ----------------------------------------------------------
    def _load_manifest(self) -> SnapshotManifest:
        pointer = json.loads(self.source.read_bytes(CURRENT_POINTER_OBJECT))
        name = pointer["current_manifest"]
        if not isinstance(name, str) or "/" in name or name.startswith("."):
            raise ValueError(f"current.json names an unusable manifest: {name!r}")
        return SnapshotManifest(**json.loads(self.source.read_bytes(name)))

    def _install(self, manifest: SnapshotManifest) -> int:
        """Download, verify, extract and activate. Raises on any failure."""
        with self.store.stage(manifest.snapshot_version) as staging:
            # Keep the published object's extension: the archive format is a
            # property of the object, and extraction dispatches on it.
            bundle = staging.parent / f"{staging.name}-{Path(manifest.bundle_object).name}"
            try:
                result = download_verified(
                    self.source, manifest, bundle,
                    max_bytes=self.max_bundle_bytes)
                extract_into = staging / "unpacked"
                stats = safe_extract(bundle, extract_into, self.extraction_limits)
            finally:
                # The bundle is large and is never needed again once unpacked.
                Path(bundle).unlink(missing_ok=True)

            if stats.files < manifest.parquet_files:
                raise ValueError(
                    f"archive holds {stats.files} files, manifest declares at least "
                    f"{manifest.parquet_files} parquet files"
                )
            self.store.activate(
                extract_into, manifest.snapshot_version,
                {
                    "version": manifest.snapshot_version,
                    "bundle_sha256": manifest.bundle_sha256,
                    "bundle_bytes": manifest.bundle_bytes,
                    "parquet_files": self._count_parquet(extract_into),
                    "rows": manifest.rows,
                    "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
            )
        return result.bytes_written

    @staticmethod
    def _count_parquet(directory: Path) -> int:
        import os

        return sum(1 for _r, _d, files in os.walk(directory)
                   for f in files if f.endswith(".parquet"))

    # -- outcomes -------------------------------------------------------
    @staticmethod
    def _describe(exc: Exception) -> str:
        return f"{type(exc).__name__}: {str(exc)[:200]}"

    def _elapsed(self, started: float) -> dict[str, float]:
        return {"total_ms": round((time.perf_counter() - started) * 1000, 1)}

    def _ready(self, version: str, *, activated: bool = False,
               reused_existing: bool = False, bytes_downloaded: int = 0,
               behind_advertised_release: bool = False,
               source_error: Optional[str] = None,
               warnings: list[str], started: float) -> BootReport:
        return BootReport(
            readiness=Readiness.READY, version=version,
            snapshot_dir=str(self.store.path_for(version)),
            fallback_to_live=False,
            behind_advertised_release=behind_advertised_release,
            activated=activated, reused_existing=reused_existing,
            bytes_downloaded=bytes_downloaded, source_error=source_error,
            warnings=tuple(warnings), timings_ms=self._elapsed(started),
        )

    def _degrade(self, materialized: Optional[str], error: str,
                 warnings: list[str], started: float) -> BootReport:
        """Adopt an existing same-Machine materialization, or hand off to live.

        Adopting one is NOT a durability guarantee: it exists only because this
        Machine has not restarted since another worker unpacked it. After a
        restart there is nothing here, and the answer is the live source.
        """
        if materialized and self.store.is_verified(materialized):
            return self._ready(
                materialized, reused_existing=True, behind_advertised_release=True,
                source_error=error, started=started,
                warnings=[
                    *warnings,
                    f"using snapshot {materialized} already materialized on this "
                    f"machine; the advertised release could not be fetched ({error})",
                ],
            )
        return BootReport(
            readiness=Readiness.UNREADY, fallback_to_live=True, source_error=error,
            warnings=(*warnings,
                      f"no snapshot materialized; using the live source ({error})"),
            timings_ms=self._elapsed(started),
        )
