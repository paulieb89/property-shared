"""Boot-only verification: materialize and validate a real snapshot without
routing any live request to it.

    fly ssh console -a property-shared
    python /app/boot_only_verify.py --verify-dir /tmp/ppd-verify-$(date +%s)

Provides **partial** G1a evidence -- fetch, extraction and adapter-open/
validation timing, peak transient disk, and cold-run confirmation -- for a
real Machine against real object storage. Every result this module produces
carries `evidence_scope: "partial_g1a"`, `g1a_complete: false` and
`stage_1_evidence: false` explicitly, because it is not a completed G1a
measurement and can never become one: the governing specification
(``docs/design/ppd-source-routing.md``) requires *application*
time-to-readiness -- full ASGI startup, async lifespan, single-flight lock
behaviour under the real deployed worker count -- which a standalone process
cannot produce no matter how its output is labelled. It is also not Stage 1
evidence: no real-traffic sample, no divergence classification.

**Isolation from the live server, by construction.** This module never
imports ``property_core.snapshot.state`` and is meant to run as an entirely
separate process from the deployed app (invoked out of band, e.g. via
``fly ssh console``) -- it cannot install an adapter live requests would ever
see, and ``PPD_SNAPSHOT_ENABLED`` is never read or set here. It reuses the
existing materialization path unchanged: ``SnapshotRuntime.boot()`` for
fetch/verify/extract (with its own already-enforced
``preflight_disk_space`` free-space precondition), then
``SnapshotAdapter.open`` for the same structural + queryable validation the
live path performs. Fetch and extraction boundaries are timed by wrapping
the exact functions ``SnapshotRuntime`` calls (``download_verified``,
``safe_extract``) for the duration of one run -- not by changing what they
do, and not by touching ``runtime.py`` itself.

**Verification-only.** The materialized snapshot is always removed at the
end of a run, successful or not -- this is a measurement, not a cache, and
never shares a directory with, or nests either way with, the application's
own ``PPD_SNAPSHOT_CACHE_DIR``. A cleanup failure is reported explicitly
(``cleanup_ok: false``), never silently swallowed.
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import shutil
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional, Sequence

#: The initial artifact's declared bundle size (design doc, "Scope and
#: account"). A cold run must download exactly this many bytes; anything
#: else means the bundle changed or the run was not genuinely cold. Not
#: overridable from the CLI -- see `_is_cold_run_valid` and `main`.
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
        # The prefix must not be built as `stripped + "/"`: for the root mount
        # `stripped` is "/", so that yields "//", which no absolute path starts
        # with, and the root filesystem then matches only the exact path "/".
        # A Fly Machine has no dedicated /tmp mount, so every path under / was
        # refused as "no mount entry" -- including this module's own documented
        # invocation.
        prefix = stripped if stripped.endswith("/") else stripped + "/"
        if resolved == stripped or resolved.startswith(prefix):
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
    """Create a unique, empty verification directory.

    Refuses nesting with the application's own store in **either**
    direction: the verifier inside the app's cache would let a future
    change reuse the app's materialization; the app's cache inside the
    verifier would put it inside a directory this module unconditionally
    `rmtree`s at the end of the run. Sibling directories only.
    """
    resolved = path.resolve()
    cache_resolved = cache_dir.resolve()
    nested = (
        resolved == cache_resolved
        or cache_resolved in resolved.parents
        or resolved in cache_resolved.parents
    )
    if nested:
        raise VerificationRefused(
            f"{path} and the application's PPD_SNAPSHOT_CACHE_DIR "
            f"({cache_dir}) must be sibling directories, not nested either way"
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
    this wraps does blocking I/O with no yield points to sample from
    instead. Must stay active through adapter-open validation, not just
    materialization -- DuckDB's own memory use during validation is part of
    the real headroom picture, and the live server process keeps running
    concurrently on the same Machine throughout.
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


class _PhaseTimes:
    """Fetch and extraction wall-clock time, bound to the real boundaries."""

    def __init__(self) -> None:
        self.fetch_ms: Optional[float] = None
        self.extraction_ms: Optional[float] = None


@contextmanager
def _instrumented_install_phases() -> Iterator[_PhaseTimes]:
    """Times the exact fetch and extraction calls `SnapshotRuntime` makes.

    Patches the names `property_core.snapshot.runtime` imported them under,
    for the lifetime of this context only, then restores them -- this times
    the real functions on their real call, it does not change what they do.
    Neither is called at all on a reused-materialization boot, which
    correctly leaves both fields `None` rather than reporting a phase that
    did not run.

    The bundle/extraction disk-overlap window the design doc asks about
    (G1a) is, by `SnapshotRuntime._install`'s own structure, the extraction
    call's duration: the bundle is fully on disk before extraction starts,
    and is unlinked immediately after extraction returns. `overlap_window_ms`
    is reported as exactly `extraction_ms` for that reason, not measured
    independently.
    """
    import property_core.snapshot.runtime as runtime_module

    times = _PhaseTimes()
    original_download = runtime_module.download_verified
    original_extract = runtime_module.safe_extract

    def timed_download(*args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            return original_download(*args, **kwargs)
        finally:
            times.fetch_ms = round((time.perf_counter() - started) * 1000, 1)

    def timed_extract(*args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            return original_extract(*args, **kwargs)
        finally:
            times.extraction_ms = round((time.perf_counter() - started) * 1000, 1)

    runtime_module.download_verified = timed_download
    runtime_module.safe_extract = timed_extract
    try:
        yield times
    finally:
        runtime_module.download_verified = original_download
        runtime_module.safe_extract = original_extract


def _is_cold_run_valid(report: Any, expected_bundle_bytes: Optional[int]) -> bool:
    """Whether this run is trustworthy as G1a cold-materialization evidence.

    A reused materialization, or a transfer short of (or over) the full
    bundle, is not a measurement of the thing G1a asks about -- record it as
    invalid rather than silently accepting it.
    """
    if report.reused_existing:
        return False
    if expected_bundle_bytes is not None:
        return report.bytes_downloaded == expected_bundle_bytes
    return report.bytes_downloaded > 0


def _base_result() -> dict:
    """Every result this module ever returns carries this, unconditionally.

    Not computed from the run's outcome: this tool structurally cannot
    produce a completed G1a measurement (no application startup lifecycle)
    or Stage 1 evidence (no real traffic, no divergence classification),
    whether this particular run succeeds, fails, or is refused outright.
    """
    return {
        "evidence_scope": "partial_g1a",
        "g1a_complete": False,
        "stage_1_evidence": False,
    }


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

    result = _base_result()
    try:
        store = SnapshotStore(verify_dir)
        runtime = SnapshotRuntime(source=source, store=store)

        # Disk/memory sampling and fetch/extract phase timing both stay
        # active through adapter-open validation, not just materialization --
        # DuckDB's own memory use during validation is otherwise invisible,
        # and process_peak_rss_bytes is read only after this block exits.
        with _DiskAndMemorySampler(verify_dir, interval=sample_interval) as sampler, \
             _instrumented_install_phases() as phase_times:
            started = time.perf_counter()
            report = runtime.boot()
            materialization_ms = round((time.perf_counter() - started) * 1000, 1)

            if report.ready and report.snapshot_dir and report.version:
                record = store.verified_record(report.version)
                if record is None:
                    result["validated"] = False
                    result["validation_error"] = (
                        "no verification record for the materialized version"
                    )
                else:
                    validation_started = time.perf_counter()
                    with SnapshotAdapter.open(
                            Path(report.snapshot_dir), record) as adapter:
                        result["validated"] = True
                        result["validation_ms"] = round(
                            (time.perf_counter() - validation_started) * 1000, 1)
                        result["coverage_from"] = adapter.coverage_from
                        result["coverage_to"] = adapter.coverage_to
            else:
                result["validated"] = False

        result.update({
            "readiness": report.readiness.value,
            "version": report.version,
            "reused_existing": report.reused_existing,
            "bytes_downloaded": report.bytes_downloaded,
            "behind_advertised_release": report.behind_advertised_release,
            "source_error": report.source_error,
            "warnings": list(report.warnings),
            "runtime_timings_ms": dict(report.timings_ms),
            "fetch_ms": phase_times.fetch_ms,
            "extraction_ms": phase_times.extraction_ms,
            "overlap_window_ms": phase_times.extraction_ms,
            "materialization_ms": materialization_ms,
            "peak_transient_disk_bytes": sampler.peak_disk_bytes,
            "machine_min_available_memory_bytes": sampler.min_available_memory_bytes,
            "process_peak_rss_bytes":
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            "expected_bundle_bytes": expected_bundle_bytes,
            "cold_run_valid": _is_cold_run_valid(report, expected_bundle_bytes),
        })
        return result
    finally:
        # Verification-only: never leave a materialized snapshot behind. A
        # removal failure is reported, never swallowed -- `ignore_errors`
        # would let this tool claim success while leaving the artifact
        # behind on the Machine's disk.
        try:
            shutil.rmtree(verify_dir)
            result["cleanup_ok"] = True
            result["cleanup_error"] = None
        except Exception as exc:  # noqa: BLE001 -- recorded, not raised
            result["cleanup_ok"] = False
            result["cleanup_error"] = f"{type(exc).__name__}: {exc}"


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
    # Deliberately no --expected-bundle-bytes flag: the CLI always requires
    # the declared EXPECTED_BUNDLE_BYTES exactly. A configurable escape
    # hatch here would let a production invocation report cold_run_valid
    # from merely `bytes_downloaded > 0`, which is not what G1a asks for.
    # `run_boot_only_verification` still takes the parameter for tests.
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    from property_core.snapshot.bootstrap import DEFAULT_CACHE_DIR, SNAPSHOT_CACHE_ENV

    args = build_parser().parse_args(argv)
    cache_dir = Path(os.environ.get(SNAPSHOT_CACHE_ENV, DEFAULT_CACHE_DIR))

    try:
        source = _build_cli_source()
        result = run_boot_only_verification(
            source,
            verify_dir=Path(args.verify_dir),
            cache_dir=cache_dir,
            expected_bundle_bytes=EXPECTED_BUNDLE_BYTES,
        )
    except VerificationRefused as exc:
        result = {**_base_result(), "refused": str(exc)}
        print(json.dumps(result, indent=2))
        if args.report:
            Path(args.report).write_text(json.dumps(result, indent=2))
        return 2

    print(json.dumps(result, indent=2))
    if args.report:
        Path(args.report).write_text(json.dumps(result, indent=2))
    ok = (result.get("validated") and result.get("cold_run_valid")
          and result.get("cleanup_ok", True))
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
