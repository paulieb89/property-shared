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
    additional_property: bool = True,
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
    ] = True,
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
    """Raw company search — returns dict. Used by the MCP tool and tests."""
    from property_core import CompaniesHouseClient

    client = CompaniesHouseClient()
    if query.strip().isdigit() and len(query.strip()) <= 8:
        result = client.lookup(query.strip())
    else:
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
        Field(description="Company name to search or 8-digit company number to look up"),
    ],
) -> dict:
    """Search Companies House for a UK company by name or number.

    If query is a numeric string (up to 8 digits), performs a direct
    company lookup. Otherwise searches by name.
    """
    return search_company(query)


# ---------------------------------------------------------------------------
# 4. EPC lookup (async)
# ---------------------------------------------------------------------------


async def lookup_epc(postcode: str, address: str | None = None) -> dict:
    """Raw EPC lookup — returns dict. Used by the MCP tool and tests."""
    from property_core import EPCClient

    client = EPCClient()
    result = await client.search_by_postcode(postcode, address=address)
    if result is None:
        return {"error": "No EPC data"}
    return _slim(result.model_dump(mode="json"))


@mcp.tool(
    annotations={"readOnlyHint": True, "openWorldHint": True},
    tags={"epc"},
    timeout=30.0,
)
async def epc_lookup(
    postcode: Annotated[str, Field(description="UK postcode to search for EPC certificates")],
    address: Annotated[
        str | None,
        Field(description="Street address to match within the postcode (optional)"),
    ] = None,
) -> dict:
    """Look up Energy Performance Certificate data for a UK property.

    Searches the EPC register by postcode. If an address is provided,
    attempts to fuzzy-match it against certificates at that postcode.
    Otherwise returns the first certificate found.
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
# Component Test (temporary — maps what claude.ai renderer supports)
# ---------------------------------------------------------------------------


def _component_test_config():
    from fastmcp.apps import PrefabAppConfig, ResourceCSP
    return PrefabAppConfig(csp=ResourceCSP(resource_domains=["https://propertydata.fly.dev"]))


@mcp.tool(
    app=_component_test_config(),
    annotations={"readOnlyHint": True},
    tags={"test"},
)
def component_test():
    """Render a sampler of Prefab components to test claude.ai renderer support."""
    from fastmcp.tools import ToolResult
    from prefab_ui.components import (
        Badge,
        Card,
        CardContent,
        Column,
        Dot,
        ForEach,
        Grid,
        Heading,
        Image,
        Metric,
        Muted,
        Progress,
        Ring,
        Row,
        Separator,
        Tabs,
        Tab,
        Text,
    )
    from prefab_ui.components.charts import BarChart, ChartSeries

    sample_chart_data = [
        {"label": "Q1", "value": 42},
        {"label": "Q2", "value": 58},
        {"label": "Q3", "value": 35},
        {"label": "Q4", "value": 71},
    ]

    view = Column(
        children=[
            Heading("Component Test", level=2),
            Muted("Each section tests a component. If a section is missing, that component crashed the renderer."),
            Separator(),

            # Section 1: Badge
            Heading("1. Badge", level=3),
            Row(children=[
                Badge(label="Flat", variant="default"),
                Badge(label="Strong", variant="success"),
                Badge(label="Weak", variant="destructive"),
                Badge(label="Pending", variant="outline"),
            ], gap=2),
            Separator(),

            # Section 2: Progress + Ring + Dot
            Heading("2. Progress / Ring / Dot", level=3),
            Progress(value=65),
            Row(children=[
                Ring(value=75, size="lg"),
                Dot(variant="success"),
                Dot(variant="destructive"),
                Dot(variant="warning"),
            ], gap=4),
            Separator(),

            # Section 3: BarChart
            Heading("3. BarChart", level=3),
            BarChart(
                data=sample_chart_data,
                series=[ChartSeries(dataKey="value", label="Revenue")],
                xAxis="label",
            ),
            Separator(),

            # Section 4: Tabs
            Heading("4. Tabs", level=3),
            Tabs(children=[
                Tab(title="Overview", children=[
                    Text("This is the overview tab content"),
                ]),
                Tab(title="Details", children=[
                    Text("This is the details tab content"),
                ]),
            ]),
            Separator(),

            # Section 5: ForEach
            Heading("5. ForEach", level=3),
            ForEach(
                key="test_items",
                children=[
                    Row(children=[
                        Text("{{ $item.name }}"),
                        Badge(label="{{ $item.price }}"),
                    ], gap=2),
                ],
            ),
            Separator(),

            # Section 6: Metric with formatted values
            Heading("6. Metric Grid", level=3),
            Grid(columns=3, children=[
                Metric(label="Count", value="50"),
                Metric(label="Median", value="£150,000"),
                Metric(label="Yield", value="6.9%"),
            ]),
            Separator(),

            # Section 7: Card layout
            Heading("7. Cards", level=3),
            Grid(columns=2, children=[
                Card(children=[CardContent(children=[
                    Heading("Sales", level=4),
                    Metric(label="Median", value="£150,000"),
                    Metric(label="Count", value="50"),
                ])]),
                Card(children=[CardContent(children=[
                    Heading("Rentals", level=4),
                    Metric(label="Median/mo", value="£866"),
                    Metric(label="Count", value="25"),
                ])]),
            ]),
            Separator(),

            # Section 8: Image (data URI — no CSP needed)
            Heading("8. Image (data URI)", level=3),
            Image(
                src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAGQAAABkCAYAAABw4pVUAAAACXBIWXMAAAsTAAALEwEAmpwYAAABIklEQVR4nO3SQQ0AIAwAQfj3jAdWuECSzbkB+tme2Z0f2fkdwH8MiRkSMyRmSMyQmCExQ2KGxAyJGRIzJGZIzJCYITFDYobEDIkZEjMkZkjMkJghMUNihsQMiRkSMyRmSMyQmCExQ2KGxAyJGRIzJGZIzJCYITFDYobEDIkZEjMkZkjMkJghMUNihsQMiRkSMyRmSMyQmCExQ2KGxAyJGRIzJGZIzJCYITFDYobEDIkZEjMkZkjMkJghMUNihsQMiRkSMyRmSMyQmCExQ2KGxAyJGRIzJGZIzJCYITFDYobEDIkZEjMkZkjMkJghMUNihsQMiRkSMyRmSMyQmCExQ2KGxAyJGRIzJGZIzJCYITFDYobEDIn9AC9RBGTuOhELAAAAAElFTkSuQmCC",
                alt="100x100 test square",
                height=100,
            ),

            Separator(),

            # Section 9: Image (proxied external URL)
            Heading("9. Image (proxied URL)", level=3),
            Image(
                src="https://propertydata.fly.dev/img?url=https%3A%2F%2Fmedia.rightmove.co.uk%3A443%2Fdir%2Fcrop%2F10%3A9-16%3A9%2Fproperty-photo%2Fb17d74096%2F174125315%2Fb17d74096dbcccb8c49b510d19b48625_max_476x317.jpeg",
                alt="Proxied Rightmove image",
                height=200,
            ),
        ],
        gap=4,
    )

    from prefab_ui.app import PrefabApp

    app_view = PrefabApp(
        state={
            "test_items": [
                {"name": "Item A", "price": 100},
                {"name": "Item B", "price": 200},
                {"name": "Item C", "price": 300},
            ],
        },
        view=view,
    )

    return ToolResult(
        content="Component test: Badge, Progress, Ring, Dot, BarChart, Tabs, ForEach, Metric, Card",
        structured_content=app_view,
    )
