# Property Shared

FastAPI service + pure-Python core library for UK property data. Integrates Land Registry (PPD), EPC, Rightmove, Planning portal lookup (98 councils), Stamp Duty calculator, Block Analyzer, and Companies House. Use as a library, HTTP API, CLI, or MCP server.

## How to run
### Dev (uv)
1) Create `.env` from `.env.example` (set `EPC_API_EMAIL`/`EPC_API_KEY` if you want EPC enabled)
2) Install deps: `uv sync --extra dev`
3) Run API: `uv run property-api` (or `uv run uvicorn app.main:app --reload`)
4) CLI (core mode): `uv run --extra cli property-cli meta` (add `--api-url http://localhost:8000` to hit the running API instead of local core)
5) Demo UI: visit `http://localhost:8000/demo` (served by the same FastAPI app)
6) Quick checks:
   - Health: `curl http://localhost:8000/v1/health`
   - Integration status: `curl http://localhost:8000/v1/meta/integrations`
   - Rightmove: `curl 'http://localhost:8000/v1/rightmove/search-url?postcode=SW1A%201AA&radius=0.25'`
     then `curl 'http://localhost:8000/v1/rightmove/listings?search_url=<pasted_url>&max_pages=1'`
   - PPD address search: `curl 'http://localhost:8000/v1/ppd/address-search?postcode_prefix=B1&street=Broad%20Street&limit=5'`
   - PPD comps: `curl 'http://localhost:8000/v1/ppd/comps?postcode=NG1%201GF&months=24&limit=5'`
   - Yield analysis: `curl 'http://localhost:8000/v1/analysis/yield?postcode=NG1%201AA'`
   - Rental analysis: `curl 'http://localhost:8000/v1/analysis/rental?postcode=NG1%201AA'`

### Live integration tests
Live tests make real network calls and are gated:
- Run: `RUN_LIVE_TESTS=1 uv run --extra dev pytest -q -s`

### Fly.io (high-level)
- Set secrets: `fly secrets set EPC_API_EMAIL=... EPC_API_KEY=...`
- Deploy: `fly deploy`

## Python SDK (OpenAPI)
Generate a typed client from the running service OpenAPI:
1) Run the API: `uv run uvicorn app.main:app --reload`
2) Generate client: `uv run --extra dev openapi-python-client generate --url http://localhost:8000/openapi.json --output-path clients/python`

## Structure
- `property_core/` – pure-Python core library (no FastAPI, no DB/Redis assumptions)
  - `models/` – domain Pydantic models (PPDTransaction, EPCData, PropertyReport, YieldAnalysis, etc.)
  - `ppd_client.py` – transport: Land Registry SPARQL + Linked Data API
  - `epc_client.py` – transport: EPC registry (async)
  - `rightmove_scraper.py` – transport: listings scraper (sync)
  - `rightmove_location.py` – transport: search URL builder
  - `postcode_client.py` – transport: postcodes.io
  - `companies_house_client.py` – transport: Companies House API
  - `ppd_service.py` – domain service: PPD comps, search, stats
  - `planning_service.py` – domain service: council matching + URL building
  - `report_service.py` – orchestrator: multi-source aggregation (async)
  - `rental_service.py` – rental analysis with optional yield calculation (async)
  - `yield_service.py` – yield analysis: PPD sales + Rightmove rentals
  - `enrichment.py` – EPC enrichment pipeline for PPD comps
  - `address_matching.py` – fuzzy address matching for EPC enrichment
  - `stamp_duty.py` – SDLT calculator (April 2025 bands)
  - `block_service.py` – groups transactions by building
  - `planning_scraper.py` – vision-guided planning portal scraper (Playwright + OpenAI)
  - `planning_councils.json` – verified council database (98 councils, 6 system types)
- `app/` – FastAPI service wrapping property_core
  - `api/v1/` – versioned routers (import directly from property_core)
  - `schemas/` – API envelope models (convenience re-exports from core)
  - `core/config.py` – settings via pydantic-settings
- `property_cli/` – Typer CLI with dual mode (core direct vs API)
- `mcp_server/` – MCP server for AI hosts (12 tools wrapping property_core)
- `docs/` – examples and reference documentation
- `USER_GUIDE.md` – quickstart and endpoint/CLI usage

## Using as a library

```
pip install property-shared
```

```python
from property_core import (
    PPDService, PropertyReportService, PlanningService,
    EPCClient, CompaniesHouseClient,
    calculate_yield, analyze_rentals, analyze_blocks, calculate_stamp_duty,
    fetch_listings, fetch_listing,
)

# Models available at top level
from property_core import (
    PPDTransaction, PPDCompsResponse, EPCData,
    RightmoveListing, PropertyReport, YieldAnalysis,
    BlockAnalysisResponse, CompanyRecord, StampDutyResult,
)
```

