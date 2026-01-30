<script lang="ts">
/**
 * Search controls component for adjusting query parameters.
 * BOUCH Design System - Professional brutalist aesthetic
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
      <select id="months-select" class="select" bind:value={months} disabled={loading}>
        {#each monthOptions as m}
          <option value={m}>{m}</option>
        {/each}
      </select>
    </div>

    {#if toolName === "property_yield"}
      <div class="control-group">
        <label for="radius-select">Radius</label>
        <select id="radius-select" class="select" bind:value={radius} disabled={loading}>
          {#each radiusOptions as r}
            <option value={r}>{r} mi</option>
          {/each}
        </select>
      </div>
    {/if}

    <div class="control-group">
      <label for="level-select">Area</label>
      <select id="level-select" class="select" bind:value={searchLevel} disabled={loading}>
        {#each searchLevelOptions as opt}
          <option value={opt.value}>{opt.label}</option>
        {/each}
      </select>
    </div>

    <div class="buttons">
      <button
        class="btn-apply"
        onclick={handleApply}
        disabled={loading || !hasChanges()}
      >
        {#if loading}
          <span class="spinner"></span>
        {/if}
        {loading ? "Loading" : "Apply"}
      </button>
      {#if hasChanges()}
        <button class="btn-reset" onclick={handleReset} disabled={loading}>
          Reset
        </button>
      {/if}
    </div>
  </div>
</div>

<style>
.search-controls {
  background: var(--bouch-charcoal, #1C1917);
  border-bottom: 2px solid var(--bouch-orange, #D97757);
  padding: 12px 16px;
  margin-bottom: 20px;
}

.controls-row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 16px;
}

.control-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.control-group label {
  font-family: 'Space Mono', monospace;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 2px;
  color: var(--bouch-mid-gray, #b0aea5);
}

.select {
  appearance: none;
  padding: 8px 32px 8px 12px;
  font-family: 'Space Mono', monospace;
  font-size: 13px;
  font-weight: 400;
  border: 1px solid rgba(250, 249, 245, 0.2);
  background: rgba(250, 249, 245, 0.05);
  color: var(--bouch-cream, #FAF9F5);
  cursor: pointer;
  transition: all 0.2s;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23D97757' d='M6 8L2 4h8z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
  min-width: 80px;
}

.select:hover:not(:disabled) {
  border-color: var(--bouch-orange, #D97757);
  background-color: rgba(250, 249, 245, 0.1);
}

.select:focus {
  outline: none;
  border-color: var(--bouch-orange, #D97757);
  box-shadow: 0 0 0 2px rgba(217, 119, 87, 0.3);
}

.select:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.buttons {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

.btn-apply {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 20px;
  font-family: 'Space Mono', monospace;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 2px;
  color: var(--bouch-charcoal, #1C1917);
  background: var(--bouch-orange, #D97757);
  border: none;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-apply:hover:not(:disabled) {
  background: #c45f3d;
  transform: translateY(-1px);
}

.btn-apply:active:not(:disabled) {
  transform: translateY(0);
}

.btn-apply:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

.spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid rgba(28, 25, 23, 0.3);
  border-radius: 50%;
  border-top-color: var(--bouch-charcoal, #1C1917);
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.btn-reset {
  padding: 8px 16px;
  font-family: 'Space Mono', monospace;
  font-size: 11px;
  font-weight: 400;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--bouch-cream, #FAF9F5);
  background: transparent;
  border: 1px solid rgba(250, 249, 245, 0.3);
  cursor: pointer;
  transition: all 0.2s;
}

.btn-reset:hover:not(:disabled) {
  border-color: var(--bouch-cream, #FAF9F5);
  background: rgba(250, 249, 245, 0.1);
}

.btn-reset:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

@media (max-width: 480px) {
  .controls-row {
    flex-direction: column;
    align-items: stretch;
  }

  .control-group {
    width: 100%;
  }

  .select {
    width: 100%;
  }

  .buttons {
    margin-left: 0;
    margin-top: 8px;
  }

  .btn-apply {
    flex: 1;
    justify-content: center;
  }
}
</style>
