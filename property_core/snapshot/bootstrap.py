"""Boot the snapshot once per server process, through the FastMCP lifespan.

Spec section 4.10, which fixes this before PR 4 rather than leaving it to be
discovered:

* **Once per process, at startup.** A lazy first-use boot would put a twenty
  second download in the path of whichever request happened to arrive first.
* **Combined lifespans where the MCP app is mounted alongside FastAPI.**
  Mounting does not chain lifespans; a lifespan that is never awaited is a boot
  that never happens. `app/main.py` awaits the FastMCP lifespan explicitly.
* **Process-scoped state** -- see `property_core.snapshot.state`.
* **The filesystem single-flight lock is retained.** Lifespan wiring coordinates
  nothing between the worker processes sharing a Machine; `flock` does.
* **A startup failure leaves the server up on the live source.** UNREADY is a
  normal outcome, not a startup error, so nothing here is allowed to raise into
  the ASGI startup sequence.

Everything is off unless `PPD_SNAPSHOT_ENABLED` is set. With it unset this module
imports nothing from DuckDB and touches no filesystem.
"""

from __future__ import annotations

import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from property_core.config import ppd_snapshot_enabled, ppd_snapshot_shadow_enabled
from property_core.snapshot import state

log = logging.getLogger("property_core.snapshot.boot")

#: Boot lifecycle, reported verbatim by `snapshot_status()`.
#:
#: * ``not_started`` -- neither flag is on, or the lifespan has not run.
#: * ``warming``     -- the background boot is in flight. The application is
#:                      already serving; requests go to the live source.
#: * ``ready``       -- materialized and validated. Routable *only* if
#:                      ``PPD_SNAPSHOT_ENABLED`` is also on.
#: * ``failed``      -- the boot did not produce a usable snapshot. The live
#:                      source keeps answering; this is not an outage.
PHASE_NOT_STARTED = "not_started"
PHASE_WARMING = "warming"
PHASE_READY = "ready"
PHASE_FAILED = "failed"

#: Where the bundle is published. A local directory is supported so the whole
#: path can be exercised without any network or cloud resource.
SNAPSHOT_URL_ENV = "PPD_SNAPSHOT_URL"
SNAPSHOT_DIR_ENV = "PPD_SNAPSHOT_DIR"
SNAPSHOT_BUCKET_ENV = "PPD_SNAPSHOT_S3_BUCKET"
#: Where it is materialized. Ephemeral: Fly's default rootfs, wiped on restart.
SNAPSHOT_CACHE_ENV = "PPD_SNAPSHOT_CACHE_DIR"
DEFAULT_CACHE_DIR = "/tmp/ppd-snapshot"

#: Set once the boot has been attempted in this process. Idempotence is by
#: attempt, not by success: a failed boot must not be retried by every worker
#: thread that happens to call the lifespan again.
_booted = False

#: Lifecycle bookkeeping, read from the event loop while the boot runs in a
#: worker thread, so every mutation is under this lock.
_phase_lock = threading.Lock()
_phase = PHASE_NOT_STARTED
_boot_error: Optional[str] = None

#: Cleared on shutdown. `anyio.to_thread.run_sync` cannot interrupt a thread
#: blocked in a socket read or an flock wait, so an abandoned boot really does
#: keep running after the lifespan has torn the snapshot down. Without this
#: gate it would install an adapter into a process that has already closed
#: everything, leaking an open DuckDB handle for the life of the process.
_accepting_installs = False

#: The in-flight boot, for a bounded join at shutdown.
_boot_thread: Optional[threading.Thread] = None

#: How long shutdown waits for a nearly-finished boot before abandoning it.
#: Small on purpose: the alternative is waiting out a stalled transfer or the
#: single-flight lock timeout, neither of which belongs in a shutdown path.
SHUTDOWN_JOIN_SECONDS = 0.5


def _set_phase(phase: str, error: Optional[str] = None) -> None:
    global _phase, _boot_error
    with _phase_lock:
        _phase = phase
        _boot_error = error


def _install_if_wanted(adapter: Any, report: Any) -> bool:
    """Install only while the lifespan is still up. Returns whether it did.

    Taken under `_phase_lock`, the same lock shutdown uses to clear
    `_accepting_installs`, so the two cannot interleave: a boot finishing at
    the moment of shutdown is either installed (and then cleared normally) or
    refused, never installed into a torn-down process.
    """
    with _phase_lock:
        if not _accepting_installs:
            return False
        state.install(adapter, report)
        return True


def boot_phase() -> str:
    """Where the snapshot boot has got to. One of the PHASE_* constants."""
    with _phase_lock:
        return _phase


def boot_error() -> Optional[str]:
    """Why the boot failed, or None."""
    with _phase_lock:
        return _boot_error


def snapshot_boot_requested() -> bool:
    """Whether either flag asks for a materialization this process.

    Serving implies booting; shadow booting does not imply serving.
    """
    return ppd_snapshot_enabled() or ppd_snapshot_shadow_enabled()


