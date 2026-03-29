# Property MCP Server

MCP server wrapping `property_core` for AI hosts (Claude.ai, Claude Code, ChatGPT). Deployed at https://property-shared.fly.dev/mcp

## Quick Start

```bash
# Local (stdio transport — Claude Code, Claude Desktop)
uv run --extra mcp property-mcp

# Or install from PyPI
pip install property-shared[mcp]
property-mcp
```

### Connect to Claude Code

Add to `.mcp.json`:

```json
{
  "mcpServers": {
    "property": {
      "command": "uv",
      "args": ["run", "--extra", "mcp", "property-mcp"]
    }
  }
}
```

### Connect to Claude.ai (remote)

The server is deployed at `https://property-shared.fly.dev/mcp` using Streamable HTTP transport with `FASTMCP_STATELESS_HTTP=true` for Fly.io compatibility.

## Tools

| Tool | Description |
|------|-------------|
| `property_report` | Full data pull for a property (comps + EPC + yield + market). Needs street address + postcode. |
| `property_comps` | Comparable sales with EPC-enriched price/sqft. Accepts `property_type` filter. |
| `ppd_transactions` | Land Registry transaction search by postcode, address, date range, or price. |
| `property_yield` | Rental yield calculation (PPD sales + Rightmove rentals). Accepts `property_type` filter. |
| `rental_analysis` | Rental market stats with optional yield from purchase price. |
| `property_epc` | EPC certificate lookup. Needs street address for exact match. |
| `rightmove_search` | Rightmove listings for sale or rent. Accepts `sort_by`. |
| `rightmove_listing` | Full details for a specific Rightmove listing (URL or numeric ID). |
| `property_blocks` | Find buildings with multiple flat sales — block-buy opportunities. |
| `stamp_duty` | SDLT calculator with surcharges (additional property, FTB, non-resident). |
| `planning_search` | Find local council planning portal for a postcode. |
| `company_search` | Companies House lookup by name or company number. |

## Skills

Want structured reports instead of raw data? Claude skills that chain these tools into investment summaries and property reports are available at [bouch.dev/products](https://bouch.dev/products).

## Architecture

```
mcp_server/
├── server.py              # FastMCP server — 12 tools, all async
├── ui/                    # MCP App UI (Svelte, not yet wired)
│   └── property_dashboard.html
└── mcp-app/               # Svelte 5 source for MCP App (WIP)
    └── src/
```

The server is a thin consumer of `property_core`. Each tool:
1. Lazy-imports from `property_core`
2. Calls the service (wrapping sync calls with `anyio.to_thread.run_sync`)
3. Returns `ToolResult` with summary text + full JSON data

```python
@mcp.tool()
async def property_comps(postcode: str, ...) -> ToolResult:
    from property_core import PPDService

    result = await anyio.to_thread.run_sync(
        partial(PPDService().comps, postcode=postcode, ...)
    )
    data = result.model_dump(mode="json")
    summary = f"Found {result.count} comps for {postcode}"
    return ToolResult(content=_content(summary, data), structured_content=data)
```

### Response contract

- `content` — summary line + slimmed JSON (strips `raw`, `images`, `floorplans`, `epc_match`). All LLM hosts read this.
- `structured_content` — full data dict for programmatic consumers and MCP Apps.

### Interpretation

The MCP server populates `yield_assessment` ("strong"/"average"/"weak") and `data_quality` ("good"/"low"/"insufficient") from `property_core.interpret` helpers — fixed server-side thresholds, not LLM inference. EPC enrichment is on by default for `property_comps`.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `EPC_API_EMAIL` | For EPC tools | EPC Register API email |
| `EPC_API_KEY` | For EPC tools | EPC Register API key |
| `COMPANIES_HOUSE_API_KEY` | For company_search | Companies House API key |
| `RIGHTMOVE_DELAY_SECONDS` | No | Rate limit delay (default 0.6s) |
| `MCP_TRANSPORT` | No | `stdio` (default), `sse`, or `http` |
| `FASTMCP_STATELESS_HTTP` | For Fly.io | Set `true` for stateless HTTP transport |

## Deployment (Fly.io)

```bash
fly deploy
```

The Fly deployment mounts the MCP endpoint at `/mcp` on the FastAPI app via middleware (avoids Starlette 307 redirect on `/mcp` → `/mcp/`). Configuration in `fly.toml` sets `min_machines_running = 1` to avoid cold-start timeouts.

## Packaging

Currently bundled with `property-shared` on PyPI:

```bash
pip install property-shared[mcp]
```

The `[mcp]` extra pulls in `fastmcp>=3.0.0`. The server depends on `property_core` for all business logic but does not depend on `app` (FastAPI) or `property_cli` (Typer).

## References

- [MCP Apps SDK](https://github.com/modelcontextprotocol/ext-apps)
- [MCP_APPS_REFERENCE.md](./MCP_APPS_REFERENCE.md) — SDK API patterns
