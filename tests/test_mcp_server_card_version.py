"""Both MCP servers must advertise the installed property-shared version.

Dogfooding v1.14.1 in production found the MCP app's card reporting "3.2.4" —
the pinned FastMCP dependency version, not the app's. FastMCP falls back to its
own version when the constructor is given no `version=`, and property_app/server.py
never passed one, so the protocol card and the app's own
/.well-known/mcp/server-card.json route disagreed about what was deployed.

These drive the REAL `initialize` handshake through an in-memory FastMCP client
rather than inspecting `mcp.version`, because the attribute is not the contract —
what a client receives is. The HTTP-card agreement check invokes the actual
well-known route rather than asserting a route exists from memory.

Versions are asserted as a property (card == installed distribution version),
not as literals, so these keep holding across releases without edits.
"""

from __future__ import annotations

import json
from importlib.metadata import version as _pkg_version

import pytest
from fastmcp import Client

INSTALLED = _pkg_version("property-shared")
CARD_ROUTE = "/.well-known/mcp/server-card.json"


async def _initialize_server_info(mcp):
    """The serverInfo a real client receives from the initialize handshake."""
    async with Client(mcp) as client:
        result = client.initialize_result
        assert result is not None, "no initialize result returned"
        return result.serverInfo


def _servers():
    from app.mcp.server import mcp as plain
    from property_app.server import mcp as app

    return {"plain": plain, "app": app}


@pytest.mark.anyio
@pytest.mark.parametrize("name", ["plain", "app"])
async def test_initialize_advertises_the_installed_version(name):
    info = await _initialize_server_info(_servers()[name])
    assert info.version == INSTALLED, (
        f"{name} server's initialize serverInfo reports {info.version!r}, "
        f"not the installed property-shared version {INSTALLED!r}"
    )


@pytest.mark.anyio
async def test_neither_advertises_the_fastmcp_version():
    """The specific failure mode: falling back to the framework's version."""
    fastmcp_version = _pkg_version("fastmcp")
    if fastmcp_version == INSTALLED:
        pytest.skip("fastmcp and property-shared share a version; test is vacuous")

    for name, mcp in _servers().items():
        info = await _initialize_server_info(mcp)
        assert info.version != fastmcp_version, (
            f"{name} server advertises the FastMCP version {fastmcp_version}"
        )


@pytest.mark.anyio
async def test_the_two_servers_agree():
    versions = {}
    for name, mcp in _servers().items():
        versions[name] = (await _initialize_server_info(mcp)).version
    assert versions["plain"] == versions["app"], versions


@pytest.mark.anyio
async def test_server_names_are_still_distinct():
    """Guard the fix from over-reaching: only the version was wrong."""
    names = {}
    for name, mcp in _servers().items():
        names[name] = (await _initialize_server_info(mcp)).name
    assert names == {"plain": "property-data", "app": "property-app"}, names


@pytest.mark.anyio
async def test_well_known_card_route_agrees_with_initialize():
    """Invoke the real route — the app has two version surfaces that must agree."""
    from starlette.testclient import TestClient

    from property_app.server import mcp

    with TestClient(mcp.http_app()) as http:
        response = http.get(CARD_ROUTE)
    assert response.status_code == 200, f"{CARD_ROUTE} -> {response.status_code}"
    payload = response.json()

    card_version = (payload.get("serverInfo") or {}).get("version")
    assert card_version == INSTALLED, (
        f"{CARD_ROUTE} reports {card_version!r}, not {INSTALLED!r}"
    )

    info = await _initialize_server_info(mcp)
    assert card_version == info.version, (
        f"the two version surfaces disagree: {CARD_ROUTE}={card_version!r} "
        f"vs initialize={info.version!r}"
    )
