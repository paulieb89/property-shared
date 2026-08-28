"""Where the runtime is started -- spec section 4.10, the governing rule for PR 4.

The rules and why each exists:

* **Boot once per server process, through the FastMCP lifespan.** Not per
  request, not lazily on first use: a lazy boot puts a 20-second download in the
  path of whichever request happens to arrive first.
* **Combine the lifespans explicitly where the MCP app is mounted alongside
  FastAPI.** Mounting does not chain them, and a lifespan that is never awaited
  is a boot that never happens.
* **Process-scoped state, never MCP session state.** Session state is client-
  and session-scoped; the materialization belongs to the Machine. Storing it per
  session would re-boot per client and leak across reconnects.
* **A startup failure leaves the server serving from live.** UNREADY is a normal
  outcome, not a startup error.
"""

from __future__ import annotations

import anyio
import pytest

from property_core.snapshot import bootstrap, state


@pytest.fixture(autouse=True)
def _clean_state():
    bootstrap.reset_for_tests()
    yield
    bootstrap.reset_for_tests()


def test_flag_off_boots_nothing(monkeypatch):
    monkeypatch.delenv("PPD_SNAPSHOT_ENABLED", raising=False)
    calls: list[int] = []
    monkeypatch.setattr(bootstrap, "_materialize", lambda: calls.append(1))

    async def _run():
        async with bootstrap.snapshot_lifespan():
            pass

    anyio.run(_run)
    assert calls == []
    assert state.active_adapter() is None


def test_flag_off_imports_no_duckdb(monkeypatch):
    """Deferred from PR 1 (§7.1): with no adapter installed nothing imports duckdb.

    Run in a clean subprocess with an import blocker: asserting against
    `sys.modules` in the shared test process passes vacuously as soon as any
    earlier test has imported DuckDB.
    """
    import subprocess
    import sys

    program = """
import sys

class Blocker:
    def find_module(self, name, path=None):
        return self.find_spec(name, path)
    def find_spec(self, name, path=None, target=None):
        if name == "duckdb" or name.startswith("duckdb."):
            raise ImportError("duckdb import blocked for this test")
        return None

sys.meta_path.insert(0, Blocker())
try:
    import duckdb
except ImportError:
    pass
else:
    raise SystemExit("blocker is not armed")

import anyio
from property_core.snapshot import bootstrap
from property_core.ppd_service import PPDService

async def main():
    async with bootstrap.snapshot_lifespan():
        assert PPDService()._active_adapter() is None

anyio.run(main)
print("OK")
"""
    env = {"PATH": "/usr/bin:/bin", "PPD_SNAPSHOT_ENABLED": "0"}
    proc = subprocess.run([sys.executable, "-c", program], capture_output=True,
                          text=True, env=env)
    assert proc.returncode == 0, proc.stderr
    assert "OK" in proc.stdout


def test_flag_off_never_imports_the_snapshot_package_on_a_request_path():
    """The flag is checked before the import, not after.

    Run in a clean subprocess: `sys.modules` in the shared test process is
    already full of snapshot modules from other tests, so an in-process
    assertion would pass vacuously.
    """
    import subprocess
    import sys

    program = """
import sys
from property_core.ppd_source import active_adapter

assert active_adapter() is None
imported = [m for m in sys.modules if m.startswith("property_core.snapshot")]
assert imported == [], imported
print("OK")
"""
    proc = subprocess.run([sys.executable, "-c", program], capture_output=True,
                          text=True, env={"PATH": "/usr/bin:/bin",
                                          "PPD_SNAPSHOT_ENABLED": "0"})
    assert proc.returncode == 0, proc.stderr
    assert "OK" in proc.stdout


def test_boot_runs_exactly_once_per_process(monkeypatch):
    monkeypatch.setenv("PPD_SNAPSHOT_ENABLED", "1")
    calls: list[int] = []
    monkeypatch.setattr(bootstrap, "_materialize", lambda: calls.append(1))

    async def _run():
        async with bootstrap.snapshot_lifespan():
            async with bootstrap.snapshot_lifespan():
                pass

    anyio.run(_run)
    assert calls == [1]


def test_boot_failure_leaves_the_server_up_on_live(monkeypatch):
    monkeypatch.setenv("PPD_SNAPSHOT_ENABLED", "1")

    def _explode():
        raise RuntimeError("object store unreachable")

    monkeypatch.setattr(bootstrap, "_materialize", _explode)

    async def _run():
        async with bootstrap.snapshot_lifespan():
            assert state.active_adapter() is None

    anyio.run(_run)  # must not raise


def test_state_is_module_scoped_not_session_scoped():
    """A session store would re-boot per client and leak across reconnects."""
    import inspect

    source = inspect.getsource(state)
    assert "session" not in source.lower() or "never" in source.lower()
    assert not hasattr(state, "set_session_state")


def test_fastmcp_servers_declare_the_boot_lifespan():
    """Both MCP servers must carry it, or one of them never boots."""
    from app.mcp.server import mcp as plain_server
    from property_app.server import mcp as app_server

    for server in (plain_server, app_server):
        assert bootstrap.lifespan_is_installed(server), (
            f"{server.name} does not run the snapshot boot lifespan")


def test_fastapi_lifespan_explicitly_awaits_the_mcp_lifespan():
    """Mounting does not chain lifespans; app/main.py must combine them."""
    import inspect

    from app import main

    source = inspect.getsource(main.lifespan)
    assert "_mcp_http_app.lifespan" in source


def test_asgi_startup_boots_the_snapshot_once(monkeypatch):
    """The end-to-end assertion: serving the app actually runs the boot."""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("PPD_SNAPSHOT_ENABLED", "1")
    calls: list[int] = []
    monkeypatch.setattr(bootstrap, "_materialize", lambda: calls.append(1))

    from app.main import create_app

    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
    assert calls == [1]


def test_shutdown_releases_the_adapter(monkeypatch, tmp_path):
    """A process that stops serving must not hold a DuckDB connection open."""
    pytest.importorskip("duckdb", reason="needs the optional 'snapshot' extra")

    from property_core.snapshot.adapter import SnapshotAdapter
    from tests.snapshot.snapshot_fixtures import build_snapshot, default_rows

    monkeypatch.setenv("PPD_SNAPSHOT_ENABLED", "1")
    directory, record = build_snapshot(tmp_path, default_rows())
    adapter = SnapshotAdapter.open(directory, record)
    monkeypatch.setattr(bootstrap, "_materialize", lambda: state.install(adapter))

    async def _run():
        async with bootstrap.snapshot_lifespan():
            assert state.active_adapter() is adapter

    anyio.run(_run)
    assert state.active_adapter() is None
    assert adapter.closed is True
