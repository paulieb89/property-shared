# Property App — MCP App with Prefab UI

The 4th consumer of `property_core` (alongside API, CLI, MCP server). A FastMCP 3.2+ server with Prefab UI 0.19+ dashboards, deployed on Fly.io.

**Production:** `https://propertydata.fly.dev/mcp`

## Commands

```bash
# Run locally
uv run --extra apps property-app                                  # stdio
MCP_TRANSPORT=http uv run --extra apps property-app               # HTTP
uv run --extra apps fastmcp dev apps property_app/server.py:mcp   # dev preview in browser

# Tests
uv run pytest tests/test_app_*.py -v

# Deploy
fly deploy --config fly.app.toml
```

## Architecture

```
property_app/
├── server.py              # FastMCP instance, /health, /img proxy, lazy imports in main()
├── tools.py               # Plain tools + stamp_duty (app=True) + component_test, image_test
├── formatting.py          # fmt_gbp(), fmt_pct(), fmt_date()
└── dashboards/
    ├── comps.py           # search_comps + comps_dashboard (BarChart, Sparkline, Table, Tabs)
    ├── yield_view.py      # get_yield + yield_dashboard (Badge assessment, Cards)
    ├── rental.py          # get_rental + rental_dashboard (Dot status, Alert, Cards)
    └── listings.py        # listings_dashboard (listing Cards with status Badges)
```

## Tool Inventory

| Tool | Type | Async | File | property_core dependency |
|------|------|-------|------|--------------------------|
| `stamp_duty` | dashboard (app=True) | no | tools.py | `calculate_stamp_duty()` |
| `planning_search` | data → dict | no | tools.py | `PlanningService.search()` |
| `company_search` | data → dict | no | tools.py | `CompaniesHouseClient` |
| `epc_lookup` | data → dict | yes | tools.py | `EPCClient.search_by_postcode()` |
| `rightmove_search` | data → dict | no | tools.py | `RightmoveLocationAPI`, `fetch_listings()` |
| `search_comps` | data → dict | no | dashboards/comps.py | `PPDService.comps()` |
| `comps_dashboard` | dashboard (app=True) | no | dashboards/comps.py | `PPDService.comps()` |
| `get_yield` | data → dict | yes | dashboards/yield_view.py | `calculate_yield()`, `classify_yield()`, `classify_data_quality()` |
| `yield_dashboard` | dashboard (app=True) | yes | dashboards/yield_view.py | same as get_yield |
| `get_rental` | data → dict | yes | dashboards/rental.py | `analyze_rentals()` |
| `rental_dashboard` | dashboard (app=True) | yes | dashboards/rental.py | same as get_rental |
| `listings_dashboard` | dashboard (app=True) | no | dashboards/listings.py | `RightmoveLocationAPI`, `fetch_listings()` |
| `component_test` | utility (app=True) | no | tools.py | none |
| `image_test` | utility | no | tools.py | none |

## Key Patterns

### Data + Dashboard pairs

Each dashboard file has two tools calling the same `_helper()`:
- **Data tool** (`@mcp.tool()`) → returns `dict` for LLM reasoning
- **Dashboard tool** (`@mcp.tool(app=True)`) → returns `ToolResult` with Prefab view

```python
def _fetch_data(postcode: str) -> dict:
    """Raw helper — calls property_core, returns dict."""
    result = SomeService().method(postcode)
    return _slim(result.model_dump(mode="json"))

@mcp.tool()
def get_data(postcode: str) -> dict:
    """Data for LLM."""
    return _fetch_data(postcode)

@mcp.tool(app=True)
def data_dashboard(postcode: str):
    """Visual dashboard."""
    data = _fetch_data(postcode)
    view = Column(children=[...], gap=4)
    return ToolResult(content=f"Summary for {postcode}", structured_content=view)
```

### Pre-populate, not forms

Always use `@mcp.tool(app=True)` with server-side data fetch. Do NOT use `@app.ui()` + `CallTool` — it renders empty forms that look broken.

### Text fallback

Always return `ToolResult(content=text_summary, structured_content=view)`. Without `content`, the LLM only sees `"[Rendered Prefab UI]"` and can't reason about the data.

### `_slim()` on data tools

Strip `raw`, `images`, `floorplans`, `epc_match` from data tool returns to stay under token budget. Defined in `tools.py`.

### Constructor vs context manager

Our dashboards use the constructor pattern: `Column(children=[...])`. FastMCP docs also show context manager syntax: `with Column() as view:`. Both work — be consistent within a file.

