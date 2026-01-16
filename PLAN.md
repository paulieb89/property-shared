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
- `app/core/` – settings + logging for the API wrapper (no DB/Redis in this repo).
- `app/schemas/` – Pydantic request/response models.
- `app/services/` – thin wrappers calling `property_core/` (optional; can keep routers thin too).
- `app/api/` – routers per domain (`ppd.py`, `epc.py`, `location.py`, `listings.py`).
- `app/clients/` – HTTP/session helpers (httpx async client with retries).
- `app/tasks/` – background jobs if we add batch scraping later.
Note: persistence (Postgres/Redis) is intentionally *not* baked into this shared repo right now; projects can add them when needed.

## Domain slices (initial scope)
### PPD (Land Registry Price Paid Data + optional UKHPI)

**Goal**
- Make Land Registry data usable without re-learning endpoints: “recent sold prices/comps” first, then richer address search, then UKHPI (house price index).

**Core (`property_core/`)**
- `property_core/ppd_client.py` (already vendored)
  - Bulk download URL builders (`complete_url`, `year_url`, `monthly_change_url`)
  - Linked Data helpers (`get_transaction_record`, `get_address`)
  - SPARQL search helper (`sparql_search`)
  - Comps helper (`get_comps_summary`)
- Planned additions
  - `property_core/ppd_sparql.py` (or extend `ppd_client.py`) to support the Land Registry “web form” style fields:
    - building name/number (PAON/SAON), street, town, district, county, locality, postcode
    - property type (D/S/T/F/O), new build (Y/N), estate type (F/L), transaction category (A/B)
    - min/max price, from/to date, limit/offset and sane hard caps
  - `property_core/ukhpi_client.py` (new) for UKHPI SPARQL patterns:
    - “region/month” lookups (e.g. Newport October 2013)
    - “properties for a region+month resource” (debug/inspection)
    - “HPI for all regions in a date range”

**API wrapper (`app/`)**
- `GET /v1/ppd/download-url`
  - Params: `kind=complete|year|monthly`, `year?`, `part?`, `fmt=csv|txt`
- `GET /v1/ppd/transactions`
  - Phase 1 (fast + reliable): `postcode` OR `postcode_prefix` (district/sector), plus optional filters already supported by `sparql_search`
  - Phase 2 (web-form style): address-part filters (paon/saon/street/town/district/county/locality) with strict caps and warnings
  - Result sizing: default `limit=50`, max `limit=200` (project can raise); “all” is not supported in the shared API.
- `GET /v1/ppd/comps`
  - Params: `postcode`, `property_type?`, `months?`, `limit?`, `search_level=postcode|sector|district`
  - Returns: `median/mean/min/max/count`, `thin_market`, and transactions list
- UKHPI (Phase 3)
  - `GET /v1/ukhpi/region-month` (region slug + YYYY-MM)
  - `GET /v1/ukhpi/range` (from/to date; optional region filters)

**Constraints + guardrails**
- SPARQL can be slow and sensitive to broad filters; keep default `limit` small, enforce max cap.
- Property type SPARQL filter sometimes causes 503s; prefer client-side filtering (current behavior).
- Address-part searches can be expensive; plan to:
  - require at least 2 fields (e.g., postcode + street, or town + street + building)
  - require a tight limit, and return a “results may be incomplete” note

**PPD milestones**
1) Phase 1: `/transactions` (postcode/prefix) + `/comps` + `/download-url`
2) Phase 2: web-form-style address search (bounded)
3) Phase 3: UKHPI endpoints

### EPC
- Core: `property_core/epc_client.py` (to build from `example_ref/epc.py` when we’re ready)
- API: `GET /v1/epc/search?postcode=&address?=`
- Guardrails: if creds missing, return `configured=false` + 501/204-style response decision; timeouts and small retry.

### Location scoring
- Core: `property_core/location/` (to build from `example_ref/location.py`)
- API: `GET /v1/location/assess?postcode=&address?=` and `POST /v1/location/batch`
- Guardrails: caching is project-level; in this repo we keep a pluggable cache interface (in-memory default).

### Listings (Rightmove)
- Core: `property_core/rightmove/` (to build from `example_ref/location_api.py` + `example_ref/rm_scraper.py`)
- API: `GET /v1/rightmove/search-url?postcode=&sale_or_rent=` and `GET /v1/rightmove/listings?...`
- Guardrails: “polite” by default (delay + low concurrency); projects can add Redis rate limiting later.

## Auth / access
- None for now (explicit). Leave hooks to add JWT/API keys later (middleware stub + dependency).

## API/SDK strategy
- Keep OpenAPI clean (typed responses). Generate Python client with `openapi-python-client`; consider TS later.
- Version routes under `/v1` to allow later breaking changes.

## Observability / ops
- Simple stdout logging + request timing middleware (upgrade to JSON logs/metrics when needed).
- Basic health endpoint; optional metrics via Prometheus-compatible middleware when needed.

## Next actions before coding
1) Scaffold FastAPI project skeleton with layout above.
2) Add `property_core/` and move/curate the “real” shared logic into it.
3) Implement PPD Phase 1 endpoints first (single vertical slice) with tests.
4) Add PPD Phase 2 address search, then UKHPI.
5) Add EPC + Rightmove + Location slices, then generate SDK.
