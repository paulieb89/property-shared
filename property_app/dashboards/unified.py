"""Unified property dashboard — single-call view combining comps + yield + rental.

get_property_data: @mcp.tool() — returns combined dict for LLM consumption
property_dashboard: @mcp.tool(app=True) — returns PrefabApp with interactive view
"""
from __future__ import annotations

import asyncio
from typing import Annotated

from pydantic import Field

from property_app.server import mcp


# ---------------------------------------------------------------------------
# Parallel data helper
# ---------------------------------------------------------------------------


async def _fetch_unified(
    postcode: str,
    months: int = 24,
    search_level: str = "sector",
    property_type: str | None = None,
    radius: float = 0.5,
) -> dict:
    """Fetch comps, yield, and rental data in parallel."""
    from property_core import PPDService, calculate_yield
    from property_core.interpret import classify_data_quality, classify_yield
    from property_core.rental_service import analyze_rentals

    from property_app.tools import _slim

    comps_result, yield_result, rental_result = await asyncio.gather(
        asyncio.to_thread(
            PPDService().comps,
            postcode=postcode,
            months=months,
            search_level=search_level,
            property_type=property_type,
        ),
        calculate_yield(
            postcode=postcode,
            months=months,
            search_level=search_level,
            property_type=property_type,
            radius=radius,
        ),
        analyze_rentals(
            postcode=postcode,
            radius=radius,
        ),
    )

    comps = _slim(comps_result.model_dump(mode="json"))
    yield_data = yield_result.model_dump(mode="json")
    rental = rental_result.model_dump(mode="json")

    # Add interpretation labels
    if yield_result.gross_yield_pct is not None:
        yield_data["yield_assessment"] = classify_yield(yield_result.gross_yield_pct)
    else:
        yield_data["yield_assessment"] = None
    yield_data["data_quality"] = classify_data_quality(
        yield_result.sale_count, yield_result.rental_count
    )

    return {"comps": comps, "yield_data": yield_data, "rental": rental}


# ---------------------------------------------------------------------------
# Data tool
# ---------------------------------------------------------------------------


@mcp.tool(
    annotations={"readOnlyHint": True, "openWorldHint": True},
    tags={"property", "unified"},
    timeout=120.0,
)
async def get_property_data(
    postcode: Annotated[str, Field(description="UK postcode e.g. NG1 1AA")],
    months: Annotated[int, Field(description="Sale lookback months", ge=1, le=60)] = 24,
    search_level: Annotated[str, Field(description="postcode, sector, or district")] = "sector",
    property_type: Annotated[str | None, Field(description="F=flat, D=detached, S=semi, T=terrace")] = None,
    radius: Annotated[float, Field(description="Rental search radius in miles", ge=0.1, le=5.0)] = 0.5,
) -> dict:
    """Combined property data: comparable sales, rental yield, and rental market.

    Returns transaction count, price stats, gross yield percentage,
    yield assessment, rental listings, and data quality classification.
    """
    return await _fetch_unified(
        postcode=postcode,
        months=months,
        search_level=search_level,
        property_type=property_type,
        radius=radius,
    )


# ---------------------------------------------------------------------------
# Dashboard helpers (reuse from existing modules)
# ---------------------------------------------------------------------------

_ASSESSMENT_SENTIMENT = {"strong": "positive", "average": "neutral", "weak": "negative"}
_ASSESSMENT_TREND = {"strong": "up", "average": "neutral", "weak": "down"}
_ASSESSMENT_VARIANTS = {"strong": "success", "average": "warning", "weak": "destructive"}
_QUALITY_VARIANTS = {"good": "success", "low": "warning", "insufficient": "destructive"}


# ---------------------------------------------------------------------------
# Dashboard tool
# ---------------------------------------------------------------------------


