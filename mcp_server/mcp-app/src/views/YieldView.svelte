<script lang="ts">
/**
 * Yield analysis view.
 * Displays yield gauge, stats, and data quality indicator.
 */
import type { YieldData } from "../lib/types";
import { formatPrice, formatRent, getQualityColor, getQualityLabel } from "../lib/formatters";
import StatCard from "../components/StatCard.svelte";
import DataBadge from "../components/DataBadge.svelte";
import YieldGauge from "../components/YieldGauge.svelte";

interface Props {
  data: YieldData;
}

let { data }: Props = $props();

let qualityColor = $derived(getQualityColor(data.data_quality));
let qualityLabel = $derived(getQualityLabel(data.data_quality));
</script>

<div class="yield-view">
  <!-- Yield Gauge -->
  <YieldGauge yieldPct={data.gross_yield_pct} assessment={data.yield_assessment} />

  <!-- Stats Grid -->
  <div class="stats-grid">
    <StatCard
      label="Median Sale Price"
      value={formatPrice(data.median_sale_price)}
      subtext={`${data.sale_count ?? 0} sales`}
    />
    <StatCard
      label="Median Monthly Rent"
      value={formatRent(data.median_monthly_rent)}
      subtext={`${data.rental_count ?? 0} listings`}
    />
  </div>

  <!-- Data Quality Badge -->
  <div class="badge-container">
    <DataBadge label={qualityLabel} color={qualityColor} />
  </div>

  <!-- Thin Market Warning -->
  {#if data.thin_market}
    <p class="thin-market-warning">
      Limited market data available for this area
    </p>
  {/if}
</div>

<style>
.yield-view {
  width: 100%;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.badge-container {
  text-align: center;
  margin-top: 8px;
}

.thin-market-warning {
  text-align: center;
  padding: 12px;
  margin-top: 16px;
  background: var(--color-background-warning-subtle, #fef3c7);
  color: var(--color-text-warning, #92400e);
  border-radius: var(--border-radius-md, 8px);
  font-size: var(--font-text-sm-size, 14px);
}
</style>
