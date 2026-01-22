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
# Search by address fields (requires at least 2)
property-cli ppd address-search --postcode "SW1A 2AA" --street "Downing"
property-cli ppd address-search --town "London" --street "Baker" --paon "221B"

# Get bulk download URLs
property-cli ppd download-url --kind complete          # Full dataset
property-cli ppd download-url --kind year --year 2024  # Year archive
property-cli ppd download-url --kind monthly           # Latest monthly

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

## Using as a Python package (in-process)
You can import the core logic directly without running the API:

### Install
- From the repo root: `uv sync --extra cli` (or your preferred env manager).
- Or install editable for reuse in another project: `pip install -e /path/to/property_shared`.

### Core imports (no HTTP)
Convenience imports from `property_core`:
```python
from property_core import PricePaidDataClient, EPCClient, RightmoveLocationAPI, fetch_listings
```

- PPD:
  - `from property_core import PricePaidDataClient`
  - Examples:
    - `client.get_comps_summary(postcode="SW1A 1AA", months=24, limit=20, search_level="sector")`
    - `client.sparql_search(postcode_prefix="SW1A", limit=10)`
    - `client.form_search(postcode_prefix="B1", street="Broad Street", limit=5)` (address-form; requires ≥2 fields)
    - `client.get_transaction_record("<transaction_id>")`
- EPC:
  - `from property_core import EPCClient`
  - Requires `EPC_API_EMAIL`/`EPC_API_KEY` in env; call `client.search_by_postcode("SW1A 1AA", address="10 Downing Street")`
- Rightmove:
  - `from property_core import RightmoveLocationAPI, fetch_listings`
  - Examples:
    - `api = RightmoveLocationAPI(); url = api.build_search_url("SW1A 1AA", property_type="sale", radius=0.25)`
    - `fetch_listings(url, max_pages=1, rate_limit_seconds=0.6)`

### Using the API service layer in-process
If you want the API guardrails (limits, normalization) but not HTTP, you can import services:
- PPD: `from app.services.ppd_service import PPDService`
- EPC: `from app.services.epc_service import EPCService`
- Rightmove: `from app.services.rightmove_service import RightmoveService`

These services wrap the core with validation, rate limiting, and Pydantic schemas.
