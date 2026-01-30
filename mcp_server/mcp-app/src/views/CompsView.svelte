<script lang="ts">
/**
 * Comparable sales view.
 * BOUCH Design System - Professional brutalist comps dashboard
 */
import type { CompsData } from "../lib/types";
import { formatPrice } from "../lib/formatters";
import StatCard from "../components/StatCard.svelte";
import TransactionTable from "../components/TransactionTable.svelte";
import SubjectPropertyCard from "../components/SubjectPropertyCard.svelte";
import SearchControls, { type SearchParams } from "../components/SearchControls.svelte";

interface Props {
  data: CompsData;
  params?: SearchParams | null;
  toolName?: string;
  loading?: boolean;
  onApply?: (params: SearchParams) => void;
}

let { data, params, toolName = "property_comps", loading = false, onApply }: Props = $props();

// Check if we have subject property data
let hasSubject = $derived(() => data.subject_property !== undefined);

// Check if we have params and can show controls
let showControls = $derived(() => params !== null && params !== undefined && onApply !== undefined);
</script>

<div class="comps-view">
  <!-- Search Controls -->
  {#if showControls() && params}
    <SearchControls
      initialParams={params}
      toolName="property_comps"
      {loading}
      onApply={onApply!}
    />
  {/if}

  <!-- Subject Property Card (when address provided and found) -->
  {#if hasSubject() && data.subject_property}
    <SubjectPropertyCard
      subject={data.subject_property}
      percentile={data.subject_price_percentile}
      vsMedianPct={data.subject_vs_median_pct}
    />
  {/if}

  <!-- Stats Grid -->
  <div class="stats-grid">
    <StatCard
      label="Median"
      value={formatPrice(data.median)}
      subtext={`${data.count ?? 0} sales`}
    />
    <StatCard
      label="Mean"
      value={formatPrice(data.mean)}
    />
    <StatCard
      label="25th Percentile"
      value={formatPrice(data.percentile_25)}
    />
    <StatCard
      label="75th Percentile"
      value={formatPrice(data.percentile_75)}
    />
  </div>

  <!-- Transaction Table -->
  {#if data.transactions && data.transactions.length > 0}
    <div class="table-section">
      <div class="table-header">
        <span class="table-title">Recent Sales</span>
        <span class="table-count">{data.transactions.length} transactions</span>
      </div>
      <TransactionTable transactions={data.transactions} />
    </div>
  {:else}
    <div class="no-data">
      <span class="no-data-icon">?</span>
      <span>No transactions found</span>
    </div>
  {/if}
</div>

<style>
.comps-view {
  width: 100%;
  font-family: 'Space Mono', monospace;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}

@media (min-width: 600px) {
  .stats-grid {
    grid-template-columns: repeat(4, 1fr);
  }
}

.table-section {
  margin-top: 8px;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  border-bottom: 2px solid var(--bouch-orange, #D97757);
  margin-bottom: 0;
}

.table-title {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 2px;
  color: var(--bouch-charcoal, #1C1917);
}

.table-count {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--bouch-mid-gray, #b0aea5);
}

.no-data {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 40px 24px;
  background: var(--bouch-gray, #e8e6dc);
  text-align: center;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 2px;
  color: var(--bouch-mid-gray, #b0aea5);
}

.no-data-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background: var(--bouch-charcoal, #1C1917);
  color: var(--bouch-orange, #D97757);
  font-family: 'Bebas Neue', sans-serif;
  font-size: 24px;
}
</style>
