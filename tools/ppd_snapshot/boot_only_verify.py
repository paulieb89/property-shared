"""Boot-only verification: materialize and validate a real snapshot without
routing any live request to it.

    fly ssh console -a property-shared
    python /app/boot_only_verify.py --verify-dir /tmp/ppd-verify-$(date +%s)

Provides **partial** G1a evidence -- materialization and adapter-open/
validation timing, peak transient disk, and cold-run confirmation -- for a
real Machine against real object storage. It is not a completed G1a
measurement: the governing specification
(``docs/design/ppd-source-routing.md``) requires *application*
time-to-readiness -- full ASGI startup, async lifespan, single-flight lock
behaviour under the real deployed worker count -- which a standalone process
cannot produce no matter how its output is labelled. Label results
accordingly; do not present ``materialization_ms`` as application
time-to-ready.

**Isolation from the live server, by construction.** This module never
imports ``property_core.snapshot.state`` and is meant to run as an entirely
separate process from the deployed app (invoked out of band, e.g. via
``fly ssh console``) -- it cannot install an adapter live requests would ever
see, and ``PPD_SNAPSHOT_ENABLED`` is never read or set here. It reuses the
existing materialization path unchanged: ``SnapshotRuntime.boot()`` for
fetch/verify/extract (with its own already-enforced
``preflight_disk_space`` free-space precondition), then
``SnapshotAdapter.open`` for the same structural + queryable validation the
live path performs.

**Verification-only.** The materialized snapshot is always removed at the
end of a run, successful or not -- this is a measurement, not a cache, and
never shares a directory with the application's own
``PPD_SNAPSHOT_CACHE_DIR``.
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Optional, Sequence

#: The initial artifact's declared bundle size (design doc, "Scope and
#: account"). A cold run must download exactly this many bytes; anything
#: else means the bundle changed or the run was not genuinely cold.
EXPECTED_BUNDLE_BYTES = 279_109_872


class VerificationRefused(RuntimeError):
    """A precondition failed before anything was materialized."""


def _filesystem_type(path: Path, mounts_text: Optional[str] = None) -> str:
    """The filesystem type backing `path`, by longest mount-point match.

    Reads `/proc/mounts` unless `mounts_text` is given (for tests). Refuses
    rather than guessing when the table can't be read or nothing matches --
    silently assuming disk-backed would defeat the point of the check.
    """
    if mounts_text is None:
        try:
            mounts_text = Path("/proc/mounts").read_text()
        except OSError as exc:
            raise VerificationRefused(f"cannot read /proc/mounts: {exc}") from exc
    resolved = str(path.resolve())
    best_match = ""
    best_type = ""
    for line in mounts_text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        mount_point, fs_type = parts[1], parts[2]
        stripped = mount_point.rstrip("/") or "/"
        if resolved == stripped or resolved.startswith(stripped + "/"):
            if len(stripped) >= len(best_match):
                best_match, best_type = stripped, fs_type
    if not best_type:
        raise VerificationRefused(f"no mount entry matches {resolved}")
    return best_type


def assert_disk_backed(path: Path, mounts_text: Optional[str] = None) -> str:
    """Refuse a tmpfs/ramfs-backed verification root.

    G1a's disk and RAM figures mean something different than they appear to
    unless the materialization root is confirmed disk-backed first (design
    doc, G1a).
    """
    fs_type = _filesystem_type(path, mounts_text)
    if fs_type in ("tmpfs", "ramfs"):
        raise VerificationRefused(
            f"{path} is backed by {fs_type!r}, not disk -- G1a requires a "
            f"disk-backed materialization root"
        )
    return fs_type


def _prepare_verification_directory(path: Path, cache_dir: Path) -> None:
    """Create a unique, empty verification directory. Never the app's store."""
    resolved = path.resolve()
    cache_resolved = cache_dir.resolve()
    if resolved == cache_resolved or cache_resolved in resolved.parents:
        raise VerificationRefused(
            f"{path} collides with the application's own "
            f"PPD_SNAPSHOT_CACHE_DIR ({cache_dir}); use a separate directory"
        )
    if resolved.exists():
        raise VerificationRefused(
            f"{path} already exists -- the verification directory must start "
            f"empty and unique per run"
        )
    resolved.mkdir()


