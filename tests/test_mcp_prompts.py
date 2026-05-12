"""Tests for MCP prompts on both servers."""
from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_full_property_analysis_registered_on_plain_mcp():
    from app.mcp.server import mcp

    prompts = await mcp.list_prompts()
    names = [p.name for p in prompts]
    assert "full_property_analysis" in names


@pytest.mark.anyio
async def test_full_property_analysis_returns_string_with_tool_names():
    from app.mcp.server import mcp

    result = await mcp.render_prompt(
        "full_property_analysis",
        {"address": "10 Downing Street", "postcode": "SW1A 2AA", "months": "24"},
    )
    rendered = "\n".join(str(m) for m in result.messages)
    assert "property_comps" in rendered
    assert "property_yield" in rendered
    assert "property_epc" in rendered
    assert "rightmove_search" in rendered
    assert "SW1A 2AA" in rendered
    assert "10 Downing Street" in rendered


@pytest.mark.anyio
async def test_property_report_tool_removed_from_plain_mcp():
    from app.mcp.server import mcp

    tools = await mcp.list_tools()
    names = [t.name for t in tools]
    assert "property_report" not in names, (
        "property_report should be removed; use full_property_analysis prompt instead"
    )
