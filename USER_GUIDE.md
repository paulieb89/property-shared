# Property Shared API — User Guide

## Setup
1) Create `.env` from `.env.example` (set `EPC_API_EMAIL`/`EPC_API_KEY` if you want EPC enabled).
2) Install dependencies: `uv sync --extra dev`.
3) Run the API: `uv run property-api` (or `uv run uvicorn app.main:app --reload`).
4) Open the demo UI: http://localhost:8000/demo.

## Key CLI commands (core mode; add `--api-url http://localhost:8000` to hit the API)
- Meta: `uv run --extra cli property-cli meta`
- PPD comps: `uv run --extra cli property-cli ppd comps "SW1A 1AA" --months 24 --limit 20 --search-level sector`
- PPD transactions: `uv run --extra cli property-cli ppd search --postcode-prefix SW1A --limit 10`
- PPD transaction record: `uv run --extra cli property-cli ppd transaction <transaction_id> --include-raw`
- PPD address search: `uv run --extra cli property-cli ppd search --postcode-prefix B1 --limit 5` (API has `/v1/ppd/address-search` for form-style filters)
- Rightmove search URL: `uv run --extra cli property-cli rightmove search-url "SW1A 1AA" --property-type sale --radius 0.25`
- Rightmove listings: `uv run --extra cli property-cli rightmove listings "<search_url>" --max-pages 1`
- EPC search (requires creds): `uv run --extra cli property-cli epc search "SW1A 1AA" --address "10 Downing Street" --include-raw`

## API quick hits
- Health: `GET /v1/health`
- Integrations: `GET /v1/meta/integrations`
- PPD:
  - `/v1/ppd/transactions?postcode=SW1A%201AA&limit=20`
  - `/v1/ppd/address-search?postcode_prefix=B1&street=Broad%20Street&limit=5` (requires ≥2 fields; limit≤50)
  - `/v1/ppd/comps?postcode=SW1A%201AA&months=24&limit=20&search_level=sector`
  - `/v1/ppd/transaction/{id}?include_raw=true`
- Rightmove:
  - `/v1/rightmove/search-url?postcode=SW1A%201AA&property_type=sale&radius=0.25`
  - `/v1/rightmove/listings?search_url=<url>&max_pages=1`
- EPC: `/v1/epc/search?postcode=SW1A%201AA&address=10%20Downing%20Street&include_raw=true` (requires EPC creds)

## Live tests
Live calls are gated. Run with:
`RUN_LIVE_TESTS=1 uv run --extra dev pytest -q tests`
The suite skips if credentials are missing or upstream services return 503.

## Notes and gaps
- Location slice was removed; projects can supply their own location intelligence.
- UKHPI endpoints are not implemented yet.
- Rightmove scraping is polite by default (delay + concurrency limits); respect upstream rate limits.
