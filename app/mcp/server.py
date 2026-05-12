"""Plain FastMCP server — property tools, no Prefab UI.

Exposes property_core functions as MCP tools. Suitable for any MCP client
regardless of ext-apps / Prefab UI support.
"""
from __future__ import annotations

from importlib.metadata import version as _pkg_version
from typing import Any

import asyncio

import httpx
from fastmcp import FastMCP
from fastmcp.server.http import create_streamable_http_app
from fastmcp.tools import ToolResult
from fastmcp.utilities.types import Image
from mcp.types import TextContent


def _slim(obj: Any) -> Any:
    """Strip bulk fields (raw, images, floorplans, epc_match) recursively.

    Used alongside Pydantic's exclude_none=True to halve token cost on tools
    that return rich data with optional unpopulated fields (PPD transactions,
    block analysis, full property reports).
    """
    if isinstance(obj, dict):
        return {k: _slim(v) for k, v in obj.items()
                if k not in ("raw", "images", "floorplans", "epc_match")}
    if isinstance(obj, list):
        return [_slim(item) for item in obj]
    return obj

mcp = FastMCP(
    "property-data",
    version=_pkg_version("property-shared"),
    instructions=(
        "UK property data tools. For a comprehensive single-property analysis, "
        "invoke the `full_property_analysis` prompt — it instructs you to call "
        "property_comps, property_yield, property_epc and rightmove_search and "
        "synthesise. For postcode-only data fetches use property_comps and "
        "property_yield separately. ppd_transactions for specific property history, "
        "rightmove_search to browse listings by postcode, rightmove_listing for "
        "full detail on one listing, property_epc for energy certificates, "
        "rental_analysis for rental market figures, stamp_duty for SDLT, "
        "property_blocks for block-buy analysis, planning_search for council "
        "planning portals, company_search to find a company by name."
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
    transaction_category: str | None = "A",
    filter_outliers: bool = False,
    search_level: str = "sector",
    address: str | None = None,
    limit: int = 50,
    enrich_epc: bool = False,
) -> dict:
    """Comparable sales from Land Registry Price Paid Data.

    Defaults return the standard residential set:
    - property_type=None means residential (F+D+S+T). Pass "F"/"D"/"S"/"T"/"O"
      for a single type, or "ALL" to disable type filtering (firehose).
    - transaction_category defaults to "A" (standard sales). Pass None to
      include category-B (bulk transfers, non-standard conveyances).
    - filter_outliers=False by default; set True for IQR-trimmed stats AND
      transaction list (1.5*IQR rule, needs >=4 prices).

    limit caps returned transactions (max 200). enrich_epc attaches EPC floor
    area and price-per-sqft to each transaction — slower but richer.
    """
    from property_core import PPDService
    result = PPDService().comps(
        postcode=postcode,
        months=months,
        property_type=property_type,
        transaction_category=transaction_category,
        filter_outliers=filter_outliers,
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
    return _slim(result.model_dump(mode="json", exclude_none=True))


@mcp.tool(annotations={"readOnlyHint": True})
async def property_yield(
    postcode: str,
    months: int = 24,
    search_level: str = "sector",
    property_type: str | None = None,
    auto_escalate: bool = True,
) -> dict:
    """Gross rental yield for a UK postcode.

    Combines Land Registry sale comps (median sale price) with Rightmove rental
    listings (median monthly rent) to produce a gross yield percentage.

    Args:
        postcode: UK postcode (e.g. "NG1 2NS").
        months: PPD sale lookback period (default 24).
        search_level: PPD search granularity — "postcode", "sector" (default),
            or "district".
        property_type: Filter sales by type. None (default) = residential set
            (F+D+S+T). Pass "F"/"D"/"S"/"T"/"O" for one type, "ALL" for firehose.
        auto_escalate: Widen the PPD search area on thin markets — postcode→
            sector→district. Default True. Set False for strict-locality only.

    Returns:
        median_sale_price, median_monthly_rent, gross_yield_pct, sale_count,
        rental_count, thin_market. Yield fields are null when sample is too thin
        or rental data is unavailable.
    """
    from property_core import calculate_yield
    return (await calculate_yield(
        postcode=postcode,
        months=months,
        search_level=search_level,
        property_type=property_type,
        auto_escalate=auto_escalate,
    )).model_dump(mode="json", exclude_none=True)


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


@mcp.resource("councils://list")
def councils_list_resource() -> str:
    """Return the 99-council UK planning portal registry as JSON.

    Static reference data sourced from property_core/planning_councils.json.
    Lets callers read the full registry once instead of calling planning_search
    for individual lookups.
    """
    import json
    from importlib.resources import files

    raw = json.loads(files("property_core").joinpath("planning_councils.json").read_text())
    councils = raw.get("councils", raw)  # support either wrapped or bare list
    return json.dumps(councils, ensure_ascii=False, indent=2)


@mcp.resource("sdlt-bands://current")
def sdlt_bands_resource() -> str:
    """Return the current UK Stamp Duty Land Tax band schedule as JSON.

    Static reference data matching `property_core/stamp_duty.py` exactly. Lets
    an LLM cite the bands directly without calling the stamp_duty calculator.
    """
    import json

    data = {
        "version": "April 2025",
        "effective_from": "2025-04-01",
        "currency": "GBP",
        "main_bands": [
            {"threshold_above": 0, "threshold_up_to": 125000, "rate_pct": 0},
            {"threshold_above": 125000, "threshold_up_to": 250000, "rate_pct": 2},
            {"threshold_above": 250000, "threshold_up_to": 925000, "rate_pct": 5},
            {"threshold_above": 925000, "threshold_up_to": 1500000, "rate_pct": 10},
            {"threshold_above": 1500000, "threshold_up_to": None, "rate_pct": 12},
        ],
        "first_time_buyer_bands": [
            {"threshold_above": 0, "threshold_up_to": 300000, "rate_pct": 0},
            {"threshold_above": 300000, "threshold_up_to": 500000, "rate_pct": 5},
        ],
        "first_time_buyer_max_eligible_price": 500000,
        "additional_property_surcharge_pct": 5,
        "non_resident_surcharge_pct": 2,
        "source": "https://www.gov.uk/stamp-duty-land-tax/residential-property-rates",
        "notes": [
            "Additional-property surcharge rose from 3% to 5% in October 2024.",
            "Non-resident surcharge applies to buyers not resident in the UK in the 12 months before purchase.",
            "First-time buyer relief is only available when buying a single residence at £500k or under.",
        ],
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.resource("council://{code}")
def council_resource(code: str) -> str:
    """Return a single council's record as JSON, keyed by its code/slug.

    Looks up the council in property_core/planning_councils.json. Raises
    ValueError if the code is unknown so callers see a clear error rather
    than a misleading empty result.
    """
    import json
    from importlib.resources import files

    raw = json.loads(files("property_core").joinpath("planning_councils.json").read_text())
    councils = raw.get("councils", raw)
    for c in councils:
        if c.get("code") == code or c.get("slug") == code:
            return json.dumps(c, ensure_ascii=False, indent=2)
    raise ValueError(f"Unknown council code: {code}")


@mcp.prompt()
def full_property_analysis(
    address: str,
    postcode: str,
    months: str = "24",
) -> str:
    """Comprehensive UK property analysis — composes comps, yield, EPC, asking prices, then synthesises.

    This is a workflow prompt, not a single API call. The LLM follows the
    instructions below to call the four primitive tools and synthesise the
    results explicitly, so every input is visible in the conversation.
    """
    return f"""Produce a comprehensive analysis of the property at {address}, {postcode}.

Execute these tool calls in order and show your work — state which tool you are calling, summarise its response, then move to the next.

1. **Sale history + area comparable sales**: call `property_comps(postcode='{postcode}', months={months}, address='{address}', enrich_epc=true)`.
   - The response's `subject_property` section (if present) has this property's sale history.
   - The top-level fields (`median`, `mean`, `min`, `max`, `percentile_25`, `percentile_75`) describe the AREA, not this property.
   - The area median is the best proxy for current value. Use it for yield calculation later — never use a historical `subject_property.last_sale.price`, especially if old.

2. **Area gross rental yield**: call `property_yield(postcode='{postcode}', months={months})`.
   - Returns the AREA's median yield (area median sale price vs area median rent).
   - For a property-specific yield, recompute: `(median_monthly_rent × 12 / area_median_sale_price) × 100`. Use the area median from step 1, NOT this property's last sale price.

3. **Energy certificate**: call `property_epc(postcode='{postcode}', address='{address}')`.
   - With a specific address, returns the matched EPC certificate.
   - Note: rating (A–G), score (0–100), floor area, total annual energy cost, potential improvements.

4. **Current asking prices**: call `rightmove_search(postcode='{postcode}', listing_type='sale')`.
   - Asking prices for sale right now. Typically above sold prices — the gap signals seller optimism vs. transactional reality.

Then synthesise (3–5 short paragraphs):
- This property's sale history (years and prices, if found).
- Where it sits relative to area median (above/below, by what percent — compare price to current area median, not historical).
- EPC rating, what it means in £/year, and improvement potential.
- A realistic gross yield using the current area median value.
- The asking-vs-sold gap and what it signals.

**Critical**: never quote a yield that divides current rent by an old sale price. Always cite which numbers came from which tool call.
"""


_http_app = create_streamable_http_app(
    mcp,
    streamable_http_path="/mcp",
    json_response=True,
    stateless_http=True,
)


def build_asgi_app():
    """Streamable-HTTP ASGI app for MCPMiddleware in app/main.py."""
    return _http_app
