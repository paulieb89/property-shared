"""Comps dashboard — search_comps tool + interactive Prefab UI.

The search_comps tool is registered on the FastMCPApp so it is callable
by both LLMs and the Prefab UI via CallTool.  The comps_dashboard UI
entry point opens an interactive form that submits to search_comps and
renders stats + a transaction table.
"""
from __future__ import annotations

from typing import Annotated

from prefab_ui.app import PrefabApp
from pydantic import Field

from property_app.server import app


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
# MCP tool (LLM + UI callable)
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
# Prefab UI entry point
# ---------------------------------------------------------------------------


@app.ui(
    title="Comps Dashboard",
    description="Interactive comparable sales explorer with search, stats, and transaction table",
)
def comps_dashboard(
    postcode: Annotated[str, Field(description="UK postcode")] = "SW1A 1AA",
    months: int = 24,
    search_level: str = "sector",
) -> "PrefabApp":
    """Return an interactive Prefab dashboard for comparable sales."""
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
        title="Comps Dashboard",
        state={"results": None, "postcode": postcode},
        view=Column(
            children=[
                Heading("Comparable Sales", level=2),
                Form(
                    on_submit=CallTool(
                        search_comps,
                        arguments={
                            "postcode": Rx("postcode"),
                            "months": months,
                        },
                        on_success=[SetState(key="results", value=RESULT)],
                        on_error=ShowToast(
                            message="Search failed", variant="error"
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
                        Button(label="Search", button_type="submit"),
                    ],
                    gap=4,
                ),
                Separator(),
                Grid(
                    columns=4,
                    children=[
                        Metric(
                            label="Transactions",
                            value=Rx("results.count") | "\u2014",
                        ),
                        Metric(
                            label="Median",
                            value=Rx("results.median") | "\u2014",
                        ),
                        Metric(
                            label="25th Pctl",
                            value=Rx("results.percentile_25") | "\u2014",
                        ),
                        Metric(
                            label="75th Pctl",
                            value=Rx("results.percentile_75") | "\u2014",
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
                                        Heading("Price Range", level=3),
                                        Metric(
                                            label="Min",
                                            value=Rx("results.min") | "\u2014",
                                        ),
                                        Metric(
                                            label="Max",
                                            value=Rx("results.max") | "\u2014",
                                        ),
                                    ],
                                ),
                            ],
                        ),
                        Card(
                            children=[
                                CardContent(
                                    children=[
                                        Heading("Averages", level=3),
                                        Metric(
                                            label="Mean",
                                            value=Rx("results.mean") | "\u2014",
                                        ),
                                        Metric(
                                            label="Count",
                                            value=Rx("results.count") | "\u2014",
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
