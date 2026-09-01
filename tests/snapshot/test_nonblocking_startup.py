"""Non-blocking snapshot startup -- the lifecycle Phase D showed we need.

Phase D measured 36.7 s of materialization plus 3.1 s of validation on the real
`property-shared` Machine. Under the previous design that time sat inside the
ASGI lifespan, so the 30 s readiness target could not be met by construction:
the application was not ready until the download finished.

This module pins the replacement. The boot moves to a background task; the
application is ready immediately, serving live data; the snapshot becomes
*routable* only once it has materialized, validated, **and** `PPD_SNAPSHOT_ENABLED`
is on. A second, control-only flag `PPD_SNAPSHOT_SHADOW_ENABLED` starts the same
boot without ever making it routable, which is what lets G1a be completed
against the real application lifecycle without serving a single snapshot row.

The invariant that must not bend: **`PPD_SNAPSHOT_ENABLED` remains the sole
authority to route.** Shadow mode changes when work happens, never what a user
request is answered from.
"""

from __future__ import annotations

import threading
import time

import anyio
import pytest

from property_core.snapshot import bootstrap, state


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    monkeypatch.delenv("PPD_SNAPSHOT_ENABLED", raising=False)
    monkeypatch.delenv("PPD_SNAPSHOT_SHADOW_ENABLED", raising=False)
    bootstrap.reset_for_tests()
    yield
    bootstrap.reset_for_tests()


class FakeAdapter:
    """Stands in for a validated SnapshotAdapter."""

    def __init__(self, version: str = "v20260828T194003Z") -> None:
        self.version = version
        self.coverage_from = "2016-01-01"
        self.coverage_to = "2026-06-30"
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeReport:
    source_error = None
    behind_advertised_release = False


async def _wait_for_phase(expected: set[str], timeout: float = 5.0) -> str:
    """Await until the boot reaches one of `expected`, or fail the test.

    Deliberately async: the boot task is scheduled with `start_soon`, so it
    does not run until the event loop yields. A blocking `time.sleep` here
    would starve the very task under test and every assertion would fail for
    the wrong reason. A real ASGI server yields constantly; this mirrors that.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        phase = bootstrap.boot_phase()
        if phase in expected:
            return phase
        await anyio.sleep(0.01)
    raise AssertionError(
        f"boot phase {bootstrap.boot_phase()!r} never reached one of {expected}"
    )


async def _await_event(event: threading.Event, timeout: float = 5.0) -> None:
    """Await a threading.Event without blocking the loop.

    Needed because `boot_phase() == "warming"` is set synchronously when the
    lifespan commits to booting, so it does NOT prove the worker thread has
    started. A shutdown test that only waited for "warming" could cancel
    before the thread was ever dispatched and pass without exercising
    anything.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if event.is_set():
            return
        await anyio.sleep(0.01)
    raise AssertionError("event was never set")


def _install_fake(adapter: FakeAdapter | None = None) -> FakeAdapter:
    adapter = adapter or FakeAdapter()
    state.install(adapter, FakeReport())
    return adapter


# ---------------------------------------------------------------------------
# Readiness is not gated on the download
# ---------------------------------------------------------------------------


def test_slow_materialisation_does_not_delay_application_readiness(monkeypatch):
    """The headline requirement: readiness must not await the transfer.

    Under the old design this test would block for the full sleep, because the
    lifespan awaited the boot before yielding.
    """
    monkeypatch.setenv("PPD_SNAPSHOT_SHADOW_ENABLED", "1")
    release = threading.Event()

    def _slow():
        # Far longer than the 30 s target; if readiness awaits this, the test
        # fails loudly on elapsed time rather than hanging forever.
        release.wait(timeout=10.0)
        _install_fake()

    monkeypatch.setattr(bootstrap, "_materialize", _slow)

    elapsed: list[float] = []

    async def _run():
        started = time.monotonic()
        async with bootstrap.snapshot_lifespan():
            elapsed.append(time.monotonic() - started)
            release.set()

    anyio.run(_run)

    assert elapsed and elapsed[0] < 1.0, (
        f"readiness waited {elapsed[0]:.2f}s for the snapshot boot"
    )


def test_application_is_ready_while_the_boot_is_still_warming(monkeypatch):
    monkeypatch.setenv("PPD_SNAPSHOT_SHADOW_ENABLED", "1")
    release = threading.Event()
    monkeypatch.setattr(bootstrap, "_materialize", lambda: release.wait(timeout=10.0))

    observed: list[str] = []

    async def _run():
        async with bootstrap.snapshot_lifespan():
            observed.append(await _wait_for_phase({"warming"}))
            release.set()

    anyio.run(_run)

    assert observed == ["warming"]


