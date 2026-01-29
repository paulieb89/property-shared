<script lang="ts">
/**
 * Comparable sales view.
 * Displays price statistics and transaction table.
 */
import type { CompsData } from "../lib/types";
import { formatPrice } from "../lib/formatters";
import StatCard from "../components/StatCard.svelte";
import TransactionTable from "../components/TransactionTable.svelte";

interface Props {
  data: CompsData;
}

let { data }: Props = $props();
</script>

<div class="comps-view">
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
