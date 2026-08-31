# Property Shared

<!-- mcp-name: io.github.paulieb89/property-shared -->

[![property-shared MCP server](https://glama.ai/mcp/servers/paulieb89/property-shared/badges/card.svg)](https://glama.ai/mcp/servers/paulieb89/property-shared)

UK property data in one package. Pulls Land Registry sales, EPC certificates, Rightmove listings, rental yields, stamp duty calculations, planning portal links, and Companies House records.

Use it as a **Python library**, **CLI**, **HTTP API**, or **MCP server**.

## What You Get

| Data Source | What It Returns |
|-------------|-----------------|
| **Land Registry PPD** | Sold prices, dates, property types, area comps with median/percentiles |
| **EPC (GOV.UK)** | Energy ratings, floor area, heating costs. England & Wales only. Certificate lookup and summary search — see EPC notes below |
| **Rightmove** | Current listings (sale + rent), prices, agents, listing details |
| **Yield Analysis** | Gross yield from PPD sales + Rightmove rentals combined |
| **Stamp Duty** | SDLT calculation with April 2025 bands, BTL surcharge, FTB relief |
| **Block Analyzer** | Groups flat sales by building to spot investor exits |
| **Planning** | Local council planning portal lookup (99 verified councils, stdio only) |
| **Companies House** | Company search and lookup by name or number |

## Skills & Plugins 

Property and Legal packs coming soon. Please get in contact if you have working experiance or expert knowledge in UK property investing, UK Estate Agents, Property and Conveyencing and would like to help shape this. paul@bouch.dev  


## Use as MCP Server

No install required — paste the URL into your MCP client config and go.

**Claude Code, Cursor, any MCP client:**

```json
{
  "mcpServers": {
    "property-shared": {
      "type": "http",
      "url": "https://property-shared.fly.dev/mcp"
    }
  }
}
```

## Install

```bash
pip install property-shared

# or with uv
uv add property-shared
```

Extras: `[cli]` for CLI, `[api]` for HTTP server.

```bash
pip install property-shared[cli]
# or
uv add property-shared --extra cli
```

## Use as a Python Library

```python
from property_core import PPDService, calculate_yield, calculate_stamp_duty

# Get comparable sales for a postcode
comps = PPDService().comps("SW1A 1AA", months=24, property_type="F")
print(f"Median flat price: {comps.median:,}")

# Calculate rental yield
import asyncio
result = asyncio.run(calculate_yield("NG1 1AA", property_type="F"))
print(f"Gross yield: {result.gross_yield_pct}%")

# Stamp duty
sdlt = calculate_stamp_duty(250000, additional_property=True)
print(f"SDLT: {sdlt.total_sdlt:,.0f} ({sdlt.effective_rate}%)")
```

All models are available at top level:
```python
from property_core import (
    PPDTransaction, PPDCompsResponse, EPCData,
    RightmoveListing, RightmoveListingDetail,
    PropertyReport, YieldAnalysis, RentalAnalysis,
    BlockAnalysisResponse, CompanyRecord, StampDutyResult,
)
```

Interpretation helpers (core returns numbers, you decide how to label them):
```python
from property_core import classify_yield, classify_data_quality, generate_insights
```

## Use as CLI

```bash
pip install property-shared[cli]  # or: uv add property-shared --extra cli

# Comparable sales
property-cli ppd comps "SW1A 1AA" --months 24 --property-type F

# Rental yield
property-cli analysis yield "NG1 1AA" --property-type F

# Stamp duty
property-cli calc stamp-duty 300000

# Rightmove search (with sort)
property-cli rightmove search-url "NG1 1AA" --sort-by most_reduced

# Full property report
property-cli report generate "10 Downing Street, SW1A 2AA" --property-type F
```

Add `--api-url http://localhost:8000` to any command to route through the HTTP API instead of calling core directly.

## Use as HTTP API

```bash
pip install property-shared[api]  # or: uv add property-shared --extra api
property-api  # starts on port 8000
```

Interactive docs at `http://localhost:8000/docs`.

Key endpoints:
- `GET /v1/ppd/comps?postcode=SW1A+1AA&property_type=F&enrich_epc=true`
- `GET /v1/analysis/yield?postcode=NG1+1AA&property_type=F`
- `GET /v1/analysis/rental?postcode=NG1+1AA&purchase_price=200000`
- `GET /v1/rightmove/search-url?postcode=NG1+1AA&sort_by=newest`
- `GET /v1/calculators/stamp-duty?price=300000&additional_property=true`
- `POST /v1/property/report` with `{ "address": "10 Downing Street, SW1A 2AA" }`

Full endpoint list in [USER_GUIDE.md](USER_GUIDE.md).

## EPC notes (v1.14.0)

The EPC service moved to a GOV.UK Bearer API. Set `EPC_API_TOKEN`; the old
`EPC_API_EMAIL`/`EPC_API_KEY` pair authenticated against a retired host and is
not a supported fallback.

What the new upstream supports, and what it does not:

- **Certificate lookup** by certificate number — full detail, one request.
- **Summary search** by postcode — returns address, UPRN (often absent), energy
  band, registration date and schema type. It does **not** return energy score,
  floor area or property type; those exist only on a full certificate.
- **A postcode selects an area, never a property.** Identifying one property
  needs a UPRN or an address matching a certificate exactly (case, punctuation
  and a leading `Flat`/`Apartment` designator aside). Anything less — no address,
  no match, or several matches — is refused rather than resolved to a best guess.
  See [USER_GUIDE.md](USER_GUIDE.md) for the CLI and REST surfaces.
- **Area statistics** are limited to the record count and, when the bounded
  response contains every matching summary, the rating distribution.
  Property-type breakdown and floor-area statistics are reported as `None` —
  unavailable, not zero — because producing them would mean one request per
  certificate.
- **Coverage is England and Wales.** Scotland, Northern Ireland and the Channel
  Islands return "no certificates found": a coverage boundary, not a statement
  about a property.
- **Pagination is not a stable snapshot.** Responses carry `complete`,
  `duplicates_removed` and `unusable_rows`; no operation claims a complete
  harvest of an area.
- **Ambiguous address matches are refused** rather than resolved to an arbitrary
  neighbouring certificate.

`search_all_by_postcode()` is unsupported — use `search_summaries()` for
candidate discovery, then `get_certificate()` for the one you need.

## Environment Variables

Create a `.env` file in the repo root (it is gitignored) with the variables you need.

> **Leave optional variables out entirely rather than assigning them empty.**
> `KEY=` sets an empty string, which is not the same as unset: `os.getenv("KEY",
> "default")` returns `""`, so the default never applies. This bit the EPC live
> tests, which sent an empty postcode upstream.

Key variables:

| Variable | Required For | Description |
|----------|-------------|-------------|
| `EPC_API_TOKEN` | EPC lookups | Bearer token from [GOV.UK EPC data](https://get-energy-performance-data.communities.gov.uk/) |
| `EPC_API_EMAIL` | *(deprecated)* | Retired service; parsed only to raise a configuration error |
| `EPC_API_KEY` | *(deprecated)* | Retired service; not a supported fallback |
| `COMPANIES_HOUSE_API_KEY` | Company search | Free key from [Companies House](https://developer.company-information.service.gov.uk/) |
| `RIGHTMOVE_DELAY_SECONDS` | No (default 0.6s) | Rate limit delay for Rightmove scraping |
| `OPENAI_API_KEY` | Planning scraper | Vision-guided planning portal scraper |

Land Registry PPD and Rightmove work without credentials.

## Development

```bash
# Install dependencies (dev tooling installs by default via [dependency-groups])
uv sync

# Run API with reload
uv run uvicorn app.main:app --reload

# Run tests (mocked, no network)
uv run pytest -v

# Run live integration tests (real network calls)
RUN_LIVE_TESTS=1 uv run pytest -v
```

Deployed at `https://property-shared.fly.dev` with API docs at `/docs` and MCP endpoint at `/mcp`.
