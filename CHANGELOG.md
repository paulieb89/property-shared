# Changelog

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
