"""Plain MCP tools — standalone lookups registered on the main server.

These are real MCP tools callable by LLMs. Each wraps a property_core
function with lazy imports and returns data directly (no Prefab UI).
The stamp_duty tool is the exception: it uses ``app=True`` to return
a PrefabApp with inline Metric + DataTable components.
"""
from __future__ import annotations

from typing import Any, Annotated

from pydantic import Field

from property_app.server import mcp


def _slim(obj: Any) -> Any:
    """Strip raw/images/floorplans/epc_match for LLM-friendly output."""
    if isinstance(obj, dict):
        return {k: _slim(v) for k, v in obj.items()
                if k not in ("raw", "images", "floorplans", "epc_match")}
    if isinstance(obj, list):
        return [_slim(item) for item in obj]
    return obj


# ---------------------------------------------------------------------------
# 1. Stamp Duty calculator (Prefab UI)
# ---------------------------------------------------------------------------


def calc_stamp_duty(
    price: int,
    additional_property: bool = False,
    first_time_buyer: bool = False,
    non_resident: bool = False,
) -> dict:
    """Raw stamp duty calculation — returns dict. Used by the MCP tool and tests."""
    from property_core import calculate_stamp_duty

    result = calculate_stamp_duty(
        price,
        additional_property=additional_property,
        first_time_buyer=first_time_buyer,
        non_resident=non_resident,
    )
    return result.model_dump(mode="json")


@mcp.tool(
    app=True,
    annotations={"readOnlyHint": True, "idempotentHint": True},
    tags={"calculator"},
)
def stamp_duty(
    price: Annotated[int, Field(description="Purchase price in GBP")],
    additional_property: Annotated[
        bool, Field(description="Buying an additional property (+5% surcharge)")
    ] = False,
    first_time_buyer: Annotated[
        bool, Field(description="First-time buyer relief (up to 300k nil rate)")
    ] = False,
    non_resident: Annotated[
        bool, Field(description="Non-UK resident (+2% surcharge)")
    ] = False,
):
    """Calculate UK Stamp Duty Land Tax for a residential property purchase.

    Returns SDLT total, effective rate, and band-by-band breakdown.
    """
    from prefab_ui.app import PrefabApp
    from prefab_ui.components import (
        Column,
        DataTable,
        DataTableColumn,
        Grid,
        Heading,
        Metric,
        Separator,
    )

    from fastmcp.tools import ToolResult

    from property_app.formatting import fmt_gbp, fmt_pct

    data = calc_stamp_duty(price, additional_property, first_time_buyer, non_resident)

    # Build band rows for the data table
    band_rows = [
        {
            "band": b["band"],
            "rate": f"{b['rate']}%",
            "amount": fmt_gbp(b["amount"]),
            "tax": fmt_gbp(b["tax"]),
        }
        for b in data.get("breakdown", [])
    ]

    view = Column(
        children=[
            Heading("Stamp Duty (SDLT)", level=2),
            Grid(
                columns=3,
                children=[
                    Metric(label="Purchase Price", value=fmt_gbp(price)),
                    Metric(label="Total SDLT", value=fmt_gbp(data["total_sdlt"])),
                    Metric(
                        label="Effective Rate",
                        value=fmt_pct(data["effective_rate"]),
                    ),
                ],
            ),
            Separator(),
            DataTable(
                columns=[
                    DataTableColumn(key="band", header="Band"),
                    DataTableColumn(key="rate", header="Rate", align="right"),
                    DataTableColumn(key="amount", header="Amount", align="right"),
                    DataTableColumn(key="tax", header="Tax", align="right"),
                ],
                rows=band_rows,
            ),
        ],
        gap=4,
    )

    # Text fallback so the model can reason about results (Lesson 24)
    return ToolResult(
        content=(
            f"SDLT for \u00a3{price:,}: \u00a3{data['total_sdlt']:,.0f} "
            f"({fmt_pct(data['effective_rate'])} effective rate)"
        ),
        structured_content=view,
    )


# ---------------------------------------------------------------------------
# 2. Planning search
# ---------------------------------------------------------------------------


def search_planning(postcode: str) -> dict:
    """Raw planning search — returns dict. Used by the MCP tool and tests."""
    from property_core import PlanningService

    result = PlanningService().search(postcode)
    # PlanningService.search() already returns a dict
    return result


@mcp.tool(
    annotations={"readOnlyHint": True},
    tags={"planning"},
)
def planning_search(
    postcode: Annotated[str, Field(description="UK postcode to look up planning portal for")],
) -> dict:
    """Find the planning portal URL for a UK postcode.

    Returns council info and portal search URLs. Does not scrape
    planning applications -- use the returned URLs to search directly.
    """
    return search_planning(postcode)


