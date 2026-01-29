<script lang="ts">
/**
 * Badge component for displaying status/quality indicators.
 * Supports different color variants.
 */

interface Props {
  label: string;
  color: string;
}

let { label, color }: Props = $props();
</script>

<span class="badge" style:background-color={color}>
  {label}
</span>

<style>
.badge {
  display: inline-block;
  padding: 6px 12px;
  border-radius: 9999px;
  font-size: var(--font-text-sm-size, 12px);
  font-weight: var(--font-weight-semibold, 600);
  color: white;
  text-align: center;
}
</style>
