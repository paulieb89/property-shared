# MCP Tools - Gold Status

## What is Gold?

A tool reaches **gold** when it meets all criteria:

### UI/UX
- [ ] BOUCH design system applied
- [ ] Interactive UI with reactive feedback
- [ ] Tested in MCP host (ChatGPT/Claude)
- [ ] Mobile responsive

### Data & Logic
- [ ] Business logic verified correct
- [ ] Data handling edge cases covered
- [ ] Error responses meaningful
- [ ] API responses validated

### Model Context Sync
- [ ] Uses `updateModelContext` for user-initiated state changes
- [ ] Capability-gated (`getHostCapabilities()?.updateModelContext`)
- [ ] Payload uses YAML frontmatter + markdown format
- [ ] Sends deltas, not full state dumps
- [ ] Updates on semantic events (commit, not every keystroke)
- [ ] Scenario mode explicit (baseline vs what-if)

### Production
- [ ] Performance acceptable
- [ ] Slider/control latency < 150ms perceived
- [ ] Debounced apply pattern (not fire on every change)
- [ ] Visibility-aware (pause animations when offscreen)
- [ ] Rate limits / quotas handled
- [ ] Ready for real users

## Gold Tools

| Tool | Gold Date | Notes |
|------|-----------|-------|
| — | — | No tools have reached gold yet |

## Roadmap (Pre-Gold)

### `property_comps`

**Status:** Ready for Gold - pending production testing

UI:
- [x] BOUCH design system
- [x] Sortable transaction table
- [x] Search controls (months, area)
- [x] Subject property card
- [x] Works in ChatGPT host
- [x] Container padding for host environments

Data/Logic:
- [x] SPARQL query via Land Registry Linked Data API - verified in ppd_client.py
- [x] Percentile calculations use `statistics.quantiles()` - correct (ppd_service.py:352-354)
- [x] Subject property matching: parses PAON/street, falls back gracefully (ppd_service.py:386-459)
- [x] Subject filtered from comps, percentile position calculated correctly
- [x] Edge cases: thin_market flag, limit enforcement (MAX_LIMIT=200)
- [ ] Live test: edge case with no results
- [ ] Live test: invalid postcode handling

Model Context Sync:
- [x] `updateModelContext` called on Apply
- [x] Capability guard (`getHostCapabilities()?.updateModelContext`)
- [x] Delta tracking (previous → current params)
- [x] YAML frontmatter payload format
- [x] Debounced (fires on commit, not every slider move)

### `property_yield`

**Status:** Ready for Gold - pending production testing

UI:
- [x] BOUCH design system
- [x] Yield gauge with animation
- [x] Price slider for what-if
- [x] Search controls (months, radius, area)
- [x] Works in ChatGPT host

Data/Logic:
- [x] Yield formula: `(annual_rent / purchase_price) * 100` - correct gross yield (yield_service.py:106-107)
- [x] Assessment thresholds: 6%+ strong, 4%+ average, <4% weak - reasonable for UK market
- [x] Data quality tiers: good (5+/5+), low (2+/2+), insufficient - sensible (yield_service.py:117-122)
- [x] Rental data from Rightmove scraper, includes LET_AGREED (confirmed deals)
- [x] thin_market flag propagated from PPD comps
- [x] Edge cases: early exit on no sales/rental data, returns data_quality="insufficient"
- [ ] Live test: postcode with no rental listings
- [ ] Live test: thin market area

Model Context Sync:
- [x] `updateModelContext` called on Apply
- [x] Capability guard (`getHostCapabilities()?.updateModelContext`)
- [x] Delta tracking (previous → current params)
- [x] Scenario mode in payload (baseline vs what-if price)
- [x] YAML frontmatter payload format
- [x] Debounced (fires on commit, not every slider move)

**Note:** Median calculation uses floor-based approach (line 103) rather than `statistics.median()`.
Acceptable for typical sample sizes but could be improved for consistency.

---

## The Rule

> **You need `updateModelContext` when the model's next action depends on UI state the model didn't produce itself.**

- If user can change things locally (sliders, selection, navigation) → model needs to know
- If model can infer everything from tool results alone → skip it

This is why transcript/pdf/map examples use it: the user moves through state the model must track.

---

## Notes

- Gold = verified correct, not just working
- Screenshots of verified results should be added
- Version tagged in git when tool reaches gold
