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
property-cli ppd comps "SW1A 1PH" --address "73 St James Street" --months 24  # includes subject property + comparison stats
property-cli ppd comps "B1 1BB" --search-level sector --enrich-epc  # adds floor area + price/sqft from EPC

# Response includes area stats: percentile_25, percentile_75, and when address provided:
# subject_price_percentile (0-100), subject_vs_median_pct (e.g., +10.8 or -5.2)

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
# Build a search URL from postcode (sales)
property-cli rightmove search-url "SW1A 1AA" --property-type sale --radius 0.25

# Build a search URL for rentals
property-cli rightmove search-url "SW1A 1AA" --property-type rent --radius 0.25

# Fetch listings from a search URL
property-cli rightmove listings "<search_url>" --max-pages 1

# Fetch full details for a single listing (tenure, service charge, ground rent, etc.)
property-cli rightmove listing 161151632
property-cli rightmove listing "https://www.rightmove.co.uk/properties/161151632" --include-raw
```

**All listings** include: `listing_status` (e.g., "SOLD_STC", "UNDER_OFFER"), `tags` (all status tags as list), `latitude`/`longitude` (direct access).

**Rental listings** include additional fields: `let_available_date`, `price_frequency` (monthly/weekly), `students`, `transaction_type`.

**Listing detail** (individual property page) includes: `tenure_type`, `years_remaining_on_lease`, `annual_service_charge`, `annual_ground_rent`, `ground_rent_review_period_years`, `council_tax_band`, `postcode`, `latitude`/`longitude`, `floorplans`, `key_features`, `description`, `price_per_sqft`, `nearest_stations`.

### Stamp Duty (SDLT Calculator)

```bash
# Calculate stamp duty (defaults: additional property surcharge ON)
property-cli calc stamp-duty 300000
property-cli calc stamp-duty 500000 --no-additional              # primary residence
property-cli calc stamp-duty 250000 --ftb                        # first-time buyer relief
property-cli calc stamp-duty 400000 --non-resident               # non-UK resident surcharge (+2%)
property-cli calc stamp-duty 300000 --ftb --no-additional        # FTB, primary residence
```

### Block Analyzer (Flat Buildings)

```bash
# Find buildings with multiple flat sales (investor exits, bulk-buy opportunities)
property-cli ppd blocks "B1 1AA"
property-cli ppd blocks "B1 1AA" --months 36 --min 3 --search-level district
```

### Companies House

Requires `COMPANIES_HOUSE_API_KEY` in `.env` (free from https://developer.company-information.service.gov.uk/).

```bash
# Search by company name
property-cli companies search "Tesco"

# Search also works with company numbers
property-cli companies search "00445790"
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

# Search for actual planning applications (vision-guided, requires UK residential IP)
property-cli planning applications "S1 2HH" --max-results 5
```

#### API usage for search-results
```bash
# By postcode (resolves council automatically)
curl -X POST http://localhost:8000/v1/planning/search-results \
  -H "Content-Type: application/json" \
  -d '{"postcode": "M1 1AA", "max_results": 5}'

# With explicit portal URL (skip council resolution)
curl -X POST http://localhost:8000/v1/planning/search-results \
  -H "Content-Type: application/json" \
  -d '{"postcode": "M1 1AA", "portal_url": "https://pa.manchester.gov.uk/online-applications/search.do?action=simple", "system": "idox", "max_results": 5}'
```

### Rental Analysis

```bash
# Standalone rental market analysis (no full report needed)
uv run python -c "
import asyncio
from property_core import analyze_rentals
r = asyncio.run(analyze_rentals('SW1A 1AA', radius=0.5, purchase_price=500000))
print(f'Median rent: £{r.median_rent_monthly}/mo, Yield: {r.gross_yield_pct}%')
"
```

### Property Report

```bash
# Generate a comprehensive report (PPD + EPC + Rightmove)
property-cli report generate "10 Downing Street, SW1A 2AA"

# Save as JSON
property-cli report generate "SW1A 2AA" -o report.json

# Save as HTML
property-cli report generate "SW1A 2AA" -o report.html --html

# Customize search parameters
property-cli report generate "SW1A 2AA" --months 36 --radius 0.25 --no-rentals

