# Property Shared API (scaffold)

FastAPI service + pure-Python core library for shared property capabilities (PPD, EPC, Rightmove, Planning). Currently scaffolded with a health route and minimal settings/logging (no DB/Redis assumptions in this repo).

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
   - Planning search: `curl 'http://localhost:8000/v1/planning/search?postcode=SW1A%201AA'`

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
- `app/main.py` – app factory, lifespan setup
- `app/core/` – config + logging for the API wrapper
- `app/api/v1/` – versioned routers (health now; domain routers to follow)
- `app/services/` – reserved for API service wrappers (will call into `property_core/`)
- `app/schemas/` – Pydantic models (EPC, more to come)
- `property_core/planning_scraper.py` – Vision-guided planning portal scraper (Playwright + OpenAI)
- `property_core/planning_councils.json` – Verified council database (98 councils, 6 system types)
- `property_core/ppd_client.py` – vendored PPD helper from `pp_data`
- `app/tasks/`, `app/clients/`, `app/utils/` – API wrapper helpers (`app/utils/polite.py` for in-memory politeness)
- `example_ref/` – reference-only example code copied from other projects
- `USER_GUIDE.md` – quickstart and endpoint/CLI usage

## Local setup
1) Create venv: `python -m venv .venv && source .venv/bin/activate`
2) Install deps (later): `pip install fastapi uvicorn pydantic pydantic-settings httpx requests tenacity beautifulsoup4`
3) Copy `.env.example` to `.env` and fill values (EPC keys, OPENAI_API_KEY for planning scraper)
4) Run: `uvicorn app.main:app --reload`

## Notes
- Rightmove politeness is in-memory (`app/utils/polite.py`) for now; projects can swap in Redis later if needed.
- Rightmove search URLs built from full postcodes default to a small radius (0.25 miles) so the initial query returns results; override `radius` to widen/narrow the area in both the API and CLI.
- OpenAPI/SDK generation will be added after endpoints land.

## API I/O contracts (summary)
- `GET /v1/health` → `{ "status": "ok" }`
- `GET /v1/meta/integrations` → `{ environment, integrations: { ppd|rightmove|epc: { available, configured } } }`
- `GET /v1/ppd/download-url?kind=complete|monthly|year&year?&part?&fmt=csv|txt` → `{ url }`
- `GET /v1/ppd/transactions?postcode|postcode_prefix&limit&filters...&include_raw=bool` (one of postcode/postcode_prefix) → `{ count, limit, offset, results: [ { transaction_id, price, date, postcode, property_type, estate_type, transaction_category, new_build, paon, saon, street, town, county, locality, district } ], warnings, raw? }`
- `GET /v1/ppd/address-search?paon?&saon?&street?&town?&county?&postcode?&postcode_prefix?&limit&include_raw=bool` (requires ≥2 fields, limit≤50) → same shape as `/transactions`
- `GET /v1/ppd/comps?postcode&property_type?&months?&limit?&search_level=postcode|sector|district&enrich_epc=bool` → `{ query, count, median, mean, min, max, thin_market, transactions: [PPDTransaction] }` (when `enrich_epc=true`, each transaction gains `epc_floor_area_sqm`, `epc_floor_area_sqft`, `price_per_sqm`, `price_per_sqft`, `epc_rating`, `epc_score`, `epc_construction_age`, `epc_built_form`)
- `GET /v1/ppd/transaction/{id}?view=all|basic&include_raw=bool` → `{ record: { transaction_id, price_paid, transaction_date, property/transaction metadata... }, raw? }`
- `GET /v1/epc/search?postcode&address?&include_raw=bool` → `{ record, raw? }` (returns 501-style response if EPC creds not configured)
- `GET /v1/rightmove/search-url?postcode&property_type=sale|rent&radius?&min/max price/bedrooms?` → `{ url }`
- `GET /v1/rightmove/listings?search_url&max_pages?&include_raw=bool` → `{ count, results: [ { id, url, price, currency, bedrooms, bathrooms, address, summary, property_type, agent_name, agent_branch, first_visible_date, images, raw? } ] }`
- `GET /v1/rightmove/listing/{property_id}?include_raw=bool` → `{ result: { id, url, price, bedrooms, bathrooms, address, description, property_type, tenure_type, years_remaining_on_lease, annual_service_charge, annual_ground_rent, ground_rent_review_period_years, council_tax_band, latitude, longitude, floorplans, key_features, display_size, ... } }`
- `GET /v1/planning/search?postcode` → `{ postcode, local_authority, council_found, council, search_urls }`
- `GET /v1/planning/councils` → `{ verified_count, untested_count, councils, systems }`
- `GET /v1/planning/council-for-postcode?postcode&include_raw=bool` → `{ postcode, local_authority, council, council_found, postcode_data? }`
- `GET /v1/planning/council/{code}` → council details
- `POST /v1/planning/search-results` body: `{ postcode, portal_url?, system?, max_results? }` → `{ postcode, council_name, system, portal_url, results: [{ reference, address, description, status, link }], count }`
- `POST /v1/planning/scrape` body: `{ url, save_screenshots? }` → `{ url, council_system, screenshots_captured, data }`
- `POST /v1/planning/probe` body: `{ url, timeout_ms? }` → `{ url, success, page_title, blocking_indicators, error }`
- `POST /v1/property/report` body: `{ address, include_rentals?, include_sales_market?, ppd_months?, search_radius? }` → `PropertyReport { report_id, key_insights, estimated_value_low/high, sale_history, market_analysis, energy_performance, rental_analysis, current_market, sources }` (supports `?format=html`)

## Rightmove CLI snippets
- Build a search URL: `uv run --extra cli property-cli rightmove search-url --postcode SW1A 1AA --property-type sale --radius 0.25`
- Fetch listings from a search URL: `uv run --extra cli property-cli rightmove listings --search-url "<rightmove_url>" --max-pages 1`
- Fetch individual listing detail: `uv run --extra cli property-cli rightmove listing 161151632`

## Other CLI commands (core mode; add `--api-url` to hit the API)
- Meta integrations: `uv run --extra cli property-cli meta`
- PPD comps (postcode is positional): `uv run --extra cli property-cli ppd comps "SW1A 1AA" --months 24 --limit 20 --search-level sector`
- PPD comps with EPC enrichment: `uv run --extra cli property-cli ppd comps "B1 1BB" --search-level sector --enrich-epc`
- PPD transactions (postcode/prefix): `uv run --extra cli property-cli ppd search --postcode-prefix SW1A --limit 10`
- PPD transaction record: `uv run --extra cli property-cli ppd transaction 31C68072-E0B5-FEE3-E063-4804A8C04F37 --include-raw` (replace with a real transaction id)
- EPC search (requires EPC_API_EMAIL/EPC_API_KEY set): `uv run --extra cli property-cli epc search "SW1A 1AA" --address "10 Downing Street" --include-raw`
- Property report: `uv run --extra cli property-cli report generate "10 Downing Street, SW1A 2AA" -o report.html --html`
