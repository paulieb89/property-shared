"""Yield analysis dashboard — pre-populated yield view.

get_yield: @mcp.tool() — returns raw dict for LLM consumption
yield_dashboard: @mcp.tool(app=True) — fetches data server-side, returns rich Prefab view
"""
from __future__ import annotations

from typing import Annotated

from pydantic import Field

from property_app.server import mcp


# ---------------------------------------------------------------------------
# Raw async helper (testable without MCP decorator overhead)
# ---------------------------------------------------------------------------


async def _fetch_yield(
    postcode: str,
    months: int = 24,
    search_level: str = "sector",
    property_type: str | None = None,
    radius: float = 0.5,
) -> dict:
    """Call calculate_yield and return a plain dict with assessment labels."""
    from property_core import calculate_yield
    from property_core.interpret import classify_data_quality, classify_yield

    result = await calculate_yield(
        postcode=postcode,
        months=months,
        search_level=search_level,
        property_type=property_type,
        radius=radius,
    )
    data = result.model_dump(mode="json")
    data["yield_assessment"] = classify_yield(result.gross_yield_pct) if result.gross_yield_pct is not None else None
    data["data_quality"] = classify_data_quality(result.sale_count, result.rental_count)
    return data


# ---------------------------------------------------------------------------
# Data tool (LLM + UI callable) — returns raw dict
# ---------------------------------------------------------------------------


@mcp.tool(
    annotations={"readOnlyHint": True, "openWorldHint": True},
    tags={"yield"},
    timeout=60.0,
)
async def get_yield(
    postcode: Annotated[str, Field(description="UK postcode e.g. NG1 1AA")],
    months: Annotated[int, Field(description="Sale lookback months", ge=1, le=60)] = 24,
    search_level: Annotated[str, Field(description="postcode, sector, or district")] = "sector",
    property_type: Annotated[str | None, Field(description="F=flat, D=detached, S=semi, T=terrace")] = None,
    radius: Annotated[float, Field(description="Rental search radius in miles", ge=0.1, le=5.0)] = 0.5,
) -> dict:
    """Analyse gross rental yield for a UK postcode.

    Returns median sale price, median monthly rent, gross yield percentage,
    yield assessment label, and data quality classification.
    """
    return await _fetch_yield(
        postcode=postcode,
        months=months,
        search_level=search_level,
        property_type=property_type,
        radius=radius,
    )


# ---------------------------------------------------------------------------
# Helpers for the Prefab view
# ---------------------------------------------------------------------------

_ASSESSMENT_VARIANTS = {"strong": "success", "average": "warning", "weak": "destructive"}
_QUALITY_VARIANTS = {"good": "success", "low": "warning", "insufficient": "destructive"}


def _fmt_gbp(n: int | float | None) -> str:
    if n is None:
        return "—"
    return f"\u00a3{int(n):,}"


def _fmt_pct(n: float | None) -> str:
    if n is None:
        return "—"
    return f"{n:.1f}%"


# ---------------------------------------------------------------------------
# Pre-populated Prefab dashboard
# ---------------------------------------------------------------------------


@mcp.tool(
    app=True,
    annotations={"readOnlyHint": True, "openWorldHint": True},
    tags={"yield", "dashboard"},
    timeout=120.0,
)
async def yield_dashboard(
    postcode: Annotated[str, Field(description="UK postcode e.g. NG1 1AA")],
    months: Annotated[int, Field(description="Sale lookback months", ge=1, le=60)] = 24,
    search_level: Annotated[str, Field(description="postcode, sector, or district")] = "sector",
    radius: Annotated[float, Field(description="Rental search radius in miles")] = 0.5,
):
    """Show rental yield analysis as an interactive dashboard.

    Combines Land Registry sale prices with Rightmove rental listings
    to calculate gross yield, with assessment and data quality indicators.
    """
    from fastmcp.tools import ToolResult
    from prefab_ui.components import (
        Badge,
        Card,
        CardContent,
        Column,
        Grid,
        Heading,
        Metric,
        Muted,
        Row,
        Separator,
    )

    data = await _fetch_yield(
        postcode=postcode,
        months=months,
        search_level=search_level,
        radius=radius,
    )

    gross_yield = data.get("gross_yield_pct")
    assessment = data.get("yield_assessment") or "—"
    quality = data.get("data_quality") or "—"
    median_price = data.get("median_sale_price")
    median_rent = data.get("median_rent_monthly")
    sale_count = data.get("sale_count", 0)
    rental_count = data.get("rental_count", 0)

    view = Column(
        children=[
            # Header
            Heading(f"Yield Analysis \u2014 {postcode.upper()}", level=2),
            Muted(f"{search_level} \u00b7 {months} months \u00b7 {radius}mi radius"),

            Separator(),

            # Key yield metric with assessment badges
            Row(
                children=[
                    Metric(label="Gross Yield", value=_fmt_pct(gross_yield)),
                    Badge(
                        label=assessment.title(),
                        variant=_ASSESSMENT_VARIANTS.get(assessment, "secondary"),
                    ),
                    Badge(
                        label=f"Data: {quality}",
                        variant=_QUALITY_VARIANTS.get(quality, "secondary"),
                    ),
                ],
                gap=4,
                css_class="items-center",
            ),

            Separator(),

            # Sale vs Rental breakdown
            Grid(
                columns=2,
                children=[
                    Card(children=[CardContent(children=[
                        Heading("Sales", level=3),
                        Metric(label="Median Price", value=_fmt_gbp(median_price)),
                        Metric(label="Transactions", value=str(sale_count)),
                    ])]),
                    Card(children=[CardContent(children=[
                        Heading("Rentals", level=3),
                        Metric(label="Median Rent/mo", value=_fmt_gbp(median_rent)),
                        Metric(label="Listings", value=str(rental_count)),
                    ])]),
                ],
            ),
        ],
        gap=4,
    )

    # Text summary for LLM reasoning
    text = (
        f"Yield analysis for {postcode.upper()} ({search_level}, {months}mo, {radius}mi): "
        f"{_fmt_pct(gross_yield)} gross yield ({assessment}), "
        f"median sale {_fmt_gbp(median_price)} ({sale_count} sales), "
        f"median rent {_fmt_gbp(median_rent)}/mo ({rental_count} listings), "
        f"data quality: {quality}"
    )

    return ToolResult(content=text, structured_content=view)
