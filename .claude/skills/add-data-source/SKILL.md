---
name: add-data-source
description: Use when adding a new external data source (API, scraper, etc.) to property_core. Walks through the complete 6-step process with patterns from existing implementations.
---

# Add a New Data Source

Follow these 6 steps in order. Each step must be completed before moving to the next.

## Step 1: Create Transport Client

Create `property_core/new_client.py`. Choose the pattern that fits:

- **Sync HTTP API** (httpx): see `property_core/companies_house_client.py`
  - `is_configured()` check for optional credentials
  - Basic auth or API key from `os.getenv()`
- **Async HTTP API** (httpx): see `property_core/epc_client.py`
- **HTML scraper** (requests + BeautifulSoup): see `property_core/rightmove_scraper.py`
- **SPARQL/RDF**: see `property_core/ppd_client.py`

Required in all clients:
- `from __future__ import annotations`
- Type hints on all methods
- Docstring on the class/module
- Rate limiting/retry logic where appropriate

## Step 2: Create Pydantic Models

Create `property_core/models/new_source.py`.

Transport-parsed models get the `raw` field:
```python
raw: dict | None = Field(default=None, exclude=True)
```

Use `@classmethod` factory methods for parsing:
```python
@classmethod
def from_api_response(cls, data: dict) -> "NewModel":
    return cls(field=data.get("key"), raw=data)
```

## Step 3: Export from models/__init__.py

Open `property_core/models/__init__.py`:
- Add import: `from .new_source import NewModel`
- Add to `__all__` list

## Step 4: Export from property_core/__init__.py

Open `property_core/__init__.py`:
- Add client/service import
- Add model import
- Add both to `__all__` list

## Step 5: Create Domain Service (if needed)

If the data source needs orchestration (combining with other sources, stats computation, guardrails), create `property_core/new_service.py`.

- Class-based if stateful: `class NewService`
- Function-based if stateless: `def analyze_new()`
- Export from `property_core/__init__.py`

## Step 6: Add Consumer Endpoints

All three consumers must be updated:

### API Router
Create `app/api/v1/new_source.py`, register in `app/api/routes.py`.
See `/add-endpoint` skill for details.

### MCP Tool
Add `@mcp.tool()` function in `mcp_server/server.py`.
See `/add-mcp-tool` skill for details.

### CLI Command
Add Typer command/subcommand in `property_cli/main.py`.
Follow existing patterns (Rich tables, `_join_tokens()` for postcodes).

## Validation Checklist

- [ ] `from __future__ import annotations` in all new files
- [ ] Models exported from `property_core/models/__init__.py`
- [ ] Client/service exported from `property_core/__init__.py`
- [ ] Router registered in `app/api/routes.py`
- [ ] MCP tool added to `mcp_server/server.py`
- [ ] CLI command added to `property_cli/main.py`
- [ ] Test created (at least one live test, gated with `RUN_LIVE_TESTS=1`)
- [ ] Environment variables documented in CLAUDE.md and `.env.example`
- [ ] All tests pass: `uv run --extra dev pytest -v`