@mcp.tool(
    app=True,
    annotations={"readOnlyHint": True, "openWorldHint": True},
    tags={"property", "dashboard", "unified"},
    timeout=180.0,
)
async def property_dashboard(
    postcode: Annotated[str, Field(description="UK postcode e.g. NG1 1AA")],
    months: Annotated[int, Field(description="Sale lookback months", ge=1, le=60)] = 24,
    search_level: Annotated[str, Field(description="postcode, sector, or district")] = "sector",
    property_type: Annotated[str | None, Field(description="F=flat, D=detached, S=semi, T=terrace")] = None,
    radius: Annotated[float, Field(description="Rental search radius in miles", ge=0.1, le=5.0)] = 0.5,
):
    """Show a unified property dashboard combining sales, yield, and rental data.

    Fetches Land Registry transactions, Rightmove rental listings, and
    calculates gross yield — all in one view with interactive controls.
    """
    from fastmcp.tools import ToolResult
    from prefab_ui.app import PrefabApp
    from prefab_ui.components import (
        Alert,
        Badge,
        Card,
        CardContent,
        CardHeader,
        CardTitle,
        Column,
        DataTable,
        Dot,
        Grid,
        Heading,
        Metric,
        Muted,
        Ring,
        Row,
        Separator,
        Switch,
        Tab,
        Tabs,
        Text,
        Tooltip,
    )
    from prefab_ui.components.charts import BarChart, ChartSeries, Sparkline
    from prefab_ui.components.control_flow import Else, If
    from prefab_ui.components.data_table import DataTableColumn
    from prefab_ui.rx import Rx

    from property_app.dashboards.comps import _build_address, _build_price_buckets, _TYPE_LABELS
    from property_app.formatting import fmt_date, fmt_gbp, fmt_pct

    data = await _fetch_unified(
        postcode=postcode,
        months=months,
        search_level=search_level,
        property_type=property_type,
        radius=radius,
    )

    comps = data["comps"]
    yield_data = data["yield_data"]
    rental = data["rental"]

    # -- Extract values --
    count = comps.get("count", 0)
    median = comps.get("median")
    mean = comps.get("mean")
    p25 = comps.get("percentile_25")
    p75 = comps.get("percentile_75")
    txns = comps.get("transactions", [])
    thin_comps = comps.get("thin_market", False)

    gross_yield = yield_data.get("gross_yield_pct")
    assessment = yield_data.get("yield_assessment") or "—"
    quality = yield_data.get("data_quality") or "—"
    sale_count = yield_data.get("sale_count", 0)

    rental_count = rental.get("rental_listings_count", 0)
    median_rent = rental.get("median_rent_monthly")
    avg_rent = rental.get("average_rent_monthly")
    min_rent = rental.get("min_rent")
    max_rent = rental.get("max_rent")
    thin_rental = rental.get("thin_market", False)

    # -- Computed values --
    median_delta = None
    median_trend = None
    if median is not None and mean is not None and mean != 0:
        delta_pct = (median - mean) / mean * 100
        sign = "+" if delta_pct >= 0 else ""
        median_delta = f"{sign}{delta_pct:.1f}% vs avg"
        median_trend = "up" if delta_pct >= 0 else "down"

    price_buckets = _build_price_buckets(txns)
    sorted_txns = sorted(
        [t for t in txns if t.get("price")],
        key=lambda t: t.get("date", ""),
    )
    price_trend = [t["price"] for t in sorted_txns]

    # -- DataTable rows --
    dt_columns = [
        DataTableColumn(key="date", header="Date", sortable=True),
        DataTableColumn(key="address", header="Address", sortable=True),
        DataTableColumn(key="type", header="Type", sortable=True),
        DataTableColumn(key="tenure", header="Tenure", sortable=True),
        DataTableColumn(key="price", header="Price", sortable=True, align="right"),
    ]
    dt_rows = [
        {
            "date": fmt_date(t.get("date")),
            "address": _build_address(t),
            "type": _TYPE_LABELS.get(t.get("property_type", "O"), t.get("property_type", "O")),
            "tenure": t.get("estate_type", "—"),
            "price": fmt_gbp(t.get("price")),
        }
        for t in txns
    ]

    # -- Build view with context managers --
    show_rent_details = Rx("show_rent_details")

    with PrefabApp(
        title=f"Property Dashboard — {postcode.upper()}",
        state={"show_rent_details": True},
        css_class="p-2",
    ) as app:
        Heading(f"Property Dashboard — {postcode.upper()}", level=2)
        Muted(f"{search_level} · {months}mo · {radius}mi radius · Land Registry + Rightmove")
        Separator()

        with Tabs():
            # ── Tab 1: Overview ────────────────────────────────
            with Tab(title="Overview"):
                with Column(gap=4):
                    # Key metrics row
                    with Grid(columns=4, gap=4):
                        with Card():
                            with CardHeader():
                                CardTitle("Median Price")
                            with CardContent():
                                Metric(
                                    label="Median",
                                    value=fmt_gbp(median),
                                    delta=median_delta,
                                    trend=median_trend,
                                )

                        with Card():
                            with CardHeader():
                                CardTitle("Gross Yield")
                            with CardContent():
                                with Tooltip(
                                    content="Annual rent ÷ median sale price × 100",
                                    delay=0,
                                ):
                                    Metric(
                                        label="Yield",
                                        value=fmt_pct(gross_yield),
                                        trend=_ASSESSMENT_TREND.get(assessment, "neutral"),
                                        trend_sentiment=_ASSESSMENT_SENTIMENT.get(assessment, "neutral"),
                                    )

                        with Card():
                            with CardHeader():
                                CardTitle("Median Rent")
                            with CardContent():
                                Metric(label="Per Month", value=fmt_gbp(median_rent))

                        with Card():
                            with CardHeader():
                                CardTitle("Data Points")
                            with CardContent():
                                Metric(label="Sales", value=str(count))
                                Metric(label="Rentals", value=str(rental_count))

                    # Alerts
                    if thin_comps:
                        with Alert(variant="warning"):
                            Muted(f"Thin sales market — only {count} transactions found")
                    if thin_rental:
                        with Alert(variant="warning"):
                            Muted(f"Thin rental market — only {rental_count} listings found")
                    if comps.get("escalated_from"):
                        with Alert(variant="info"):
                            Muted(f"Sales search widened from {comps['escalated_from']} to {comps['escalated_to']}")
                    if rental.get("escalated_from"):
                        with Alert(variant="info"):
                            Muted(f"Rental radius widened from {rental['escalated_from']}mi to {rental['escalated_to']}mi")

                    # Price trend sparkline
                    if len(price_trend) >= 3:
                        with Card(css_class="pb-0 gap-0"):
                            with CardContent():
                                Metric(label="Price Trend", value=f"{len(price_trend)} sales")
                            Sparkline(
                                data=price_trend,
                                height=60,
                                fill=True,
                                curve="smooth",
                                variant="info",
                                css_class="h-16",
                            )

                    # Price distribution
                    if price_buckets:
                        with Card():
                            with CardHeader():
                                CardTitle("Price Distribution")
                            with CardContent():
                                BarChart(
                                    data=price_buckets,
                                    series=[ChartSeries(dataKey="count", label="Sales")],
                                    xAxis="range",
                                    height=200,
                                    barRadius=4,
                                    showTooltip=True,
                                )

            # ── Tab 2: Transactions ────────────────────────────
            with Tab(title=f"Transactions ({len(txns)})"):
                if dt_rows:
                    DataTable(
                        columns=dt_columns,
                        rows=dt_rows,
                        search=True,
                        paginated=True,
                        page_size=10,
                    )
                else:
                    Muted("No transactions found")

            # ── Tab 3: Yield & Rental ──────────────────────────
            with Tab(title="Yield & Rental"):
                with Column(gap=4):
                    # Yield ring + badges
                    if gross_yield is not None:
                        with Card():
                            with CardHeader():
                                CardTitle("Gross Rental Yield")
                            with CardContent():
                                with Row(gap=6, align="center", css_class="justify-center"):
                                    Ring(
                                        value=min(gross_yield, 15),
                                        max=15,
                                        label=fmt_pct(gross_yield),
                                        variant=_ASSESSMENT_VARIANTS.get(assessment, "default"),
                                        size="lg",
                                        thickness=10,
                                    )
                                    with Column(gap=2):
                                        Badge(
                                            label=assessment.title(),
                                            variant=_ASSESSMENT_VARIANTS.get(assessment, "secondary"),
                                        )
                                        Badge(
                                            label=f"Data: {quality}",
                                            variant=_QUALITY_VARIANTS.get(quality, "secondary"),
                                        )

                    # Sales vs Rental breakdown
                    with Grid(columns=2, gap=4):
                        with Card():
                            with CardHeader():
                                CardTitle("Sales")
                            with CardContent():
                                Metric(label="Median Price", value=fmt_gbp(median))
                                Metric(label="Transactions", value=str(sale_count))
                                Metric(label="Price Range", value=f"{fmt_gbp(p25)} – {fmt_gbp(p75)}")

                        with Card():
                            with CardHeader():
                                with Row(gap=2, align="center"):
                                    CardTitle("Rentals")
                                    Dot(variant="destructive" if thin_rental else "success")
                            with CardContent():
                                Metric(label="Median Rent/mo", value=fmt_gbp(median_rent))
                                Metric(label="Listings", value=str(rental_count))

                    # Toggleable rent range details
                    with Row(gap=2, align="center"):
                        Switch(name="show_rent_details", value=True, label="Show rent range")

                    with If(show_rent_details):
                        with Card():
                            with CardHeader():
                                CardTitle("Rent Range")
                            with CardContent():
                                with Grid(columns=3, gap=4):
                                    Metric(label="Lowest", value=fmt_gbp(min_rent))
                                    Metric(label="Average", value=fmt_gbp(avg_rent))
                                    Metric(label="Highest", value=fmt_gbp(max_rent))

    # Text summary for LLM reasoning
    text_parts = [
        f"Property dashboard for {postcode.upper()} ({search_level}, {months}mo, {radius}mi):",
        f"  Sales: {count} transactions, median {fmt_gbp(median)}, range {fmt_gbp(p25)}–{fmt_gbp(p75)}",
        f"  Rentals: {rental_count} listings, median {fmt_gbp(median_rent)}/mo",
    ]
    if gross_yield is not None:
        text_parts.append(f"  Yield: {fmt_pct(gross_yield)} gross ({assessment}), data quality: {quality}")

    return ToolResult(content="\n".join(text_parts), structured_content=app)
