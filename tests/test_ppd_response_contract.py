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

**PR 4 adds source routing**, so the golden was regenerated again and that
delta reviewed line by line. It is additive apart from one line:

* every PPD-bearing surface gains a `provenance` block. With no snapshot
  materialized -- which is what this harness captures -- it reports
  `source: "sparql"`, null coverage fields, and whatever completeness the
  transport actually observed;
* `cli.ppd_comps` stdout changes for a second reason: `_echo_json` no longer
  goes through rich's `print`, which soft-wrapped long strings and left a
  newline inside a JSON value, so the document did not parse. JSON output
  exists to be machine-read.

**The shared window contract adds two provenance fields**, so the golden was
regenerated a third time and that delta reviewed the same way. It is purely
additive -- a key-level diff of every surface showed only `+` lines:

* every PPD-bearing surface gains `provenance.requested_window` and
  `provenance.effective_window`. Either alone is ambiguous: `effective` on its
  own cannot say whether it was the request or a clamp, and a model whose
  earlier turn has left its context cannot reconstruct it.
* both are `null` in THIS golden, and that is correct rather than a gap. The
  harness captures the live path, which builds no `CoverageDecision`, so there
  is no clamp to report. `snapshot_provenance` populates both. A live path that
  published a window would be asserting bounds it never applied.

Nothing else moved. `rest.meta_integrations` is untouched, the live-path
warning strings are byte-identical, and no row of data changed -- routing is
inert until a snapshot is materialized and the flag is on.

The harness also clears `PPD_SNAPSHOT_ENABLED`: this golden pins the LIVE-path
contract, and a developer with the flag set in their shell would otherwise
capture a different one.

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
        f"{surface} changed. If the change is intended, regenerate the golden "
        f"(`python -m tests.ppd_golden_harness`), review the delta line by line, "
        f"and record it in this module's docstring and the changelog."
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


def test_every_ppd_bearing_surface_carries_provenance(actual):
    """PR 4 wires the block in. Inverted from PR 1's inertness assertion.

    `rest.meta_integrations` is excluded: it carries no PPD rows, so a
    provenance block there would describe nothing.
    """
    for surface in ("core.comps", "core.search_transactions",
                    "mcp.plain.ppd_transactions", "mcp.app.ppd_transactions"):
        provenance = actual[surface]["provenance"]
        assert provenance is not None, surface
        assert provenance["source"] == "sparql", surface
        assert provenance["attribution_ref"] == "/v1/meta#attribution", surface

    for surface in ("rest.comps", "rest.transactions"):
        assert actual[surface]["body"]["provenance"]["source"] == "sparql", surface

    assert "provenance" not in actual["rest.meta_integrations"]["body"]


def test_licence_prose_is_never_inlined_into_a_response(actual):
    """Spec test 28c. Responses carry a reference; the licence lives at /v1/meta."""
    blob = json.dumps(actual)
    assert "Open Government Licence" not in blob
    assert "Crown copyright" not in blob


def test_the_live_path_declares_no_snapshot_coverage(actual):
    """With nothing materialized, the snapshot fields must be null, not empty.

    A `coverage_from` of `""` or `0` would read as a stated bound. Null is the
    only honest value for "this answer has no coverage bounds".
    """
    for surface in ("core.comps", "core.search_transactions"):
        provenance = actual[surface]["provenance"]
        assert provenance["source_release"] is None, surface
        assert provenance["coverage_from"] is None, surface
        assert provenance["coverage_to"] is None, surface
        assert provenance["freshness_days"] is None, surface
        assert provenance["older_records_exist"] is None, surface
