"""Both MCP servers must advertise the installed property-shared version.

Dogfooding v1.14.1 in production found the MCP app's card reporting "3.2.4" —
the pinned FastMCP dependency version, not the app's. FastMCP falls back to its
own version when the constructor is given no `version=`, and property_app/server.py
never passed one, so the protocol card and the app's own /server-info HTTP route
disagreed about what was deployed.

These assert the property (card == installed distribution version) rather than a
literal, so they keep holding across releases without edits.
"""

from __future__ import annotations

from importlib.metadata import version as _pkg_version

import pytest

INSTALLED = _pkg_version("property-shared")


def _server_version(mcp) -> str | None:
    """Read the advertised version off a FastMCP instance.

    Tries the public attribute first and falls back to the constructed
    low-level server, so this does not depend on one FastMCP internal.
    """
    for probe in (
        lambda: mcp.version,
        lambda: mcp._mcp_server.version,
        lambda: mcp._mcp_server.server_version,
    ):
        try:
            v = probe()
        except AttributeError:
            continue
        if v:
            return v
    return None


class TestBothCardsReportTheInstalledVersion:
    def test_plain_mcp_server(self):
        from app.mcp.server import mcp

        assert _server_version(mcp) == INSTALLED

    def test_mcp_app_server(self):
        from property_app.server import mcp

        assert _server_version(mcp) == INSTALLED, (
            "the MCP app is advertising the FastMCP dependency version instead "
            "of property-shared's"
        )

    def test_neither_reports_the_fastmcp_version(self):
        """The specific failure mode: falling back to the framework's version."""
        fastmcp_version = _pkg_version("fastmcp")
        if fastmcp_version == INSTALLED:
            pytest.skip("fastmcp and property-shared share a version; test is vacuous")

        from app.mcp.server import mcp as plain
        from property_app.server import mcp as app

        for name, server in (("plain", plain), ("app", app)):
            assert _server_version(server) != fastmcp_version, \
                f"{name} server advertises the FastMCP version {fastmcp_version}"

    def test_the_two_servers_agree(self):
        from app.mcp.server import mcp as plain
        from property_app.server import mcp as app

        assert _server_version(plain) == _server_version(app)


class TestAppHttpRouteAgreesWithTheCard:
    """The app has a second version surface; the two must not drift apart."""

    def test_server_info_route_matches_the_mcp_card(self):
        from property_app.server import mcp

        assert _server_version(mcp) == INSTALLED
