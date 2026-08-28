"""Standalone MCP App server -- property tools + interactive Prefab dashboards.

This is the 4th consumer of property_core, alongside the API, CLI, and MCP server.
Tools are real MCP tools (LLM-callable). Dashboards layer Prefab UI on top.
"""
from __future__ import annotations

from importlib.metadata import version as _pkg_version

from fastmcp import FastMCP
from fastmcp.server.middleware.caching import (
    CallToolSettings,
    ReadResourceSettings,
    ResponseCachingMiddleware,
)
# Main server — all tools registered directly via @mcp.tool()
from property_core.snapshot.bootstrap import fastmcp_lifespan, mark_installed

mcp = FastMCP(
    "property-app",
    # Same boot, same rule (spec 4.10). This server is deployed on its own, so
    # it must carry the lifespan itself -- there is no FastAPI app here to chain
    # it from.
    lifespan=fastmcp_lifespan(None),
    # Without this, FastMCP advertises its OWN version on the MCP card, so the
    # `initialize` response reported the framework version (3.2.4) while the
    # /.well-known/mcp/server-card.json route below reported the real one. The
    # plain server in app/mcp/server.py has always passed it; this one did not.
    version=_pkg_version("property-shared"),
    instructions=(
        "UK property tools with interactive dashboards. "
        "Tools return data directly -- dashboards add visual Prefab UI. "
        "Use property_dashboard for a unified view combining sales, yield, and rental data. "
        "Use comps_dashboard, yield_dashboard, rental_dashboard, listings_dashboard for focused single-topic views. "
        "Use search_comps, get_yield, get_rental for raw data. "
        "Use stamp_duty, planning_search, epc_lookup, rightmove_search for quick lookups. "
        "Use company_search to find a company by name. "
        "Price Paid Data results are bounded by the coverage stated in each "
        "response's `provenance`; an empty result means 'no sales in coverage', "
        "never 'never sold'. Contains HM Land Registry data (c) Crown copyright "
        "and database right, licensed under the Open Government Licence v3.0."
    ),
)


mark_installed(mcp)


@mcp.resource("councils://list")
def councils_list_resource() -> str:
    """Return the 99-council UK planning portal registry as JSON.

    Static reference data sourced from property_core/planning_councils.json.
    Lets callers read the full registry once instead of calling planning_search
    for individual lookups.
    """
    import json
    from importlib.resources import files

    raw = json.loads(files("property_core").joinpath("planning_councils.json").read_text())
    councils = raw.get("councils", raw)
    return json.dumps(councils, ensure_ascii=False, indent=2)


