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
import { getOpenAIFallbackData, onOpenAIGlobalsChange, type OpenAIGlobals } from "./lib/openai-fallback";

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

// Debug state - start with init message to verify render
let debugLog = $state<string[]>(["init: waiting for messages..."]);

// Current tool and params for re-querying
let currentToolName = $state<string | null>(null);
let currentParams = $state<SearchParams | null>(null);

// ---------------------------------------------------------------------------
// Model Context Sync
// ---------------------------------------------------------------------------

type ScenarioMode = "baseline" | "what-if";

interface CommittedSnapshot {
  tool: string;
  mode: ScenarioMode;
  view: DataType;
  postcode: string;
  params: SearchParams;
  // Key outputs for delta tracking
  outputs: {
    median?: number;
    gross_yield_pct?: number;
    assessment?: string;
    data_quality?: string;
    count?: number;
  };
}

let lastCommitted = $state<CommittedSnapshot | null>(null);
let lastContextSignature = $state<string>("");

// Visibility tracking for resource management
let isVisible = $state(true);
let mainElement = $state<HTMLElement | null>(null);

/**
 * Check if host supports updateModelContext
 */
function canUpdateModelContext(appInstance: App | null): boolean {
  if (!appInstance) return false;
  const caps = appInstance.getHostCapabilities?.() as { updateModelContext?: unknown } | null;
  return Boolean(caps?.updateModelContext);
}

/**
 * Format currency for display
 */
function fmtGBP(n: number | undefined): string {
  if (n === undefined) return "—";
  return `£${Math.round(n).toLocaleString("en-GB")}`;
}

/**
 * Format percentage for display
 */
function fmtPct(x: number | undefined): string {
  if (x === undefined) return "—";
  return `${x.toFixed(1)}%`;
}

/**
 * Compute deltas between two snapshots
 */
function computeDeltas(prev: CommittedSnapshot | null, next: CommittedSnapshot): string[] {
  if (!prev) return [];

  const changes: string[] = [];

  // Params changes
  if (prev.params.months !== next.params.months) {
    changes.push(`- months: ${prev.params.months} → ${next.params.months}`);
  }
  if (prev.params.search_level !== next.params.search_level) {
    changes.push(`- search_level: ${prev.params.search_level} → ${next.params.search_level}`);
  }
  if (prev.params.radius !== next.params.radius) {
    changes.push(`- radius: ${prev.params.radius}mi → ${next.params.radius}mi`);
  }

  // Output changes
  if (prev.outputs.median !== next.outputs.median) {
    changes.push(`- median: ${fmtGBP(prev.outputs.median)} → ${fmtGBP(next.outputs.median)}`);
  }
  if (prev.outputs.gross_yield_pct !== next.outputs.gross_yield_pct) {
    changes.push(`- gross_yield: ${fmtPct(prev.outputs.gross_yield_pct)} → ${fmtPct(next.outputs.gross_yield_pct)}`);
  }
  if (prev.outputs.assessment !== next.outputs.assessment) {
    changes.push(`- assessment: ${prev.outputs.assessment} → ${next.outputs.assessment}`);
  }

  return changes;
}

/**
 * Build YAML frontmatter + markdown payload for model context
 */
function buildModelContextMarkdown(
  next: CommittedSnapshot,
  changes: string[]
): string {
  const frontmatter = [
    "---",
    `tool: ${next.tool}`,
    `scenario: ${next.mode}`,
    `postcode: ${next.postcode}`,
    `view: ${next.view}`,
    "---",
  ].join("\n");

  const changesBlock = changes.length > 0
    ? changes.join("\n")
    : "- (initial load)";

  const viewLines: string[] = [];

  if (next.view === "comps") {
    viewLines.push(`- median: ${fmtGBP(next.outputs.median)}`);
    viewLines.push(`- count: ${next.outputs.count ?? 0} transactions`);
    viewLines.push(`- search_level: ${next.params.search_level}`);
    viewLines.push(`- months: ${next.params.months}`);
  } else if (next.view === "yield") {
    viewLines.push(`- gross_yield: ${fmtPct(next.outputs.gross_yield_pct)}`);
    viewLines.push(`- assessment: ${next.outputs.assessment ?? "—"}`);
    viewLines.push(`- data_quality: ${next.outputs.data_quality ?? "—"}`);
    viewLines.push(`- median: ${fmtGBP(next.outputs.median)}`);
  }

  return [
    frontmatter,
    "",
    "## Changes",
    changesBlock,
    "",
    "## Current View",
    viewLines.join("\n"),
    "",
  ].join("\n");
}

/**
 * Push model context update (guarded + deduped)
 */
async function pushModelContext(
  appInstance: App | null,
  snapshot: CommittedSnapshot
): Promise<void> {
  if (!canUpdateModelContext(appInstance)) {
    console.info("[MCP App] Host does not support updateModelContext");
    return;
  }

  const changes = computeDeltas(lastCommitted, snapshot);
  const markdown = buildModelContextMarkdown(snapshot, changes);

  // Dedupe identical updates
  if (markdown === lastContextSignature) {
    console.info("[MCP App] Skipping duplicate context update");
    return;
  }

  console.info("[MCP App] Pushing model context:", markdown);

  try {
    await appInstance!.updateModelContext({
      content: [{ type: "text", text: markdown }],
    });
    lastContextSignature = markdown;
    lastCommitted = snapshot;
  } catch (err) {
    console.warn("[MCP App] Failed to update model context:", err);
  }
}

