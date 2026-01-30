<script lang="ts">
/**
 * Price slider component for interactive value adjustment.
 * Used for "what-if" yield calculations.
 */

interface Props {
  min: number;
  max: number;
  value: number;
  step?: number;
  label?: string;
  formatFn?: (value: number) => string;
  onchange?: (value: number) => void;
}

let { min, max, value = $bindable(), step = 10000, label, formatFn, onchange }: Props = $props();

// Default formatter for GBP prices
function defaultFormat(v: number): string {
  if (v >= 1_000_000) return `£${(v / 1_000_000).toFixed(1)}m`;
  return `£${Math.round(v / 1000)}k`;
}

let format = formatFn ?? defaultFormat;

function handleInput(e: Event) {
  const target = e.target as HTMLInputElement;
  const newValue = parseFloat(target.value);
  value = newValue;
  onchange?.(newValue);
}

// Calculate fill percentage for gradient
let fillPct = $derived(() => ((value - min) / (max - min)) * 100);
</script>

<div class="price-slider">
  {#if label}
    <label class="label">{label}</label>
  {/if}
  <div class="slider-row">
    <span class="value-display">{format(value)}</span>
    <input
      type="range"
      {min}
      {max}
      {step}
      {value}
      class="slider"
      style:--fill-pct="{fillPct()}%"
      oninput={handleInput}
    />
  </div>
  <div class="range-labels">
    <span>{format(min)}</span>
    <span>{format(max)}</span>
  </div>
</div>

<style>
.price-slider {
  width: 100%;
}

.label {
  display: block;
  font-size: var(--font-text-xs-size, 11px);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-secondary, #64748b);
  margin-bottom: 8px;
}

.slider-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.value-display {
  min-width: 70px;
  font-size: var(--font-text-md-size, 16px);
  font-weight: var(--font-weight-bold, 700);
  color: var(--color-text-primary, #1e293b);
}

.slider {
  flex: 1;
  height: 8px;
  appearance: none;
  background: linear-gradient(
    to right,
    var(--color-ring-primary, #3b82f6) 0%,
    var(--color-ring-primary, #3b82f6) var(--fill-pct),
    var(--color-background-tertiary, #e2e8f0) var(--fill-pct),
    var(--color-background-tertiary, #e2e8f0) 100%
  );
  border-radius: 4px;
  cursor: pointer;
}

.slider::-webkit-slider-thumb {
  appearance: none;
  width: 20px;
  height: 20px;
  background: var(--color-ring-primary, #3b82f6);
  border: 3px solid white;
  border-radius: 50%;
  box-shadow: 0 2px 4px rgba(0,0,0,0.2);
  cursor: pointer;
  transition: transform 0.1s ease;
}

.slider::-webkit-slider-thumb:hover {
  transform: scale(1.1);
}

.slider::-moz-range-thumb {
  width: 20px;
  height: 20px;
  background: var(--color-ring-primary, #3b82f6);
  border: 3px solid white;
  border-radius: 50%;
  box-shadow: 0 2px 4px rgba(0,0,0,0.2);
  cursor: pointer;
}

.range-labels {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: var(--color-text-tertiary, #94a3b8);
  margin-top: 4px;
}
</style>
