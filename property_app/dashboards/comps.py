"""Comps dashboard — pre-populated comparable sales view.

search_comps: @app.tool(model=True) — returns raw dict, callable by LLM and UI
comps_dashboard: @mcp.tool(app=True) — fetches data server-side, returns rich Prefab view
"""
from __future__ import annotations

from typing import Annotated

from pydantic import Field

from property_app.server import app, mcp


# ---------------------------------------------------------------------------
# Raw helper (testable without MCP decorator overhead)
# ---------------------------------------------------------------------------


def _search_comps(
    postcode: str,
    months: int = 24,
    limit: int = 30,
    search_level: str = "sector",
    address: str | None = None,
    property_type: str | None = None,
) -> dict:
    """Call PPDService.comps() and return a plain dict."""
    from property_core import PPDService

    svc = PPDService()
    result = svc.comps(
        postcode=postcode,
        months=months,
        limit=limit,
        search_level=search_level,
        address=address,
        property_type=property_type,
    )
    from property_app.tools import _slim

    return _slim(result.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# Data tool (LLM + UI callable) — returns raw dict
# ---------------------------------------------------------------------------


@app.tool(
    model=True,
    description="Search comparable property sales for a UK postcode",
    timeout=60.0,
)
def search_comps(
    postcode: Annotated[str, Field(description="UK postcode e.g. SW1A 1AA")],
    months: Annotated[int, Field(description="Lookback period in months", ge=1, le=60)] = 24,
    limit: Annotated[int, Field(description="Max results", ge=1, le=200)] = 30,
    search_level: Annotated[
        str, Field(description="postcode, sector, or district")
    ] = "sector",
    address: Annotated[
        str | None, Field(description="Street address for subject property")
    ] = None,
    property_type: Annotated[
        str | None, Field(description="F=flat, D=detached, S=semi, T=terrace")
    ] = None,
) -> dict:
    """Search comparable property sales for a UK postcode.

    Returns transaction count, median/percentile stats, and individual
    transactions within the lookback period.
    """
    return _search_comps(
        postcode=postcode,
        months=months,
        limit=limit,
        search_level=search_level,
        address=address,
        property_type=property_type,
    )


# ---------------------------------------------------------------------------
# Helpers for the Prefab view
# ---------------------------------------------------------------------------

_TYPE_LABELS = {"F": "Flat", "D": "Detached", "S": "Semi", "T": "Terraced", "O": "Other"}
_TYPE_VARIANTS = {"F": "default", "D": "success", "S": "info", "T": "warning", "O": "secondary"}


def _fmt_gbp(n: int | float | None) -> str:
    if n is None:
        return "—"
    return f"\u00a3{int(n):,}"


def _fmt_date(d: str | None) -> str:
    if not d:
        return "—"
    parts = d.split("T")[0].split("-")
    if len(parts) == 3:
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    return d


def _build_price_buckets(transactions: list[dict]) -> list[dict]:
    """Group transactions into price buckets for a bar chart."""
    buckets = [
        (0, 50_000, "<50k"),
        (50_000, 100_000, "50-100k"),
        (100_000, 150_000, "100-150k"),
        (150_000, 200_000, "150-200k"),
        (200_000, 250_000, "200-250k"),
        (250_000, 300_000, "250-300k"),
        (300_000, 400_000, "300-400k"),
        (400_000, 500_000, "400-500k"),
        (500_000, float("inf"), "500k+"),
    ]
    counts = {label: 0 for _, _, label in buckets}
    for t in transactions:
        price = t.get("price") or 0
        for lo, hi, label in buckets:
            if lo <= price < hi:
                counts[label] += 1
                break
    return [{"range": label, "count": count} for label, count in counts.items() if count > 0]


def _build_address(t: dict) -> str:
    """Build a readable address from transaction fields."""
    parts = []
    if t.get("saon"):
        parts.append(t["saon"])
    if t.get("paon"):
        parts.append(t["paon"])
    if t.get("street"):
        parts.append(t["street"])
    return ", ".join(parts) or "—"


# ---------------------------------------------------------------------------
# Pre-populated Prefab dashboard
# ---------------------------------------------------------------------------


@mcp.tool(
    app=True,
    annotations={"readOnlyHint": True, "openWorldHint": True},
    tags={"comps", "dashboard"},
    timeout=120.0,
)
def comps_dashboard(
    postcode: Annotated[str, Field(description="UK postcode e.g. NG1 1AA")],
    months: Annotated[int, Field(description="Lookback period in months", ge=1, le=60)] = 24,
    search_level: Annotated[str, Field(description="postcode, sector, or district")] = "sector",
    property_type: Annotated[str | None, Field(description="F=flat, D=detached, S=semi, T=terrace")] = None,
):
    """Show comparable property sales as an interactive dashboard.

    Fetches Land Registry transactions and displays stats, price
    distribution chart, and transaction list with property type badges.
    """
    from fastmcp.tools import ToolResult
    from prefab_ui.components import (
        Alert,
        Badge,
        Column,
        Grid,
        Heading,
        Metric,
        Muted,
        Separator,
        Tab,
        Table,
        TableBody,
        TableCell,
        TableHead,
        TableHeader,
        TableRow,
        Tabs,
    )
    from prefab_ui.components.charts import BarChart, ChartSeries, Sparkline

    data = _search_comps(
        postcode=postcode,
        months=months,
        search_level=search_level,
        property_type=property_type,
    )

    count = data.get("count", 0)
    median = data.get("median")
    mean = data.get("mean")
    p25 = data.get("percentile_25")
    p75 = data.get("percentile_75")
    txns = data.get("transactions", [])

    # Price distribution chart data
    price_buckets = _build_price_buckets(txns)

    # Price trend sparkline (chronological prices)
    sorted_txns = sorted(
        [t for t in txns if t.get("price")],
        key=lambda t: t.get("date", ""),
    )
    price_trend = [t["price"] for t in sorted_txns]

    # Transaction table rows (latest 20)
    table_rows = []
    for t in txns[:20]:
        addr = _build_address(t)
        ptype = t.get("property_type", "O")
        table_rows.append(
            TableRow(children=[
                TableCell(content=_fmt_date(t.get("date"))),
                TableCell(content=addr),
                TableCell(children=[
                    Badge(
                        label=_TYPE_LABELS.get(ptype, ptype),
                        variant=_TYPE_VARIANTS.get(ptype, "secondary"),
                    ),
                ]),
                TableCell(content=t.get("estate_type", "—")),
                TableCell(content=_fmt_gbp(t.get("price"))),
            ])
        )

    # Escalation alert
    escalation_alert = []
    if data.get("escalated_from") and data.get("escalated_to"):
        escalation_alert = [
            Alert(
                children=[Muted(f"Search widened from {data['escalated_from']} to {data['escalated_to']}")],
                variant="warning",
            ),
        ]

    # Thin market alert
    thin_market_alert = []
    if data.get("thin_market"):
        thin_market_alert = [
            Alert(
                children=[Muted(f"Thin market \u2014 only {count} transactions found")],
                variant="warning",
            ),
        ]

    # --- Overview tab ---
    overview_children = [
        Grid(
            columns=5,
            children=[
                Metric(label="Transactions", value=str(count)),
                Metric(label="Median", value=_fmt_gbp(median)),
                Metric(label="Mean", value=_fmt_gbp(mean)),
                Metric(label="Lower Quartile", value=_fmt_gbp(p25)),
                Metric(label="Upper Quartile", value=_fmt_gbp(p75)),
            ],
        ),
        *thin_market_alert,
        *escalation_alert,
    ]

    # Add sparkline if we have enough data points
    if len(price_trend) >= 3:
        overview_children.append(Separator())
        overview_children.append(Heading("Price Trend", level=3))
        overview_children.append(Sparkline(data=price_trend, height=60, fill=True, curve="smooth"))

    # Add bar chart if we have buckets
    if price_buckets:
        overview_children.append(Separator())
        overview_children.append(Heading("Price Distribution", level=3))
        overview_children.append(
            BarChart(
                data=price_buckets,
                series=[ChartSeries(dataKey="count", label="Sales")],
                xAxis="range",
                height=200,
            )
        )

    # --- Transactions tab ---
    if table_rows:
        transactions_content = Table(children=[
            TableHeader(children=[
                TableRow(children=[
                    TableHead(content="Date"),
                    TableHead(content="Address"),
                    TableHead(content="Type"),
                    TableHead(content="Tenure"),
                    TableHead(content="Price"),
                ]),
            ]),
            TableBody(children=table_rows),
        ])
    else:
        transactions_content = Muted("No transactions found")

    view = Column(
        children=[
            Heading(f"Comparable Sales \u2014 {postcode.upper()}", level=2),
            Muted(f"{search_level} \u00b7 {months} months \u00b7 Land Registry"),
            Separator(),
            Tabs(children=[
                Tab(title="Overview", children=[
                    Column(children=overview_children, gap=4),
                ]),
                Tab(title=f"Transactions ({min(len(txns), 20)})", children=[
                    transactions_content,
                ]),
            ]),
        ],
        gap=4,
    )

    # Text summary for LLM reasoning
    text = (
        f"Comparable sales for {postcode.upper()} ({search_level}, {months}mo): "
        f"{count} transactions, median {_fmt_gbp(median)}, "
        f"mean {_fmt_gbp(mean)}, range {_fmt_gbp(p25)}\u2013{_fmt_gbp(p75)}"
    )

    return ToolResult(content=text, structured_content=view)