# Via API
property-cli report generate "SW1A 2AA" --api-url http://localhost:8000
```

## API Endpoints

### Health & Meta
- `GET /v1/health` — Health check
- `GET /v1/meta/integrations` — Integration status

### PPD
- `GET /v1/ppd/transactions?postcode=SW1A%201AA&limit=20&include_raw=true`
- `GET /v1/ppd/address-search?postcode=SW1A&street=Downing&limit=5&include_raw=true` (requires ≥2 fields)
- `GET /v1/ppd/comps?postcode=SW1A%201AA&months=24&address=10%20Downing%20Street` (address optional, add `&enrich_epc=true` for floor area/price-per-sqft)
- `GET /v1/ppd/transaction/{id}?include_raw=true`
- `GET /v1/ppd/download-url?kind=monthly`

Results include `locality` and `district` fields from the Land Registry address data.

### EPC
- `GET /v1/epc/search?postcode=SW1A%201AA&address=10%20Downing%20Street` (requires creds)
- `GET /v1/epc/search?q=10%20Downing%20Street,%20SW1A%202AA` (combined address query)
- `GET /v1/epc/certificate/{certificate_hash}` (direct lookup by lmk-key)

### Rightmove
- `GET /v1/rightmove/search-url?postcode=SW1A%201AA&property_type=sale&radius=0.25` — Sales
- `GET /v1/rightmove/search-url?postcode=SW1A%201AA&property_type=rent&radius=0.25` — Rentals
- `GET /v1/rightmove/listings?search_url=<url>&max_pages=1`
- `GET /v1/rightmove/listing/{property_id}` — Full listing detail (tenure, costs, floorplans)

All listing results include `raw` with the full `__NEXT_DATA__` property object.
Listing detail results include `raw` with the full `PAGE_MODEL.propertyData` dict.

### Planning
- `GET /v1/planning/search?postcode=S1%202HH` — Search by postcode (returns search URLs)
- `POST /v1/planning/search-results` — Search for planning applications (vision-guided, 30-60s)
- `GET /v1/planning/council-for-postcode?postcode=SW1A%202AA&include_raw=true` — Look up council for postcode (with `include_raw`, returns full postcodes.io data: NHS, constituency, LSOA, police force, etc.)
- `GET /v1/planning/councils` — List all councils
- `GET /v1/planning/council/{code}` — Council details
- `POST /v1/planning/probe` — Connectivity diagnostics
- `POST /v1/planning/scrape` — Scrape planning application detail page

### Stamp Duty
- `GET /v1/calculators/stamp-duty?price=300000&additional_property=true&first_time_buyer=false&non_resident=false`

### Block Analyzer
- `GET /v1/ppd/blocks?postcode=B1%201AA&months=24&min_transactions=2&search_level=sector`

### Companies House
- `GET /v1/companies/search?q=Tesco&limit=5` — Search by company name
- `GET /v1/companies/{company_number}` — Fetch company by number (includes officers)

### Property Report
- `POST /v1/property/report` — Generate comprehensive property report (PPD + EPC + Rightmove)
  - Returns JSON by default, or HTML with `?format=html`
  - Body: `{ "address": "10 Downing Street, SW1A 2AA", "ppd_months": 24, "search_radius": 0.5 }`

## Live Tests

Live tests make real network calls and are gated:
```bash
RUN_LIVE_TESTS=1 uv run --extra dev pytest -q tests
```
The suite skips if credentials are missing or upstream services return 503.

## Using as a Python Package

### Install
```bash
# From PyPI
pip install property-shared

# From repo root (development)
uv sync --extra cli

# Or install editable in another project
pip install -e /path/to/property_shared
```

### Core Imports (no HTTP)
```python
from property_core import (
    PricePaidDataClient, PPDService, EPCClient, RightmoveLocationAPI, fetch_listings, PostcodeClient,
    analyze_rentals, compute_enriched_stats, enrich_comps_with_epc, calculate_stamp_duty,
    analyze_blocks, CompaniesHouseClient
)
from property_core.rightmove_scraper import fetch_listing

# PPD (transport client — returns typed models)
client = PricePaidDataClient()
transactions = client.sparql_search(postcode_prefix="SW1A", limit=10)  # list[PPDTransaction]
transactions = client.form_search(postcode="SW1A", street="Downing", limit=5)  # list[PPDTransaction]
record = client.get_transaction_record("<transaction_id>")  # PPDTransactionRecord

