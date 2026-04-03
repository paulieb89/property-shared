# Rental Auto-Escalation Spec

## Problem

`rental_analysis` returns thin/AMBER yield flags for postcodes where local rental
listings are sparse — even when the wider area has good rental market data.

## Solution

When `auto_escalate=True` (default in MCP tool), the service widens its search
radius if the initial result is below the thin market threshold.

## Escalation Levels

| Level | Radius | Equivalent to |
|-------|--------|---------------|
| 0 (specific) | 0.5 mi | postcode |
| 1 | 1.0 mi | sector |
| 2 (broad) | 1.5 mi | district |

Escalation stops at 1.5 mi or when listing count ≥ threshold (default: 3).

## Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `thin_market` | bool | True if final result is still below threshold |
| `escalated_from` | float? | Radius that triggered escalation |
| `escalated_to` | float? | Final radius used |
| `search_postcode` | str | Postcode used for search |

## Pattern

Matches `property_comps` auto_escalate (postcode → sector → district).
Radius widening is used because Rightmove is radius-based, not postcode-prefix-based.
