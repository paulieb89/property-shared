"""Listings dashboard — pre-populated Rightmove listings view with images.

rightmove_search: plain @mcp.tool() in tools.py — returns raw dict
listings_dashboard: @mcp.tool(app=PrefabAppConfig) — fetches listings server-side, shows cards with thumbnails
"""
from __future__ import annotations

from typing import Annotated

from pydantic import Field

from property_app.server import mcp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt_gbp(n: int | float | None) -> str:
    if n is None:
        return "—"
    return f"\u00a3{int(n):,}"


def _fmt_rent(price: int | None, frequency: str | None) -> str:
    if price is None:
        return "—"
    label = _fmt_gbp(price)
    if frequency == "monthly":
        return f"{label}/mo"
    if frequency == "weekly":
        return f"{label}/wk"
    return label


# ---------------------------------------------------------------------------
# Pre-populated Prefab dashboard
# ---------------------------------------------------------------------------


def _listings_app_config():
    """CSP config allowing Rightmove image CDN."""
    from fastmcp.apps import PrefabAppConfig, ResourceCSP

    return PrefabAppConfig(
        csp=ResourceCSP(
            resource_domains=[
                "https://media.rightmove.co.uk",
                "https://media.rightmove.co.uk:443",
            ],
        ),
    )


@mcp.tool(
    app=_listings_app_config(),
    annotations={"readOnlyHint": True, "openWorldHint": True},
    tags={"rightmove", "listings", "dashboard"},
    timeout=120.0,
)
def listings_dashboard(
    postcode: Annotated[str, Field(description="UK postcode e.g. NG1 1AA")],
    property_type: Annotated[str, Field(description="'sale' or 'rent'")] = "sale",
    min_bedrooms: Annotated[int | None, Field(description="Minimum bedrooms")] = None,
    max_price: Annotated[int | None, Field(description="Maximum price")] = None,
    radius: Annotated[float | None, Field(description="Search radius in miles")] = None,
    building_type: Annotated[str | None, Field(description="F=flat, D=detached, S=semi, T=terraced")] = None,
):
    """Show Rightmove property listings as a visual dashboard with images.

    Searches Rightmove for sale or rent listings and displays them
    as cards with property photos, prices, and key details.
    """
    from statistics import median as stat_median

    from fastmcp.apps import PrefabAppConfig, ResourceCSP
    from fastmcp.tools import ToolResult
    from prefab_ui.components import (
        Badge,
        Card,
        CardContent,
        Column,
        Grid,
        Heading,
        Image,
        Metric,
        Muted,
        Row,
        Separator,
        Text,
    )

    from property_core import RightmoveLocationAPI, fetch_listings

    # Fetch listings (un-slimmed — we need image URLs)
    loc_api = RightmoveLocationAPI()
    search_url = loc_api.build_search_url(
        postcode,
        property_type=property_type,
        min_bedrooms=min_bedrooms,
        max_price=max_price,
        radius=radius,
        building_type=building_type,
    )
    raw_listings = fetch_listings(search_url, max_pages=1)

    prices = [l.price for l in raw_listings if l.price and l.price > 0]
    median_price = int(stat_median(prices)) if prices else None
    count = len(raw_listings)

    # Build listing cards
    listing_cards = []
    for l in raw_listings[:12]:  # Cap at 12 for reasonable widget size
        # First image as thumbnail
        img_children = []
        if l.images:
            # Strip :443 from URLs — redundant for HTTPS and may cause CSP mismatch
            img_url = l.images[0].replace(":443", "")
            img_children.append(
                Image(
                    src=img_url,
                    alt=l.address or "Property",
                    height=160,
                    css_class="w-full object-cover rounded-t-lg",
                )
            )

        # Status badge
        status_children = []
        if l.listing_status:
            variant = "destructive"
            if l.listing_status in ("SOLD_STC", "LET_AGREED"):
                variant = "warning"
            elif l.listing_status == "UNDER_OFFER":
                variant = "info"
            status_children.append(Badge(label=l.listing_status.replace("_", " ").title(), variant=variant))

        # Price display
        if property_type == "rent":
            price_text = _fmt_rent(l.price, l.price_frequency)
        else:
            price_text = _fmt_gbp(l.price)

        card = Card(children=[
            *img_children,
            CardContent(children=[
                Row(children=[
                    Heading(price_text, level=4),
                    *status_children,
                ], gap=2, css_class="items-center"),
                Text(l.address or "—", css_class="text-sm"),
                Row(children=[
                    Badge(label=l.property_type or "—", variant="outline"),
                    *(
                        [Badge(label=f"{l.bedrooms} bed", variant="secondary")]
                        if l.bedrooms else []
                    ),
                ], gap=2),
                Muted(l.agent_name or ""),
            ]),
        ])
        listing_cards.append(card)

    # Type label for header
    type_label = "For Rent" if property_type == "rent" else "For Sale"

    view = Column(
        children=[
            Heading(f"Properties {type_label} \u2014 {postcode.upper()}", level=2),
            Muted(f"{count} listings found on Rightmove"),

            Separator(),

            # Stats
            Grid(columns=3, children=[
                Metric(label="Listings", value=str(count)),
                Metric(label="Median Price", value=_fmt_gbp(median_price)),
                Metric(
                    label="Price Range",
                    value=f"{_fmt_gbp(min(prices))} \u2013 {_fmt_gbp(max(prices))}" if prices else "—",
                ),
            ]),

            Separator(),

            # Listing cards grid
            *(
                [Grid(columns=2, children=listing_cards, gap=4)]
                if listing_cards
                else [Muted("No listings found")]
            ),
        ],
        gap=4,
    )

    # Text summary for LLM
    text = (
        f"{count} {property_type} listings near {postcode.upper()}, "
        f"median {_fmt_gbp(median_price)}"
    )
    if prices:
        text += f", range {_fmt_gbp(min(prices))}\u2013{_fmt_gbp(max(prices))}"

    return ToolResult(content=text, structured_content=view)