# PPD comps (domain service — adds stats, guardrails)
service = PPDService()
result = service.comps(postcode="SW1A 1AA", months=24, limit=20, search_level="sector")

# EPC (requires EPC_API_EMAIL/EPC_API_KEY in env)
epc = EPCClient()
await epc.search_by_postcode("SW1A 1AA", address="10 Downing Street")

# Rightmove - Sales
api = RightmoveLocationAPI()
url = api.build_search_url("SW1A 1AA", property_type="sale", radius=0.25)
listings = fetch_listings(url, max_pages=1, rate_limit_seconds=0.6)

# Rightmove - raw data is always populated (no include_raw parameter needed)
listings = fetch_listings(url, max_pages=1)
for listing in listings:
    print(listing.raw["location"])  # {"latitude": ..., "longitude": ...}

# Rightmove - Filter out SOLD_STC/UNDER_OFFER (critical for active listings)
listings = fetch_listings(url, max_pages=1)
available = [l for l in listings if l.listing_status not in ("SOLD_STC", "UNDER_OFFER")]
print(f"{len(available)} available out of {len(listings)} total")

# Rightmove - Rentals
url = api.build_search_url("SW1A 1AA", property_type="rent", radius=0.25)
rentals = fetch_listings(url, max_pages=1)
for r in rentals:
    print(f"£{r.price} {r.price_frequency} - {r.address} (available: {r.let_available_date})")

# Rightmove - Individual listing detail (tenure, service charge, ground rent)
detail = fetch_listing("161151632")  # or full URL
print(f"Tenure: {detail.tenure_type}, {detail.years_remaining_on_lease} years remaining")
print(f"Service charge: £{detail.annual_service_charge}/yr")
print(f"Ground rent: £{detail.annual_ground_rent}/yr")
print(f"Size: {detail.display_size}, Council tax: {detail.council_tax_band}")

# Postcode lookup (returns typed PostcodeResult)
from property_core import PostcodeClient
pc = PostcodeClient()
result = pc.lookup("SW1A 1AA")  # Optional[PostcodeResult]
print(result.admin_district)    # "Westminster"
print(result.latitude, result.longitude)

# Or use get_local_authority() for structured dict
la = pc.get_local_authority("SW1A 1AA", include_raw=True)
print(la["name"])  # "Westminster"

# Rental analysis (standalone, no full report needed)
import asyncio
rental = asyncio.run(analyze_rentals("SW1A 1AA", purchase_price=500000))
print(f"Median: £{rental.median_rent_monthly}/mo, Yield: {rental.gross_yield_pct}%")

# Yield analysis (combines PPD sales + Rightmove rentals)
from property_core import calculate_yield
result = asyncio.run(calculate_yield("SW1A 1AA"))
print(f"Sale: £{result.median_sale_price}, Rent: £{result.median_monthly_rent}/mo")
print(f"Gross yield: {result.gross_yield_pct}% ({result.yield_assessment})")
print(f"Data quality: {result.data_quality}")

# Planning (residential IP only, requires playwright + openai)
from property_core.planning_scraper import scrape_planning_application, search_planning_by_postcode

# Scrape a single application detail page
result = scrape_planning_application("https://council.gov.uk/planning/app/123")

# Search for applications by postcode (vision-guided form filling)
results = search_planning_by_postcode(
    portal_url="https://pa.manchester.gov.uk/online-applications/search.do?action=simple",
    postcode="M1 1AA",
    max_results=10,
    system="idox",
)
```

### Domain Services (typed models, guardrails)
```python
from property_core import PPDService, PlanningService, PropertyReportService

# PPD with subject property context and area stats
service = PPDService()
result = service.comps(postcode="SW1A 1AA", address="10 Downing Street", months=24, limit=50, search_level="sector")
print(result.subject_property)           # Transaction history for the specific address
print(result.percentile_25, result.percentile_75)  # Area price quartiles
print(result.subject_vs_median_pct)      # e.g., +10.8 means 10.8% above median

# PPD transactions (returns dict with typed transaction list)
result = service.search_transactions(postcode="SW1A 1AA", postcode_prefix=None, limit=5, include_raw=True)
print(result["results"][0].locality)     # "LONDON"
print(result["results"][0].district)     # "CITY OF WESTMINSTER"

