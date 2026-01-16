# Property Shared API (scaffold)

FastAPI service + pure-Python core library for shared property capabilities (PPD, EPC, Rightmove, Location scoring). Currently scaffolded with a health route and minimal settings/logging (no DB/Redis assumptions in this repo).

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
   - Location (placeholder): `curl 'http://localhost:8000/v1/location/assess?postcode=SW1A%201AA'` (deterministic demo; projects should swap in their own assessor)

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
- `app/schemas/` – Pydantic models (EPC, location, more to come)
- `property_core/ppd_client.py` – vendored PPD helper from `pp_data`
- `app/tasks/`, `app/clients/`, `app/utils/` – API wrapper helpers (`app/utils/polite.py` for in-memory politeness)
- `example_ref/` – reference-only example code copied from other projects

## Local setup
1) Create venv: `python -m venv .venv && source .venv/bin/activate`
2) Install deps (later): `pip install fastapi uvicorn pydantic pydantic-settings httpx requests tenacity beautifulsoup4`
3) Copy `.env.example` to `.env` and fill values (EPC/OpenAI keys if used)
4) Run: `uvicorn app.main:app --reload`

## Notes
- Rightmove politeness is in-memory (`app/utils/polite.py`) for now; projects can swap in Redis later if needed.
- Rightmove search URLs built from full postcodes default to a small radius (0.25 miles) so the initial query returns results; override `radius` to widen/narrow the area in both the API and CLI.
- OpenAPI/SDK generation will be added after endpoints land.

## Rightmove CLI snippets
- Build a search URL: `uv run --extra cli property-cli rightmove search-url --postcode SW1A 1AA --property-type sale --radius 0.25`
- Fetch listings from a search URL: `uv run --extra cli property-cli rightmove listings --search-url "<rightmove_url>" --max-pages 1`

## Location CLI snippet
- Assess a postcode (placeholder): `uv run --extra cli property-cli location assess SW1A 1AA` (add `--api-url http://localhost:8000` to exercise the API; replace the assessor for real location intelligence)
