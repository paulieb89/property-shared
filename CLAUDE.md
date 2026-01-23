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
property_core/          # Pure Python library (no FastAPI, no DB assumptions)
├── ppd_client.py       # Land Registry SPARQL + Linked Data API
├── epc_client.py       # EPC registry (async, needs EPC_API_EMAIL/EPC_API_KEY)
├── rightmove_scraper.py # Listings scraper with rate limiting
├── rightmove_location.py # Search URL builder (uses location autocomplete)
├── planning_scraper.py # Vision-guided planning portal scraper (Playwright + OpenAI)
└── planning_councils.json # Verified council database (98 councils, 6 system types)

app/                    # FastAPI service wrapping property_core
├── api/v1/             # Versioned routers: health, ppd, epc, rightmove, planning, meta
├── services/           # Service layer with validation/limits on top of core
├── schemas/            # Pydantic request/response models
├── core/config.py      # Settings via pydantic-settings (reads .env)
└── web/                # Demo UI at /demo

property_cli/           # Typer CLI with dual mode (core direct vs API)
└── main.py             # All commands; --api-url switches to HTTP mode
```

**Data flow**: API router → Service (validation/limits) → Core client (network)

## Key Patterns

- **Dual-mode CLI**: Commands call `property_core` directly by default (fast, offline-capable). Add `--api-url` to route through the HTTP API instead.
- **Service layer guardrails**: `app/services/` enforces limits (MAX_LIMIT=200, FORM_MAX_LIMIT=50) and normalizes responses before returning to API.
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
# Core clients (no HTTP, no FastAPI)
from property_core import PricePaidDataClient, EPCClient, RightmoveLocationAPI, fetch_listings

# Planning scraper (requires playwright, openai)
from property_core.planning_scraper import scrape_planning_application, search_planning_by_postcode

# Service layer (includes validation/limits, Pydantic schemas)
from app.services.epc_service import EPCService
from app.services.rightmove_service import RightmoveService
from app.services.planning_service import PlanningService
```
