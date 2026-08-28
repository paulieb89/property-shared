"""Tiny synthetic Parquet snapshots. Nothing large or real is ever committed.

Every snapshot built here is a handful of rows written by the same DuckDB the
adapter reads with, laid out exactly as the build pipeline will lay one out:
one directory per year partition, one Parquet file inside it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Optional

from property_core.snapshot.models import VerificationRecord
from property_core.snapshot.store import VERIFIED_RECORD, SnapshotStore

#: Column order the fixture writes. The adapter's contract is by NAME, not
#: position; this is only the order the fixture happens to emit.
COLUMNS = (
    "transaction_id", "price", "transfer_date", "postcode", "outcode", "sector",
    "property_type", "duration", "ppd_category", "new_build",
    "paon", "saon", "street", "locality", "town", "district", "county",
    "area", "year",
)


def row(
    transaction_id: str,
    postcode: str,
    transfer_date: str,
    price: int = 250_000,
    *,
    property_type: str = "F",
    duration: str = "L",
    ppd_category: str = "A",
    new_build: bool = False,
    paon: Optional[str] = "1",
    saon: Optional[str] = None,
    street: Optional[str] = "HIGH STREET",
    locality: Optional[str] = None,
    town: Optional[str] = "BIRMINGHAM",
    district: Optional[str] = "BIRMINGHAM",
    county: Optional[str] = "WEST MIDLANDS",
) -> dict[str, Any]:
    """One snapshot row with outcode/sector/area/year derived as the build does."""
    pc = postcode.strip().upper()
    head, _, tail = pc.partition(" ")
    return {
        "transaction_id": transaction_id,
        "price": price,
        "transfer_date": transfer_date,
        "postcode": pc,
        "outcode": head or None,
        "sector": f"{head} {tail[0]}" if tail else None,
        "property_type": property_type,
        "duration": duration,
        "ppd_category": ppd_category,
        "new_build": new_build,
        "paon": paon,
        "saon": saon,
        "street": street,
        "locality": locality,
        "town": town,
        "district": district,
        "county": county,
        "area": "".join(c for c in head if c.isalpha()) or "UNKNOWN",
        "year": int(transfer_date[:4]),
    }


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


#: DuckDB type for each column. Overridable so a test can write a snapshot with
#: the wrong type for one column and prove the schema gate rejects it.
DEFAULT_TYPES = {
    "transaction_id": "VARCHAR", "price": "BIGINT", "transfer_date": "DATE",
    "postcode": "VARCHAR", "outcode": "VARCHAR", "sector": "VARCHAR",
    "property_type": "VARCHAR", "duration": "VARCHAR", "ppd_category": "VARCHAR",
    "new_build": "BOOLEAN", "paon": "VARCHAR", "saon": "VARCHAR",
    "street": "VARCHAR", "locality": "VARCHAR", "town": "VARCHAR",
    "district": "VARCHAR", "county": "VARCHAR", "area": "VARCHAR", "year": "INTEGER",
}


def write_parquet_snapshot(
    directory: Path,
    rows: Iterable[dict[str, Any]],
    *,
    types: Optional[dict[str, str]] = None,
    drop_columns: Iterable[str] = (),
) -> int:
    """Write rows into `directory` as year=<YYYY>/data.parquet. Returns file count."""
    import duckdb

    types = {**DEFAULT_TYPES, **(types or {})}
    keep = [c for c in COLUMNS if c not in set(drop_columns)]
    rows = list(rows)
    directory.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    try:
        projection = ", ".join(f"CAST(c{i} AS {types[name]}) AS {name}"
                               for i, name in enumerate(keep))
        if rows:
            values = ", ".join(
                "(" + ", ".join(_sql_literal(r.get(name)) for name in keep) + ")"
                for r in rows
            )
            con.execute(
                f"CREATE TABLE src AS SELECT {projection} FROM (VALUES {values}) "
                f"AS t({', '.join(f'c{i}' for i in range(len(keep)))})"
            )
        else:
            empty = ", ".join(f"CAST(NULL AS {types[name]}) AS {name}" for name in keep)
            con.execute(f"CREATE TABLE src AS SELECT {empty} WHERE 1=0")

        years = sorted({r["year"] for r in rows}) or [1970]
        for year in years:
            part = directory / f"year={year}"
            part.mkdir(parents=True, exist_ok=True)
            con.execute(
                f"COPY (SELECT * FROM src WHERE year = {year}) "
                f"TO '{part / 'data.parquet'}' (FORMAT parquet)"
            )
        return len(years)
    finally:
        con.close()


def build_snapshot(
    root: Path,
    rows: Iterable[dict[str, Any]],
    *,
    version: str = "v20260101T000000Z",
    coverage_from: str = "2016-01-01",
    coverage_to: str = "2026-06-30",
    provisional_from: Optional[str] = "2026-04-01",
    declared_rows: Optional[int] = None,
    types: Optional[dict[str, str]] = None,
    drop_columns: Iterable[str] = (),
) -> tuple[Path, VerificationRecord]:
    """A materialized snapshot directory plus the record the store would hold.

    `declared_rows` defaults to the real count; pass a different value to prove
    the row-count gate rejects a snapshot that does not hold what it claims.
    """
    rows = list(rows)
    store = SnapshotStore(root)
    directory = store.snapshots_dir / version
    files = write_parquet_snapshot(directory, rows, types=types,
                                   drop_columns=drop_columns)

    record = VerificationRecord(
        version=version,
        bundle_sha256="0" * 64,
        bundle_bytes=1024,
        bundle_object=f"snapshot-{version}.tar",
        parquet_files=files,
        rows=len(rows) if declared_rows is None else declared_rows,
        verified_at="2026-01-01T00:00:00Z",
        coverage_from=coverage_from,
        coverage_to=coverage_to,
        provisional_from=provisional_from,
        layout="year",
        duckdb_version="1.5.5",
        inventory=SnapshotStore.inventory(directory),
    )
    (directory / VERIFIED_RECORD).write_text(record.model_dump_json(indent=2))
    store.set_current(version)
    return directory, record


def default_rows() -> list[dict[str, Any]]:
    """A small corpus with the geography traps the spec names.

    `B5` and `B50` are different places ~20 miles apart; `B5 6` and `B5 7` are
    different sectors. Same-date ties exist so ordering can be asserted.
    """
    return [
        row("T-B57-2024", "B5 7AA", "2024-03-01", 200_000),
        row("T-B57-2023", "B5 7AB", "2023-06-15", 210_000, property_type="T"),
        row("T-B56-2024", "B5 6QQ", "2024-03-01", 300_000),
        row("T-B50-2024", "B50 4AA", "2024-05-01", 400_000),
        row("T-B50-2022", "B50 4AB", "2022-05-01", 380_000),
        row("T-M37-2024", "M3 7AA", "2024-01-10", 250_000, town="MANCHESTER"),
        row("T-M38-2024", "M3 8AA", "2024-01-10", 260_000, town="MANCHESTER"),
        row("T-B57-CATB", "B5 7AC", "2024-02-01", 999_000, ppd_category="B"),
        row("T-B57-OTHER", "B5 7AD", "2024-02-02", 111_000, property_type="O"),
    ]


def read_verified(directory: Path) -> VerificationRecord:
    return VerificationRecord(**json.loads((directory / VERIFIED_RECORD).read_text()))
