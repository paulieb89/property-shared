/**
 * OpenAI Fallback Utility
 *
 * Bridges the gap between MCP Apps SDK (async notifications) and
 * OpenAI Apps SDK (sync window.openai properties).
 *
 * ChatGPT doesn't send MCP `ui/notifications/tool-result` for historical results.
 * Instead, it provides data via `window.openai.toolOutput` as a sync property.
 *
 * Use this after `app.connect()` to check for and process OpenAI sync data.
 */

import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** OpenAI globals available on window.openai */
export interface OpenAIGlobals {
  toolInput?: {
    name?: string;
    arguments?: Record<string, unknown>;
  };
  toolOutput?: unknown;
  toolResponseMetadata?: Record<string, unknown>;
  theme?: "light" | "dark";
  locale?: string;
  displayMode?: "inline" | "fullscreen" | "pip";
  widgetState?: unknown;
}

/** Result from checking OpenAI environment */
export interface OpenAIFallbackResult {
  isOpenAI: boolean;
  toolInput?: {
    name: string;
    arguments: Record<string, unknown>;
  };
  toolResult?: CallToolResult;
  theme?: "light" | "dark";
  locale?: string;
}

// ---------------------------------------------------------------------------
// Detection
// ---------------------------------------------------------------------------

/**
 * Check if running in an OpenAI/ChatGPT environment
 */
export function isOpenAIEnvironment(): boolean {
  return typeof window !== "undefined" && "openai" in window;
}

/**
 * Get the OpenAI globals object (if available)
 */
export function getOpenAIGlobals(): OpenAIGlobals | null {
  if (!isOpenAIEnvironment()) return null;
  return (window as { openai?: OpenAIGlobals }).openai ?? null;
}

// ---------------------------------------------------------------------------
// Data Extraction
// ---------------------------------------------------------------------------

/**
 * Convert OpenAI toolOutput to MCP CallToolResult format
 */
function normalizeToolOutput(toolOutput: unknown): CallToolResult {
  if (!toolOutput) {
    return { content: [] };
  }

  // Already in CallToolResult format
  if (
    typeof toolOutput === "object" &&
    toolOutput !== null &&
    "structuredContent" in toolOutput
  ) {
    return toolOutput as CallToolResult;
  }

  // Raw structured content - wrap it
  if (typeof toolOutput === "object" && toolOutput !== null) {
    return {
      content: [],
      structuredContent: toolOutput as Record<string, unknown>,
    };
  }

  // String or other primitive
  return {
    content: [{ type: "text", text: String(toolOutput) }],
  };
}

/**
 * Check for OpenAI sync data and return normalized result.
 * Call this after app.connect() to handle historical tool results in ChatGPT.
 *
 * @example
 * ```ts
 * await app.connect();
 *
 * const fallback = getOpenAIFallbackData();
 * if (fallback.isOpenAI && fallback.toolResult) {
 *   // Process as if ontoolresult fired
 *   handleToolResult(fallback.toolResult);
 * }
 * ```
 */
export function getOpenAIFallbackData(): OpenAIFallbackResult {
  const globals = getOpenAIGlobals();

  if (!globals) {
    return { isOpenAI: false };
  }

  // Debug: log all available keys on window.openai
  console.info("[OpenAI Fallback] window.openai keys:", Object.keys(globals));
  console.info("[OpenAI Fallback] window.openai:", globals);

  const result: OpenAIFallbackResult = {
    isOpenAI: true,
    theme: globals.theme,
    locale: globals.locale,
  };

  // Extract tool input
  if (globals.toolInput) {
    console.info("[OpenAI Fallback] toolInput:", globals.toolInput);
    result.toolInput = {
      name: globals.toolInput.name ?? "",
      arguments: globals.toolInput.arguments ?? {},
    };
  }

  // Extract and normalize tool output
  if (globals.toolOutput) {
    console.info("[OpenAI Fallback] toolOutput:", globals.toolOutput);
    result.toolResult = normalizeToolOutput(globals.toolOutput);
  } else {
    console.info("[OpenAI Fallback] toolOutput is:", globals.toolOutput, "(falsy)");
  }

  return result;
}

// ---------------------------------------------------------------------------
// Reactive Updates (for OpenAI's set_globals event)
// ---------------------------------------------------------------------------

type GlobalsChangeHandler = (globals: Partial<OpenAIGlobals>) => void;

/**
 * Subscribe to OpenAI globals changes (theme, displayMode, etc.)
 * Returns unsubscribe function.
 *
 * @example
 * ```ts
 * const unsub = onOpenAIGlobalsChange((globals) => {
 *   if (globals.theme) applyTheme(globals.theme);
 * });
 * // Later: unsub();
 * ```
 */
export function onOpenAIGlobalsChange(handler: GlobalsChangeHandler): () => void {
  if (typeof window === "undefined") return () => {};

  const listener = (event: Event) => {
    const detail = (event as CustomEvent<{ globals: Partial<OpenAIGlobals> }>).detail;
    if (detail?.globals) {
      handler(detail.globals);
    }
  };

  window.addEventListener("openai:set_globals", listener);
  return () => window.removeEventListener("openai:set_globals", listener);
}
