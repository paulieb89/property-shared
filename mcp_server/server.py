"""Property MCP server — UK property data tools for AI hosts.

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

from property_core import PPDService, PropertyReportService, calculate_yield
from property_core.epc_client import EPCClient
from property_core.enrichment import compute_enriched_stats, enrich_comps_with_epc

UI_DIR = Path(__file__).parent / "ui"

mcp = FastMCP(
    "property-server",
    instructions=(
        "UK property data tools. Use property_report for full deal analysis "
        "(one call: comps + EPC + yield + market). Use property_comps for "
        "granular comparable sales, property_yield for yield breakdown, "
        "property_epc for energy certificates, stamp_duty for SDLT, "
        "property_blocks for block-buy opportunities."
    ),
    host="0.0.0.0",
    port=8080,
    stateless_http=True,
)

# Service
_ppd = PPDService()

# ---------------------------------------------------------------------------
# Auto-Escalation for Thin Markets
# ---------------------------------------------------------------------------

MIN_RESULTS = 5  # Minimum results before auto-escalating
ESCALATION_PATH = {"postcode": "sector", "sector": "district", "district": None}


async def _fetch_comps_with_escalation(
    postcode: str,
    months: int,
    limit: int,
    search_level: str,
    address: Optional[str],
    property_type: Optional[str] = None,
) -> tuple:
    """Fetch comps, auto-escalating search level if thin market."""
    original_level = search_level

    result = await anyio.to_thread.run_sync(
        partial(
            _ppd.comps,
            postcode=postcode,
            months=months,
            limit=limit,
            search_level=search_level,
            address=address,
            property_type=property_type,
        )
    )

    # Auto-escalate if thin market
    while result.thin_market and len(result.transactions) < MIN_RESULTS:
        next_level = ESCALATION_PATH.get(search_level)
        if not next_level:
            break  # Can't escalate further

        search_level = next_level
        result = await anyio.to_thread.run_sync(
            partial(
                _ppd.comps,
                postcode=postcode,
                months=months,
                limit=limit,
                search_level=search_level,
                address=address,
                property_type=property_type,
            )
        )

    return result, original_level, search_level


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
    property_type: Optional[str] = None,
    enrich_epc: bool = False,
) -> types.CallToolResult:
    """Comparable property sales from Land Registry Price Paid Data.

    Args:
        postcode: UK postcode (e.g. "SW1A 1AA", "NG11 9HD")
        months: Lookback period in months (default 24)
        limit: Max transactions to return (default 30)
        search_level: Search area granularity - usually leave as default
        address: Optional street address to identify subject property and show percentile rank
        property_type: Filter by type: F=flat, D=detached, S=semi, T=terraced (default all)
        enrich_epc: Set true to add floor area, price/sqft, and EPC rating to each comp
    """
    result, requested_level, actual_level = await _fetch_comps_with_escalation(
        postcode, months, limit, search_level, address, property_type
    )

    # EPC enrichment if requested
    if enrich_epc and result.transactions:
        epc = EPCClient()
        if epc.is_configured():
            result.transactions = await enrich_comps_with_epc(
                result.transactions, epc
            )
            result = compute_enriched_stats(result)

    data = result.model_dump(mode="json")
    count = len(data.get("transactions", []))

    # Track escalation in response data
    if requested_level != actual_level:
        data["_escalated_from"] = requested_level
        data["_escalated_to"] = actual_level
        if data.get("query"):
            data["query"]["search_level"] = actual_level

    # Build summary
    summary = f"Found {count} comparable sales for {postcode}"
    if requested_level != actual_level:
        summary += f" (expanded search from {requested_level} to {actual_level})"
    if enrich_epc:
        match_rate = data.get("epc_match_rate")
        if match_rate is not None:
            summary += f" (EPC matched {match_rate}%)"

    return types.CallToolResult(
        content=[
            types.TextContent(
                type="text",
                text=json.dumps({
                    "summary": summary,
                    "median": data.get("median"),
                    "count": count,
                    "median_price_per_sqft": data.get("median_price_per_sqft"),
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
# Block Analyzer
# ---------------------------------------------------------------------------

@mcp.tool(meta=TOOL_UI_META)
async def property_blocks(
    postcode: str,
    months: int = 24,
    min_transactions: int = 2,
) -> types.CallToolResult:
    """Find buildings with multiple flat sales — block buying opportunities.

    Groups Land Registry transactions by building to identify blocks being
    sold off, investor exits, and bulk-buy opportunities.

    Args:
        postcode: UK postcode (e.g. "B1 1AA")
        months: Lookback period in months (default 24)
        min_transactions: Minimum sales per building to qualify (default 2)
    """
    from property_core.block_service import analyze_blocks

    result = await anyio.to_thread.run_sync(
        partial(
            analyze_blocks,
            postcode=postcode,
            months=months,
            min_transactions=min_transactions,
        )
    )
    data = result.model_dump(mode="json")

    return types.CallToolResult(
        content=[
            types.TextContent(
                type="text",
                text=json.dumps({
                    "summary": f"Found {result.blocks_found} flat blocks for {postcode}",
                    "blocks_found": result.blocks_found,
                }),
            )
        ],
        structuredContent=data,
        _meta=TOOL_UI_META,
    )


# ---------------------------------------------------------------------------
# Stamp Duty Calculator
# ---------------------------------------------------------------------------

@mcp.tool()
async def stamp_duty(
    price: int,
    additional_property: bool = True,
    first_time_buyer: bool = False,
    non_resident: bool = False,
) -> types.CallToolResult:
    """Calculate UK Stamp Duty Land Tax (SDLT) for a residential property.

    Args:
        price: Purchase price in £
        additional_property: True if buying additional property (+5% surcharge)
        first_time_buyer: True for first-time buyer relief (up to £300k nil rate)
        non_resident: True if buyer not UK resident (+2% surcharge)
    """
    from property_core.stamp_duty import calculate_stamp_duty

    result = calculate_stamp_duty(
        price=price,
        additional_property=additional_property,
        first_time_buyer=first_time_buyer,
        non_resident=non_resident,
    )
    data = result.model_dump(mode="json")

    return types.CallToolResult(
        content=[
            types.TextContent(
                type="text",
                text=json.dumps({
                    "summary": f"SDLT for £{price:,}: £{result.total_sdlt:,.0f} ({result.effective_rate}%)",
                    "total_sdlt": result.total_sdlt,
                    "effective_rate": result.effective_rate,
                }),
            )
        ],
        structuredContent=data,
    )


# ---------------------------------------------------------------------------
# Property Report — full deal analysis in one call
# ---------------------------------------------------------------------------

_report_service = PropertyReportService()


@mcp.tool(meta=TOOL_UI_META)
async def property_report(
    address: str,
    include_rentals: bool = True,
    include_sales_market: bool = True,
    ppd_months: int = 24,
    search_radius: float = 0.5,
) -> types.CallToolResult:
    """Full deal analysis for a UK property in one call.

    Returns sale history, area comps, EPC rating with refurb potential,
    rental market, current sales market, yield estimate, and value range.

    Args:
        address: Address with postcode, e.g. "10 Downing Street, SW1A 2AA"
        include_rentals: Include Rightmove rental market analysis (default true)
        include_sales_market: Include Rightmove sales market (default true)
        ppd_months: Lookback period for comparable sales (default 24)
        search_radius: Radius in miles for Rightmove searches (default 0.5)
    """
    report = await _report_service.generate_report(
        address_query=address,
        include_rentals=include_rentals,
        include_sales_market=include_sales_market,
        ppd_months=ppd_months,
        search_radius=search_radius,
    )
    data = report.model_dump(mode="json", exclude_none=True)

    # Build summary from key insights
    insights = report.key_insights or []
    summary_parts = [f"Property report for {report.query_postcode}"]
    summary_parts.extend(insights[:5])

    sources_available = [s.name for s in (report.sources or []) if s.available]
    if sources_available:
        summary_parts.append(f"Sources: {', '.join(sources_available)}")

    return types.CallToolResult(
        content=[
            types.TextContent(
                type="text",
                text="\n".join(summary_parts),
            )
        ],
        structuredContent=data,
        _meta=TOOL_UI_META,
    )


# ---------------------------------------------------------------------------
# EPC Direct Lookup
# ---------------------------------------------------------------------------

@mcp.tool()
async def property_epc(
    postcode: str,
    address: Optional[str] = None,
) -> types.CallToolResult:
    """EPC certificate for a UK property — rating, score, floor area,
    construction age, heating costs, CO2 emissions, and improvement potential.

    Args:
        postcode: UK postcode (e.g. "SW1A 1AA")
        address: Optional street address for exact match
    """
    epc = EPCClient()
    if not epc.is_configured():
        return types.CallToolResult(
            content=[
                types.TextContent(
                    type="text",
                    text="EPC service not configured (set EPC_API_EMAIL and EPC_API_KEY)",
                )
            ],
        )

    result = await epc.search_by_postcode(postcode, address=address)
    if not result:
        return types.CallToolResult(
            content=[
                types.TextContent(
                    type="text",
                    text=f"No EPC found for {address or ''} {postcode}".strip(),
                )
            ],
        )

    data = result.model_dump(mode="json", exclude_none=True)

    summary_parts = [f"EPC for {address or postcode}"]
    if result.rating:
        summary_parts.append(f"Rating: {result.rating} (score {result.score})")
    if result.floor_area:
        summary_parts.append(f"Floor area: {result.floor_area} sqm")
    if result.property_type:
        summary_parts.append(f"Type: {result.property_type}")
    if result.construction_age:
        summary_parts.append(f"Built: {result.construction_age}")

    return types.CallToolResult(
        content=[
            types.TextContent(
                type="text",
                text="\n".join(summary_parts),
            )
        ],
        structuredContent=data,
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
