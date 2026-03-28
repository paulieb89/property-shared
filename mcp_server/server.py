"""Property MCP server — thin wrapper over property_core for AI hosts.

Run:  uv run property-mcp
"""

from __future__ import annotations

import json
from functools import partial
from statistics import median as stat_median
from typing import Any, Optional

import anyio
from fastmcp import FastMCP
from fastmcp.tools.tool import ToolResult


def _slim(obj: Any) -> Any:
    """Strip raw/images/floorplans for LLM-friendly content."""
    if isinstance(obj, dict):
        return {k: _slim(v) for k, v in obj.items()
                if k not in ("raw", "images", "floorplans")}
    if isinstance(obj, list):
        return [_slim(item) for item in obj]
    return obj


def _content(summary: str, data: dict) -> str:
    """Build content string: summary + slimmed JSON data for LLM hosts."""
    return summary + "\n\n" + json.dumps(_slim(data), indent=2, default=str)

mcp = FastMCP(
    "property-server",
    instructions=(
        "UK property data tools. Start with property_report for full data pull "
        "(comps + EPC + yield + market in one call). Use property_comps for area "
        "comparable sales with stats, ppd_transactions for specific property history "
        "or filtered searches, rightmove_search to browse current listings for sale "
        "or rent, rightmove_listing for full details on a specific property. "
        "property_epc for energy certificates, property_yield or rental_analysis "
        "for rental market and yield figures, stamp_duty for SDLT, "
        "property_blocks for block-buy opportunities, planning_search for council "
        "planning portals, company_search for Companies House lookups."
    ),
)


# ---------------------------------------------------------------------------
# Tools — each one calls property_core and returns ToolResult
# ---------------------------------------------------------------------------


@mcp.tool()
async def property_report(
    address: str,
    include_rentals: bool = True,
    include_sales_market: bool = True,
    ppd_months: int = 24,
    search_radius: float = 0.5,
    property_type: Optional[str] = None,
) -> ToolResult:
    """Full data pull for a UK property in one call.

    Returns sale history, area comps, EPC rating, rental market listings,
    current sales market listings, rental yield calculation, and price range
    from area median.

    Requires a street address + postcode for subject property identification.
    Postcode-only (e.g. "NG1 2NS") returns area-level data without a subject
    property — use property_comps or property_yield for postcode-only queries.

    Args:
        address: Street address with postcode, e.g. "10 Downing Street, SW1A 2AA"
        include_rentals: Include Rightmove rental market analysis (default true)
        include_sales_market: Include Rightmove sales market (default true)
        ppd_months: Lookback period for comparable sales (default 24)
        search_radius: Radius in miles for Rightmove searches (default 0.5)
        property_type: Filter comparable sales by type: F=flat, D=detached, S=semi, T=terraced (default all)
    """
    from property_core import PropertyReportService

    report = await PropertyReportService().generate_report(
        address_query=address,
        include_rentals=include_rentals,
        include_sales_market=include_sales_market,
        ppd_months=ppd_months,
        search_radius=search_radius,
        property_type=property_type,
    )
    data = report.model_dump(mode="json", exclude_none=True)

    from property_core.interpret import generate_insights

    insights = generate_insights(report)
    sources = [s.name for s in (report.sources or []) if s.available]
    summary = f"Property report for {report.query_postcode}"
    if insights:
        summary += "\n" + "\n".join(insights[:5])
    if sources:
        summary += f"\nSources: {', '.join(sources)}"

    return ToolResult(content=_content(summary, data), structured_content=data)


@mcp.tool()
async def property_comps(
    postcode: str,
    months: int = 24,
    limit: int = 30,
    search_level: str = "sector",
    address: Optional[str] = None,
    property_type: Optional[str] = None,
    enrich_epc: bool = False,
) -> ToolResult:
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

    data = result.model_dump(mode="json")

    summary = f"Found {result.count} comps for {postcode}"
    if result.median:
        summary += f", median \u00a3{result.median:,}"
    if result.escalated_from:
        summary += f" (expanded from {result.escalated_from} to {result.escalated_to})"
    if enrich_epc and result.epc_match_rate is not None:
        summary += f" (EPC matched {result.epc_match_rate}%)"

    return ToolResult(content=_content(summary, data), structured_content=data)


