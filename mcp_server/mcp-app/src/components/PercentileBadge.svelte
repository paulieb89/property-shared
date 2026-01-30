<script lang="ts">
/**
 * Percentile badge component.
 * Shows where a value sits on a 0-100 scale with a visual bar.
 */

interface Props {
  percentile: number; // 0-100
  label?: string;
}

let { percentile, label }: Props = $props();

// Determine color based on percentile position
let color = $derived(() => {
  if (percentile <= 25) return "#22c55e"; // green - good value
  if (percentile <= 50) return "#84cc16"; // lime - below median
  if (percentile <= 75) return "#eab308"; // yellow - above median
  return "#f97316"; // orange - premium
});

let positionLabel = $derived(() => {
  if (percentile <= 25) return "Below average";
  if (percentile <= 50) return "Average";
  if (percentile <= 75) return "Above average";
  return "Premium";
});
</script>

<div class="percentile-badge">
  {#if label}
    <span class="label">{label}</span>
  {/if}
  <div class="bar-container">
    <div class="bar">
      <div class="marker" style:left="{percentile}%" style:background-color={color()}></div>
    </div>
    <div class="scale">
      <span>0</span>
      <span>50</span>
      <span>100</span>
    </div>
  </div>
  <div class="info">
    <span class="percentile-value" style:color={color()}>{Math.round(percentile)}th</span>
    <span class="position-label">{positionLabel()}</span>
  </div>
</div>

<style>
.percentile-badge {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.label {
  font-size: var(--font-text-xs-size, 11px);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-secondary, #666);
}

.bar-container {
  width: 100%;
}

.bar {
  position: relative;
  height: 8px;
  background: linear-gradient(to right, #22c55e, #84cc16, #eab308, #f97316);
  border-radius: 4px;
  overflow: visible;
}

.marker {
  position: absolute;
  top: -4px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 3px solid white;
  box-shadow: 0 1px 3px rgba(0,0,0,0.3);
  transform: translateX(-50%);
}

.scale {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: var(--color-text-tertiary, #999);
  margin-top: 2px;
}

.info {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-top: 2px;
}

.percentile-value {
  font-size: var(--font-text-md-size, 16px);
  font-weight: var(--font-weight-bold, 700);
}

.position-label {
  font-size: var(--font-text-sm-size, 12px);
  color: var(--color-text-secondary, #666);
}
</style>
