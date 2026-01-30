<script lang="ts">
/**
 * Badge component for displaying status/quality indicators.
 * BOUCH Design System - Brutalist badge styling
 */

interface Props {
  label: string;
  color: string;
}

let { label, color }: Props = $props();

// Map semantic colors to BOUCH palette
function getBouchColor(c: string): string {
  // If it's a hex color, use it directly
  if (c.startsWith('#')) return c;

  // Map common color names to BOUCH colors
  const colorMap: Record<string, string> = {
    green: '#38a169',
    success: '#38a169',
    orange: '#D97757',
    warning: '#c05621',
    red: '#dc2626',
    danger: '#dc2626',
    gray: '#b0aea5',
    muted: '#b0aea5',
  };

  return colorMap[c.toLowerCase()] || c;
}

let bgColor = $derived(getBouchColor(color));
let textColor = $derived(() => {
  // Use dark text for light backgrounds
  if (bgColor === '#38a169' || bgColor === '#D97757') {
    return '#1C1917';
  }
  return '#FAF9F5';
});
</script>

<span class="badge" style:background-color={bgColor} style:color={textColor()}>
  {label}
</span>

<style>
.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  font-family: 'Space Mono', monospace;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1px;
  text-align: center;
  transition: transform 0.15s ease;
}

.badge:hover {
  transform: scale(1.02);
}
</style>