# ---------------------------------------------------------------------------
# 3. Company search
# ---------------------------------------------------------------------------


def search_company(query: str) -> dict:
    """Raw company name search — returns dict. Used by the MCP tool and tests."""
    from property_core import CompaniesHouseClient

    client = CompaniesHouseClient()
    result = client.search(query)

    if result is None:
        return {"error": "Not found"}
    return _slim(result.model_dump(mode="json"))


@mcp.tool(
    annotations={"readOnlyHint": True, "openWorldHint": True},
    tags={"companies"},
)
def company_search(
    query: Annotated[
        str,
        Field(description="Company name to search (e.g. 'Tesco'). For direct lookup by number, use the company://{company_number} resource."),
    ],
) -> dict:
    """Search Companies House by company name. Returns a list of matches.

    For a direct lookup by company number, use the company://{company_number}
    resource instead (e.g. read_resource("company://00445790")).
    """
    return search_company(query)


# ---------------------------------------------------------------------------
# 4. EPC lookup (async)
# ---------------------------------------------------------------------------


async def lookup_epc(postcode: str, address: str | None = None) -> dict:
    """Raw EPC lookup — returns dict. Used by the MCP tool and tests.

    With address: returns the matched certificate.
    Without address: returns all certificates at the postcode with area summary.
    """
    from collections import Counter

    from property_core import EPCClient

    client = EPCClient()

    if address:
        result = await client.search_by_postcode(postcode, address=address)
        if result is None:
            return {"error": "No EPC data"}
        return _slim(result.model_dump(mode="json"))

    # Area mode
    certs = await client.search_all_by_postcode(postcode)
    if not certs:
        return {"error": "No EPC data"}

    ratings = Counter(c.rating for c in certs if c.rating)
    types = Counter(c.property_type for c in certs if c.property_type)
    areas = [c.floor_area for c in certs if c.floor_area]

    summary = {
        "count": len(certs),
        "rating_distribution": dict(sorted(ratings.items())),
        "property_type_breakdown": dict(sorted(types.items())),
        "floor_area_min": min(areas) if areas else None,
        "floor_area_max": max(areas) if areas else None,
        "floor_area_avg": round(sum(areas) / len(areas), 1) if areas else None,
    }
    # Return only the summary — skip the full 25-cert list to save tokens in
    # the LLM context (data tools return dicts that the MCP framework puts in
    # content[]; a 25-cert payload is ~20KB). For individual property detail,
    # callers should re-call with a specific address.
    return _slim({
        "postcode": postcode,
        "summary": summary,
        "note": "Call lookup_epc again with a specific address for individual property details.",
    })


@mcp.tool(
    annotations={"readOnlyHint": True, "openWorldHint": True},
    tags={"epc"},
    timeout=30.0,
)
async def epc_lookup(
    postcode: Annotated[str, Field(description="UK postcode to search for EPC certificates")],
    address: Annotated[
        str | None,
        Field(description="Street address to match (omit for area view)"),
    ] = None,
) -> dict:
    """Energy Performance Certificate data for a UK property or postcode area.

    With address: returns the matched certificate for that specific property.
    Without address: returns all certificates at the postcode with area
    aggregation — rating distribution, floor area range, property type
    breakdown. Use the area mode for postcode-level views rather than
    a single-property lookup.
    """
    return await lookup_epc(postcode, address=address)


# ---------------------------------------------------------------------------
# 5. Rightmove search
# ---------------------------------------------------------------------------


def search_rightmove(
    postcode: str,
    property_type: str = "sale",
    min_bedrooms: int | None = None,
    max_price: int | None = None,
    radius: float | None = None,
    building_type: str | None = None,
) -> dict:
    """Raw Rightmove search — returns dict. Used by the MCP tool and tests."""
    from statistics import median as stat_median

    from property_core import RightmoveLocationAPI, fetch_listings

    loc_api = RightmoveLocationAPI()
    search_url = loc_api.build_search_url(
        postcode,
        property_type=property_type,
        min_bedrooms=min_bedrooms,
        max_price=max_price,
        radius=radius,
        building_type=building_type,
    )

    listings = fetch_listings(search_url, max_pages=1)
    prices = [l.price for l in listings if l.price and l.price > 0]
    median_price = int(stat_median(prices)) if prices else None

    return {
        "search_url": search_url,
        "count": len(listings),
        "listings": [_slim(l.model_dump(mode="json")) for l in listings],
        "median_price": median_price,
    }


