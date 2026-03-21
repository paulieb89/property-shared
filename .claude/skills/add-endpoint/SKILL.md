---
name: add-endpoint
description: Use when adding a new API endpoint to app/api/v1/. Covers router creation, registration, and response patterns.
---

# Add an API Endpoint

API routers are thin HTTP wrappers — all business logic lives in property_core.

## Step 1: Create Router File

Create `app/api/v1/new_endpoint.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/new", tags=["new"])


@router.get("/action")
async def action_endpoint(
    required: str = Query(..., description="Required parameter"),
    optional: str | None = Query(None, description="Optional filter"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
):
    """Endpoint description."""
    import asyncio
    from property_core import SomeService

    try:
        result = await asyncio.to_thread(
            SomeService().method,
            param=required,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return result.model_dump(mode="json")
```

## Step 2: Register in routes.py

Open `app/api/routes.py`:

```python
from .v1 import new_endpoint
api_router.include_router(new_endpoint.router)
```

## Step 3: Response Model (optional)

- Prefer returning `property_core` models directly (Pydantic → JSON automatic)
- If you need an envelope, add to `app/schemas/new_endpoint.py`
- Re-export from `app/schemas/__init__.py` if needed

## Patterns

| Pattern | Example |
|---------|---------|
| Sync service call | `app/api/v1/ppd.py` |
| Async service call | `app/api/v1/analysis.py` |
| Simple calculator | `app/api/v1/stamp_duty.py` |
| Configuration check | `app/api/v1/epc.py` |

## Checklist

- [ ] Router file created in `app/api/v1/`
- [ ] Router registered in `app/api/routes.py`
- [ ] No business logic in the router (property_core handles that)
- [ ] `Query()` annotations with descriptions on all parameters
- [ ] Error handling: `ValueError` → 422, upstream failure → 502
