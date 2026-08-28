"""Synthetic HM Land Registry Price Paid CSV rows.

The real feed is headerless, quoted, and sixteen columns wide in a fixed order.
These fixtures reproduce that shape exactly -- a build test that reads a
convenient made-up layout proves nothing about the file the pipeline is pointed
at in production.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, Sequence

#: The published column order of `pp-complete.csv`. No header row is emitted:
#: the real file has none.
SOURCE_COLUMNS: tuple[str, ...] = (
    "transaction_id", "price", "transfer_date", "postcode", "property_type",
    "new_build", "duration", "paon", "saon", "street", "locality", "town",
    "district", "county", "ppd_category", "record_status",
)


def csv_row(
    transaction_id: str,
    postcode: str,
    transfer_date: str,
    price: int = 250_000,
    *,
    property_type: str = "F",
    new_build: str = "N",
    duration: str = "L",
    paon: str = "1",
    saon: str = "",
    street: str = "HIGH STREET",
    locality: str = "",
    town: str = "BIRMINGHAM",
    district: str = "BIRMINGHAM",
    county: str = "WEST MIDLANDS",
    ppd_category: str = "A",
    record_status: str = "A",
) -> tuple[str, ...]:
    """One source row, in published column order."""
    return (
        transaction_id, str(price), transfer_date, postcode, property_type,
        new_build, duration, paon, saon, street, locality, town, district,
        county, ppd_category, record_status,
    )


def write_source_csv(path: Path, rows: Iterable[Sequence[str]]) -> Path:
    """Write rows in the published dialect: quoted, comma separated, no header."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, quoting=csv.QUOTE_ALL, lineterminator="\n")
        for row in rows:
            writer.writerow(list(row))
    return path


def spanning_rows(years: Iterable[int]) -> list[tuple[str, ...]]:
    """One row per year, enough to fill an eleven-partition window."""
    return [
        csv_row(f"{{T-{year}}}", "B5 7AA", f"{year}-06-15 00:00", 200_000 + year)
        for year in years
    ]