@mcp.tool(
    annotations={"readOnlyHint": True, "openWorldHint": True},
    tags={"rightmove", "listings"},
    timeout=60.0,
)
def rightmove_search(
    postcode: Annotated[str, Field(description="UK postcode to search around")],
    property_type: Annotated[
        str, Field(description="'sale' or 'rent'")
    ] = "sale",
    min_bedrooms: Annotated[
        int | None, Field(description="Minimum number of bedrooms")
    ] = None,
    max_price: Annotated[
        int | None, Field(description="Maximum price filter")
    ] = None,
    radius: Annotated[
        float | None, Field(description="Search radius in miles")
    ] = None,
    building_type: Annotated[
        str | None,
        Field(description="Building type filter: F=flat, D=detached, S=semi, T=terraced"),
    ] = None,
) -> dict:
    """Search Rightmove property listings by postcode.

    Builds a search URL, fetches the first page of results, and returns
    listing summaries with a median price.
    """
    return search_rightmove(
        postcode,
        property_type=property_type,
        min_bedrooms=min_bedrooms,
        max_price=max_price,
        radius=radius,
        building_type=building_type,
    )



# ---------------------------------------------------------------------------
# 6. Property blocks — find buildings with multiple flat sales
# ---------------------------------------------------------------------------


def analyse_blocks(
    postcode: str,
    search_level: str = "sector",
    months: int = 24,
    limit: int = 50,
    min_transactions: int = 2,
) -> dict:
    """Raw block analysis — returns dict. Used by the MCP tool and tests."""
    from property_core import analyze_blocks

    result = analyze_blocks(
        postcode=postcode,
        search_level=search_level,
        months=months,
        limit=limit,
        min_transactions=min_transactions,
    )
    return _slim(result.model_dump(mode="json", exclude_none=True))


@mcp.tool(
    annotations={"readOnlyHint": True},
    tags={"ppd", "blocks"},
    timeout=60.0,
)
def property_blocks(
    postcode: Annotated[str, Field(description="UK postcode (e.g. 'B1 1AA')")],
    search_level: Annotated[
        str, Field(description="postcode, sector, or district")
    ] = "sector",
    months: Annotated[int, Field(description="Sale lookback months", ge=1, le=120)] = 24,
    limit: Annotated[int, Field(description="Target number of blocks to return", ge=1, le=200)] = 50,
    min_transactions: Annotated[
        int, Field(description="Minimum sales per building to qualify as a block", ge=2)
    ] = 2,
) -> dict:
    """Identify buildings with multiple flat sales — block-buy opportunities.

    Groups Land Registry transactions by building (PAON/street) and returns
    blocks where at least min_transactions units sold in the lookback window.
    Useful for spotting investor exits, new-build releases, or portfolio
    bulk transfers.
    """
    return analyse_blocks(
        postcode=postcode,
        search_level=search_level,
        months=months,
        limit=limit,
        min_transactions=min_transactions,
    )


# ---------------------------------------------------------------------------
# 7. PPD transactions — raw Land Registry transactions for a postcode
# ---------------------------------------------------------------------------


def search_ppd_transactions(
    postcode: str,
    limit: int = 10,
    property_type: str | None = None,
) -> dict:
    """Raw PPD transaction search — returns dict. Used by the MCP tool and tests."""
    from property_core import PPDService

    result = PPDService().search_transactions(
        postcode=postcode,
        postcode_prefix=None,
        limit=limit,
        property_type=property_type,
    )
    return {
        **{k: v for k, v in result.items() if k != "results"},
        "results": [_slim(t.model_dump(mode="json", exclude_none=True)) for t in result["results"]],
    }


@mcp.tool(
    annotations={"readOnlyHint": True},
    tags={"ppd"},
)
def ppd_transactions(
    postcode: Annotated[str, Field(description="UK postcode")],
    limit: Annotated[int, Field(description="Max transactions to return", ge=1, le=200)] = 10,
    property_type: Annotated[
        str | None,
        Field(description="Filter by type: F=flat, D=detached, S=semi, T=terraced, O=other. Default None = all"),
    ] = None,
) -> dict:
    """Raw Land Registry Price Paid transactions for a postcode.

    Returns every recorded transaction at the postcode, unfiltered (includes
    category-B bulk transfers and commercial sales). For clean residential
    comparable sales, use property_comps instead.
    """
    return search_ppd_transactions(
        postcode=postcode,
        limit=limit,
        property_type=property_type,
    )
