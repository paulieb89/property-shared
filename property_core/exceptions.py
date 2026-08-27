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


class SnapshotUnavailableError(PPDError):
    """No verified snapshot is open. Distinct from 'no rows matched'."""

    code = "snapshot_unavailable"
    retryable = True


class UpstreamUnavailableError(PPDError):
    """A live upstream failed. Distinct from both 'empty' and 'no snapshot'."""

    code = "upstream_unavailable"
    retryable = True
