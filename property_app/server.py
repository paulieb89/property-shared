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
mcp = FastMCP(
    "property-app",
    instructions=(
        "UK property tools with interactive dashboards. "
        "Tools return data directly -- dashboards add visual Prefab UI. "
        "Use property_dashboard for a unified view combining sales, yield, and rental data. "
        "Use comps_dashboard, yield_dashboard, rental_dashboard, listings_dashboard for focused single-topic views. "
        "Use search_comps, get_yield, get_rental for raw data. "
        "Use stamp_duty, planning_search, epc_lookup, rightmove_search for quick lookups. "
        "Use company_search to find a company by name."
    ),
)


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


@mcp.custom_route("/img", methods=["GET"])
async def proxy_image(request):
    """Proxy external images through our domain to avoid CSP blocks."""
    import httpx
    from starlette.responses import Response

    url = request.query_params.get("url", "")
    if not url or not url.startswith("https://media.rightmove.co.uk"):
        return Response(status_code=400, content=b"Invalid URL")

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, follow_redirects=True, timeout=10.0)

    return Response(
        content=resp.content,
        media_type=resp.headers.get("content-type", "image/jpeg"),
        headers={"Cache-Control": "public, max-age=86400"},
    )


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
