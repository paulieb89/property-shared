<script lang="ts">
/**
 * Main MCP App entry point.
 * Handles MCP lifecycle and routes to appropriate view based on data type.
 */
import { onMount } from "svelte";
import {
  App,
  applyDocumentTheme,
  applyHostFonts,
  applyHostStyleVariables,
  type McpUiHostContext,
} from "@modelcontextprotocol/ext-apps";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";

import type { ToolData, DataType, CompsData, YieldData } from "./lib/types";
import { isYieldData, isCompsData } from "./lib/types";
import CompsView from "./views/CompsView.svelte";
import YieldView from "./views/YieldView.svelte";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let app = $state<App | null>(null);
let hostContext = $state<McpUiHostContext | undefined>();
let loading = $state(true);
let loadingMessage = $state("Loading...");
let error = $state<string | null>(null);
let data = $state<ToolData | null>(null);
let dataType = $state<DataType | null>(null);

// ---------------------------------------------------------------------------
// Host styling
// ---------------------------------------------------------------------------

$effect(() => {
  if (hostContext?.theme) {
    applyDocumentTheme(hostContext.theme);
  }
  if (hostContext?.styles?.variables) {
    applyHostStyleVariables(hostContext.styles.variables);
  }
  if (hostContext?.styles?.css?.fonts) {
    applyHostFonts(hostContext.styles.css.fonts);
  }
});

// ---------------------------------------------------------------------------
// Data extraction
// ---------------------------------------------------------------------------

function extractToolData(result: CallToolResult): { data: ToolData | null; type: DataType | null } {
  let parsed: unknown = null;

  if (result.structuredContent) {
    parsed = result.structuredContent;
  } else {
    const textContent = result.content?.find((c) => c.type === "text");
    if (textContent && "text" in textContent) {
      try {
        parsed = JSON.parse(textContent.text);
      } catch {
        return { data: null, type: null };
      }
    }
  }

  if (!parsed) return { data: null, type: null };

  if (isYieldData(parsed)) {
    return { data: parsed, type: "yield" };
  }
  if (isCompsData(parsed)) {
    return { data: parsed, type: "comps" };
  }

  // Fallback: assume comps if has median/mean
  if (typeof parsed === "object" && parsed !== null && ("median" in parsed || "mean" in parsed)) {
    return { data: parsed as CompsData, type: "comps" };
  }

  return { data: null, type: null };
}

// ---------------------------------------------------------------------------
// MCP Lifecycle
// ---------------------------------------------------------------------------

onMount(async () => {
  const instance = new App({ name: "Property Dashboard", version: "1.0.0" });

  instance.onteardown = async () => {
    console.info("[MCP App] Teardown");
    return {};
  };

  instance.ontoolinput = (params) => {
    console.info("[MCP App] Tool input:", params);
    loading = true;
    error = null;

    const postcode = params.arguments?.postcode;
    const toolName = params.name || "";

    // Detect tool type from name for loading message
    if (toolName.includes("yield")) {
      loadingMessage = postcode ? `Calculating yield for ${postcode}...` : "Calculating rental yield...";
    } else {
      loadingMessage = postcode ? `Searching comparable sales for ${postcode}...` : "Loading comparable sales...";
    }
  };

  instance.ontoolresult = (result) => {
    console.info("[MCP App] Tool result:", result);
    loading = false;
    const extracted = extractToolData(result);
    if (extracted.data) {
      data = extracted.data;
      dataType = extracted.type;
    }
  };

  instance.ontoolcancelled = (params) => {
    console.info("[MCP App] Tool cancelled:", params.reason);
    loading = false;
    error = `Cancelled: ${params.reason}`;
  };

  instance.onerror = (err) => {
    console.error("[MCP App] Error:", err);
    loading = false;
    error = String(err);
  };

  instance.onhostcontextchanged = (params) => {
    hostContext = { ...hostContext, ...params };
  };

  await instance.connect();
  app = instance;
  hostContext = instance.getHostContext();
});
</script>

<main
  class="main"
  style:padding={hostContext?.safeAreaInsets && `${hostContext.safeAreaInsets.top}px ${hostContext.safeAreaInsets.right}px ${hostContext.safeAreaInsets.bottom}px ${hostContext.safeAreaInsets.left}px`}
>
  {#if loading}
    <div class="loading">{loadingMessage}</div>
  {:else if error}
    <div class="error">{error}</div>
  {:else if data && dataType === "yield"}
    <YieldView data={data as YieldData} />
  {:else if data && dataType === "comps"}
    <CompsView data={data as CompsData} />
  {:else}
    <div class="loading">No data available</div>
  {/if}
</main>

<style>
.main {
  width: 100%;
  max-width: 800px;
  margin: 0 auto;
}

.loading {
  text-align: center;
  padding: 40px;
  color: var(--color-text-secondary, #666);
}

.error {
  text-align: center;
  padding: 40px;
  color: var(--color-background-danger, #dc2626);
  background: var(--color-background-danger-subtle, #fef2f2);
  border-radius: var(--border-radius-md, 8px);
}
</style>
