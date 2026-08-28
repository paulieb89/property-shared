"""READY is not permission to route: the adapter must prove queryability first.

Spec section 4.4 / 4.5. The boot runtime establishes *structural* verification --
the bundle matched its digest, every archive member was safe, the file inventory
is exactly what was written. That is a strictly weaker claim than "this snapshot
answers queries correctly", and the routing layer is where the stronger claim has
to be earned: schema, row count, and an actual executed query.

Every failure here is a SnapshotFailure, which is the caller's signal to use the
live source -- never to return an empty result set.
"""

from __future__ import annotations

import pytest

duckdb = pytest.importorskip("duckdb", reason="needs the optional 'snapshot' extra")

from property_core.exceptions import SnapshotFailure  # noqa: E402
from property_core.snapshot.adapter import SnapshotAdapter  # noqa: E402
from property_core.snapshot.errors import (  # noqa: E402
    SnapshotNotQueryableError,
    SnapshotRowCountError,
    SnapshotSchemaError,
)
from tests.snapshot.snapshot_fixtures import build_snapshot, default_rows, row  # noqa: E402


def test_valid_snapshot_opens_and_reports_its_coverage(tmp_path):
    directory, record = build_snapshot(tmp_path, default_rows())
    with SnapshotAdapter.open(directory, record) as adapter:
        assert adapter.version == record.version
        assert adapter.coverage_from == "2016-01-01"
        assert adapter.coverage_to == "2026-06-30"
        assert adapter.provisional_from == "2026-04-01"


def test_missing_required_column_is_rejected(tmp_path):
    """A snapshot without `sector` cannot answer a sector query at all.

    Discovering that on the first request would surface as an empty result --
    the one thing an empty result must never mean.
    """
    directory, record = build_snapshot(tmp_path, default_rows(),
                                       drop_columns=["sector"])
    with pytest.raises(SnapshotSchemaError) as exc:
        SnapshotAdapter.open(directory, record)
    assert "sector" in str(exc.value)
    assert isinstance(exc.value, SnapshotFailure)


def test_wrong_column_type_is_rejected(tmp_path):
    """`transfer_date` as VARCHAR compares lexically, not chronologically.

    A date range filter would still "work" and silently return the wrong rows.
    """
    directory, record = build_snapshot(tmp_path, default_rows(),
                                       types={"transfer_date": "VARCHAR"})
    with pytest.raises(SnapshotSchemaError) as exc:
        SnapshotAdapter.open(directory, record)
    assert "transfer_date" in str(exc.value)


def test_row_count_mismatch_is_rejected(tmp_path):
    """The record says how many rows were built. Fewer means a partial snapshot."""
    rows = default_rows()
    directory, record = build_snapshot(tmp_path, rows,
                                       declared_rows=len(rows) + 5)
    with pytest.raises(SnapshotRowCountError) as exc:
        SnapshotAdapter.open(directory, record)
    assert str(len(rows)) in str(exc.value)
    assert str(len(rows) + 5) in str(exc.value)


def test_unreadable_parquet_is_rejected_as_not_queryable(tmp_path):
    """Structurally verified bytes can still be an unreadable Parquet file."""
    directory, record = build_snapshot(tmp_path, default_rows())
    target = next(directory.rglob("*.parquet"))
    target.write_bytes(b"PAR1" + b"\x00" * 64)
    with pytest.raises(SnapshotFailure) as exc:
        SnapshotAdapter.open(directory, record)
    assert isinstance(exc.value, (SnapshotNotQueryableError, SnapshotSchemaError))


def test_snapshot_with_no_parquet_files_is_rejected(tmp_path):
    directory, record = build_snapshot(tmp_path, default_rows())
    for parquet in directory.rglob("*.parquet"):
        parquet.unlink()
    with pytest.raises(SnapshotFailure):
        SnapshotAdapter.open(directory, record)


def test_row_count_uses_metadata_not_a_full_scan(tmp_path, monkeypatch):
    """count(*) over Parquet reads row-group metadata; nothing may scan values.

    Phase 3 found a readiness probe using `count(DISTINCT filename)`, which reads
    every row. Asserted by inspecting the statements the adapter issues.
    """
    directory, record = build_snapshot(tmp_path, default_rows())
    seen: list[str] = []
    original = SnapshotAdapter._execute

    def _record(self, sql, params=()):
        seen.append(sql)
        return original(self, sql, params)

    monkeypatch.setattr(SnapshotAdapter, "_execute", _record)
    with SnapshotAdapter.open(directory, record):
        pass

    counts = [s for s in seen if "count(" in s.lower()]
    assert counts, "expected a row-count statement during validation"
    assert not any("distinct" in s.lower() for s in counts)


def test_validation_failure_leaves_no_open_connection(tmp_path):
    """A rejected snapshot must not leak a DuckDB connection into the process."""
    directory, record = build_snapshot(tmp_path, default_rows(),
                                       drop_columns=["sector"])
    with pytest.raises(SnapshotSchemaError) as exc:
        SnapshotAdapter.open(directory, record)
    assert getattr(exc.value, "connection", None) is None


def test_extra_columns_are_tolerated(tmp_path):
    """The contract is 'these columns, these types', not 'exactly these columns'.

    A future build adding a column must not take the snapshot path down.
    """
    directory, record = build_snapshot(tmp_path, [row("T-1", "B5 7AA", "2024-01-01")])
    import duckdb as _duckdb

    parquet = next(directory.rglob("*.parquet"))
    con = _duckdb.connect()
    con.execute(
        f"COPY (SELECT *, 'extra' AS future_column FROM read_parquet('{parquet}')) "
        f"TO '{parquet}' (FORMAT parquet)"
    )
    con.close()
    record = record.model_copy(update={"inventory": dict(record.inventory)})
    with SnapshotAdapter.open(directory, record) as adapter:
        assert adapter.version == record.version
