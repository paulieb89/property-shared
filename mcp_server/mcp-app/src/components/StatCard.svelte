<script lang="ts">
/**
 * Reusable stat display card.
 * BOUCH Design System - Clean brutalist stat presentation
 */

interface Props {
  label: string;
  value: string;
  subtext?: string;
  variant?: "default" | "positive" | "negative";
}

let { label, value, subtext, variant = "default" }: Props = $props();
</script>

<div class="stat-card" class:positive={variant === "positive"} class:negative={variant === "negative"}>
  <span class="stat-label">{label}</span>
  <span class="stat-value">{value}</span>
  {#if subtext}
    <span class="stat-subtext">{subtext}</span>
  {/if}
</div>

<style>
.stat-card {
  display: flex;
  flex-direction: column;
  padding: 20px 16px;
  background: var(--bouch-cream, #FAF9F5);
  border: 1px solid var(--bouch-gray, rgba(28, 25, 23, 0.12));
  border-left: 3px solid var(--bouch-orange, #D97757);
  text-align: center;
  transition: all 0.2s ease;
}

.stat-card:hover {
  border-left-width: 5px;
  background: white;
}

.stat-label {
  font-family: 'Space Mono', monospace;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 2px;
  color: var(--bouch-mid-gray, #b0aea5);
  margin-bottom: 8px;
}

.stat-value {
  font-family: 'Bebas Neue', sans-serif;
  font-size: 28px;
  letter-spacing: 1px;
  color: var(--bouch-charcoal, #1C1917);
  line-height: 1;
}

.stat-subtext {
  font-family: 'Space Mono', monospace;
  font-size: 11px;
  color: var(--bouch-mid-gray, #b0aea5);
  margin-top: 6px;
}

.stat-card.positive .stat-value {
  color: var(--bouch-success, #38a169);
}

.stat-card.negative .stat-value {
  color: #dc2626;
}
</style>
