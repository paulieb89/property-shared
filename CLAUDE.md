# CLAUDE.md

@GUIDELINES.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Property Shared is a FastAPI service + pure-Python core library for UK property data. It integrates:
- **PPD** (Price Paid Data) - Land Registry transactions via SPARQL/Linked Data API
- **EPC** - Energy Performance Certificates (requires API credentials)
- **Rightmove** - Property listings via scraping with built-in politeness
- **Planning** - UK council planning applications via vision-guided browser automation (99 verified councils)
- **Stamp Duty** - SDLT calculator with April 2025 bands, additional property/FTB/non-resident surcharges
- **Block Analyzer** - Groups PPD transactions by building to find bulk-buy opportunities
- **Companies House** - Company search and lookup via free API (requires API key)

## Commands

```bash
# Install dependencies (with dev extras)
uv sync --extra dev

# Run API server
uv run property-api                              # production mode
uv run uvicorn app.main:app --reload             # dev mode with reload

# Run CLI (core mode - no server needed)
uv run --extra cli property-cli meta
uv run --extra cli property-cli ppd comps "SW1A 1AA" --months 24
uv run --extra cli property-cli rightmove search-url "SW1A 1AA"
uv run --extra cli property-cli calc stamp-duty 300000
uv run --extra cli property-cli ppd blocks "B1 1AA"
uv run --extra cli property-cli companies search "Tesco"
uv run --extra cli property-cli analysis yield "NG1 1AA"
uv run --extra cli property-cli analysis rental "NG1 1AA"

# CLI targeting running API (add --api-url)
uv run --extra cli property-cli ppd comps "SW1A 1AA" --api-url http://localhost:8000

# Tests
uv run --extra dev pytest                        # unit tests (mocked)
RUN_LIVE_TESTS=1 uv run --extra dev pytest       # live network tests

# Single test
uv run --extra dev pytest tests/test_ppd_service_live.py -v
```

## Architecture

```
property_core/              # Pure Python library (no FastAPI, no DB assumptions)
├── models/                 # Domain Pydantic models
│   ├── ppd.py              # PPDTransaction, PPDCompsResponse, SubjectProperty, etc.
│   ├── epc.py              # EPCData
│   ├── rightmove.py        # RightmoveListing, RightmoveListingDetail
│   ├── report.py           # PropertyReport, YieldAnalysis, RentalAnalysis, etc.
│   ├── block.py            # BlockUnit, BlockBuilding, BlockAnalysisResponse
│   └── companies_house.py  # CompanyRecord, CompanySearchResult, CompanyOfficer
├── ppd_client.py           # Transport: Land Registry SPARQL + Linked Data API → typed models
├── epc_client.py           # Transport: EPC registry (async) → typed EPCData models
├── rightmove_scraper.py    # Transport: listings scraper (sync) → typed Pydantic models
├── rightmove_location.py   # Transport: search URL builder (sync)
├── postcode_client.py      # Transport: postcodes.io → typed PostcodeResult model
├── companies_house_client.py # Transport: Companies House API (sync httpx, basic auth)
├── ppd_service.py          # Domain service: PPD comps, search, stats (sync)
├── planning_service.py     # Domain service: council matching + URL building (sync)
├── report_service.py       # Orchestrator: multi-source aggregation (async)
├── rental_service.py       # Rental analysis with optional yield calculation (async)
├── yield_service.py        # Yield analysis: PPD sales + Rightmove rentals → YieldAnalysis
├── interpret.py            # Opt-in interpretation helpers (classify_yield, generate_insights, etc.)
├── enrichment.py           # EPC enrichment pipeline + compute_enriched_stats()
├── address_matching.py     # Fuzzy address matching for EPC enrichment
├── stamp_duty.py           # SDLT calculator: April 2025 bands, surcharges, FTB relief
├── block_service.py        # Block analyzer: groups PPD transactions by building
├── planning_scraper.py     # Vision-guided planning portal scraper (Playwright + OpenAI)
└── planning_councils.json  # Verified council database (99 councils, 6 system types)

app/                        # FastAPI service (thin HTTP wrapper)
├── api/v1/                 # Versioned routers (import directly from property_core)
├── schemas/                # API envelope models (convenience re-exports from core)
├── core/config.py          # Settings via pydantic-settings (reads .env)
└── web/                    # Demo UI at /demo

property_cli/               # Typer CLI (imports only from property_core)
└── main.py                 # All commands; --api-url switches to HTTP mode

mcp_server/                 # MCP server for AI hosts (wraps property_core)
├── server.py               # FastMCP tools + resources
└── mcp-app/                # Svelte UI for interactive results
```

