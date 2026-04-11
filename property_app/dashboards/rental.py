"""Rental analysis dashboard — pre-populated rental market view.

get_rental: @app.tool(model=True) — returns raw dict, callable by LLM and UI
rental_dashboard: @mcp.tool(app=True) — fetches data server-side, returns rich Prefab view
"""
from __future__ import annotations

from typing import Annotated

from pydantic import Field

from property_app.server import app, mcp


# ---------------------------------------------------------------------------
# Raw async helper (testable without MCP decorator overhead)
# ---------------------------------------------------------------------------


async def _fetch_rental(
    postcode: str,
    radius: float = 0.5,
    purchase_price: int | None = None,
    auto_escalate: bool = True,
    building_type: str | None = None,
) -> dict:
    """Call analyze_rentals and return a plain dict."""
    from property_core import analyze_rentals

    result = await analyze_rentals(
        postcode=postcode,
        radius=radius,
        purchase_price=purchase_price,
        auto_escalate=auto_escalate,
        building_type=building_type,
    )
    return result.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Data tool (LLM + UI callable) — returns raw dict
# ---------------------------------------------------------------------------


@app.tool(
    model=True,
    description="Analyse rental market for a UK postcode",
    timeout=60.0,
)
async def get_rental(
    postcode: Annotated[str, Field(description="UK postcode e.g. NG1 1AA")],
    radius: Annotated[float, Field(description="Search radius in miles", ge=0.1, le=5.0)] = 0.5,
    purchase_price: Annotated[int | None, Field(description="Purchase price for yield calc")] = None,
    auto_escalate: Annotated[bool, Field(description="Widen search on thin market")] = True,
    building_type: Annotated[str | None, Field(description="Flats, detached, semi, terraced")] = None,
) -> dict:
    """Analyse rental market for a UK postcode.

    Returns listing count, median/average rent, rent range,
    and optional gross yield if purchase_price is provided.
    """
    return await _fetch_rental(
        postcode=postcode,
        radius=radius,
        purchase_price=purchase_price,
        auto_escalate=auto_escalate,
        building_type=building_type,
    )


# ---------------------------------------------------------------------------
# Helpers for the Prefab view
# ---------------------------------------------------------------------------


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
    tags={"rental", "dashboard"},
    timeout=120.0,
)
async def rental_dashboard(
    postcode: Annotated[str, Field(description="UK postcode e.g. NG1 1AA")],
    radius: Annotated[float, Field(description="Search radius in miles")] = 0.5,
    purchase_price: Annotated[int | None, Field(description="Purchase price for yield calc")] = None,
):
    """Show rental market analysis as an interactive dashboard.

    Displays rental listing stats, rent range, market depth,
    and optional gross yield if a purchase price is provided.
    """
    from fastmcp.tools import ToolResult
    from prefab_ui.components import (
        Alert,
        Card,
        CardContent,
        Column,
        Dot,
        Grid,
        Heading,
        Metric,
        Muted,
        Row,
        Separator,
        Text,
    )

    data = await _fetch_rental(
        postcode=postcode,
        radius=radius,
        purchase_price=purchase_price,
    )

    listing_count = data.get("rental_listings_count", 0)
    median_rent = data.get("median_rent_monthly")
    avg_rent = data.get("average_rent_monthly")
    min_rent = data.get("min_rent")
    max_rent = data.get("max_rent")
    gross_yield = data.get("gross_yield_pct")
    thin_market = data.get("thin_market", False)
    escalated_from = data.get("escalated_from")
    escalated_to = data.get("escalated_to")

    # Build yield card only if purchase price was provided
    yield_children = []
    if purchase_price and gross_yield is not None:
        yield_children = [
            Separator(),
            Heading("Investment Yield", level=3),
            Grid(columns=2, children=[
                Metric(label="Purchase Price", value=_fmt_gbp(purchase_price)),
                Metric(label="Gross Yield", value=_fmt_pct(gross_yield)),
            ]),
        ]

    # Alerts
    alerts = []
    if thin_market:
        alerts.append(Alert(
            children=[Muted(f"Thin market \u2014 only {listing_count} listings found")],
            variant="warning",
        ))
    if escalated_from and escalated_to:
        alerts.append(Alert(
            children=[Muted(f"Search widened from {escalated_from}mi to {escalated_to}mi radius")],
            variant="info",
        ))

    view = Column(
        children=[
            # Header
            Heading(f"Rental Analysis \u2014 {postcode.upper()}", level=2),
            Muted(f"{radius}mi radius \u00b7 {listing_count} listings"),

            Separator(),

            # Key stats
            Grid(
                columns=3,
                children=[
                    Metric(label="Median Rent/mo", value=_fmt_gbp(median_rent)),
                    Metric(label="Average Rent/mo", value=_fmt_gbp(avg_rent)),
                    Metric(label="Listings Found", value=str(listing_count)),
                ],
            ),

            Separator(),

            # Rent range
            Grid(
                columns=2,
                children=[
                    Card(children=[CardContent(children=[
                        Heading("Rent Range", level=3),
                        Metric(label="Lowest", value=_fmt_gbp(min_rent)),
                        Metric(label="Highest", value=_fmt_gbp(max_rent)),
                    ])]),
                    Card(children=[CardContent(children=[
                        Heading("Market", level=3),
                        Row(children=[
                            Dot(variant="destructive" if thin_market else "success"),
                            Text("Thin market" if thin_market else "Adequate supply"),
                        ], gap=2, css_class="items-center"),
                    ])]),
                ],
            ),

            # Alerts (thin market, escalation)
            *alerts,

            # Optional yield section
            *yield_children,
        ],
        gap=4,
    )

    # Text summary for LLM reasoning
    parts = [
        f"Rental analysis for {postcode.upper()} ({radius}mi): "
        f"{listing_count} listings, median {_fmt_gbp(median_rent)}/mo, "
        f"avg {_fmt_gbp(avg_rent)}/mo, "
        f"range {_fmt_gbp(min_rent)}\u2013{_fmt_gbp(max_rent)}"
    ]
    if thin_market:
        parts.append(", thin market")
    if gross_yield is not None:
        parts.append(f", {_fmt_pct(gross_yield)} gross yield on {_fmt_gbp(purchase_price)}")

    return ToolResult(content="".join(parts), structured_content=view)
