# Phase 2 Plan — Multiple “Surfaces” (Core + API + CLI + Demo UI)

Goal: run one project with several user touch surfaces (API, CLI dev tools, browser demo) sharing the same domain logic, while keeping boundaries clean.

## Architecture decisions (commit to these)

### Source of truth
- `property_core/` is the single source of truth for domain logic (PPD/EPC/Rightmove).
- `app/` is a thin FastAPI wrapper that exposes `property_core/` over HTTP.

### CLI strategy
- Default: CLI **imports `property_core`** (fast local dev, no server required).
- Optional: CLI can call the deployed API when `--api-url` is provided (validates real service behavior).

### Demo UI strategy
- Phase 2 demo UI lives in `app/web/` (FastAPI-served templates/static).
- Demo UI should **call the API routes** (even when same process) to validate contracts.
- A separate `ui/` (Next.js) is a later option if/when we want a real standalone webapp.

## Repo layout changes
- `property_cli/` (new) — Typer-based CLI package
- `app/web/` (new) — minimal demo UI (templates + static)
- `clients/python/` (generated) — OpenAPI client output (gitignored or committed by choice)

## Dependency management (uv + extras)

Keep one `pyproject.toml` with optional extras:
- `api`: `fastapi`, `uvicorn`
- `cli`: `typer`, optional `rich`
- `demo`: `jinja2`, optional `python-multipart`
- `dev`: `pytest`, `openapi-python-client`, `python-dotenv`

Guideline: base deps should be minimal; “surface” deps go into extras.

## Entry points (`[project.scripts]`)

Add scripts so each surface is runnable consistently:
- `property-api` → run FastAPI (uvicorn `app.main:app`)
- `property-cli` → Typer entrypoint (`property_cli.main:app`)
- `property-demo` → run API with demo routes enabled (could be same as `property-api` initially)

## API work (small tweaks)
- Add `/v1/meta/integrations` is already present; ensure it’s used by demo/CLI for self-check.
- Keep response normalization consistent (`record` + optional `raw`) for provider-backed endpoints.

## CLI scope (initial)

Commands (MVP):
- `property-cli meta integrations` (via core or API)
- `property-cli ppd comps --postcode ...`
- `property-cli ppd transaction --id ... [--raw]`
- `property-cli epc search --postcode ... [--address ...] [--raw]`
- `property-cli rightmove search-url --postcode ... --type sale|rent`
- `property-cli rightmove listings --search-url ... --max-pages 1`

Behavior:
- If `--api-url` is set, call HTTP endpoints.
- Otherwise, call `property_core` directly.

## Demo UI scope (initial)

Pages:
- `/demo` index with links
- `/demo/ppd` (postcode/prefix search, comps, transaction lookup)
- `/demo/epc` (postcode + optional address, toggle include_raw)
- `/demo/rightmove` (postcode → search url; optional fetch listings)

Implementation:
- Simple server-rendered HTML with fetch calls to `/v1/...`
- No auth
- Clear “this calls third-party services” note

## OpenAPI client generation (Python)

Add a documented command (and optional script) to generate:
- `uv run --extra dev openapi-python-client generate --url http://localhost:8000/openapi.json --output-path clients/python`

Decide whether to:
- commit generated client (stable consumer use), or
- ignore it and generate on demand (lighter repo).

## Testing strategy
- Keep unit tests fast and offline by default.
- Keep live tests gated behind `RUN_LIVE_TESTS=1`.
- Add minimal CLI smoke tests (offline) if feasible.

## Milestones
1) Adjust `pyproject.toml` extras + add scripts
2) Scaffold `property_cli/` + MVP commands (core mode first)
3) Add `--api-url` mode for CLI
4) Add `app/web/` demo pages that call API
5) Add OpenAPI client generation docs + optional script

