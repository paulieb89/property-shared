"""The words, the schema defaults and the runtime behaviour cannot disagree.

Before this, the MCP input schema for `months` was `{"default": 24, "type":
"integer"}` — a model choosing a value had the type and nothing else. Meanwhile
`/v1/ppd/transactions` had no `months` at all and took `from_date`/`to_date`,
and `le=120` bounded direct HTTP callers but not models.

Each of those was invisible from any single surface. So the guard is not "the
docstring mentions months"; it is that every published surface is *derived from*
`property_core.window`, asserted here against the contract rather than against a
literal restated in this file.
"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest

from property_core.window import (
    DEFAULT_MONTHS,
    MIN_MONTHS,
    MONTHS_DESCRIPTION,
    resolve_window,
    window_from_months,
)


# --- the contract itself ----------------------------------------------------


def test_the_description_states_the_default_it_ships_with():
    """A description naming a different default than the schema is the defect."""
    assert f"default {DEFAULT_MONTHS}" in MONTHS_DESCRIPTION


def test_the_description_says_coverage_bounds_the_answer():
    """A model must know the window can come back smaller than it asked."""
    assert "limited to available coverage" in MONTHS_DESCRIPTION


def test_no_maximum_is_declared_anywhere_in_the_contract():
    """Coverage is the ceiling and it moves; a second number would go stale."""
    import property_core.window as w

    assert not hasattr(w, "MAX_MONTHS")


# --- months -> dates --------------------------------------------------------


def test_window_from_months_counts_back_from_today():
    frm, to = window_from_months(12, today=date(2026, 9, 4))
    assert to == "2026-09-04"
    assert frm == "2025-09-09"      # 12 * 30 days, the shipped approximation


def test_window_from_months_refuses_below_the_minimum():
    with pytest.raises(ValueError, match="months must be"):
        window_from_months(MIN_MONTHS - 1)


def test_window_from_months_accepts_a_window_larger_than_any_coverage():
    """No maximum: a huge request is answered over the overlap, not refused."""
    frm, to = window_from_months(1200, today=date(2026, 9, 4))
    assert frm < "1930-01-01"


# --- clamping, and saying so ------------------------------------------------


def test_a_window_inside_coverage_is_not_clamped():
    w = resolve_window(requested_from="2024-01-01", requested_to="2025-01-01",
                       coverage_from="1995-01-01", coverage_to="2026-07-31")
    assert (w.effective_from, w.effective_to) == ("2024-01-01", "2025-01-01")
    assert w.truncated is False
    assert w.truncation_warning is None


def test_a_window_starting_before_coverage_is_clamped_and_says_so():
    w = resolve_window(requested_from="1980-01-01", requested_to="2025-01-01",
                       coverage_from="1995-01-01", coverage_to="2026-07-31")
    assert w.effective_from == "1995-01-01"
    assert w.truncated is True
    assert "1980-01-01" in w.truncation_warning
    assert "1995-01-01" in w.truncation_warning


def test_a_window_ending_after_coverage_is_clamped_and_says_so():
    w = resolve_window(requested_from="2024-01-01", requested_to="2026-12-31",
                       coverage_from="1995-01-01", coverage_to="2026-07-31")
    assert w.effective_to == "2026-07-31"
    assert w.truncated is True


def test_an_absent_request_bound_takes_the_coverage_bound():
    w = resolve_window(requested_from=None, requested_to=None,
                       coverage_from="1995-01-01", coverage_to="2026-07-31")
    assert (w.effective_from, w.effective_to) == ("1995-01-01", "2026-07-31")
    assert w.truncated is True, "an unbounded ask answered over coverage IS narrower"


def test_a_source_with_no_stated_coverage_clamps_nothing():
    w = resolve_window(requested_from="1980-01-01", requested_to=None,
                       coverage_from=None, coverage_to=None)
    assert (w.effective_from, w.effective_to) == ("1980-01-01", None)
    assert w.truncated is False


def test_the_warning_names_both_windows_not_just_the_fact_of_clamping():
    """A caller deciding whether an answer supports a claim needs the bounds."""
    w = resolve_window(requested_from="1980-01-01", requested_to="2030-01-01",
                       coverage_from="1995-01-01", coverage_to="2026-07-31")
    for figure in ("1980-01-01", "2030-01-01", "1995-01-01", "2026-07-31"):
        assert figure in w.truncation_warning


# --- the published surfaces are derived from the contract -------------------


MCP_TOOLS_WITH_MONTHS = ["property_comps", "property_yield"]


def _schema(server, tool_name: str) -> dict:
    tool = asyncio.run(server.get_tool(tool_name))
    return tool.parameters["properties"]


@pytest.mark.parametrize("tool_name", MCP_TOOLS_WITH_MONTHS)
def test_the_mcp_schema_for_months_is_the_contract(tool_name):
    """What the model reads, asserted against the contract, not a restatement.

    `months` shipped as `{"default": 24, "type": "integer"}` — no description,
    no minimum. This is the guard that it cannot go back.
    """
    from app.mcp.server import mcp

    months = _schema(mcp, tool_name)["months"]
    assert months["description"] == MONTHS_DESCRIPTION
    assert months["default"] == DEFAULT_MONTHS
    assert months["minimum"] == MIN_MONTHS
    assert "maximum" not in months, (
        "a maximum in the schema contradicts the contract: coverage is the "
        "ceiling and it moves when the artifact is rebuilt"
    )


@pytest.mark.parametrize("tool_name", MCP_TOOLS_WITH_MONTHS)
def test_the_mcp_default_matches_what_the_function_actually_does(tool_name):
    """A schema default that differs from the signature default is a lie."""
    import inspect

    from app.mcp.server import mcp

    tool = asyncio.run(mcp.get_tool(tool_name))
    signature_default = inspect.signature(tool.fn).parameters["months"].default
    assert signature_default == _schema(mcp, tool_name)["months"]["default"]


def test_the_rest_date_parameters_are_described_from_the_contract():
    from fastapi.routing import APIRoute

    from app.api.v1.ppd import router
    from property_core.window import FROM_DATE_DESCRIPTION, TO_DATE_DESCRIPTION

    route = next(r for r in router.routes
                 if isinstance(r, APIRoute) and r.path.endswith("/transactions"))
    described = {p.name: p.field_info.description for p in route.dependant.query_params}
    assert described["from_date"] == FROM_DATE_DESCRIPTION
    assert described["to_date"] == TO_DATE_DESCRIPTION
