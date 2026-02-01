# MCP Apps SDK Reference

Quick reference for `@modelcontextprotocol/ext-apps` - building interactive UIs for MCP servers.

**Source**: Context7 + [Official Docs](https://modelcontextprotocol.github.io/ext-apps/api/)

---

## Pattern Index

Quick jump to patterns:

| Pattern | Section |
|---------|---------|
| Server-side registration | [Server-Side Registration](#server-side-registration) |
| Client-side handlers | [Client-Side App Class](#client-side-app-class) |
| Commit-based context sync | [Model Context Sync](#model-context-sync) |
| Snapshot + delta tracking | [Delta Tracking Pattern](#delta-tracking-pattern) |
| YAML frontmatter payload | [Payload Shape](#payload-shape-yaml-frontmatter) |
| Debounced apply | [Debounced Apply Pattern](#debounced-apply-pattern) |
| Visibility-aware pause | [Visibility-Based Resource Management](#visibility-based-resource-management) |
| Streaming partial input | [Streaming Partial Input](#streaming-partial-input-progressive-rendering) |
| Fullscreen toggle | [Fullscreen Toggle](#fullscreen-toggle) |
| Host quirks / compatibility | [Host Quirks](#host-quirks) |
| UI state model | [UI State Model](#ui-state-model) |

---

## Core Concept

MCP Apps = Tool + Resource linked via `_meta.ui.resourceUri`

```
Host calls tool → Server returns result → Host renders resource UI → UI receives result
```

### Bidirectional Communication

```
Model → Tool → UI     (tool results flow to UI)
UI → Model            (updateModelContext syncs state back)
UI → Chat             (sendMessage triggers model response)
```

**The Rule**: Use `updateModelContext` when the model's next action depends on UI state the model didn't produce itself.

- User can change things locally (sliders, selection, navigation) → model needs to know
- Model can infer from tool results alone → skip it

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

---

## Model Context Sync

Keep the model informed of UI state changes it didn't produce.

### When to Use

**DO update model context when:**
- User commits slider/control (mouseup, Apply button)
- Selection changes (scenario, property, tab)
- Assumption/constraint toggles
- Navigation (page, region, zoom)
- New data chunk arrives (transcript, stream)

**DON'T update when:**
- Every keystroke
- Every render cycle
- Timer-based polling
- Mouse movement

### Capability Guard

Always check before calling:

```typescript
const caps = app.getHostCapabilities();
if (!caps?.updateModelContext) return;
```

### Payload Shape (YAML Frontmatter)

Use structured markdown with YAML frontmatter for machine + human readability:

```typescript
const markdown = `---
tool: property_yield
scenario: what-if
postcode: NG1 1AA
---

## Changes
- purchase_price: £320,000 → £400,000
- gross_yield: 5.2% → 4.1%

## Current View
- median_rent: £1,200/mo
- data_quality: good
- assessment: below_average
`;

await app.updateModelContext({
  content: [{ type: "text", text: markdown }],
});
```

### Delta Tracking Pattern

Send what changed, not full state:

```typescript
interface ParamDelta {
  field: string;
  from: any;
  to: any;
}

function computeDeltas(prev: Record<string, any>, next: Record<string, any>): ParamDelta[] {
  return Object.keys(next)
    .filter(k => prev[k] !== next[k])
    .map(k => ({ field: k, from: prev[k], to: next[k] }));
}

function formatDeltas(deltas: ParamDelta[]): string {
  return deltas.map(d => `- ${d.field}: ${d.from} → ${d.to}`).join('\n');
}
```

### Real Example: transcript-server

```typescript
function updateModelContext() {
  const caps = app.getHostCapabilities();
  if (!caps?.updateModelContext) return;

  const text = getUnsentText();
  const frontmatter = [
    "---",
    "tool: transcribe",
    `status: ${isListening ? "listening" : "paused"}`,
    `unsent-entries: ${unsentCount}`,
    "---",
  ].join("\n");

  const markdown = text ? `${frontmatter}\n\n${text}` : frontmatter;

  app.updateModelContext({
    content: [{ type: "text", text: markdown }],
  }).catch(console.warn);
}
```

### Performance Budget

| Metric | Target |
|--------|--------|
| Perceived latency | < 150ms |
| Update frequency | On commit, not continuous |
| Payload size | Deltas preferred over dumps |

---

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

### Debounced Apply Pattern

For sliders and frequent inputs, update UI immediately but debounce server calls:

```typescript
let applyTimeout: number | null = null;
let previousParams: SearchParams | null = null;

function handleSliderChange(value: number) {
  // Optimistic UI update immediately
  updateDisplay(value);

  // Debounce server call + model context update
  if (applyTimeout) clearTimeout(applyTimeout);
  applyTimeout = window.setTimeout(() => {
    const newParams = buildParams(value);
    commitChange(newParams);
    syncModelContext(previousParams, newParams);
    previousParams = newParams;
  }, 150);
}

async function syncModelContext(prev: SearchParams | null, next: SearchParams) {
  const caps = app.getHostCapabilities();
  if (!caps?.updateModelContext) return;

  const deltas = prev ? computeDeltas(prev, next) : [];
  const markdown = formatContextPayload(next, deltas);

  await app.updateModelContext({
    content: [{ type: "text", text: markdown }],
  });
}
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

## UI State Model

Canonical state model for MCP Apps:

```typescript
interface AppState {
  // What the user is currently editing (not yet committed)
  inputsDraft: SearchParams;

  // What triggered the last tool call
  inputsCommitted: SearchParams;

  // Server response (structuredContent)
  resultSnapshot: ToolData;

  // Local UI state (tabs, filters, selection)
  viewState: ViewState;

  // Debug: last context payload sent
  lastContextPayload: string;
}
```

**Rules**:
- Only `inputsCommitted` generates deltas + context sync
- UI renders outputs from `resultSnapshot` only
- `inputsDraft` updates on every interaction, `inputsCommitted` on Apply
- `viewState` changes trigger context sync if they affect interpretation

---

## Payload Hygiene

### commit_id for ordering

Include monotonic commit ID in YAML frontmatter to help debug stale interpretation:

```yaml
---
tool: property_yield
commit_id: 3
scenario: what-if
view: yield
---
```

### structuredContent schema hygiene

For portability across versions:

- **Include inputs echo** — mirror the params in response for auditability
- **Include data quality** — `data_quality: "good" | "low" | "insufficient"`
- **Include source counts** — `sale_count`, `rental_count` for transparency
- **Keep stable keys** — don't rename fields across versions

Example:
```json
{
  "inputs": { "postcode": "NG11", "months": 24 },
  "median": 250000,
  "count": 15,
  "data_quality": "good",
  "thin_market": false
}
```

---

## Host Quirks

Documented host-specific behaviors from real-world testing.

### ChatGPT

ChatGPT uses the OpenAI Apps SDK bridge, NOT pure MCP notifications:

- **Skips `ontoolinput`**: Never fires. Infer params from result data.
- **Data delivery**: Via `window.openai.toolOutput` (sync) or `openai:set_globals` event (async), NOT MCP `ontoolresult` notification.
- **No serverTools proxy**: `callServerTool()` fails with "MCP proxy not enabled". Use `sendMessage()` fallback.
- **`updateModelContext` works**: Supported with capability guard.

**ChatGPT fallback pattern** (required for ChatGPT compatibility):

```typescript
// After app.connect(), check for OpenAI sync data
if (window.openai?.toolOutput) {
  // Data is available immediately (sync path)
  const result = normalizeToolOutput(window.openai.toolOutput);
  renderUI(result.structuredContent);
}

// Subscribe for late-arriving data (async path)
window.addEventListener("openai:set_globals", (event) => {
  const { globals } = event.detail;
  if (globals?.toolOutput) {
    const result = normalizeToolOutput(globals.toolOutput);
    renderUI(result.structuredContent);
  }
});

// Helper to normalize OpenAI format to MCP CallToolResult
function normalizeToolOutput(toolOutput: unknown): CallToolResult {
  if (typeof toolOutput === "object" && "structuredContent" in toolOutput) {
    return toolOutput as CallToolResult;
  }
  if (typeof toolOutput === "object") {
    return { content: [], structuredContent: toolOutput };
  }
  return { content: [{ type: "text", text: String(toolOutput) }] };
}
```

### Claude

- **Full MCP lifecycle**: Both `ontoolinput` and `ontoolresult` fire via MCP notifications.
- **Needs flat meta keys**: Use both `"ui": {"resourceUri": ...}` and `"ui/resourceUri": ...`
- **`updateModelContext` works**: Supported with capability guard.
- **`callServerTool` works**: Server tools proxy is enabled.

### Host Parity Matrix

| Capability              | ChatGPT | Claude |
|------------------------|---------|--------|
| `ontoolinput`          | ❌ skipped | ✅ |
| `ontoolresult` (MCP)   | ❌ via OpenAI bridge | ✅ |
| `window.openai.toolOutput` | ✅ | ❌ |
| `updateModelContext`   | ✅      | ✅     |
| `callServerTool` proxy | ❌      | ✅     |
| Flat meta keys         | ✅      | ✅ required |
| Nested meta keys       | ✅      | ❌      |
| `safeAreaInsets`       | ✅      | ✅     |

**Minimum manual test** (per host):
1. Baseline tool call renders UI with correct data
2. User commits param change via Apply
3. Model correctly references the delta in next response

### Defensive patterns

```typescript
// Handle missing ontoolinput (ChatGPT)
if (!currentParams && result.structuredContent) {
  currentParams = inferParamsFromResult(result.structuredContent);
}

// Handle missing serverTools proxy (ChatGPT)
try {
  await app.callServerTool(name, args);
} catch (e) {
  if (e.message.includes("proxy not enabled")) {
    await app.sendMessage({ role: "user", content: [...] });
  }
}

// Check for OpenAI environment
function isOpenAIEnvironment(): boolean {
  return typeof window !== "undefined" && "openai" in window;
}
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
8. **Missing model context sync** - User changes state but model doesn't know
9. **Dumping full state** - Send deltas, not entire app state on every update
10. **Updating too frequently** - Debounce, update on commit not every keystroke
11. **No capability guard** - Always check `getHostCapabilities()?.updateModelContext`

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
