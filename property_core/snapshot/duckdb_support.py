"""Guarded access to the optional DuckDB dependency.

PR 3 does not query anything; this exists so that any later code path -- and any
operator who enables the flag without installing the extra -- gets an actionable
typed error instead of a bare ``ModuleNotFoundError: duckdb`` that names neither
the feature nor the fix.
"""

from __future__ import annotations

from typing import Any

from property_core.snapshot.errors import SnapshotExtraMissingError


def require_duckdb(feature: str = "the PPD snapshot source") -> Any:
    """Import duckdb, or raise a typed error naming the extra to install."""
    try:
        import duckdb  # noqa: PLC0415
    except ImportError as exc:
        raise SnapshotExtraMissingError(feature=feature, package="duckdb",
                                        extra="snapshot") from exc
    return duckdb
