"""Standalone MCP App server -- property tools + interactive Prefab dashboards.

This is the 4th consumer of property_core, alongside the API, CLI, and MCP server.
Tools are real MCP tools (LLM-callable). Dashboards layer Prefab UI on top.
"""
from __future__ import annotations

from fastmcp import FastMCP

# Main server — all tools registered directly via @mcp.tool()
mcp = FastMCP(
    "property-app",
    instructions=(
        "UK property tools with interactive dashboards. "
        "Tools return data directly -- dashboards add visual Prefab UI. "
        "Use comps_dashboard, yield_dashboard, rental_dashboard, listings_dashboard for rich visual views. "
        "Use search_comps, get_yield, get_rental for raw data. "
        "Use stamp_duty, planning_search, company_search, epc_lookup, rightmove_search for quick lookups."
    ),
)


@mcp.custom_route("/health", methods=["GET"])
async def health(request):  # noqa: ARG001
    from starlette.responses import JSONResponse

    return JSONResponse({"status": "ok"})


def main() -> None:
    import os
    # Import tool/dashboard modules so they register on mcp/app
    from property_app import tools  # noqa: F401
    from property_app.dashboards import comps, listings, yield_view, rental  # noqa: F401

    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport not in ("stdio", "sse", "http"):
        transport = "stdio"
    kwargs: dict = {}
    if transport in ("sse", "http"):
        kwargs["host"] = os.environ.get("FASTMCP_HOST", "0.0.0.0")
        kwargs["port"] = int(os.environ.get("FASTMCP_PORT", "8080"))
        kwargs["stateless_http"] = True
    mcp.run(transport=transport, **kwargs)


if __name__ == "__main__":
    main()
