<script lang="ts">
interface CompsData {
  median?: number;
  mean?: number;
  count?: number;
  percentile_25?: number;
  percentile_75?: number;
}

let { data }: { data: CompsData } = $props();

function formatPrice(price: number | undefined): string {
  if (price === undefined) return "N/A";
  return "£" + price.toLocaleString("en-GB");
}
</script>

<div class="stats-panel">
  <div class="stat">
    <span class="label">Median</span>
    <span class="value">{formatPrice(data.median)}</span>
  </div>
  <div class="stat">
    <span class="label">Mean</span>
    <span class="value">{formatPrice(data.mean)}</span>
  </div>
  <div class="stat">
    <span class="label">Count</span>
    <span class="value">{data.count ?? 0}</span>
  </div>
  <div class="stat">
    <span class="label">Range (25th-75th)</span>
    <span class="value">{formatPrice(data.percentile_25)} - {formatPrice(data.percentile_75)}</span>
  </div>
</div>

<style>
.stats-panel {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
  padding: 16px;
  background: var(--color-background-secondary, #f5f5f5);
  border-radius: var(--border-radius-md, 8px);
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.label {
  font-size: var(--font-text-sm-size, 12px);
  color: var(--color-text-secondary, #666);
  font-weight: var(--font-weight-semibold, 600);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.value {
  font-size: var(--font-text-md-size, 16px);
  font-weight: var(--font-weight-bold, 700);
  color: var(--color-text-primary, #1a1a1a);
}
</style>
