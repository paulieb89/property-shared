"""Plain FastMCP server — property tools, no Prefab UI.

Exposes property_core functions as MCP tools. Suitable for any MCP client
regardless of ext-apps / Prefab UI support.
"""
from __future__ import annotations

from importlib.metadata import version as _pkg_version

import asyncio

import httpx
from fastmcp import FastMCP
from fastmcp.server.http import create_streamable_http_app
from fastmcp.tools import ToolResult
from fastmcp.utilities.types import Image
from mcp.types import TextContent

mcp = FastMCP(
    "property-data",
    version=_pkg_version("property-shared"),
    instructions=(
        "UK property data tools. Use property_report for a full data pull when you "
        "have a street address + postcode. For postcode-only queries use property_comps "
        "and property_yield separately. ppd_transactions for specific property history, "
        "rightmove_search to browse listings by postcode, rightmove_listing for full "
        "detail on one listing, property_epc for energy certificates, rental_analysis "
        "for rental market figures, stamp_duty for SDLT, property_blocks for block-buy "
        "analysis, planning_search for council planning portals, company_search to find "
        "a company by name."
    ),
)


async def _fetch_rightmove_image(url: str) -> bytes | None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"https://propertydata.fly.dev/img?url={url}")
            if resp.status_code != 200:
                return None
            return resp.content
    except Exception:
        return None


@mcp.tool(annotations={"readOnlyHint": True})
async def property_comps(
    postcode: str,
    months: int = 24,
    property_type: str | None = None,
    search_level: str = "sector",
    address: str | None = None,
    limit: int = 50,
    enrich_epc: bool = False,
) -> dict:
    """Comparable sales from Land Registry Price Paid Data.

    limit caps returned transactions (max 200). enrich_epc attaches EPC floor
    area and price-per-sqft to each transaction — slower but richer.
    """
    from property_core import PPDService
    result = PPDService().comps(
        postcode=postcode,
        months=months,
        property_type=property_type,
        search_level=search_level,
        address=address,
        limit=limit,
    )
    if enrich_epc and result.transactions:
        from property_core import EPCClient
        from property_core.enrichment import compute_enriched_stats, enrich_comps_with_epc
        epc = EPCClient()
        await enrich_comps_with_epc(result.transactions, epc)
        compute_enriched_stats(result)
    return result.model_dump()


@mcp.tool(annotations={"readOnlyHint": True})
async def property_yield(
    postcode: str,
    months: int = 24,
    search_level: str = "sector",
    property_type: str | None = None,
) -> dict:
    """Rental yield analysis for a postcode."""
    from property_core import calculate_yield
    return (await calculate_yield(
        postcode=postcode,
        months=months,
        search_level=search_level,
        property_type=property_type,
    )).model_dump()


@mcp.tool(annotations={"readOnlyHint": True})
async def rental_analysis(
    postcode: str,
    radius: float = 0.5,
    purchase_price: int | None = None,
    auto_escalate: bool = True,
) -> dict:
    """Rental market analysis and achievable rent estimate.

    auto_escalate widens the search area when fewer than 5 listings are found
    (thin market). Response includes thin_market, escalated_from, escalated_to
    fields when escalation occurs.
    """
    from property_core import analyze_rentals
    return (await analyze_rentals(
        postcode=postcode,
        radius=radius,
        purchase_price=purchase_price,
        auto_escalate=auto_escalate,
    )).model_dump()


@mcp.tool(annotations={"readOnlyHint": True})
async def property_epc(postcode: str, address: str | None = None) -> dict | None:
    """EPC energy certificate lookup by postcode (+ optional address filter)."""
    from property_core import EPCClient
    result = await EPCClient().search_by_postcode(postcode=postcode, address=address)
    return result.model_dump() if result else None


@mcp.tool(annotations={"readOnlyHint": True})
def stamp_duty(
    price: int,
    additional_property: bool = False,
    first_time_buyer: bool = False,
    non_resident: bool = False,
) -> dict:
    """UK Stamp Duty Land Tax (SDLT) calculation with full breakdown."""
    from property_core import calculate_stamp_duty
    return calculate_stamp_duty(
        price=price,
        additional_property=additional_property,
        first_time_buyer=first_time_buyer,
        non_resident=non_resident,
    ).model_dump()


