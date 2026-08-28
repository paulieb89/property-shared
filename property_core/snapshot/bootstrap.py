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
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from property_core.config import ppd_snapshot_enabled
from property_core.snapshot import state

log = logging.getLogger("property_core.snapshot.boot")

#: Where the bundle is published. A local directory is supported so the whole
#: path can be exercised without any network or cloud resource.
SNAPSHOT_URL_ENV = "PPD_SNAPSHOT_URL"
SNAPSHOT_DIR_ENV = "PPD_SNAPSHOT_DIR"
#: Where it is materialized. Ephemeral: Fly's default rootfs, wiped on restart.
SNAPSHOT_CACHE_ENV = "PPD_SNAPSHOT_CACHE_DIR"
DEFAULT_CACHE_DIR = "/tmp/ppd-snapshot"

#: Set once the boot has been attempted in this process. Idempotence is by
#: attempt, not by success: a failed boot must not be retried by every worker
#: thread that happens to call the lifespan again.
_booted = False


def _build_source() -> Any:
    from property_core.snapshot.source import HttpObjectSource, LocalDirectorySource

    directory = os.getenv(SNAPSHOT_DIR_ENV)
    if directory:
        return LocalDirectorySource(Path(directory))
    url = os.getenv(SNAPSHOT_URL_ENV)
    if not url:
        raise RuntimeError(
            f"{SNAPSHOT_URL_ENV} or {SNAPSHOT_DIR_ENV} must be set when "
            f"PPD_SNAPSHOT_ENABLED is on"
        )
    return HttpObjectSource(url)


def _materialize() -> None:
    """Fetch, verify, validate and install. Raises; the caller degrades.

    Split out as its own function so the lifespan's failure policy is visible in
    one place, and so tests can substitute a materialization without standing up
    an object store.
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
        return

    record = store.verified_record(report.version)
    if record is None:
        log.warning("snapshot %s has no readable verification record; using the "
                    "live source", report.version)
        return

    # READY is structural. This is where it becomes permission to route:
    # schema, row count and an executed query, all before anything is served.
    adapter = SnapshotAdapter.open(Path(report.snapshot_dir), record)
    state.install(adapter, report)
    log.info("snapshot %s validated and routable (coverage %s..%s)",
             adapter.version, adapter.coverage_from, adapter.coverage_to)


def boot_once() -> None:
    """Attempt the boot at most once per process. Never raises."""
    global _booted
    if _booted:
        return
    _booted = True
    if not ppd_snapshot_enabled():
        return
    try:
        _materialize()
    except Exception as exc:  # noqa: BLE001
        # The server must come up. A snapshot that cannot be materialized or
        # validated means the live source answers, which is the documented
        # steady state after every restart anyway.
        log.warning("snapshot boot failed (%s: %s); serving from the live source",
                    type(exc).__name__, exc)


def reset_for_tests() -> None:
    """Forget that a boot was attempted. Test-only."""
    global _booted
    _booted = False
    state.clear()


@asynccontextmanager
async def snapshot_lifespan() -> AsyncIterator[None]:
    """Startup/shutdown for the snapshot source.

    Installed on both FastMCP servers. `app/main.py` awaits the FastMCP lifespan
    from inside the FastAPI lifespan, so the mounted deployment boots exactly
    once too.
    """
    import anyio.to_thread

    # The boot does blocking I/O -- network, disk, and a flock wait of up to
    # LOCK_WAIT_SECONDS. Off the event loop so a co-hosted FastAPI app is not
    # frozen while a sibling worker holds the single-flight lock.
    await anyio.to_thread.run_sync(boot_once)
    try:
        yield
    finally:
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
    """A small, honest summary for health output and diagnostics."""
    adapter = state.installed_adapter()
    report = state.boot_report()
    if adapter is None:
        return {
            "enabled": ppd_snapshot_enabled(),
            "routable": False,
            "source_error": getattr(report, "source_error", None),
        }
    return {
        "enabled": ppd_snapshot_enabled(),
        "routable": state.active_adapter() is not None,
        "version": adapter.version,
        "coverage_from": adapter.coverage_from,
        "coverage_to": adapter.coverage_to,
        "behind_advertised_release": getattr(report, "behind_advertised_release",
                                             False),
    }
