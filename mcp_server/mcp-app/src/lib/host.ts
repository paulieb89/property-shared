/**
 * MCP Host utilities - handle host quirks and defensive patterns.
 */

import type { App } from "@modelcontextprotocol/ext-apps";
import type { CompsData, YieldData, DataType, SearchParams, ToolEnvelope } from "./types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface HostCapabilities {
  updateModelContext?: boolean;
  callServerTool?: boolean;
  sendMessage?: boolean;
  requestDisplayMode?: boolean;
}

export interface CallServerToolResult {
  success: boolean;
  result?: ToolEnvelope;
  fallbackRequired?: boolean;
  error?: string;
}

// ---------------------------------------------------------------------------
// Capability detection
// ---------------------------------------------------------------------------

/**
 * Safely get host capabilities with proper typing.
 */
export function getHostCapabilities(app: App | null): HostCapabilities {
  if (!app) return {};
  try {
    const caps = app.getHostCapabilities?.();
    return (caps as HostCapabilities) ?? {};
  } catch {
    return {};
  }
}

/**
 * Check if host supports updateModelContext.
 */
export function canUpdateModelContext(app: App | null): boolean {
  return Boolean(getHostCapabilities(app).updateModelContext);
}

/**
 * Check if host supports callServerTool proxy.
 */
export function canCallServerTool(app: App | null): boolean {
  // Note: Even if capability exists, ChatGPT returns error at runtime
  return Boolean(getHostCapabilities(app).callServerTool);
}

// ---------------------------------------------------------------------------
// Safe server tool call
// ---------------------------------------------------------------------------

/**
 * Attempt to call server tool with fallback detection.
 * Returns result or indicates fallback is needed.
 */
export async function callServerToolSafe(
  app: App | null,
  name: string,
  args: Record<string, unknown>
): Promise<CallServerToolResult> {
  if (!app) {
    return { success: false, error: "No app instance" };
  }

  try {
    const result = await app.callServerTool({ name, arguments: args });
    return { success: true, result };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);

    // Detect ChatGPT's proxy not enabled error
    if (message.includes("proxy not enabled") || message.includes("MCP error -32000")) {
      return {
        success: false,
        fallbackRequired: true,
        error: "Host does not support callServerTool proxy",
      };
    }

    return { success: false, error: message };
  }
}

// ---------------------------------------------------------------------------
// Param inference (when ontoolinput is skipped)
// ---------------------------------------------------------------------------

/**
 * Infer search params from structuredContent when ontoolinput was skipped.
 * ChatGPT skips ontoolinput and goes straight to ontoolresult.
 */
export function inferParamsFromResult(
  data: CompsData | YieldData | null,
  dataType: DataType | null
): SearchParams {
  if (!data) {
    return {
      postcode: "",
      months: 24,
      radius: 0.5,
      search_level: "sector",
    };
  }

  // Try to extract postcode from data
  let postcode = "";

  if (dataType === "comps") {
    const comps = data as CompsData;
    postcode = comps.transactions?.[0]?.postcode ?? "";
  } else if (dataType === "yield") {
    const yieldData = data as YieldData;
    postcode = yieldData.postcode ?? "";
  }

  // Return defaults with inferred postcode
  return {
    postcode,
    months: 24,
    radius: 0.5,
    search_level: "sector",
  };
}

/**
 * Infer tool name from data type.
 */
export function inferToolName(dataType: DataType | null): string {
  if (dataType === "yield") return "property_yield";
  if (dataType === "comps") return "property_comps";
  return "";
}
