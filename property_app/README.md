# Property Data MCP App

MCP server with interactive Prefab UI dashboards, wrapping `property_core` for AI hosts. Deployed at https://propertydata.fly.dev/mcp

## Quick Start

```bash
# Local (stdio)
uv run --extra apps property-app

# HTTP (for remote hosts)
MCP_TRANSPORT=http uv run --extra apps property-app

# Dev mode with browser preview
uv run --extra apps fastmcp dev apps property_app/server.py:mcp
```

### Connect to Claude

Add to `.mcp.json`:

```json
{
  "mcpServers": {
    "propertydata": {
      "type": "http",
      "url": "https://propertydata.fly.dev/mcp"
    }
  }
}
```

Or local stdio:

```json
{
  "mcpServers": {
    "propertydata": {
      "command": "uv",
      "args": ["run", "--extra", "apps", "property-app"]
    }
  }
}
```

## Tools

All tools are `@mcp.tool()` — LLM-callable, returning structured data.

| Tool | Tags | What it does |
|------|------|-------------|
| `search_comps` | comps | Comparable sales — raw dict |
| `get_yield` | yield | Gross rental yield — raw dict |
| `get_rental` | rental | Rental market stats — raw dict |
| `stamp_duty` | calculator | SDLT calculator — Prefab inline view |
| `planning_search` | planning | Find planning portal for a council |
| `company_search` | companies | Companies House lookup |
| `epc_lookup` | epc | Energy Performance Certificate data |
| `rightmove_search` | listings | Browse Rightmove listings |
| `component_test` | test | Prefab component sampler (dev tool) |

### Dashboards (Prefab UI)

Pre-populated dashboards — data fetched server-side, rendered immediately. No empty forms or button clicks.

| Dashboard | Features |
|-----------|----------|
| `comps_dashboard` | Tabs (Overview/Transactions), stats grid, BarChart, Sparkline, Table, Badges |
| `yield_dashboard` | Yield metric with assessment Badge, sale/rental Cards |
| `rental_dashboard` | Rent stats, range Cards, market depth Dot, Alert for thin market |

## Architecture

```
property_app/
├── server.py              # FastMCP server — all tools via @mcp.tool()
├── tools.py               # Plain tools + stamp_duty (app=True) + component_test
├── formatting.py           # GBP, %, date helpers
└── dashboards/
    ├── comps.py            # search_comps + comps_dashboard (app=True)
    ├── yield_view.py       # get_yield + yield_dashboard (app=True)
    └── rental.py           # get_rental + rental_dashboard (app=True)
```

**Pattern:** Each dashboard file has a data tool (`@mcp.tool()` returning dict) and a visual dashboard (`@mcp.tool(app=True)` returning `ToolResult` with text + Prefab view). Both call the same `_helper()` function.

Built on FastMCP 3.2+ and Prefab UI 0.19+. All tools import directly from `property_core`.

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `EPC_API_EMAIL` | For EPC | EPC registry credentials |
| `EPC_API_KEY` | For EPC | EPC registry credentials |
| `COMPANIES_HOUSE_API_KEY` | For companies | Companies House API |
| `MCP_TRANSPORT` | No | `stdio` (default), `sse`, or `http` |
| `FASTMCP_HOST` | No | Bind host (default `0.0.0.0`) |
| `FASTMCP_PORT` | No | Bind port (default `8080`) |

## Deployment

Deployed on Fly.io as `propertydata`. To redeploy:

```bash
fly deploy --config fly.app.toml
```
