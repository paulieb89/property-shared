# Property Shared API – Plan

Goal: ship a reusable FastAPI service (Fly.io) exposing shared property capabilities with no auth for now, plus a small pure-Python core library so other Python projects can reuse logic without HTTP.

## Stack + deps (latest as of today)
- `fastapi 0.128.0`, `uvicorn 0.40.0`
- `pydantic 2.12.5`, `pydantic-settings 2.12.0`
- `httpx 0.28.1`, `requests 2.32.5`, `tenacity 9.1.2`
- `beautifulsoup4 4.14.3`
- `openapi-python-client 0.28.1` (for generating SDK)

## Repo layout (proposed)
- `property_core/` – small Python core (no FastAPI); minimal dependencies; no persistence assumptions.
- `app/main.py` – FastAPI app factory, lifespan wiring, middleware.
- `app/core/` – settings, logging, db/redis pools, rate limiting utils.
- `app/schemas/` – Pydantic request/response models.
- `app/services/` – domain logic wrapping shared helpers (ppd, epc, location, listings).
- `app/api/` – routers per domain (`ppd.py`, `epc.py`, `location.py`, `listings.py`).
- `app/clients/` – HTTP/session helpers (httpx async client with retries).
- `app/tasks/` – background jobs if we add batch scraping later.
Note: persistence (Postgres/Redis) is intentionally *not* baked into this shared repo right now; projects can add them when needed.

## Domain slices (initial scope)
- **PPD**: expose search + comps + download URL. Use `pp_data/ppd_client.py`; wrap with input validation, optional cached responses, thin-market flag.
- **EPC**: `/epc/search` using `epc.py`; return friendly “not configured” when creds missing; set request timeout; bubble match score if helpful.
- **Location scoring**: async endpoint; move cache to Postgres; reuse `location.py` agent flow; batch by outcode.
- **Listings (Rightmove)**: build search URL from postcode via `location_api.py`; fetch listings via `rm_scraper.py`; enforce polite rate limits (in-memory delay + single-flight by default); retry with backoff already in helper.

## Auth / access
- None for now (explicit). Leave hooks to add JWT/API keys later (middleware stub + dependency).

## API/SDK strategy
- Keep OpenAPI clean (typed responses). Generate Python client with `openapi-python-client`; consider TS later.
- Version routes under `/v1` to allow later breaking changes.

## Observability / ops
- Structured JSON logging to stdout; request/response timing middleware.
- Basic health endpoint; optional metrics via Prometheus-compatible middleware when needed.

## Next actions before coding
1) Scaffold FastAPI project skeleton with layout above.
2) Add `property_core/` and move/curate the “real” shared logic into it.
3) Implement PPD endpoints first (single vertical slice) with tests.
4) Add EPC + Rightmove + Location slices, then generate SDK.