def test_live_source_answers_while_the_snapshot_is_warming(monkeypatch):
    """Warming must not route, and must not withhold an answer."""
    monkeypatch.setenv("PPD_SNAPSHOT_ENABLED", "1")
    monkeypatch.setenv("PPD_SNAPSHOT_SHADOW_ENABLED", "1")
    release = threading.Event()
    monkeypatch.setattr(bootstrap, "_materialize", lambda: release.wait(timeout=10.0))

    routable_while_warming: list[bool] = []

    async def _run():
        async with bootstrap.snapshot_lifespan():
            await _wait_for_phase({"warming"})
            routable_while_warming.append(state.active_adapter() is not None)
            release.set()

    anyio.run(_run)

    assert routable_while_warming == [False], "warming must fall through to live"


# ---------------------------------------------------------------------------
# Exactly one boot
# ---------------------------------------------------------------------------


def test_boot_runs_exactly_once_per_process(monkeypatch):
    monkeypatch.setenv("PPD_SNAPSHOT_SHADOW_ENABLED", "1")
    calls: list[int] = []
    monkeypatch.setattr(bootstrap, "_materialize", lambda: calls.append(1))

    async def _run():
        async with bootstrap.snapshot_lifespan():
            await _wait_for_phase({"ready", "failed"})
        # A second lifespan in the same process must not boot again.
        async with bootstrap.snapshot_lifespan():
            pass

    anyio.run(_run)

    assert calls == [1]


# ---------------------------------------------------------------------------
# Failure is recorded, never fatal
# ---------------------------------------------------------------------------


def test_boot_failure_is_recorded_and_never_raises(monkeypatch):
    monkeypatch.setenv("PPD_SNAPSHOT_SHADOW_ENABLED", "1")

    def _boom():
        raise RuntimeError("tigris unreachable")

    monkeypatch.setattr(bootstrap, "_materialize", _boom)

    async def _run():
        async with bootstrap.snapshot_lifespan():
            await _wait_for_phase({"failed"})

    anyio.run(_run)  # must not raise

    assert bootstrap.boot_phase() == "failed"
    assert "tigris unreachable" in (bootstrap.boot_error() or "")


