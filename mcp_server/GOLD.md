# MCP Tools - Gold Status

## What is Gold?

A tool reaches **gold** when it meets all criteria:

- [ ] BOUCH design system applied
- [ ] Interactive UI with reactive feedback
- [ ] `app.callServerTool()` re-query working
- [ ] Tested in ChatGPT host (interactions verified)
- [ ] Tested in Claude host (if available)
- [ ] Error states polished
- [ ] Mobile responsive
- [ ] Ready for production use

## Gold Tools

| Tool | Gold Date | Notes |
|------|-----------|-------|
| — | — | No tools have reached gold yet |

## Roadmap (Pre-Gold)

### `property_comps`

**Status:** Beta - BOUCH styled, needs interaction testing

- [x] BOUCH design system
- [x] Sortable transaction table
- [x] Search controls (months, area)
- [x] Subject property card
- [ ] Verify sorting works in ChatGPT
- [ ] Verify Apply button re-queries
- [ ] Test error states
- [ ] Mobile testing

### `property_yield`

**Status:** Beta - BOUCH styled, needs interaction testing

- [x] BOUCH design system
- [x] Yield gauge with animation
- [x] Price slider for what-if
- [x] Search controls (months, radius, area)
- [ ] Verify slider updates gauge in ChatGPT
- [ ] Verify Apply button re-queries
- [ ] Test thin market warning
- [ ] Mobile testing

---

## Notes

- Gold certification requires manual verification in actual MCP hosts
- Screenshots of working interactions should be added to docs when gold
- Version tagged in git when tool reaches gold
