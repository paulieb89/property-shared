"""DuckDB adapter over a materialized snapshot.

**This is where READY becomes permission to route.** The boot runtime proves
structural facts -- the bundle matched its digest, every archive member was safe,
the unpacked inventory is exactly what was written. None of that says the Parquet
files parse, carry the columns a query needs, or hold the rows the record claims.
`SnapshotAdapter.open` establishes those three before it will answer anything,
and refuses with a typed `SnapshotFailure` otherwise -- which routing turns into
a live fallback, never into an empty result set.

Two properties this adapter has that the live path cannot:

* **Exact geography.** Membership is `outcode = ?` / `sector = ?` against
  materialized columns, so `B5` cannot match `B50` by construction.
* **Limit-independent completeness.** It asks for `limit + 1` rows; a short
  answer is positive proof that nothing was truncated. That is real evidence,
  unlike the live path's `raw_bindings < fetch_limit`, which moves with the
  caller's page size.

Deliberately absent: any notion of widening the search. Escalation is a caller
decision made on evidence, never something a query does on its own.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from datetime import date
from typing import Any, Iterable, Optional, Sequence

from property_core.models.ppd import PPDTransaction
from property_core.postcode_rules import (
    is_sector,
    normalise_postcode,
    normalise_prefix,
)
from property_core.provenance import CompletenessBasis
from property_core.snapshot.duckdb_support import require_duckdb
from property_core.snapshot.errors import (
    SnapshotMetadataError,
    SnapshotNotQueryableError,
    SnapshotQueryError,
    SnapshotRowCountError,
    SnapshotSchemaError,
)
from property_core.snapshot.models import VerificationRecord
from property_core.snapshot.schema import (
    PROJECTION,
    REQUIRED_COLUMNS,
    normalise_type,
)

#: The relation name the adapter registers its Parquet files under.
VIEW = "ppd"

#: Reverse of the CSV codes carried through the build. Kept explicit rather than
#: trusting whatever string the column happens to hold.
_ESTATE_TYPES = frozenset({"F", "L"})
_PROPERTY_TYPES = frozenset({"D", "S", "T", "F", "O"})
_CATEGORIES = frozenset({"A", "B"})


@dataclass(frozen=True)
class SnapshotPage:
    """One page of snapshot rows plus the evidence that judges completeness.

    The two fields say different things, and the difference is the whole point:

    * `exhausted` is scoped to the PAGE -- the adapter asked for one row more
      than the caller wanted and did not get it, so this page ran out;
    * `completeness_basis` is scoped to the whole matching set. It is set only
      when the page ran out *and* it was the only page (`offset == 0`), because
      rows skipped over by an offset were never examined. A claim of
      completeness with no stated basis is not a claim anyone can check.
    """

    transactions: list[PPDTransaction]
    exhausted: bool
    fetch_limit: int
    #: The offset this page started at. `exhausted` is scoped to the page, so a
    #: non-zero offset means it cannot speak for the whole matching set.
    offset: int = 0
    completeness_basis: Optional[CompletenessBasis] = None


def _row_to_transaction(row: Sequence[Any]) -> PPDTransaction:
    """Map one projected row onto the shared transaction model.

    Codes are validated rather than passed through: a snapshot column holding
    something outside the known set becomes `None`, which reads as "not stated",
    instead of an invented code that a consumer would filter or display.
    """
    (transaction_id, price, transfer_date, postcode, property_type, duration,
     ppd_category, new_build, paon, saon, street, locality, town, district,
     county) = row

    def _code(value: Any, allowed: frozenset[str]) -> Optional[str]:
        if not isinstance(value, str):
            return None
        text = value.strip().upper()
        return text if text in allowed else None

    return PPDTransaction(
        # The bulk CSV wraps ids in braces; the Linked Data and SPARQL paths do
        # not. Stripped here so an id means the same thing on every source.
        transaction_id=(transaction_id or "").strip("{} ") or None,
        price=int(price) if price is not None else None,
        date=transfer_date.isoformat() if hasattr(transfer_date, "isoformat")
        else (str(transfer_date) if transfer_date is not None else None),
        postcode=postcode,
        property_type=_code(property_type, _PROPERTY_TYPES),
        estate_type=_code(duration, _ESTATE_TYPES),
        transaction_category=_code(ppd_category, _CATEGORIES),
        new_build=bool(new_build) if new_build is not None else None,
        paon=paon, saon=saon, street=street, locality=locality,
        town=town, district=district, county=county,
    )


@dataclass
class SnapshotAdapter:
    """A validated, queryable view over one materialized snapshot.

    Constructed through `open`, which is the only path that runs validation. A
    directly constructed instance is not routable, and nothing in this package
    constructs one.
    """

    directory: Path
    record: VerificationRecord
    _connection: Any = None
    _files: tuple[str, ...] = ()
    #: DuckDB connections are not safe to share across threads. The service layer
    #: runs sync calls in a thread pool, so every query holds this.
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _closed: bool = False

    # -- lifecycle ------------------------------------------------------
    @classmethod
    def open(cls, directory: Path | str, record: VerificationRecord) -> "SnapshotAdapter":
        """Connect, validate, and return a routable adapter -- or raise.

        On any validation failure the connection is closed before the error
        leaves this method: a rejected snapshot must not leak a DuckDB handle
        into a process that is about to serve from the live source for hours.
        """
        adapter = cls(directory=Path(directory), record=record)
        try:
            adapter._connect()
            adapter._validate()
        except Exception:
            adapter.close()
            raise
        return adapter

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                try:
                    self._connection.close()
                finally:
                    self._connection = None
            self._closed = True

    def __enter__(self) -> "SnapshotAdapter":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    @property
    def closed(self) -> bool:
        return self._closed

    # -- coverage -------------------------------------------------------
    @property
    def version(self) -> str:
        return self.record.version

    @property
    def coverage_from(self) -> Optional[str]:
        return self.record.coverage_from

    @property
    def coverage_to(self) -> Optional[str]:
        return self.record.coverage_to

    @property
    def provisional_from(self) -> Optional[str]:
        return self.record.provisional_from

    @property
    def imported_at(self) -> Optional[str]:
        return self.record.verified_at

    # -- validation -----------------------------------------------------
    @staticmethod
    def _quote(path: str) -> str:
        """A SQL string literal for a path we produced ourselves.

        These come from our own rglob over the verified directory, never from a
        caller. Quotes are still escaped so an odd filename on disk cannot break
        out of the literal.
        """
        return "'" + path.replace("'", "''") + "'"

    def _connect(self) -> None:
        duckdb = require_duckdb("the PPD snapshot adapter")
        files = sorted(str(p) for p in self.directory.rglob("*.parquet"))
        if not files:
            raise SnapshotNotQueryableError(
                f"no parquet files under {self.directory}")
        self._files = tuple(files)
        self._connection = duckdb.connect()

    def _create_view(self) -> None:
        # `hive_partitioning=false`: the build lays partitions out as
        # `year=<YYYY>/`, and letting DuckDB synthesise a `year` column from the
        # directory name would collide with the real column the build projects.
        #
        # `union_by_name=true` is safe ONLY because every partition has already
        # been validated individually. On its own it is actively dangerous: it
        # fills a column one partition lacks with NULLs, so a partition missing
        # `outcode` passes a check over the combined view, silently contributes
        # no rows to any outcode search, and the short result is then reported
        # as exhaustive. A whole year of sales disappears and the response says
        # nothing is missing. With the per-file gate ahead of it, all it now
        # tolerates is a partition carrying EXTRA columns.
        listed = ", ".join(self._quote(f) for f in self._files)
        try:
            self._execute(
                f"CREATE VIEW {VIEW} AS SELECT * FROM read_parquet([{listed}], "
                f"hive_partitioning=false, union_by_name=true)"
            )
        except Exception as exc:
            # DuckDB reads Parquet footers here, so a truncated or corrupt file
            # surfaces at view creation. Translated so a caller handles one
            # taxonomy rather than a bare `_duckdb.InvalidInputException`.
            raise SnapshotNotQueryableError(
                f"snapshot parquet files are not readable: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    def _validate(self) -> None:
        # Order matters. Every partition is checked on its own BEFORE the union
        # exists, because the union is what hides a partition-level defect.
        self._validate_coverage()
        for path in self._files:
            self._validate_partition(path)
        self._create_view()
        self._validate_schema(f"SELECT * FROM {VIEW}", source="the combined view")
        self._validate_row_count()
        self._validate_queryable()

    def _validate_coverage(self) -> None:
        """Coverage metadata must be sound before it can decide anything.

        Routing answers every coverage question from these three fields -- what
        to refuse, what to narrow, what a warning says. Absent or contradictory
        bounds do not degrade those decisions, they remove them silently, so an
        unusable record is a typed failure and the caller uses the live source.
        """
        def _parsed(value: Optional[str], field: str) -> date:
            if value is None:
                raise SnapshotMetadataError(
                    f"snapshot declares no {field}; routing cannot state what "
                    f"coverage it is answering within",
                    field=field,
                )
            try:
                return date.fromisoformat(value)
            except (TypeError, ValueError) as exc:
                raise SnapshotMetadataError(
                    f"snapshot {field} {value!r} is not an ISO date", field=field
                ) from exc

        coverage_from = _parsed(self.record.coverage_from, "coverage_from")
        coverage_to = _parsed(self.record.coverage_to, "coverage_to")
        if coverage_from > coverage_to:
            raise SnapshotMetadataError(
                f"snapshot coverage is inverted: coverage_from "
                f"{self.record.coverage_from} is after coverage_to "
                f"{self.record.coverage_to}",
                field="coverage_from",
            )

        provisional = self.record.provisional_from
        if provisional is not None:
            boundary = _parsed(provisional, "provisional_from")
            if not (coverage_from <= boundary <= coverage_to):
                raise SnapshotMetadataError(
                    f"snapshot provisional_from {provisional} is outside coverage "
                    f"{self.record.coverage_from}..{self.record.coverage_to}; a "
                    f"provisional tail that is not inside the data marks nothing",
                    field="provisional_from",
                )

    def _validate_partition(self, path: str) -> None:
        """One Parquet file, on its own terms. See `_create_view` for why."""
        self._validate_schema(f"SELECT * FROM read_parquet({self._quote(path)})",
                              source=path)

    def _validate_schema(self, relation: str, *, source: str) -> None:
        try:
            described = self._execute(f"DESCRIBE {relation}").fetchall()
        except Exception as exc:
            raise SnapshotNotQueryableError(
                f"{source} could not be described: {type(exc).__name__}: {exc}"
            ) from exc

        found = {str(row[0]): normalise_type(str(row[1])) for row in described}
        for column, accepted in REQUIRED_COLUMNS.items():
            if column not in found:
                raise SnapshotSchemaError(
                    f"{source} is missing required column {column!r}; routing "
                    f"cannot answer a query it has no column for",
                    column=column,
                )
            if found[column] not in accepted:
                raise SnapshotSchemaError(
                    f"{source}: column {column!r} has type {found[column]}, "
                    f"expected one of {sorted(accepted)}",
                    column=column,
                )

    def _validate_row_count(self) -> None:
        # count(*) over Parquet is answered from row-group metadata. Never
        # count(DISTINCT filename) -- Phase 3 found that scans every row.
        try:
            found = int(self._execute(f"SELECT count(*) FROM {VIEW}").fetchone()[0])
        except Exception as exc:
            raise SnapshotNotQueryableError(
                f"snapshot row count failed: {type(exc).__name__}: {exc}"
            ) from exc
        if found != self.record.rows:
            raise SnapshotRowCountError(expected=self.record.rows, found=found)

    def _validate_queryable(self) -> None:
        """Run the shape a request will run. Metadata parsing is not enough."""
        sql = (f"SELECT {', '.join(PROJECTION)} FROM {VIEW} "
               f"WHERE transfer_date IS NOT NULL "
               f"ORDER BY transfer_date DESC, transaction_id ASC LIMIT 1")
        try:
            rows = self._execute(sql).fetchall()
        except Exception as exc:
            raise SnapshotNotQueryableError(
                f"snapshot did not answer a probe query: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        if rows:
            try:
                _row_to_transaction(rows[0])
            except Exception as exc:
                raise SnapshotSchemaError(
                    f"snapshot row does not map onto the transaction model: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc

    # -- queries --------------------------------------------------------
    def _execute(self, sql: str, params: Sequence[Any] = ()) -> Any:
        if self._connection is None:
            raise SnapshotNotQueryableError("adapter has no open connection")
        return self._connection.execute(sql, list(params))

    def search(
        self,
        *,
        postcode: Optional[str] = None,
        postcode_prefix: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        property_types: Optional[Iterable[str]] = None,
        estate_type: Optional[str] = None,
        transaction_category: Optional[str] = None,
        new_build: Optional[bool] = None,
        limit: int = 20,
        offset: int = 0,
        order_desc: bool = True,
    ) -> SnapshotPage:
        """Rows matching the filters, plus completeness evidence.

        Every filter is pushed into SQL. Nothing is filtered client-side, which
        is what makes `limit + 1` mean what it says: a short answer proves the
        source was exhausted, not merely that our own post-filter discarded a
        lot.

        `offset` is honoured. Unlike the live path, paging here is exact: the
        ORDER BY is total (date, then transaction id), so successive pages
        neither repeat nor omit a row. `exhausted` still describes only the page
        that was fetched -- a short final page says nothing about the pages
        skipped over, so the caller must not read it as whole-sample
        completeness.
        """
        where: list[str] = []
        params: list[Any] = []

        # Geography by parsed column, never by text prefix. `normalise_*` raises
        # InvalidPostcodeError, which is a caller error and must NOT be caught
        # into a live fallback.
        if postcode is not None:
            where.append("postcode = ?")
            params.append(normalise_postcode(postcode))
        if postcode_prefix is not None:
            prefix = normalise_prefix(postcode_prefix)
            where.append("sector = ?" if is_sector(prefix) else "outcode = ?")
            params.append(prefix)

        if from_date:
            where.append("transfer_date >= CAST(? AS DATE)")
            params.append(from_date)
        if to_date:
            where.append("transfer_date <= CAST(? AS DATE)")
            params.append(to_date)
        if min_price is not None:
            where.append("price >= ?")
            params.append(int(min_price))
        if max_price is not None:
            where.append("price <= ?")
            params.append(int(max_price))

        types = sorted({t.strip().upper() for t in property_types}) if property_types else None
        if types:
            where.append(f"property_type IN ({', '.join('?' * len(types))})")
            params.extend(types)
        if estate_type:
            where.append("duration = ?")
            params.append(estate_type.strip().upper())
        if transaction_category:
            where.append("ppd_category = ?")
            params.append(transaction_category.strip().upper())
        if new_build is not None:
            where.append("new_build = ?")
            params.append(bool(new_build))

        limit = max(1, int(limit))
        offset = max(0, int(offset))
        # One more than asked for. The extra row is evidence, never data.
        fetch_limit = limit + 1
        direction = "DESC" if order_desc else "ASC"
        sql = (
            f"SELECT {', '.join(PROJECTION)} FROM {VIEW}"
            + (f" WHERE {' AND '.join(where)}" if where else "")
            # transaction_id breaks same-date ties, so the order is total and
            # repeating a query cannot repeat or omit a row.
            + f" ORDER BY transfer_date {direction}, transaction_id ASC"
            + f" LIMIT {fetch_limit} OFFSET {offset}"
        )

        with self._lock:
            try:
                rows = self._execute(sql, params).fetchall()
            except Exception as exc:
                raise SnapshotQueryError(
                    f"snapshot query failed: {type(exc).__name__}: {exc}"
                ) from exc

        exhausted = len(rows) <= limit
        # A basis is a claim that every matching row was examined, so it needs
        # BOTH facts: the page ended, and it was the only page. At an offset the
        # rows skipped over were never looked at, however short the final page
        # is. The provenance builder withdraws a basis at an offset as well;
        # that stays, but this type is exported and its evidence must be true on
        # its own terms rather than relying on a later caller to correct it.
        basis = (CompletenessBasis.LIMIT_PLUS_ONE
                 if exhausted and offset == 0 else None)
        return SnapshotPage(
            transactions=[_row_to_transaction(r) for r in rows[:limit]],
            exhausted=exhausted,
            fetch_limit=fetch_limit,
            offset=offset,
            completeness_basis=basis,
        )
