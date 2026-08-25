"""Typed EPC failures.

The adapter — not the upstream — decides which of these applies. Missing and
invalid credentials produce an identical 403 from the API, but the adapter knows
whether it supplied a token, so the distinction is made locally.

None of these subclass ValueError: an upstream or configuration fault must never
be mistaken for caller error and mapped to a 4xx.
"""

from __future__ import annotations


class EPCError(Exception):
    """Base for every EPC failure."""


class EPCConfigurationError(EPCError):
    """No usable credential is configured. No request is made.

    Also raised when only the retired Basic-auth credentials are present:
    those are not a supported fallback, and silently ignoring them while
    reporting the integration as configured would be a lie.
    """


class EPCAuthenticationError(EPCError):
    """A token was supplied and the upstream rejected it (401/403)."""


class EPCRateLimitError(EPCError):
    """Upstream rate limit (429)."""


class EPCInvalidQueryError(EPCError):
    """The upstream rejected the query as malformed (HTTP 400).

    Caller error, not an outage: mapping it to 503 would tell an operator to
    retry something that will never succeed.
    """


class EPCUpstreamError(EPCError):
    """The EPC service could not be consulted, so absence cannot be concluded."""


class EPCUpstreamShapeError(EPCUpstreamError):
    """The response parsed but did not match the expected contract.

    Raised for a foreign envelope, a payload fed to the wrong adapter, or a
    malformed money object. Deliberately not degraded to None: a shape change
    that silently yields empty data is the failure mode this migration removes.
    """


class EPCAmbiguousMatchError(EPCError):
    """Candidate selection could not identify exactly one certificate.

    Raised rather than returning an arbitrary neighbour. The audit showed the
    legacy matcher accepting a different house on the same street (score 36)
    and tie-breaking between flats by upstream row order.
    """

    def __init__(self, message: str, candidates: list | None = None):
        super().__init__(message)
        self.candidates = candidates or []


class EPCUnsupportedOperationError(EPCError):
    """An operation the replacement upstream cannot support honestly.

    `search_all_by_postcode() -> list[EPCData]` is the case: search returns
    summaries only, EPCData.score is a non-Optional int, and fabricating a
    score is not compatibility.
    """
