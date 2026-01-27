# Development Guidelines

## Architecture

Three-layer pattern:

1. **Transport clients** (`property_core/*_client.py`)
   - Raw HTTP calls → dicts
   - Handle rate limiting, retries, auth
   - Examples: `epc_client.py`, `ppd_client.py`, `postcode_client.py`

2. **Domain services** (`property_core/*_service.py`)
   - Parse raw data → typed Pydantic models
   - Business logic, validation, orchestration
   - Examples: `ppd_service.py`, `planning_service.py`

3. **API routers** (`app/api/v1/*.py`)
   - Thin HTTP wrappers over services
   - Request validation, response envelopes

## Adding a New Data Source

1. Create transport client in `property_core/new_client.py`
2. Create domain service in `property_core/new_service.py` (if needed)
3. Add models to `property_core/models/new.py`
4. Export from `property_core/models/__init__.py`
5. Export from `property_core/__init__.py`
6. Add API router in `app/api/v1/new.py` (optional)

## Error Handling

- **Not found**: Return `None` (let caller decide)
- **Invalid input**: Raise `ValueError` with helpful message
- **Network errors**: Let bubble up or wrap in domain-specific exception
- **Debugging**: Use `include_raw=True` instead of logging

## Testing

All tests are live integration tests:

```bash
RUN_LIVE_TESTS=1 uv run --extra dev pytest -v
```

Tests skip gracefully on 503/network errors.

Env vars: `RIGHTMOVE_TEST_POSTCODE`, `EPC_API_EMAIL`, `EPC_API_KEY`

## Code Style

- Type hints on all functions
- Docstrings on public functions
- Private functions with `_` prefix
- Pydantic models with `Field()` for defaults
- `from __future__ import annotations` in all modules
