# Property MCP Server

MCP server with interactive UI for UK property data tools. Deployed at https://property-shared.fly.dev/mcp

## Tools

| Tool | Description | UI |
|------|-------------|-----|
| `property_comps` | Comparable property sales with price statistics | Stats grid + transaction table |
| `property_yield` | Rental yield analysis (PPD + Rightmove) | Gauge + stats + quality badge |

## Architecture

```
mcp_server/
├── server.py              # FastMCP server with tools + resources
├── ui/
│   └── property_dashboard.html  # Vite-bundled Svelte UI (single file)
└── mcp-app/               # Svelte 5 source
    ├── src/
    │   ├── App.svelte     # MCP lifecycle + view routing
    │   ├── lib/
    │   │   ├── types.ts   # Shared interfaces + type guards
    │   │   └── formatters.ts  # Display formatting utilities
    │   ├── components/
    │   │   ├── StatCard.svelte      # Reusable stat display
    │   │   ├── DataBadge.svelte     # Quality/status badge
    │   │   ├── YieldGauge.svelte    # Circular yield gauge
    │   │   └── TransactionTable.svelte  # Property sales table
    │   └── views/
    │       ├── CompsView.svelte     # Comparable sales view
    │       └── YieldView.svelte     # Yield analysis view
    ├── mcp-app.html       # Entry HTML
    ├── vite.config.ts     # Vite + vite-plugin-singlefile
    └── package.json
```

## How It Works

1. **Server** registers tools with `_meta.ui.resourceUri` linking to UI resource
2. **Both tools** share the same unified UI (`property_dashboard.html`)
3. **UI detects data type** from `structuredContent`:
   - Has `gross_yield_pct` → Yield view
   - Has `transactions` → Comps view
4. **Host** (Claude.ai/ChatGPT) renders the UI in an iframe

## Development

```bash
cd mcp-app

# Install dependencies
npm install

# Dev mode (hot reload)
npm run dev

# Build single-file HTML
npm run build

# Copy to server
cp dist/mcp-app.html ../ui/property_dashboard.html
```

## Server Setup

The server uses FastMCP with stateless HTTP transport:

```python
mcp = FastMCP(
    "property-server",
    host="0.0.0.0",
    port=8080,
    stateless_http=True,
)
```

### Tool Registration Pattern

```python
WIDGET_URI = "ui://property/comps-dashboard"
WIDGET_MIME = "text/html;profile=mcp-app"

TOOL_UI_META = {
    "ui": {"resourceUri": WIDGET_URI},
    "ui/resourceUri": WIDGET_URI,  # flat key for Claude.ai compat
}

@mcp.resource(WIDGET_URI, mime_type=WIDGET_MIME)
def dashboard_resource() -> str:
    return load_html()

@mcp.tool(meta=TOOL_UI_META)
async def property_comps(...) -> types.CallToolResult:
    return types.CallToolResult(
        content=[...],  # Text fallback for non-UI hosts
        structuredContent=data,  # Structured data for UI
        _meta=TOOL_UI_META,
    )
```

## UI Component Pattern

Components use Svelte 5 runes (`$props`, `$derived`, `$state`):

```svelte
<script lang="ts">
import { formatPrice } from "../lib/formatters";

interface Props {
  label: string;
  value: string;
}

let { label, value }: Props = $props();
</script>

<div class="stat-card">
  <span class="label">{label}</span>
  <span class="value">{value}</span>
</div>
```

## Deployment

```bash
# From project root
fly deploy
```

## Testing

Test in Claude.ai or ChatGPT with MCP enabled:
- "Get comps for SW1A 1AA"
- "What's the rental yield for NG1?"

## References

- [MCP Apps SDK](https://github.com/modelcontextprotocol/ext-apps)
- [MCP_APPS_REFERENCE.md](./MCP_APPS_REFERENCE.md) - SDK API reference
