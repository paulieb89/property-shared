<script lang="ts">
/**
 * Price slider component for interactive value adjustment.
 * BOUCH Design System - Brutalist slider with reactive feedback
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

let isDragging = $state(false);

function handleInput(e: Event) {
  const target = e.target as HTMLInputElement;
  const newValue = parseFloat(target.value);
  value = newValue;
  onchange?.(newValue);
}

// Calculate fill percentage for gradient
let fillPct = $derived(() => ((value - min) / (max - min)) * 100);
</script>

<div class="price-slider" class:dragging={isDragging}>
  {#if label}
    <label class="label">{label}</label>
  {/if}
  <div class="slider-row">
    <span class="value-display">{format(value)}</span>
    <div class="slider-track">
      <input
        type="range"
        {min}
        {max}
        {step}
        {value}
        class="slider"
        style:--fill-pct="{fillPct()}%"
        oninput={handleInput}
        onmousedown={() => isDragging = true}
        onmouseup={() => isDragging = false}
        ontouchstart={() => isDragging = true}
        ontouchend={() => isDragging = false}
      />
      <div class="slider-fill" style:width="{fillPct()}%"></div>
    </div>
  </div>
  <div class="range-labels">
    <span>{format(min)}</span>
    <span>{format(max)}</span>
  </div>
</div>

<style>
.price-slider {
  width: 100%;
  padding: 16px;
  background: var(--bouch-charcoal, #1C1917);
  transition: all 0.2s ease;
}

.price-slider.dragging {
  background: #2d2926;
}

.label {
  display: block;
  font-family: 'Space Mono', monospace;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 2px;
  color: var(--bouch-mid-gray, #b0aea5);
  margin-bottom: 12px;
}

.slider-row {
  display: flex;
  align-items: center;
  gap: 16px;
}

.value-display {
  min-width: 70px;
  font-family: 'Bebas Neue', sans-serif;
  font-size: 24px;
  letter-spacing: 1px;
  color: var(--bouch-cream, #FAF9F5);
}

.slider-track {
  flex: 1;
  position: relative;
  height: 6px;
  background: rgba(250, 249, 245, 0.2);
}

.slider-fill {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  background: var(--bouch-orange, #D97757);
  pointer-events: none;
  transition: width 0.1s ease;
}

.slider {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 100%;
  height: 24px;
  appearance: none;
  background: transparent;
  cursor: pointer;
  margin: 0;
}

.slider::-webkit-slider-thumb {
  appearance: none;
  width: 20px;
  height: 20px;
  background: var(--bouch-cream, #FAF9F5);
  border: 3px solid var(--bouch-orange, #D97757);
  cursor: grab;
  transition: all 0.15s ease;
}

.slider::-webkit-slider-thumb:hover {
  transform: scale(1.15);
  box-shadow: 0 0 0 4px rgba(217, 119, 87, 0.3);
}

.slider::-webkit-slider-thumb:active {
  cursor: grabbing;
  transform: scale(0.95);
}

.slider::-moz-range-thumb {
  width: 20px;
  height: 20px;
  background: var(--bouch-cream, #FAF9F5);
  border: 3px solid var(--bouch-orange, #D97757);
  border-radius: 0;
  cursor: grab;
}

.slider::-moz-range-thumb:active {
  cursor: grabbing;
}

.range-labels {
  display: flex;
  justify-content: space-between;
  font-family: 'Space Mono', monospace;
  font-size: 10px;
  letter-spacing: 1px;
  color: var(--bouch-mid-gray, #b0aea5);
  margin-top: 8px;
}
</style>
