"""Property MCP server — minimal version with one tool + UI.

Run:  uv run property-mcp
"""

from __future__ import annotations

import json
from functools import lru_cache, partial
from pathlib import Path
from typing import Optional

import anyio
import mcp.types as types
from mcp.server.fastmcp import FastMCP

from property_core import PPDService, calculate_yield

UI_DIR = Path(__file__).parent / "ui"

mcp = FastMCP(
    "property-server",
    instructions="UK property data tools. Use property_comps for comparable sales, property_yield for rental yield analysis.",
    host="0.0.0.0",
    port=8080,
    stateless_http=True,
)

# Service
_ppd = PPDService()

# ---------------------------------------------------------------------------
# UI Resource
# ---------------------------------------------------------------------------

WIDGET_URI = "ui://property/comps-dashboard"
WIDGET_MIME = "text/html;profile=mcp-app"

TOOL_UI_META = {
    "ui": {"resourceUri": WIDGET_URI},
    "ui/resourceUri": WIDGET_URI,
}


@lru_cache(maxsize=None)
def _load_dashboard_html() -> str:
    return (UI_DIR / "property_dashboard.html").read_text()


@mcp.resource(
    WIDGET_URI,
    name="Property dashboard",
    description="Property data dashboard - comps and yield analysis",
    mime_type=WIDGET_MIME,
)
def comps_dashboard_resource() -> str:
    return _load_dashboard_html()


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

@mcp.tool(meta=TOOL_UI_META)
async def property_comps(
    postcode: str,
    months: int = 24,
    limit: int = 30,
    search_level: str = "sector",
    address: Optional[str] = None,
) -> types.CallToolResult:
    """Get comparable property sales for a UK postcode.

    Args:
        postcode: UK postcode (e.g. "SW1A 1AA", "NG11 9HD")
        months: Lookback period in months (default 24)
        limit: Max transactions to return (default 30)
        search_level: "sector" (recommended), "district", or "postcode"
        address: Optional street address to identify subject property
    """
    result = await anyio.to_thread.run_sync(
        partial(
            _ppd.comps,
            postcode=postcode,
            months=months,
            limit=limit,
            search_level=search_level,
            address=address,
        )
    )
    data = result.model_dump(mode="json")
    count = len(data.get("transactions", []))

    return types.CallToolResult(
        content=[
            types.TextContent(
                type="text",
                text=json.dumps({
                    "summary": f"Found {count} comparable sales for {postcode}",
                    "median": data.get("median"),
                    "count": count,
                }),
            )
        ],
        structuredContent=data,
        _meta=TOOL_UI_META,
    )


# ---------------------------------------------------------------------------
# Yield Tool + UI
# ---------------------------------------------------------------------------

YIELD_URI = "ui://property/yield-dashboard"

YIELD_UI_META = {
    "ui": {"resourceUri": YIELD_URI},
    "ui/resourceUri": YIELD_URI,
}


@mcp.resource(
    YIELD_URI,
    name="Property dashboard",
    description="Property data dashboard - comps and yield analysis",
    mime_type=WIDGET_MIME,
)
def yield_dashboard_resource() -> str:
    return _load_dashboard_html()


@mcp.tool(meta=YIELD_UI_META)
async def property_yield(
    postcode: str,
    months: int = 24,
    search_level: str = "sector",
    radius: float = 0.5,
) -> types.CallToolResult:
    """Calculate rental yield for a UK postcode.

    Combines Land Registry sales data with Rightmove rental listings.

    Args:
        postcode: UK postcode (e.g. "NG11", "SW1A 1AA")
        months: Sales lookback period in months (default 24)
        search_level: "sector" (recommended), "district", or "postcode"
        radius: Rental search radius in miles (default 0.5)
    """
    result = await calculate_yield(
        postcode=postcode,
        months=months,
        search_level=search_level,
        radius=radius,
    )
    data = result.model_dump(mode="json")

    return types.CallToolResult(
        content=[
            types.TextContent(
                type="text",
                text=json.dumps({
                    "summary": f"Yield analysis for {postcode}",
                    "gross_yield_pct": data.get("gross_yield_pct"),
                    "yield_assessment": data.get("yield_assessment"),
                    "data_quality": data.get("data_quality"),
                }),
            )
        ],
        structuredContent=data,
        _meta=YIELD_UI_META,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    import os
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport not in ("stdio", "sse", "streamable-http"):
        transport = "stdio"
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
