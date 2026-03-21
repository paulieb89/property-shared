# Development Guidelines

## Architecture

Three-layer pattern:

1. **Transport clients** (`property_core/`)
   - HTTP/SPARQL calls → typed Pydantic models
   - Handle rate limiting, retries, auth
   - Named `*_client.py` for HTTP/API transport or `*_scraper.py` for HTML scraping
   - `rightmove_location.py` is the Rightmove URL builder (transport, historical naming)

2. **Domain services** (`property_core/`)
   - Orchestration and business logic → typed Pydantic models
   - Class-based: `PPDService`, `PlanningService`, `PropertyReportService`
   - Function-based: `analyze_blocks()`, `calculate_yield()`, `analyze_rentals()`
   - Utility modules: `enrichment.py`, `address_matching.py`, `stamp_duty.py`

3. **Consumer layers** (three independent consumers, all import from `property_core`):
   - **API routers** (`app/api/v1/*.py`) — thin HTTP wrappers, no service wrapper layer
   - **MCP server** (`mcp_server/server.py`) — AI host tools via FastMCP
   - **CLI** (`property_cli/main.py`) — Typer CLI using service layer

**Data flow**: Consumer → Core service (domain logic) → Core client (network)

## Core Package Files

| File | Role |
|------|------|
| `__init__.py` | Package exports (services, functions, models) |
| `address_matching.py` | Address parsing/matching for EPC enrichment |
| `block_service.py` | Groups PPD transactions by building |
| `companies_house_client.py` | Transport: Companies House API |
| `enrichment.py` | EPC enrichment pipeline |
| `epc_client.py` | Transport: EPC API (async) |
| `planning_councils.json` | Council database (98 councils, 6 system types) |
| `planning_scraper.py` | Vision-guided planning scraper |
| `planning_service.py` | Council matching + URL building |
| `postcode_client.py` | Transport: postcodes.io |
| `ppd_client.py` | Transport: Land Registry SPARQL |
| `ppd_service.py` | Domain service: PPD comps, search, stats |
| `rental_service.py` | Rental analysis with optional yield calc |
| `report_service.py` | Multi-source report orchestrator |
| `rightmove_location.py` | Rightmove search URL builder |
| `rightmove_scraper.py` | Rightmove listings scraper |
| `stamp_duty.py` | SDLT calculator (April 2025 bands) |
| `yield_service.py` | Yield analysis: PPD sales + Rightmove rentals |

## Design Principles

- **property_core is a data library** — aggregates and returns data, does not make product decisions
- **Opinionated defaults are configurable** — yield thresholds, outlier filtering, search escalation, value ranges all have parameters with backward-compatible defaults
- **Transport-parsed models carry `raw`** — PPDTransaction, EPCData, RightmoveListing, CompanyRecord, PostcodeResult. Report, block, planning, and aggregate models do NOT.
- **All consumers import directly from property_core** — no wrapper/adapter layer between core and consumers

## Adding a New Data Source

1. Create transport client in `property_core/new_client.py`
2. Create Pydantic models in `property_core/models/new.py`
3. Export from `property_core/models/__init__.py`
4. Export from `property_core/__init__.py`
5. Create domain service in `property_core/new_service.py` (if orchestration needed)
6. Add consumer endpoints: API router, MCP tool, CLI command

## Adding an MCP Tool

1. Add tool function in `mcp_server/server.py` using `@mcp.tool()`
2. Import from `property_core` (lazy imports inside the tool function)
3. Return `ToolResult` from `fastmcp.tools.tool` with:
   - `content`: Summary line + slimmed JSON via `_content()` helper
   - `structured_content`: Full data dict for programmatic consumers
4. Use `anyio.to_thread.run_sync()` for sync calls

## Error Handling

- **Not found**: Return `None` (let caller decide)
- **Invalid input**: Raise `ValueError` with helpful message
- **Network errors**: Let bubble up or wrap in domain-specific exception

## Testing

**Unit tests** (mocked, default):
```bash
uv run --extra dev pytest -v
```

**Live integration tests** (real network calls):
```bash
RUN_LIVE_TESTS=1 uv run --extra dev pytest -v
```

Tests skip gracefully on 503/network errors.

## Code Style

- Type hints on all functions
- Docstrings on public functions
- Private functions with `_` prefix
- Pydantic models with `Field()` for defaults
- `from __future__ import annotations` in all modules