**Three-layer separation**:
- Transport clients (HTTP/SPARQL → typed Pydantic models)
- Domain services (orchestration → typed Pydantic models)
- Consumer layers: API, MCP, CLI (all import directly from property_core)

**Data flow**: Consumer → Core service (domain logic) → Core client (network)

## Key Patterns

- **Dual-mode CLI**: Commands call `property_core` directly by default (fast, offline-capable). Add `--api-url` to route through the HTTP API instead.
- **Domain service guardrails**: `property_core/ppd_service.py` enforces limits (MAX_LIMIT=200, FORM_MAX_LIMIT=50) and normalizes responses. API routers are thin wrappers.
- **`raw` field pattern**: Transport-parsed models carry a `raw: dict | None` field (PPDTransaction, EPCData, RightmoveListing, CompanyRecord, PostcodeResult). Report, block, planning, and aggregate models do NOT have raw fields.
- **Core returns data, consumers interpret**: `property_core` services return raw numbers only (yield %, counts, price differences). Interpretation labels ("strong"/"weak", "good"/"insufficient", key insights) are generated by consumers using opt-in helpers from `property_core.interpret` — `classify_yield()`, `classify_data_quality()`, `classify_price_position()`, `estimate_value_range()`, `generate_insights()`.
- **Configurable defaults**: Parameters have defaults but are overridable — `auto_escalate=False`, `additional_property=False`, `filter_outliers=True`, `property_type="F"`, `thin_market_threshold=5`.
- **Area stats**: `PPDCompsResponse` includes `percentile_25`, `percentile_75` for price quartiles. When an address is provided and found, also includes `subject_price_percentile` (0-100) and `subject_vs_median_pct` (e.g., +10.8 means 10.8% above median).
- **EPC enrichment**: PPD comps can be enriched with EPC floor area via `enrich_epc=true` on the comps endpoint (or `--enrich-epc` in CLI). Groups comps by postcode, fetches all EPC certs per postcode (one API call each), fuzzy-matches addresses, and attaches derived fields (`epc_floor_area_sqm`, `price_per_sqft`, `epc_rating`, etc.) plus the full matched cert (`epc_match`) and confidence score (`epc_match_score`). After enrichment, call `compute_enriched_stats()` to populate `median_price_per_sqft` and `epc_match_rate`.
- **Standalone rental analysis**: `analyze_rentals(postcode, purchase_price=N, filter_outliers=True)` returns rental market stats (median/average rent, listing count) with optional gross yield calculation. Rental range uses IQR-based outlier filtering by default.
- **Station distance rounding**: `fetch_listing()` rounds station distances to 1 decimal place (e.g., "1.9 miles" not "1.8666295329683218 miles").
- **Live test gating**: Tests making real network calls check `RUN_LIVE_TESTS=1` and skip gracefully on 503 or missing credentials.

## Environment Variables

Copy `.env.example` to `.env`. Key variables:
- `EPC_API_EMAIL` / `EPC_API_KEY` - Required for EPC endpoints
- `RIGHTMOVE_DELAY_SECONDS` - Rate limit delay (default 0.6s)
- `OPENAI_API_KEY` - Required for planning scraper (vision extraction)
- `PLAYWRIGHT_PROXY_URL` - Optional residential proxy for planning scraper (councils block datacenter IPs)
- `COMPANIES_HOUSE_API_KEY` - Required for Companies House endpoints (free key from https://developer.company-information.service.gov.uk/)
- `COMPANIES_HOUSE_SANDBOX` - Set to `true` to use sandbox API (default `false`)

## Using as a Library

Install from PyPI: `pip install property-shared`

```python
# Services and functions
from property_core import PPDService, PlanningService, PropertyReportService
from property_core import PricePaidDataClient, EPCClient, RightmoveLocationAPI, PostcodeClient
from property_core import CompaniesHouseClient, analyze_blocks
from property_core import fetch_listings, fetch_listing, analyze_rentals
from property_core import calculate_yield, calculate_stamp_duty
from property_core import enrich_comps_with_epc, compute_enriched_stats

# Models (available at top level since v1.2)
from property_core import (
    PPDTransaction, PPDCompsResponse, PPDTransactionRecord,
    EPCData, RightmoveListing, RightmoveListingDetail,
    PropertyReport, YieldAnalysis, RentalAnalysis,
    BlockAnalysisResponse, CompanyRecord, StampDutyResult,
)

# Planning scraper (requires playwright, openai)
from property_core.planning_scraper import scrape_planning_application, search_planning_by_postcode
```

## MCP Server

The MCP server (`mcp_server/`) wraps property_core for AI hosts (ChatGPT, Claude). See `mcp_server/README.md` for details.
Path-specific rules load automatically when editing MCP server files.
