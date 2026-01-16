"""Typer CLI for property shared tools.

Defaults to calling `property_core` directly (fast, offline). Pass `--api-url`
to exercise the deployed API instead.
"""

from __future__ import annotations

import json
from typing import Optional

import typer
from rich import print as rprint
from rich.table import Table

from property_core.epc_client import EPCClient
from property_core.ppd_client import PricePaidDataClient
from property_core.rightmove_location import RightmoveLocationAPI
from property_core.rightmove_scraper import fetch_listings

try:
    import httpx
except ImportError:  # pragma: no cover - optional when using API mode
    httpx = None

app = typer.Typer(help="Property shared CLI (core mode).")


def _maybe_http_client(api_url: Optional[str]) -> Optional["HTTPClient"]:
    if not api_url:
        return None
    return HTTPClient(api_url.rstrip("/"))


def _echo_json(data: object) -> None:
    rprint(json.dumps(data, indent=2, default=str))


@app.command("meta")
def meta(api_url: Optional[str] = typer.Option(None, help="Call API instead of core")) -> None:
    """Show integration availability (core or API)."""
    client = _maybe_http_client(api_url)
    if client:
        data = client.get("/v1/meta/integrations")
        _echo_json(data)
        return
    rprint(
        {
            "ppd": True,
            "epc": bool(EPCClient().is_configured()),
            "rightmove": True,
        }
    )


ppd = typer.Typer(help="PPD commands")
app.add_typer(ppd, name="ppd")


@ppd.command("comps")
def ppd_comps(
    postcode: str = typer.Argument(...),
    property_type: Optional[str] = typer.Option(None, help="D/S/T/F/O"),
    months: int = typer.Option(24, help="Lookback months"),
    limit: int = typer.Option(50, help="Max transactions"),
    search_level: str = typer.Option("sector", help="postcode|sector|district"),
    api_url: Optional[str] = typer.Option(None, help="Call API instead of core"),
) -> None:
    http = _maybe_http_client(api_url)
    if http:
        data = http.get(
            "/v1/ppd/comps",
            params={
                "postcode": postcode,
                "property_type": property_type,
                "months": months,
                "limit": limit,
                "search_level": search_level,
            },
        )
        _echo_json(data)
    else:
        client = PricePaidDataClient()
        data = client.get_comps_summary(
            postcode=postcode,
            property_type=property_type,
            months=months,
            limit=limit,
            search_level=search_level,
        )
        _echo_json(data)


@ppd.command("transaction")
def ppd_transaction(
    transaction_id: str = typer.Argument(...),
    include_raw: bool = typer.Option(False, help="Include raw linked-data JSON"),
    api_url: Optional[str] = typer.Option(None, help="Call API instead of core"),
) -> None:
    http = _maybe_http_client(api_url)
    if http:
        data = http.get(
            f"/v1/ppd/transaction/{transaction_id}",
            params={"include_raw": include_raw},
        )
        _echo_json(data)
    else:
        client = PricePaidDataClient()
        raw = client.get_transaction_record(transaction_id)
        output = {"record": raw, "raw": raw if include_raw else None}
        _echo_json(output)


@ppd.command("search")
def ppd_search(
    postcode: Optional[str] = typer.Option(None),
    postcode_prefix: Optional[str] = typer.Option(None),
    limit: int = typer.Option(10),
    api_url: Optional[str] = typer.Option(None, help="Call API instead of core"),
) -> None:
    if bool(postcode) == bool(postcode_prefix):
        typer.echo("Provide exactly one of --postcode or --postcode-prefix")
        raise typer.Exit(code=1)
    http = _maybe_http_client(api_url)
    if http:
        data = http.get(
            "/v1/ppd/transactions",
            params={
                "postcode": postcode,
                "postcode_prefix": postcode_prefix,
                "limit": limit,
            },
        )
        _echo_json(data)
    else:
        client = PricePaidDataClient()
        res = client.sparql_search(
            postcode=postcode,
            postcode_prefix=postcode_prefix,
            limit=limit,
        )
        _echo_json(res.get("results", {}))