def _close_quietly(adapter: Any) -> None:
    """Close an adapter that will never be installed. Shutdown must not raise."""
    close = getattr(adapter, "close", None)
    if callable(close):
        try:
            close()
        except Exception:  # noqa: BLE001
            pass


def _build_source() -> Any:
    from property_core.snapshot.source import HttpObjectSource, LocalDirectorySource

    directory = os.getenv(SNAPSHOT_DIR_ENV)
    url = os.getenv(SNAPSHOT_URL_ENV)
    bucket = os.getenv(SNAPSHOT_BUCKET_ENV)
    if bucket and (directory or url):
        raise RuntimeError(
            f"{SNAPSHOT_BUCKET_ENV} cannot be combined with {SNAPSHOT_DIR_ENV} or "
            f"{SNAPSHOT_URL_ENV}; configure exactly one PPD snapshot source"
        )
    if bucket:
        from property_core.snapshot.s3_source import TigrisObjectSource

        return TigrisObjectSource(
            bucket,
            prefix=os.getenv("PPD_SNAPSHOT_S3_PREFIX") or "ppd",
            access_key=os.getenv("PPD_SNAPSHOT_S3_ACCESS_KEY_ID", ""),
            secret_key=os.getenv("PPD_SNAPSHOT_S3_SECRET_ACCESS_KEY", ""),
        )
    if directory:
        return LocalDirectorySource(Path(directory))
    if not url:
        raise RuntimeError(
            f"{SNAPSHOT_URL_ENV}, {SNAPSHOT_DIR_ENV} or {SNAPSHOT_BUCKET_ENV} must be set when "
            f"PPD_SNAPSHOT_ENABLED is on"
        )
    return HttpObjectSource(url)


def _materialize() -> Any:
    """Fetch, verify, validate and install. Raises; the caller degrades.

    Split out as its own function so the lifespan's failure policy is visible in
    one place, and so tests can substitute a materialization without standing up
    an object store.

    Returns the runtime's `BootReport` when it produced one, so a boot that
    fails without installing can still report *why*. The report is otherwise
    only reachable through `state.install()`, which by definition does not run
    on a failed boot -- so without this the status said merely "no snapshot
    materialized" while the real cause sat in the logs.
    """
    from property_core.snapshot.adapter import SnapshotAdapter
    from property_core.snapshot.runtime import SnapshotRuntime
    from property_core.snapshot.store import SnapshotStore

    store = SnapshotStore(os.getenv(SNAPSHOT_CACHE_ENV, DEFAULT_CACHE_DIR))
    runtime = SnapshotRuntime(source=_build_source(), store=store)
    report = runtime.boot()

    if not report.ready or not report.snapshot_dir or not report.version:
        log.warning("snapshot boot did not produce a snapshot; using the live "
                    "source (%s)", report.source_error)
        return report

    record = store.verified_record(report.version)
    if record is None:
        log.warning("snapshot %s has no readable verification record; using the "
                    "live source", report.version)
        return report

    # READY is structural. This is where it becomes eligible to route:
    # schema, row count and an executed query, all before anything is served.
    # Eligible, not routing -- `state.active_adapter()` still consults
    # PPD_SNAPSHOT_ENABLED on every call, so under shadow alone this adapter is
    # installed and never handed to a request.
    adapter = SnapshotAdapter.open(Path(report.snapshot_dir), record)

    if not _install_if_wanted(adapter, report):
        # Shutdown abandoned this boot while it was in flight. Installing now
        # would leak an open handle into a torn-down process.
        _close_quietly(adapter)
        log.info("snapshot boot completed after shutdown; discarded")
        return report

    log.info("snapshot %s validated (coverage %s..%s); routable=%s",
             adapter.version, adapter.coverage_from, adapter.coverage_to,
             ppd_snapshot_enabled())
    return report


def boot_once() -> None:
    """Attempt the boot at most once per process. Never raises.

    Runs in a worker thread, off the event loop. Nothing here is allowed to
    propagate: a snapshot that cannot be materialized means the live source
    answers, which is the documented steady state after every restart anyway.
    """
    global _booted
    if _booted:
        return
    _booted = True
    if not snapshot_boot_requested():
        return

    _set_phase(PHASE_WARMING)
    report = None
    try:
        report = _materialize()
    except Exception as exc:  # noqa: BLE001
        _set_phase(PHASE_FAILED, f"{type(exc).__name__}: {exc}")
        log.warning("snapshot boot failed (%s: %s); serving from the live source",
                    type(exc).__name__, exc)
        return

    if state.installed_adapter() is None:
        # `_materialize` returns without installing when the runtime could not
        # produce a usable snapshot. That is a failed boot, not a ready one --
        # and the returned report carries why, which `state.boot_report()`
        # cannot, since nothing was installed.
        detail = (getattr(report, "source_error", None)
                  or getattr(state.boot_report(), "source_error", None)
                  or "no snapshot materialized")
        _set_phase(PHASE_FAILED, detail)
        return

    _set_phase(PHASE_READY)


