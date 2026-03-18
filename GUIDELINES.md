# Development Guidelines

## Architecture

Three-layer pattern:

1. **Transport clients** (`property_core/*_client.py`)
   - HTTP/SPARQL calls → typed Pydantic models
   - Handle rate limiting, retries, auth
   - Examples: `epc_client.py`, `ppd_client.py`, `postcode_client.py`

2. **Domain services** (`property_core/*_service.py`)
   - Parse raw data → typed Pydantic models
   - Business logic, validation, orchestration
   - Examples: `ppd_service.py`, `planning_service.py`

3. **API routers** (`app/api/v1/*.py`)
   - Thin HTTP wrappers over services
   - Request validation, response envelopes

4. **MCP server** (`mcp_server/server.py`)
   - Thin wrapper over domain services for AI hosts
   - Returns `content` (text summary) + `structuredContent` (full data)
   - UI in `mcp-app/` renders interactive dashboards

## Core Package Files

| File | Role |
|------|------|
| `__init__.py` | Package exports |
| `address_matching.py` | Address parsing/matching (used by report_service, epc.py, enrichment) |
| `enrichment.py` | EPC enrichment pipeline |
| `epc_client.py` | Transport: EPC API |
| `planning_councils.json` | Council database for planning_service |
| `planning_scraper.py` | Vision-guided planning scraper |
| `planning_service.py` | Council matching + URL building |
| `postcode_client.py` | Transport: postcodes.io |
| `ppd_client.py` | Transport: Land Registry SPARQL |
| `ppd_service.py` | Domain service: PPD comps |
| `py.typed` | PEP 561 marker (needed for typed package) |
| `rental_service.py` | Rental analysis + yield calc |
| `report_service.py` | Multi-source report pipeline |
| `rightmove_location.py` | Search URL builder |
| `rightmove_scraper.py` | Listings scraper |
| `yield_service.py` | Standalone yield analysis |

## Adding a New Data Source

1. Create transport client in `property_core/new_client.py`
2. Create domain service in `property_core/new_service.py` (if needed)
3. Add models to `property_core/models/new.py`
4. Export from `property_core/models/__init__.py`
5. Export from `property_core/__init__.py`
6. Add API router in `app/api/v1/new.py` (optional)

## Adding an MCP Tool

1. Add tool function in `mcp_server/server.py` using `@mcp.tool(meta=UI_META)`
2. Call domain service from `property_core` (no business logic in MCP layer)
3. Return `CallToolResult` with:
   - `content`: Text summary for models without UI
   - `structuredContent`: Full data for UI rendering
   - `_meta`: UI resource link (both nested and flat keys for host compat)
4. Update UI in `mcp-app/src/` to handle new data type
5. Build UI: `cd mcp_server/mcp-app && npm run build`
6. Track progress in `mcp_server/GOLD.md`

## Adding an MCP App View (UI + Context Sync)

Full checklist for interactive MCP App with bidirectional communication:

**Server side**:
1. Register tool with `_meta.ui.resourceUri` pointing to resource
2. Register resource with `mime_type="text/html;profile=mcp-app"`
3. Build UI to single HTML file (`vite-plugin-singlefile`)

**UI handler order** (register ALL before `app.connect()`):
1. `ontoolresult` — required, receives `structuredContent`
2. `onhostcontextchanged` — handle theme, safe area insets
3. `onteardown` — cleanup on unmount
4. `ontoolinputpartial` — optional, for streaming preview
5. `ontoolinput` — optional, some hosts skip it (infer from result)

**Context sync requirements**:
1. Capability guard: `getHostCapabilities()?.updateModelContext`
2. Commit-only triggers (not every keystroke)
3. YAML frontmatter payload format
4. Delta tracking (what changed, not full state dump)
5. Dedupe identical payloads

**Production patterns**:
1. Visibility-based pause (IntersectionObserver for animations/polling)
2. Safe area insets handling
3. Host theme integration (CSS variables)
4. Fallback when `ontoolinput` skipped

## MCP Tool Ergonomics

Conventions for consistent tools:

- **Naming**: `snake_case` tool names (e.g., `property_comps`)
- **Input defaults**: Sensible defaults with documented bounds
- **Content summary**: Always include JSON summary in `content[]` for quick model read
- **Data quality**: Include `data_quality` field where meaningful (good/low/insufficient)
- **Source counts**: Include counts (`sale_count`, `rental_count`) for transparency
- **Meta keys**: Both nested (`ui.resourceUri`) and flat (`ui/resourceUri`) for host compat

## Error Handling

- **Not found**: Return `None` (let caller decide)
- **Invalid input**: Raise `ValueError` with helpful message
- **Network errors**: Let bubble up or wrap in domain-specific exception
- **Debugging**: All models carry `raw` field with source data — inspect directly, no extra parameter needed

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

Env vars: `RIGHTMOVE_TEST_POSTCODE`, `EPC_API_EMAIL`, `EPC_API_KEY`

**MCP UI tests**: Manual via host (ChatGPT/Claude). Automation optional.

## Code Style

- Type hints on all functions
- Docstrings on public functions
- Private functions with `_` prefix
- Pydantic models with `Field()` for defaults
- `from __future__ import annotations` in all modules
