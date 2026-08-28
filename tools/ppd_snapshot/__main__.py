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
    promote_release,
    snapshot_version,
    verify_bundle,
)
from tools.ppd_snapshot.release_check import (
    DEFAULT_URL,
    ReleaseObservation,
    check_release,
    declared_coverage_end,
    describe,
    record_ingested,
)
from tools.ppd_snapshot.source_receipt import (
    SourceMismatch,
    download_with_receipt,
    load_receipt,
    verify_source,
    write_receipt,
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
        eligible_source_rows=built.eligible_source_rows,
    )


def _print_report(report) -> None:
    for gate in report.gates:
        mark = {"pass": "ok  ", "fail": "FAIL", "skipped": "skip"}[gate.status]
        line = f"  [{mark}] {gate.name}"
        print(line if not gate.detail else f"{line} -- {gate.detail}")


def _release_state(path: Optional[str]) -> dict:
    if not path or not Path(path).is_file():
        return {}
    try:
        state = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def _observed(state: dict) -> Optional[ReleaseObservation]:
    """The release as most recently observed, or nothing.

    Nothing is a refusal upstream, never a default: a build that cannot say
    which release is published now cannot claim the file it holds is that one.
    """
    if not state:
        return None
    return ReleaseObservation(
        etag=state.get("etag"), last_modified=state.get("last_modified"),
        content_length=state.get("content_length"))


def _expected_end(receipt) -> Optional[date]:
    """The coverage end the bound release implies. Not an argument.

    There is deliberately no override on `build`/`all`. `--coverage-to` is the
    operator's declaration and this is the evidence it is checked against, so a
    flag that sets the evidence too makes the check compare a claim with itself:
    a 28 July release was published as covering 31 July by setting both.

    It is derived from the RECEIPT rather than the release-state file because
    the receipt is the document bound to the bytes that were actually read.
    """
    return declared_coverage_end(receipt.last_modified)


# -- commands ----------------------------------------------------------------

def _cmd_check_release(args) -> int:
    check = check_release(args.url, args.state)
    print(describe(check))
    return 0


def _cmd_receipt(args) -> int:
    observation = _observed(_release_state(args.release_state))
    if observation is None:
        print("refusing: no release observation is recorded; run check-release "
              "first so the file can be bound to a release")
        return 2
    try:
        receipt = write_receipt(Path(args.csv), observation, Path(args.receipt),
                                expected_sha256=args.expected_sha256)
    except SourceMismatch as exc:
        print(f"refusing to write a receipt: {exc}")
        return 2
    print(f"receipt written for {receipt.file}: {receipt.bytes} bytes, "
          f"sha256 {receipt.sha256}, ETag {receipt.etag} "
          f"(evidence: {receipt.evidence})")
    return 0


def _cmd_download(args) -> int:
    """Stream a release and mint its receipt from the same response."""
    try:
        receipt = download_with_receipt(args.url, Path(args.dest),
                                        Path(args.receipt))
    except SourceMismatch as exc:
        print(f"download refused: {exc}")
        return 2
    print(f"downloaded {receipt.bytes} bytes to {args.dest}; receipt sha256 "
          f"{receipt.sha256} (evidence: {receipt.evidence})")
    return 0


def load_receipt_or_none(args):
    """Refuse unless the CSV, its receipt and the observed release agree.

    Every gate after this point checks the snapshot against itself, so an
    internally consistent snapshot of the wrong file passes all of them. This is
    the only check that looks at what was read.
    """
    try:
        receipt = load_receipt(args.source_receipt)
        verify_source(Path(args.csv), receipt,
                      _observed(_release_state(args.release_state)))
    except SourceMismatch as exc:
        print(f"refusing to build: {exc}")
        return None
    return receipt