@mcp.tool()
async def ppd_transactions(
    postcode: Optional[str] = None,
    street: Optional[str] = None,
    town: Optional[str] = None,
    paon: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    property_type: Optional[str] = None,
    limit: int = 25,
) -> ToolResult:
    """Search Land Registry transactions by postcode, address, date range, or price.

    Use for specific property history ("what has 10 Downing Street sold for?")
    or filtered market queries ("all sales over 500k in SW1 last year").

    Args:
        postcode: UK postcode (e.g. "SW1A 1AA") - required for postcode search
        street: Street name for address-based search
        town: Town name for address-based search
        paon: Primary address (house name/number) for address-based search
        from_date: Start date filter (ISO format, e.g. "2023-01-01")
        to_date: End date filter (ISO format)
        min_price: Minimum price filter in £
        max_price: Maximum price filter in £
        property_type: Filter by type: F=flat, D=detached, S=semi, T=terraced
        limit: Max results to return (default 25)
    """
    from property_core import PPDService

    svc = PPDService()

    if street or paon:
        result = await anyio.to_thread.run_sync(
            partial(
                svc.address_search,
                paon=paon,
                street=street,
                town=town,
                postcode=postcode,
                limit=limit,
            )
        )
    else:
        result = await anyio.to_thread.run_sync(
            partial(
                svc.search_transactions,
                postcode=postcode,
                postcode_prefix=None,
                from_date=from_date,
                to_date=to_date,
                min_price=min_price,
                max_price=max_price,
                property_type=property_type,
                limit=limit,
            )
        )

    # Serialize Pydantic models in results list
    result["results"] = [t.model_dump(mode="json") for t in result["results"]]
    if result.get("raw"):
        del result["raw"]

    count = result["count"]
    location = postcode or street or "search"
    summary = f"Found {count} transactions for {location}"
    if result.get("warnings"):
        summary += f" (warnings: {', '.join(result['warnings'])})"

    return ToolResult(content=_content(summary, result), structured_content=result)


@mcp.tool()
async def property_yield(
    postcode: str,
    months: int = 24,
    search_level: str = "sector",
    property_type: Optional[str] = None,
    radius: float = 0.5,
) -> ToolResult:
    """Calculate rental yield for a UK postcode.

    Combines Land Registry sales data with Rightmove rental listings
    to produce a gross yield figure.

    Args:
        postcode: UK postcode (e.g. "NG11", "SW1A 1AA")
        months: Sales lookback period in months (default 24)
        search_level: "sector" (recommended), "district", or "postcode"
        property_type: Filter comparable sales by type: F=flat, D=detached, S=semi, T=terraced (default all)
        radius: Rental search radius in miles (default 0.5)
    """
    from property_core import calculate_yield

    result = await calculate_yield(
        postcode=postcode,
        months=months,
        search_level=search_level,
        property_type=property_type,
        radius=radius,
    )
    data = result.model_dump(mode="json")

    from property_core.interpret import classify_data_quality, classify_yield

    summary = f"Yield analysis for {postcode}"
    if result.gross_yield_pct is not None:
        summary += f": {result.gross_yield_pct:.1f}% gross yield"
        summary += f" ({classify_yield(result.gross_yield_pct)})"
    summary += f", data quality: {classify_data_quality(result.sale_count, result.rental_count)}"

    return ToolResult(content=_content(summary, data), structured_content=data)


@mcp.tool()
async def rental_analysis(
    postcode: str,
    radius: float = 0.5,
    purchase_price: Optional[int] = None,
) -> ToolResult:
    """Rental market analysis for a UK postcode.

    Returns median/average rent, listing count, and rent range.
    Optionally calculates gross yield from a given purchase price.

    Args:
        postcode: UK postcode (e.g. "NG1 1AA")
        radius: Search radius in miles (default 0.5)
        purchase_price: Optional purchase price to calculate gross yield
    """
    from property_core.rental_service import analyze_rentals

    result = await analyze_rentals(
        postcode,
        radius=radius,
        purchase_price=purchase_price,
    )
    data = result.model_dump(mode="json")

    summary = f"Rental analysis for {postcode}: {result.rental_listings_count} listings"
    if result.median_rent_monthly:
        summary += f", median \u00a3{result.median_rent_monthly:,.0f}/month"
    if result.gross_yield_pct is not None:
        summary += f", {result.gross_yield_pct:.1f}% gross yield"

    return ToolResult(content=_content(summary, data), structured_content=data)


