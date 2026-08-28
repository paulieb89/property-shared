"""The gates a built snapshot must clear before anything is packaged from it.

**These gates do not decide the snapshot is servable.** They check what the
build declared against what it wrote. The merged runtime is the arbiter: digest
and length verification, member-validated extraction, an exact Parquet-file
count and a full file inventory, and then `SnapshotAdapter.open`, which runs its
own schema, row-count and queryability validation before routing. Running the
real thing end to end is part of acceptance for exactly that reason.

What is checked here, and why each one exists rather than being assumed:

* **schema** -- every partition on its own terms, against
  `property_core.snapshot.schema.REQUIRED_COLUMNS`. Per file, never over the
  union: the adapter's `union_by_name` fills a column one partition lacks with
  NULLs, so a defective partition passes a combined check while contributing no
  rows to any outcode search.
* **partitions** -- exactly the expected years, one `data.parquet` each, and
  nothing else in the tree.
* **rows** -- the declared count, the union count and the sum of the parts all
  agree.
* **uniqueness** -- `transaction_id` is a key across the whole window.
* **coverage** -- coverage is a *declaration about the source release*, not a
  measurement of the rows. So the bounds are checked for being the intended
  partition boundary and the release's declared end, and the data is checked for
  falling *inside* them. `min(transfer_date) == coverage_from` is deliberately
  NOT required: a window with no sale on its first day is normal, and demanding
  it would make the declaration follow the data instead of the other way round.
* **guarantee** -- the window still answers the largest request any surface
  accepts (`months le=120`). This is what makes eleven partitions load-bearing.
* **provisional** -- the boundary is the computed month and lies inside the
  window, which is the precondition the adapter's coverage validation applies.
* **ordering** -- each partition is in the declared logical order. Checked by
  physical row number, not by trusting scan order.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Optional

from property_core.snapshot.schema import REQUIRED_COLUMNS, normalise_type

from tools.ppd_snapshot.build import (
    PARTITION_FILE,
    expected_years,
    coverage_start,
    covers_maximum_request,
    provisional_boundary,
)

#: The order gates run in. Data gates are skipped when the schema gate fails,
#: because a query over a defective partition reports a defect of its own and
#: would bury the real one.
GATE_ORDER = ("partitions", "schema", "required_values", "rows",
              "reconciliation", "uniqueness", "coverage", "guarantee",
              "provisional", "ordering")
_DATA_GATES = frozenset({"required_values", "rows", "reconciliation",
                         "uniqueness", "coverage", "ordering"})


class _Skip(str):
    """A gate that could not run. Not a pass -- the report says so."""


@dataclass(frozen=True)
class GateFailure:
    gate: str
    detail: str

    def __str__(self) -> str:  # pragma: no cover - operator output
        return f"{self.gate}: {self.detail}"


@dataclass(frozen=True)
class GateResult:
    name: str
    #: "pass", "fail" or "skipped". A skipped gate is not a passing gate, and
    #: the report refuses to call itself passed while one is present.
    status: str
    detail: str = ""


@dataclass(frozen=True)
class ValidationReport:
    gates: tuple[GateResult, ...]
    facts: dict[str, Any]

    @property
    def failures(self) -> tuple[GateFailure, ...]:
        return tuple(GateFailure(g.name, g.detail)
                     for g in self.gates if g.status == "fail")

    @property
    def skipped(self) -> tuple[str, ...]:
        return tuple(g.name for g in self.gates if g.status == "skipped")

    @property
    def passed(self) -> bool:
        return not self.failures and not self.skipped


@dataclass(frozen=True)
class DeclaredSnapshot:
    """What the build says it produced. Every field here is a claim under test."""

    directory: Path
    coverage_from: date
    coverage_to: date
    provisional_from: date
    rows: int
    parquet_files: int
    #: Eligible rows counted from the source, independently of what was written.
    #: None means the source was not available to compare against, which is a
    #: skipped gate rather than a passing one.
    eligible_source_rows: Optional[int] = None

    def replace(self, **changes: Any) -> "DeclaredSnapshot":
        return dataclasses.replace(self, **changes)


@dataclass
class _Context:
    """Everything the gates share, resolved once."""

    files: dict[int, Path]
    strays: tuple[str, ...]
    today: date
    source_coverage_end: date
    connection: Any = None

    def relative(self, path: Path, root: Path) -> str:
        return path.relative_to(root).as_posix()


def _quote(value: Any) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _scan(paths: Iterable[Path]) -> str:
    listed = ", ".join(_quote(p) for p in paths)
    return (f"read_parquet([{listed}], hive_partitioning=false, "
            f"union_by_name=true)")


def _discover(directory: Path) -> tuple[dict[int, Path], tuple[str, ...]]:
    """Partition files by year, plus anything in the tree that is not one."""
    files: dict[int, Path] = {}
    strays: list[str] = []
    for path in sorted(directory.rglob("*")):
        if path.is_dir():
            continue
        relative = path.relative_to(directory)
        parts = relative.parts
        if (len(parts) == 2 and parts[0].startswith("year=")
                and parts[1] == PARTITION_FILE):
            try:
                files[int(parts[0][len("year="):])] = path
            except ValueError:
                strays.append(relative.as_posix())
            continue
        strays.append(relative.as_posix())
    return files, tuple(strays)


# -- gates -------------------------------------------------------------------

def _gate_partitions(declared: DeclaredSnapshot, ctx: _Context) -> Optional[str]:
    expected = set(expected_years(declared.coverage_to))
    found = set(ctx.files)
    problems = []
    if missing := sorted(expected - found):
        problems.append(f"missing partition(s) for {missing}")
    if extra := sorted(found - expected):
        problems.append(f"unexpected partition(s) for {extra}")
    if ctx.strays:
        problems.append(f"files that are not partitions: {list(ctx.strays)}")
    if declared.parquet_files != len(ctx.files):
        problems.append(f"declared {declared.parquet_files} parquet file(s), "
                        f"found {len(ctx.files)}")
    return "; ".join(problems) or None


def _gate_schema(declared: DeclaredSnapshot, ctx: _Context) -> Optional[str]:
    problems = []
    for year in sorted(ctx.files):
        path = ctx.files[year]
        name = ctx.relative(path, declared.directory)
        try:
            described = ctx.connection.execute(
                f"DESCRIBE SELECT * FROM read_parquet({_quote(path)})").fetchall()
        except Exception as exc:
            problems.append(f"{name} is not readable: {type(exc).__name__}: {exc}")
            continue
        found = {str(r[0]): normalise_type(str(r[1])) for r in described}
        for column, accepted in REQUIRED_COLUMNS.items():
            if column not in found:
                problems.append(f"{name} is missing required column {column!r}")
            elif found[column] not in accepted:
                problems.append(
                    f"{name} column {column!r} has type {found[column]}, "
                    f"expected one of {sorted(accepted)}")
    return "; ".join(problems) or None


def _gate_required_values(declared: DeclaredSnapshot,
                          ctx: _Context) -> Optional[str]:
    """No row may be missing a value the service has to have.

    `TRY_CAST` turns an unparseable price or date into NULL, which every other
    gate then waves through: the row count is right, the schema is right, and
    the snapshot serves a sale with no price. Required means required.
    """
    total, no_id, no_price, no_date = ctx.connection.execute(
        f"SELECT count(*), "
        f"       count(*) FILTER (WHERE transaction_id IS NULL "
        f"                           OR trim(transaction_id) = ''), "
        f"       count(*) FILTER (WHERE price IS NULL), "
        f"       count(*) FILTER (WHERE transfer_date IS NULL) "
        f"FROM {_scan(ctx.files.values())}").fetchone()
    problems = []
    for count, column in ((no_id, "transaction_id"), (no_price, "price"),
                          (no_date, "transfer_date")):
        if int(count):
            problems.append(f"{int(count)} of {int(total)} row(s) have no "
                            f"{column}")
    return "; ".join(problems) or None


def _gate_reconciliation(declared: DeclaredSnapshot,
                         ctx: _Context) -> Optional[str]:
    """What the source held against what the snapshot wrote.

    Every other count is taken from the artifact, so a row lost between reading
    the CSV and writing the Parquet is invisible to all of them: the snapshot is
    perfectly consistent with itself and quietly short.
    """
    if declared.eligible_source_rows is None:
        return _Skip("no source row count was supplied, so the snapshot cannot "
                     "be reconciled with what it was built from")
    written = int(ctx.connection.execute(
        f"SELECT count(*) FROM {_scan(ctx.files.values())}").fetchone()[0])
    if written != declared.eligible_source_rows:
        return (f"the source held {declared.eligible_source_rows} eligible "
                f"row(s) but the snapshot holds {written}")
    return None


def _gate_rows(declared: DeclaredSnapshot, ctx: _Context) -> Optional[str]:
    total = int(ctx.connection.execute(
        f"SELECT count(*) FROM {_scan(ctx.files.values())}").fetchone()[0])
    parts = 0
    for path in ctx.files.values():
        parts += int(ctx.connection.execute(
            f"SELECT count(*) FROM read_parquet({_quote(path)})").fetchone()[0])
    problems = []
    if declared.rows != total:
        problems.append(f"declared {declared.rows} row(s), the snapshot holds {total}")
    if parts != total:
        problems.append(f"partitions sum to {parts} but the combined view "
                        f"reports {total}")
    return "; ".join(problems) or None


def _gate_uniqueness(declared: DeclaredSnapshot, ctx: _Context) -> Optional[str]:
    # A missing id is the required-values gate's business; this one is only
    # about the id being a key.
    total, distinct = ctx.connection.execute(
        f"SELECT count(*), count(DISTINCT transaction_id) "
        f"FROM {_scan(ctx.files.values())}").fetchone()
    problems = []
    if int(total) != int(distinct):
        problems.append(f"{int(total)} row(s) carry only {int(distinct)} distinct "
                        f"transaction_id(s)")
    return "; ".join(problems) or None


def _gate_coverage(declared: DeclaredSnapshot, ctx: _Context) -> Optional[str]:
    problems = []
    boundary = coverage_start(declared.coverage_to)
    if declared.coverage_from != boundary:
        problems.append(f"coverage_from {declared.coverage_from} is not the "
                        f"partition boundary {boundary}")
    if declared.coverage_to != ctx.source_coverage_end:
        problems.append(f"coverage_to {declared.coverage_to} is not the source "
                        f"release's declared end {ctx.source_coverage_end}")

    outside = int(ctx.connection.execute(
        f"SELECT count(*) FROM {_scan(ctx.files.values())} "
        f"WHERE transfer_date < DATE {_quote(declared.coverage_from)} "
        f"   OR transfer_date > DATE {_quote(declared.coverage_to)}").fetchone()[0])
    if outside:
        problems.append(f"{outside} row(s) fall outside the declared window "
                        f"{declared.coverage_from}..{declared.coverage_to}")

    for year in sorted(ctx.files):
        path = ctx.files[year]
        misfiled = int(ctx.connection.execute(
            f"SELECT count(*) FROM read_parquet({_quote(path)}) "
            # A NULL date is the required-values gate's business, so it is not
            # counted here as well: one fault, one gate.
            f"WHERE year IS DISTINCT FROM {year} "
            f"   OR (transfer_date IS NOT NULL "
            f"       AND EXTRACT(year FROM transfer_date) IS DISTINCT FROM {year})"
        ).fetchone()[0])
        if misfiled:
            problems.append(
                f"{ctx.relative(path, declared.directory)} holds {misfiled} "
                f"row(s) that are not from {year}")
    return "; ".join(problems) or None


def _gate_guarantee(declared: DeclaredSnapshot, ctx: _Context) -> Optional[str]:
    if covers_maximum_request(declared.coverage_from, ctx.today):
        return None
    return (f"coverage_from {declared.coverage_from} does not reach back 120 "
            f"months from {ctx.today}; the largest permitted request would fall "
            f"outside the window")


def _gate_provisional(declared: DeclaredSnapshot, ctx: _Context) -> Optional[str]:
    expected = provisional_boundary(declared.coverage_to)
    problems = []
    if declared.provisional_from != expected:
        problems.append(f"provisional_from {declared.provisional_from} is not "
                        f"the computed boundary {expected}")
    if not (declared.coverage_from <= declared.provisional_from
            <= declared.coverage_to):
        problems.append(f"provisional_from {declared.provisional_from} is "
                        f"outside coverage {declared.coverage_from}.."
                        f"{declared.coverage_to}")
    return "; ".join(problems) or None


def _gate_ordering(declared: DeclaredSnapshot, ctx: _Context) -> Optional[str]:
    """`transfer_date DESC, transaction_id ASC`, checked by physical position.

    `file_row_number` is the file's own row order, so this does not depend on
    the scan happening to return rows in storage order.
    """
    problems = []
    for year in sorted(ctx.files):
        path = ctx.files[year]
        inversions = int(ctx.connection.execute(
            f"WITH ordered AS (SELECT file_row_number AS rn, transfer_date, "
            f"                        transaction_id "
            f"                 FROM read_parquet({_quote(path)}, "
            f"                                   file_row_number=true)) "
            f"SELECT count(*) FROM ordered a JOIN ordered b ON b.rn = a.rn + 1 "
            f"WHERE b.transfer_date > a.transfer_date "
            f"   OR (b.transfer_date = a.transfer_date "
            f"       AND b.transaction_id < a.transaction_id)").fetchone()[0])
        if inversions:
            problems.append(
                f"{ctx.relative(path, declared.directory)} has {inversions} "
                f"row(s) out of transfer_date DESC, transaction_id ASC order")
    return "; ".join(problems) or None


# -- runner ------------------------------------------------------------------

def content_digests(directory: Path | str,
                    connection: Any = None) -> dict[str, str]:
    """An order-sensitive digest of each partition's contents.

    This is how a rebuild is compared with the build before it. It is
    deliberately **logical**, not byte-level: whether DuckDB 1.5.5 writes
    byte-identical Parquet for identical input is a property of the writer that
    has not been established here, and asserting it would be testing an
    assumption. What matters to a reader of the snapshot is that the same source
    yields the same rows, with the same values, in the same order -- which this
    detects, and which a byte comparison would conflate with compressor detail.
    """
    import duckdb

    directory = Path(directory)
    con = connection or duckdb.connect()
    try:
        digests: dict[str, str] = {}
        for path in sorted(directory.glob(f"year=*/{PARTITION_FILE}")):
            year = path.parent.name[len("year="):]
            columns = [str(row[0]) for row in con.execute(
                f"DESCRIBE SELECT * FROM read_parquet({_quote(path)})").fetchall()]
            # Length-prefixed, so the encoding is injective. Joining fields
            # with a separator is not: `paon="A|B", saon="C"` and
            # `paon="A", saon="B|C"` are different properties that a delimiter
            # join renders as the same string, and the digest then stops
            # distinguishing them. A NULL gets its own marker for the same
            # reason -- it is a distinct value, not an empty one.
            rendered = ", ".join(
                f"CASE WHEN {name} IS NULL THEN 'N:' ELSE concat("
                f"  CAST(length(CAST({name} AS VARCHAR)) AS VARCHAR), ':', "
                f"  CAST({name} AS VARCHAR)) END"
                for name in columns)
            digests[year] = str(con.execute(
                f"SELECT coalesce(md5(string_agg(row_text, chr(10) "
                f"                              ORDER BY rn)), '') FROM ("
                f"  SELECT file_row_number AS rn, concat({rendered}) "
                f"         AS row_text "
                f"  FROM read_parquet({_quote(path)}, file_row_number=true))"
            ).fetchone()[0])
        return digests
    finally:
        if connection is None:
            con.close()


def _facts(ctx: _Context, declared: DeclaredSnapshot) -> dict[str, Any]:
    if ctx.connection is None or not ctx.files:
        return {}
    row = ctx.connection.execute(
        f"SELECT count(*), count(DISTINCT transaction_id), min(transfer_date), "
        f"max(transfer_date) FROM {_scan(ctx.files.values())}").fetchone()
    per_year = {}
    for year in sorted(ctx.files):
        per_year[str(year)] = int(ctx.connection.execute(
            f"SELECT count(*) FROM read_parquet({_quote(ctx.files[year])})"
        ).fetchone()[0])
    return {
        "rows": int(row[0]),
        "distinct_transaction_ids": int(row[1]),
        "earliest_transfer_date": str(row[2]) if row[2] else None,
        "latest_transfer_date": str(row[3]) if row[3] else None,
        "rows_per_year": per_year,
        "bytes_on_disk": sum(p.stat().st_size for p in ctx.files.values()),
        "content_digest_per_year": content_digests(declared.directory,
                                                   ctx.connection),
    }


def validate_snapshot(declared: DeclaredSnapshot, *, source_coverage_end: date,
                      today: date) -> ValidationReport:
    """Run every gate and report each one's result.

    All gates run, rather than stopping at the first failure: an operator fixing
    a build wants the whole picture, and a report that stops early hides how bad
    the artifact is.
    """
    import duckdb

    directory = Path(declared.directory)
    files, strays = _discover(directory)
    ctx = _Context(files=files, strays=strays, today=today,
                   source_coverage_end=source_coverage_end)

    results: list[GateResult] = []
    ctx.connection = duckdb.connect()
    try:
        schema_failed = False
        for name in GATE_ORDER:
            if name in _DATA_GATES and (schema_failed or not files):
                results.append(GateResult(
                    name, "skipped",
                    "not run: the partitions did not pass the schema gate"))
                continue
            detail = globals()[f"_gate_{name}"](declared, ctx)
            if name == "schema" and detail:
                schema_failed = True
            if isinstance(detail, _Skip):
                results.append(GateResult(name, "skipped", str(detail)))
            else:
                results.append(GateResult(name, "fail" if detail else "pass",
                                          detail or ""))
        facts = {} if schema_failed else _facts(ctx, declared)
    finally:
        ctx.connection.close()

    return ValidationReport(gates=tuple(results), facts=facts)