def _cmd_build(args) -> int:
    # The same binding as `all`: this writes the artifact `validate` then
    # blesses, so it is not a way around the source check.
    receipt = load_receipt_or_none(args)
    if receipt is None:
        return 2
    if _expected_end(receipt) is None:
        print("refusing to build: the bound release carries no usable "
              "publication date, so its coverage end cannot be derived")
        return 2
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
    source_end = _iso(args.source_coverage_end)
    if source_end is not None:
        print("note: --source-coverage-end was supplied, so the coverage gate "
              "is comparing two operator-stated dates; build/all derive it from "
              "the bound release instead")
    else:
        source_end = declared_coverage_end(
            _release_state(args.release_state).get("last_modified"))
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
        eligible_source_rows=args.eligible_source_rows,
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

    receipt = load_receipt_or_none(args)
    if receipt is None:
        return 2
    source_end = _expected_end(receipt)
    if source_end is None:
        print("refusing to build: the bound release carries no usable "
              "publication date, so its coverage end cannot be derived")
        return 2
    print(f"the bound release implies a coverage end of {source_end}")
    print(f"source verified: {Path(args.csv).name} matches its receipt and the "
          f"observed release")

    built = _build(args)
    print(f"built {built.rows} row(s) into {built.parquet_files} partition(s) "
          f"at {built.snapshot_dir} ({built.eligible_source_rows} eligible "
          f"source row(s))")

    report = validate_snapshot(_declared(built), source_coverage_end=source_end,
                               today=_iso(args.today) or date.today())
    _print_report(report)
    if not report.passed:
        print("validation failed; nothing was packaged")
        return 1

    version = args.version or snapshot_version()
    state = _release_state(args.release_state)
    source = {"file": Path(args.csv).name, "sha256": receipt.sha256,
              "bytes": receipt.bytes, "digest_evidence": receipt.evidence}
    source.update({k: state.get(k) for k in
                   ("url", "etag", "last_modified", "content_length")})

    release = package_release(built, dist_dir=dist,
                              candidate_root=work / "candidates",
                              version=version, source=source,
                              facts={"gates": "passed", **report.facts})
    verify_bundle(release.bundle_path, expected_sha256=release.bundle_sha256,
                  expected_bytes=release.bundle_bytes)
    print(f"packaged {release.bundle_path.name} "
          f"({release.bundle_bytes} bytes, sha256 {release.bundle_sha256}) "
          f"into {release.candidate_dir.name}")

    # Booted from the CANDIDATE. Nothing reaches the dist root until this
    # passes, so a failed boot cannot leave a publishable release behind.
    outcome = _boot_check(release.candidate_dir, work / "boot-cache")
    print(f"boot check: {outcome['readiness'].upper()} "
          f"({outcome.get('source_error') or 'validated through the adapter'})")

    stored = json.loads(release.report_path.read_text())
    stored["boot_check"] = outcome
    release.report_path.write_text(json.dumps(stored, indent=2) + "\n")

    if outcome["readiness"] != "ready":
        print(f"not promoted; the candidate is left at "
              f"{release.candidate_dir} for diagnosis")
        return 1

    promoted = promote_release(release)
    print(f"promoted to {promoted.bundle_path.parent}")
    if state:
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
    build.add_argument("--release-state", required=True,
                       help="the observed-release state written by check-release")
    build.add_argument("--today")
    build.add_argument("--version")
    build.add_argument("--source-receipt", required=True,
                       help="the receipt binding the CSV to a release")
    build.set_defaults(handler=_cmd_build)

    receipt = sub.add_parser(
        "receipt", help="bind a local CSV to the observed release")
    receipt.add_argument("--csv", required=True)
    receipt.add_argument("--release-state", required=True)
    receipt.add_argument("--receipt", required=True)
    receipt.add_argument("--expected-sha256", required=True,
                         help="the digest recorded when this file was fetched")
    receipt.set_defaults(handler=_cmd_receipt)

    download = sub.add_parser(
        "download", help="stream a release and mint its receipt in one pass")
    download.add_argument("--url", default=DEFAULT_URL)
    download.add_argument("--dest", required=True)
    download.add_argument("--receipt", required=True)
    download.set_defaults(handler=_cmd_download)

    validate = sub.add_parser("validate", help="run the gates on a built snapshot")
    validate.add_argument("--snapshot", required=True)
    validate.add_argument("--coverage-to", required=True)
    validate.add_argument("--source-coverage-end")
    validate.add_argument("--release-state")
    validate.add_argument("--today")
    validate.add_argument("--rows", type=int)
    validate.add_argument("--eligible-source-rows", type=int)
    validate.set_defaults(handler=_cmd_validate)

    every = sub.add_parser("all", help="build, validate, package, verify, boot")
    _add_build_arguments(every)
    every.add_argument("--dist", required=True)
    every.add_argument("--release-state", required=True,
                       help="the observed-release state written by check-release")
    every.add_argument("--today")
    every.add_argument("--version")
    every.add_argument("--source-receipt", required=True,
                       help="the receipt binding the CSV to a release")
    every.set_defaults(handler=_cmd_all)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    return int(args.handler(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
