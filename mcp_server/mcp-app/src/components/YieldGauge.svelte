<script lang="ts">
/**
 * Circular gauge component for displaying yield percentage.
 * BOUCH Design System - Animated gauge with brutalist aesthetic
 */
import { getAssessmentColor, getAssessmentLabel } from "../lib/formatters";

interface Props {
  yieldPct?: number;
  assessment?: string;
}

let { yieldPct, assessment }: Props = $props();

const circumference = 2 * Math.PI * 45;

// Map assessment to BOUCH colors
function getBouchColor(a: string | undefined): string {
  switch (a) {
    case "strong": return "#38a169"; // success green
    case "average": return "#D97757"; // orange accent
    case "weak": return "#dc2626"; // red
    default: return "#b0aea5"; // mid-gray
  }
}

// Derived values
let color = $derived(getBouchColor(assessment));
let label = $derived(getAssessmentLabel(assessment));

let displayPct = $derived(() => {
  if (yieldPct === undefined || yieldPct === null) return "—";
  return yieldPct.toFixed(1) + "%";
});

let strokeDashoffset = $derived(() => {
  const pct = Math.min((yieldPct ?? 0) / 10, 1); // normalize to 0-1 (10% = 100%)
  return circumference * (1 - pct);
});
</script>

<div class="gauge-container">
  <svg class="gauge" viewBox="0 0 100 100">
    <!-- Background circle -->
    <circle
      cx="50"
      cy="50"
      r="45"
      fill="none"
      stroke="var(--bouch-gray, #e8e6dc)"
      stroke-width="6"
    />
    <!-- Progress circle -->
    <circle
      cx="50"
      cy="50"
      r="45"
      fill="none"
      stroke={color}
      stroke-width="6"
      stroke-dasharray={circumference}
      stroke-dashoffset={strokeDashoffset()}
      transform="rotate(-90 50 50)"
      class="progress"
    />
    <!-- Corner markers for brutalist feel -->
    <rect x="4" y="4" width="8" height="2" fill="var(--bouch-charcoal, #1C1917)" />
    <rect x="4" y="4" width="2" height="8" fill="var(--bouch-charcoal, #1C1917)" />
    <rect x="88" y="4" width="8" height="2" fill="var(--bouch-charcoal, #1C1917)" />
    <rect x="94" y="4" width="2" height="8" fill="var(--bouch-charcoal, #1C1917)" />
    <rect x="4" y="94" width="8" height="2" fill="var(--bouch-charcoal, #1C1917)" />
    <rect x="4" y="88" width="2" height="8" fill="var(--bouch-charcoal, #1C1917)" />
    <rect x="88" y="94" width="8" height="2" fill="var(--bouch-charcoal, #1C1917)" />
    <rect x="94" y="88" width="2" height="8" fill="var(--bouch-charcoal, #1C1917)" />
  </svg>
  <div class="gauge-text">
    <span class="yield-value">{displayPct()}</span>
    <span class="yield-label" style:color={color}>{label}</span>
  </div>
</div>

<style>
.gauge-container {
  position: relative;
  width: 180px;
  height: 180px;
  margin: 0 auto 20px;
}

.gauge {
  width: 100%;
  height: 100%;
}

.progress {
  transition: stroke-dashoffset 0.6s cubic-bezier(0.4, 0, 0.2, 1);
}

.gauge-text {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
}

.yield-value {
  display: block;
  font-family: 'Bebas Neue', sans-serif;
  font-size: 42px;
  letter-spacing: 2px;
  color: var(--bouch-charcoal, #1C1917);
  line-height: 1;
}

.yield-label {
  display: block;
  font-family: 'Space Mono', monospace;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 2px;
  margin-top: 4px;
}
</style>
