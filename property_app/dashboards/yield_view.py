"""Yield analysis dashboard -- get_yield tool + interactive Prefab UI.

The get_yield tool is registered on the FastMCPApp so it is callable
by both LLMs and the Prefab UI via CallTool.  The yield_dashboard UI
entry point opens an interactive form that submits to get_yield and
renders yield metrics, assessment, and sale/rental detail cards.
"""
from __future__ import annotations

from typing import Annotated

from prefab_ui.app import PrefabApp  # module-level for forward ref
from pydantic import Field

from property_app.server import app


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
# MCP tool (LLM + UI callable)
# ---------------------------------------------------------------------------


@app.tool(
    model=True,
    description="Analyse gross rental yield for a UK postcode",
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
# Prefab UI entry point
# ---------------------------------------------------------------------------


@app.ui(
    title="Yield Dashboard",
    description="Interactive gross rental yield analyser with sale and rental market metrics",
)
def yield_dashboard(
    postcode: Annotated[str, Field(description="UK postcode")] = "NG1 1AA",
    months: int = 24,
    radius: float = 0.5,
) -> "PrefabApp":
    """Return an interactive Prefab dashboard for yield analysis."""
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
        Text,
    )
    from prefab_ui.rx import RESULT, Rx

    from property_app.formatting import fmt_gbp, fmt_pct

    return PrefabApp(
        title="Yield Dashboard",
        state={"data": None, "postcode": postcode},
        view=Column(
            children=[
                Heading("Yield Analysis", level=2),
                Form(
                    on_submit=CallTool(
                        tool="get_yield",
                        arguments={
                            "postcode": Rx("postcode"),
                            "months": months,
                            "radius": radius,
                        },
                        on_success=[SetState(key="data", value=RESULT)],
                        on_error=ShowToast(
                            message="Yield analysis failed", variant="error"
                        ),
                    ),
                    children=[
                        Input(
                            name="postcode",
                            value=postcode,
                            placeholder="Enter UK postcode",
                        ),
                        Input(
                            name="months",
                            value=str(months),
                            input_type="number",
                            placeholder="Lookback months",
                        ),
                        Input(
                            name="radius",
                            value=str(radius),
                            input_type="number",
                            placeholder="Rental search radius (miles)",
                        ),
                        Button(label="Analyse", button_type="submit"),
                    ],
                    gap=4,
                ),
                Separator(),
                Grid(
                    columns=3,
                    children=[
                        Metric(
                            label="Gross Yield",
                            value=Rx("data.gross_yield_pct") | "\u2014",
                        ),
                        Metric(
                            label="Assessment",
                            value=Rx("data.yield_assessment") | "\u2014",
                        ),
                        Metric(
                            label="Data Quality",
                            value=Rx("data.data_quality") | "\u2014",
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
                                        Heading("Sales", level=3),
                                        Metric(
                                            label="Median Price",
                                            value=Rx("data.median_sale_price") | "\u2014",
                                        ),
                                        Metric(
                                            label="Sale Count",
                                            value=Rx("data.sale_count") | "\u2014",
                                        ),
                                    ],
                                ),
                            ],
                        ),
                        Card(
                            children=[
                                CardContent(
                                    children=[
                                        Heading("Rentals", level=3),
                                        Metric(
                                            label="Median Rent/mo",
                                            value=Rx("data.median_monthly_rent") | "\u2014",
                                        ),
                                        Metric(
                                            label="Rental Count",
                                            value=Rx("data.rental_count") | "\u2014",
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
