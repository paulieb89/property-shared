/**
 * Shared type definitions for the Property MCP App.
 */

export interface Transaction {
  date: string;
  paon?: string;
  saon?: string;
  street?: string;
  postcode?: string;
  price: number;
  property_type?: string;
  estate_type?: string;
  town?: string;
  locality?: string;
  district?: string;
  // EPC enrichment fields
  epc_floor_area_sqm?: number;
  epc_floor_area_sqft?: number;
  price_per_sqm?: number;
  price_per_sqft?: number;
  epc_rating?: string;
  epc_score?: number;
  epc_match_score?: number;
}

export interface SubjectProperty {
  address: string;
  postcode: string;
  last_sale?: Transaction;
  transaction_count: number;
  transaction_history: Transaction[];
}

export interface CompsData {
  median?: number;
  mean?: number;
  count?: number;
  percentile_25?: number;
  percentile_75?: number;
  min?: number;
  max?: number;
  thin_market?: boolean;
  transactions?: Transaction[];
  // Subject property context (when address provided)
  subject_property?: SubjectProperty;
  subject_price_percentile?: number; // 0-100
  subject_vs_median_pct?: number; // e.g., +10.8 or -5.2
  // EPC enrichment stats
  median_price_per_sqft?: number;
  epc_match_rate?: number; // 0-1
}

export interface YieldData {
  postcode?: string;
  median_sale_price?: number;
  sale_count?: number;
  median_monthly_rent?: number;
  rental_count?: number;
  gross_yield_pct?: number;
  yield_assessment?: "strong" | "average" | "weak";
  data_quality?: "good" | "low" | "insufficient";
  thin_market?: boolean;
}

export type ToolData = CompsData | YieldData;
export type DataType = "comps" | "yield";

/**
 * Search parameters for property tools.
 */
export interface SearchParams {
  postcode?: string;
  months?: number;
  radius?: number;
  search_level?: string;
}

/**
 * Tool result envelope - matches what extractToolData consumes.
 * Use this for typing callServerTool responses.
 */
export interface ToolEnvelope {
  structuredContent?: unknown;
  content?: Array<{ type: string; text?: string }>;
}

/**
 * Type guards for data detection.
 */
export function isYieldData(obj: unknown): obj is YieldData {
  return typeof obj === "object" && obj !== null && "gross_yield_pct" in obj;
}

export function isCompsData(obj: unknown): obj is CompsData {
  return typeof obj === "object" && obj !== null && "transactions" in obj;
}
