/**
 * MCP App Lifecycle Manager
 *
 * Handles MCP connection and host compatibility for both ChatGPT and Claude.
 *
 * Key insight: ChatGPT and Claude handle tool results differently:
 * - Claude: Sends `ontoolinput` then `ontoolresult` via MCP notifications
 * - ChatGPT: Skips `ontoolinput`, provides data via `window.openai.toolOutput` or `set_globals` event
 *
 * This module abstracts those differences so your app just receives data.
 */

import {
  App,
  applyDocumentTheme,
  applyHostFonts,
  applyHostStyleVariables,
  type McpUiHostContext,
} from "@modelcontextprotocol/ext-apps";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Callbacks your app provides to handle lifecycle events */
export interface LifecycleCallbacks<TData> {
  /** Called when data is ready to render */
  onData: (data: TData, toolName: string, params: Record<string, unknown>) => void;
  /** Called when loading starts */
  onLoading: (message: string) => void;
  /** Called on error */
  onError: (error: string) => void;
  /** Called for debug logging (optional) */
  onDebug?: (message: string) => void;
  /** Extract your data type from tool result - YOU implement this */
  extractData: (result: CallToolResult) => TData | null;
  /** Infer params from data when ontoolinput was skipped - YOU implement this */
  inferParams: (data: TData) => Record<string, unknown>;
  /** Infer tool name from data when ontoolinput was skipped - YOU implement this */
  inferToolName: (data: TData) => string;
  /** Generate loading message from tool input */
  getLoadingMessage?: (toolName: string, params: Record<string, unknown>) => string;
}

/** Result from initializing the MCP app */
export interface McpAppInstance {
  app: App;
  getHostContext: () => McpUiHostContext | undefined;
}

// ---------------------------------------------------------------------------
// OpenAI/ChatGPT Fallback
// ---------------------------------------------------------------------------

interface OpenAIGlobals {
  toolInput?: { name?: string; arguments?: Record<string, unknown> };
  toolOutput?: unknown;
  theme?: "light" | "dark";
}

function isOpenAIEnvironment(): boolean {
  return typeof window !== "undefined" && "openai" in window;
}

function getOpenAIGlobals(): OpenAIGlobals | null {
  if (!isOpenAIEnvironment()) return null;
  return (window as { openai?: OpenAIGlobals }).openai ?? null;
}

// ---------------------------------------------------------------------------
// Main Lifecycle Function
// ---------------------------------------------------------------------------

/**
 * Initialize MCP App with host-compatible lifecycle handling.
 *
 * This function:
 * 1. Creates App instance and registers callbacks
 * 2. Connects to host
 * 3. Handles OpenAI fallback for ChatGPT
 * 4. Applies host theming
 *
 * @example
 * ```typescript
 * const { app } = await initMcpApp({
 *   onData: (data, toolName, params) => {
 *     myData = data;
 *     loading = false;
 *   },
 *   onLoading: (msg) => { loading = true; loadingMessage = msg; },
 *   onError: (e) => { error = e; },
 *   extractData: (result) => result.structuredContent as MyData,
 *   inferParams: (data) => ({ query: data.query }),
 *   inferToolName: (data) => "my_tool",
 * });
 * ```
 */
