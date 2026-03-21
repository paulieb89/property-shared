"""Typer CLI for property shared tools.

Defaults to calling `property_core` directly (fast, offline). Pass `--api-url`
to exercise the deployed API instead.
"""

from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()  # Load .env file for local development


import json
from typing import Iterable, Optional

import typer
from rich import print as rprint
from rich.table import Table

from property_core.epc_client import EPCClient

from property_core.rightmove_location import RightmoveLocationAPI
from property_core.rightmove_scraper import fetch_listing, fetch_listings

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


def _join_tokens(tokens: Iterable[str] | str) -> str:
    if isinstance(tokens, str):
        return tokens.strip()
    return " ".join(tokens).strip()


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
    postcode: list[str] = typer.Argument(..., help="Postcode (can include spaces)"),
    property_type: Optional[str] = typer.Option(None, help="D/S/T/F/O"),
    months: int = typer.Option(24, help="Lookback months"),
    limit: int = typer.Option(50, help="Max transactions"),
    search_level: str = typer.Option("sector", help="postcode|sector|district"),
    address: Optional[str] = typer.Option(None, help="Subject property address for context"),
    enrich_epc: bool = typer.Option(False, "--enrich-epc", help="Attach EPC floor area and price/sqft"),
    api_url: Optional[str] = typer.Option(None, help="Call API instead of core"),
) -> None:
    """Get comparable sales summary for a postcode.

    If --address is provided, also returns subject property transaction history.
    If --enrich-epc is set, attaches EPC floor area and price-per-sqft to each comp.
    """
    postcode_value = _join_tokens(postcode)
    http = _maybe_http_client(api_url)
    if http:
        params: dict[str, object] = {
            "postcode": postcode_value,
            "months": months,
            "limit": limit,
            "search_level": search_level,
        }
        if property_type:
            params["property_type"] = property_type
        if address:
            params["address"] = address
        if enrich_epc:
            params["enrich_epc"] = True
        data = http.get("/v1/ppd/comps", params=params)
        _echo_json(data)
    else:
        # Use service layer for full functionality including subject_property
        from property_core.ppd_service import PPDService
        service = PPDService()
        result = service.comps(
            postcode=postcode_value,
            property_type=property_type,
            months=months,
            limit=limit,
            search_level=search_level,
            address=address,
        )
        if enrich_epc:
            import asyncio
            from property_core.enrichment import compute_enriched_stats, enrich_comps_with_epc
            asyncio.run(enrich_comps_with_epc(result.transactions))
            compute_enriched_stats(result)
        _echo_json(result.model_dump())


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
        from property_core.ppd_service import PPDService
        result = PPDService().transaction_record(transaction_id, include_raw=include_raw)
        output = {"record": result["record"].model_dump(), "raw": result["raw"]}
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
        from property_core.ppd_service import PPDService
        result = PPDService().search_transactions(
            postcode=postcode,
            postcode_prefix=postcode_prefix,
            limit=limit,
        )
        _echo_json([t.model_dump() for t in result["results"]])


@ppd.command("address-search")
def ppd_address_search(
    paon: Optional[str] = typer.Option(None, help="Building name/number (e.g., '10' or 'Rose Cottage')"),
    saon: Optional[str] = typer.Option(None, help="Secondary address (e.g., 'Flat 2')"),
    street: Optional[str] = typer.Option(None, help="Street name"),
    town: Optional[str] = typer.Option(None, help="Town or city"),
    county: Optional[str] = typer.Option(None, help="County"),
    postcode: Optional[str] = typer.Option(None, help="Full postcode"),
    postcode_prefix: Optional[str] = typer.Option(None, help="Postcode prefix (e.g., 'SW1A')"),
    limit: int = typer.Option(25, help="Max results (max 50)"),
    api_url: Optional[str] = typer.Option(None, help="Call API instead of core"),
) -> None:
    """Search PPD by address fields (requires at least 2 fields)."""
    # Count provided fields
    provided = [v for v in (paon, saon, street, town, county, postcode, postcode_prefix) if v]
    if len(provided) < 2:
        typer.echo("Provide at least two address fields (e.g., --postcode SW1A --street 'Downing Street')")
        raise typer.Exit(code=1)

    http = _maybe_http_client(api_url)
    if http:
        params: dict[str, object] = {"limit": limit}
        if paon:
            params["paon"] = paon
        if saon:
            params["saon"] = saon
        if street:
            params["street"] = street
        if town:
            params["town"] = town
        if county:
            params["county"] = county
        if postcode:
            params["postcode"] = postcode
        if postcode_prefix:
            params["postcode_prefix"] = postcode_prefix
        data = http.get("/v1/ppd/address-search", params=params)
        _echo_json(data)
    else:
        from property_core.ppd_service import PPDService
        result = PPDService().address_search(
            paon=paon,
            saon=saon,
            street=street,
            town=town,
            county=county,
            postcode=postcode,
            postcode_prefix=postcode_prefix,
            limit=limit,
        )
        _echo_json([t.model_dump() for t in result["results"]])


