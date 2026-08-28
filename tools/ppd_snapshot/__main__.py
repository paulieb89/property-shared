"""Operator entry point for the local snapshot build.

    uv run --extra snapshot python -m tools.ppd_snapshot all \
        --csv  /path/to/pp-complete.csv \
        --work /path/to/scratch \
        --dist /path/to/dist \
        --coverage-to 2026-06-30

Ordering is the control this command exists to enforce: **validate before
packaging.** A bundle that exists is a bundle someone can publish, so a snapshot
that fails a gate must never become one. `all` stops at the first failure and
leaves the dist directory empty.

**Local only, and deliberately so** (specification section 4.8). `--dist` is a
directory on this machine. Nothing here uploads, creates a bucket, reads a
secret or touches a deployed system; artifact distribution is separately
approved and is not part of this pipeline.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Optional, Sequence

from tools.ppd_snapshot.build import (
    BuildRequest,
    BuildResult,
    build_snapshot,
    coverage_start,
    provisional_boundary,
)
from tools.ppd_snapshot.package import (
    package_release,
    snapshot_version,
    verify_bundle,
)
from tools.ppd_snapshot.release_check import (
    DEFAULT_URL,
    check_release,
    declared_coverage_end,
    describe,
    record_ingested,
)
from tools.ppd_snapshot.validate import DeclaredSnapshot, validate_snapshot


def _iso(value: Optional[str]) -> Optional[date]:
    return date.fromisoformat(value) if value else None


def _declared(built: BuildResult) -> DeclaredSnapshot:
    return DeclaredSnapshot(
        directory=built.snapshot_dir,
        coverage_from=built.coverage_from,
        coverage_to=built.coverage_to,
        provisional_from=built.provisional_from,
        rows=built.rows,
        parquet_files=built.parquet_files,
    )


def _print_report(report) -> None:
    for gate in report.gates:
        mark = {"pass": "ok  ", "fail": "FAIL", "skipped": "skip"}[gate.status]
        line = f"  [{mark}] {gate.name}"
        print(line if not gate.detail else f"{line} -- {gate.detail}")


def _source_end(args) -> Optional[date]:
    """The release's declared coverage end, from the release record if not given.

    Kept independent of `--coverage-to` on purpose: the two agreeing is the
    check. Deriving one from the other would make the gate say nothing.
    """
    explicit = _iso(getattr(args, "source_coverage_end", None))
    if explicit:
        return explicit
    state_path = getattr(args, "release_state", None)
    if not state_path or not Path(state_path).is_file():
        return None
    try:
        state = json.loads(Path(state_path).read_text())
    except (OSError, ValueError):
        return None
    return declared_coverage_end(state.get("last_modified"))


# -- commands ----------------------------------------------------------------

def _cmd_check_release(args) -> int:
    check = check_release(args.url, args.state)
    print(describe(check))
    return 0


def _cmd_build(args) -> int:
    built = _build(args)
    print(f"built {built.rows} row(s) into {built.parquet_files} partition(s) "
          f"at {built.snapshot_dir}")
    return 0


def _build(args) -> BuildResult:
    work = Path(args.work)
    return build_snapshot(BuildRequest(
        csv_path=Path(args.csv),
        out_dir=work / "snapshot",
        coverage_to=date.fromisoformat(args.coverage_to),
        temp_dir=work / "tmp",
        memory_limit=args.memory,
    ))


def _cmd_validate(args) -> int:
    directory = Path(args.snapshot)
    coverage_to = date.fromisoformat(args.coverage_to)
    source_end = _source_end(args)
    if source_end is None:
        print("refusing to validate: the source release's declared coverage end "
              "is unknown; pass --source-coverage-end or --release-state")
        return 2
    if args.rows is None:
        # Said out loud: with no independently declared count, the rows gate is
        # comparing the artifact with itself and cannot fail. In the `all` path
        # the count comes from the build, before a single file was written.
        print("note: --rows not given, so the row count is read back from the "
              "artifact and the rows gate cannot fail")

    declared = DeclaredSnapshot(
        directory=directory,
        coverage_from=coverage_start(coverage_to),
        coverage_to=coverage_to,
        provisional_from=provisional_boundary(coverage_to),
        rows=args.rows if args.rows is not None else _count(directory),
        parquet_files=len(list(directory.glob("year=*/data.parquet"))),
    )
    report = validate_snapshot(declared, source_coverage_end=source_end,
                               today=_iso(args.today) or date.today())
    _print_report(report)
    return 0 if report.passed else 1


def _count(directory: Path) -> int:
    """Row count read back from the artifact, for a standalone validate run."""
    import duckdb

    files = sorted(directory.glob("year=*/data.parquet"))
    if not files:
        return 0
    listed = ", ".join("'" + str(p).replace("'", "''") + "'" for p in files)
    con = duckdb.connect()
    try:
        return int(con.execute(
            f"SELECT count(*) FROM read_parquet([{listed}], "
            f"union_by_name=true)").fetchone()[0])
    finally:
        con.close()


def _boot_check(dist_dir: Path, cache_dir: Path) -> dict:
    """Boot the published bundle through the merged runtime and open it.

    This is the acceptance that matters: the gates above are this pipeline
    marking its own work, while `SnapshotRuntime` plus `SnapshotAdapter` is the
    code that has to serve it.
    """
    from property_core.snapshot.adapter import SnapshotAdapter
    from property_core.snapshot.runtime import SnapshotRuntime
    from property_core.snapshot.source import LocalDirectorySource
    from property_core.snapshot.store import SnapshotStore

    store = SnapshotStore(cache_dir)
    runtime = SnapshotRuntime(source=LocalDirectorySource(dist_dir), store=store)
    report = runtime.boot()
    outcome = {
        "readiness": report.readiness.value,
        "version": report.version,
        "activated": report.activated,
        "bytes_downloaded": report.bytes_downloaded,
        "source_error": report.source_error,
        "timings_ms": report.timings_ms,
    }
    if not report.ready:
        return outcome

    record = store.verified_record(report.version)
    with SnapshotAdapter.open(Path(report.snapshot_dir), record) as adapter:
        outcome["adapter"] = {
            "coverage_from": adapter.coverage_from,
            "coverage_to": adapter.coverage_to,
            "provisional_from": adapter.provisional_from,
            "validated": True,
        }
    outcome["extracted_bytes"] = sum(
        p.stat().st_size for p in Path(report.snapshot_dir).rglob("*")
        if p.is_file())
    return outcome


def _cmd_all(args) -> int:
    work = Path(args.work)
    dist = Path(args.dist)
    source_end = _source_end(args)
    if source_end is None:
        print("refusing to build: the source release's declared coverage end is "
              "unknown; pass --source-coverage-end or --release-state")
        return 2

    built = _build(args)
    print(f"built {built.rows} row(s) into {built.parquet_files} partition(s) "
          f"at {built.snapshot_dir}")

    report = validate_snapshot(_declared(built), source_coverage_end=source_end,
                               today=_iso(args.today) or date.today())
    _print_report(report)
    if not report.passed:
        print("validation failed; nothing was packaged")
        return 1

    version = args.version or snapshot_version()
    source = {"file": Path(args.csv).name}
    if args.release_state and Path(args.release_state).is_file():
        try:
            state = json.loads(Path(args.release_state).read_text())
            source.update({k: state.get(k) for k in
                           ("url", "etag", "last_modified", "content_length")})
        except (OSError, ValueError):
            pass
    if args.source_sha256:
        source["sha256"] = args.source_sha256

    release = package_release(built, dist_dir=dist, version=version,
                              source=source,
                              facts={"gates": "passed", **report.facts})
    verify_bundle(release.bundle_path, expected_sha256=release.bundle_sha256,
                  expected_bytes=release.bundle_bytes)
    print(f"packaged {release.bundle_path.name} "
          f"({release.bundle_bytes} bytes, sha256 {release.bundle_sha256})")

    outcome = _boot_check(dist, work / "boot-cache")
    print(f"boot check: {outcome['readiness'].upper()} "
          f"({outcome.get('source_error') or 'validated through the adapter'})")

    # The report is rewritten once the boot check has run, so the recorded
    # evidence covers the whole pipeline rather than stopping at packaging.
    stored = json.loads(release.report_path.read_text())
    stored["boot_check"] = outcome
    release.report_path.write_text(json.dumps(stored, indent=2) + "\n")

    if outcome["readiness"] != "ready":
        return 1
    if args.release_state and Path(args.release_state).is_file():
        state = json.loads(Path(args.release_state).read_text())
        record_ingested(args.release_state, version=version,
                        etag=state.get("etag"))
    return 0


# -- wiring ------------------------------------------------------------------

def _add_build_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--csv", required=True, help="source pp-complete.csv")
    parser.add_argument("--work", required=True, help="scratch directory")
    parser.add_argument("--coverage-to", required=True,
                        help="the source release's coverage end (YYYY-MM-DD)")
    parser.add_argument("--memory", default="4GB", help="DuckDB memory limit")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tools.ppd_snapshot",
                                     description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check-release", help="HEAD the source; download nothing")
    check.add_argument("--url", default=DEFAULT_URL)
    check.add_argument("--state", required=True)
    check.set_defaults(handler=_cmd_check_release)

    build = sub.add_parser("build", help="build the partitions")
    _add_build_arguments(build)
    build.add_argument("--dist")
    build.add_argument("--source-coverage-end")
    build.add_argument("--release-state")
    build.add_argument("--today")
    build.add_argument("--version")
    build.add_argument("--source-sha256")
    build.set_defaults(handler=_cmd_build)

    validate = sub.add_parser("validate", help="run the gates on a built snapshot")
    validate.add_argument("--snapshot", required=True)
    validate.add_argument("--coverage-to", required=True)
    validate.add_argument("--source-coverage-end")
    validate.add_argument("--release-state")
    validate.add_argument("--today")
    validate.add_argument("--rows", type=int)
    validate.set_defaults(handler=_cmd_validate)

    every = sub.add_parser("all", help="build, validate, package, verify, boot")
    _add_build_arguments(every)
    every.add_argument("--dist", required=True)
    every.add_argument("--source-coverage-end")
    every.add_argument("--release-state")
    every.add_argument("--today")
    every.add_argument("--version")
    every.add_argument("--source-sha256")
    every.set_defaults(handler=_cmd_all)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    return int(args.handler(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