@mcp.tool()
async def property_epc(
    postcode: str,
    address: Optional[str] = None,
) -> ToolResult:
    """EPC certificate for a UK property — energy rating, score, floor area,
    construction age, heating costs, and improvement potential.

    Without an address, returns an arbitrary certificate from the postcode —
    not a specific property. Always provide address for subject property lookup.

    Args:
        postcode: UK postcode (e.g. "SW1A 1AA")
        address: Street address for exact match (strongly recommended)
    """
    from property_core.epc_client import EPCClient

    epc = EPCClient()
    if not epc.is_configured():
        return ToolResult(content="EPC service not configured (set EPC_API_EMAIL and EPC_API_KEY)")

    result = await epc.search_by_postcode(postcode, address=address)
    if not result:
        return ToolResult(content=f"No EPC found for {address or ''} {postcode}".strip())

    data = result.model_dump(mode="json", exclude_none=True)

    parts = [f"EPC for {address or postcode}"]
    if result.rating:
        parts.append(f"Rating: {result.rating} (score {result.score})")
    if result.floor_area:
        parts.append(f"Floor area: {result.floor_area} sqm")
    if result.property_type:
        parts.append(f"Type: {result.property_type}")
    if result.construction_age:
        parts.append(f"Built: {result.construction_age}")

    return ToolResult(content=_content(", ".join(parts), data), structured_content=data)


@mcp.tool()
async def rightmove_search(
    postcode: str,
    property_type: str = "sale",
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    min_bedrooms: Optional[int] = None,
    max_bedrooms: Optional[int] = None,
    radius: Optional[float] = None,
    max_pages: int = 1,
    sort_by: Optional[str] = None,
) -> ToolResult:
    """Search Rightmove property listings for sale or rent near a postcode.

    Returns prices, addresses, bedrooms, agent details, and listing URLs.

    Args:
        postcode: UK postcode (e.g. "NG1 1AA", "SW1A 2AA")
        property_type: "sale" or "rent" (default "sale")
        min_price: Minimum price/rent filter in £
        max_price: Maximum price/rent filter in £
        min_bedrooms: Minimum bedrooms filter
        max_bedrooms: Maximum bedrooms filter
        radius: Search radius in miles (default varies by area)
        max_pages: Max pages to fetch (default 1, ~25 listings per page)
        sort_by: Sort order: "newest", "oldest", "price_low", "price_high", "most_reduced" (default: Rightmove default)
    """
    from property_core.rightmove_location import RightmoveLocationAPI
    from property_core.rightmove_scraper import fetch_listings

    url = await anyio.to_thread.run_sync(
        partial(
            RightmoveLocationAPI().build_search_url,
            postcode,
            property_type=property_type,
            min_price=min_price,
            max_price=max_price,
            min_bedrooms=min_bedrooms,
            max_bedrooms=max_bedrooms,
            radius=radius,
            sort_by=sort_by,
        )
    )

    listings = await anyio.to_thread.run_sync(
        partial(fetch_listings, url, max_pages=max_pages)
    )

    data = {
        "search_url": url,
        "count": len(listings),
        "listings": [listing.model_dump(mode="json") for listing in listings],
    }

    prices = [listing.price for listing in listings if listing.price and listing.price > 0]
    summary = f"Found {len(listings)} {property_type} listings near {postcode}"
    if prices:
        median = int(stat_median(prices))
        summary += f", median \u00a3{median:,}, range \u00a3{min(prices):,}-\u00a3{max(prices):,}"

    return ToolResult(content=_content(summary, data), structured_content=data)


