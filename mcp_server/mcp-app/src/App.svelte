<script lang="ts">
/**
 * Main MCP App entry point.
 * Handles MCP lifecycle and routes to appropriate view based on data type.
 * BOUCH Design System - Professional brutalist aesthetic
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

import "./lib/bouch-system.css";
import type { ToolData, DataType, CompsData, YieldData } from "./lib/types";
import { isYieldData, isCompsData } from "./lib/types";
import CompsView from "./views/CompsView.svelte";
import YieldView from "./views/YieldView.svelte";

import type { SearchParams } from "./components/SearchControls.svelte";

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

// Current tool and params for re-querying
let currentToolName = $state<string | null>(null);
let currentParams = $state<SearchParams | null>(null);

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

    const args = params.arguments || {};
    const toolName = params.name || "";

    // Store tool name and params for re-querying
    currentToolName = toolName;
    currentParams = {
      postcode: args.postcode,
      months: args.months ?? 24,
      radius: args.radius ?? 0.5,
      search_level: args.search_level ?? "sector",
      address: args.address,
    };

    const postcode = args.postcode;

    // Detect tool type from name for loading message
    if (toolName.includes("yield")) {
      loadingMessage = postcode ? `Calculating yield for ${postcode}` : "Calculating rental yield";
    } else {
      loadingMessage = postcode ? `Searching comps for ${postcode}` : "Loading comparable sales";
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

// ---------------------------------------------------------------------------
// Re-query handler for SearchControls
// ---------------------------------------------------------------------------

async function handleApply(params: SearchParams) {
  if (!app || !currentToolName) return;

  console.info("[MCP App] Re-querying with params:", params);
  loading = true;
  error = null;

  const postcode = params.postcode;
  if (currentToolName.includes("yield")) {
    loadingMessage = postcode ? `Calculating yield for ${postcode}` : "Calculating rental yield";
  } else {
    loadingMessage = postcode ? `Searching comps for ${postcode}` : "Loading comparable sales";
  }

  try {
    const result = await app.callServerTool({
      name: currentToolName,
      arguments: params,
    });

    console.info("[MCP App] Re-query result:", result);
    loading = false;

    const extracted = extractToolData(result);
    if (extracted.data) {
      data = extracted.data;
      dataType = extracted.type;
      // Update stored params
      currentParams = params;
    }
  } catch (err) {
    console.error("[MCP App] Re-query error:", err);
    loading = false;
    error = String(err);
  }
}
</script>

<main
  class="main"
  style:padding={hostContext?.safeAreaInsets && `${hostContext.safeAreaInsets.top}px ${hostContext.safeAreaInsets.right}px ${hostContext.safeAreaInsets.bottom}px ${hostContext.safeAreaInsets.left}px`}
>
  {#if loading}
    <div class="loading-state animate-fade-up">
      <div class="loading-spinner"></div>
      <div class="loading-text">{loadingMessage}</div>
      <div class="loading-dots">
        <span></span><span></span><span></span>
      </div>
    </div>
  {:else if error}
    <div class="error-state animate-fade-up">
      <div class="error-icon">!</div>
      <div class="error-title">Error</div>
      <div class="error-message">{error}</div>
      <button class="btn btn-secondary" onclick={() => error = null}>
        Dismiss
      </button>
    </div>
  {:else if data && dataType === "yield"}
    <div class="animate-fade-up">
      <YieldView
        data={data as YieldData}
        params={currentParams}
        toolName={currentToolName ?? "property_yield"}
        {loading}
        onApply={handleApply}
      />
    </div>
  {:else if data && dataType === "comps"}
    <div class="animate-fade-up">
      <CompsView
        data={data as CompsData}
        params={currentParams}
        toolName={currentToolName ?? "property_comps"}
        {loading}
        onApply={handleApply}
      />
    </div>
  {:else}
    <div class="empty-state animate-fade-up">
      <div class="empty-icon">P</div>
      <div class="empty-title">Property Dashboard</div>
      <div class="empty-text">Waiting for data...</div>
    </div>
  {/if}
</main>

<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Bebas+Neue&display=swap');

.main {
  width: 100%;
  max-width: 800px;
  margin: 0 auto;
  font-family: 'Space Mono', ui-monospace, monospace;
}

/* Loading State */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 24px;
  text-align: center;
}

.loading-spinner {
  width: 48px;
  height: 48px;
  border: 3px solid var(--bouch-gray, #e8e6dc);
  border-top-color: var(--bouch-orange, #D97757);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-bottom: 24px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading-text {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 3px;
  color: var(--bouch-charcoal, #1C1917);
  margin-bottom: 12px;
}

.loading-dots {
  display: flex;
  gap: 6px;
}

.loading-dots span {
  width: 8px;
  height: 8px;
  background: var(--bouch-orange, #D97757);
  animation: bounce 1.4s ease-in-out infinite;
}

.loading-dots span:nth-child(2) {
  animation-delay: 0.2s;
}

.loading-dots span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes bounce {
  0%, 80%, 100% { transform: translateY(0); }
  40% { transform: translateY(-8px); }
}

/* Error State */
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px 24px;
  text-align: center;
  background: var(--bouch-charcoal, #1C1917);
  border: 2px solid var(--bouch-orange, #D97757);
}

.error-icon {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bouch-orange, #D97757);
  color: var(--bouch-charcoal, #1C1917);
  font-family: 'Bebas Neue', sans-serif;
  font-size: 32px;
  margin-bottom: 16px;
}

.error-title {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 3px;
  color: var(--bouch-orange, #D97757);
  margin-bottom: 12px;
}

.error-message {
  font-size: 13px;
  color: var(--bouch-cream, #FAF9F5);
  line-height: 1.6;
  margin-bottom: 24px;
  max-width: 400px;
}

.btn {
  padding: 12px 24px;
  font-family: 'Space Mono', monospace;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s;
  text-transform: uppercase;
  letter-spacing: 2px;
  border: 2px solid transparent;
}

.btn-secondary {
  background: transparent;
  color: var(--bouch-cream, #FAF9F5);
  border-color: var(--bouch-cream, #FAF9F5);
}

.btn-secondary:hover {
  background: rgba(250, 249, 245, 0.1);
}

/* Empty State */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 60px 24px;
  text-align: center;
}

.empty-icon {
  width: 64px;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bouch-charcoal, #1C1917);
  color: var(--bouch-orange, #D97757);
  font-family: 'Bebas Neue', sans-serif;
  font-size: 36px;
  margin-bottom: 16px;
}

.empty-title {
  font-family: 'Bebas Neue', sans-serif;
  font-size: 24px;
  letter-spacing: 3px;
  color: var(--bouch-charcoal, #1C1917);
  margin-bottom: 8px;
}

.empty-text {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 2px;
  color: var(--bouch-mid-gray, #b0aea5);
}

/* Animation */
.animate-fade-up {
  animation: fadeUp 0.3s ease-out;
}

@keyframes fadeUp {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
