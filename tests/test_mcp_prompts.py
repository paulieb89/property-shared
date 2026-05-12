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


@pytest.mark.anyio
async def test_get_property_data_tool_removed_from_mcp_app():
    """get_property_data was a composition tool; replaced by full_property_analysis prompt."""
    import property_app.tools  # noqa: F401
    import property_app.dashboards.comps  # noqa: F401
    import property_app.dashboards.yield_view  # noqa: F401
    import property_app.dashboards.rental  # noqa: F401
    import property_app.dashboards.listings  # noqa: F401
    import property_app.dashboards.unified  # noqa: F401
    from property_app.server import mcp

    tools = await mcp.list_tools()
    names = [t.name for t in tools]
    assert "get_property_data" not in names
    assert "property_dashboard" in names  # UI tool preserved


@pytest.mark.anyio
async def test_property_report_tool_removed_from_mcp_app():
    import property_app.tools  # noqa: F401
    from property_app.server import mcp

    tools = await mcp.list_tools()
    names = [t.name for t in tools]
    assert "property_report" not in names


@pytest.mark.anyio
async def test_full_property_analysis_registered_on_mcp_app():
    import property_app.tools  # noqa: F401
    import property_app.dashboards.unified  # noqa: F401
    from property_app.server import mcp

    prompts = await mcp.list_prompts()
    names = [p.name for p in prompts]
    assert "full_property_analysis" in names


@pytest.mark.anyio
async def test_dev_utility_tools_removed_from_mcp_app():
    """component_test and image_test are dev utilities, should not be in production."""
    import property_app.tools  # noqa: F401
    from property_app.server import mcp

    tools = await mcp.list_tools()
    names = [t.name for t in tools]
    assert "component_test" not in names
    assert "image_test" not in names


@pytest.mark.anyio
async def test_area_comparison_prompt_registered():
    from app.mcp.server import mcp

    prompts = await mcp.list_prompts()
    names = [p.name for p in prompts]
    assert "area_comparison" in names


@pytest.mark.anyio
async def test_area_comparison_prompt_renders():
    from app.mcp.server import mcp

    result = await mcp.render_prompt(
        "area_comparison",
        {"postcodes": "NG1 2NS, DE12 7DH, NG11 9HD", "months": "24"},
    )
    rendered = "\n".join(str(m) for m in result.messages)
    assert "NG1 2NS" in rendered
    assert "DE12 7DH" in rendered
    assert "NG11 9HD" in rendered
    assert "property_yield" in rendered
    assert "property_comps" in rendered


@pytest.mark.anyio
async def test_investment_analysis_prompt_registered():
    from app.mcp.server import mcp

    prompts = await mcp.list_prompts()
    names = [p.name for p in prompts]
    assert "investment_analysis" in names


@pytest.mark.anyio
async def test_investment_analysis_prompt_renders():
    from app.mcp.server import mcp

    result = await mcp.render_prompt(
        "investment_analysis",
        {
            "address": "10 Downing Street",
            "postcode": "SW1A 2AA",
            "purchase_price": "1500000",
            "additional_property": "true",
        },
    )
    rendered = "\n".join(str(m) for m in result.messages)
    assert "10 Downing Street" in rendered
    assert "SW1A 2AA" in rendered
    assert "1,500,000" in rendered or "1500000" in rendered
    assert "stamp_duty" in rendered
    assert "property_yield" in rendered
