<script lang="ts">
/**
 * Yield analysis view.
 * Displays yield gauge, stats, and data quality indicator.
 * Includes interactive price slider for "what-if" yield calculations.
 * Includes search controls for re-querying with different parameters.
 */
import type { YieldData } from "../lib/types";
import { formatPrice, formatRent, getQualityColor, getQualityLabel, getYieldAssessment, getAssessmentColor, getAssessmentLabel } from "../lib/formatters";
import StatCard from "../components/StatCard.svelte";
import DataBadge from "../components/DataBadge.svelte";
import YieldGauge from "../components/YieldGauge.svelte";
import PriceSlider from "../components/PriceSlider.svelte";
import SearchControls, { type SearchParams } from "../components/SearchControls.svelte";

interface Props {
  data: YieldData;
  params?: SearchParams | null;
  toolName?: string;
  loading?: boolean;
  onApply?: (params: SearchParams) => void;
}

let { data, params, toolName = "property_yield", loading = false, onApply }: Props = $props();

// Check if we can show controls
let showControls = $derived(() => params !== null && params !== undefined && onApply !== undefined);

let qualityColor = $derived(getQualityColor(data.data_quality));
let qualityLabel = $derived(getQualityLabel(data.data_quality));

// Interactive price state - initialized to market median
let customPrice = $state(data.median_sale_price ?? 200000);

// Calculate custom yield based on slider value
let customYield = $derived(() => {
  if (!data.median_monthly_rent || !customPrice) return null;
  return ((data.median_monthly_rent * 12) / customPrice) * 100;
});

// Get assessment for custom yield
let customAssessment = $derived(() => {
  if (customYield() === null) return undefined;
  return getYieldAssessment(customYield()!);
});

// Check if custom price differs from market
let isCustom = $derived(() => {
  return customPrice !== data.median_sale_price && data.median_sale_price !== undefined;
});

// Calculate price range for slider (50% to 150% of median, or reasonable defaults)
let priceMin = $derived(() => {
  const median = data.median_sale_price ?? 200000;
  return Math.round(median * 0.5 / 10000) * 10000; // Round to 10k
});

let priceMax = $derived(() => {
  const median = data.median_sale_price ?? 200000;
  return Math.round(median * 1.5 / 10000) * 10000;
});
</script>

<div class="yield-view">
  <!-- Search Controls -->
  {#if showControls() && params}
    <SearchControls
      initialParams={params}
      toolName="property_yield"
      {loading}
      onApply={onApply!}
    />
  {/if}

  <!-- Yield Gauge - shows custom yield when price adjusted, otherwise market yield -->
  {#if isCustom() && customYield() !== null}
    <YieldGauge yieldPct={customYield()} assessment={customAssessment()} />
    <div class="custom-indicator">Custom calculation</div>
  {:else}
    <YieldGauge yieldPct={data.gross_yield_pct} assessment={data.yield_assessment} />
    <div class="market-indicator">Based on market median</div>
  {/if}

  <!-- Price Slider for what-if analysis -->
  {#if data.median_monthly_rent}
    <div class="slider-section">
      <PriceSlider
        min={priceMin()}
        max={priceMax()}
        bind:value={customPrice}
        label="Adjust purchase price"
      />
      {#if isCustom()}
        <button class="reset-btn" onclick={() => customPrice = data.median_sale_price ?? 200000}>
          Reset to market median
        </button>
      {/if}
    </div>
  {/if}

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

.custom-indicator,
.market-indicator {
  text-align: center;
  font-size: var(--font-text-xs-size, 11px);
  margin-top: -8px;
  margin-bottom: 16px;
}

.custom-indicator {
  color: var(--color-ring-primary, #3b82f6);
  font-weight: var(--font-weight-semibold, 600);
}

.market-indicator {
  color: var(--color-text-tertiary, #94a3b8);
}

.slider-section {
  background: var(--color-background-secondary, #f8fafc);
  border-radius: var(--border-radius-md, 8px);
  padding: 16px;
  margin-bottom: 16px;
}

.reset-btn {
  display: block;
  margin: 12px auto 0;
  padding: 6px 12px;
  font-size: var(--font-text-xs-size, 12px);
  color: var(--color-ring-primary, #3b82f6);
  background: transparent;
  border: 1px solid var(--color-ring-primary, #3b82f6);
  border-radius: var(--border-radius-sm, 4px);
  cursor: pointer;
  transition: background 0.15s ease;
}

.reset-btn:hover {
  background: var(--color-background-ghost, rgba(59, 130, 246, 0.1));
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
