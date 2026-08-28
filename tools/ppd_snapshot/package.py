"""Bundle the partitions and publish the manifest the runtime will read.

Two documents come out of this, and keeping them apart is the point:

* **`manifest-<version>.json`** -- exactly the eleven fields
  `property_core.snapshot.models.SnapshotManifest` declares, no more. That model
  is frozen and `extra="forbid"`, so a manifest carrying the build's own
  provenance does not degrade gracefully: it fails to parse at boot and the
  Machine falls back to the live source. The prototype's richer manifest
  (`source_sha256`, `compression`, `row_group_size`, `logical_sort_order`) is
  exactly that shape and is not portable.
* **`build-report-<version>.json`** -- everything else worth keeping: source
  provenance, timings, per-year row counts, measured sizes. Nothing reads it at
  runtime; it exists so a build can be explained afterwards.

**Local only.** This writes files into a directory on this machine. There is no
upload, no bucket, no credential, and `current.json` is published beside the
manifest purely so the whole boot path can be exercised offline through
`LocalDirectorySource`.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import shutil
import tarfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from property_core.snapshot.models import SnapshotManifest, validate_component

from tools.ppd_snapshot.build import COMPRESSION, PARTITION_FILE, BuildResult

#: Read in fixed chunks so a full-history bundle is never held in memory --
#: the same discipline the boot fetch applies on the way in.
CHUNK_BYTES = 1024 * 1024

#: zstd level. 10 is the knee of the curve for already-zstd-compressed Parquet:
#: higher levels cost minutes and save single-digit MiB.
ZSTD_LEVEL = 10

LAYOUT = "year"


class BundleMismatch(RuntimeError):
    """The bundle on disk is not what the manifest says it is."""


class VersionAlreadyPublished(RuntimeError):
    """A published version names one set of bytes, for ever.

    The store refuses to materialise a second bundle under a version it already
    holds, so publishing over one here would create an artifact the runtime can
    never install. Republishing requires a new version.
    """


@dataclass(frozen=True)
class PackagedRelease:
    version: str
    dist_dir: Path
    #: Where the release is assembled. A bundle sitting in the dist root is a
    #: bundle someone can publish, so nothing arrives there until it has booted.
    candidate_dir: Path
    bundle_path: Path
    manifest_path: Path
    current_path: Path
    report_path: Path
    bundle_bytes: int
    bundle_sha256: str
    parquet_files: int
    rows: int


def snapshot_version(built_at: Optional[datetime] = None) -> str:
    """A version name from the build instant, in UTC.

    Sortable, unambiguous, and a single safe path component -- the store turns
    it straight into a directory name.
    """
    stamp = built_at or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        raise ValueError("built_at must be timezone-aware")
    return "v" + stamp.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _normalise(info: tarfile.TarInfo) -> tarfile.TarInfo:
    """Strip everything that is about this machine rather than the data.

    Ownership, names and timestamps vary between builds of identical content and
    would otherwise make two byte-identical snapshots produce different bundles.
    """
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mtime = 0
    info.mode = 0o644
    return info


def _partition_members(snapshot_dir: Path) -> list[tuple[Path, str]]:
    members = []
    for path in sorted(snapshot_dir.glob(f"year=*/{PARTITION_FILE}")):
        members.append((path, path.relative_to(snapshot_dir).as_posix()))
    if not members:
        raise ValueError(f"no partitions found under {snapshot_dir}")
    return members


def write_bundle(snapshot_dir: Path, bundle_path: Path) -> tuple[int, str]:
    """Write the `.tar.zst` and return its length and digest.

    The digest is computed by reading the finished file back, not from the bytes
    on the way out: what the runtime verifies is what landed on disk.
    """
    import zstandard

    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    compressor = zstandard.ZstdCompressor(level=ZSTD_LEVEL)
    with open(bundle_path, "wb") as raw:
        with compressor.stream_writer(raw) as stream:
            # A stream mode ("w|"), so nothing seeks back over the archive.
            with tarfile.open(fileobj=stream, mode="w|") as tar:
                for path, arcname in _partition_members(snapshot_dir):
                    tar.add(path, arcname=arcname, filter=_normalise)
    return _measure(bundle_path)


def _measure(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    length = 0
    with open(path, "rb") as fh:
        while chunk := fh.read(CHUNK_BYTES):
            digest.update(chunk)
            length += len(chunk)
    return length, digest.hexdigest()


def verify_bundle(bundle_path: Path, *, expected_sha256: str,
                  expected_bytes: int) -> None:
    """Re-verify a published bundle exactly as the runtime will."""
    length, digest = _measure(Path(bundle_path))
    if length != expected_bytes:
        raise BundleMismatch(
            f"{bundle_path.name} is {length} bytes, manifest declares "
            f"{expected_bytes}")
    if digest != expected_sha256:
        raise BundleMismatch(
            f"{bundle_path.name} sha256 is {digest}, manifest declares "
            f"{expected_sha256}")


def package_release(built: BuildResult, *, dist_dir: Path, version: str,
                    source: Mapping[str, Any],
                    facts: Mapping[str, Any]) -> PackagedRelease:
    """Bundle, publish the manifest, and record the build report."""
    validate_component(version, "snapshot_version")
    dist_dir = Path(dist_dir)
    dist_dir.mkdir(parents=True, exist_ok=True)
    candidate_dir = dist_dir / f"candidate-{version}"

    bundle_path = candidate_dir / f"snapshot-{version}.tar.zst"
    manifest_path = candidate_dir / f"manifest-{version}.json"
    report_path = candidate_dir / f"build-report-{version}.json"
    for existing in (bundle_path, manifest_path,
                     dist_dir / bundle_path.name, dist_dir / manifest_path.name):
        if existing.exists():
            raise VersionAlreadyPublished(
                f"{existing.name} already exists; a changed snapshot requires a "
                f"new version, never a rewritten one")
    candidate_dir.mkdir(parents=True, exist_ok=True)

    bundle_bytes, bundle_sha256 = write_bundle(built.snapshot_dir, bundle_path)

    # Constructed through the runtime's own model, so an unpublishable manifest
    # fails here rather than at someone else's boot.
    manifest = SnapshotManifest(
        snapshot_version=version,
        bundle_object=bundle_path.name,
        bundle_sha256=bundle_sha256,
        bundle_bytes=bundle_bytes,
        parquet_files=built.parquet_files,
        rows=built.rows,
        coverage_from=built.coverage_from.isoformat(),
        coverage_to=built.coverage_to.isoformat(),
        provisional_from=built.provisional_from.isoformat(),
        layout=LAYOUT,
        duckdb_version=built.duckdb_version,
    )
    manifest_path.write_text(json.dumps(manifest.model_dump(), indent=2) + "\n")

    # The candidate gets its own pointer so the whole boot path can be
    # exercised against it. The pointer in the dist root is written only at
    # promotion, and only last.
    current_path = candidate_dir / "current.json"
    current_path.write_text(
        json.dumps({"current_manifest": manifest_path.name}, indent=2) + "\n")

    report = {
        "snapshot_version": version,
        "built_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": dict(source),
        "layout": LAYOUT,
        "compression": COMPRESSION,
        "logical_sort_order": "transfer_date DESC, transaction_id ASC",
        "duckdb_version": built.duckdb_version,
        "coverage_from": built.coverage_from.isoformat(),
        "coverage_to": built.coverage_to.isoformat(),
        "provisional_from": built.provisional_from.isoformat(),
        "years": list(built.years),
        "parquet_files": built.parquet_files,
        "rows": built.rows,
        "source_rows": built.source_rows,
        "rows_outside_window": built.rows_outside_window,
        "rows_without_date": built.rows_without_date,
        "bundle_bytes": bundle_bytes,
        "bundle_sha256": bundle_sha256,
        "snapshot_bytes": sum(p.stat().st_size
                              for p in built.snapshot_dir.rglob("*.parquet")),
        "timings_seconds": dict(built.timings_seconds),
        "peak_rss_mb": built.peak_rss_mb,
        **dict(facts),
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n")

    return PackagedRelease(
        version=version, dist_dir=dist_dir, candidate_dir=candidate_dir,
        bundle_path=bundle_path,
        manifest_path=manifest_path, current_path=current_path,
        report_path=report_path, bundle_bytes=bundle_bytes,
        bundle_sha256=bundle_sha256, parquet_files=built.parquet_files,
        rows=built.rows)


def promote_release(release: PackagedRelease) -> PackagedRelease:
    """Move a booted candidate into the dist root, writing the pointer last.

    `current.json` is a promise that what it names is present. Writing it before
    the manifest and bundle have landed would publish that promise ahead of the
    thing it describes, so a promotion interrupted half way leaves a partial
    directory and **no pointer** -- which reads as "nothing published", the only
    honest state to be in.
    """
    dist_dir = release.dist_dir
    moved: dict[str, Path] = {}
    for path in (release.bundle_path, release.manifest_path, release.report_path):
        target = dist_dir / path.name
        if target.exists():
            raise VersionAlreadyPublished(
                f"{target.name} is already published; a changed snapshot "
                f"requires a new version")
        shutil.move(str(path), str(target))
        moved[path.name] = target

    current_path = dist_dir / "current.json"
    current_path.write_text(
        json.dumps({"current_manifest": release.manifest_path.name},
                   indent=2) + "\n")
    shutil.rmtree(release.candidate_dir, ignore_errors=True)

    return dataclasses.replace(
        release,
        bundle_path=moved[release.bundle_path.name],
        manifest_path=moved[release.manifest_path.name],
        report_path=moved[release.report_path.name],
        current_path=current_path)
