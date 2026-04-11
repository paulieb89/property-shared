"""Rental analysis dashboard -- get_rental tool + interactive Prefab UI.

The get_rental tool is registered on the FastMCPApp so it is callable
by both LLMs and the Prefab UI via CallTool.  The rental_dashboard UI
entry point opens an interactive form that submits to get_rental and
renders rental market metrics, rent range, and market depth cards.
"""
from __future__ import annotations

from typing import Annotated

from prefab_ui.app import PrefabApp  # module-level for forward ref
from pydantic import Field

from property_app.server import app


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
# MCP tool (LLM + UI callable)
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
# Prefab UI entry point
# ---------------------------------------------------------------------------


@app.ui(
    title="Rental Analysis",
    description="Interactive rental market analyser with listing stats, rent range, and market depth",
)
def rental_dashboard(
    postcode: Annotated[str, Field(description="UK postcode")] = "NG1 1AA",
    radius: float = 0.5,
    purchase_price: int | None = None,
) -> "PrefabApp":
    """Return an interactive Prefab dashboard for rental analysis."""
    from prefab_ui.actions import SetState, ShowToast
    from prefab_ui.actions.mcp import CallTool
    from prefab_ui.app import PrefabApp
    from prefab_ui.components import (
        Button,
        Card,
        CardContent,
        Column,
        Form,
        Grid,
        Heading,
        Input,
        Metric,
        Separator,
    )
    from prefab_ui.rx import RESULT, Rx

    return PrefabApp(
        title="Rental Analysis",
        state={"data": None, "postcode": postcode},
        view=Column(
            children=[
                Heading("Rental Analysis", level=2),
                Form(
                    on_submit=CallTool(
                        tool="get_rental",
                        arguments={
                            "postcode": Rx("postcode"),
                            "radius": radius,
                        },
                        on_success=[SetState(key="data", value=RESULT)],
                        on_error=ShowToast(
                            message="Analysis failed", variant="error"
                        ),
                    ),
                    children=[
                        Input(
                            name="postcode",
                            value=postcode,
                            placeholder="Enter UK postcode",
                        ),
                        Input(
                            name="radius",
                            value=str(radius),
                            input_type="number",
                            placeholder="Radius (mi)",
                        ),
                        Input(
                            name="purchase_price",
                            input_type="number",
                            placeholder="Purchase price (optional)",
                        ),
                        Button(label="Analyse", button_type="submit"),
                    ],
                    gap=4,
                ),
                Separator(),
                Grid(
                    columns=4,
                    children=[
                        Metric(
                            label="Listings",
                            value=Rx("data.rental_listings_count") | "\u2014",
                        ),
                        Metric(
                            label="Median Rent",
                            value=Rx("data.median_rent_monthly") | "\u2014",
                        ),
                        Metric(
                            label="Avg Rent",
                            value=Rx("data.average_rent_monthly") | "\u2014",
                        ),
                        Metric(
                            label="Gross Yield",
                            value=Rx("data.gross_yield_pct") | "\u2014",
                        ),
                    ],
                ),
                Grid(
                    columns=2,
                    children=[
                        Card(
                            children=[
                                CardContent(
                                    children=[
                                        Heading("Rent Range", level=4),
                                        Metric(
                                            label="Min",
                                            value=Rx("data.rent_range_low") | "\u2014",
                                        ),
                                        Metric(
                                            label="Max",
                                            value=Rx("data.rent_range_high") | "\u2014",
                                        ),
                                    ],
                                ),
                            ],
                        ),
                        Card(
                            children=[
                                CardContent(
                                    children=[
                                        Heading("Market Depth", level=4),
                                        Metric(
                                            label="Thin Market",
                                            value=Rx("data.thin_market") | "\u2014",
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
            ],
            gap=4,
        ),
    )