/**
 * Build snapshot from current state + data
 */
function buildSnapshot(
  toolName: string,
  params: SearchParams,
  toolData: ToolData,
  type: DataType,
  mode: ScenarioMode = "baseline"
): CommittedSnapshot {
  const outputs: CommittedSnapshot["outputs"] = {};

  if (type === "comps" && isCompsData(toolData)) {
    outputs.median = toolData.median;
    outputs.count = toolData.count;
  } else if (type === "yield" && isYieldData(toolData)) {
    outputs.gross_yield_pct = toolData.gross_yield_pct;
    outputs.assessment = toolData.yield_assessment;
    outputs.data_quality = toolData.data_quality;
    outputs.median = toolData.median_sale_price;
  }

  return {
    tool: toolName,
    mode,
    view: type,
    postcode: params.postcode ?? "",
    params,
    outputs,
  };
}

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
// Visibility-aware resource management
// ---------------------------------------------------------------------------

$effect(() => {
  if (!mainElement) return;

  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        isVisible = entry.isIntersecting;
        console.info("[MCP App] Visibility changed:", isVisible ? "visible" : "hidden");
      }
    },
    { threshold: 0.1 }
  );

  observer.observe(mainElement);

  return () => observer.disconnect();
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
  // Early debug: log ALL postMessage events from parent
  window.addEventListener("message", (event) => {
    console.info("[MCP App] Raw postMessage received:", {
      origin: event.origin,
      dataType: typeof event.data,
      dataKeys: event.data && typeof event.data === "object" ? Object.keys(event.data) : "N/A",
      method: event.data?.method || event.data?.jsonrpc ? event.data.method : "unknown",
    });
    if (event.data?.method) {
      debugLog = [...debugLog, `postMessage: ${event.data.method}`];
    }
  });

  const instance = new App({ name: "Property Dashboard", version: "1.0.0" });

  instance.onteardown = async () => {
    console.info("[MCP App] Teardown");
    return {};
  };

  instance.ontoolinput = (params) => {
    console.info("[MCP App] Tool input:", params);
    debugLog = [...debugLog, `ontoolinput: ${params.name || "?"}`];
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
    debugLog = [...debugLog, `ontoolresult: hasStructured=${!!result.structuredContent}`];
    loading = false;

    // Handle error results (e.g., timeout from host)
    if (result.isError || (typeof result === "string" && result.includes("error"))) {
      const errMsg = typeof result === "string" ? result :
        result.content?.[0]?.text || "Tool execution failed";
      debugLog = [...debugLog, `ERROR: ${errMsg}`];
      error = errMsg;
      return;
    }

    const extracted = extractToolData(result);
    debugLog = [...debugLog, `extracted: type=${extracted.type}, hasData=${!!extracted.data}`];

    if (extracted.data && extracted.type) {
      // If ontoolinput wasn't called (ChatGPT skips it), infer params from data
      if (!currentParams || !currentToolName) {
        debugLog = [...debugLog, "inferring params from result data"];
        const inferredPostcode =
          (extracted.data as CompsData).transactions?.[0]?.postcode ||
          (extracted.data as YieldData).postcode ||
          "";
        currentToolName = extracted.type === "yield" ? "property_yield" : "property_comps";
        currentParams = {
          postcode: inferredPostcode,
          months: 24,
          radius: 0.5,
          search_level: "sector",
        };
      }

      data = extracted.data;
      dataType = extracted.type;

      // Push initial baseline to model context
      const snapshot = buildSnapshot(
        currentToolName,
        currentParams,
        extracted.data,
        extracted.type,
        "baseline"
      );
      pushModelContext(instance, snapshot);
    } else {
      debugLog = [...debugLog, `SKIP: no data extracted`];
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
  const caps = instance.getHostCapabilities();
  const hostInfo = instance.getHostVersion();
  debugLog = [
    ...debugLog,
    `connected to ${hostInfo?.name ?? "unknown"} v${hostInfo?.version ?? "?"}`,
    `caps: serverTools=${!!caps?.serverTools}, updateModelContext=${!!caps?.updateModelContext}`,
  ];
  app = instance;
  hostContext = instance.getHostContext();

  // ---------------------------------------------------------------------------
  // OpenAI Fallback: ChatGPT provides sync properties instead of MCP notifications
  // ---------------------------------------------------------------------------
  const fallback = getOpenAIFallbackData();
  if (fallback.isOpenAI) {
    debugLog = [...debugLog, "OpenAI env detected"];

    // Process tool input (arguments)
    if (fallback.toolInput) {
      debugLog = [...debugLog, `toolInput: ${fallback.toolInput.name}`];
      const args = fallback.toolInput.arguments;
      currentToolName = fallback.toolInput.name;
      currentParams = {
        postcode: args.postcode as string | undefined,
        months: (args.months as number) ?? 24,
        radius: (args.radius as number) ?? 0.5,
        search_level: (args.search_level as string) ?? "sector",
        address: args.address as string | undefined,
      };
    }

    // Process tool result (output)
    if (fallback.toolResult) {
      debugLog = [...debugLog, "toolOutput found - processing"];
      loading = false;

      const extracted = extractToolData(fallback.toolResult);
      debugLog = [...debugLog, `extracted: type=${extracted.type}`];

      if (extracted.data && extracted.type) {
        // Infer params from result if toolInput wasn't available
        if (!currentParams || !currentToolName) {
          const inferredPostcode =
            (extracted.data as CompsData).transactions?.[0]?.postcode ||
            (extracted.data as YieldData).postcode || "";
          currentToolName = extracted.type === "yield" ? "property_yield" : "property_comps";
          currentParams = {
            postcode: inferredPostcode,
            months: 24,
            radius: 0.5,
            search_level: "sector",
          };
        }

        data = extracted.data;
        dataType = extracted.type;

        // Push baseline to model context
        const snapshot = buildSnapshot(currentToolName, currentParams, extracted.data, extracted.type, "baseline");
        pushModelContext(instance, snapshot);
      }
    } else {
      debugLog = [...debugLog, "No toolOutput - waiting for live result"];

      // Subscribe to globals changes for when toolOutput becomes available later
      const unsub = onOpenAIGlobalsChange((globals: Partial<OpenAIGlobals>) => {
        debugLog = [...debugLog, `set_globals: keys=${Object.keys(globals).join(",")}`];

        if (globals.toolOutput && loading) {
          debugLog = [...debugLog, "toolOutput arrived via set_globals!"];
          loading = false;

          // Normalize and process
          const toolResult = {
            content: [],
            structuredContent: typeof globals.toolOutput === "object" ? globals.toolOutput : undefined,
          };
          const extracted = extractToolData(toolResult as CallToolResult);

          if (extracted.data && extracted.type) {
            // Infer params if needed
            if (!currentParams || !currentToolName) {
              const inferredPostcode =
                (extracted.data as CompsData).transactions?.[0]?.postcode ||
                (extracted.data as YieldData).postcode || "";
              currentToolName = extracted.type === "yield" ? "property_yield" : "property_comps";
              currentParams = {
                postcode: inferredPostcode,
                months: 24,
                radius: 0.5,
                search_level: "sector",
              };
            }

            data = extracted.data;
            dataType = extracted.type;

            const snapshot = buildSnapshot(currentToolName, currentParams, extracted.data, extracted.type, "baseline");
            pushModelContext(instance, snapshot);
            unsub(); // Stop listening once we have data
          }
        }
      });
    }
  }
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
    if (extracted.data && extracted.type) {
      data = extracted.data;
      dataType = extracted.type;

      // Determine scenario mode: "what-if" if user changed params from initial
      const isWhatIf = lastCommitted !== null && (
        params.months !== lastCommitted.params.months ||
        params.search_level !== lastCommitted.params.search_level ||
        params.radius !== lastCommitted.params.radius
      );

      // Push updated context to model
      const snapshot = buildSnapshot(
        currentToolName,
        params,
        extracted.data,
        extracted.type,
        isWhatIf ? "what-if" : "baseline"
      );
      pushModelContext(app, snapshot);

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
  bind:this={mainElement}
  class="main"
  class:hidden={!isVisible}
  style:padding={hostContext?.safeAreaInsets && `${hostContext.safeAreaInsets.top}px ${hostContext.safeAreaInsets.right}px ${hostContext.safeAreaInsets.bottom}px ${hostContext.safeAreaInsets.left}px`}
>
  {#if loading}
    <div class="loading-state animate-fade-up">
      <div class="loading-spinner"></div>
      <div class="loading-text">{loadingMessage}</div>
      <div class="loading-dots">
        <span></span><span></span><span></span>
      </div>
      {#if debugLog.length > 0}
        <div class="debug-log">
          <div class="debug-title">Debug:</div>
          {#each debugLog as line}
            <div>{line}</div>
          {/each}
        </div>
      {/if}
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
      {#if debugLog.length > 0}
        <div class="debug-log">
          {#each debugLog as line}
            <div>{line}</div>
          {/each}
        </div>
      {/if}
    </div>
  {/if}
</main>

<style>
/* NOTE: External fonts blocked by MCP Apps CSP - using system fonts */

.main {
  width: 100%;
  max-width: 800px;
  margin: 0 auto;
  padding: 16px;
  box-sizing: border-box;
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
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

/* Visibility-aware: pause animations when offscreen */
.main.hidden .loading-spinner,
.main.hidden .loading-dots span {
  animation-play-state: paused;
}

/* Debug log */
.debug-log {
  margin-top: 1rem;
  padding: 0.5rem;
  background: #1a1a1a;
  border: 1px solid #333;
  font-family: var(--font-mono);
  font-size: 10px;
  text-align: left;
  max-height: 100px;
  overflow-y: auto;
}
.debug-log div {
  color: #0f0;
  margin: 2px 0;
}
</style>
