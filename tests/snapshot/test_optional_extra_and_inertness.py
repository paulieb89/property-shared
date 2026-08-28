"""The extra is optional, the flag is off, and PR 3 changes no behaviour."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

BLOCKER = """
import sys

class _DuckDBBlocker:
    def find_module(self, fullname, path=None):
        return self.find_spec(fullname, path)
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "duckdb" or fullname.startswith("duckdb."):
            raise ImportError("No module named 'duckdb' (blocked by test)")
        return None

sys.meta_path.insert(0, _DuckDBBlocker())
sys.modules.pop("duckdb", None)
"""


def _blocked(body: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", BLOCKER + textwrap.dedent(body)],
                          cwd=REPO, capture_output=True, text=True, timeout=180)


def test_the_blocker_actually_blocks():
    proc = _blocked("""
        try:
            import duckdb; print("NOT_BLOCKED")
        except ImportError: print("BLOCKED")
    """)
    assert proc.stdout.strip() == "BLOCKED", proc.stderr[-1500:]


def test_the_whole_snapshot_runtime_imports_without_duckdb():
    proc = _blocked("""
        import property_core.snapshot as s
        from property_core.snapshot.runtime import SnapshotRuntime
        from property_core.snapshot.store import SnapshotStore
        from property_core.snapshot.fetch import download_verified
        from property_core.snapshot.archive import safe_extract
        from property_core.snapshot.lock import single_flight
        print("OK", len(s.__all__))
    """)
    assert proc.returncode == 0, proc.stderr[-2500:]
    assert "OK" in proc.stdout


def test_a_full_boot_runs_without_duckdb(tmp_path):
    """PR 3 verifies and activates; it never opens the snapshot."""
    proc = _blocked(f"""
        import hashlib, io, json, tarfile
        from pathlib import Path
        from property_core.snapshot.runtime import SnapshotRuntime
        from property_core.snapshot.store import SnapshotStore

        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            data = b"PAR1tiny"
            ti = tarfile.TarInfo("data.parquet"); ti.size = len(data)
            tar.addfile(ti, io.BytesIO(data))
        blob = buf.getvalue()
        manifest = {{"snapshot_version": "v1", "bundle_object": "snapshot-v1.tar",
                     "bundle_sha256": hashlib.sha256(blob).hexdigest(),
                     "bundle_bytes": len(blob), "parquet_files": 1, "rows": 1}}
        objects = {{"current.json": json.dumps({{"current_manifest": "m.json"}}).encode(),
                    "m.json": json.dumps(manifest).encode(),
                    "snapshot-v1.tar": blob}}

        class Src:
            def read_bytes(self, name, *, max_bytes=None): return objects[name]
            def open_stream(self, name):
                b = objects[name]
                class S:
                    declared_length = len(b)
                    def __init__(self): self.p = 0
                    def read(self, n):
                        out = b[self.p:self.p+n]; self.p += len(out); return out
                    def __enter__(self): return self
                    def __exit__(self, *e): return False
                return S()

        rt = SnapshotRuntime(source=Src(), store=SnapshotStore({str(tmp_path)!r}))
        print("READINESS", rt.boot().readiness.value)
    """)
    assert proc.returncode == 0, proc.stderr[-2500:]
    assert "READINESS ready" in proc.stdout, proc.stdout


def test_missing_extra_raises_an_actionable_typed_error():
    proc = _blocked("""
        from property_core.snapshot.duckdb_support import require_duckdb
        from property_core.snapshot.errors import SnapshotExtraMissingError
        try:
            require_duckdb()
            print("NO_ERROR")
        except SnapshotExtraMissingError as exc:
            d = exc.to_dict()
            print("CODE", d["error"]); print("EXTRA", d["extra"])
            print("MSG", str(exc))
    """)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "CODE snapshot_extra_missing" in proc.stdout
    assert "EXTRA snapshot" in proc.stdout
    # Actionable: names the feature, the package and how to install it.
    assert "property-shared[snapshot]" in proc.stdout
    assert "duckdb" in proc.stdout
    assert "PPD_SNAPSHOT_ENABLED" in proc.stdout


def test_missing_extra_error_is_not_a_bare_import_error():
    proc = _blocked("""
        from property_core.snapshot.duckdb_support import require_duckdb
        try:
            require_duckdb()
        except ImportError as exc:
            print("BARE_IMPORT_ERROR", type(exc).__name__)
        except Exception as exc:
            print("TYPED", type(exc).__name__)
    """)
    assert "TYPED SnapshotExtraMissingError" in proc.stdout, proc.stdout


# --- flag-off inertness ----------------------------------------------------

def test_the_flag_is_still_off_by_default(monkeypatch):
    monkeypatch.delenv("PPD_SNAPSHOT_ENABLED", raising=False)
    from property_core.config import ppd_snapshot_enabled

    assert ppd_snapshot_enabled() is False


def test_importing_property_core_does_not_import_the_snapshot_runtime():
    """PR 3 must not add import cost or side effects to the library's front door."""
    proc = subprocess.run(
        [sys.executable, "-c",
         "import sys, property_core; "
         "print(any(m.startswith('property_core.snapshot') for m in sys.modules))"],
        cwd=REPO, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-1500:]
    assert proc.stdout.strip() == "False", (
        "property_core eagerly imports the snapshot runtime"
    )


