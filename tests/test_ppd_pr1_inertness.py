"""PR 1 must change no observable behaviour.

The golden fixture was generated from the pre-PR-1 tree (ebf8f3d) with the
identical harness in `tests/ppd_golden_harness.py`, then confirmed byte-identical
against this branch. It is a change-detector, not a correctness oracle: its job is
to fail loudly if foundation work ever leaks into a response.

Input is a fixed in-memory fixture with the transport patched out and sockets
hard-failed, so nothing here depends on a live upstream.

Spec: docs/design/ppd-source-routing.md section 10 (PR 1).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.ppd_golden_harness import capture, deterministic_ppd

GOLDEN = Path(__file__).parent / "fixtures" / "ppd" / "pr1_inertness_golden.json"


@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(GOLDEN.read_text())


@pytest.fixture(scope="module")
def actual() -> dict:
    return capture()


def test_golden_covers_every_named_pr1_surface(golden):
    assert set(golden) == {
        "core.comps",
        "core.search_transactions",
        "mcp.plain.ppd_transactions",
        "mcp.app.ppd_transactions",
        "rest.comps",
        "rest.transactions",
        "rest.meta_integrations",
        "cli.ppd_comps",
    }


@pytest.mark.parametrize(
    "surface",
    ["core.comps", "core.search_transactions",
     "mcp.plain.ppd_transactions", "mcp.app.ppd_transactions",
     "rest.comps", "rest.transactions", "rest.meta_integrations",
     "cli.ppd_comps"],
)
def test_surface_is_unchanged(surface, golden, actual):
    assert actual[surface] == golden[surface], (
        f"{surface} changed; PR 1 must add no behaviour. "
        f"If this change is intended it belongs in a later PR with its own tests."
    )


def test_whole_capture_is_byte_identical(golden, actual):
    assert json.dumps(actual, sort_keys=True) == json.dumps(golden, sort_keys=True)


def test_harness_makes_no_network_connection():
    """Guard the guard: the socket block must actually be armed."""
    import socket

    with deterministic_ppd():
        with pytest.raises(AssertionError, match="network connection"):
            socket.socket().connect(("127.0.0.1", 9))


def test_capture_is_independent_of_ambient_credentials(monkeypatch):
    """The golden must not depend on a developer's shell or .env.

    /v1/meta/integrations reports EPC as configured straight from the
    environment, so without neutralisation this surface differs between an
    isolated run and the full suite.
    """
    monkeypatch.setenv("EPC_API_TOKEN", "ambient-token-should-be-ignored")
    with_token = capture()
    monkeypatch.delenv("EPC_API_TOKEN", raising=False)
    without_token = capture()
    assert with_token == without_token


def test_no_provenance_fields_leaked_into_responses(actual):
    """PR 1 defines the provenance model but wires it nowhere."""
    blob = json.dumps(actual)
    for field in ("attribution_ref", "completeness_basis", "source_release",
                  "older_records_exist", "sample_complete"):
        assert field not in blob, f"{field} was wired into a response in PR 1"