def test_serving_stays_live_after_a_boot_failure(monkeypatch):
    monkeypatch.setenv("PPD_SNAPSHOT_ENABLED", "1")
    monkeypatch.setenv("PPD_SNAPSHOT_SHADOW_ENABLED", "1")
    monkeypatch.setattr(bootstrap, "_materialize",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    routable: list[bool] = []

    async def _run():
        async with bootstrap.snapshot_lifespan():
            await _wait_for_phase({"failed"})
            routable.append(state.active_adapter() is not None)

    anyio.run(_run)

    assert routable == [False]


# ---------------------------------------------------------------------------
# Shadow mode never routes
# ---------------------------------------------------------------------------


def test_shadow_mode_materialises_but_never_routes(monkeypatch):
    """The whole point of the shadow flag: do the work, serve none of it."""
    monkeypatch.setenv("PPD_SNAPSHOT_SHADOW_ENABLED", "1")
    monkeypatch.delenv("PPD_SNAPSHOT_ENABLED", raising=False)
    monkeypatch.setattr(bootstrap, "_materialize", _install_fake)

    seen: dict[str, object] = {}

    async def _run():
        async with bootstrap.snapshot_lifespan():
            await _wait_for_phase({"ready"})
            seen["installed"] = state.installed_adapter() is not None
            seen["routable"] = state.active_adapter() is not None
            seen["status"] = bootstrap.snapshot_status()

    anyio.run(_run)

    assert seen["installed"] is True, "shadow mode must actually materialize"
    assert seen["routable"] is False, "shadow mode must never route"
    status = seen["status"]
    assert status["routable"] is False
    assert status["enabled"] is False
    assert status["shadow_enabled"] is True
    assert status["state"] == "ready"


def test_shadow_flag_alone_does_not_make_the_adapter_routable(monkeypatch):
    monkeypatch.setenv("PPD_SNAPSHOT_SHADOW_ENABLED", "1")
    monkeypatch.delenv("PPD_SNAPSHOT_ENABLED", raising=False)
    _install_fake()

    assert state.installed_adapter() is not None
    assert state.active_adapter() is None


def test_validated_adapter_becomes_routable_only_when_serving_is_enabled(monkeypatch):
    """PPD_SNAPSHOT_ENABLED is the sole routing authority, read per call."""
    monkeypatch.setenv("PPD_SNAPSHOT_SHADOW_ENABLED", "1")
    monkeypatch.delenv("PPD_SNAPSHOT_ENABLED", raising=False)
    _install_fake()

    assert state.active_adapter() is None

    monkeypatch.setenv("PPD_SNAPSHOT_ENABLED", "1")
    assert state.active_adapter() is not None

    monkeypatch.setenv("PPD_SNAPSHOT_ENABLED", "0")
    assert state.active_adapter() is None


# ---------------------------------------------------------------------------
# Neither flag: nothing happens at all
# ---------------------------------------------------------------------------


def test_neither_flag_boots_nothing(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(bootstrap, "_materialize", lambda: calls.append(1))

    async def _run():
        async with bootstrap.snapshot_lifespan():
            pass

    anyio.run(_run)

    assert calls == []
    assert state.active_adapter() is None
    assert bootstrap.boot_phase() == "not_started"


def test_serving_flag_alone_still_boots(monkeypatch):
    """The serving flag must keep working on its own -- shadow is additive."""
    monkeypatch.setenv("PPD_SNAPSHOT_ENABLED", "1")
    monkeypatch.delenv("PPD_SNAPSHOT_SHADOW_ENABLED", raising=False)
    monkeypatch.setattr(bootstrap, "_materialize", _install_fake)

    async def _run():
        async with bootstrap.snapshot_lifespan():
            await _wait_for_phase({"ready"})

    anyio.run(_run)

    assert bootstrap.boot_phase() == "ready"


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------


def test_shutdown_closes_the_installed_adapter(monkeypatch):
    monkeypatch.setenv("PPD_SNAPSHOT_SHADOW_ENABLED", "1")
    adapter = FakeAdapter()
    monkeypatch.setattr(bootstrap, "_materialize", lambda: _install_fake(adapter))

    async def _run():
        async with bootstrap.snapshot_lifespan():
            await _wait_for_phase({"ready"})

    anyio.run(_run)

    assert adapter.closed is True
    assert state.installed_adapter() is None


def test_shutdown_does_not_wait_for_a_stuck_boot(monkeypatch):
    """A shutdown must not hang for the lock timeout or a slow transfer."""
    monkeypatch.setenv("PPD_SNAPSHOT_SHADOW_ENABLED", "1")
    release = threading.Event()
    entered = threading.Event()

    def _stuck():
        entered.set()
        release.wait(timeout=10.0)

    monkeypatch.setattr(bootstrap, "_materialize", _stuck)

    elapsed: list[float] = []

    async def _run():
        started = time.monotonic()
        async with bootstrap.snapshot_lifespan():
            # The boot must genuinely be in flight, not merely scheduled.
            await _await_event(entered)
        elapsed.append(time.monotonic() - started)

    try:
        anyio.run(_run)
    finally:
        release.set()

    assert elapsed and elapsed[0] < 2.0, (
        f"shutdown blocked {elapsed[0]:.2f}s on the in-flight boot"
    )


def test_a_boot_finishing_after_shutdown_does_not_install(monkeypatch):
    """The abandoned worker must not resurrect state after clear().

    A boot thread blocked in a socket read cannot be interrupted, so a slow
    boot really does keep running after shutdown abandons it. Without a guard
    it would install an adapter into a process that has already torn the
    snapshot down, leaking an open DuckDB handle.

    This drives the **real** `bootstrap._materialize`, patching only the
    collaborators it imports. An earlier version of this test replaced
    `_materialize` with a fake that re-implemented the gate itself; deleting
    the production check then broke nothing, because the assertions were
    exercising the fake. Mutation testing caught that. The seam is now
    `SnapshotAdapter.open`, which is the call immediately before the gate.
    """
    import property_core.snapshot.adapter as adapter_module
    import property_core.snapshot.runtime as runtime_module
    import property_core.snapshot.store as store_module

    monkeypatch.setenv("PPD_SNAPSHOT_SHADOW_ENABLED", "1")

    adapter = FakeAdapter()
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    class _Report:
        ready = True
        snapshot_dir = "/nonexistent/snapshot"
        version = "v20260828T194003Z"
        source_error = None
        behind_advertised_release = False

    class _Store:
        def __init__(self, *_a, **_k) -> None:
            pass

        def verified_record(self, _version):
            return object()

    class _Runtime:
        def __init__(self, *_a, **_k) -> None:
            pass

        def boot(self):
            return _Report()

    class _Adapter:
        @staticmethod
        def open(_directory, _record):
            # Blocks exactly where the real adapter-open validation would, so
            # shutdown lands between `open` returning and the install gate.
            entered.set()
            release.wait(timeout=10.0)
            finished.set()
            return adapter

    monkeypatch.setattr(bootstrap, "_build_source", lambda: object())
    monkeypatch.setattr(store_module, "SnapshotStore", _Store)
    monkeypatch.setattr(runtime_module, "SnapshotRuntime", _Runtime)
    monkeypatch.setattr(adapter_module, "SnapshotAdapter", _Adapter)

    async def _run():
        async with bootstrap.snapshot_lifespan():
            await _await_event(entered)

    anyio.run(_run)

    release.set()
    assert finished.wait(timeout=5.0), "the abandoned boot never finished"
    # The install happens just after open() returns; give the thread a moment.
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and not adapter.closed:
        time.sleep(0.01)

    assert state.installed_adapter() is None, (
        "a boot completing after shutdown installed into a torn-down process"
    )
    assert adapter.closed is True, "the late adapter was left open"


# ---------------------------------------------------------------------------
# Status reporting
# ---------------------------------------------------------------------------


def test_status_reports_not_started_before_any_boot(monkeypatch):
    status = bootstrap.snapshot_status()

    assert status["state"] == "not_started"
    assert status["enabled"] is False
    assert status["shadow_enabled"] is False
    assert status["routable"] is False


def test_status_reports_failure_with_the_error(monkeypatch):
    monkeypatch.setenv("PPD_SNAPSHOT_SHADOW_ENABLED", "1")
    monkeypatch.setattr(bootstrap, "_materialize",
                        lambda: (_ for _ in ()).throw(RuntimeError("403 from tigris")))

    status: dict = {}

    async def _run():
        async with bootstrap.snapshot_lifespan():
            await _wait_for_phase({"failed"})
            status.update(bootstrap.snapshot_status())

    anyio.run(_run)

    assert status["state"] == "failed"
    assert status["routable"] is False
    assert "403 from tigris" in (status["source_error"] or "")


def test_status_carries_artifact_identity_once_ready(monkeypatch):
    monkeypatch.setenv("PPD_SNAPSHOT_ENABLED", "1")
    monkeypatch.setenv("PPD_SNAPSHOT_SHADOW_ENABLED", "1")
    monkeypatch.setattr(bootstrap, "_materialize", _install_fake)

    status: dict = {}

    async def _run():
        async with bootstrap.snapshot_lifespan():
            await _wait_for_phase({"ready"})
            status.update(bootstrap.snapshot_status())

    anyio.run(_run)

    assert status["state"] == "ready"
    assert status["version"] == "v20260828T194003Z"
    assert status["coverage_from"] == "2016-01-01"
    assert status["coverage_to"] == "2026-06-30"
    assert status["routable"] is True


def test_status_is_never_routable_without_the_serving_flag(monkeypatch):
    """Belt and braces: routable must track active_adapter(), not installation."""
    monkeypatch.setenv("PPD_SNAPSHOT_SHADOW_ENABLED", "1")
    monkeypatch.delenv("PPD_SNAPSHOT_ENABLED", raising=False)
    _install_fake()

    status = bootstrap.snapshot_status()

    assert status["routable"] is False
    assert status["version"] == "v20260828T194003Z", "identity is still reported"


def test_status_reports_why_the_source_failed_not_just_that_it_did(monkeypatch):
    """A not-ready boot must surface the runtime's own source_error.

    Observed in the built image: shadow mode against an unreachable source
    reported `source_error: "no snapshot materialized"`, which says only that
    nothing happened. The runtime knew the real reason and it was dropped,
    because the report is stored by `state.install()` -- which never runs on a
    failed boot.
    """
    import property_core.snapshot.runtime as runtime_module
    import property_core.snapshot.store as store_module

    monkeypatch.setenv("PPD_SNAPSHOT_SHADOW_ENABLED", "1")

    class _Report:
        ready = False
        snapshot_dir = None
        version = None
        source_error = "ConnectionRefusedError: [Errno 111] Connection refused"
        behind_advertised_release = False

    class _Store:
        def __init__(self, *_a, **_k) -> None:
            pass

    class _Runtime:
        def __init__(self, *_a, **_k) -> None:
            pass

        def boot(self):
            return _Report()

    monkeypatch.setattr(bootstrap, "_build_source", lambda: object())
    monkeypatch.setattr(store_module, "SnapshotStore", _Store)
    monkeypatch.setattr(runtime_module, "SnapshotRuntime", _Runtime)

    status: dict = {}

    async def _run():
        async with bootstrap.snapshot_lifespan():
            await _wait_for_phase({"failed"})
            status.update(bootstrap.snapshot_status())

    anyio.run(_run)

    assert status["state"] == "failed"
    assert "Connection refused" in (status["source_error"] or ""), status["source_error"]
