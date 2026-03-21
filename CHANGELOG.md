# Changelog

## v1.3.0 (2026-03-21)

### Breaking Changes
- `yield_assessment` and `data_quality` fields on `YieldAnalysis` are no longer populated by `calculate_yield()` — they default to `None`. Use `property_core.interpret.classify_yield()` and `classify_data_quality()` instead.
- `yield_assessment` field on `RentalAnalysis` is no longer populated by `analyze_rentals()` — use `classify_yield()` on `gross_yield_pct`.
- `key_insights`, `estimated_value_low`, `estimated_value_high` fields on `PropertyReport` are no longer populated by `generate_report()` — use `generate_insights()` and `estimate_value_range()`.
- `price_vs_median` field on `MarketAnalysis` is no longer populated — `price_difference_pct` (raw number) is still computed. Use `classify_price_position()` for the label.
- `YieldAnalysis.data_quality` type changed from `str` (default `"insufficient"`) to `Optional[str]` (default `None`).
- `PropertyReportService.generate_report()` no longer accepts `value_range_pct` or `price_vs_median_pct` parameters.

### New Features
- **`property_core.interpret` module** — opt-in interpretation helpers: `classify_yield()`, `classify_data_quality()`, `classify_price_position()`, `estimate_value_range()`, `generate_insights()`. All exported from `property_core`.
- `PPDService.comps()` now accepts `thin_market_threshold` parameter (default 5) — previously hard-coded.

### Design
- **property_core returns numbers, consumers interpret them.** Services no longer generate assessment labels, quality judgments, insight text, or estimated value ranges. All raw data (yield %, counts, price difference %) is still returned. Consumers (MCP server, CLI) call interpret helpers for presentation.

## v1.2.0 (2026-03-21)

### Breaking Changes
- `calculate_stamp_duty()` default `additional_property` changed from `True` to `False` — callers that relied on the investor default must now pass `additional_property=True` explicitly
- `PPDService.comps()` default `auto_escalate` changed from `True` to `False` — callers that relied on auto-escalation must pass `auto_escalate=True` explicitly

### Configurable Defaults
- `calculate_yield()`: new `strong_yield_pct`, `average_yield_pct`, `min_comps_good` parameters for customizing yield assessment thresholds
- `analyze_rentals()`: new `filter_outliers` parameter (default True) to control IQR filtering on rent range, plus `strong_yield_pct` and `average_yield_pct` for yield thresholds
- `analyze_blocks()`: new `property_type` parameter (default "F") — pass `None` to search all property types
- `PropertyReportService.generate_report()`: new `value_range_pct` (default 15.0) and `price_vs_median_pct` (default 5.0) parameters for configurable interpretation thresholds

### New Features
- API: `GET /v1/analysis/yield` and `GET /v1/analysis/rental` endpoints
- API: `auto_escalate` query parameter on `GET /v1/ppd/comps`
- CLI: `property-cli analysis yield` and `property-cli analysis rental` commands
- CLI: PPD commands now use `PPDService` instead of raw `PricePaidDataClient` for consistent guardrails

### Fixed
- Model exports: `YieldAnalysis` now exported from `property_core.models`
- Top-level model imports: `PPDTransaction`, `EPCData`, `RightmoveListing`, `PropertyReport`, `BlockAnalysisResponse`, `CompanyRecord`, and more available directly from `property_core`
- API stamp duty default now matches core library default (`additional_property=False`)
- CLI stamp duty default now matches core library default (`--no-additional` by default)

### Removed
- `app/services/` wrapper layer — API routers now import directly from `property_core` (same pattern as MCP server and CLI). Removed `epc_service.py`, `rightmove_service.py`, and `app/utils/polite.py`

### Documentation
- Rewrote GUIDELINES.md to match actual code conventions (file naming, architecture, design principles)
- Updated CLAUDE.md: removed `app/services/` from architecture, fixed `raw` field description (transport models only), added new CLI commands and API endpoints, updated library import examples

## v1.1.2 (2026-03-20)

