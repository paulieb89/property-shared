<script lang="ts">
/**
 * Subject property card component.
 * Displays the subject property with last sale, percentile position, and vs median comparison.
 */
import type { SubjectProperty } from "../lib/types";
import { formatPrice, formatDate } from "../lib/formatters";
import PercentileBadge from "./PercentileBadge.svelte";

interface Props {
  subject: SubjectProperty;
  percentile?: number; // 0-100
  vsMedianPct?: number; // e.g., +10.8 or -5.2
}

let { subject, percentile, vsMedianPct }: Props = $props();

// Format the vs median indicator
let vsMedianDisplay = $derived(() => {
  if (vsMedianPct === undefined || vsMedianPct === null) return null;
  const sign = vsMedianPct >= 0 ? "+" : "";
  return `${sign}${vsMedianPct.toFixed(1)}% vs median`;
});

let vsMedianColor = $derived(() => {
  if (vsMedianPct === undefined || vsMedianPct === null) return "#666";
  if (vsMedianPct < -10) return "#22c55e"; // green - well below median
  if (vsMedianPct < 0) return "#84cc16"; // lime - below median
  if (vsMedianPct < 10) return "#eab308"; // yellow - near median
  return "#f97316"; // orange - above median
});

// Format address from subject
let displayAddress = $derived(() => {
  return subject.address || "Unknown address";
});
</script>

<div class="subject-card">
  <div class="header">
    <span class="icon">&#127968;</span>
    <span class="title">Subject Property</span>
  </div>

  <div class="address">{displayAddress()}</div>

  {#if subject.last_sale}
    <div class="last-sale">
      <div class="sale-info">
        <span class="sale-price">{formatPrice(subject.last_sale.price)}</span>
        <span class="sale-date">{formatDate(subject.last_sale.date)}</span>
      </div>
      {#if vsMedianDisplay()}
        <span class="vs-median" style:color={vsMedianColor()}>{vsMedianDisplay()}</span>
      {/if}
    </div>
  {:else}
    <div class="no-sale">No sale history found</div>
  {/if}

  {#if percentile !== undefined}
    <div class="percentile-section">
      <PercentileBadge {percentile} label="Price position in area" />
    </div>
  {/if}

  {#if subject.transaction_count > 1}
    <div class="history-note">
      {subject.transaction_count} sales on record
    </div>
  {/if}
</div>

<style>
.subject-card {
  background: var(--color-background-secondary, #f8fafc);
  border: 2px solid var(--color-border-primary, #e2e8f0);
  border-radius: var(--border-radius-lg, 12px);
  padding: 16px;
  margin-bottom: 16px;
}

.header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.icon {
  font-size: 20px;
}

.title {
  font-size: var(--font-text-xs-size, 11px);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-secondary, #64748b);
  font-weight: var(--font-weight-semibold, 600);
}

.address {
  font-size: var(--font-text-md-size, 16px);
  font-weight: var(--font-weight-semibold, 600);
  color: var(--color-text-primary, #1e293b);
  margin-bottom: 12px;
}

.last-sale {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px 16px;
  margin-bottom: 12px;
}

.sale-info {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.sale-price {
  font-size: var(--font-text-lg-size, 20px);
  font-weight: var(--font-weight-bold, 700);
  color: var(--color-text-primary, #1e293b);
}

.sale-date {
  font-size: var(--font-text-sm-size, 14px);
  color: var(--color-text-secondary, #64748b);
}

.vs-median {
  font-size: var(--font-text-sm-size, 14px);
  font-weight: var(--font-weight-semibold, 600);
}

.no-sale {
  font-size: var(--font-text-sm-size, 14px);
  color: var(--color-text-tertiary, #94a3b8);
  font-style: italic;
  margin-bottom: 12px;
}

.percentile-section {
  padding-top: 12px;
  border-top: 1px solid var(--color-border-secondary, #e2e8f0);
}

.history-note {
  margin-top: 12px;
  font-size: var(--font-text-xs-size, 11px);
  color: var(--color-text-tertiary, #94a3b8);
}
</style>
