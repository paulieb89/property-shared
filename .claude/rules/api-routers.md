---
paths:
  - "app/api/**/*.py"
---

# API Router Rules

API routers are **thin HTTP wrappers** — no business logic here.

## Required Patterns

- Import directly from `property_core` (services, functions, models)
- No intermediate service/adapter layer between core and API
- Use `asyncio.to_thread` for sync service calls, `await` for async services
- Response models come from `property_core.models` (re-exported in `app/schemas/` for convenience)

## New Router Checklist

1. Create `app/api/v1/new_endpoint.py`
2. Define `router = APIRouter(prefix="/new", tags=["new"])`
3. Register in `app/api/routes.py`: import and `api_router.include_router(new_endpoint.router)`

## Error Handling

- `ValueError` from property_core → `HTTPException(status_code=422, detail=str(e))`
- Upstream network failures → `HTTPException(status_code=502, detail="upstream unavailable")`

## Reference Patterns

- Sync endpoint: `app/api/v1/ppd.py`
- Async endpoint: `app/api/v1/analysis.py`
- Simple calculator: `app/api/v1/stamp_duty.py`

Use `/add-endpoint` skill for the full workflow.