### Documentation
- Updated USER_GUIDE.md with accurate code examples — fixed broken method names, signatures, and imports
- Added Stamp Duty, Block Analyzer, Companies House, and MCP Server documentation sections
- Added runnable examples in docs/examples.py for all new features
- Removed stale UKHPI/location slice notes

## v1.1.1 (2026-03-19)

### MCP Server
- Rewrote MCP server with FastMCP v3 (`fastmcp>=3.0.0`) — expanded from 7 investor-focused tools to 12 covering full property_shared data surface
- New tools: `ppd_transactions`, `rightmove_search`, `rightmove_listing`, `planning_search`, `rental_analysis`
- Fixed ToolResult content for Claude.ai compatibility — `_slim()` + `_content()` helpers put full JSON data in `content[]` so all LLM hosts see the data, not just summary lines

### Bug Fixes
- Fixed Rightmove listing field mapping: `floor_area_sqft` → `display_size`, `tenure` → `tenure_type`
- Moved URI-based SPARQL filters (property_type, estate_type, etc.) to client-side post-fetch in ppd_client.py — fixes 503 timeouts from Land Registry endpoint

## v1.1.0 (2026-03-18)

### New Features
- **Stamp Duty Calculator**: `calculate_stamp_duty()` — April 2025 SDLT bands with additional property (+5%), non-resident (+2%), and first-time buyer relief. API: `GET /v1/calculators/stamp-duty`, CLI: `property-cli calc stamp-duty`
- **Block Analyzer**: `analyze_blocks()` — groups PPD flat transactions by building to find blocks with multiple unit sales (investor exits, bulk-buy opportunities). API: `GET /v1/ppd/blocks`, CLI: `property-cli ppd blocks`
- **Companies House Client**: `CompaniesHouseClient` — search by name or lookup by company number, returns typed models with officers. API: `GET /v1/companies/search`, `GET /v1/companies/{number}`, CLI: `property-cli companies search`

### MCP Server
- Added `stamp_duty` and `property_blocks` tools

## v1.0.0 (2026-03-18)

First public release. Full-featured UK property data library + API.

### Core Library (`property_core`)
- **PPD (Price Paid Data)**: Land Registry transactions via SPARQL + Linked Data API with typed Pydantic models, address search, comps with area stats (median, percentiles, subject property comparison)
- **EPC**: Energy Performance Certificate lookup (async), enrichment pipeline for PPD comps with fuzzy address matching — adds floor area, price/sqft, EPC rating to transactions
- **Rightmove**: Listings scraper with search URL builder, individual listing detail (tenure, floorplans, station distances), rental analysis with IQR outlier filtering
- **Planning**: Council matching for 98 verified UK councils (6 system types), vision-guided Playwright + OpenAI scraper for planning applications
- **Yield Analysis**: PPD sales + Rightmove rentals → gross yield with market assessment
- **Property Reports**: Multi-source aggregation (PPD + EPC + Rightmove) → structured report with key insights, estimated value range, energy performance, rental analysis
- **Postcode**: postcodes.io lookup → typed PostcodeResult model
- **Typed throughout**: All transport clients and domain services return Pydantic v2 models with `raw` field carrying original source data

### API (`app`)
- FastAPI service with versioned routers (`/v1/`)
- Endpoints: health, meta, PPD (transactions, comps, address-search, download-url), EPC search, Rightmove (search-url, listings, listing detail), property report
- Async threading for sync scrapers, in-memory rate limiting for Rightmove
- Demo UI at `/demo`
- Deployed on Fly.io (LHR region)

### CLI (`property_cli`)
- Typer CLI with dual mode: core direct (fast, no server) or API mode (`--api-url`)
- Commands: meta, ppd (comps, search, transaction), epc search, rightmove (search-url, listings, listing), report generate

### MCP Server (`mcp_server`)
- FastMCP server exposing `property_comps` and `property_yield` tools
- Svelte UI for interactive dashboards (BOUCH design system)
- Model Context Sync for AI host state management
- Compatible with Claude.ai and ChatGPT MCP hosts

### Infrastructure
- Published to PyPI as `property-shared`
- Hatch build system with wheel/sdist
- `.dockerignore` and build excludes for clean images
- Fly.io deployment with auto-stop machines