epc = typer.Typer(help="EPC commands")
app.add_typer(epc, name="epc")


@epc.command("search")
def epc_search(
    postcode: str = typer.Argument(...),
    address: Optional[str] = typer.Option(None),
    include_raw: bool = typer.Option(False, help="Show raw EPC payload"),
    api_url: Optional[str] = typer.Option(None, help="Call API instead of core"),
) -> None:
    http = _maybe_http_client(api_url)
    if http:
        data = http.get(
            "/v1/epc/search",
            params={
                "postcode": postcode,
                "address": address,
                "include_raw": include_raw,
            },
        )
        _echo_json(data)
        return

    client = EPCClient()
    if not client.is_configured():
        typer.echo("EPC not configured (set EPC_API_EMAIL/EPC_API_KEY)")
        raise typer.Exit(code=1)
    import asyncio

    result = asyncio.run(client.search_by_postcode(postcode, address=address))
    if not result:
        typer.echo("No EPC found")
        raise typer.Exit(code=1)
    record, raw = result
    output = {"record": record, "raw": raw if include_raw else None}
    _echo_json(output)


rightmove = typer.Typer(help="Rightmove commands")
app.add_typer(rightmove, name="rightmove")


@rightmove.command("search-url")
def rightmove_search_url(
    postcode: str = typer.Argument(...),
    property_type: str = typer.Option("sale"),
    radius: Optional[float] = typer.Option(None, help="Search radius in miles"),
    api_url: Optional[str] = typer.Option(None, help="Call API instead of core"),
) -> None:
    http = _maybe_http_client(api_url)
    if http:
        data = http.get(
            "/v1/rightmove/search-url",
            params={
                "postcode": postcode,
                "property_type": property_type,
                "radius": radius,
            },
        )
        typer.echo(data.get("url"))
    else:
        api = RightmoveLocationAPI()
        url = api.build_search_url(
            postcode,
            property_type=property_type,
            radius=radius,
        )
        typer.echo(url)


@rightmove.command("listings")
def rightmove_listings(
    search_url: str = typer.Argument(...),
    max_pages: Optional[int] = typer.Option(1),
    rate_limit_seconds: float = typer.Option(0.6, help="Delay between pages"),
    api_url: Optional[str] = typer.Option(None, help="Call API instead of core"),
) -> None:
    http = _maybe_http_client(api_url)
    if http:
        data = http.get(
            "/v1/rightmove/listings",
            params={"search_url": search_url, "max_pages": max_pages},
        )
        listings = [
            typer.SimpleNamespace(
                price=item.get("price"),
                bedrooms=item.get("bedrooms"),
                address=item.get("address"),
            )
            for item in data.get("results", [])
        ]
    else:
        listings = fetch_listings(
            search_url,
            max_pages=max_pages,
            rate_limit_seconds=rate_limit_seconds,
        )
    table = Table(title=f"Listings ({len(listings)})")
    table.add_column("Price", justify="right")
    table.add_column("Beds", justify="right")
    table.add_column("Address")
    for item in listings[:20]:
        table.add_row(
            f"{item.price or ''}",
            f"{item.bedrooms or ''}",
            item.address or "",
        )
    rprint(table)
    if len(listings) > 20:
        typer.echo(f"...and {len(listings) - 20} more")


if __name__ == "__main__":
    app()


class HTTPClient:
    def __init__(self, base_url: str):
        if httpx is None:
            raise RuntimeError("Install api extras to use HTTP mode (uv sync --extra api)")
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=15)

    def get(self, path: str, params: Optional[dict[str, object]] = None) -> dict:
        resp = self.client.get(f"{self.base_url}{path}", params=params)
        resp.raise_for_status()
        return resp.json()
