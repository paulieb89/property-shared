# Changelog

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
