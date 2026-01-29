<script lang="ts">
import { onMount } from "svelte";
import {
  App,
  applyDocumentTheme,
  applyHostFonts,
  applyHostStyleVariables,
  type McpUiHostContext,
} from "@modelcontextprotocol/ext-apps";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import StatsPanel from "./StatsPanel.svelte";
import CompsTable from "./CompsTable.svelte";

interface Transaction {
  date: string;
  paon?: string;
  street?: string;
  postcode?: string;
  price: number;
  property_type?: string;
}

interface CompsData {
  median?: number;
  mean?: number;
  count?: number;
  percentile_25?: number;
  percentile_75?: number;
  transactions?: Transaction[];
}

// State using Svelte 5 runes
let app = $state<App | null>(null);
let hostContext = $state<McpUiHostContext | undefined>();
let loading = $state(true);
let loadingMessage = $state("Loading comparable sales...");
let error = $state<string | null>(null);
let data = $state<CompsData | null>(null);

// Apply host styles reactively when hostContext changes
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

function extractCompsData(result: CallToolResult): CompsData | null {
  if (result.structuredContent) {
    return result.structuredContent as CompsData;
  }
  const textContent = result.content?.find((c) => c.type === "text");
  if (textContent && "text" in textContent) {
    try {
      return JSON.parse(textContent.text) as CompsData;
    } catch {
      return null;
    }
  }
  return null;
}

onMount(async () => {
  const instance = new App({ name: "Property Comps Dashboard", version: "1.0.0" });

  instance.onteardown = async () => {
    console.info("[MCP App] Teardown");
    return {};
  };

  instance.ontoolinput = (params) => {
    console.info("[MCP App] Tool input:", params);
    loading = true;
    error = null;
    const postcode = params.arguments?.postcode;
    if (postcode) {
      loadingMessage = `Searching comparable sales for ${postcode}...`;
    }
  };

  instance.ontoolresult = (result) => {
    console.info("[MCP App] Tool result:", result);
    loading = false;
    const compsData = extractCompsData(result);
    if (compsData) {
      data = compsData;
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
  {:else if data}
    <StatsPanel {data} />
    <CompsTable transactions={data.transactions ?? []} />
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