## Local setup
1) Copy `.env.example` to `.env` and fill values (EPC keys, OPENAI_API_KEY for planning scraper)
2) Install deps: `uv sync --extra dev`
3) Run: `uv run property-api` (or `uv run uvicorn app.main:app --reload`)

## Notes
- Transport-parsed models (PPDTransaction, EPCData, RightmoveListing, CompanyRecord, PostcodeResult) carry a `raw` field with original source data. Report, block, and aggregate models do not.
- Rightmove scraper has built-in rate limiting via `rate_limit_seconds` parameter.
- Rightmove search URLs default to a small radius (0.25 miles); override `radius` to widen/narrow.
- Station distances in listing details are rounded to 1 decimal place (e.g., "1.9 miles").
- Rental analysis (`analyze_rentals`) uses IQR-based outlier filtering by default (`filter_outliers=True`).
- Opinionated defaults are configurable: yield thresholds, outlier filtering, auto-escalation, value ranges, property type filters all accept parameters.
- See `docs/examples.md` for copy-paste usage examples with real output.

## API endpoints (summary)
- `GET /v1/health` → `{ "status": "ok" }`
- `GET /v1/meta/integrations` → `{ environment, integrations: { ppd|rightmove|epc: { available, configured } } }`
- `GET /v1/ppd/download-url?kind=complete|monthly|year&year?&part?&fmt=csv|txt` → `{ url }`
- `GET /v1/ppd/transactions?postcode|postcode_prefix&limit&filters...&include_raw=bool` → `{ count, limit, offset, results, warnings, raw? }`
- `GET /v1/ppd/address-search?paon?&saon?&street?&town?&...&limit&include_raw=bool` (requires >=2 fields, limit<=50)
- `GET /v1/ppd/comps?postcode&property_type?&months?&limit?&search_level&auto_escalate&enrich_epc` → `{ query, count, median, mean, min, max, thin_market, transactions }`
- `GET /v1/ppd/blocks?postcode&months?&limit?&min_transactions?&search_level?` → `{ postcode, blocks_found, blocks }`
- `GET /v1/ppd/transaction/{id}?view=all|basic&include_raw=bool` → `{ record, raw? }`
- `GET /v1/epc/search?postcode&address?&include_raw=bool` → `{ record, raw? }`
- `GET /v1/epc/certificate/{hash}?include_raw=bool` → `{ record, raw? }`
- `GET /v1/rightmove/search-url?postcode&property_type=sale|rent&radius?&filters...` → `{ url }`
- `GET /v1/rightmove/listings?search_url&max_pages?` → `{ count, results }`
- `GET /v1/rightmove/listing/{property_id}` → `{ result }`
- `GET /v1/analysis/yield?postcode&months?&search_level?&radius?` → `YieldAnalysis`
- `GET /v1/analysis/rental?postcode&radius?&purchase_price?` → `RentalAnalysis`
- `GET /v1/calculators/stamp-duty?price&additional_property&first_time_buyer&non_resident` → `StampDutyResult`
- `GET /v1/companies/search?q&limit?` → company results
- `POST /v1/property/report` body: `{ address, include_rentals?, include_sales_market?, ppd_months?, search_radius? }` → `PropertyReport`
- Planning routes exist in code but are **disabled** — scraping requires a UK residential IP.

## CLI commands (core mode; add `--api-url` to hit the API)
- `property-cli meta` – integration status
- `property-cli ppd comps "SW1A 1AA" --months 24` – comparable sales
- `property-cli ppd comps "B1 1BB" --enrich-epc` – comps with EPC enrichment
- `property-cli ppd search --postcode-prefix SW1A --limit 10` – transaction search
- `property-cli ppd address-search --postcode "SW1A 2AA" --street "Downing Street"` – address search
- `property-cli ppd transaction <ID>` – single transaction record
- `property-cli ppd blocks "B1 1AA"` – flat blocks analysis
- `property-cli epc search "SW1A 1AA"` – EPC lookup
- `property-cli rightmove search-url "SW1A 1AA"` – build search URL
- `property-cli rightmove listings --search-url "<url>"` – fetch listings
- `property-cli rightmove listing 161151632` – listing detail
- `property-cli analysis yield "NG1 1AA"` – rental yield analysis
- `property-cli analysis rental "NG1 1AA"` – rental market analysis
- `property-cli calc stamp-duty 300000` – stamp duty calculation
- `property-cli companies search "Tesco"` – Companies House lookup
- `property-cli report generate "10 Downing Street, SW1A 2AA"` – full property report
