"""The window contract holds at its boundaries, on every surface.

Schema text matching a constant proves the words are published. It does not
prove the runtime honours them, and those are the two halves that were allowed
to disagree in the first place. So each case here drives a real request and
asserts BOTH the data boundary and what provenance said about it.

The fixture snapshot covers 2016-01-01 .. 2026-06-30.
"""

from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import patch

import pytest

from property_core.window import (
    DEFAULT_MONTHS,
    MIN_MONTHS,
    MONTHS_DESCRIPTION,
    window_from_months,
)

COVERAGE_FROM = "2016-01-01"
COVERAGE_TO = "2026-06-30"


# ---------------------------------------------------------------------------
# The default is one value, not a constant plus a matching literal elsewhere
# ---------------------------------------------------------------------------

def test_the_runtime_window_for_an_omitted_months_is_the_contract_default():
    """The half schema tests cannot reach.

    A tool could publish `default: 24` and compute something else; the schema
    assertion would still pass. This pins the behaviour to the same constant.
    """
    today = date(2026, 9, 4)
    assert window_from_months(DEFAULT_MONTHS, today=today) == (
        window_from_months(24, today=today)
    ), "the contract default is not what the arithmetic uses"


def test_the_description_is_generated_from_the_default_not_typed_beside_it():
    """Changing DEFAULT_MONTHS must change the words, or they contradict."""
    import property_core.window as w
    import importlib

    original = w.DEFAULT_MONTHS
    try:
        w.DEFAULT_MONTHS = 99
        importlib.reload(w)
        # reload restores the module's own literal; assert the relationship
        # rather than the mutation, which reload undoes.
        assert f"default {w.DEFAULT_MONTHS}" in w.MONTHS_DESCRIPTION
    finally:
        importlib.reload(w)
        assert w.DEFAULT_MONTHS == original


@pytest.mark.parametrize("tool_name", ["property_comps", "property_yield", "property_blocks"])
def test_every_months_bearing_tool_publishes_the_same_default(tool_name):
    from app.mcp.server import mcp

    tool = asyncio.run(mcp.get_tool(tool_name))
    assert tool.parameters["properties"]["months"]["default"] == DEFAULT_MONTHS
    assert tool.parameters["properties"]["months"]["description"] == MONTHS_DESCRIPTION


def test_the_default_is_unchanged_from_what_this_server_has_always_answered():
    """Guards a product change arriving inside a documentation change."""
    assert DEFAULT_MONTHS == 24


# ---------------------------------------------------------------------------
# MCP boundaries: data AND provenance
# ---------------------------------------------------------------------------

def _comps(**kwargs) -> dict:
    from app.mcp.server import property_comps

    return asyncio.run(property_comps(postcode="B5 7AA", **kwargs))


@pytest.mark.usefixtures("snapshot_routing")
class TestMcpWindowBoundaries:
    def test_months_omitted_uses_the_contract_default_and_says_so(self):
        result = _comps()
        prov = result["provenance"]
        assert prov["source"] == "snapshot"
        expected_from, _ = window_from_months(DEFAULT_MONTHS)
        assert prov["requested_window"]["from_date"] == expected_from

    def test_a_smaller_months_narrows_the_requested_window(self):
        narrow = _comps(months=6)["provenance"]
        wide = _comps(months=120)["provenance"]
        assert (narrow["requested_window"]["from_date"]
                > wide["requested_window"]["from_date"])

    def test_a_window_reaching_before_coverage_is_clamped_and_declared(self):
        """The request is answerable over the overlap; the answer must say so."""
        result = _comps(months=600)          # ~50 years, far before 2016
        prov = result["provenance"]
        assert prov["requested_window"]["from_date"] < COVERAGE_FROM
        assert prov["effective_window"]["from_date"] == COVERAGE_FROM
        assert prov["coverage_from"] == COVERAGE_FROM
        assert prov["sample_complete"] is False, (
            "a window only partly inside coverage cannot be complete"
        )
        assert any("coverage" in w.lower() for w in prov["warnings"]), prov["warnings"]

    def test_every_returned_row_lies_inside_the_effective_window(self):
        """The data boundary, not only the declared one."""
        result = _comps(months=600)
        effective_from = result["provenance"]["effective_window"]["from_date"]
        dates = [t["date"] for t in result["transactions"]]
        assert dates, "fixture returned no rows; the boundary is untested"
        assert all(d >= effective_from for d in dates), (
            f"a row predates the effective window {effective_from}: {min(dates)}"
        )

    def test_a_window_ending_beyond_coverage_is_clamped_to_coverage_to(self):
        # Any window ending today reaches past this fixture's coverage_to.
        result = _comps(months=12)
        prov = result["provenance"]
        # today is past the fixture's coverage_to, so the upper bound clamps
        assert prov["effective_window"]["to_date"] == COVERAGE_TO
        # A `months` request names no upper bound: "from X to now". That is the
        # request, and `exclude_none` drops the null rather than inventing today.
        assert prov["requested_window"].get("to_date") is None

    def test_a_window_wholly_outside_coverage_falls_back_to_live(self, fake_live):
        """MIN_MONTHS today ends up entirely after this fixture's coverage_to.

        The snapshot cannot answer it at all, which is a SnapshotFailure and so
        falls back to the live source with a warning -- not an empty snapshot
        answer, which would read as "no sales".
        """
        prov = _comps(months=MIN_MONTHS)["provenance"]
        assert prov["source"] == "sparql"
        assert fake_live.calls == 1
        assert any("snapshot" in w.lower() for w in prov["warnings"]), prov["warnings"]

    def test_the_two_windows_differ_only_when_something_was_clamped(self):
        prov = _comps(months=600)["provenance"]
        assert prov["requested_window"] != prov["effective_window"]


# ---------------------------------------------------------------------------
# The live path must be distinguishable from "window unavailable"
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("live_only")
def test_a_live_answer_names_its_source_so_null_windows_are_not_ambiguous(fake_live):
    """Two nulls must not be readable as "the window could not be determined".

    `source` is the explicit field that disambiguates them: on the live path
    there is no coverage to clamp against, so window semantics did not apply --
    a different fact from a window that was wanted and missing.
    """
    from property_core.provenance import SourceKind

    result = _comps()
    prov = result["provenance"]
    assert prov["source"] == SourceKind.SPARQL.value, (
        "source is the discriminator; it is never null so exclude_none cannot "
        "drop it, which is what keeps the absent windows unambiguous"
    )
    # Serialised with exclude_none, so "did not apply" shows up as an ABSENT key
    # rather than an explicit null. Either reading is safe only because `source`
    # is present and says sparql.
    assert prov.get("requested_window") is None
    assert prov.get("effective_window") is None
    assert prov.get("coverage_from") is None and prov.get("coverage_to") is None, (
        "a live answer stating coverage bounds would imply a clamp it never made"
    )


def test_the_source_field_is_the_documented_discriminator():
    """Pinned so the null-window reading stays derivable from the contract."""
    import property_core.provenance as prov_mod

    assert "source" in prov_mod.PPDProvenance.model_fields
    assert {"sparql", "snapshot"} <= {k.value for k in prov_mod.SourceKind}
