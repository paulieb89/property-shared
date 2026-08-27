"""Locks the observable PPD response contract across every consumer.

Started life as the PR 1 inertness gate. PR 1 was inert and the golden matched
the pre-PR-1 tree byte for byte. **PR 2 deliberately changes comps behaviour**,
so the golden was regenerated and the delta reviewed line by line against the
same harness run on the pre-PR-2 tree (377a553). Every difference was intended:

* `core.comps` / `rest.comps` / `cli.ppd_comps` gain the additive `warnings`
  field;
* `rest.comps` no longer widens sector -> district: `search_level` stays
  `sector`, `escalated_from`/`escalated_to` are null, and a warning explains
  why (live-source completeness cannot authorise escalation).

Everything else -- `core.search_transactions`, both MCP `ppd_transactions`
tools, `rest.transactions`, `rest.meta_integrations` -- is byte-identical to
pre-PR-2, which is the point: containment changed comps and nothing else.

This is a change-detector, not a correctness oracle. Input is a fixed binding
fixture patched in at the real transport boundary (`_fetch_sparql`) with sockets
hard-failed, so it exercises the actual parse/filter/containment path and no
live upstream.

Spec: docs/design/ppd-source-routing.md sections 2.7 and 10.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.ppd_golden_harness import capture, deterministic_ppd

GOLDEN = Path(__file__).parent / "fixtures" / "ppd" / "response_contract_golden.json"


@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(GOLDEN.read_text())


@pytest.fixture(scope="module")
def actual() -> dict:
    return capture()


def test_golden_covers_every_named_surface(golden):
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


def test_pr2_disabled_live_escalation_is_locked(actual):
    """The behaviour change PR 2 makes, pinned so it cannot silently revert."""
    body = actual["rest.comps"]["body"]
    assert body["escalated_from"] is None and body["escalated_to"] is None
    assert body["query"]["search_level"] == "sector"
    assert any("escalat" in w.lower() for w in body["warnings"]), body["warnings"]


def test_surfaces_pr2_should_not_have_touched_carry_no_warnings(actual):
    """Containment changed comps. It must not have changed the raw search path."""
    for surface in ("core.search_transactions", "mcp.plain.ppd_transactions",
                    "mcp.app.ppd_transactions"):
        assert actual[surface]["warnings"] == [], actual[surface]


def test_no_provenance_fields_leaked_into_responses(actual):
    """The provenance model exists but is still wired nowhere (PR 4 does that)."""
    blob = json.dumps(actual)
    for field in ("attribution_ref", "completeness_basis", "source_release",
                  "older_records_exist", "sample_complete"):
        assert field not in blob, f"{field} was wired into a response in PR 1"
