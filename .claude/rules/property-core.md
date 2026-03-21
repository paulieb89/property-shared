---
paths:
  - "property_core/**/*.py"
---

# property_core Rules

You are in the **core library layer** — pure Python, no FastAPI, no DB, no HTTP framework assumptions.

## Module Types

- **Transport clients** (`*_client.py`, `*_scraper.py`) — fetch data from external APIs, return typed Pydantic models
- **Domain services** (`*_service.py`, standalone functions) — orchestrate, compute, enforce guardrails
- **Models** (`models/*.py`) — Pydantic data classes
- **Utilities** (`interpret.py`, `enrichment.py`, `address_matching.py`, `stamp_duty.py`)

## Required Patterns

- `from __future__ import annotations` at the top of every module
- Type hints on all function signatures
- Docstrings on public functions
- Private functions use `_` prefix
- Pydantic models use `Field()` for defaults

## `raw` Field Rule

Transport-parsed models carry `raw: dict | None = Field(default=None, exclude=True)`:
- YES: PPDTransaction, EPCData, RightmoveListing, CompanyRecord, PostcodeResult
- NO: PropertyReport, PPDCompsResponse, BlockAnalysisResponse, YieldAnalysis, RentalAnalysis

## Data Only — No Interpretation

Core returns raw numbers (yield %, counts, prices). Interpretation labels ("strong"/"weak", "good"/"insufficient") belong in `interpret.py` and are called by consumers, not core services.

## Exports

New public symbols (classes, functions, models) MUST be exported from:
1. `property_core/models/__init__.py` (for models)
2. `property_core/__init__.py` (for the public API)

Add to both the import and the `__all__` list.

## Error Handling

- **Not found**: Return `None` (let caller decide)
- **Invalid input**: Raise `ValueError` with helpful message
- **Network errors**: Let bubble up or wrap in domain-specific exception

## Adding a New Data Source

See GUIDELINES.md "Adding a New Data Source" for the full 6-step checklist, or run `/add-data-source`.