### Annotations

All tools use `readOnlyHint=True`. External API tools add `openWorldHint=True`. Calculator tools add `idempotentHint=True`.

### Tool descriptions

Neutral data-assembly language. Say "yield calculation" not "yield estimate". Say "comparable sales data" not "deal analysis". This prevents LLM consumers from expecting synthesis that isn't there.

## Prefab Component Gotchas

Verified working in claude.ai as of 2026-04-11:

| Gotcha | Correct | Wrong |
|--------|---------|-------|
| Tab trigger text | `Tab(title="Overview")` | `Tab(label="Overview")` |
| Chart data key | `ChartSeries(dataKey="price")` | `ChartSeries(data_key="price")` |
| Bar chart x-axis | `BarChart(xAxis="quarter")` | `BarChart(x_axis="quarter")` |
| Ring size | `Ring(size="lg")` | `Ring(size=3)` |
| Sparkline curve | `"linear"`, `"smooth"`, `"step"` | `"natural"` |
| Image in claude.ai | **Blocked** — CSP at iframe level | All approaches fail (data URI, proxy, direct) |

**Metric** has additional props not yet used: `delta` (change string like "+5.2%"), `trend` ("up"/"down"/"neutral"), `trendSentiment` ("positive"/"negative"/"neutral").

**Sparkline** also has: `variant` (color presets), `strokeWidth`, `mode` ("line"/"bar").

**BarChart** also has: `stacked`, `horizontal`, `barRadius`, `showLegend`, `showTooltip`, `showGrid`, `yAxisFormat` ("auto"/"compact").

**All verified components:** Column, Row, Grid, Heading, Text, Muted, Badge, Card, CardContent, Separator, Metric, Tabs, Tab, Table/TableHeader/TableHead/TableBody/TableRow/TableCell, BarChart, ChartSeries, Sparkline, Progress, Ring, Dot, Alert, ForEach, Input, Button, Form.

## Adding a New Tool / Dashboard

1. Create `_helper()` function in a new file under `dashboards/` — calls property_core, returns dict
2. Create `@mcp.tool()` data tool returning the helper's dict
3. Create `@mcp.tool(app=True)` dashboard returning `ToolResult(content=text, structured_content=view)`
4. Import the module in `server.py` `main()` so decorators register
5. Add test file `tests/test_app_{name}.py` — mock property_core calls, test both helper and dashboard

## Documentation References

Append `.md` to any doc page URL to get raw markdown (useful for LLM context).

| Resource | URL |
|----------|-----|
| Prefab full docs index | `https://prefab.prefect.io/docs/llms.txt` |
| Prefab component guide | `https://prefab.prefect.io/docs/components/{name}.md` |
| Prefab protocol/schema | `https://prefab.prefect.io/docs/protocol/{name}.md` |
| FastMCP full docs index | `https://gofastmcp.com/llms.txt` |
| FastMCP apps overview | `https://gofastmcp.com/apps/overview.md` |
| FastMCP Prefab guide | `https://gofastmcp.com/apps/prefab.md` |
| FastMCP patterns | `https://gofastmcp.com/apps/patterns.md` |
| FastMCP tools reference | `https://gofastmcp.com/servers/tools.md` |
| MCP Apps spec | `https://apps.extensions.modelcontextprotocol.io/api/documents/overview.html` |

To check a specific component's props: `https://prefab.prefect.io/docs/protocol/{component-name}.md`

## Deployment

- **Fly.io app:** `propertydata` in LHR (London)
- **Dockerfile.app:** Python 3.11 slim, `uv sync --frozen --no-dev --extra apps`
- **Health check:** `GET /health` every 30s (implemented in `server.py`)
- **Transport:** `MCP_TRANSPORT=http` with `stateless_http=True`
- **VM:** 512MB RAM, shared CPU, 1 machine minimum
- **Image proxy:** `/img?url=...` proxies Rightmove images through our domain (bypasses CSP for non-claude.ai hosts)

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `EPC_API_TOKEN` | For EPC | GOV.UK EPC Bearer token (England & Wales) |
| `EPC_API_EMAIL` / `EPC_API_KEY` | *(deprecated)* | Retired service; not a fallback |
| `COMPANIES_HOUSE_API_KEY` | For companies | Companies House API |
| `MCP_TRANSPORT` | No | `stdio` (default), `sse`, or `http` |
| `FASTMCP_HOST` | No | Bind host (default `0.0.0.0`) |
| `FASTMCP_PORT` | No | Bind port (default `8080`) |
