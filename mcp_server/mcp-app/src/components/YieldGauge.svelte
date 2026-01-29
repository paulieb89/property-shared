<script lang="ts">
/**
 * Circular gauge component for displaying yield percentage.
 */
import { getAssessmentColor, getAssessmentLabel } from "../lib/formatters";

interface Props {
  yieldPct?: number;
  assessment?: string;
}

let { yieldPct, assessment }: Props = $props();

const circumference = 2 * Math.PI * 45;

// Derived values
let color = $derived(getAssessmentColor(assessment));
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
      stroke="var(--color-border-primary, #e0e0e0)"
      stroke-width="8"
    />
    <!-- Progress circle -->
    <circle
      cx="50"
      cy="50"
      r="45"
      fill="none"
      stroke={color}
      stroke-width="8"
      stroke-linecap="round"
      stroke-dasharray={circumference}
      stroke-dashoffset={strokeDashoffset()}
      transform="rotate(-90 50 50)"
      class="progress"
    />
  </svg>
  <div class="gauge-text">
    <span class="yield-value">{displayPct()}</span>
    <span class="yield-label" style:color={color}>{label}</span>
  </div>
</div>

<style>
.gauge-container {
  position: relative;
  width: 160px;
  height: 160px;
  margin: 0 auto 16px;
}

.gauge {
  width: 100%;
  height: 100%;
}

.progress {
  transition: stroke-dashoffset 0.5s ease-out;
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
  font-size: var(--font-heading-lg-size, 28px);
  font-weight: var(--font-weight-bold, 700);
  color: var(--color-text-primary, #1a1a1a);
  line-height: 1.2;
}

.yield-label {
  display: block;
  font-size: var(--font-text-sm-size, 14px);
  font-weight: var(--font-weight-semibold, 600);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
</style>
