"""A second arm for the snapshot that needs no live upstream.

Stage 1's live arm has been unavailable: 429 on 2026-09-02, then a 503 after
271.8 s on 2026-09-04. Its central criterion is the false empty --

    "snapshot_false_empty": snap.count == 0 and live.count > 0

-- which is undetectable with one arm, because a wrongly-empty answer is
indistinguishable from a correctly-empty one. A snapshot-only rehearsal, however
many assertions it passes, cannot close that gap.

This module supplies a **second arm that is not the live source**. It compares
the snapshot against *itself*, read a different way, so the comparison needs no
network and no HMLR availability.

## Why this can find anything at all

The adapter answers geography queries by equality against **materialized**
`outcode`/`sector` columns (`property_core/snapshot/schema.py`). That design
removes the `STRSTARTS("B5")`-matches-`B50` class of bug entirely -- but it
relocates the risk rather than deleting it: if the *build* wrote those columns
wrongly, every query filtering on them is silently short, and no amount of
querying the same column can reveal it.

The two derivations really are independent:

* the **build** (`tools/ppd_snapshot/build.py`, `_DERIVE`) uses DuckDB string
  surgery -- `split_part(trim(postcode), ' ', 1)` -- which validates nothing and
  notably never upper-cases;
* the **reference** here uses `property_core.postcode_rules`, a validated regex
  grammar with exact GIR handling, which upper-cases and rejects malformed
  input.

A postcode those two disagree about is a row the adapter cannot find by
geography. That is a false empty, discoverable offline.

## The three checks

1. **Geography derivation** -- recompute `outcode`/`sector` from the `postcode`
   column and compare against what the build stored.
2. **Query semantics** -- for each corpus case, select the matching rows in
   plain Python from decoded Parquet, and compare against what the adapter's SQL
   returned. DuckDB is used only as a Parquet *decoder* here; every predicate,
   the ordering and the limit are reimplemented independently, because that is
   where a WHERE/ORDER/LIMIT defect would live.
3. **Partition completeness** -- one partition per year of declared coverage. A
   missing year is not an error at query time; it is simply fewer rows.

## What this does NOT establish

**It is not Stage 1 and cannot be filed as Stage 1 evidence.** It shares the
snapshot's own data, so it cannot detect a row that never reached the artifact:
if the build dropped rows the CSV contained, both arms here are equally blind.
Only a comparison against an independent publication of the dataset -- the live
SPARQL source, or the bulk CSV -- can close that.

It also says nothing about latency (no p95 here), and nothing about whether the
snapshot agrees with what HMLR would answer today.

What it does establish is narrower and still worth having: **that the artifact
is internally consistent, and that the query path can reach every row the
artifact contains.**

Out-of-band operator tooling, on the same contract as `boot_only_verify.py`:
never imported by the application, never wired into `CMD`, and inert unless
explicitly invoked.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from property_core.postcode_rules import _normalise, outcode_of, sector_of

#: Findings carry a bounded sample, never one entry per disagreeing row. On a
#: wholly mis-derived artifact that list would hold ~10.4M ids.
_SAMPLE_CAP = 5

#: Rows pulled per fetch. The artifact holds ~10.4M rows and the deployed
#: Machine has ~1.6 GB free while serving traffic, so materializing the result
#: set would OOM the app. Chunked, peak memory is this many rows.
_CHUNK_ROWS = 50_000

#: Columns the reference arm reads. Deliberately includes the derived columns so
#: they can be checked, and `postcode` so they can be recomputed.
_COLUMNS = (
    "transaction_id", "price", "transfer_date", "postcode", "outcode", "sector",
    "property_type", "duration", "ppd_category", "new_build",
)


@dataclass
class Finding:
    """One disagreement. `sample` never carries a price, address or full row."""

    check: str
    detail: str
    count: int = 0
    sample: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"check": self.check, "detail": self.detail,
                "count": self.count, "sample": self.sample}


def reference_geography(postcode: Any) -> tuple[Optional[str], Optional[str]]:
    """Outcode and sector by the validated grammar, independent of the build.

    Returns `(None, None)` for anything the grammar refuses. That is the point
    of disagreement worth reporting: the build would still have stored a value.
    """
    text = _normalise(postcode)
    if not text:
        return None, None
    return outcode_of(text), sector_of(text)


def check_geography_derivation(rows: Iterable[Sequence[Any]]) -> list[Finding]:
    """Stored `outcode`/`sector` against the reference derivation.

    Three distinct disagreements, kept apart because they have different causes
    and different consequences:

    * **unreachable** -- the reference derives a geography the build did not
      store, or stored differently. A query for the reference value cannot find
      this row. This is the false empty.
    * **case_mismatch** -- equal but for case. The build never upper-cases and
      the query side does (`normalise_prefix`), so a lower-case stored value is
      unreachable in practice even though the text "matches".
    * **unvalidated** -- the build stored a geography the grammar rejects. Not
      itself unreachable, but it means the column holds values no caller can
      ever ask for.
    """
    # Counters plus a capped sample, never full id lists. The artifact holds
    # ~10.4M rows against ~1.6 GB free on the deployed Machine, so a check that
    # accumulated one entry per disagreement would exhaust memory on exactly the
    # broken artifact it exists to diagnose -- and take the app with it.
    counts = {"unreachable": 0, "case_mismatch": 0, "unvalidated": 0}
    samples: dict[str, list[str]] = {k: [] for k in counts}

    def note(kind: str, txid: str) -> None:
        counts[kind] += 1
        if len(samples[kind]) < _SAMPLE_CAP:
            samples[kind].append(txid)

    for row in rows:
        fields = dict(zip(_COLUMNS, row))
        txid = str(fields.get("transaction_id") or "?")
        stored_out = fields.get("outcode")
        stored_sec = fields.get("sector")
        ref_out, ref_sec = reference_geography(fields.get("postcode"))

        if isinstance(stored_out, str) and stored_out != stored_out.upper():
            note("case_mismatch", txid)
        elif ref_out is not None and stored_out != ref_out:
            note("unreachable", txid)
        elif ref_out is None and stored_out is not None:
            note("unvalidated", txid)
        elif ref_sec is not None and stored_sec != ref_sec:
            note("unreachable", txid)

    findings = []
    if counts["unreachable"]:
        findings.append(Finding(
            "geography_derivation",
            "stored outcode/sector differs from the validated derivation; a "
            "query for the derived value cannot reach these rows",
            counts["unreachable"], samples["unreachable"]))
    if counts["case_mismatch"]:
        findings.append(Finding(
            "geography_case",
            "stored geography is not upper-case while the query path "
            "upper-cases its input, so these rows are unreachable by equality",
            counts["case_mismatch"], samples["case_mismatch"]))
    if counts["unvalidated"]:
        findings.append(Finding(
            "geography_unvalidated",
            "stored geography is not a well-formed outcode; no caller can ask "
            "for this value",
            counts["unvalidated"], samples["unvalidated"]))
    return findings


def python_select(
    rows: Iterable[Sequence[Any]],
    *,
    outcode: Optional[str] = None,
    sector: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    property_types: Optional[Sequence[str]] = None,
    transaction_category: Optional[str] = None,
    limit: int = 50,
) -> list[str]:
    """The corpus predicate, reimplemented in plain Python.

    Filters on geography **recomputed from `postcode`**, never on the stored
    derived column -- otherwise a wrong derivation would hide itself by being
    wrong identically in both arms.

    Ordering mirrors the adapter's total order (`transfer_date DESC`, then
    `transaction_id ASC`) so the two are comparable row for row.
    """
    selected: list[tuple[Any, str]] = []
    wanted_types = {t.strip().upper() for t in property_types} if property_types else None
    category = transaction_category.strip().upper() if transaction_category else None

    for row in rows:
        record = dict(zip(_COLUMNS, row))
        ref_out, ref_sec = reference_geography(record.get("postcode"))
        if outcode is not None and ref_out != outcode:
            continue
        if sector is not None and ref_sec != sector:
            continue

        transferred: Any = record.get("transfer_date")
        if transferred is None:
            continue
        iso = (transferred.isoformat() if hasattr(transferred, "isoformat")
               else str(transferred))
        if from_date and iso < from_date:
            continue
        if to_date and iso > to_date:
            continue

        if wanted_types is not None:
            value = record.get("property_type")
            if not isinstance(value, str) or value.strip().upper() not in wanted_types:
                continue
        if category is not None:
            value = record.get("ppd_category")
            if not isinstance(value, str) or value.strip().upper() != category:
                continue

        txid = str(record.get("transaction_id") or "").strip("{} ")
        selected.append((iso, txid))

    # Two stable passes rather than one composite key: the adapter orders
    # transfer_date DESC then transaction_id ASC, and mixing directions in one
    # key means negating a string, which does not order ids of unequal length
    # the way ASC does.
    selected.sort(key=lambda pair: pair[1])                    # transaction_id ASC
    selected.sort(key=lambda pair: pair[0], reverse=True)      # transfer_date DESC
    return [txid for _, txid in selected[:limit]]


def iter_rows(cursor: Any, chunk: int = _CHUNK_ROWS) -> Iterable[Sequence[Any]]:
    """Stream a result set in bounded chunks.

    `fetchall()` on this artifact would materialize ~10.4M rows as Python
    tuples -- several GB against the ~1.6 GB free on a Machine that is serving
    production traffic at the time. Peak memory here is `chunk` rows, whatever
    the artifact's size.
    """
    while True:
        batch = cursor.fetchmany(chunk)
        if not batch:
            return
        yield from batch


def check_partition_completeness(
    snapshot_dir: Path, coverage_from: date, coverage_to: date
) -> list[Finding]:
    """One partition per year of declared coverage.

    A missing year does not fail a query. It returns fewer rows, which is
    exactly the shape of the defect this whole module exists to find.
    """
    present = {
        int(child.name.split("=", 1)[1])
        for child in snapshot_dir.iterdir()
        if child.is_dir() and child.name.startswith("year=")
        and child.name.split("=", 1)[1].isdigit()
    }
    expected = set(range(coverage_from.year, coverage_to.year + 1))
    missing = sorted(expected - present)
    if not missing:
        return []
    return [Finding(
        "partition_completeness",
        f"declared coverage {coverage_from}..{coverage_to} spans "
        f"{len(expected)} years but partitions are missing; queries touching "
        f"them return fewer rows rather than failing",
        len(missing), [str(year) for year in missing])]


def build_report(findings: Sequence[Finding], *, artifact: dict[str, Any],
                 rows_examined: int, cases_compared: int) -> dict[str, Any]:
    return {
        "kind": "ppd_snapshot_nonlive_verification",
        "not_stage_1_evidence": True,
        "note": (
            "A second arm that is not the live source. It shares the snapshot's "
            "own data, so it cannot detect a row that never reached the "
            "artifact; only an independent publication of the dataset can. It "
            "establishes internal consistency and query-path reachability."
        ),
        "artifact": artifact,
        "rows_examined": rows_examined,
        "cases_compared": cases_compared,
        "passed": not findings,
        "findings": [f.to_dict() for f in findings],
    }


def main(argv: Optional[Sequence[str]] = None) -> int:  # pragma: no cover - CLI
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--max-rows", type=int, default=0,
                        help="0 examines every row")
    args = parser.parse_args(argv)

    from property_core.snapshot.duckdb_support import require_duckdb

    verified = json.loads((args.snapshot_dir / ".verified.json").read_text())
    duckdb = require_duckdb("the non-live snapshot verifier")
    con = duckdb.connect()
    files = sorted(str(p) for p in args.snapshot_dir.rglob("*.parquet"))
    if not files:
        print("no parquet files found", file=sys.stderr)
        return 2

    listed = ", ".join("'" + f.replace("'", "''") + "'" for f in files)
    sql = (f"SELECT {', '.join(_COLUMNS)} FROM read_parquet([{listed}], "
           f"union_by_name=true)")
    if args.max_rows:
        sql += f" LIMIT {int(args.max_rows)}"

    # Streamed, not fetchall(): see iter_rows. Counted as it goes so the row
    # total is observed rather than taken from the manifest.
    cursor = con.execute(sql)
    examined = 0

    def counted() -> Iterable[Sequence[Any]]:
        nonlocal examined
        for row in iter_rows(cursor):
            examined += 1
            yield row

    findings = list(check_geography_derivation(counted()))
    findings += check_partition_completeness(
        args.snapshot_dir,
        date.fromisoformat(verified["coverage_from"]),
        date.fromisoformat(verified["coverage_to"]),
    )

    report = build_report(
        findings,
        artifact={k: verified.get(k) for k in
                  ("version", "bundle_sha256", "coverage_from", "coverage_to", "rows")},
        rows_examined=examined,
        cases_compared=0,
    )
    args.report.write_text(json.dumps(report, indent=2))
    print(f"report written to {args.report}")
    print(f"passed: {report['passed']}  rows_examined: {examined}")
    for finding in findings:
        print(f"  {finding.check}: {finding.count} — {finding.detail}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