@mcp.resource("sdlt-bands://current")
def sdlt_bands_resource() -> str:
    """Return the current UK Stamp Duty Land Tax band schedule as JSON.

    Static reference data matching `property_core/stamp_duty.py` exactly.
    """
    import json

    data = {
        "version": "April 2025",
        "effective_from": "2025-04-01",
        "currency": "GBP",
        "main_bands": [
            {"threshold_above": 0, "threshold_up_to": 125000, "rate_pct": 0},
            {"threshold_above": 125000, "threshold_up_to": 250000, "rate_pct": 2},
            {"threshold_above": 250000, "threshold_up_to": 925000, "rate_pct": 5},
            {"threshold_above": 925000, "threshold_up_to": 1500000, "rate_pct": 10},
            {"threshold_above": 1500000, "threshold_up_to": None, "rate_pct": 12},
        ],
        "first_time_buyer_bands": [
            {"threshold_above": 0, "threshold_up_to": 300000, "rate_pct": 0},
            {"threshold_above": 300000, "threshold_up_to": 500000, "rate_pct": 5},
        ],
        "first_time_buyer_max_eligible_price": 500000,
        "additional_property_surcharge_pct": 5,
        "non_resident_surcharge_pct": 2,
        "source": "https://www.gov.uk/stamp-duty-land-tax/residential-property-rates",
        "notes": [
            "Additional-property surcharge rose from 3% to 5% in October 2024.",
            "Non-resident surcharge applies to buyers not resident in the UK in the 12 months before purchase.",
            "First-time buyer relief is only available when buying a single residence at £500k or under.",
        ],
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.resource("epc-ratings://reference")
def epc_ratings_resource() -> str:
    """Return EPC band definitions and score ranges as JSON.

    Canonical reference for UK domestic Energy Performance Certificate bands.
    """
    import json

    data = {
        "scale": "UK domestic SAP 2012",
        "ratings": [
            {"band": "A", "score_min": 92, "score_max": 100, "description": "Most efficient — very low running costs (near-zero or new-build standard)."},
            {"band": "B", "score_min": 81, "score_max": 91, "description": "Highly efficient — modern home with good insulation and heating."},
            {"band": "C", "score_min": 69, "score_max": 80, "description": "Above average — typical for recent builds or well-improved older homes. Proposed future minimum for rented homes (band C by 1 October 2030); not yet in force."},
            {"band": "D", "score_min": 55, "score_max": 68, "description": "Average — typical UK home as-built. Improvement potential usually high."},
            {"band": "E", "score_min": 39, "score_max": 54, "description": "Below average — the current legal minimum standard for rented homes in England and Wales (since 1 April 2020), subject to exemptions."},
            {"band": "F", "score_min": 21, "score_max": 38, "description": "Poor — running costs significantly above average, often single-glazed or uninsulated."},
            {"band": "G", "score_min": 1, "score_max": 20, "description": "Very poor — typically pre-1900 stock with no insulation upgrades."},
        ],
        "methodology": "Scores are calculated via the Standard Assessment Procedure (SAP 2012). Each property gets a current rating and a potential rating after recommended improvements.",
        "regulation_note": "The current legal minimum for privately rented domestic property in England and Wales is EPC band E (since 1 April 2020), subject to registered exemptions. The government has proposed raising this to band C, with a single compliance date of 1 October 2030 applying to all tenancies — an earlier date for new tenancies was explicitly ruled out. The band C standard is not yet in force.",
        "source": "https://www.gov.uk/government/collections/energy-performance-certificates",
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.resource("council://{code}")
def council_resource(code: str) -> str:
    """Return a single council's record as JSON, keyed by its code/slug.

    Raises ValueError if the code is unknown.
    """
    import json
    from importlib.resources import files

    raw = json.loads(files("property_core").joinpath("planning_councils.json").read_text())
    councils = raw.get("councils", raw)
    for c in councils:
        if c.get("code") == code or c.get("slug") == code:
            return json.dumps(c, ensure_ascii=False, indent=2)
    raise ValueError(f"Unknown council code: {code}")


@mcp.prompt()
def investment_analysis(
    address: str,
    postcode: str,
    purchase_price: str,
    additional_property: str = "true",
    first_time_buyer: str = "false",
    non_resident: str = "false",
) -> str:
    """Evaluate a UK property as a buy-to-let investment."""
    try:
        price_int = int(purchase_price)
        price_fmt = f"£{price_int:,}"
    except ValueError:
        price_fmt = f"£{purchase_price}"

    return f"""Evaluate {address}, {postcode} as a buy-to-let investment with a purchase price of {price_fmt}.

Run these tool calls in order:

1. `search_comps(postcode='{postcode}', address='{address}', months=24)` — establish area median for sanity-checking the asking price, plus subject property sale history.

2. `get_yield(postcode='{postcode}', months=24)` — area gross yield.

3. `epc_lookup(postcode='{postcode}', address='{address}')` — energy rating. The current legal minimum for England + Wales rentals is EPC band E; a band C minimum is proposed for 1 October 2030 but is not yet in force.

4. `stamp_duty(price={purchase_price}, additional_property={additional_property}, first_time_buyer={first_time_buyer}, non_resident={non_resident})` — calculate SDLT.

Then produce an investment summary (5–7 paragraphs):
- **Position vs market**: how {price_fmt} compares to area median.
- **Recent sale history**: years and prices, capital growth implied.
- **Gross yield**: median monthly rent × 12 / {price_fmt} × 100. Classify (strong ≥6%, average 4–6%, weak <4%).
- **Net yield rough estimate**: subtract 25-30% from gross for costs.
- **EPC compliance**: rating + regulatory note + rough cost of upgrades if needed.
- **Tax cost**: SDLT total and effective rate.
- **Key risks**: 2–3 specifics.

Cite specific numbers from each tool call. Describe, don't recommend.
"""


@mcp.prompt()
def area_comparison(
    postcodes: str,
    months: str = "24",
) -> str:
    """Compare 2-3 UK postcodes side-by-side for area-level investment evaluation."""
    parsed = [p.strip() for p in postcodes.split(",") if p.strip()]
    if len(parsed) < 2 or len(parsed) > 3:
        return f"Area comparison needs 2 or 3 postcodes — got {len(parsed)}: {parsed}. Ask the user to clarify."

    pc_list = ", ".join(repr(p) for p in parsed)
    return f"""Compare these UK postcodes for area-level investment characteristics: {pc_list}.

For each postcode, run two tool calls in parallel where possible:
- `search_comps(postcode=<pc>, months={months})` — area median sale price, transaction count, price range
- `get_yield(postcode=<pc>, months={months})` — area gross rental yield

After all calls return, produce a comparison table with columns:
- Postcode
- Area median sale price
- Sale count over {months} months (market depth)
- Median monthly rent
- Area gross yield %
- Yield assessment (strong ≥6%, average 4-6%, weak <4%)

Then write 2-3 sentences identifying which postcode looks strongest for a typical buy-to-let investor and why — citing specific numbers from your tool calls.
"""


@mcp.prompt()
def full_property_analysis(
    address: str,
    postcode: str,
    months: str = "24",
) -> str:
    """Comprehensive UK property analysis — composes comps, yield, EPC, asking prices, then synthesises.

    This is a workflow prompt, not a single API call. The LLM follows the
    instructions below to call the four primitive tools and synthesise the
    results explicitly, so every input is visible in the conversation.
    """
    return f"""Produce a comprehensive analysis of the property at {address}, {postcode}.

Execute these tool calls in order and show your work — state which tool you are calling, summarise its response, then move to the next.

1. **Sale history + area comparable sales**: call `search_comps(postcode='{postcode}', months={months}, address='{address}')`.
   - The response's `subject_property` section (if present) has this property's sale history.
   - The top-level fields (`median`, `mean`, `min`, `max`, `percentile_25`, `percentile_75`) describe the AREA, not this property.
   - The area median is the best proxy for current value. Use it for yield calculation later — never use a historical `subject_property.last_sale.price`, especially if old.

2. **Area gross rental yield**: call `get_yield(postcode='{postcode}', months={months})`.
   - Returns the AREA's median yield (area median sale price vs area median rent).
   - For a property-specific yield, recompute: `(median_monthly_rent × 12 / area_median_sale_price) × 100`. Use the area median from step 1, NOT this property's last sale price.

3. **Energy certificate**: call `epc_lookup(postcode='{postcode}', address='{address}')`.
   - With a specific address, returns the matched EPC certificate.
   - Note: rating (A–G), score (0–100), floor area, total annual energy cost, potential improvements.

4. **Current asking prices**: call `rightmove_search(postcode='{postcode}', property_type='sale')`.
   - Asking prices for sale right now. Typically above sold prices — the gap signals seller optimism vs. transactional reality.

Then synthesise (3–5 short paragraphs):
- This property's sale history (years and prices, if found).
- Where it sits relative to area median (above/below, by what percent — compare price to current area median, not historical).
- EPC rating, what it means in £/year, and improvement potential.
- A realistic gross yield using the current area median value.
- The asking-vs-sold gap and what it signals.

**Critical**: never quote a yield that divides current rent by an old sale price. Always cite which numbers came from which tool call.
"""


@mcp.custom_route("/health", methods=["GET"])
async def health(request):  # noqa: ARG001
    from starlette.responses import JSONResponse

    return JSONResponse({"status": "ok"})


@mcp.custom_route("/.well-known/glama.json", methods=["GET"])
async def glama_claim(request):
    from starlette.responses import JSONResponse

    return JSONResponse({
        "$schema": "https://glama.ai/mcp/schemas/connector.json",
        "maintainers": [{"email": "paul@bouch.dev"}],
    })


@mcp.custom_route("/.well-known/mcp/server-card.json", methods=["GET"])
async def smithery_server_card(request):
    from starlette.responses import JSONResponse

    return JSONResponse({"serverInfo": {"name": "property-app", "version": _pkg_version("property-shared")}})


_IMG_ALLOWED_HOSTS = frozenset({"media.rightmove.co.uk"})
_IMG_MAX_BYTES = 10 * 1024 * 1024
_IMG_MAX_REDIRECTS = 5
_IMG_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
# NB: a raw space is NOT disallowed here. Starlette decodes "+" in a query
# string to " ", and Rightmove media paths legitimately contain "+", so
# rejecting spaces would silently break image fetching. Host confusion is
# already prevented by parsing with httpx below; backslashes and control
# characters remain rejected.
_IMG_DISALLOWED_CHARS = frozenset("\\\t\n\r\x00\x7f")
_IMG_ALLOWED_CONTENT_TYPES = ("image/",)


def _validated_img_url(raw: str):
    """Validate an image URL using httpx's own parser and return an httpx.URL.

    Deliberately does NOT use urllib.parse: this request is issued by httpx, so
    validating with a different parser could let the two disagree about the host
    (the exact bypass class this check exists to prevent). Returns None if unsafe.
    """
    import httpx

    if not raw or _IMG_DISALLOWED_CHARS & set(raw):
        return None
    try:
        url = httpx.URL(raw)
    except httpx.InvalidURL:
        return None
    if url.scheme != "https":
        return None
    if url.userinfo:
        return None
    if url.port not in (None, 443):
        return None
    if (url.host or "").lower() not in _IMG_ALLOWED_HOSTS:
        return None
    return url


@mcp.custom_route("/img", methods=["GET"])
async def proxy_image(request):
    """Proxy Rightmove images through our domain to avoid CSP blocks.

    Only allowlisted hosts are fetched, and redirects are followed manually so
    each hop is re-validated — an allowlisted host must not be able to bounce
    this server to an arbitrary internal address.
    """
    import httpx
    from starlette.responses import Response

    url = _validated_img_url(request.query_params.get("url", ""))
    if url is None:
        return Response(status_code=400, content=b"Invalid URL")

    async with httpx.AsyncClient() as client:
        for _ in range(_IMG_MAX_REDIRECTS + 1):
            # Stream rather than buffer: a non-streaming get() materialises the
            # whole body in memory before any size check, so the cap would only
            # stop us forwarding it — not stop a 2GB body OOMing a 512MB VM.
            async with client.stream(
                "GET", url, follow_redirects=False, timeout=10.0
            ) as resp:
                if resp.status_code in _IMG_REDIRECT_STATUSES:
                    location = resp.headers.get("Location")
                    if not location:
                        return Response(status_code=502, content=b"Bad redirect")
                    try:
                        # httpx.URL.join — the same parser that issues the next
                        # request. join() itself can raise on hostile values
                        # (e.g. "////evil.example"), so it is inside the try.
                        joined = str(url.join(location))
                    except httpx.InvalidURL:
                        return Response(status_code=400, content=b"Invalid redirect target")
                    nxt = _validated_img_url(joined)
                    if nxt is None:
                        return Response(status_code=400, content=b"Invalid redirect target")
                    url = nxt
                    continue

                if resp.status_code >= 400:
                    return Response(status_code=502, content=b"Upstream error")

                content_type = resp.headers.get("content-type", "image/jpeg")
                # Only ever re-serve images. media.rightmove.co.uk carries
                # third-party-supplied files; echoing an arbitrary Content-Type
                # would let one be served as HTML on this app's own origin.
                if not content_type.lower().startswith(_IMG_ALLOWED_CONTENT_TYPES):
                    return Response(status_code=502, content=b"Unsupported content type")

                declared = resp.headers.get("Content-Length")
                if declared and declared.isdigit() and int(declared) > _IMG_MAX_BYTES:
                    return Response(status_code=502, content=b"Image too large")

                chunks: list[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total > _IMG_MAX_BYTES:
                        return Response(status_code=502, content=b"Image too large")
                    chunks.append(chunk)

                return Response(
                    content=b"".join(chunks),
                    media_type=content_type,
                    headers={
                        "Cache-Control": "public, max-age=86400",
                        "X-Content-Type-Options": "nosniff",
                    },
                )

    return Response(status_code=502, content=b"Too many redirects")


class _AcceptNormalizer:
    """Stamp Accept to the MCP-spec value on /mcp only, so json_response=True never 406s.

    Anthropic sends mixed Accept headers per request type (application/json for
    initialize, text/event-stream for tools/list). Only stamp the MCP endpoint —
    leave /health and other routes with their original Accept headers.
    """
    def __init__(self, app, mcp_path: bytes = b"/mcp"):
        self.app = app
        self._mcp_path = mcp_path.rstrip(b"/")

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path", "").rstrip("/").encode() == self._mcp_path:
            headers = [
                (b"accept", b"application/json, text/event-stream")
                if name.lower() == b"accept"
                else (name, value)
                for name, value in scope.get("headers", [])
            ]
            scope = {**scope, "headers": headers}
        await self.app(scope, receive, send)


def main() -> None:
    import os
    import uvicorn
    from fastmcp.server.http import create_streamable_http_app

    # Import tool/dashboard modules so they register on mcp/app
    from property_app import tools  # noqa: F401
    from property_app.dashboards import comps, listings, rental, unified, yield_view  # noqa: F401

    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport not in ("stdio", "http"):
        transport = "stdio"
    if transport == "http":
        port = int(os.environ.get("FASTMCP_PORT", "8080"))
        app = create_streamable_http_app(
            mcp,
            streamable_http_path="/mcp",
            json_response=True,
            stateless_http=True,
        )
        uvicorn.run(
            _AcceptNormalizer(app),
            host=os.environ.get("FASTMCP_HOST", "0.0.0.0"),
            port=port,
            forwarded_allow_ips="*",
            proxy_headers=True,
            lifespan="on",
            log_level="info",
        )
    else:
        mcp.run()


# 1h cache for read-only surfaces
mcp.add_middleware(ResponseCachingMiddleware(
    read_resource_settings=ReadResourceSettings(ttl=3600),
    call_tool_settings=CallToolSettings(ttl=3600),
))


if __name__ == "__main__":
    main()