# PPD comps with EPC enrichment (floor area, price/sqft)
import asyncio
from property_core import enrich_comps_with_epc, EPCClient, compute_enriched_stats
result = service.comps(postcode="B1 1BB", months=24, search_level="sector")
epc_client = EPCClient()  # requires EPC_API_EMAIL/EPC_API_KEY in env
enriched = asyncio.run(enrich_comps_with_epc(result.transactions, epc_client))
# enriched transactions now have epc_floor_area_sqm, price_per_sqft, epc_rating, etc.
stats = compute_enriched_stats(enriched)  # median_price_per_sqft, epc_match_rate

# Planning - find council for postcode
planning = PlanningService()
info = planning.council_for_postcode("SW1A 2AA")
print(info["council"]["name"], info["council"]["system"])

# Property report (async)
report_service = PropertyReportService()
report = asyncio.run(report_service.generate_report("10 Downing Street, SW1A 2AA"))
print(report.estimated_value_low, report.estimated_value_high)

# Stamp Duty (SDLT calculator — April 2025 bands)
from property_core import calculate_stamp_duty
result = calculate_stamp_duty(price=300000, additional_property=True, first_time_buyer=False)
print(f"Tax: £{result.tax:,}, Effective rate: {result.effective_rate}%")
print(f"Bands: {result.bands}")

# Block Analyzer (find investor exits / bulk-buy opportunities)
from property_core import analyze_blocks
blocks = analyze_blocks(postcode="B1 1AA", months=24, min_transactions=3)
for b in blocks.blocks:
    print(f"{b.building} {b.street}: {b.transaction_count} sales, £{b.min_price:,}-£{b.max_price:,}")

# Companies House (requires COMPANIES_HOUSE_API_KEY in env)
from property_core import CompaniesHouseClient
ch = CompaniesHouseClient()
search_result = ch.search("Tesco", items_per_page=5)
for c in search_result.companies:
    print(f"{c.company_number}: {c.company_name}")
company = ch.get_company("00445790")  # fetch by number, includes officers
```

## MCP Server (AI Host Integration)

The MCP server exposes all property_core tools to AI hosts like Claude, ChatGPT, and Claude Code.

### Running locally
```bash
cd mcp_server && uv run property-mcp
```

### Connecting from Claude Code
Add to your `.mcp.json`:
```json
{
  "mcpServers": {
    "property": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/property_shared/mcp_server", "property-mcp"]
    }
  }
}
```

### Connecting via SSE (remote / Fly.io)
```json
{
  "mcpServers": {
    "property": {
      "type": "sse",
      "url": "https://your-app.fly.dev/sse"
    }
  }
}
```

### Available MCP Tools
| Tool | Description |
|------|-------------|
| `property_report` | Full deal analysis (comps + EPC + yield + market) |
| `property_comps` | Comparable sales with stats, optional EPC enrichment |
| `ppd_transactions` | Search Land Registry by postcode, address, date, price |
| `rightmove_search` | Search Rightmove listings (sale or rent) |
| `rightmove_listing` | Full details for a single property |
| `property_yield` | Rental yield calculation (sales + rentals) |
| `rental_analysis` | Rental market stats with optional yield |
| `property_epc` | EPC certificate lookup |
| `planning_search` | Find planning portal URLs for a postcode |
| `property_blocks` | Find flat blocks with multiple unit sales |
| `stamp_duty` | SDLT calculator |
| `company_search` | Companies House lookup |

## Notes

- **`raw` field pattern**: All core models carry a `raw` field always populated with source data. At the API layer, PPD/EPC/Planning endpoints support `include_raw=true` to control raw data in HTTP responses. Rightmove models always include raw data; the API parameter is accepted but ignored for backward compatibility.
- **Planning scraper** requires UK residential IP — councils block all datacenter IPs. Set `PLAYWRIGHT_PROXY_URL` for proxy support.
- **Planning search-results** endpoint takes 30-60 seconds (browser automation + vision extraction).
- **Rightmove scraping** is polite by default (0.6s delay); respect rate limits.
- **API reference**: Full interactive API docs available at `http://localhost:8000/docs` (Swagger) and `http://localhost:8000/redoc` (ReDoc) when the server is running.