@ppd.command("download-url")
def ppd_download_url(
    kind: str = typer.Option("monthly", help="Dataset: complete, year, or monthly"),
    year: Optional[int] = typer.Option(None, help="Year (required for 'year' kind)"),
    part: Optional[int] = typer.Option(None, help="Part 1 or 2 (optional for 'year' kind)"),
    fmt: str = typer.Option("csv", help="Format: csv or txt"),
    api_url: Optional[str] = typer.Option(None, help="Call API instead of core"),
) -> None:
    """Get Land Registry bulk download URL."""
    http = _maybe_http_client(api_url)
    if http:
        params: dict[str, object] = {"kind": kind, "fmt": fmt}
        if year is not None:
            params["year"] = year
        if part is not None:
            params["part"] = part
        data = http.get("/v1/ppd/download-url", params=params)
        typer.echo(data.get("url"))
    else:
        from property_core.ppd_service import PPDService
        try:
            url = PPDService().download_url(kind=kind, year=year, part=part, fmt=fmt)
        except ValueError as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=1) from exc
        typer.echo(url)


@ppd.command("blocks")
def ppd_blocks(
    postcode: list[str] = typer.Argument(..., help="Postcode (can include spaces)"),
    months: int = typer.Option(24, help="Lookback months"),
    limit: int = typer.Option(50, help="Target blocks"),
    min_transactions: int = typer.Option(2, "--min", help="Min sales per building"),
    search_level: str = typer.Option("sector", help="postcode|sector|district"),
    api_url: Optional[str] = typer.Option(None, help="Call API instead of core"),
) -> None:
    """Find buildings with multiple flat sales (block buyers)."""
    postcode_value = _join_tokens(postcode)
    http = _maybe_http_client(api_url)
    if http:
        data = http.get(
            "/v1/ppd/blocks",
            params={
                "postcode": postcode_value,
                "months": months,
                "limit": limit,
                "min_transactions": min_transactions,
                "search_level": search_level,
            },
        )
        _echo_json(data)
    else:
        from property_core.block_service import analyze_blocks

        result = analyze_blocks(
            postcode=postcode_value,
            months=months,
            limit=limit,
            min_transactions=min_transactions,
            search_level=search_level,
        )

        if not result.blocks:
            rprint(f"No blocks found with {min_transactions}+ flat sales")
            return

        table = Table(title=f"Flat Blocks — {postcode_value} ({result.blocks_found} found)")
        table.add_column("Building")
        table.add_column("Street")
        table.add_column("Sales", justify="right")
        table.add_column("Avg Price", justify="right")
        table.add_column("Range", justify="right")
        table.add_column("Dates")
        for b in result.blocks[:20]:
            price_range = ""
            if b.min_price and b.max_price:
                price_range = f"£{b.min_price:,} - £{b.max_price:,}"
            table.add_row(
                b.building_name or "",
                b.street or "",
                str(b.transaction_count),
                f"£{b.avg_price:,}" if b.avg_price else "",
                price_range,
                b.date_range or "",
            )
        rprint(table)


epc = typer.Typer(help="EPC commands")
app.add_typer(epc, name="epc")


@epc.command("search")
def epc_search(
    postcode: Optional[list[str]] = typer.Argument(None, help="Postcode (can include spaces)"),
    address: Optional[str] = typer.Option(None, help="Address filter (e.g., '10 Downing Street')"),
    q: Optional[str] = typer.Option(None, help="Combined query (e.g., '10 Downing Street, SW1A 2AA')"),
    include_raw: bool = typer.Option(False, help="Show raw EPC payload"),
    api_url: Optional[str] = typer.Option(None, help="Call API instead of core"),
) -> None:
    """Search for EPC by postcode or combined address query.

    Use --q for combined address input: '10 Downing Street, SW1A 2AA'
    """
    http = _maybe_http_client(api_url)
    if http:
        params: dict[str, object] = {"include_raw": include_raw}
        if q:
            params["q"] = q
        else:
            if not postcode:
                typer.echo("Provide postcode argument or --q parameter")
                raise typer.Exit(code=1)
            params["postcode"] = _join_tokens(postcode)
            if address:
                params["address"] = address
        data = http.get("/v1/epc/search", params=params)
        _echo_json(data)
        return

    # Core mode: parse q if provided
    if q:
        import re
        postcode_re = re.compile(r"([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\s*$", re.IGNORECASE)
        match = postcode_re.search(q)
        if match:
            postcode_value = match.group(1).upper()
            address = q[: match.start()].strip().rstrip(",").strip() or None
        else:
            typer.echo("Could not parse postcode from query. Use format: '10 Downing Street, SW1A 2AA'")
            raise typer.Exit(code=1)
    else:
        if not postcode:
            typer.echo("Provide postcode argument or --q parameter")
            raise typer.Exit(code=1)
        postcode_value = _join_tokens(postcode)

    client = EPCClient()
    if not client.is_configured():
        typer.echo("EPC not configured (set EPC_API_EMAIL/EPC_API_KEY)")
        raise typer.Exit(code=1)
    import asyncio

    result = asyncio.run(client.search_by_postcode(postcode_value, address=address))
    if not result:
        typer.echo("No EPC found")
        raise typer.Exit(code=1)
    output = {"record": result.model_dump(), "raw": result.raw if include_raw else None}
    _echo_json(output)


