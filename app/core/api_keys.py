"""API-key gate for the public Rightmove surface.

Covers the `rightmove_*` MCP tools and every `/v1/rightmove/*` route. Both
surfaces must be gated together: gating one leaves the other as an open
scraping endpoint for the same listings.

Keys come from `RIGHTMOVE_API_KEYS` (comma-separated, set as a Fly secret) and
are read per request, so a rotated secret takes effect on the next restart
without code changes. With no keys configured the gate fails closed: every
remote caller is refused, rather than an unset secret silently reopening it.

Callers present a key as `Authorization: Bearer <key>` or `X-API-Key: <key>`.
Keys are deliberately not accepted in the query string: request lines are
logged, and a key in a URL ends up in those logs.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Mapping

from prometheus_client import Counter
from starlette.requests import Request

KEYS_ENV = "RIGHTMOVE_API_KEYS"
CONTACT_EMAIL = "paul@bouch.dev"
CONTACT_URL = "https://bouch.dev"

GATE_MESSAGE = (
    "Rightmove tools require an API key. Send it as 'Authorization: Bearer <key>' "
    f"or 'X-API-Key: <key>'. To request a key, email {CONTACT_EMAIL} or visit "
    f"{CONTACT_URL}."
)


# Per-key usage. `key_id` is an opaque sha256 prefix of a *validated* key, so
# /metrics (public) never shows a key or who holds it; the id -> holder mapping
# lives off-repo. Refused calls share key_id="none", so a caller cannot grow
# the label set by sending junk keys.
KEY_CALLS_TOTAL = Counter(
    "property_shared_rightmove_key_calls_total",
    "Remote Rightmove calls by API key (opaque id); key_id='none' means refused.",
    labelnames=("key_id",),
)


def key_id(key: str) -> str:
    """Opaque, stable id for a key: first 10 hex chars of its sha256."""
    return hashlib.sha256(key.encode()).hexdigest()[:10]


def _admit(key: str | None) -> bool:
    """Validate a presented key and count the call under its key_id."""
    if key and key_is_valid(key):
        KEY_CALLS_TOTAL.labels(key_id=key_id(key)).inc()
        return True
    KEY_CALLS_TOTAL.labels(key_id="none").inc()
    return False


def _configured_keys() -> list[str]:
    return [k.strip() for k in os.environ.get(KEYS_ENV, "").split(",") if k.strip()]


def presented_key(headers: Mapping[str, str]) -> str | None:
    """The key a request carries, from X-API-Key or a Bearer Authorization."""
    key = (headers.get("x-api-key") or "").strip()
    if key:
        return key
    scheme, _, token = (headers.get("authorization") or "").strip().partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return None


def key_is_valid(key: str | None) -> bool:
    if not key:
        return False
    # Compare against every key so timing does not reveal which one matched.
    matches = [hmac.compare_digest(key.encode(), k.encode()) for k in _configured_keys()]
    return any(matches)


def require_rightmove_key_mcp(tool: str) -> None:
    """Refuse an MCP tool call over HTTP that carries no valid key.

    Calls with no HTTP request behind them (stdio, in-process clients) are not
    gated, and not counted: they cannot come from a remote caller.
    """
    from fastmcp.server.dependencies import get_http_request
    from mcpfleet_obs import raise_tool_error

    try:
        # get_http_headers() strips `authorization`, so read the request itself.
        headers = get_http_request().headers
    except RuntimeError:
        return
    if not _admit(presented_key(headers)):
        raise_tool_error(
            "auth_required",
            is_retryable=False,
            attempted=tool,
            description=GATE_MESSAGE,
        )


async def require_rightmove_key_http(request: Request) -> None:
    """FastAPI dependency for the /v1/rightmove router."""
    from fastapi import HTTPException

    if not _admit(presented_key(request.headers)):
        raise HTTPException(
            status_code=401,
            detail={
                "error": "api_key_required",
                "message": GATE_MESSAGE,
                "contact": {"email": CONTACT_EMAIL, "url": CONTACT_URL},
            },
            headers={"WWW-Authenticate": 'Bearer realm="rightmove"'},
        )
