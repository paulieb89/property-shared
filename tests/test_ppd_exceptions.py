"""PR 1 — protocol-neutral PPD exceptions.

`property_core` is a pure library with four consumers (REST, two MCP servers,
CLI). Its exceptions therefore carry *typed data*, never HTTP status codes: the
mapping to 422/502/503 belongs to the REST layer, and MCP/CLI map the same types
differently.

Spec: docs/design/ppd-source-routing.md section 3.2.
"""

from __future__ import annotations

import inspect

import pytest

from property_core import exceptions as exc_mod
from property_core.exceptions import (
    PPDCoverageError,
    PPDError,
    SnapshotUnavailableError,
    UpstreamUnavailableError,
)


def test_coverage_error_carries_requested_and_available_as_structured_data():
    err = PPDCoverageError(
        requested_from="2004-01-01",
        requested_to=None,
        coverage_from="2016-01-01",
        coverage_to="2026-06-30",
        source_release="v20260827T123230Z",
    )
    payload = err.to_dict()
    assert payload["error"] == "ppd_coverage_error"
    # structured objects, not prose
    assert payload["requested"] == {"from_date": "2004-01-01", "to_date": None}
    assert payload["available"] == {
        "coverage_from": "2016-01-01",
        "coverage_to": "2026-06-30",
    }
    assert payload["source_release"] == "v20260827T123230Z"


def test_coverage_error_requires_the_available_range():
    """An error that cannot tell the caller what IS available is useless."""
    with pytest.raises((TypeError, ValueError)):
        PPDCoverageError(requested_from="2004-01-01")  # type: ignore[call-arg]


def test_the_three_error_types_are_distinct():
    types = {PPDCoverageError, SnapshotUnavailableError, UpstreamUnavailableError}
    assert len({t.code for t in types}) == 3
    for t in types:
        assert issubclass(t, PPDError)
    assert not issubclass(SnapshotUnavailableError, UpstreamUnavailableError)
    assert not issubclass(UpstreamUnavailableError, SnapshotUnavailableError)


def test_snapshot_unavailable_is_not_an_empty_result():
    err = SnapshotUnavailableError("no verified snapshot is open")
    d = err.to_dict()
    assert d["error"] == "snapshot_unavailable"
    assert d["retryable"] is True
    assert "results" not in d and "count" not in d


def test_upstream_unavailable_is_distinct_from_snapshot_unavailable():
    assert (
        UpstreamUnavailableError("sparql timeout").to_dict()["error"]
        == "upstream_unavailable"
    )


def test_exceptions_are_protocol_neutral():
    """No HTTP status codes anywhere in the core exception module."""
    src = inspect.getsource(exc_mod)
    for token in ("422", "502", "503", "404", "status_code", "HTTPException"):
        assert token not in src, f"{token!r} leaks a transport concern into core"