def test_no_request_path_boots_a_snapshot():
    """Boot happens at startup only -- never on the path of a request.

    PR 4 added routing, so these modules may now *consult* an already-installed
    adapter. What none of them may do is construct the boot runtime: that would
    put a download in the path of whichever request arrived first, which is the
    exact failure the lifespan rule (spec 4.10) exists to prevent.
    """
    import inspect

    import app.api.v1.ppd as rest
    import app.mcp.server as plain
    import property_core.ppd_service as svc
    import property_core.ppd_source as routing

    for module in (rest, plain, svc, routing):
        src = inspect.getsource(module)
        assert "SnapshotRuntime" not in src, (
            f"{module.__name__} constructs the boot runtime on a request path")


def test_only_the_bootstrap_module_constructs_the_runtime():
    """One place boots, and it is the one the lifespan calls."""
    # Walked from disk, not `git grep`: a new caller that has not been staged
    # yet is exactly the one this needs to catch.
    callers = sorted(
        str(path.relative_to(REPO))
        for package in ("property_core", "app", "property_app", "property_cli")
        for path in (REPO / package).rglob("*.py")
        if "SnapshotRuntime(" in path.read_text()
    )
    assert callers == ["property_core/snapshot/bootstrap.py"], callers


def test_the_snapshot_extra_declares_a_zstd_reader():
    """The bundle is .tar.zst; py3.11 has no stdlib zstd and the slim images
    ship no zstd binary, so the extra must carry a reader of its own."""
    import tomllib

    data = tomllib.loads((REPO / "pyproject.toml").read_text())
    extra = data["project"]["optional-dependencies"]["snapshot"]
    assert any(dep.startswith("zstandard") for dep in extra), extra
    assert any(dep.startswith("duckdb") for dep in extra), extra


def test_neither_new_dependency_is_required():
    import tomllib

    data = tomllib.loads((REPO / "pyproject.toml").read_text())
    required = " ".join(data["project"]["dependencies"]).lower()
    assert "duckdb" not in required and "zstandard" not in required


def test_uv_lock_is_in_sync():
    proc = subprocess.run(["uv", "lock", "--check"], cwd=REPO,
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-2000:]


def test_a_zst_bundle_without_a_reader_gives_an_actionable_error(tmp_path):
    """If neither the module nor the binary is present, say which extra to add."""
    proc = _blocked(f"""
        import sys, types
        # Simulate zstandard being absent as well.
        class _Block:
            def find_spec(self, fullname, path=None, target=None):
                if fullname.split(".")[0] in ("zstandard", "duckdb"):
                    raise ImportError("blocked")
                return None
        sys.meta_path.insert(0, _Block())
        import shutil
        shutil.which = lambda *a, **k: None   # no zstd binary either

        from pathlib import Path
        from property_core.snapshot.archive import safe_extract
        from property_core.snapshot.errors import SnapshotExtraMissingError
        p = Path({str(tmp_path)!r}) / "b.tar.zst"; p.write_bytes(b"not really zstd")
        try:
            safe_extract(p, Path({str(tmp_path)!r}) / "out")
            print("NO_ERROR")
        except SnapshotExtraMissingError as exc:
            print("TYPED", "zstandard" in str(exc), "snapshot" in str(exc))
    """)
    assert "TYPED True True" in proc.stdout, proc.stdout + proc.stderr[-1500:]