@mcp.tool(annotations={"readOnlyHint": True})
async def rightmove_search(
    postcode: str,
    listing_type: str = "sale",
    radius: float = 0.5,
    property_type: str | None = None,
    min_bedrooms: int | None = None,
    max_price: int | None = None,
    sort_by: str | None = None,
    max_pages: int = 3,
) -> list[dict]:
    """Fetch Rightmove listings for a postcode.

    listing_type: "sale" or "rent". sort_by: "newest", "most_reduced",
    "price_asc", "price_desc". Images are excluded from results.
    """
    import anyio
    from property_core import RightmoveLocationAPI, fetch_listings
    loc_api = RightmoveLocationAPI()
    search_url = await anyio.to_thread.run_sync(
        lambda: loc_api.build_search_url(
            postcode,
            property_type=listing_type,
            building_type=property_type,
            min_bedrooms=min_bedrooms,
            max_price=max_price,
            radius=radius,
            sort_by=sort_by,
        )
    )
    listings = await anyio.to_thread.run_sync(
        lambda: fetch_listings(search_url, max_pages=max_pages)
    )
    return [l.model_dump(exclude={"images"}) for l in listings]


@mcp.tool(annotations={"readOnlyHint": True})
async def rightmove_listing(
    property_url_or_id: str,
    include_images: bool = False,
    max_images: int = 3,
) -> dict | ToolResult:
    """Full detail for a single Rightmove listing (URL or numeric ID).

    include_images fetches and embeds photos and floorplans as MCP image content.
    max_images caps the number of property photos (default 3); floorplans always included.
    """
    import anyio
    from property_core import fetch_listing

    result = await anyio.to_thread.run_sync(lambda: fetch_listing(property_url_or_id))

    if not include_images:
        return result.model_dump(exclude={"images", "floorplans"})

    photo_urls = (result.images or [])[:max_images]
    floorplan_urls = result.floorplans or []
    all_urls = photo_urls + floorplan_urls

    raw_results = await asyncio.gather(
        *[_fetch_rightmove_image(u) for u in all_urls],
        return_exceptions=True,
    )

    price_str = f"£{result.price:,}" if result.price else "price unknown"
    beds = result.bedrooms if result.bedrooms is not None else "?"
    prop_type = result.property_type or "property"
    address = result.address or "unknown address"
    summary = f"{address} — {price_str} — {beds} bed {prop_type}"

    content: list = [TextContent(type="text", text=summary)]
    for img_bytes in raw_results:
        if isinstance(img_bytes, bytes) and img_bytes:
            content.append(Image(data=img_bytes, format="jpeg"))

    return ToolResult(
        content=content,
        structured_content=result.model_dump(exclude={"images", "floorplans"}),
    )


@mcp.tool(annotations={"readOnlyHint": True})
async def property_blocks(
    postcode: str,
    search_level: str = "sector",
    months: int = 24,
) -> dict:
    """Property block analysis — identify buildings with multiple flat sales (block-buy opportunities)."""
    import anyio
    from property_core import analyze_blocks
    result = await anyio.to_thread.run_sync(
        lambda: analyze_blocks(
            postcode=postcode,
            search_level=search_level,
            months=months,
        )
    )
    return result.model_dump()


@mcp.tool(annotations={"readOnlyHint": True})
def company_search(name: str) -> dict:
    """Search Companies House for a company by name."""
    from property_core import CompaniesHouseClient
    result = CompaniesHouseClient().search(name)
    return result.model_dump() if result else {"items": []}


@mcp.tool(annotations={"readOnlyHint": True})
async def property_report(
    address: str,
    postcode: str,
    months: int = 24,
) -> dict:
    """Full property data pull — comps + EPC + yield + market in one call.

    Requires both a street address and postcode, e.g. address='10 Downing Street',
    postcode='SW1A 2AA'.
    """
    from property_core.report_service import PropertyReportService
    result = await PropertyReportService().generate_report(
        address_query=f"{address}, {postcode}",
        ppd_months=months,
    )
    return result.model_dump()


@mcp.tool(annotations={"readOnlyHint": True})
def planning_search(postcode: str) -> dict:
    """Find the council planning portal URL for a postcode."""
    from property_core import PlanningService
    return PlanningService().search(postcode)


@mcp.tool(annotations={"readOnlyHint": True})
def ppd_transactions(
    postcode: str,
    limit: int = 10,
    property_type: str | None = None,
) -> dict:
    """Raw Land Registry Price Paid transactions for a postcode."""
    from property_core import PPDService
    result = PPDService().search_transactions(
        postcode=postcode,
        postcode_prefix=None,
        limit=limit,
        property_type=property_type,
    )
    return {
        **{k: v for k, v in result.items() if k != "results"},
        "results": [t.model_dump() for t in result["results"]],
    }


_http_app = create_streamable_http_app(
    mcp,
    streamable_http_path="/mcp",
    json_response=True,
    stateless_http=True,
)


def build_asgi_app():
    """Streamable-HTTP ASGI app for MCPMiddleware in app/main.py."""
    return _http_app