export async function initMcpApp<TData>(
  callbacks: LifecycleCallbacks<TData>,
  appInfo: { name: string; version: string } = { name: "MCP App", version: "1.0.0" }
): Promise<McpAppInstance> {
  const { onData, onLoading, onError, onDebug, extractData, inferParams, inferToolName, getLoadingMessage } = callbacks;
  const debug = onDebug ?? (() => {});

  let hostContext: McpUiHostContext | undefined;
  let currentToolName: string | null = null;
  let currentParams: Record<string, unknown> = {};
  let dataReceived = false;

  // Create App instance
  const app = new App(appInfo);

  // ---------------------------------------------------------------------------
  // MCP Callbacks (Claude path)
  // ---------------------------------------------------------------------------

  app.ontoolinput = (params) => {
    debug(`ontoolinput: ${params.name}`);
    currentToolName = params.name ?? null;
    currentParams = params.arguments ?? {};

    const msg = getLoadingMessage
      ? getLoadingMessage(currentToolName ?? "tool", currentParams)
      : `Loading ${currentToolName ?? "data"}...`;
    onLoading(msg);
  };

  app.ontoolresult = (result) => {
    debug(`ontoolresult: hasStructured=${!!result.structuredContent}`);

    if (dataReceived) {
      debug("Ignoring duplicate ontoolresult");
      return;
    }

    const data = extractData(result);
    if (!data) {
      debug("extractData returned null");
      return;
    }

    dataReceived = true;

    // If ontoolinput was skipped (ChatGPT), infer from data
    if (!currentToolName) {
      currentToolName = inferToolName(data);
      currentParams = inferParams(data);
      debug(`Inferred: tool=${currentToolName}`);
    }

    onData(data, currentToolName, currentParams);
  };

  app.ontoolcancelled = (params) => {
    debug(`ontoolcancelled: ${params.reason}`);
    onError(`Cancelled: ${params.reason}`);
  };

  app.onerror = (error) => {
    debug(`onerror: ${error}`);
    onError(String(error));
  };

  app.onhostcontextchanged = (ctx) => {
    hostContext = { ...hostContext, ...ctx };
    applyHostStyles(ctx);
  };

  // ---------------------------------------------------------------------------
  // Connect
  // ---------------------------------------------------------------------------

  debug("Connecting to host...");
  await app.connect();

  const hostInfo = app.getHostVersion();
  const caps = app.getHostCapabilities();
  debug(`Connected to ${hostInfo?.name ?? "unknown"} v${hostInfo?.version ?? "?"}`);
  debug(`Capabilities: serverTools=${!!caps?.serverTools}, updateModelContext=${!!caps?.updateModelContext}`);

  hostContext = app.getHostContext();
  if (hostContext) {
    applyHostStyles(hostContext);
  }

  // ---------------------------------------------------------------------------
  // OpenAI Fallback (ChatGPT path)
  // ---------------------------------------------------------------------------

  if (isOpenAIEnvironment()) {
    debug("OpenAI environment detected");
    const globals = getOpenAIGlobals();

    // Check for immediate toolOutput
    if (globals?.toolOutput && !dataReceived) {
      debug("Found immediate toolOutput");
      const result: CallToolResult = normalizeToolOutput(globals.toolOutput);
      const data = extractData(result);

      if (data) {
        dataReceived = true;
        const toolName = globals.toolInput?.name ?? inferToolName(data);
        const params = globals.toolInput?.arguments ?? inferParams(data);
        onData(data, toolName, params);
      }
    }

    // Subscribe to set_globals for late-arriving data
    if (!dataReceived) {
      debug("Subscribing to set_globals event");
      const handler = (event: Event) => {
        const detail = (event as CustomEvent<{ globals: Partial<OpenAIGlobals> }>).detail;
        if (!detail?.globals?.toolOutput || dataReceived) return;

        debug("toolOutput arrived via set_globals");
        const result: CallToolResult = normalizeToolOutput(detail.globals.toolOutput);
        const data = extractData(result);

        if (data) {
          dataReceived = true;
          const toolName = detail.globals.toolInput?.name ?? inferToolName(data);
          const params = detail.globals.toolInput?.arguments ?? inferParams(data);
          onData(data, toolName, params);
          window.removeEventListener("openai:set_globals", handler);
        }
      };
      window.addEventListener("openai:set_globals", handler);
    }
  }

  return {
    app,
    getHostContext: () => hostContext,
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function normalizeToolOutput(toolOutput: unknown): CallToolResult {
  if (!toolOutput) return { content: [] };

  // Already CallToolResult format
  if (typeof toolOutput === "object" && toolOutput !== null && "structuredContent" in toolOutput) {
    return toolOutput as CallToolResult;
  }

  // Raw object - wrap as structuredContent
  if (typeof toolOutput === "object" && toolOutput !== null) {
    return { content: [], structuredContent: toolOutput as Record<string, unknown> };
  }

  // Primitive - wrap as text
  return { content: [{ type: "text", text: String(toolOutput) }] };
}

function applyHostStyles(ctx: Partial<McpUiHostContext>) {
  if (ctx.theme) {
    applyDocumentTheme(ctx.theme);
  }
  if (ctx.styles?.variables) {
    applyHostStyleVariables(ctx.styles.variables);
  }
  if (ctx.styles?.css?.fonts) {
    applyHostFonts(ctx.styles.css.fonts);
  }
}
