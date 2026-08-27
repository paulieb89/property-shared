"""PR 1 — DuckDB is an OPTIONAL extra, and the snapshot flag is off by default.

The import-isolation tests run in a clean SUBPROCESS under an explicit
``sys.meta_path`` blocker. They deliberately do not inspect ``sys.modules`` in
the shared test process: another test may already have imported DuckDB, which
would make these pass vacuously.

Spec: docs/design/ppd-source-routing.md section 5.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# A meta_path finder that makes `import duckdb` fail exactly as it would on a
# machine that never installed the extra.
BLOCKER = """
import sys

class _Blocked(Exception):
    pass

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


def _run_blocked(body: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", BLOCKER + body],
        cwd=REPO, capture_output=True, text=True, timeout=180,
    )


def test_duckdb_is_genuinely_blocked_in_the_subprocess():
    """Guard the guard: if the blocker silently failed, every test below is vacuous."""
    proc = _run_blocked(
        "try:\n"
        "    import duckdb\n"
        "    print('NOT_BLOCKED')\n"
        "except ImportError:\n"
        "    print('BLOCKED')\n"
    )
    assert proc.stdout.strip() == "BLOCKED", proc.stderr[-2000:]


def test_property_core_imports_without_duckdb():
    proc = _run_blocked("import property_core; print('OK')")
    assert proc.returncode == 0, proc.stderr[-3000:]
    assert "OK" in proc.stdout


def test_every_public_export_imports_without_duckdb():
    """A library consumer that never touches snapshots must not need the extra."""
    proc = _run_blocked(
        "import property_core\n"
        "names = getattr(property_core, '__all__', None) or [\n"
        "    n for n in dir(property_core) if not n.startswith('_')]\n"
        "missing = [n for n in names if not hasattr(property_core, n)]\n"
        "print(json.dumps({'count': len(names), 'missing': missing}))\n".replace(
            "json.dumps", "__import__('json').dumps")
    )
    assert proc.returncode == 0, proc.stderr[-3000:]
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["missing"] == []
    assert payload["count"] > 0


def test_new_pr1_modules_import_without_duckdb():
    proc = _run_blocked(
        "from property_core.provenance import PPDProvenance, TransportEvidence\n"
        "from property_core.exceptions import PPDCoverageError\n"
        "print('OK')"
    )
    assert proc.returncode == 0, proc.stderr[-3000:]
    assert "OK" in proc.stdout


# --------------------------------------------------------------------------
# Declaration
# --------------------------------------------------------------------------

def test_pyproject_declares_the_snapshot_extra():
    data = tomllib.loads((REPO / "pyproject.toml").read_text())
    extras = data["project"]["optional-dependencies"]
    assert extras["snapshot"] == ["duckdb==1.5.5"], extras.get("snapshot")


def test_duckdb_is_not_a_required_dependency():
    data = tomllib.loads((REPO / "pyproject.toml").read_text())
    required = " ".join(data["project"]["dependencies"]).lower()
    assert "duckdb" not in required


def test_uv_lock_contains_the_optional_dependency():
    lock = (REPO / "uv.lock").read_text()
    assert 'name = "duckdb"' in lock
    assert 'version = "1.5.5"' in lock


def test_uv_lock_is_in_sync_with_pyproject():
    proc = subprocess.run(
        ["uv", "lock", "--check"], cwd=REPO, capture_output=True, text=True, timeout=300
    )
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-3000:]


# --------------------------------------------------------------------------
# Flag
# --------------------------------------------------------------------------

def test_snapshot_flag_defaults_false_in_core(monkeypatch):
    monkeypatch.delenv("PPD_SNAPSHOT_ENABLED", raising=False)
    from property_core.config import ppd_snapshot_enabled

    assert ppd_snapshot_enabled() is False


@pytest.mark.parametrize(
    "value, expected",
    [("1", True), ("true", True), ("TRUE", True), ("yes", True),
     ("0", False), ("false", False), ("", False), ("nonsense", False)],
)
def test_snapshot_flag_parses_conservatively(monkeypatch, value, expected):
    monkeypatch.setenv("PPD_SNAPSHOT_ENABLED", value)
    from property_core.config import ppd_snapshot_enabled

    assert ppd_snapshot_enabled() is expected


def test_snapshot_flag_defaults_false_in_api_settings(monkeypatch):
    monkeypatch.delenv("PPD_SNAPSHOT_ENABLED", raising=False)
    from app.core.config import Settings

    assert Settings(_env_file=None).ppd_snapshot_enabled is False


@pytest.mark.parametrize(
    "value, expected",
    [("1", True), ("true", True), ("TRUE", True), ("yes", True), ("on", True),
     ("0", False), ("false", False), ("", False), ("nonsense", False),
     ("  ", False), ("2", False)],
)
def test_core_and_api_agree_on_every_flag_value(monkeypatch, value, expected):
    """One parser, one behaviour.

    Pydantic's own bool coercion raises on "" and "nonsense" while the library
    returns False. Unaligned, an operator typo would start the CLI and crash the
    API. Both must fail closed identically.
    """
    monkeypatch.setenv("PPD_SNAPSHOT_ENABLED", value)
    from app.core.config import Settings
    from property_core.config import ppd_snapshot_enabled

    core = ppd_snapshot_enabled()
    api = Settings(_env_file=None).ppd_snapshot_enabled
    assert core is expected
    assert api is expected
    assert core is api


def test_invalid_flag_value_does_not_crash_api_startup(monkeypatch):
    monkeypatch.setenv("PPD_SNAPSHOT_ENABLED", "definitely-not-a-bool")
    from app.core.config import Settings

    assert Settings(_env_file=None).ppd_snapshot_enabled is False
