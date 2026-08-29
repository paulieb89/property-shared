"""Local rehearsal of the shadow-corpus Definition against a built artifact.

`docs/design/ppd-shadow-corpus.md` defines the Stage 1 corpus as request shapes
plus semantic assertions, deliberately carrying no artifact and no concrete
geographies. This module runs those shapes against one local artifact, through
the snapshot adapter only, and reports whether each Definition invariant held.

**It is not Stage 1.** There is no live arm, so it can satisfy neither the p95
criterion nor any divergence criterion, and its report is labelled accordingly.
What it can establish is that every case is well-formed, routes to the snapshot,
and produces the shape the Definition says it must.

Three rules shape the implementation:

* **Refuse the instance before materializing.** The instance names the artifact
  and supplies the geographies the Definition leaves as placeholders. Validating
  it after boot would burn ~534 MiB and the wall time first, and leave a cache
  directory nobody can account for. Schema and digest binding are both checked
  before `SnapshotRuntime` is constructed.

* **No live path.** Sockets are blocked with a self-check proving the block is
  armed, and every case asserts its provenance says `snapshot`. A rehearsal that
  silently fell back to live would look exactly like one that did not.

* **Aggregates only in the report.** Some invariants -- subset containment
  between two cases -- need transaction-id sets. Those sets are built in memory
  and discarded; the report carries booleans, counts and offending outcodes.
  No id, price, address or row ever reaches the report or a log line.
"""

from __future__ import annotations

import json
import re
import socket
from dataclasses import dataclass, field
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

#: Exactly these top-level keys. Unknown keys are refused rather than ignored:
#: a typo in an instance is a silently different rehearsal.
REQUIRED_KEYS = frozenset({
    "instance_kind", "snapshot_version", "bundle_sha256", "geographies",
    "aggregate_baselines",
})

#: Full-artifact counts that qualify the containment relations. A paged
#: rehearsal cannot re-derive these -- section 9 says containment is
#: established here, during instance qualification, not from a page -- so they
#: are declared, and checked for consistency with what they claim to establish.
REQUIRED_BASELINES = frozenset({"S1_full", "S3_full", "S9_full"})

#: The Definition's placeholders. Every one must be supplied; no others.
REQUIRED_GEOGRAPHIES = frozenset({
    "S4_thin", "S5_dense", "S6_unit", "S7_type_weak",
    "S8_type_strong", "S11_provisional_empty", "S13_empty_unit",
})

#: `rehearsal`, never `stage1`. The kind is in the file so a rehearsal instance
#: cannot be handed to a Stage 1 runner by accident.
INSTANCE_KIND = "rehearsal"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VERSION = re.compile(r"^v\d{8}T\d{6}Z$")
#: Outward code, optional sector digit, optional unit. Deliberately narrow: a
#: placeholder that is not a real geography is a corpus error, not a query that
#: happens to return nothing.
_GEOGRAPHY = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?( \d([A-Z]{2})?)?$")


class InstanceRefused(Exception):
    """The instance is malformed, incomplete, or bound to another artifact.

    Raised before anything is materialized. The CLI maps it to exit 2.
    """


@dataclass(frozen=True)
class RehearsalInstance:
    instance_kind: str
    snapshot_version: str
    bundle_sha256: str
    geographies: dict[str, str]
    aggregate_baselines: dict[str, int]


def _published_manifest(dist_dir: Path) -> dict[str, Any]:
    """Read the dist pointer and manifest. Metadata only -- nothing is opened."""
    current = dist_dir / "current.json"
    if not current.is_file():
        raise InstanceRefused(f"no current.json in {dist_dir}")
    try:
        pointer = json.loads(current.read_text())
        name = pointer["current_manifest"]
        return json.loads((dist_dir / name).read_text())
    except (OSError, ValueError, KeyError) as exc:
        raise InstanceRefused(f"unreadable dist pointer or manifest: {exc}") from exc


