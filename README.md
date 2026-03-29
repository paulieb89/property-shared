# Property Shared

UK property data in one package. Pulls Land Registry sales, EPC certificates, Rightmove listings, rental yields, stamp duty calculations, planning portal links, and Companies House records.

Use it as a **Python library**, **CLI**, **HTTP API**, or **MCP server for AI agents**.

## What You Get

| Data Source | What It Returns |
|-------------|-----------------|
| **Land Registry PPD** | Sold prices, dates, property types, area comps with median/percentiles |
| **EPC Register** | Energy ratings, floor area, construction age, heating costs |
| **Rightmove** | Current listings (sale + rent), prices, agents, listing details |
| **Yield Analysis** | Gross yield from PPD sales + Rightmove rentals combined |
| **Stamp Duty** | SDLT calculation with April 2025 bands, BTL surcharge, FTB relief |
| **Block Analyzer** | Groups flat sales by building to spot investor exits |
| **Planning** | Local council planning portal lookup (98 verified councils) |
| **Companies House** | Company search and lookup by name or number |

## Skills

Want structured property reports instead of raw data? Claude skills that chain these tools into investment summaries are available at [bouch.dev/products](https://bouch.dev/products).

## Install

```bash
pip install property-shared

# or with uv
uv add property-shared
```

Extras: `[mcp]` for MCP server, `[cli]` for CLI, `[api]` for HTTP server, `[dev]` for tests.

```bash
pip install property-shared[mcp,cli]
# or
uv add property-shared --extra mcp --extra cli
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

## Use as MCP Server (AI Agents)

For Claude.ai, Claude Code, ChatGPT, or any MCP-compatible host.

```bash
pip install property-shared[mcp]  # or: uv add property-shared --extra mcp
property-mcp  # starts stdio transport
```

12 tools available: `property_report`, `property_comps`, `ppd_transactions`, `property_yield`, `rental_analysis`, `property_epc`, `rightmove_search`, `rightmove_listing`, `property_blocks`, `stamp_duty`, `planning_search`, `company_search`.

Remote server deployed at `https://property-shared.fly.dev/mcp` (Streamable HTTP).

See [mcp_server/README.md](mcp_server/README.md) for connection setup and tool details.

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

## Environment Variables

Copy `.env.example` to `.env`. Key variables:

| Variable | Required For | Description |
|----------|-------------|-------------|
| `EPC_API_EMAIL` | EPC lookups | Free key from [EPC Register](https://epc.opendatacommunities.org/) |
| `EPC_API_KEY` | EPC lookups | Paired with email above |
| `COMPANIES_HOUSE_API_KEY` | Company search | Free key from [Companies House](https://developer.company-information.service.gov.uk/) |
| `RIGHTMOVE_DELAY_SECONDS` | No (default 0.6s) | Rate limit delay for Rightmove scraping |
| `OPENAI_API_KEY` | Planning scraper | Vision-guided planning portal scraper |

Land Registry PPD and Rightmove work without credentials.

## Development

```bash
# Install with dev extras
uv sync --extra dev

# Run API with reload
uv run uvicorn app.main:app --reload

# Run tests (mocked, no network)
uv run --extra dev pytest -v

# Run live integration tests (real network calls)
RUN_LIVE_TESTS=1 uv run --extra dev pytest -v
```

## Architecture

Three-layer separation — core stays framework-agnostic:

```
property_core/     Pure Python library (all business logic)
app/               FastAPI wrapper (thin HTTP layer)
property_cli/      Typer CLI (thin CLI layer)
mcp_server/        FastMCP wrapper (thin MCP layer for AI hosts)
```

All three consumers import directly from `property_core`. No adapter layers.

## Deploy (Fly.io)

```bash
fly secrets set EPC_API_EMAIL=... EPC_API_KEY=...
fly deploy
```

Deployed at `https://property-shared.fly.dev` with API docs at `/docs` and MCP endpoint at `/mcp`.
