"""Property MCP server — thin wrapper over property_core for AI hosts.

Run:  uv run property-mcp
"""

from __future__ import annotations

from functools import partial
from typing import Optional

import anyio
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "property-server",
    instructions=(
        "UK property data tools. Use property_report for full deal analysis "
        "(one call: comps + EPC + yield + market). Use property_comps for "
        "granular comparable sales, property_yield for yield breakdown, "
        "property_epc for energy certificates, stamp_duty for SDLT, "
        "property_blocks for block-buy opportunities, company_search for "
        "Companies House lookups."
    ),
    host="0.0.0.0",
    port=8080,
    stateless_http=True,
)


# ---------------------------------------------------------------------------
# Tools — each one calls property_core and returns model_dump()
# ---------------------------------------------------------------------------


@mcp.tool()
async def property_report(
    address: str,
    include_rentals: bool = True,
    include_sales_market: bool = True,
    ppd_months: int = 24,
    search_radius: float = 0.5,
) -> dict:
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
    from property_core import PropertyReportService

    report = await PropertyReportService().generate_report(
        address_query=address,
        include_rentals=include_rentals,
        include_sales_market=include_sales_market,
        ppd_months=ppd_months,
        search_radius=search_radius,
    )
    return report.model_dump(mode="json", exclude_none=True)


@mcp.tool()
async def property_comps(
    postcode: str,
    months: int = 24,
    limit: int = 30,
    search_level: str = "sector",
    address: Optional[str] = None,
    property_type: Optional[str] = None,
    enrich_epc: bool = False,
) -> dict:
    """Comparable property sales from Land Registry Price Paid Data.

    Auto-escalates to wider search area if fewer than 5 results found.

    Args:
        postcode: UK postcode (e.g. "SW1A 1AA", "NG11 9HD")
        months: Lookback period in months (default 24)
        limit: Max transactions to return (default 30)
        search_level: Search area granularity - usually leave as default
        address: Optional street address to identify subject property and show percentile rank
        property_type: Filter by type: F=flat, D=detached, S=semi, T=terraced (default all)
        enrich_epc: Set true to add floor area, price/sqft, and EPC rating to each comp
    """
    from property_core import PPDService
    from property_core.epc_client import EPCClient
    from property_core.enrichment import compute_enriched_stats, enrich_comps_with_epc

    result = await anyio.to_thread.run_sync(
        partial(
            PPDService().comps,
            postcode=postcode,
            months=months,
            limit=limit,
            search_level=search_level,
            address=address,
            property_type=property_type,
            auto_escalate=True,
        )
    )

    if enrich_epc and result.transactions:
        epc = EPCClient()
        if epc.is_configured():
            result.transactions = await enrich_comps_with_epc(
                result.transactions, epc
            )
            result = compute_enriched_stats(result)

    return result.model_dump(mode="json")


@mcp.tool()
async def property_yield(
    postcode: str,
    months: int = 24,
    search_level: str = "sector",
    radius: float = 0.5,
) -> dict:
    """Calculate rental yield for a UK postcode.

    Combines Land Registry sales data with Rightmove rental listings.

    Args:
        postcode: UK postcode (e.g. "NG11", "SW1A 1AA")
        months: Sales lookback period in months (default 24)
        search_level: "sector" (recommended), "district", or "postcode"
        radius: Rental search radius in miles (default 0.5)
    """
    from property_core import calculate_yield

    result = await calculate_yield(
        postcode=postcode,
        months=months,
        search_level=search_level,
        radius=radius,
    )
    return result.model_dump(mode="json")


@mcp.tool()
async def property_epc(
    postcode: str,
    address: Optional[str] = None,
) -> dict:
    """EPC certificate for a UK property — rating, score, floor area,
    construction age, heating costs, and improvement potential.

    Args:
        postcode: UK postcode (e.g. "SW1A 1AA")
        address: Optional street address for exact match
    """
    from property_core.epc_client import EPCClient

    epc = EPCClient()
    if not epc.is_configured():
        return {"error": "EPC service not configured (set EPC_API_EMAIL and EPC_API_KEY)"}

    result = await epc.search_by_postcode(postcode, address=address)
    if not result:
        return {"error": f"No EPC found for {address or ''} {postcode}".strip()}

    return result.model_dump(mode="json", exclude_none=True)


@mcp.tool()
async def property_blocks(
    postcode: str,
    months: int = 24,
    min_transactions: int = 2,
) -> dict:
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
    return result.model_dump(mode="json")


@mcp.tool()
async def stamp_duty(
    price: int,
    additional_property: bool = True,
    first_time_buyer: bool = False,
    non_resident: bool = False,
) -> dict:
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
    return result.model_dump(mode="json")


@mcp.tool()
async def company_search(
    query: str,
) -> dict:
    """Search Companies House for a UK company by name or number.

    If query looks like a company number (digits only), fetches directly.
    Otherwise searches by name.

    Args:
        query: Company name (e.g. "Tesco") or number (e.g. "00445790")
    """
    from property_core.companies_house_client import CompaniesHouseClient

    client = CompaniesHouseClient()
    if not client.is_configured():
        return {"error": "Companies House not configured (set COMPANIES_HOUSE_API_KEY)"}

    result = await anyio.to_thread.run_sync(partial(client.lookup, query))
    return result.model_dump(mode="json")


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
