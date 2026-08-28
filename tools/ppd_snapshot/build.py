"""`pp-complete.csv` -> eleven year-only Parquet partitions.

Layout and window are fixed by the governing specification:

* **Eleven calendar-year partitions** (section 1.1). Ten would silently
  under-serve a legal 120-month request for most of the year, because
  `PPDService.comps` measures its window from today rather than from a year
  boundary.
* **Year only, one file per year** (section 1.2). The adapter filters on
  `postcode`/`sector`/`outcode` and never on `area`, so a year+area layout
  charges thousands of files of Parquet metadata and prunes nothing.
* **`provisional_from` is recorded, never inferred at query time** (section 1.3).

Two things are derived here and stored as materialized columns rather than
computed per query:

* `outcode` / `sector`, which is what makes membership an equality test in the
  adapter and puts the `B5`-matching-`B50` class of bug out of reach; and
* `year`, which the adapter relies on being a real column -- it opens the
  partitions with `hive_partitioning=false` precisely so a synthesised
  directory-name column cannot collide with this one.

`transaction_id` is stored **without** the source's surrounding braces, so one
id means the same thing on every source: the bulk CSV wraps ids in `{...}`,
while the Linked Data and SPARQL paths do not. The adapter strips them too, and
that stays as a defensive no-op for snapshots built elsewhere.
"""

from __future__ import annotations

import resource
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

#: Section 1.1. Not a tunable: ten partitions cannot serve a 120-month request
#: made in December, and twelve buys coverage nothing asks for.
PARTITION_YEARS = 11

#: Section 1.3. HMLR revises recent months after first publication, so the tail
#: of the window is declared provisional in the manifest.
PROVISIONAL_MONTHS = 3

#: The largest window any surface may request, from `app/api/v1/ppd.py`'s
#: `months le=120` ceiling, expressed the way `PPDService.comps` computes it:
#: `date.today() - timedelta(days=months * 30)`.
MAX_REQUEST_DAYS = 120 * 30

COMPRESSION = "zstd"
ROW_GROUP_SIZE = 122_880

#: The published column order of the source feed. Headerless, sixteen columns.
SOURCE_COLUMNS: tuple[str, ...] = (
    "transaction_id", "price", "transfer_date", "postcode", "property_type",
    "new_build", "duration", "paon", "saon", "street", "locality", "town",
    "district", "county", "ppd_category", "record_status",
)

#: One file per partition. The name is part of the bundle contract: the runtime
#: counts `*.parquet` and the adapter globs for them.
PARTITION_FILE = "data.parquet"


def expected_years(coverage_to: date) -> tuple[int, ...]:
    """The exact set of calendar years a snapshot for this release must hold."""
    return tuple(range(coverage_to.year - PARTITION_YEARS + 1, coverage_to.year + 1))


def coverage_start(coverage_to: date) -> date:
    """The declared window start: 1 January of the earliest partition year.

    A partition boundary, not the earliest transaction that happens to be in the
    data. Coverage is a statement about what the snapshot was built to hold.
    """
    return date(coverage_to.year - PARTITION_YEARS + 1, 1, 1)


