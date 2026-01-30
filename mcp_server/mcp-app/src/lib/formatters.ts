/**
 * Display formatting utilities.
 */

/**
 * Format a price in GBP (e.g., "£250,000").
 */
export function formatPrice(price: number | undefined | null): string {
  if (price === undefined || price === null) return "N/A";
  return "£" + price.toLocaleString("en-GB");
}

/**
 * Format a monthly rent in GBP (e.g., "£1,200/mo").
 */
export function formatRent(rent: number | undefined | null): string {
  if (rent === undefined || rent === null) return "N/A";
  return "£" + rent.toLocaleString("en-GB") + "/mo";
}

/**
 * Format a percentage (e.g., "5.2%").
 */
export function formatPercent(
  value: number | undefined | null,
  decimals: number = 1
): string {
  if (value === undefined || value === null) return "N/A";
  return value.toFixed(decimals) + "%";
}

/**
 * Format a date string (e.g., "2024-01-15" → "15 Jan 2024").
 */
export function formatDate(dateStr: string | undefined | null): string {
  if (!dateStr) return "N/A";
  try {
    const date = new Date(dateStr);
    return date.toLocaleDateString("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  } catch {
    return dateStr;
  }
}

/**
 * Format a count with label (e.g., "12 sales").
 */
export function formatCount(count: number | undefined | null, label: string): string {
  const n = count ?? 0;
  return `${n} ${label}${n === 1 ? "" : "s"}`;
}

/**
 * Get color for yield assessment.
 */
export function getAssessmentColor(assessment: string | undefined): string {
  if (assessment === "strong") return "#22c55e"; // green
  if (assessment === "average") return "#eab308"; // yellow
  return "#ef4444"; // red for weak
}

/**
 * Get color for data quality.
 */
export function getQualityColor(quality: string | undefined): string {
  if (quality === "good") return "#22c55e"; // green
  if (quality === "low") return "#eab308"; // yellow
  return "#ef4444"; // red for insufficient
}

/**
 * Get label for data quality.
 */
export function getQualityLabel(quality: string | undefined): string {
  if (quality === "good") return "Good data";
  if (quality === "low") return "Limited data";
  return "Insufficient data";
}

/**
 * Get label for yield assessment.
 */
export function getAssessmentLabel(assessment: string | undefined): string {
  if (assessment === "strong") return "Strong";
  if (assessment === "average") return "Average";
  if (assessment === "weak") return "Weak";
  return "N/A";
}

/**
 * Format a price in short form (e.g., "£250k", "£1.2m").
 */
export function formatPriceShort(price: number | undefined | null): string {
  if (price === undefined || price === null) return "N/A";
  if (price >= 1_000_000) return `£${(price / 1_000_000).toFixed(1)}m`;
  return `£${Math.round(price / 1000)}k`;
}

/**
 * Get yield assessment from percentage.
 */
export function getYieldAssessment(yieldPct: number): "strong" | "average" | "weak" {
  if (yieldPct >= 6) return "strong";
  if (yieldPct >= 4) return "average";
  return "weak";
}
