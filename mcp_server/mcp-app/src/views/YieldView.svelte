<script lang="ts">
/**
 * Yield analysis view.
 * BOUCH Design System - Professional brutalist yield dashboard
 */
import type { YieldData } from "../lib/types";
import { formatPrice, formatRent, getQualityColor, getQualityLabel, getYieldAssessment } from "../lib/formatters";
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
  <div class="gauge-section">
    {#if isCustom() && customYield() !== null}
      <YieldGauge yieldPct={customYield()} assessment={customAssessment()} />
      <div class="indicator custom-indicator">Custom calculation</div>
    {:else}
      <YieldGauge yieldPct={data.gross_yield_pct} assessment={data.yield_assessment} />
      <div class="indicator market-indicator">Based on market median</div>
    {/if}
  </div>

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
    <div class="thin-market-warning">
      <span class="warning-icon">!</span>
      Limited market data available for this area
    </div>
  {/if}
</div>

<style>
.yield-view {
  width: 100%;
  font-family: 'Space Mono', monospace;
}

.gauge-section {
  padding: 24px 0;
  border-bottom: 1px solid var(--bouch-gray, rgba(28, 25, 23, 0.12));
  margin-bottom: 0;
}

.indicator {
  text-align: center;
  font-family: 'Space Mono', monospace;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 2px;
  margin-top: -8px;
}

.custom-indicator {
  color: var(--bouch-orange, #D97757);
}

.market-indicator {
  color: var(--bouch-mid-gray, #b0aea5);
}

.slider-section {
  margin-bottom: 20px;
}

.reset-btn {
  display: block;
  width: 100%;
  margin-top: 0;
  padding: 10px 16px;
  font-family: 'Space Mono', monospace;
  font-size: 11px;
  font-weight: 400;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--bouch-cream, #FAF9F5);
  background: transparent;
  border: none;
  border-top: 1px solid rgba(250, 249, 245, 0.2);
  cursor: pointer;
  transition: all 0.2s ease;
}

.reset-btn:hover {
  background: rgba(250, 249, 245, 0.1);
  color: var(--bouch-orange, #D97757);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}

.badge-container {
  text-align: center;
  padding: 16px 0;
}

.thin-market-warning {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 14px 16px;
  margin-top: 16px;
  background: var(--bouch-charcoal, #1C1917);
  border: 2px solid var(--bouch-orange, #D97757);
  font-family: 'Space Mono', monospace;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--bouch-cream, #FAF9F5);
}

.warning-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  background: var(--bouch-orange, #D97757);
  color: var(--bouch-charcoal, #1C1917);
  font-weight: 700;
}
</style>
