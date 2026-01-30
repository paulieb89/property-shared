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

### Production
- [ ] Performance acceptable
- [ ] Rate limits / quotas handled
- [ ] Ready for real users

## Gold Tools

| Tool | Gold Date | Notes |
|------|-----------|-------|
| — | — | No tools have reached gold yet |

## Roadmap (Pre-Gold)

### `property_comps`

**Status:** Beta - UI complete, data logic needs review

UI:
- [x] BOUCH design system
- [x] Sortable transaction table
- [x] Search controls (months, area)
- [x] Subject property card
- [x] Works in ChatGPT host

Data/Logic:
- [ ] Verify SPARQL query returns correct data
- [ ] Check percentile calculations
- [ ] Validate subject property matching
- [ ] Edge case: no results
- [ ] Edge case: invalid postcode

### `property_yield`

**Status:** Beta - UI complete, data logic needs review

UI:
- [x] BOUCH design system
- [x] Yield gauge with animation
- [x] Price slider for what-if
- [x] Search controls (months, radius, area)
- [x] Works in ChatGPT host

Data/Logic:
- [ ] Verify yield calculation formula
- [ ] Check rental data source accuracy
- [ ] Validate thin_market threshold
- [ ] Edge case: no sales data
- [ ] Edge case: no rental data

---

## Notes

- Gold = verified correct, not just working
- Screenshots of verified results should be added
- Version tagged in git when tool reaches gold
