# MCP Apps SDK Reference

Quick reference for `@modelcontextprotocol/ext-apps` - building interactive UIs for MCP servers.

**Source**: Context7 + [Official Docs](https://modelcontextprotocol.github.io/ext-apps/api/)

---

## Core Concept

MCP Apps = Tool + Resource linked via `_meta.ui.resourceUri`

```
Host calls tool → Server returns result → Host renders resource UI → UI receives result
```

---

## Server-Side Registration

### registerAppTool

```typescript
import { registerAppTool, registerAppResource, RESOURCE_MIME_TYPE } from "@modelcontextprotocol/ext-apps/server";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

const server = new McpServer({ name: "Weather Server", version: "1.0.0" });
const resourceUri = "ui://weather/dashboard.html";

// Register tool with UI metadata
registerAppTool(server, "get-weather", {
  title: "Get Weather",
  description: "Get current weather for a location",
  inputSchema: { location: z.string() },
  _meta: {
    ui: {
      resourceUri,
      visibility: ["model", "app"], // visible to both model and UI
    },
  },
}, async (args) => {
  const weather = await fetchWeather(args.location);
  return {
    content: [{ type: "text", text: `Weather: ${weather.temp}°F` }],
    structuredContent: { temp: weather.temp, conditions: weather.conditions },
  };
});

// Register UI resource
registerAppResource(
  server,
  "Weather Dashboard",
  resourceUri,
  { description: "Weather visualization UI" },
  async () => ({
    contents: [{
      uri: resourceUri,
      mimeType: RESOURCE_MIME_TYPE, // "text/html;profile=mcp-app"
      text: getWidgetHtml(),
    }],
  }),
);
```

### Tool Visibility

```typescript
// Default: visible to both model and app
_meta: { ui: { resourceUri, visibility: ["model", "app"] } }

// UI-only (hidden from model) - for refresh buttons, form submissions
_meta: { ui: { resourceUri, visibility: ["app"] } }

// Model-only (app cannot call)
_meta: { ui: { resourceUri, visibility: ["model"] } }
```

### FastMCP (Python) Pattern

```python
from mcp.server.fastmcp import FastMCP
import mcp.types as types

WIDGET_URI = "ui://property/comps-dashboard"
WIDGET_MIME = "text/html;profile=mcp-app"

# Both nested and flat keys for host compatibility
TOOL_UI_META = {
    "ui": {"resourceUri": WIDGET_URI},
    "ui/resourceUri": WIDGET_URI,  # flat key for Claude.ai
}

mcp = FastMCP("my-server")

@mcp.resource(WIDGET_URI, name="Dashboard", mime_type=WIDGET_MIME)
def dashboard_resource() -> str:
    return load_html()

@mcp.tool(meta=TOOL_UI_META)
def my_tool(arg: str) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text="Result")],
        structuredContent={"data": "value"},
        _meta=TOOL_UI_META,
    )
```

---

## Client-Side App Class

### Initialization

```typescript
import {
  App,
  applyDocumentTheme,
  applyHostStyleVariables,
  applyHostFonts,
} from "@modelcontextprotocol/ext-apps";

// 1. Create app instance
const app = new App(
  { name: "My App", version: "1.0.0" },
  { tools: { listChanged: true } }, // capabilities
  { autoResize: true } // options
);

// 2. Register handlers BEFORE connecting
app.ontoolinput = (params) => {
  console.log("Tool arguments:", params.arguments);
};

app.ontoolresult = (result) => {
  console.log("Tool result:", result.structuredContent);
  updateUI(result.structuredContent);
};

app.ontoolinputpartial = (params) => {
  // Streaming partial - healed JSON, always valid
  console.log("Partial args:", params.arguments);
};

app.ontoolcancelled = (params) => {
  console.log("Tool cancelled:", params.reason);
};

app.onhostcontextchanged = (ctx) => {
  if (ctx.theme) applyDocumentTheme(ctx.theme);
  if (ctx.styles?.variables) applyHostStyleVariables(ctx.styles.variables);
  if (ctx.styles?.css?.fonts) applyHostFonts(ctx.styles.css.fonts);
  if (ctx.safeAreaInsets) {
    const { top, right, bottom, left } = ctx.safeAreaInsets;
    document.body.style.padding = `${top}px ${right}px ${bottom}px ${left}px`;
  }
};

app.onteardown = async () => {
  await saveState();
  return {};
};

// 3. Connect to host
await app.connect();

// Apply initial context
const context = app.getHostContext();
if (context?.theme) applyDocumentTheme(context.theme);
```

### App Methods

```typescript
// Call a server tool from the UI
const result = await app.callServerTool("refresh-data", { id: "123" });

// Send message to chat
await app.sendMessage({
  role: "user",
  content: [{ type: "text", text: "User clicked button" }],
});

// Update model context (non-disruptive)
await app.updateModelContext({
  content: [{ type: "text", text: "User selected item X" }],
  structuredContent: { selectedItem: "X" },
});

// Request fullscreen
const result = await app.requestDisplayMode({ mode: "fullscreen" });

// Send debug log to host
await app.sendLog({ level: "info", data: "Debug message" });

// Get current host context
const ctx = app.getHostContext();
```

### React Hook

```typescript
import { useApp, useHostStyles } from "@modelcontextprotocol/ext-apps/react";

function MyApp() {
  const { app, toolInput, toolResult, hostContext } = useApp({
    appInfo: { name: "My App", version: "1.0.0" },
    capabilities: { tools: { listChanged: true } },
    onAppCreated: (app) => console.log("Connected"),
  });

  useHostStyles(app); // Injects CSS variables to document

  return <div>{toolResult?.structuredContent?.data}</div>;
}
```

---

## Host Context Interface

```typescript
interface HostContext {
  theme?: "light" | "dark";
  styles?: {
    variables?: Record<McpUiStyleVariableKey, string>;
    css?: { fonts?: string };
  };
  displayMode?: "inline" | "fullscreen" | "pip";
  availableDisplayModes?: string[];
  containerDimensions?: { width?: number; maxWidth?: number; height?: number; maxHeight?: number };
  locale?: string;  // BCP 47, e.g., "en-US"
  timeZone?: string; // IANA, e.g., "America/New_York"
  userAgent?: string;
  platform?: "web" | "desktop" | "mobile";
  deviceCapabilities?: { touch?: boolean; hover?: boolean };
  safeAreaInsets?: { top: number; right: number; bottom: number; left: number };
  toolInfo?: { id?: RequestId; tool: Tool };
}
```

---

## CSS Variables

After calling `applyHostStyleVariables()`, use in CSS:

```css
.container {
  background: var(--color-background-primary);
  color: var(--color-text-primary);
  font-family: var(--font-sans);
  border-radius: var(--border-radius-md);
}

.code {
  font-family: var(--font-mono);
  font-size: var(--font-text-sm-size);
  line-height: var(--font-text-sm-line-height);
}
```

### Available Variables

| Category | Variables |
|----------|-----------|
| **Background** | `--color-background-primary`, `-secondary`, `-tertiary`, `-inverse`, `-ghost`, `-info`, `-danger`, `-success`, `-warning`, `-disabled` |
| **Text** | `--color-text-primary`, `-secondary`, `-tertiary`, `-inverse`, `-info`, `-danger`, `-success`, `-warning`, `-disabled`, `-ghost` |
| **Border** | `--color-border-primary`, `-secondary`, `-tertiary`, `-inverse`, `-ghost`, `-info`, `-danger`, `-success`, `-warning`, `-disabled` |
| **Ring** | `--color-ring-primary`, `-secondary`, `-inverse`, `-info`, `-danger`, `-success`, `-warning` |
| **Fonts** | `--font-sans`, `--font-mono` |
| **Weight** | `--font-weight-normal`, `-medium`, `-semibold`, `-bold` |
| **Text Size** | `--font-text-xs-size`, `-sm-size`, `-md-size`, `-lg-size` |
| **Heading Size** | `--font-heading-xs-size` through `--font-heading-3xl-size` |
| **Line Height** | `--font-text-*-line-height`, `--font-heading-*-line-height` |
| **Border Radius** | `--border-radius-xs`, `-sm`, `-md`, `-lg`, `-xl`, `-full` |
| **Border Width** | `--border-width-regular` |
| **Shadows** | `--shadow-hairline`, `-sm`, `-md`, `-lg` |

---

## Common Patterns

### Visibility-Based Resource Management

```typescript
const observer = new IntersectionObserver((entries) => {
  entries.forEach((entry) => {
    if (entry.isIntersecting) {
      animation.play(); // or startPolling()
    } else {
      animation.pause(); // or stopPolling()
    }
  });
});
observer.observe(document.querySelector(".main"));
```

### Fullscreen Toggle

```typescript
let currentMode = "inline";

app.onhostcontextchanged = (ctx) => {
  if (ctx.displayMode) {
    currentMode = ctx.displayMode;
    container.classList.toggle("fullscreen", currentMode === "fullscreen");
  }
};

async function toggleFullscreen() {
  const newMode = currentMode === "fullscreen" ? "inline" : "fullscreen";
  const result = await app.requestDisplayMode({ mode: newMode });
  currentMode = result.mode;
}
```

### Streaming Partial Input (Progressive Rendering)

```typescript
app.ontoolinputpartial = (params) => {
  // Healed JSON - always valid, fields appear as generated
  codePreview.textContent = params.arguments?.code ?? "";
  codePreview.style.display = "block";
  canvas.style.display = "none";
};

app.ontoolinput = (params) => {
  // Final complete input
  codePreview.style.display = "none";
  canvas.style.display = "block";
  render(params.arguments);
};
```

---

## Build Configuration

**vite.config.ts** - Must use single-file bundling:

```typescript
import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

export default defineConfig({
  plugins: [viteSingleFile()],
  build: {
    outDir: "dist",
    rollupOptions: {
      input: "src/mcp-app.html",
    },
  },
});
```

---

## Common Mistakes

1. **Handlers after connect()** - Register ALL handlers BEFORE `app.connect()`
2. **Missing single-file bundling** - Must use `vite-plugin-singlefile`
3. **Forgetting resource registration** - Both tool AND resource must be registered
4. **Missing resourceUri link** - Tool must have `_meta.ui.resourceUri`
5. **Ignoring safe area insets** - Always handle `ctx.safeAreaInsets`
6. **No text fallback** - Always provide `content` array for non-UI hosts
7. **Hardcoded styles** - Use host CSS variables for theme integration

---

## Testing

```bash
# Clone SDK examples
git clone --branch "v$(npm view @modelcontextprotocol/ext-apps version)" \
  --depth 1 https://github.com/modelcontextprotocol/ext-apps.git /tmp/mcp-ext-apps

# Run basic-host for local testing
cd /tmp/mcp-ext-apps/examples/basic-host
npm install
SERVERS='["http://localhost:3001/mcp"]' npm run start
# Open http://localhost:8080
```
