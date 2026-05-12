"""Tests for MCP resources on both servers."""
from __future__ import annotations

import json

import pytest


@pytest.mark.anyio
async def test_councils_list_resource_on_plain_mcp():
    from app.mcp.server import mcp

    resources = await mcp.list_resources()
    uris = [str(r.uri) for r in resources]
    assert "councils://list" in uris

    result = await mcp.read_resource("councils://list")
    text = result.contents[0].content
    data = json.loads(text)
    assert isinstance(data, list)
    assert len(data) >= 50
    first = data[0]
    assert any(k in first for k in ("code", "slug", "name", "council_name"))


@pytest.mark.anyio
async def test_councils_list_resource_on_mcp_app():
    import property_app.tools  # noqa: F401
    from property_app.server import mcp

    resources = await mcp.list_resources()
    uris = [str(r.uri) for r in resources]
    assert "councils://list" in uris
