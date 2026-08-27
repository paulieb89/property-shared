"""Protocol-neutral PPD exceptions.

`property_core` has four consumers (REST API, two MCP servers, CLI) that map
failures differently, so these carry typed data and no transport concerns. The
REST layer chooses the response code; MCP surfaces them as tool errors; the CLI
exits non-zero.

The distinction these types exist to preserve: **a failure is not an absence**.
An empty result means "no matching rows within the stated coverage" and nothing
else.

See docs/design/ppd-source-routing.md section 3.2.
"""

from __future__ import annotations

from typing import Any, Optional


class PPDError(Exception):
    """Base for typed PPD failures. Never raised directly."""

    code = "ppd_error"
    retryable = False

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.code, "detail": str(self), "retryable": self.retryable}


class PPDCoverageError(PPDError):
    """The requested date range falls outside the available data.

    Carries both ranges as structured data so a caller can reformulate the
    request without parsing prose. Never answer such a request partially: a
    truncated result is indistinguishable from a complete one.
    """

    code = "ppd_coverage_error"
    retryable = False

    def __init__(
        self,
        *,
        coverage_from: str,
        coverage_to: str,
        requested_from: Optional[str] = None,
        requested_to: Optional[str] = None,
        source_release: Optional[str] = None,
        detail: str = "requested range precedes available coverage",
    ):
        if not coverage_from or not coverage_to:
            raise ValueError(
                "PPDCoverageError requires the available coverage range; an error "
                "that cannot state what IS available gives the caller no remedy"
            )
        self.coverage_from = coverage_from
        self.coverage_to = coverage_to
        self.requested_from = requested_from
        self.requested_to = requested_to
        self.source_release = source_release
        super().__init__(detail)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.code,
            "detail": str(self),
            "requested": {"from_date": self.requested_from, "to_date": self.requested_to},
            "available": {
                "coverage_from": self.coverage_from,
                "coverage_to": self.coverage_to,
            },
            "source_release": self.source_release,
            "retryable": self.retryable,
            "remedy": (
                f"set from_date >= {self.coverage_from}, or look up a known "
                f"transaction by its id"
            ),
        }


class InvalidPostcodeError(PPDError):
    """Caller supplied a postcode or prefix outside the allowlisted grammar.

    ``field`` distinguishes an exact postcode from a prefix. They share this
    type, but a consumer must be able to tell which input was wrong -- and an
    internally derived prefix that fails validation is a bug in our own
    derivation, not something to silently repair.
    """

    code = "invalid_postcode"
    retryable = False

    def __init__(self, value: str, *, field: str = "postcode", expected: str = ""):
        self.value = value
        self.field = field
        self.expected = expected
        detail = f"{field} {value!r} is not valid"
        if expected:
            detail += f"; expected {expected}"
        super().__init__(detail)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.code,
            "detail": str(self),
            "field": self.field,
            "value": self.value,
            "expected": self.expected,
            "retryable": self.retryable,
        }


class TransactionNotFoundError(PPDError):
    """No such transaction upstream. Distinct from a failed lookup."""

    code = "transaction_not_found"
    retryable = False

    def __init__(self, transaction_id: str, detail: str = ""):
        self.transaction_id = transaction_id
        super().__init__(detail or f"no transaction record for {transaction_id}")

    def to_dict(self) -> dict[str, Any]:
        return {**super().to_dict(), "transaction_id": self.transaction_id}


class SnapshotUnavailableError(PPDError):
    """No verified snapshot is open. Distinct from 'no rows matched'."""

    code = "snapshot_unavailable"
    retryable = True


class UpstreamUnavailableError(PPDError):
    """A live upstream failed. Distinct from both 'empty' and 'no snapshot'."""

    code = "upstream_unavailable"
    retryable = True