def _install_is_still_wanted() -> bool:
    with _phase_lock:
        return _accepting_installs


def reset_for_tests() -> None:
    """Forget that a boot was attempted. Test-only."""
    global _booted
    _booted = False
    _set_phase(PHASE_NOT_STARTED)
    state.clear()


@asynccontextmanager
async def snapshot_lifespan() -> AsyncIterator[None]:
    """Startup/shutdown for the snapshot source.

    Installed on both FastMCP servers. `app/main.py` awaits the FastMCP lifespan
    from inside the FastAPI lifespan, so the mounted deployment boots exactly
    once too.

    **The boot does not gate readiness.** Phase D measured 36.7 s of
    materialization plus 3.1 s of validation on the real 2 GB Machine; awaiting
    that here made the 30 s readiness target unreachable by construction. The
    boot is started as a background task and the lifespan yields immediately,
    so the application serves live data from the first request while the
    snapshot warms behind it.

    The single-flight `flock` is unchanged -- it still coordinates the worker
    processes sharing a Machine, which lifespan wiring cannot.
    """
    global _accepting_installs, _boot_thread, _phase

    if not snapshot_boot_requested():
        # Neither flag: import nothing, touch nothing, start nothing.
        try:
            yield
        finally:
            state.clear()
        return

    # A plain daemon thread, not an anyio task group. The boot does blocking
    # I/O -- a socket read and an flock wait of up to lock.DEFAULT_TIMEOUT --
    # which no cancellation can interrupt, so a task group would only be able
    # to stop *waiting* for it anyway. Worse, cancelling a task-group scope
    # from the `finally` of an async context manager deadlocks when the
    # lifespan runs in a portal task, which is exactly what Starlette's
    # TestClient and uvicorn's startup do. A thread has none of that coupling
    # and behaves identically under uvicorn, TestClient, FastMCP and the CLI.
    with _phase_lock:
        _accepting_installs = True
        if _phase == PHASE_NOT_STARTED:
            # Committed to booting, so say so before yielding: a status check
            # between here and the thread's first instruction must not report
            # `not_started` when a boot is already under way.
            _phase = PHASE_WARMING

    thread = threading.Thread(target=boot_once, name="ppd-snapshot-boot", daemon=True)
    _boot_thread = thread
    thread.start()

    try:
        yield
    finally:
        # Refuse further installs *before* clearing, under the same lock the
        # installing thread takes, so a boot landing at this instant is either
        # installed-then-cleared or refused outright -- never installed into a
        # process that has already torn the snapshot down.
        with _phase_lock:
            _accepting_installs = False
        # A brief, bounded join reaps a nearly-finished boot tidily. It is
        # deliberately not a full join: shutdown must never wait out a stalled
        # transfer or the single-flight lock timeout. The thread is a daemon,
        # so anything still running dies with the process.
        thread.join(timeout=SHUTDOWN_JOIN_SECONDS)
        _boot_thread = None
        state.clear()


def fastmcp_lifespan(server: Any):
    """The lifespan callable FastMCP expects, ignoring the server argument."""
    @asynccontextmanager
    async def _lifespan(_server: Any) -> AsyncIterator[dict]:
        async with snapshot_lifespan():
            yield {}

    return _lifespan


def lifespan_is_installed(server: Any) -> bool:
    """Whether `server` runs the snapshot boot lifespan.

    Asserted by test against both MCP servers: one of them silently missing it
    would mean that deployment never boots a snapshot, and the only symptom
    would be permanently-live provenance nobody looked at.
    """
    return bool(getattr(server, "_ppd_snapshot_lifespan", False))


def mark_installed(server: Any) -> Any:
    """Record that this server carries the boot lifespan."""
    setattr(server, "_ppd_snapshot_lifespan", True)
    return server


def snapshot_status() -> dict[str, Optional[object]]:
    """A small, honest summary for health output and diagnostics.

    `routable` tracks `state.active_adapter()`, never mere installation, so it
    can only be true when `PPD_SNAPSHOT_ENABLED` is on *and* validation
    completed. Under shadow alone the artifact identity is reported and
    `routable` stays false -- that pairing is the whole point of the mode.
    """
    adapter = state.installed_adapter()
    report = state.boot_report()
    common: dict[str, Optional[object]] = {
        "enabled": ppd_snapshot_enabled(),
        "shadow_enabled": ppd_snapshot_shadow_enabled(),
        "state": boot_phase(),
        "routable": state.active_adapter() is not None,
    }
    if adapter is None:
        return {
            **common,
            "source_error": boot_error() or getattr(report, "source_error", None),
        }
    return {
        **common,
        "source_error": boot_error() or getattr(report, "source_error", None),
        "version": adapter.version,
        "coverage_from": adapter.coverage_from,
        "coverage_to": adapter.coverage_to,
        "behind_advertised_release": getattr(report, "behind_advertised_release",
                                             False),
    }
