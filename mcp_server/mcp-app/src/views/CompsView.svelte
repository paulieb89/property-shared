<script lang="ts">
/**
 * Comparable sales view.
 * Displays price statistics and transaction table.
 * Optionally shows subject property context when address was provided.
 * Includes search controls for re-querying with different parameters.
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
    <TransactionTable transactions={data.transactions} />
  {:else}
    <p class="no-data">No transactions found</p>
  {/if}
</div>

<style>
.comps-view {
  width: 100%;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

@media (min-width: 600px) {
  .stats-grid {
    grid-template-columns: repeat(4, 1fr);
  }
}

.no-data {
  text-align: center;
  padding: 24px;
  color: var(--color-text-secondary, #666);
}
</style>
