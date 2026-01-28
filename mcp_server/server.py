"""Property MCP server — thin wrapper over property_core.

Run:  uv run property-mcp
Or:   uv run python -m mcp_server.server
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from property_core import PPDService, PlanningService
from property_core.postcode_client import PostcodeClient

UI_DIR = Path(__file__).parent / "ui"

mcp = FastMCP(
    "property-server",
    instructions=(
        "UK property data tools. Use property_comps to get comparable sales "
        "with price statistics for any UK postcode. Use property_postcode_info "
        "to look up local authority and area details."
    ),
)

# ---------------------------------------------------------------------------
# Services (instantiated once)
# ---------------------------------------------------------------------------
_ppd = PPDService()
_planning = PlanningService()
_postcode = PostcodeClient()

# ---------------------------------------------------------------------------
# UI Resources
# ---------------------------------------------------------------------------

@mcp.resource("ui://property/comps-dashboard", mime_type="text/html")
def comps_dashboard_ui() -> str:
    """Interactive comparable sales dashboard."""
    return (UI_DIR / "comps_dashboard.html").read_text()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def property_comps(
    postcode: str,
    months: int = 24,
    limit: int = 30,
    search_level: str = "sector",
    address: Optional[str] = None,
) -> str:
    """Get comparable property sales for a UK postcode.

    Returns price statistics (median, mean, percentiles) and individual
    transactions from the Land Registry Price Paid Data.

    Args:
        postcode: UK postcode (e.g. "SW1A 1AA", "B1 1BB")
        months: Lookback period in months (default 24)
        limit: Max transactions to return (default 30, max 200)
        search_level: "sector" (e.g. SW1A 1), "district" (SW1A), or "postcode" (exact)
        address: Optional address to identify a subject property for comparison
    """
    result = _ppd.comps(
        postcode=postcode,
        months=months,
        limit=limit,
        search_level=search_level,
        address=address,
    )
    return result.model_dump_json()


@mcp.tool()
def property_transactions(
    postcode: str,
    limit: int = 20,
) -> str:
    """Search Land Registry transactions by postcode.

    Args:
        postcode: UK postcode or prefix (e.g. "SW1A 1AA" or "SW1A")
        limit: Max results (default 20, max 200)
    """
    result = _ppd.search_transactions(postcode=postcode, limit=limit)
    # Convert PPDTransaction objects to dicts for JSON serialization
    result["results"] = [
        t.model_dump() if hasattr(t, "model_dump") else t
        for t in result.get("results", [])
    ]
    return json.dumps(result, default=str)


@mcp.tool()
def property_postcode_info(postcode: str) -> str:
    """Look up local authority, region, and area details for a UK postcode.

    Args:
        postcode: UK postcode (e.g. "SW1A 2AA")
    """
    result = _postcode.get_local_authority(postcode, include_raw=True)
    return json.dumps(result, default=str)


@mcp.tool()
def property_planning_search(postcode: str) -> str:
    """Find planning portal and search URLs for a UK postcode.

    Args:
        postcode: UK postcode (e.g. "S1 2HH", "SW1A 2AA")
    """
    result = _planning.search(postcode)
    return json.dumps(result, default=str)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    mcp.run()


if __name__ == "__main__":
    main()