@epc.command("certificate")
def epc_certificate(
    certificate_hash: str = typer.Argument(..., help="EPC certificate hash (lmk-key)"),
    include_raw: bool = typer.Option(False, help="Show raw EPC payload"),
    api_url: Optional[str] = typer.Option(None, help="Call API instead of core"),
) -> None:
    """Get EPC certificate by hash (lmk-key)."""
    http = _maybe_http_client(api_url)
    if http:
        data = http.get(
            f"/v1/epc/certificate/{certificate_hash}",
            params={"include_raw": include_raw},
        )
        _echo_json(data)
        return

    client = EPCClient()
    if not client.is_configured():
        typer.echo("EPC not configured (set EPC_API_EMAIL/EPC_API_KEY)")
        raise typer.Exit(code=1)
    import asyncio

    result = asyncio.run(client.get_certificate(certificate_hash))
    if not result:
        typer.echo("No EPC found for this certificate hash")
        raise typer.Exit(code=1)
    output = {"record": result.model_dump(), "raw": result.raw if include_raw else None}
    _echo_json(output)


rightmove = typer.Typer(help="Rightmove commands")
app.add_typer(rightmove, name="rightmove")


@rightmove.command("search-url")
def rightmove_search_url(
    postcode: list[str] = typer.Argument(..., help="Postcode (can include spaces)"),
    property_type: str = typer.Option("sale"),
    radius: Optional[float] = typer.Option(None, help="Search radius in miles"),
    api_url: Optional[str] = typer.Option(None, help="Call API instead of core"),
) -> None:
    postcode_value = _join_tokens(postcode)
    http = _maybe_http_client(api_url)
    if http:
        data = http.get(
            "/v1/rightmove/search-url",
            params={
                "postcode": postcode_value,
                "property_type": property_type,
                "radius": radius,
            },
        )
        typer.echo(data.get("url"))
    else:
        api = RightmoveLocationAPI()
        url = api.build_search_url(
            postcode_value,
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


@rightmove.command("listing")
def rightmove_listing(
    url_or_id: str = typer.Argument(..., help="Rightmove property URL or numeric ID"),
    include_raw: bool = typer.Option(False, "--include-raw", help="Include raw PAGE_MODEL data"),
    api_url: Optional[str] = typer.Option(None, help="Call API instead of core"),
) -> None:
    """Fetch full details for an individual Rightmove listing."""
    http = _maybe_http_client(api_url)
    if http:
        # Extract property ID from URL if needed
        prop_id = url_or_id.strip().rstrip("/").split("/")[-1] if "/" in url_or_id else url_or_id
        data = http.get(
            f"/v1/rightmove/listing/{prop_id}",
            params={"include_raw": include_raw},
        )
        detail = data.get("result", {})
    else:
        result = fetch_listing(url_or_id, include_raw=include_raw)
        detail = result.model_dump()

    # Display structured output
    table = Table(title=f"Listing: {detail.get('address', url_or_id)}")
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("Price", f"£{detail.get('price', ''):,}" if detail.get("price") else "—")
    table.add_row("Bedrooms", str(detail.get("bedrooms") or "—"))
    table.add_row("Bathrooms", str(detail.get("bathrooms") or "—"))
    table.add_row("Property Type", detail.get("property_sub_type") or detail.get("property_type") or "—")
    table.add_row("Display Size", detail.get("display_size") or "—")
    table.add_row("Tenure", detail.get("tenure_type") or "—")
    table.add_row("Lease Remaining", f"{detail['years_remaining_on_lease']} years" if detail.get("years_remaining_on_lease") else "—")
    table.add_row("Service Charge", f"£{detail['annual_service_charge']:,}/yr" if detail.get("annual_service_charge") else "—")
    table.add_row("Ground Rent", f"£{detail['annual_ground_rent']:,}/yr" if detail.get("annual_ground_rent") else "—")
    table.add_row("Council Tax Band", detail.get("council_tax_band") or "—")
    table.add_row("Agent", detail.get("agent_name") or detail.get("agent_branch") or "—")
    table.add_row("Lat/Lon", f"{detail.get('latitude')}, {detail.get('longitude')}" if detail.get("latitude") else "—")
    table.add_row("Floorplans", str(len(detail.get("floorplans") or [])))
    table.add_row("Images", str(len(detail.get("images") or [])))

    rprint(table)

    if detail.get("key_features"):
        rprint("\n[bold]Key Features:[/bold]")
        for feat in detail["key_features"]:
            rprint(f"  • {feat}")

    if include_raw and detail.get("raw"):
        rprint("\n[bold]Raw data:[/bold]")
        rprint(json.dumps(detail["raw"], indent=2, default=str)[:5000])


planning = typer.Typer(help="Planning portal commands")
app.add_typer(planning, name="planning")


@planning.command("probe")
def planning_probe(
    url: str = typer.Argument(..., help="URL to probe"),
    timeout: int = typer.Option(30000, help="Timeout in milliseconds"),
    save_screenshot: Optional[str] = typer.Option(None, help="Save screenshot to this path"),
    proxy: Optional[str] = typer.Option(None, envvar="PLAYWRIGHT_PROXY_URL", help="Proxy URL (or set PLAYWRIGHT_PROXY_URL)"),
    api_url: Optional[str] = typer.Option(None, help="Call API instead of core"),
) -> None:
    """Quick connectivity probe to diagnose access issues (blocks, captchas, etc)."""
    http = _maybe_http_client(api_url)
    if http:
        data = http.post("/v1/planning/probe", json={"url": url, "timeout_ms": timeout})
    else:
        # Set proxy env var if provided via CLI
        if proxy:
            os.environ["PLAYWRIGHT_PROXY_URL"] = proxy
        from property_core.planning_scraper import probe_connectivity
        data = probe_connectivity(url=url, timeout_ms=timeout)

    # Extract and save screenshot if requested
    screenshot_b64 = data.pop("screenshot_base64", None)
    if save_screenshot and screenshot_b64:
        import base64
        from pathlib import Path
        Path(save_screenshot).write_bytes(base64.b64decode(screenshot_b64))
        rprint(f"[green]Screenshot saved to {save_screenshot}[/green]")

    # Show results
    rprint(f"\n[bold]Probe Results for:[/bold] {data.get('url', url)}")
    rprint(f"  Success: {'[green]Yes[/green]' if data.get('success') else '[red]No[/red]'}")
    rprint(f"  Status: {data.get('status_code')}")
    rprint(f"  Load time: {data.get('load_time_ms')}ms")
    rprint(f"  Page title: {data.get('page_title', 'N/A')}")
    proxy_used = data.get('proxy_used')
    rprint(f"  Proxy: {proxy_used[:50] + '...' if proxy_used and len(proxy_used) > 50 else proxy_used or '[dim]none[/dim]'}")

    if data.get("blocking_indicators"):
        rprint("\n[yellow]Blocking indicators:[/yellow]")
        for indicator in data["blocking_indicators"]:
            rprint(f"  - {indicator}")

    if data.get("error"):
        rprint(f"\n[red]Error:[/red] {data['error']}")

    if data.get("html_snippet"):
        rprint(f"\n[dim]HTML snippet (first 500 chars):[/dim]")
        rprint(data["html_snippet"][:500])


@planning.command("scrape")
def planning_scrape(
    url: str = typer.Argument(..., help="Planning application URL"),
    save_screenshots: bool = typer.Option(False, help="Save screenshots to ./output"),
    output_dir: Optional[str] = typer.Option(None, help="Output directory for screenshots"),
    api_url: Optional[str] = typer.Option(None, help="Call API instead of core"),
) -> None:
    """Scrape a planning application from any UK council portal."""
    http = _maybe_http_client(api_url)
    if http:
        data = http.post(
            "/v1/planning/scrape",
            json={"url": url, "save_screenshots": save_screenshots},
        )
        _echo_json(data)
    else:
        from pathlib import Path
        from property_core.planning_scraper import scrape_planning_application

        out = Path(output_dir) if output_dir else (Path("./output") if save_screenshots else None)
        result = scrape_planning_application(
            url=url,
            output_dir=out,
            save_screenshots=save_screenshots,
        )
        _echo_json(result)


@planning.command("councils")
def planning_councils(
    api_url: Optional[str] = typer.Option(None, help="Call API instead of core"),
) -> None:
    """List verified UK council planning portals."""
    http = _maybe_http_client(api_url)
    if http:
        data = http.get("/v1/planning/councils")
    else:
        from pathlib import Path
        councils_file = Path(__file__).parent.parent / "property_core" / "planning_councils.json"
        if councils_file.exists():
            data = json.load(open(councils_file))
        else:
            data = {"councils": [], "untested": []}

    table = Table(title="Verified Councils")
    table.add_column("Code")
    table.add_column("Name")
    table.add_column("System")
    for c in data.get("councils", []):
        table.add_row(c.get("code", ""), c.get("name", ""), c.get("system", ""))
    rprint(table)

    if data.get("untested"):
        rprint(f"\n[dim]+ {len(data['untested'])} untested councils[/dim]")


@planning.command("council")
def planning_council(
    code: str = typer.Argument(..., help="Council code (e.g., sheffield)"),
    api_url: Optional[str] = typer.Option(None, help="Call API instead of core"),
) -> None:
    """Get details for a specific council."""
    http = _maybe_http_client(api_url)
    if http:
        data = http.get(f"/v1/planning/council/{code}")
        _echo_json(data)
    else:
        from pathlib import Path
        councils_file = Path(__file__).parent.parent / "property_core" / "planning_councils.json"
        if not councils_file.exists():
            typer.echo("Councils database not found")
            raise typer.Exit(code=1)

        data = json.load(open(councils_file))
        for council in data.get("councils", []) + data.get("untested", []):
            if council.get("code") == code:
                _echo_json(council)
                return

        typer.echo(f"Council '{code}' not found")
        raise typer.Exit(code=1)


@planning.command("search")
def planning_search(
    postcode: list[str] = typer.Argument(..., help="UK postcode (can include spaces)"),
    api_url: Optional[str] = typer.Option(None, help="Call API instead of core"),
) -> None:
    """Search for planning applications by postcode.

    Returns the council search URLs for this postcode. For Idox councils
    (most common), provides a direct search URL you can open in a browser.
    """
    postcode_value = _join_tokens(postcode)
    http = _maybe_http_client(api_url)
    if http:
        data = http.get("/v1/planning/search", params={"postcode": postcode_value})
    else:
        from property_core.planning_service import PlanningService
        service = PlanningService()
        data = service.search(postcode_value)

    # Display results
    rprint(f"\n[bold]Planning Search for:[/bold] {data.get('postcode', postcode_value)}")

    if not data.get("council_found"):
        rprint(f"\n[yellow]No planning portal found for this area.[/yellow]")
        la = data.get("local_authority")
        if la:
            rprint(f"Local authority: {la.get('name')}")
        rprint("\n[dim]Use 'planning councils' to see available councils.[/dim]")
        return

    council = data.get("council", {})
    rprint(f"\n[bold]Council:[/bold] {council.get('name')}")
    rprint(f"  System: {council.get('system')}")
    rprint(f"  Status: {council.get('status')}")

    urls = data.get("search_urls", {})
    if urls.get("direct_search"):
        rprint(f"\n[bold green]Direct Search URL:[/bold green]")
        rprint(f"  {urls['direct_search']}")
    if urls.get("search_page"):
        rprint(f"\n[bold]Search Page:[/bold]")
        rprint(f"  {urls['search_page']}")
    if urls.get("instructions"):
        rprint(f"\n[dim]{urls['instructions']}[/dim]")

    if data.get("note"):
        rprint(f"\n[yellow]Note:[/yellow] {data['note']}")


@planning.command("applications")
def planning_applications(
    postcode: list[str] = typer.Argument(..., help="UK postcode (can include spaces)"),
    max_results: int = typer.Option(20, "--max", help="Maximum results to return"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Output JSON file path"),
) -> None:
    """Scrape planning applications for a postcode using vision-guided search.

    Uses AI vision to navigate council planning portals and extract applications.
    Requires UK residential IP for best results (council portals block datacenters).

    Example:
        property-cli planning applications "S1 2HH"
        property-cli planning applications "SW1A 1AA" --max 10 -o results.json
    """
    from pathlib import Path
    from property_core.planning_service import PlanningService
    from property_core.planning_scraper import search_planning_by_postcode

    postcode_value = _join_tokens(postcode)

    # First find the council portal URL
    rprint(f"\n[bold]Finding planning portal for:[/bold] {postcode_value}")
    service = PlanningService()
    search_data = service.search(postcode_value)

    if not search_data.get("council_found"):
        rprint(f"[red]No planning portal found for this area.[/red]")
        raise typer.Exit(code=1)

    council = search_data.get("council", {})
    urls = search_data.get("search_urls", {})

    rprint(f"[bold]Council:[/bold] {council.get('name')} ({council.get('system')})")

    # Get the search page URL - prefer simple search for postcode queries
    # direct_search has postcode pre-filled, search_page is often weekly list
    portal_url = urls.get("direct_search") or urls.get("search_page")

    # For Idox councils, ensure we use simple search (not weeklyList)
    if council.get("system") == "idox" and portal_url:
        # Convert weeklyList or other URLs to simple search
        if "weeklyList" in portal_url or "action=simple" not in portal_url:
            base = portal_url.split("/search.do")[0] if "/search.do" in portal_url else portal_url.rstrip("/")
            portal_url = f"{base}/search.do?action=simple"

    if not portal_url:
        rprint("[red]No search URL available for this council.[/red]")
        raise typer.Exit(code=1)

    rprint(f"[dim]Portal: {portal_url}[/dim]\n")

    # Run the vision-guided search
    try:
        results = search_planning_by_postcode(
            portal_url=portal_url,
            postcode=postcode_value,
            max_results=max_results,
        )
    except Exception as e:
        rprint(f"[red]Scraping failed: {e}[/red]")
        raise typer.Exit(code=1)

    if not results:
        rprint("[yellow]No planning applications found.[/yellow]")
        return

    # Display results
    rprint(f"\n[bold green]Found {len(results)} applications:[/bold green]\n")

    table = Table()
    table.add_column("Reference", style="cyan")
    table.add_column("Address")
    table.add_column("Description")
    table.add_column("Status")

    for app in results:
        table.add_row(
            app.get("reference", ""),
            app.get("address", "")[:40] + "..." if len(app.get("address", "")) > 40 else app.get("address", ""),
            app.get("description", "")[:50] + "..." if len(app.get("description", "")) > 50 else app.get("description", ""),
            app.get("status", ""),
        )
    rprint(table)

    # Save to file if requested
    if output:
        with open(output, "w") as f:
            json.dump(results, f, indent=2)
        rprint(f"\n[dim]Full results saved to: {output}[/dim]")
    else:
        rprint(f"\n[dim]Use -o results.json to save full data with links[/dim]")


@planning.command("council-for-postcode")
def planning_council_for_postcode(
    postcode: list[str] = typer.Argument(..., help="UK postcode (can include spaces)"),
    api_url: Optional[str] = typer.Option(None, help="Call API instead of core"),
) -> None:
    """Look up the planning council for a UK postcode."""
    postcode_value = _join_tokens(postcode)
    http = _maybe_http_client(api_url)
    if http:
        data = http.get("/v1/planning/council-for-postcode", params={"postcode": postcode_value})
    else:
        from property_core.planning_service import PlanningService
        service = PlanningService()
        data = service.council_for_postcode(postcode_value)

    # Display results
    rprint(f"\n[bold]Postcode:[/bold] {data.get('postcode', postcode_value)}")

    la = data.get("local_authority")
    if la:
        rprint(f"\n[bold]Local Authority:[/bold]")
        rprint(f"  Name: {la.get('name')}")
        rprint(f"  Code: {la.get('code')}")
        rprint(f"  Region: {la.get('region')}")

    council = data.get("council")
    if council:
        rprint(f"\n[bold green]Planning Portal Found:[/bold green]")
        rprint(f"  Name: {council.get('name')}")
        rprint(f"  Code: {council.get('code')}")
        rprint(f"  System: {council.get('system')}")
        rprint(f"  Status: {council.get('status')}")
        if council.get("base_url"):
            rprint(f"  URL: {council.get('base_url')}")
    else:
        rprint(f"\n[yellow]No planning portal found in database for this local authority.[/yellow]")
        rprint("[dim]Use 'planning councils' to see available councils.[/dim]")


# =============================================================================
# Calculator Commands
# =============================================================================

calc = typer.Typer(help="Property calculators")
app.add_typer(calc, name="calc")


@calc.command("stamp-duty")
def calc_stamp_duty(
    price: int = typer.Argument(..., help="Purchase price in £"),
    additional: bool = typer.Option(False, "--additional/--no-additional", help="Additional property surcharge (+5%)"),
    ftb: bool = typer.Option(False, "--ftb", help="First-time buyer relief"),
    non_resident: bool = typer.Option(False, "--non-resident", help="Non-UK resident surcharge (+2%)"),
    api_url: Optional[str] = typer.Option(None, help="Call API instead of core"),
) -> None:
    """Calculate UK Stamp Duty Land Tax (SDLT)."""
    http = _maybe_http_client(api_url)
    if http:
        data = http.get(
            "/v1/calculators/stamp-duty",
            params={
                "price": price,
                "additional_property": additional,
                "first_time_buyer": ftb,
                "non_resident": non_resident,
            },
        )
        _echo_json(data)
    else:
        from property_core.stamp_duty import calculate_stamp_duty

        result = calculate_stamp_duty(
            price=price,
            additional_property=additional,
            first_time_buyer=ftb,
            non_resident=non_resident,
        )

        table = Table(title=f"SDLT for £{price:,}")
        table.add_column("Band", style="bold")
        table.add_column("Amount", justify="right")
        table.add_column("Rate", justify="right")
        table.add_column("Tax", justify="right")
        for b in result.breakdown:
            table.add_row(b.band, f"£{b.amount:,}", f"{b.rate}%", f"£{b.tax:,.2f}")
        table.add_section()
        table.add_row("Total SDLT", "", f"{result.effective_rate}%", f"£{result.total_sdlt:,.2f}")
        rprint(table)


# =============================================================================
# Analysis Commands
# =============================================================================

analysis = typer.Typer(help="Yield and rental analysis")
app.add_typer(analysis, name="analysis")


@analysis.command("yield")
def analysis_yield(
    postcode: list[str] = typer.Argument(..., help="Postcode (can include spaces)"),
    months: int = typer.Option(24, help="PPD lookback months"),
    search_level: str = typer.Option("sector", help="postcode|sector|district"),
    radius: float = typer.Option(0.5, help="Rental search radius (miles)"),
    api_url: Optional[str] = typer.Option(None, help="Call API instead of core"),
) -> None:
    """Calculate gross rental yield for a postcode."""
    import asyncio

    postcode_value = _join_tokens(postcode)
    http = _maybe_http_client(api_url)
    if http:
        data = http.get(
            "/v1/analysis/yield",
            params={
                "postcode": postcode_value,
                "months": months,
                "search_level": search_level,
                "radius": radius,
            },
        )
        _echo_json(data)
    else:
        from property_core import calculate_yield

        result = asyncio.run(calculate_yield(
            postcode=postcode_value,
            months=months,
            search_level=search_level,
            radius=radius,
        ))

        table = Table(title=f"Yield Analysis — {postcode_value}")
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")
        table.add_row("Median Sale Price", f"£{result.median_sale_price:,}" if result.median_sale_price else "—")
        table.add_row("Sale Count", str(result.sale_count))
        table.add_row("Median Monthly Rent", f"£{result.median_monthly_rent:,}" if result.median_monthly_rent else "—")
        table.add_row("Rental Count", str(result.rental_count) if result.rental_count else "—")
        table.add_row("Gross Yield", f"{result.gross_yield_pct}%" if result.gross_yield_pct is not None else "—")
        table.add_row("Assessment", result.yield_assessment or "—")
        table.add_row("Data Quality", result.data_quality or "—")
        rprint(table)


@analysis.command("rental")
def analysis_rental(
    postcode: list[str] = typer.Argument(..., help="Postcode (can include spaces)"),
    radius: float = typer.Option(0.5, help="Search radius (miles)"),
    purchase_price: Optional[int] = typer.Option(None, "--price", help="Purchase price for yield calc"),
    api_url: Optional[str] = typer.Option(None, help="Call API instead of core"),
) -> None:
    """Rental market analysis for a postcode."""
    import asyncio

    postcode_value = _join_tokens(postcode)
    http = _maybe_http_client(api_url)
    if http:
        params: dict = {"postcode": postcode_value, "radius": radius}
        if purchase_price is not None:
            params["purchase_price"] = purchase_price
        data = http.get("/v1/analysis/rental", params=params)
        _echo_json(data)
    else:
        from property_core.rental_service import analyze_rentals

        result = asyncio.run(analyze_rentals(
            postcode_value,
            radius=radius,
            purchase_price=purchase_price,
        ))

        table = Table(title=f"Rental Analysis — {postcode_value}")
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")
        table.add_row("Listings Found", str(result.rental_listings_count))
        table.add_row("Median Rent", f"£{result.median_rent_monthly:,}/mo" if result.median_rent_monthly else "—")
        table.add_row("Average Rent", f"£{result.average_rent_monthly:,}/mo" if result.average_rent_monthly else "—")
        table.add_row("Range Low", f"£{result.rent_range_low:,}/mo" if result.rent_range_low else "—")
        table.add_row("Range High", f"£{result.rent_range_high:,}/mo" if result.rent_range_high else "—")
        if result.gross_yield_pct is not None:
            table.add_row("Gross Yield", f"{result.gross_yield_pct}%")
            table.add_row("Assessment", result.yield_assessment or "—")
        rprint(table)


# =============================================================================
# Companies House Commands
# =============================================================================

companies = typer.Typer(help="Companies House commands")
app.add_typer(companies, name="companies")


@companies.command("search")
def companies_search(
    query: list[str] = typer.Argument(..., help="Company name or number"),
    limit: int = typer.Option(5, help="Max results"),
    api_url: Optional[str] = typer.Option(None, help="Call API instead of core"),
) -> None:
    """Search Companies House for company information."""
    query_value = _join_tokens(query)
    http = _maybe_http_client(api_url)
    if http:
        data = http.get("/v1/companies/search", params={"q": query_value, "limit": limit})
        _echo_json(data)
    else:
        from property_core.companies_house_client import CompaniesHouseClient
        from property_core.models.companies_house import CompanyRecord

        client = CompaniesHouseClient()
        if not client.is_configured():
            typer.echo("Companies House not configured (set COMPANIES_HOUSE_API_KEY)")
            raise typer.Exit(code=1)

        result = client.lookup(query_value)

        if isinstance(result, CompanyRecord):
            # Direct company lookup
            table = Table(title=f"Company: {result.company_name}")
            table.add_column("Field", style="bold")
            table.add_column("Value")
            table.add_row("Number", result.company_number or "")
            table.add_row("Status", result.company_status or "")
            table.add_row("Type", result.company_type or "")
            table.add_row("Created", result.date_of_creation or "")
            if result.registered_office:
                addr = result.registered_office
                table.add_row("Address", ", ".join(v for v in [
                    addr.get("address_line_1"),
                    addr.get("address_line_2"),
                    addr.get("locality"),
                    addr.get("postal_code"),
                ] if v))
            if result.sic_codes:
                table.add_row("SIC Codes", ", ".join(result.sic_codes))
            rprint(table)

            if result.officers:
                rprint("\n[bold]Officers:[/bold]")
                for o in result.officers:
                    rprint(f"  {o.name} — {o.role} (appointed {o.appointed or '?'})")
        else:
            # Search results
            table = Table(title=f"Companies matching '{query_value}' ({result.total_results} total)")
            table.add_column("Number")
            table.add_column("Name")
            table.add_column("Status")
            table.add_column("Type")
            table.add_column("Address")
            for c in result.companies:
                table.add_row(
                    c.company_number or "",
                    c.company_name or "",
                    c.company_status or "",
                    c.company_type or "",
                    (c.address_snippet or "")[:40],
                )
            rprint(table)


# =============================================================================
# Report Commands
# =============================================================================

report = typer.Typer(help="Property report commands")
app.add_typer(report, name="report")


@report.command("generate")
def report_generate(
    address: list[str] = typer.Argument(..., help="Address with postcode, e.g. '10 Downing Street SW1A 2AA'"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path"),
    html: bool = typer.Option(False, "--html", help="Output as HTML (default is JSON)"),
    no_rentals: bool = typer.Option(False, "--no-rentals", help="Skip rental market analysis"),
    no_sales: bool = typer.Option(False, "--no-sales", help="Skip current sales market"),
    months: int = typer.Option(24, "--months", help="PPD lookback period in months"),
    radius: float = typer.Option(0.5, "--radius", help="Search radius in miles for Rightmove"),
    api_url: Optional[str] = typer.Option(None, help="Call API instead of core"),
) -> None:
    """Generate a comprehensive property intelligence report.

    Example:
        property-cli report generate "10 Downing Street, SW1A 2AA"
        property-cli report generate "SW1A 2AA" -o report.json
        property-cli report generate "SW1A 2AA" -o report.html --html
    """
    import asyncio
    import json

    address_query = _join_tokens(address)
    http = _maybe_http_client(api_url)

    rprint(f"\n[bold]Generating property report for:[/bold] {address_query}")
    rprint("[dim]Fetching data from multiple sources...[/dim]\n")

    if http:
        from property_core.models.report import PropertyReport

        try:
            data = http.post("/v1/property/report", json={
                "address": address_query,
                "include_rentals": not no_rentals,
                "include_sales_market": not no_sales,
                "ppd_months": months,
                "search_radius": radius,
            })
        except Exception as e:
            rprint(f"[red]Error:[/red] {e}")
            raise typer.Exit(code=1)
        report_data = PropertyReport(**data)
    else:
        from property_core.report_service import PropertyReportService

        service = PropertyReportService()
        try:
            report_data = asyncio.run(
                service.generate_report(
                    address_query,
                    include_rentals=not no_rentals,
                    include_sales_market=not no_sales,
                    ppd_months=months,
                    search_radius=radius,
                )
            )
        except ValueError as e:
            rprint(f"[red]Error:[/red] {e}")
            raise typer.Exit(code=1)

    # Display summary
    rprint(f"[bold green]Report Generated[/bold green] (ID: {report_data.report_id})")
    rprint(f"Address: {report_data.query_address or 'N/A'}")
    rprint(f"Postcode: {report_data.query_postcode}")

    # Key insights
    if report_data.key_insights:
        rprint("\n[bold]Key Insights:[/bold]")
        for insight in report_data.key_insights:
            rprint(f"  - {insight}")

    # Data sources
    rprint("\n[bold]Data Sources:[/bold]")
    for src in report_data.sources:
        status = "[green]OK[/green]" if src.available else "[yellow]N/A[/yellow]"
        if src.error:
            status = f"[red]{src.error}[/red]"
        rprint(f"  {src.name}: {status} ({src.records_found} records)")

    # Value estimate
    if report_data.estimated_value_low and report_data.estimated_value_high:
        rprint(f"\n[bold]Estimated Value Range:[/bold] £{report_data.estimated_value_low:,} - £{report_data.estimated_value_high:,}")

    # Output to file if requested
    if output:
        if html:
            from pathlib import Path
            from jinja2 import Environment, FileSystemLoader

            # Find template directory
            template_dir = Path(__file__).parent.parent / "app" / "templates"
            if not template_dir.exists():
                rprint("[red]Error: Template directory not found[/red]")
                raise typer.Exit(code=1)

            env = Environment(loader=FileSystemLoader(str(template_dir)))
            template = env.get_template("report.html")
            html_content = template.render(report=report_data)

            with open(output, "w") as f:
                f.write(html_content)
            rprint(f"\n[bold green]HTML report saved to: {output}[/bold green]")
        else:
            report_dict = report_data.model_dump(mode="json")
            with open(output, "w") as f:
                json.dump(report_dict, f, indent=2, default=str)
            rprint(f"\n[dim]Full report saved to: {output}[/dim]")
    else:
        rprint("\n[dim]Use -o report.json or -o report.html --html to save report[/dim]")


if __name__ == "__main__":
    app()


class HTTPClient:
    def __init__(self, base_url: str):
        if httpx is None:
            raise RuntimeError("Install api extras to use HTTP mode (uv sync --extra api)")
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=120)  # Planning scrapes can take 30-60s

    def get(self, path: str, params: Optional[dict[str, object]] = None) -> dict:
        resp = self.client.get(f"{self.base_url}{path}", params=params)
        resp.raise_for_status()
        return resp.json()

    def post(self, path: str, json: Optional[dict[str, object]] = None) -> dict:
        resp = self.client.post(f"{self.base_url}{path}", json=json)
        resp.raise_for_status()
        return resp.json()
