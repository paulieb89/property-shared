<script lang="ts">
/**
 * Reusable stat display card.
 * Used by both CompsView and YieldView for consistent stat presentation.
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
  padding: 16px;
  background: var(--color-background-secondary, #f5f5f5);
  border-radius: var(--border-radius-md, 8px);
  text-align: center;
}

.stat-label {
  font-size: var(--font-text-sm-size, 12px);
  color: var(--color-text-secondary, #666);
  font-weight: var(--font-weight-semibold, 600);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
}

.stat-value {
  font-size: var(--font-text-lg-size, 20px);
  font-weight: var(--font-weight-bold, 700);
  color: var(--color-text-primary, #1a1a1a);
}

.stat-subtext {
  font-size: var(--font-text-sm-size, 12px);
  color: var(--color-text-tertiary, #999);
  margin-top: 4px;
}

.stat-card.positive .stat-value {
  color: #22c55e;
}

.stat-card.negative .stat-value {
  color: #ef4444;
}
</style>