def load_instance(path: Path, dist_dir: Path) -> RehearsalInstance:
    """Validate the instance and bind it to the artifact at `dist_dir`.

    Structure first, then binding. Both complete before any materialization, so
    a refused instance costs a file read rather than half a gigabyte.
    """
    try:
        raw = json.loads(Path(path).read_text())
    except FileNotFoundError as exc:
        raise InstanceRefused(f"instance file not found: {path}") from exc
    except (OSError, ValueError) as exc:
        raise InstanceRefused(f"instance is not readable JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise InstanceRefused("instance must be a JSON object")

    keys = set(raw)
    if missing := REQUIRED_KEYS - keys:
        raise InstanceRefused(f"instance is missing required key(s): {sorted(missing)}")
    if unknown := keys - REQUIRED_KEYS:
        raise InstanceRefused(f"instance carries unknown key(s): {sorted(unknown)}")

    if raw["instance_kind"] != INSTANCE_KIND:
        raise InstanceRefused(
            f"instance_kind is {raw['instance_kind']!r}; this tool runs "
            f"{INSTANCE_KIND!r} instances only. A Stage 1 instance is not a "
            f"rehearsal and must not be run through it."
        )

    version, digest = raw["snapshot_version"], raw["bundle_sha256"]
    if not isinstance(version, str) or not _VERSION.match(version):
        raise InstanceRefused(f"snapshot_version is not a version string: {version!r}")
    if not isinstance(digest, str) or not _SHA256.match(digest):
        raise InstanceRefused("bundle_sha256 is not a 64-character hex digest")

    geographies = raw["geographies"]
    if not isinstance(geographies, dict):
        raise InstanceRefused("geographies must be a JSON object")
    supplied = set(geographies)
    if missing := REQUIRED_GEOGRAPHIES - supplied:
        raise InstanceRefused(
            f"the Definition's placeholder(s) {sorted(missing)} are unsupplied")
    if unknown := supplied - REQUIRED_GEOGRAPHIES:
        raise InstanceRefused(
            f"geographies carries unknown placeholder(s): {sorted(unknown)}")
    for key, value in sorted(geographies.items()):
        if not isinstance(value, str) or not _GEOGRAPHY.match(value.strip().upper()):
            raise InstanceRefused(
                f"{key} is {value!r}, which is not a postcode, sector or outcode")

    baselines = raw["aggregate_baselines"]
    if not isinstance(baselines, dict):
        raise InstanceRefused("aggregate_baselines must be a JSON object")
    supplied_b = set(baselines)
    if missing := REQUIRED_BASELINES - supplied_b:
        raise InstanceRefused(
            f"aggregate_baselines is missing {sorted(missing)}; these are the "
            f"qualification evidence for the containment relations")
    if unknown := supplied_b - REQUIRED_BASELINES:
        raise InstanceRefused(
            f"aggregate_baselines carries unknown key(s): {sorted(unknown)}")
    for key in sorted(REQUIRED_BASELINES):
        value = baselines[key]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise InstanceRefused(
                f"aggregate_baselines[{key}] is {value!r}, not a count")
    # The baselines exist to establish two relations. A set that contradicts
    # them qualifies nothing, and would be worse than absent: it would look
    # like evidence.
    if baselines["S3_full"] >= baselines["S1_full"]:
        raise InstanceRefused(
            f"aggregate_baselines say S3 holds {baselines['S3_full']} rows and "
            f"S1 holds {baselines['S1_full']}; S3 is one sector inside S1's "
            f"district, and the Definition requires a STRICT subset. Equal "
            f"counts would say the sector is the whole district, which "
            f"qualifies nothing.")
    if baselines["S9_full"] <= baselines["S3_full"]:
        raise InstanceRefused(
            f"aggregate_baselines say S9 ({baselines['S9_full']}) does not "
            f"exceed S3 ({baselines['S3_full']}); including category B cannot "
            f"return fewer rows than excluding it")

    # Binding: the instance must name the artifact it is about to be run
    # against. An instance that is internally valid but describes a different
    # snapshot would produce a report whose provenance is a fiction.
    manifest = _published_manifest(dist_dir)
    if manifest.get("snapshot_version") != version:
        raise InstanceRefused(
            f"instance names snapshot_version {version}, but {dist_dir} publishes "
            f"{manifest.get('snapshot_version')}"
        )
    if manifest.get("bundle_sha256") != digest:
        raise InstanceRefused(
            f"instance bundle_sha256 does not match the digest published in "
            f"{dist_dir}; the instance describes a different artifact"
        )

    return RehearsalInstance(
        instance_kind=raw["instance_kind"],
        snapshot_version=version,
        bundle_sha256=digest,
        geographies={k: v.strip().upper() for k, v in geographies.items()},
        aggregate_baselines=dict(baselines),
    )


# ---------------------------------------------------------------------------
# Socket blocker
# ---------------------------------------------------------------------------

class LivePathAttempted(RuntimeError):
    """Something tried to open a socket during a rehearsal."""


@dataclass
class SocketBlocker:
    """Hard-fail every socket for the duration, and prove it is armed.

    An unarmed blocker is worse than none: the run would look isolated while
    quietly reaching the network, and the report would claim a rehearsal that
    was partly a live query.
    """

    _original: Any = field(default=None, init=False)

    def arm(self) -> None:
        self._original = socket.socket

        def _refuse(*_args, **_kwargs):
            raise LivePathAttempted(
                "a rehearsal attempted to open a socket; no live path may be "
                "constructed during a rehearsal"
            )

        socket.socket = _refuse  # type: ignore[assignment]
        self.self_check()

    def self_check(self) -> None:
        """Prove the block actually fires, rather than assuming the patch took."""
        try:
            socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except LivePathAttempted:
            return
        raise RuntimeError(
            "socket blocker did not fire on its own self-check; refusing to "
            "run a rehearsal that cannot prove it is isolated"
        )

    def disarm(self) -> None:
        if self._original is not None:
            socket.socket = self._original  # type: ignore[assignment]
            self._original = None


# ---------------------------------------------------------------------------
# Case shapes -- the Definition's S1..S14
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Case:
    """One corpus shape, with the Definition's frozen parameters attached."""

    shape: str
    intent: str
    postcode: str
    search_level: str
    months: int = 24
    property_type: Optional[str] = None
    transaction_category: Optional[str] = "A"

    def request(self) -> dict[str, Any]:
        """The wire request, with omissions recorded as omissions.

        `property_type=None` and `address=None` are not values the HTTP surface
        can carry: omission is the only way to ask for the residential default.
        The record says so rather than implying a null was sent.
        """
        wire: dict[str, Any] = {
            "postcode": self.postcode,
            "search_level": self.search_level,
            "months": self.months,
            "limit": 50,
            "transaction_category": self.transaction_category or "all",
            "filter_outliers": False,
            "auto_escalate": True,
            "enrich_epc": False,
        }
        if self.property_type is None:
            wire["property_type"] = "<omitted>"
        else:
            wire["property_type"] = self.property_type
        wire["address"] = "<omitted>"
        return wire

    def effective(self) -> dict[str, Any]:
        return {
            "property_type": (self.property_type
                              or "residential_default (F/D/S/T)"),
            "address": None,
            "transaction_category": self.transaction_category,
        }


def cases(geo: dict[str, str]) -> list[Case]:
    """The Definition's thirteen shapes, with placeholders resolved."""
    return [
        Case("S1", "contamination boundary", "B5", "district"),
        Case("S2", "reverse boundary", "B50", "district"),
        Case("S3", "sector isolation", "B5 4", "sector"),
        Case("S4", "thin market", geo["S4_thin"], "sector"),
        Case("S5", "dense market and truncation", geo["S5_dense"], "sector"),
        Case("S6", "exact-postcode geography", geo["S6_unit"], "postcode"),
        Case("S7", "type filter barely bites", geo["S7_type_weak"], "sector",
             property_type="F"),
        Case("S8", "type filter genuinely bites", geo["S8_type_strong"], "sector",
             property_type="F"),
        Case("S9", "category filtering", "B5 4", "sector",
             transaction_category=None),
        # S10 removed: "provisional tail, non-empty" discriminates nothing now
        # that every comps case is provisional (Definition section 3).
        Case("S11", "provisional flag is a window property",
             geo["S11_provisional_empty"], "sector", months=6),
        Case("S12", "widest window, deepest history", "B5", "district", months=120),
        Case("S13", "expected empty", geo["S13_empty_unit"], "postcode",
             property_type="D"),
        Case("S14", "expected empty, sector shape", "B5 4", "sector",
             property_type="T"),
    ]


def derived_from_date(observed_at: date, months: int) -> str:
    """The window a harness must reconstruct; `comps` does not report it.

    Mirrors `PPDService.comps`. Pinned behaviourally in
    `tests/snapshot/test_shadow_corpus_definition.py`, because if this drifts,
    every window recorded by every observation is wrong.
    """
    return (observed_at - timedelta(days=months * 30)).isoformat()


# ---------------------------------------------------------------------------
# Running the rehearsal
# ---------------------------------------------------------------------------

def _outcodes(transactions: Any) -> list[str]:
    """Distinct outcodes in a result. Geography membership, never rows."""
    seen = set()
    for t in transactions:
        pc = (getattr(t, "postcode", None) or "").strip().upper()
        head = pc.partition(" ")[0]
        if head:
            seen.add(head)
    return sorted(seen)


def _sectors(transactions: Any) -> list[str]:
    seen = set()
    for t in transactions:
        pc = (getattr(t, "postcode", None) or "").strip().upper()
        head, _, tail = pc.partition(" ")
        if head and tail:
            seen.add(f"{head} {tail[0]}")
    return sorted(seen)


def _ids(transactions: Any) -> set[str]:
    """In-memory only. Used for containment; never returned or written."""
    return {t.transaction_id for t in transactions if getattr(t, "transaction_id", None)}


class MidnightCrossing(RuntimeError):
    """An observation could not be taken within a single calendar date.

    Carries the attempts already made: they are the evidence that the guard
    tried, and are lost if only the message survives.
    """

    def __init__(self, message: str, *, retries: int = 0) -> None:
        super().__init__(message)
        self.retries = retries


def _observe(service: Any, case: Case, *,
             attempts: int = 3) -> tuple[Any, str, int, float]:
    """One case, guaranteed inside a single calendar date.

    `comps` derives its window from `date.today()`, so an observation that
    straddles midnight silently describes a different window than the one
    recorded. Retry that case; if a same-date observation cannot be obtained,
    fail the rehearsal rather than keep an observation whose window is unknown.
    """
    retries = 0
    for _ in range(attempts):
        before = date.today()
        started = time.monotonic()
        response = service.comps(
            postcode=case.postcode,
            search_level=case.search_level,
            months=case.months,
            property_type=case.property_type,
            transaction_category=case.transaction_category,
            filter_outliers=False,
            limit=50,
            auto_escalate=True,
        )
        elapsed_ms = (time.monotonic() - started) * 1000.0
        after = date.today()
        if before == after:
            return response, before.isoformat(), retries, elapsed_ms
        retries += 1
    raise MidnightCrossing(
        f"{case.shape}: the midnight guard could not obtain a same-date "
        f"observation in {attempts} attempts. `comps` derives its window from "
        f"date.today(), so the window recorded for this case would not describe "
        f"the query that was actually run.",
        retries=retries,
    )


def _warning_classes(warnings: tuple[str, ...]) -> list[str]:
    """The Definition's classes, matched by their published predicates."""
    found = []
    for w in warnings:
        if "beyond snapshot coverage" in w and "are not included" in w:
            found.append("coverage_clamp")
        if "narrowed to" in w and "coverage" in w:
            found.append("coverage_floor_narrowing")
        if "days behind its coverage end" in w:
            found.append("freshness")
        if w.startswith("auto-escalation not applied:"):
            found.append("escalation_containment")
        if "the upstream window was not exhausted" in w:
            found.append("live_incompleteness")
        if "removed by geography containment" in w:
            found.append("geography_containment")
    return sorted(set(found))


def run_rehearsal(*, instance: RehearsalInstance, dist_dir: Path,
                  cache_dir: Path, report_path: Path) -> dict[str, Any]:
    """Materialize, run every case adapter-only, and write an aggregate report.

    The instance is already validated and bound when this is called: nothing
    here re-checks it, and nothing before this point materializes anything.
    """
    import os

    blocker = SocketBlocker()
    blocker.arm()

    # A rehearsal is a guest in whatever process runs it. Capture what was
    # there -- including "not set", which is different from "set to empty" --
    # so the caller's process is unchanged afterwards.
    managed = ("PPD_SNAPSHOT_ENABLED", "PPD_SNAPSHOT_DIR", "PPD_SNAPSHOT_CACHE_DIR")
    prior_env = {k: os.environ.get(k) for k in managed}

    os.environ["PPD_SNAPSHOT_ENABLED"] = "1"
    os.environ["PPD_SNAPSHOT_DIR"] = str(dist_dir)
    os.environ["PPD_SNAPSHOT_CACHE_DIR"] = str(cache_dir)

    from property_core.ppd_service import PPDService
    from property_core.snapshot import state
    from property_core.snapshot.adapter import SnapshotAdapter
    from property_core.snapshot.runtime import SnapshotRuntime
    from property_core.snapshot.source import LocalDirectorySource
    from property_core.snapshot.store import SnapshotStore

    prior_adapter = state.installed_adapter()
    prior_report = state.boot_report()

    failure: Optional[str] = None
    results: list[dict[str, Any]] = []
    id_sets: dict[str, set[str]] = {}
    counts: dict[str, int] = {}
    midnight = {"exclusions": 0, "retries": 0, "unrecoverable": False}
    adapter = None
    try:
        store = SnapshotStore(cache_dir)
        runtime = SnapshotRuntime(source=LocalDirectorySource(dist_dir), store=store)
        boot = runtime.boot()
        if not boot.ready or not boot.snapshot_dir:
            raise RuntimeError(f"snapshot did not boot READY: {boot}")

        adapter = SnapshotAdapter.open(Path(boot.snapshot_dir), store.verified_record(
            boot.version) if hasattr(store, "verified_record") else boot.record)
        state.install(adapter, boot)

        service = PPDService()
        for case in cases(instance.geographies):
            response, observed, retries, latency_ms = _observe(service, case)
            midnight["retries"] += retries
            midnight["exclusions"] += retries
            provenance = response.provenance
            warnings = tuple(response.warnings or ())
            classes = _warning_classes(warnings)
            id_sets[case.shape] = _ids(response.transactions)
            counts[case.shape] = response.count
            dates = sorted(t.date for t in response.transactions if getattr(t, "date", None))

            results.append({
                "shape": case.shape,
                "intent": case.intent,
                "request": {"wire": case.request(), "effective": case.effective()},
                "observed_at_before": observed,
                "observed_at_after": observed,
                "derived_from_date": derived_from_date(
                    date.fromisoformat(observed), case.months),
                "resolved_to_date": provenance.coverage_to if provenance else None,
                "count": response.count,
                "latency_ms": round(latency_ms, 2),
                "returned_date_from": dates[0] if dates else None,
                "returned_date_to": dates[-1] if dates else None,
                "thin_market": response.thin_market,
                "outcodes_returned": _outcodes(response.transactions),
                "sectors_returned": _sectors(response.transactions),
                "warning_classes": classes,
                "provenance": {
                    "source": (provenance.source.value
                               if provenance and hasattr(provenance.source, "value")
                               else str(provenance.source) if provenance else None),
                    "coverage_from": provenance.coverage_from if provenance else None,
                    "coverage_to": provenance.coverage_to if provenance else None,
                    "recent_period_provisional": (
                        provenance.recent_period_provisional if provenance else None),
                    "sample_count": provenance.sample_count if provenance else None,
                    "sample_limit": provenance.sample_limit if provenance else None,
                    "sample_complete": provenance.sample_complete if provenance else None,
                    "completeness_basis": (
                        str(provenance.completeness_basis)
                        if provenance and provenance.completeness_basis else None),
                },
                "invariants": _invariants(case, response, provenance, classes),
                "not_evaluable": {},
            })
    except MidnightCrossing as exc:
        # Recorded, not raised past the report. The Definition says an
        # unrecoverable crossing fails the run clearly; a traceback with no
        # report is not clearly, and leaves nothing to review afterwards.
        midnight["unrecoverable"] = True
        midnight["retries"] += getattr(exc, "retries", 0)
        midnight["exclusions"] += getattr(exc, "retries", 0)
        failure = str(exc)
    finally:
        # Close OUR adapter, then hand back whatever the caller had installed.
        # `state.clear()` would close the caller's adapter too, which is not
        # ours to close.
        if adapter is not None:
            close = getattr(adapter, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # noqa: BLE001
                    pass
        if prior_adapter is None:
            state.install(None, None)
        else:
            state.install(prior_adapter, prior_report)

        blocker.disarm()
        for key, value in prior_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    if failure is None:
        _cross_case_invariants(results, id_sets, counts)
    id_sets.clear()

    # An assertion is passed, failed, or not evaluable. `not_evaluable` is
    # counted on its own and never as a pass: a saturated comparison is an
    # unanswerable question, not a satisfied one.
    a_passed = sum(1 for r in results for v in r["invariants"].values() if v is True)
    a_failed = sum(1 for r in results for v in r["invariants"].values() if v is False)
    a_uneval = sum(len(r["not_evaluable"]) for r in results)
    passed = sum(1 for r in results
                 if all(v is True for v in r["invariants"].values()))
    report = {
        "kind": "rehearsal",
        "not_stage_1_evidence": True,
        "disclaimer": (
            "A rehearsal has no live arm, so it can satisfy neither the p95 "
            "criterion nor any divergence criterion of Stage 1. This report is "
            "a correctness exercise and must never be filed as Stage 1 evidence."
        ),
        "definition": "docs/design/ppd-shadow-corpus.md",
        "artifact": {
            "snapshot_version": instance.snapshot_version,
            "bundle_sha256": instance.bundle_sha256,
            "dist_dir": str(dist_dir),
        },
        "isolation": {
            "socket_blocker_armed": True,
            "self_check_passed": True,
            "live_adapter_constructed": False,
        },
        "midnight": midnight,
        "failure": failure,
        "qualification": {
            "source": "declared in the instance, not measured by this rehearsal",
            "baselines": dict(instance.aggregate_baselines),
            "note": (
                "Containment between cases is qualified from these full "
                "aggregate counts. A paged rehearsal cannot re-derive them, so "
                "it records them rather than claiming to have measured them."
            ),
        },
        "cases_total": len(results),
        "cases_passed": passed,
        "assertions_total": a_passed + a_failed + a_uneval,
        "assertions_passed": a_passed,
        "assertions_failed": a_failed,
        "assertions_not_evaluable": a_uneval,
        # A run may exit 0 with not_evaluable assertions present; it may never
        # exit 0 with a failed one.
        "passed": (a_failed == 0 and not midnight["unrecoverable"]
                   and failure is None),
        "cases": results,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=False))
    return report


def _invariants(case: Case, response: Any, provenance: Any,
                classes: list[str]) -> dict[str, bool]:
    """The Definition's per-case assertions. Booleans only."""
    inv: dict[str, bool] = {
        # Universal (Definition section 3): comps never sends to_date.
        "coverage_clamp_warning_present": "coverage_clamp" in classes,
        "sample_complete_is_false": bool(
            provenance is not None and provenance.sample_complete is False),
        "completeness_basis_is_null": bool(
            provenance is not None and provenance.completeness_basis is None),
        "answered_by_snapshot": bool(
            provenance is not None and "snapshot" in str(provenance.source).lower()),
        # Universal, not per-shape: the resolved upper bound is always
        # `coverage_to` and `provisional_from` never exceeds it, so every comps
        # window intersects the provisional period (Definition section 3).
        "provisional_flagged": bool(
            provenance is not None and provenance.recent_period_provisional is True),
    }

    outcodes = _outcodes(response.transactions)
    requested_outcode = case.postcode.split()[0].upper()
    if case.search_level in {"district", "sector", "postcode"}:
        inv["geography_isolation"] = all(o == requested_outcode for o in outcodes)

    if case.shape in {"S5", "S12"}:
        inv["truncated_at_limit"] = response.count == 50
    if case.shape == "S4":
        inv["thin_market_flagged"] = response.thin_market is True
    if case.shape == "S11":
        inv["empty_result"] = response.count == 0
    if case.shape in {"S13", "S14"}:
        inv["expected_empty"] = response.count == 0
    return inv


#: The page size every case is frozen at. A result of exactly this length was
#: truncated, and a truncated page cannot answer a containment question.
LIMIT = 50

_SATURATED = (
    "not evaluable: {a} returned {na} rows and {b} returned {nb}, and a page "
    "saturated at limit={limit} is not a subset of a wider page ordered "
    "most-recent-first. Containment is established from full aggregate counts "
    "during instance qualification, not from a page."
)


def _cross_case_invariants(results: list[dict[str, Any]],
                           id_sets: dict[str, set[str]],
                           counts: dict[str, int]) -> None:
    """Containment between cases, from id sets held only in memory.

    The sets never reach the report: the outcome is a boolean, a count, or a
    `not_evaluable` reason. Where either side is saturated the question is
    unanswerable on pages, and saying so is more honest than reporting a
    failure the artifact did not cause.
    """
    by_shape = {r["shape"]: r for r in results}

    def _compare(name: str, subject: str, a: str, b: str) -> None:
        if a not in id_sets or b not in id_sets:
            return
        if counts.get(a) == LIMIT or counts.get(b) == LIMIT:
            by_shape[subject]["not_evaluable"][name] = _SATURATED.format(
                a=a, na=counts.get(a), b=b, nb=counts.get(b), limit=LIMIT)
            return
        by_shape[subject]["invariants"][name] = id_sets[a] <= id_sets[b]

    _compare("subset_of_S1", "S3", "S3", "S1")
    _compare("category_all_is_superset_of_default", "S9", "S3", "S9")

    # Geography containment survives truncation: however a page was cut, every
    # row S3 returns must lie inside the outcode S1 asked for. This is the
    # containment check that stays meaningful when the set comparison cannot.
    if "S3" in by_shape and "S1" in by_shape:
        s1_outcode = by_shape["S1"]["request"]["wire"]["postcode"].split()[0].upper()
        by_shape["S3"]["invariants"]["within_S1_geography"] = all(
            o == s1_outcode for o in by_shape["S3"]["outcodes_returned"])

    id_sets.clear()