def _directory_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for entry in path.rglob("*"):
        try:
            if entry.is_file():
                total += entry.stat().st_size
        except OSError:
            continue
    return total


def _available_memory_bytes() -> Optional[int]:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


class _DiskAndMemorySampler:
    """Polls verification-directory size and Machine-wide available memory.

    A background thread, not a hook into the runtime: the fetch/extract code
    this wraps does blocking I/O with no yield points to sample from instead,
    and the live server process keeps running concurrently on the same
    Machine, so its memory pressure is part of the real headroom picture.
    """

    def __init__(self, directory: Path, interval: float = 0.2):
        self._directory = directory
        self._interval = interval
        self._stop = threading.Event()
        self._peak_disk_bytes = 0
        self._min_available_memory_bytes: Optional[int] = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _sample_once(self) -> None:
        current = _directory_bytes(self._directory)
        if current > self._peak_disk_bytes:
            self._peak_disk_bytes = current
        available = _available_memory_bytes()
        if available is not None and (
            self._min_available_memory_bytes is None
            or available < self._min_available_memory_bytes
        ):
            self._min_available_memory_bytes = available

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._sample_once()
            except Exception:  # noqa: BLE001 -- sampling must not abort the boot
                pass
            self._stop.wait(self._interval)

    def __enter__(self) -> "_DiskAndMemorySampler":
        self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._stop.set()
        self._thread.join(timeout=5)
        # One final sample: a fast run can finish between poll intervals and
        # otherwise report a peak of zero.
        try:
            self._sample_once()
        except Exception:  # noqa: BLE001
            pass

    @property
    def peak_disk_bytes(self) -> int:
        return self._peak_disk_bytes

    @property
    def min_available_memory_bytes(self) -> Optional[int]:
        return self._min_available_memory_bytes


def _is_cold_run_valid(report: Any, expected_bundle_bytes: Optional[int]) -> bool:
    """Whether this run is trustworthy as G1a cold-materialization evidence.

    A reused materialization, or a transfer short of the full bundle, is not
    a measurement of the thing G1a asks about -- record it as invalid rather
    than silently accepting it.
    """
    if report.reused_existing:
        return False
    if expected_bundle_bytes is not None:
        return report.bytes_downloaded == expected_bundle_bytes
    return report.bytes_downloaded > 0


