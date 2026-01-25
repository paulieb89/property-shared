# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Property Shared is a FastAPI service + pure-Python core library for UK property data. It integrates:
- **PPD** (Price Paid Data) - Land Registry transactions via SPARQL/Linked Data API
- **EPC** - Energy Performance Certificates (requires API credentials)
- **Rightmove** - Property listings via scraping with built-in politeness
- **Planning** - UK council planning applications via vision-guided browser automation (98 verified councils)

## Commands

# Start .venv

``bash
act 
```

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
│   └── report.py           # PropertyReport, SaleHistory, MarketAnalysis, etc.
├── ppd_client.py           # Transport: Land Registry SPARQL + Linked Data API → dicts
├── epc_client.py           # Transport: EPC registry (async) → dicts/tuples
├── rightmove_scraper.py    # Transport: listings scraper (sync) → dataclasses
├── rightmove_location.py   # Transport: search URL builder (sync)
├── postcode_client.py      # Transport: postcodes.io → dicts
├── ppd_service.py          # Domain service: SPARQL parsing → typed PPD models (sync)
├── planning_service.py     # Domain service: council matching + URL building (sync)
├── report_service.py       # Product pipeline: multi-source aggregation (async)
├── rental_service.py       # Standalone rental analysis with yield calculation (async)
├── enrichment.py           # EPC enrichment pipeline + compute_enriched_stats()
├── planning_scraper.py     # Vision-guided planning portal scraper (Playwright + OpenAI)
└── planning_councils.json  # Verified council database (98 councils, 6 system types)

app/                        # FastAPI service (thin HTTP wrapper)
├── api/v1/                 # Versioned routers (import services from property_core)
├── services/               # API-specific adapters (async threading, config binding)
│   ├── epc_service.py      # Config-binding wrapper around EPCClient
│   └── rightmove_service.py # anyio.to_thread + PoliteLimiter
├── schemas/                # API envelope models (import domain models from core)
├── core/config.py          # Settings via pydantic-settings (reads .env)
└── web/                    # Demo UI at /demo

property_cli/               # Typer CLI (imports only from property_core)
└── main.py                 # All commands; --api-url switches to HTTP mode
```

**Three-layer separation**:
- Transport clients (raw HTTP/SPARQL → dicts)
- Domain services (parsing + orchestration → typed Pydantic models)
- API layer (envelopes, async threading, rate limiting)

**Data flow**: API router → Core service (domain logic) → Core client (network)

## Key Patterns

- **Dual-mode CLI**: Commands call `property_core` directly by default (fast, offline-capable). Add `--api-url` to route through the HTTP API instead.
- **Domain service guardrails**: `property_core/ppd_service.py` enforces limits (MAX_LIMIT=200, FORM_MAX_LIMIT=50) and normalizes responses. API routers are thin wrappers.
- **`include_raw` pattern**: All endpoints normalize data by default. Pass `include_raw=true` to get the original source data alongside normalized fields. EPC, PPD (transactions/address-search), Rightmove (listings), and Planning (council-for-postcode) all support this.
- **Area stats**: `PPDCompsResponse` includes `percentile_25`, `percentile_75` for price quartiles. When an address is provided and found, also includes `subject_price_percentile` (0-100) and `subject_vs_median_pct` (e.g., +10.8 means 10.8% above median).
- **EPC enrichment**: PPD comps can be enriched with EPC floor area via `enrich_epc=true` on the comps endpoint (or `--enrich-epc` in CLI). Groups comps by postcode, fetches all EPC certs per postcode (one API call each), fuzzy-matches addresses, and attaches derived fields (`epc_floor_area_sqm`, `price_per_sqft`, `epc_rating`, etc.) plus the full matched cert (`epc_match`) and confidence score (`epc_match_score`). After enrichment, call `compute_enriched_stats()` to populate `median_price_per_sqft` and `epc_match_rate`.
- **Standalone rental analysis**: `analyze_rentals(postcode, purchase_price=N)` returns rental market stats (median/average rent, listing count) with optional gross yield calculation. No full report needed.
- **Live test gating**: Tests making real network calls check `RUN_LIVE_TESTS=1` and skip gracefully on 503 or missing credentials.

## Environment Variables

Copy `.env.example` to `.env`. Key variables:
- `EPC_API_EMAIL` / `EPC_API_KEY` - Required for EPC endpoints
- `RIGHTMOVE_DELAY_SECONDS` - Rate limit delay (default 0.6s)
- `OPENAI_API_KEY` - Required for planning scraper (vision extraction)
- `PLAYWRIGHT_PROXY_URL` - Optional residential proxy for planning scraper (councils block datacenter IPs)

## Using as a Library

Install in another project: `pip install /path/to/property_shared` or add to dependencies.

```python
# Domain services (typed models, no FastAPI needed)
from property_core import PPDService, PlanningService, PropertyReportService

# Transport clients (raw dicts)
from property_core import PricePaidDataClient, EPCClient, RightmoveLocationAPI, fetch_listings, PostcodeClient
from property_core import enrich_comps_with_epc, compute_enriched_stats, fetch_listing, analyze_rentals

# Domain models
from property_core.models.ppd import PPDTransaction, PPDCompsResponse
from property_core.models.epc import EPCData
from property_core.models.report import PropertyReport

# Planning scraper (requires playwright, openai)
from property_core.planning_scraper import scrape_planning_application, search_planning_by_postcode
```
