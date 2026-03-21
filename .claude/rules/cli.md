---
paths:
  - "property_cli/**"
---

# CLI Rules

Typer-based CLI with dual-mode operation.

## Dual-Mode Pattern

- **Default**: calls `property_core` directly (fast, no server needed)
- **`--api-url`**: switches to HTTP mode via the running API

## Required Patterns

- Import from `property_core` — never import from `app/`
- Use Rich for formatted output: `rprint()` for JSON, `Table` for tabular data
- All commands use Typer with type annotations on parameters
- Postcode arguments accept space-separated tokens (e.g., `"SW1A" "1AA"`), joined via `_join_tokens()`
- Optional `httpx` import for API mode (gated behind try/except)

## Reference

All commands are in `property_cli/main.py`. Follow existing patterns for new commands.
