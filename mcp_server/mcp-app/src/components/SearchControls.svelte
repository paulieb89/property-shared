<script lang="ts">
/**
 * Search controls component for adjusting query parameters.
 * Allows users to modify months, radius, and search_level, then re-query.
 */

export interface SearchParams {
  postcode?: string;
  months: number;
  radius?: number;
  search_level: string;
  address?: string;
}

interface Props {
  initialParams: SearchParams;
  toolName: "property_comps" | "property_yield";
  loading?: boolean;
  onApply: (params: SearchParams) => void;
}

let { initialParams, toolName, loading = false, onApply }: Props = $props();

// Local state for form values
let months = $state(initialParams.months);
let radius = $state(initialParams.radius ?? 0.5);
let searchLevel = $state(initialParams.search_level);

// Check if values have changed
let hasChanges = $derived(() => {
  return months !== initialParams.months ||
    radius !== (initialParams.radius ?? 0.5) ||
    searchLevel !== initialParams.search_level;
});

function handleApply() {
  onApply({
    ...initialParams,
    months,
    radius,
    search_level: searchLevel,
  });
}

function handleReset() {
  months = initialParams.months;
  radius = initialParams.radius ?? 0.5;
  searchLevel = initialParams.search_level;
}

// Options
const monthOptions = [6, 12, 24, 36];
const radiusOptions = [0.25, 0.5, 1, 2];
const searchLevelOptions = [
  { value: "postcode", label: "Postcode" },
  { value: "sector", label: "Sector" },
  { value: "district", label: "District" },
];
</script>

<div class="search-controls">
  <div class="controls-row">
    <div class="control-group">
      <label for="months-select">Months</label>
      <select id="months-select" bind:value={months} disabled={loading}>
        {#each monthOptions as m}
          <option value={m}>{m}</option>
        {/each}
      </select>
    </div>

    {#if toolName === "property_yield"}
      <div class="control-group">
        <label for="radius-select">Radius</label>
        <select id="radius-select" bind:value={radius} disabled={loading}>
          {#each radiusOptions as r}
            <option value={r}>{r} mi</option>
          {/each}
        </select>
      </div>
    {/if}

    <div class="control-group">
      <label for="level-select">Area</label>
      <select id="level-select" bind:value={searchLevel} disabled={loading}>
        {#each searchLevelOptions as opt}
          <option value={opt.value}>{opt.label}</option>
        {/each}
      </select>
    </div>

    <div class="buttons">
      <button
        class="apply-btn"
        onclick={handleApply}
        disabled={loading || !hasChanges()}
      >
        {loading ? "Loading..." : "Apply"}
      </button>
      {#if hasChanges()}
        <button class="reset-btn" onclick={handleReset} disabled={loading}>
          Reset
        </button>
      {/if}
    </div>
  </div>
</div>

<style>
.search-controls {
  background: var(--color-background-secondary, #f8fafc);
  border-radius: var(--border-radius-md, 8px);
  padding: 12px;
  margin-bottom: 16px;
}

.controls-row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 12px;
}

.control-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.control-group label {
  font-size: var(--font-text-xs-size, 11px);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-secondary, #64748b);
}

.control-group select {
  padding: 6px 10px;
  font-size: var(--font-text-sm-size, 14px);
  border: 1px solid var(--color-border-primary, #e2e8f0);
  border-radius: var(--border-radius-sm, 4px);
  background: var(--color-background-primary, white);
  color: var(--color-text-primary, #1e293b);
  cursor: pointer;
}

.control-group select:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.buttons {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

.apply-btn {
  padding: 6px 16px;
  font-size: var(--font-text-sm-size, 14px);
  font-weight: var(--font-weight-semibold, 600);
  color: white;
  background: var(--color-ring-primary, #3b82f6);
  border: none;
  border-radius: var(--border-radius-sm, 4px);
  cursor: pointer;
  transition: background 0.15s ease;
}

.apply-btn:hover:not(:disabled) {
  background: var(--color-ring-secondary, #2563eb);
}

.apply-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.reset-btn {
  padding: 6px 12px;
  font-size: var(--font-text-sm-size, 14px);
  color: var(--color-text-secondary, #64748b);
  background: transparent;
  border: 1px solid var(--color-border-primary, #e2e8f0);
  border-radius: var(--border-radius-sm, 4px);
  cursor: pointer;
}

.reset-btn:hover:not(:disabled) {
  background: var(--color-background-tertiary, #f1f5f9);
}

@media (max-width: 480px) {
  .controls-row {
    flex-direction: column;
    align-items: stretch;
  }

  .control-group {
    width: 100%;
  }

  .control-group select {
    width: 100%;
  }

  .buttons {
    margin-left: 0;
    justify-content: stretch;
  }

  .apply-btn {
    flex: 1;
  }
}
</style>