@mcp.tool()
async def rightmove_listing(
    property_id: str,
) -> ToolResult:
    """Full details for a Rightmove property listing.

    Returns price, tenure, lease years remaining, service charge, ground rent,
    council tax band, floor area, key features, nearest stations, and floorplan URLs.

    Args:
        property_id: Rightmove property URL (e.g. "https://www.rightmove.co.uk/properties/12345678") or numeric ID (e.g. "12345678")
    """
    from property_core.rightmove_scraper import fetch_listing

    result = await anyio.to_thread.run_sync(
        partial(fetch_listing, property_id)
    )
    data = result.model_dump(mode="json")

    summary = f"{result.address or 'Property'}"
    if result.price:
        summary += f" — \u00a3{result.price:,}"
    if result.tenure_type:
        summary += f" ({result.tenure_type})"
    if result.bedrooms:
        summary += f", {result.bedrooms} bed"
    if result.display_size:
        summary += f", {result.display_size}"

    return ToolResult(content=_content(summary, data), structured_content=data)


@mcp.tool()
async def property_blocks(
    postcode: str,
    months: int = 24,
    min_transactions: int = 2,
) -> ToolResult:
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

    summary = f"Found {result.blocks_found} flat blocks for {postcode}"
    if result.blocks:
        top = result.blocks[0]
        summary += f" (top: {top.building_name}, {top.transaction_count} sales)"

    return ToolResult(content=_content(summary, data), structured_content=data)


@mcp.tool()
async def stamp_duty(
    price: int,
    additional_property: bool = True,
    first_time_buyer: bool = False,
    non_resident: bool = False,
) -> ToolResult:
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

    summary = f"SDLT for \u00a3{price:,}: \u00a3{result.total_sdlt:,.0f} ({result.effective_rate}% effective rate)"

    return ToolResult(content=_content(summary, data), structured_content=data)


@mcp.tool()
async def planning_search(
    postcode: str,
) -> ToolResult:
    """Find the planning portal for a UK postcode.

    Returns the local council, planning system type, and direct search URLs.
    For Idox councils (most common), provides a clickable URL pre-filled with the postcode.

    Args:
        postcode: UK postcode (e.g. "S1 1AA", "SW1A 2AA")
    """
    from property_core.planning_service import PlanningService

    result = await anyio.to_thread.run_sync(
        partial(PlanningService().search, postcode)
    )

    if result.get("council_found"):
        council = result.get("council", {})
        name = council.get("name", "Unknown")
        system = council.get("system", "unknown")
        summary = f"{name} ({system} system)"
        urls = result.get("search_urls", {})
        if urls.get("direct_search"):
            summary += f", direct search: {urls['direct_search']}"
    else:
        summary = f"No planning portal found for {postcode}"

    return ToolResult(content=_content(summary, result), structured_content=result)


@mcp.tool()
async def company_search(
    query: str,
) -> ToolResult:
    """Search Companies House for a UK company by name or number.

    If query looks like a company number (e.g. "00445790", "SC123456"),
    fetches directly. Otherwise searches by name.

    Args:
        query: Company name (e.g. "Tesco") or number (e.g. "00445790")
    """
    from property_core.companies_house_client import CompaniesHouseClient

    client = CompaniesHouseClient()
    if not client.is_configured():
        return ToolResult(content="Companies House not configured (set COMPANIES_HOUSE_API_KEY)")

    result = await anyio.to_thread.run_sync(partial(client.lookup, query))
    data = result.model_dump(mode="json")

    # CompanyRecord has company_name; CompanySearchResult has total_results
    if hasattr(result, "company_name"):
        summary = f"{result.company_name} ({result.company_status})"
    else:
        summary = f"Found {result.total_results} companies for '{query}'"

    return ToolResult(content=_content(summary, data), structured_content=data)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    import os

    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport not in ("stdio", "sse", "http"):
        transport = "stdio"

    kwargs = {}
    if transport in ("sse", "http"):
        kwargs["host"] = os.environ.get("FASTMCP_HOST", "0.0.0.0")
        kwargs["port"] = int(os.environ.get("FASTMCP_PORT", "8080"))

    mcp.run(transport=transport, **kwargs)


if __name__ == "__main__":
    main()
