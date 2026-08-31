#!/usr/bin/env bash
# Single validation entrypoint: same commands for local pre-commit, CI (ci.yml),
# and the release gate (release.yml). Anchors to its own location rather than
# trusting the caller's cwd.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.." || { echo "cannot resolve repo root from script location" >&2; exit 1; }
[ "$(git rev-parse --show-toplevel 2>/dev/null)" = "$PWD" ] || { echo "not at a git repo root" >&2; exit 1; }

uv lock --check
uv run --locked pre-commit run --all-files
uv sync --locked --extra api --extra apps --extra cli --extra snapshot
uv run --locked pytest
