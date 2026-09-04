"""Refuse query parameters the route does not declare.

FastAPI ignores undeclared query parameters. That is a fine HTTP default and a
poor one here, because the parameters callers get wrong are the ones that bound
the answer. The case that prompted this:

    GET /v1/ppd/transactions?postcode=NG11+9HD&months=24

`months` does not exist on that route — it takes `from_date`/`to_date`, while
the MCP tool of the same name takes `months`. The request succeeded, scanned the
full window instead of two years, took 1.7 s instead of 0.27 s, and returned a
plausible answer to a question nobody asked. Nothing said the filter had been
dropped, so nothing could notice — least of all a model, which had no second
source to compare against.

A silently discarded parameter is worse than a rejected one. A rejection is
recoverable in the next tool call; a plausible wrong answer is not recoverable
at all, because nothing downstream knows to doubt it.

So this is a deliberate breaking change: requests that "succeeded" while
carrying a typo now fail. The response names the offending parameters, lists
what the route does accept, and suggests the near-miss — because the caller most
likely to hit this is an agent that has to fix it without a human reading a
changelog.
"""

from __future__ import annotations

import difflib
from typing import Iterable

from fastapi import HTTPException, Request

#: Parameters accepted anywhere, so a route need not declare them to tolerate
#: them. Kept deliberately small: every entry here is a name a typo can hide in.
_ALWAYS_ALLOWED: frozenset[str] = frozenset()

#: Cutoff for "did you mean". High enough that unrelated names are not paired
#: with a confident-looking suggestion, which would be its own wrong answer.
_SUGGESTION_CUTOFF = 0.7


def _declared(request: Request) -> set[str]:
    """Query parameter names this route declares, by alias where one is set."""
    route = request.scope.get("route")
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return set()

    names: set[str] = set()
    stack = [dependant]
    while stack:
        current = stack.pop()
        for param in current.query_params:
            names.add(param.alias or param.name)
        # Sub-dependencies may declare their own query parameters, including
        # this one; missing them would reject a parameter the route does accept.
        stack.extend(current.dependencies)
    return names


def _suggestions(unknown: Iterable[str], declared: Iterable[str]) -> dict[str, str]:
    declared = list(declared)
    out: dict[str, str] = {}
    for name in unknown:
        match = difflib.get_close_matches(name, declared, n=1, cutoff=_SUGGESTION_CUTOFF)
        if match:
            out[name] = match[0]
    return out


async def reject_unknown_query_params(request: Request) -> None:
    """Raise 400 naming every undeclared query parameter. Otherwise do nothing.

    400 rather than 422: the request itself is malformed, which is a different
    fact from a declared parameter carrying an invalid value. The latter stays
    422 with its typed body, as the rest of this API already does.
    """
    declared = _declared(request) | _ALWAYS_ALLOWED
    unknown = sorted({k for k in request.query_params.keys()} - declared)
    if not unknown:
        return

    supported = sorted(declared)
    raise HTTPException(
        status_code=400,
        detail={
            "error": "unknown_query_parameter",
            "detail": (
                f"unknown query parameter(s): {', '.join(unknown)}. This route "
                f"accepts: {', '.join(supported) or 'no query parameters'}. "
                f"Unknown parameters are refused rather than ignored, because a "
                f"silently dropped filter returns a plausible answer to a "
                f"different question."
            ),
            "unknown": unknown,
            "supported": supported,
            "did_you_mean": _suggestions(unknown, supported),
            "retryable": False,
        },
    )
