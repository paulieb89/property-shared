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

All tools are LLM-callable. Dashboards add interactive Prefab UI on top.

| Tool | Type | What it does |
|------|------|-------------|
| `search_comps` | tool (model+app) | Comparable sales for a UK postcode |
| `get_yield` | tool (model+app) | Gross rental yield analysis |
| `get_rental` | tool (model+app) | Rental market stats |
| `stamp_duty` | tool (Prefab inline) | SDLT calculator with band breakdown |
| `planning_search` | tool | Find planning portal for a council |
| `company_search` | tool | Companies House lookup |
| `epc_lookup` | tool | Energy Performance Certificate data |
| `rightmove_search` | tool | Browse Rightmove listings |

### Interactive Dashboards

These open a Prefab UI in hosts that support MCP Apps (Claude, ChatGPT):

| Dashboard | Opens via | Features |
|-----------|----------|----------|
| `comps_dashboard` | LLM calls it | Search form, stats grid, transaction table |
| `yield_dashboard` | LLM calls it | Yield metrics, sale/rental breakdown |
| `rental_dashboard` | LLM calls it | Rental stats, market depth, optional yield |

## Architecture

```
property_app/
├── server.py              # FastMCP + FastMCPApp wiring
├── tools.py               # Plain @mcp.tool() wrappers
├── formatting.py           # GBP, %, date helpers
└── dashboards/
    ├── comps.py            # @app.tool(model=True) + @app.ui()
    ├── yield_view.py       # @app.tool(model=True) + @app.ui()
    └── rental.py           # @app.tool(model=True) + @app.ui()
```

Built on FastMCP 3.2+ and Prefab UI. All tools import directly from `property_core`.

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
