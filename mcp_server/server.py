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

from property_core import PPDService

UI_DIR = Path(__file__).parent / "ui"

mcp = FastMCP(
    "property-server",
    instructions="UK property comparables tool. Use property_comps to get comparable sales for any UK postcode.",
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
def _load_widget_html() -> str:
    # Use Vite-bundled version (follows official MCP Apps pattern exactly)
    return (UI_DIR / "comps_dashboard_vite.html").read_text()


@mcp.resource(
    WIDGET_URI,
    name="Comps dashboard",
    description="Comparable sales dashboard with price statistics",
    mime_type=WIDGET_MIME,
)
def comps_dashboard_resource() -> str:
    return _load_widget_html()


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
# Entry point
# ---------------------------------------------------------------------------

def main():
    mcp.run()


if __name__ == "__main__":
    main()
