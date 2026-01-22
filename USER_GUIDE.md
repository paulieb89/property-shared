# Property Shared API — User Guide

## Setup
1) Create `.env` from `.env.example` (set `EPC_API_EMAIL`/`EPC_API_KEY` if you want EPC enabled).
2) Install dependencies: `uv sync --extra dev`.
3) Run the API: `uv run property-api` (or `uv run uvicorn app.main:app --reload`).
4) Open the demo UI: http://localhost:8000/demo.

## CLI Commands

All commands support `--api-url http://localhost:8000` to hit the API instead of calling core directly.

### Meta
```bash
property-cli meta
```

### PPD (Price Paid Data)

```bash
# Comparable sales summary (with optional subject property context)
property-cli ppd comps "SW1A 1AA" --months 24 --limit 20 --search-level sector
property-cli ppd comps "SW1A 1PH" --address "73 St James Street" --months 24  # includes subject property history

# Search transactions by postcode
property-cli ppd search --postcode "SW1A 1AA" --limit 10
property-cli ppd search --postcode-prefix SW1A --limit 10

# Search by address fields (requires at least 2 fields)
property-cli ppd address-search --postcode "SW1A 2AA" --street "Downing"
property-cli ppd address-search --town "London" --street "Baker" --paon "221B"

# Get single transaction record
property-cli ppd transaction <transaction_id> --include-raw

# Get bulk download URLs
property-cli ppd download-url --kind complete          # Full dataset (~4GB)
property-cli ppd download-url --kind year --year 2024  # Year archive
property-cli ppd download-url --kind monthly           # Latest monthly update
```

### EPC (Energy Performance Certificates)

Requires `EPC_API_EMAIL` and `EPC_API_KEY` in `.env`.

```bash
# Search by postcode (returns first/best match)
property-cli epc search "SW1A 1AA"
property-cli epc search "SW1A 1AA" --address "10 Downing Street" --include-raw

# Combined address query (parses postcode from end)
property-cli epc search --q "10 Downing Street, SW1A 2AA"

# Direct lookup by certificate hash (lmk-key)
property-cli epc certificate <certificate_hash>
```

### Rightmove

```bash
# Build a search URL from postcode
property-cli rightmove search-url "SW1A 1AA" --property-type sale --radius 0.25

# Fetch listings from a search URL
property-cli rightmove listings "<search_url>" --max-pages 1
```

### Planning (UK Council Portals)

**Note:** Planning scraper only works from UK residential IPs. Councils block datacenter IPs.

```bash
# Search for planning applications by postcode (returns search URLs)
property-cli planning search "S1 2HH"      # Sheffield - returns direct search URL
property-cli planning search "SW1A 2AA"    # Westminster

# Look up council for a postcode
property-cli planning council-for-postcode "SW1A 2AA"

# List verified councils
property-cli planning councils

# Get council details
property-cli planning council sheffield

# Probe connectivity (diagnose blocking issues)
property-cli planning probe "https://planningapps.sheffield.gov.uk/..." --timeout 30000

# Scrape a planning application (uses OpenAI Vision)
property-cli planning scrape "https://planningapps.sheffield.gov.uk/..." --save-screenshots
```

## API Endpoints

### Health & Meta
- `GET /v1/health` — Health check
- `GET /v1/meta/integrations` — Integration status

### PPD
- `GET /v1/ppd/transactions?postcode=SW1A%201AA&limit=20`
- `GET /v1/ppd/address-search?postcode=SW1A&street=Downing&limit=5` (requires ≥2 fields)
- `GET /v1/ppd/comps?postcode=SW1A%201AA&months=24&address=10%20Downing%20Street` (address optional)
- `GET /v1/ppd/transaction/{id}?include_raw=true`
- `GET /v1/ppd/download-url?kind=monthly`

### EPC
- `GET /v1/epc/search?postcode=SW1A%201AA&address=10%20Downing%20Street` (requires creds)
- `GET /v1/epc/search?q=10%20Downing%20Street,%20SW1A%202AA` (combined address query)
- `GET /v1/epc/certificate/{certificate_hash}` (direct lookup by lmk-key)

### Rightmove
- `GET /v1/rightmove/search-url?postcode=SW1A%201AA&property_type=sale&radius=0.25`
- `GET /v1/rightmove/listings?search_url=<url>&max_pages=1`

### Planning
- `GET /v1/planning/search?postcode=S1%202HH` — Search by postcode (returns search URLs)
- `GET /v1/planning/council-for-postcode?postcode=SW1A%202AA` — Look up council for postcode
- `GET /v1/planning/councils` — List all councils
- `GET /v1/planning/council/{code}` — Council details
- `POST /v1/planning/probe` — Connectivity diagnostics
- `POST /v1/planning/scrape` — Scrape planning application

## Live Tests

Live tests make real network calls and are gated:
```bash
RUN_LIVE_TESTS=1 uv run --extra dev pytest -q tests
```
The suite skips if credentials are missing or upstream services return 503.

## Using as a Python Package

### Install
```bash
# From repo root
uv sync --extra cli

# Or install editable in another project
pip install -e /path/to/property_shared
```

### Core Imports (no HTTP)
```python
from property_core import PricePaidDataClient, EPCClient, RightmoveLocationAPI, fetch_listings

# PPD
client = PricePaidDataClient()
client.get_comps_summary(postcode="SW1A 1AA", months=24, limit=20, search_level="sector")
client.sparql_search(postcode_prefix="SW1A", limit=10)
client.form_search(postcode="SW1A", street="Downing", limit=5)  # requires ≥2 fields
client.get_transaction_record("<transaction_id>")

# EPC (requires EPC_API_EMAIL/EPC_API_KEY in env)
epc = EPCClient()
await epc.search_by_postcode("SW1A 1AA", address="10 Downing Street")

# Rightmove
api = RightmoveLocationAPI()
url = api.build_search_url("SW1A 1AA", property_type="sale", radius=0.25)
listings = fetch_listings(url, max_pages=1, rate_limit_seconds=0.6)

# Planning (residential IP only)
from property_core.planning_scraper import scrape_planning_application
result = scrape_planning_application("https://council.gov.uk/planning/app/123")
```

### Service Layer (with guardrails)
```python
from app.services.ppd_service import PPDService
from app.services.epc_service import EPCService
from app.services.rightmove_service import RightmoveService

# PPD with subject property context
service = PPDService()
result = service.comps(postcode="SW1A 1AA", address="10 Downing Street", months=24, limit=50, search_level="sector")
print(result.subject_property)  # Transaction history for the specific address
```

## Notes

- **Planning scraper** requires UK residential IP — councils block all datacenter IPs.
- **Rightmove scraping** is polite by default (0.6s delay); respect rate limits.
- **UKHPI endpoints** are not implemented yet.
- **Location slice** was removed; projects can supply their own location intelligence.
