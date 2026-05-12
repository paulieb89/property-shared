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


@pytest.mark.anyio
async def test_individual_council_resource():
    from app.mcp.server import mcp
    from importlib.resources import files

    raw = json.loads(files("property_core").joinpath("planning_councils.json").read_text())
    councils = raw.get("councils", raw)
    sample = councils[0]
    code = sample.get("code") or sample.get("slug")
    assert code

    result = await mcp.read_resource(f"council://{code}")
    text = result.contents[0].content
    data = json.loads(text)
    assert data.get("code") == code or data.get("slug") == code


@pytest.mark.anyio
async def test_sdlt_bands_resource():
    from app.mcp.server import mcp

    result = await mcp.read_resource("sdlt-bands://current")
    text = result.contents[0].content
    data = json.loads(text)
    assert "main_bands" in data
    assert "effective_from" in data
    body = json.dumps(data)
    assert "additional" in body.lower() or "surcharge" in body.lower()


@pytest.mark.anyio
async def test_epc_ratings_resource():
    from app.mcp.server import mcp

    result = await mcp.read_resource("epc-ratings://reference")
    text = result.contents[0].content
    data = json.loads(text)
    assert "ratings" in data
    letters = {r["band"] for r in data["ratings"]}
    assert letters == {"A", "B", "C", "D", "E", "F", "G"}
    for rating in data["ratings"]:
        assert "score_min" in rating
        assert "score_max" in rating
        assert "description" in rating