def run_boot_only_verification(
    source: Any,
    *,
    verify_dir: Path,
    cache_dir: Path,
    expected_bundle_bytes: Optional[int] = EXPECTED_BUNDLE_BYTES,
    sample_interval: float = 0.2,
    mounts_text: Optional[str] = None,
) -> dict:
    """Materialize and validate one snapshot through `source`, then discard it.

    Never imports ``property_core.snapshot.state`` and never installs
    anything a live request could be routed to -- by construction, not by
    convention.
    """
    from property_core.snapshot.adapter import SnapshotAdapter
    from property_core.snapshot.runtime import SnapshotRuntime
    from property_core.snapshot.store import SnapshotStore

    if not verify_dir.parent.is_dir():
        raise VerificationRefused(
            f"{verify_dir.parent} does not exist; create the parent "
            f"directory first"
        )
    assert_disk_backed(verify_dir.parent, mounts_text)
    _prepare_verification_directory(verify_dir, cache_dir)

    result: dict[str, Any] = {"label": "boot-only verification measurement"}
    try:
        store = SnapshotStore(verify_dir)
        runtime = SnapshotRuntime(source=source, store=store)

        with _DiskAndMemorySampler(verify_dir, interval=sample_interval) as sampler:
            started = time.perf_counter()
            report = runtime.boot()
            materialization_ms = (time.perf_counter() - started) * 1000

        result.update({
            "readiness": report.readiness.value,
            "version": report.version,
            "reused_existing": report.reused_existing,
            "bytes_downloaded": report.bytes_downloaded,
            "behind_advertised_release": report.behind_advertised_release,
            "source_error": report.source_error,
            "warnings": list(report.warnings),
            "runtime_timings_ms": dict(report.timings_ms),
            "materialization_ms": round(materialization_ms, 1),
            "peak_transient_disk_bytes": sampler.peak_disk_bytes,
            "machine_min_available_memory_bytes": sampler.min_available_memory_bytes,
            "process_peak_rss_bytes":
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            "expected_bundle_bytes": expected_bundle_bytes,
            "cold_run_valid": _is_cold_run_valid(report, expected_bundle_bytes),
        })

        if not report.ready or not report.snapshot_dir or not report.version:
            result["validated"] = False
            return result

        record = store.verified_record(report.version)
        if record is None:
            result["validated"] = False
            result["validation_error"] = (
                "no verification record for the materialized version"
            )
            return result

        validation_started = time.perf_counter()
        with SnapshotAdapter.open(Path(report.snapshot_dir), record) as adapter:
            result.update({
                "validated": True,
                "validation_ms":
                    round((time.perf_counter() - validation_started) * 1000, 1),
                "coverage_from": adapter.coverage_from,
                "coverage_to": adapter.coverage_to,
            })
        return result
    finally:
        # Verification-only: never leave a materialized snapshot behind, and
        # touch nothing on the Machine's filesystem beyond this one directory.
        shutil.rmtree(verify_dir, ignore_errors=True)


def _build_cli_source() -> Any:
    """The real Tigris source, built exactly as the deployed app would build it."""
    from property_core.snapshot.bootstrap import _build_source
    from property_core.snapshot.s3_source import TigrisObjectSource

    try:
        source = _build_source()
    except RuntimeError as exc:
        raise VerificationRefused(str(exc)) from exc
    if not isinstance(source, TigrisObjectSource):
        raise VerificationRefused(
            f"PPD_SNAPSHOT_S3_BUCKET must be set for boot-only verification; "
            f"resolved a {type(source).__name__} instead"
        )
    return source


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python boot_only_verify.py",
        description=__doc__,
    )
    parser.add_argument(
        "--verify-dir", required=True,
        help="a not-yet-existing directory on a disk-backed filesystem; "
             "created fresh and removed at the end of this run",
    )
    parser.add_argument("--report", help="also write the JSON report here")
    parser.add_argument(
        "--expected-bundle-bytes", type=int, default=EXPECTED_BUNDLE_BYTES,
        help="required bytes_downloaded for a valid cold run "
             "(0 disables the exact-size check)",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    from property_core.snapshot.bootstrap import DEFAULT_CACHE_DIR, SNAPSHOT_CACHE_ENV

    args = build_parser().parse_args(argv)
    cache_dir = Path(os.environ.get(SNAPSHOT_CACHE_ENV, DEFAULT_CACHE_DIR))
    expected = args.expected_bundle_bytes or None

    try:
        source = _build_cli_source()
        result = run_boot_only_verification(
            source,
            verify_dir=Path(args.verify_dir),
            cache_dir=cache_dir,
            expected_bundle_bytes=expected,
        )
    except VerificationRefused as exc:
        result = {"label": "boot-only verification measurement",
                  "refused": str(exc)}
        print(json.dumps(result, indent=2))
        if args.report:
            Path(args.report).write_text(json.dumps(result, indent=2))
        return 2

    print(json.dumps(result, indent=2))
    if args.report:
        Path(args.report).write_text(json.dumps(result, indent=2))
    return 0 if result.get("validated") and result.get("cold_run_valid") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
