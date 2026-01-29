/**
 * Shared type definitions for the Property MCP App.
 */

export interface Transaction {
  date: string;
  paon?: string;
  street?: string;
  postcode?: string;
  price: number;
  property_type?: string;
}

export interface CompsData {
  median?: number;
  mean?: number;
  count?: number;
  percentile_25?: number;
  percentile_75?: number;
  transactions?: Transaction[];
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
 * Type guards for data detection.
 */
export function isYieldData(obj: unknown): obj is YieldData {
  return typeof obj === "object" && obj !== null && "gross_yield_pct" in obj;
}

export function isCompsData(obj: unknown): obj is CompsData {
  return typeof obj === "object" && obj !== null && "transactions" in obj;
}