def provisional_boundary(coverage_to: date,
                         months: int = PROVISIONAL_MONTHS) -> date:
    """First day of the month `months` before the month of `coverage_to`."""
    if months < 0:
        raise ValueError("months must not be negative")
    index = coverage_to.year * 12 + (coverage_to.month - 1) - months
    return date(index // 12, index % 12 + 1, 1)


def covers_maximum_request(coverage_from: date, today: date) -> bool:
    """Whether the window still serves the largest request a surface permits."""
    return (today - coverage_from).days >= MAX_REQUEST_DAYS


@dataclass(frozen=True)
class BuildRequest:
    """Everything the build needs, stated rather than discovered.

    `coverage_to` is an **input**, not a measurement: it is the source release's
    declared coverage end, taken from the release the CSV came from. Deriving it
    from `max(transfer_date)` would let a truncated download declare a window it
    has data for, which is exactly the claim coverage must not be able to make.
    """

    csv_path: Path
    out_dir: Path
    coverage_to: date
    temp_dir: Path
    memory_limit: str = "4GB"


@dataclass(frozen=True)
class BuildResult:
    snapshot_dir: Path
    coverage_from: date
    coverage_to: date
    provisional_from: date
    years: tuple[int, ...]
    parquet_files: int
    rows: int
    source_rows: int
    rows_outside_window: int
    rows_without_date: int
    duckdb_version: str
    #: Peak resident memory of the build process, in MB. Recorded so a future
    #: build on a smaller machine can be sized rather than guessed at.
    peak_rss_mb: float = 0.0
    timings_seconds: dict[str, float] = field(default_factory=dict)


def _sql_literal(path: Path | str) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def _clear_database(db_path: Path) -> None:
    for suffix in ("", ".wal", ".tmp"):
        candidate = Path(str(db_path) + suffix)
        if candidate.is_file():
            candidate.unlink()


_DERIVE = """
CREATE OR REPLACE TABLE ppd AS
SELECT
  trim(transaction_id, '{{}} ')                   AS transaction_id,
  TRY_CAST(price AS BIGINT)                       AS price,
  TRY_CAST(transfer_date AS TIMESTAMP)::DATE      AS transfer_date,
  nullif(trim(postcode), '')                      AS postcode,
  CASE WHEN nullif(trim(postcode), '') IS NULL THEN NULL
       ELSE split_part(trim(postcode), ' ', 1) END AS outcode,
  CASE WHEN nullif(trim(postcode), '') IS NULL
         OR split_part(trim(postcode), ' ', 2) = '' THEN NULL
       ELSE split_part(trim(postcode), ' ', 1) || ' '
            || substr(split_part(trim(postcode), ' ', 2), 1, 1)
  END                                             AS sector,
  property_type,
  new_build = 'Y'                                 AS new_build,
  duration, paon, saon, street, locality, town, district, county, ppd_category,
  CAST(EXTRACT(year FROM TRY_CAST(transfer_date AS TIMESTAMP)) AS INTEGER) AS year
FROM staged
WHERE TRY_CAST(transfer_date AS TIMESTAMP)::DATE BETWEEN DATE {coverage_from}
                                                     AND DATE {coverage_to}
"""


def build_snapshot(request: BuildRequest) -> BuildResult:
    """Build the partitions and report what was written. Validation is separate.

    This function does not judge its own output: `validate.py` runs the gates,
    and the merged runtime is the final arbiter. Keeping the two apart is what
    lets a gate fail on an artifact this code was perfectly happy with.
    """
    import duckdb

    coverage_from = coverage_start(request.coverage_to)
    provisional_from = provisional_boundary(request.coverage_to)
    years = expected_years(request.coverage_to)

    temp_dir = Path(request.temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    snapshot_dir = Path(request.out_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    db_path = temp_dir / "build.duckdb"
    _clear_database(db_path)

    timings: dict[str, float] = {}
    con = duckdb.connect(str(db_path))
    try:
        con.execute(f"SET temp_directory={_sql_literal(temp_dir)}")
        con.execute(f"SET memory_limit='{request.memory_limit}'")
        duckdb_version = con.execute("SELECT version()").fetchone()[0]

        started = time.perf_counter()
        columns = ", ".join(f"'{name}': 'VARCHAR'" for name in SOURCE_COLUMNS)
        con.execute(
            f"CREATE OR REPLACE TABLE staged AS SELECT * FROM read_csv("
            f"{_sql_literal(request.csv_path)}, header=false, "
            f"columns={{{columns}}}, ignore_errors=false)"
        )
        source_rows = con.execute("SELECT count(*) FROM staged").fetchone()[0]
        timings["ingest"] = time.perf_counter() - started

        started = time.perf_counter()
        con.execute(_DERIVE.format(
            coverage_from=_sql_literal(coverage_from.isoformat()),
            coverage_to=_sql_literal(request.coverage_to.isoformat()),
        ))
        rows = con.execute("SELECT count(*) FROM ppd").fetchone()[0]
        # Accounted for explicitly rather than left as a silent difference: a
        # row the window excluded and a row with no parseable date are different
        # facts, and only one of them is expected.
        without_date = con.execute(
            "SELECT count(*) FROM staged "
            "WHERE TRY_CAST(transfer_date AS TIMESTAMP) IS NULL").fetchone()[0]
        timings["derive"] = time.perf_counter() - started

        started = time.perf_counter()
        for year in years:
            partition = snapshot_dir / f"year={year}"
            partition.mkdir(parents=True, exist_ok=True)
            # Written a year at a time, ORDER BY inside the COPY: the ordering is
            # part of the artifact, asserted by the ordering gate rather than
            # assumed. `preserve_insertion_order` is deliberately left at its
            # default -- turning it off lets the writer emit rows in any order,
            # which would quietly make the declared sort order a fiction.
            con.execute(
                f"COPY (SELECT * FROM ppd WHERE year = {year} "
                f"      ORDER BY transfer_date DESC, transaction_id ASC) "
                f"TO {_sql_literal(partition / PARTITION_FILE)} "
                f"(FORMAT parquet, COMPRESSION '{COMPRESSION}', "
                f" ROW_GROUP_SIZE {ROW_GROUP_SIZE})"
            )
        timings["write"] = time.perf_counter() - started
    finally:
        con.close()
        _clear_database(db_path)

    return BuildResult(
        snapshot_dir=snapshot_dir,
        coverage_from=coverage_from,
        coverage_to=request.coverage_to,
        provisional_from=provisional_from,
        years=years,
        parquet_files=sum(1 for _ in snapshot_dir.rglob("*.parquet")),
        rows=int(rows),
        source_rows=int(source_rows),
        rows_outside_window=int(source_rows) - int(rows) - int(without_date),
        rows_without_date=int(without_date),
        duckdb_version=str(duckdb_version),
        peak_rss_mb=round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 1),
        timings_seconds={k: round(v, 3) for k, v in timings.items()},
    )
