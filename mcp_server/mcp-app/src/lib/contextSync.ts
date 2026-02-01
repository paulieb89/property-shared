/**
 * Model Context Sync utilities - payload building, delta tracking, deduplication.
 */

import type { App } from "@modelcontextprotocol/ext-apps";
import { canUpdateModelContext } from "./host";
import type { DataType, SearchParams } from "./types";

// Re-export for backwards compatibility
export type { SearchParams };

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ScenarioMode = "baseline" | "what-if";

export interface OutputSnapshot {
  median?: number;
  gross_yield_pct?: number;
  assessment?: string;
  data_quality?: string;
  count?: number;
}

export interface CommittedSnapshot {
  tool: string;
  mode: ScenarioMode;
  view: DataType;
  postcode: string;
  params: SearchParams;
  outputs: OutputSnapshot;
  commitId: number;
}

export interface ContextSyncState {
  lastCommitted: CommittedSnapshot | null;
  lastSignature: string;
  commitCounter: number;
}

export interface PushContextResult {
  sent: boolean;
  payload?: string;
  newState: ContextSyncState;
  reason?: "no_capability" | "duplicate" | "sent" | "error";
}

// ---------------------------------------------------------------------------
// Formatters
// ---------------------------------------------------------------------------

export function fmtGBP(n: number | undefined): string {
  if (n === undefined) return "—";
  return `£${Math.round(n).toLocaleString("en-GB")}`;
}

export function fmtPct(x: number | undefined): string {
  if (x === undefined) return "—";
  return `${x.toFixed(1)}%`;
}

// ---------------------------------------------------------------------------
// Delta computation
// ---------------------------------------------------------------------------

export interface DeltaConfig {
  paramFields: (keyof SearchParams)[];
  outputFields: (keyof OutputSnapshot)[];
  formatters?: Partial<Record<string, (v: unknown) => string>>;
}

const defaultConfig: DeltaConfig = {
  paramFields: ["months", "search_level", "radius"],
  outputFields: ["median", "gross_yield_pct", "assessment"],
  formatters: {
    median: (v) => fmtGBP(v as number),
    gross_yield_pct: (v) => fmtPct(v as number),
    radius: (v) => `${v}mi`,
  },
};

/**
 * Compute deltas between two snapshots.
 */
export function computeDeltas(
  prev: CommittedSnapshot | null,
  next: CommittedSnapshot,
  config: DeltaConfig = defaultConfig
): string[] {
  if (!prev) return [];

  const changes: string[] = [];
  const fmt = (field: string, v: unknown) =>
    config.formatters?.[field]?.(v) ?? String(v);

  // Param changes
  for (const field of config.paramFields) {
    const prevVal = prev.params[field];
    const nextVal = next.params[field];
    if (prevVal !== nextVal) {
      changes.push(`- ${field}: ${fmt(field, prevVal)} → ${fmt(field, nextVal)}`);
    }
  }

  // Output changes
  for (const field of config.outputFields) {
    const prevVal = prev.outputs[field];
    const nextVal = next.outputs[field];
    if (prevVal !== nextVal) {
      changes.push(`- ${field}: ${fmt(field, prevVal)} → ${fmt(field, nextVal)}`);
    }
  }

  return changes;
}

// ---------------------------------------------------------------------------
// Payload building
// ---------------------------------------------------------------------------

export interface PayloadConfig {
  snapshot: CommittedSnapshot;
  changes: string[];
  viewLines?: string[];
}

/**
 * Build YAML frontmatter + markdown payload for model context.
 */
export function buildPayload(config: PayloadConfig): string {
  const { snapshot, changes, viewLines = [] } = config;

  const frontmatter = [
    "---",
    `tool: ${snapshot.tool}`,
    `commit_id: ${snapshot.commitId}`,
    `scenario: ${snapshot.mode}`,
    `postcode: ${snapshot.postcode}`,
    `view: ${snapshot.view}`,
    "---",
  ].join("\n");

  const changesBlock = changes.length > 0
    ? changes.join("\n")
    : "- (initial load)";

  // Auto-generate view lines if not provided
  let finalViewLines = viewLines;
  if (finalViewLines.length === 0) {
    finalViewLines = buildDefaultViewLines(snapshot);
  }

  return [
    frontmatter,
    "",
    "## Changes",
    changesBlock,
    "",
    "## Current View",
    finalViewLines.join("\n"),
    "",
  ].join("\n");
}

function buildDefaultViewLines(snapshot: CommittedSnapshot): string[] {
  const lines: string[] = [];

  if (snapshot.view === "comps") {
    lines.push(`- median: ${fmtGBP(snapshot.outputs.median)}`);
    lines.push(`- count: ${snapshot.outputs.count ?? 0} transactions`);
    lines.push(`- search_level: ${snapshot.params.search_level}`);
    lines.push(`- months: ${snapshot.params.months}`);
  } else if (snapshot.view === "yield") {
    lines.push(`- gross_yield: ${fmtPct(snapshot.outputs.gross_yield_pct)}`);
    lines.push(`- assessment: ${snapshot.outputs.assessment ?? "—"}`);
    lines.push(`- data_quality: ${snapshot.outputs.data_quality ?? "—"}`);
    lines.push(`- median: ${fmtGBP(snapshot.outputs.median)}`);
  }

  return lines;
}

// ---------------------------------------------------------------------------
// Context sync
// ---------------------------------------------------------------------------

/**
 * Create initial sync state.
 */
export function createSyncState(): ContextSyncState {
  return {
    lastCommitted: null,
    lastSignature: "",
    commitCounter: 0,
  };
}

/**
 * Push model context update with capability guard and deduplication.
 * Returns new state and whether the push was sent.
 */
export async function pushContext(
  app: App | null,
  snapshot: Omit<CommittedSnapshot, "commitId">,
  state: ContextSyncState
): Promise<PushContextResult> {
  // Always increment commit counter for local tracking
  const commitId = state.commitCounter + 1;
  const fullSnapshot: CommittedSnapshot = { ...snapshot, commitId };

  // Capability guard - still advance state for local tracking
  if (!canUpdateModelContext(app)) {
    console.info("[MCP App] Host does not support updateModelContext");
    return {
      sent: false,
      newState: {
        lastCommitted: fullSnapshot,
        lastSignature: state.lastSignature,
        commitCounter: commitId,
      },
      reason: "no_capability",
    };
  }

  // Compute deltas and build payload
  const changes = computeDeltas(state.lastCommitted, fullSnapshot);
  const payload = buildPayload({ snapshot: fullSnapshot, changes });

  // Dedupe identical payloads
  if (payload === state.lastSignature) {
    console.info("[MCP App] Skipping duplicate context update");
    return {
      sent: false,
      newState: state,
      reason: "duplicate",
    };
  }

  console.info("[MCP App] Pushing model context:", payload);

  try {
    await app!.updateModelContext({
      content: [{ type: "text", text: payload }],
    });

    const newState: ContextSyncState = {
      lastCommitted: fullSnapshot,
      lastSignature: payload,
      commitCounter: commitId,
    };

    return {
      sent: true,
      payload,
      newState,
      reason: "sent",
    };
  } catch (err) {
    console.warn("[MCP App] Failed to update model context:", err);
    return {
      sent: false,
      newState: state,
      reason: "error",
    };
  }
}
