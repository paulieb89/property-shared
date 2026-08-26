"""Test collection must not configure integrations as a side effect.

Reproduced on 0e267d7: the primary worktree reported 3 failed / 607 passed while
every other worktree on the SAME commit reported 610 passed. The only difference
was a .env on disk. Three live modules called load_dotenv() at import time, which
loaded EPC_API_TOKEN into os.environ for the whole session; unit tests asserting
unconfigured EPC behaviour then saw a configured client.

The defect had two halves and so does the fix:
  * credentials load only behind the explicit RUN_LIVE_TESTS gate, so merely
    having a .env never activates or configures a live integration;
  * unconfigured-behaviour tests strip the credential variables via monkeypatch,
    so they hold even when the developer's shell exports them.

These tests pin the PATTERN rather than the three modules that happened to
exhibit it, so a newly added live module reintroducing it fails here.
"""

from __future__ import annotations

import ast
import os
import pathlib

import pytest

TESTS_DIR = pathlib.Path(__file__).parent
CREDENTIAL_VARS = (
    "EPC_API_TOKEN", "EPC_API_EMAIL", "EPC_API_KEY",
    "COMPANIES_HOUSE_API_KEY", "OPENAI_API_KEY",
)


def _test_modules():
    return sorted(p for p in TESTS_DIR.glob("test_*.py"))


def _ungated_dotenv_calls(path: pathlib.Path) -> list[tuple[int, str]]:
    """Module-level load_dotenv() calls not gated specifically on RUN_LIVE_TESTS.

    Checking merely "is it inside some `if`" is not enough: the original code was
    `if load_dotenv:` — inside an if, and still loading a .env on every import.
    Each enclosing `if` test is inspected for the RUN_LIVE_TESTS name, so only the
    real gate counts. Calls inside functions are ignored: they run on demand
    rather than at collection.
    """
    tree = ast.parse(path.read_text())
    findings: list[tuple[int, str]] = []

    def gate_mentions_run_live_tests(node: ast.If) -> bool:
        return any(
            isinstance(n, ast.Constant) and n.value == "RUN_LIVE_TESTS"
            for n in ast.walk(node.test)
        ) or any(
            isinstance(n, ast.Name) and n.id == "RUN_LIVE_TESTS"
            for n in ast.walk(node.test)
        )

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.gates: list[ast.If] = []

        def visit_If(self, node):
            self.gates.append(node)
            self.generic_visit(node)
            self.gates.pop()

        def visit_FunctionDef(self, node):
            pass  # not import-time

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node):
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name == "load_dotenv":
                if not any(gate_mentions_run_live_tests(g) for g in self.gates):
                    where = "ungated" if not self.gates else "gated on something else"
                    findings.append((node.lineno, where))
            self.generic_visit(node)

    Visitor().visit(tree)
    return findings


class TestNoImportTimeCredentialLoading:
    @pytest.mark.parametrize("path", _test_modules(), ids=lambda p: p.name)
    def test_dotenv_is_gated_on_run_live_tests(self, path):
        findings = _ungated_dotenv_calls(path)
        assert not findings, (
            f"{path.name} calls load_dotenv() at import time {findings}. Collection "
            "would then load a developer's .env into os.environ for the whole "
            "session, silently configuring integrations for every other test. "
            'Gate it on `if os.getenv("RUN_LIVE_TESTS") == "1":` specifically — '
            "`if load_dotenv:` is not a gate, it only checks the import succeeded."
        )


class TestUnconfiguredFixtureActuallyWorks:
    def test_fixture_removes_every_epc_variable(self, monkeypatch, no_epc_credentials):
        for var in ("EPC_API_TOKEN", "EPC_API_EMAIL", "EPC_API_KEY"):
            assert os.getenv(var) is None, f"{var} survived the fixture"

    def test_client_is_unconfigured_even_with_an_ambient_token(
        self, monkeypatch, no_epc_credentials
    ):
        """The scenario that broke: a real token exported in the environment."""
        from property_core.epc_client import EPCClient

        assert EPCClient().is_configured() is False
        assert EPCClient(token=None).is_configured() is False

    def test_without_the_fixture_an_ambient_token_does_configure(self, monkeypatch):
        """Pins WHY the fixture is needed: token=None is not 'unconfigured'."""
        from property_core.epc_client import EPCClient

        monkeypatch.setenv("EPC_API_TOKEN", "ambient-token-from-the-shell")
        assert EPCClient(token=None).is_configured() is True, (
            "EPCClient no longer falls back to the environment; the fixture's "
            "rationale has changed and this test should be revisited"
        )
