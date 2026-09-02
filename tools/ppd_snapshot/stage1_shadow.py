"""Stage 1 production shadow comparison, run out of band on the Machine.

    fly ssh console -a property-shared
    cd /app
    PPD_SHADOW_COMPARE_ENABLED=1 python -m tools.ppd_snapshot.stage1_shadow \\
        qualify --out /tmp/stage1-candidate-instance.json
    PPD_SHADOW_COMPARE_ENABLED=1 python -m tools.ppd_snapshot.stage1_shadow \\
        compare --instance /tmp/stage1-instance.json --report /tmp/stage1.json

Two modes, in the order the runbook uses them.

* **`qualify`** -- read-only, snapshot-only. Runs the full aggregate COUNT
  queries the frozen Definition needs, selects the seven placeholder
  geographies against their published qualification rules, and emits a
  *candidate* Instance bound to the artifact's version and full bundle digest.
  It makes no live call, downloads nothing, and writes nothing into the
  snapshot. Its output is reviewed and committed as its own change; nothing
  artifact-specific is ever hard-coded here.

* **`compare`** -- the Stage 1 run. Executes the thirteen frozen cases against
  **both** the existing live source and the already-materialized snapshot,
  then repeats the snapshot arm alone for the latency sample.

**Why out of band rather than in the request path.** Stage 1 needs evidence, not
a permanent feature. A sampling hook inside the serving application would mean a
queue, a worker thread, sampling configuration and a telemetry stream living in
the request path of a live service, outliving the gate they were built for. As a
separate process this tool is in no request path at all, so *"shadow comparison
never makes a live request fail"* holds by construction rather than by careful
coding. The governing specification's rev 10 records that decision and the
matching p95 revision.

**Isolation from the running server.** This module never installs into
`property_core.snapshot.state`, never sets or reads `PPD_SNAPSHOT_ENABLED`,
never downloads an artifact and never writes inside the snapshot directory. It
opens **its own** adapter over the parquet files the server already
materialized; `SnapshotAdapter` connects to an in-memory DuckDB and reads
Parquet, so there is no database file to lock and no contention with the
process that is serving.

**What is persisted.** Counts, month histograms, field-mismatch tallies,
geography results, warning classes, source evidence, latency, classification and
artifact identity. Transaction ids and the values of compared fields exist in
memory for the length of one comparison and are then discarded: **no id, no
address, no price and no row ever reaches a report.**
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Optional

from tools.ppd_snapshot.corpus import (
    DEFINITIONAL_GEOGRAPHIES,
    LIMIT,
    REQUIRED_GEOGRAPHIES,
    Case,
    InstanceRefused,
    cases,
    derived_from_date,
    geography_violations,
    ids as _ids,
    is_contaminated,
    outcodes as _outcodes,
    returned_date_bounds,
    snapshot_invariants,
    sectors as _sectors,
    validate_artifact_identity,
    validate_baselines,
    validate_geographies,
    validate_substitutions,
    warning_classes as _warning_classes,
)

#: Bound to every observation. A report whose numbers cannot be attributed to a
#: known comparator is not evidence -- two runs of "the comparator" could have
#: measured different things.
COMPARATOR_VERSION = "1"

#: Default off, and separately controlled. The tool refuses to open an adapter,
#: issue a query or write a report unless this parses true. Passed inline for
#: one invocation rather than set as a Fly secret: setting a secret restarts the
#: Machine, which wipes the ephemeral rootfs and destroys the very materialized
#: snapshot the run is about.
SHADOW_COMPARE_ENABLED_ENV = "PPD_SHADOW_COMPARE_ENABLED"

#: The comps fields compared on shared transaction ids. `raw` is excluded: it is
#: the live SPARQL binding dict and has no snapshot counterpart by construction,
#: so comparing it would report a difference on every row. The EPC fields are
#: excluded because the corpus freezes `enrich_epc=false`, so they are null on
#: both sides and would pad the tally with meaningless agreement.
COMPARED_FIELDS: tuple[str, ...] = (
    "transaction_id", "price", "date", "postcode", "property_type",
    "estate_type", "transaction_category", "new_build", "paon", "saon",
    "street", "town", "county", "locality", "district",
)

#: A unit postcode is only selectable as a corpus geography when it is
#: aggregate-dense; the Definition requires S6 to be "aggregate-dense, so not
#: individually identifying". Made executable here so qualification cannot pick
#: a postcode that names one household's sale history.
MIN_UNIT_POSTCODE_ROWS = 10

#: Definition section 2: comps' thin-market threshold under frozen parameters.
THIN_MARKET_THRESHOLD = 5

#: The residential default the corpus selects by omitting `property_type`.
RESIDENTIAL_TYPES = ("F", "D", "S", "T")

#: The frozen corpus is thirteen cases. A report covering fewer is not a
#: smaller Stage 1 result; it is not a Stage 1 result.
REQUIRED_CASES = 13

#: The latency sample the gate is defined over: every case repeated this many
#: times. Fixed rather than taken from the CLI, so a run cannot lower the bar
#: it is measured against by passing a smaller number.
REQUIRED_LATENCY_REPEATS = 30
REQUIRED_LATENCY_OBSERVATIONS = REQUIRED_CASES * REQUIRED_LATENCY_REPEATS

#: The literal reading of the Definition's S1 rule: "the longer neighbouring
#: outcode holds **comparable or greater** volume".
#:
#: An earlier version of this tool operationalised that as "at least 10% of the
#: district's rows" and auto-qualified on it. That was wrong: a tenth is not
#: comparable, and quietly redefining a frozen qualification rule downwards is
#: exactly the kind of change that must not happen inside an implementation.
#: The threshold here is the one the words say. Anything below it is **not
#: refused and not passed** -- it is referred to the owner, with the measurement
#: attached, because "is 0.6 comparable for this artifact?" is a judgement about
#: the corpus, and the Definition already provides the two ways to settle it:
#: accept it, or substitute a geography with recorded justification.
NEIGHBOUR_COMPARABLE_RATIO = 1.0

#: The placeholder `qualify` writes into a candidate Instance. An Instance still
#: carrying it has not been through the review the field exists to record.
GOVERNS_RUN_PLACEHOLDER = "<fill in: the Stage 1 run this Instance governs>"


class ComparisonRefused(RuntimeError):
    """A precondition failed before anything was opened, queried or written.

    Raised before the adapter exists. The CLI maps it to exit 2, distinct from
    a run that executed and found problems (exit 1).
    """


class RunAborted(RuntimeError):
    """A health, resource or divergence anomaly stopped the run mid-flight.

    The partial report is still written: a run that stopped for a reason is
    evidence about that reason, and a traceback with no report leaves nothing
    to review.
    """


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def require_enabled(env: Optional[dict[str, str]] = None) -> None:
    """Refuse unless the comparison is explicitly enabled. Fails CLOSED.

    Uses `property_core`'s single flag parser, so an operator typo means "off"
    here exactly as it does for every other snapshot flag, rather than being
    truthy because it is a non-empty string.
    """
    from property_core.config import parse_bool_flag

    source = os.environ if env is None else env
    if not parse_bool_flag(source.get(SHADOW_COMPARE_ENABLED_ENV)):
        raise ComparisonRefused(
            f"{SHADOW_COMPARE_ENABLED_ENV} is not set to a true value; shadow "
            f"comparison is off by default and must be enabled deliberately for "
            f"the invocation that runs it"
        )


@dataclass(frozen=True)
class Materialized:
    """The snapshot this Machine already holds, opened read-only."""

    adapter: Any
    version: str
    bundle_sha256: str
    coverage_from: Optional[str]
    coverage_to: Optional[str]
    provisional_from: Optional[str]
    directory: Path

    def identity(self) -> dict[str, Any]:
        """Artifact identity and coverage, attached to every result."""
        return {
            "snapshot_version": self.version,
            "bundle_sha256": self.bundle_sha256,
            "coverage_from": self.coverage_from,
            "coverage_to": self.coverage_to,
            "provisional_from": self.provisional_from,
            "comparator_version": COMPARATOR_VERSION,
        }


def open_materialized(cache_dir: Path) -> Materialized:
    """Open the snapshot the server already materialized. Never create one.

    **Refuses rather than materializing.** Every directory this reads must
    already exist: the tool's whole premise is that it observes what the
    deployed application booted, and a tool that would happily build its own
    snapshot could silently measure a different artifact from the one serving.
    The existence checks come first so that constructing `SnapshotStore` --
    which creates its directories -- is provably a no-op rather than a write.
    """
    from property_core.snapshot.adapter import SnapshotAdapter
    from property_core.snapshot.store import SnapshotStore

    cache_dir = Path(cache_dir)
    if not (cache_dir / "snapshots").is_dir() or not (cache_dir / "CURRENT").is_file():
        raise ComparisonRefused(
            f"{cache_dir} holds no materialized snapshot (no CURRENT pointer and "
            f"snapshots/ directory); this tool observes what the application "
            f"booted and never materializes one of its own"
        )

    store = SnapshotStore(cache_dir)
    version = store.current_version()
    if not version:
        raise ComparisonRefused(f"{cache_dir}/CURRENT names no version")
    record = store.verified_record(version)
    if record is None:
        raise ComparisonRefused(
            f"snapshot {version} has no readable verification record; its "
            f"artifact identity cannot be established, so nothing measured "
            f"against it could be attributed")

    directory = store.snapshots_dir / version
    adapter = SnapshotAdapter.open(directory, record)
    return Materialized(
        adapter=adapter,
        version=record.version,
        bundle_sha256=record.bundle_sha256,
        coverage_from=record.coverage_from,
        coverage_to=record.coverage_to,
        provisional_from=record.provisional_from,
        directory=directory,
    )


# ---------------------------------------------------------------------------
# The Stage 1 Instance
# ---------------------------------------------------------------------------

INSTANCE_KIND = "stage1"

#: Definition section 10. A Stage 1 Instance is a superset of a rehearsal one:
#: it additionally records when it was qualified, the rule each geography
#: satisfied, any substitution and its justification, its staleness bound, and
#: the run it governs.
REQUIRED_INSTANCE_KEYS = frozenset({
    "instance_kind", "snapshot_version", "bundle_sha256", "geographies",
    "aggregate_baselines", "qualified_at", "qualification", "staleness_bound_days",
    "governs_run",
})

#: Optional, and absent in the normal case: the Definition's substitution route
#: for the section 4 geographies.
OPTIONAL_INSTANCE_KEYS = frozenset({"substitutions"})

#: Every case whose geography an Instance fixes must say how it qualified --
#: the seven placeholders plus the two definitional cases. A block covering
#: some of them is silent about the rest while looking complete.
REQUIRED_QUALIFICATION_KEYS = frozenset(
    REQUIRED_GEOGRAPHIES | {"S1_district", "S2_district", "S3_sector"})

#: Qualification entries that must name the geography they were measured over,
#: and be checked against the Instance's EFFECTIVE geographies. These three fix
#: the definitional cases and the S1/S3/S9 baselines, so a substitution that
#: left them describing `B5`/`B50`/`B5 4` would be evidence about one set of
#: geographies attached to a run executing another.
GEOGRAPHY_BOUND_QUALIFICATIONS = {
    "S1_district": "S1_district",
    "S2_district": "S2_neighbour_district",
    "S3_sector": "S3_sector",
}


@dataclass(frozen=True)
class Stage1Instance:
    instance_kind: str
    snapshot_version: str
    bundle_sha256: str
    geographies: dict[str, str]
    aggregate_baselines: dict[str, int]
    qualified_at: str
    qualification: dict[str, Any]
    staleness_bound_days: int
    governs_run: str
    #: Empty in the normal case. The Definition's section 4 substitution route.
    substitutions: dict[str, str]


def _required_number(entry: dict[str, Any], key: str, where: str) -> float:
    value = entry.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InstanceRefused(
            f"qualification[{where}].{key} is {value!r}, not a number; the "
            f"baselines cannot be checked against a measurement that is not "
            f"recorded")
    return value


def _cross_check_measurements(qualification: dict[str, Any],
                              baselines: dict[str, int],
                              effective: dict[str, str]) -> None:
    """Every recorded definitional measurement and derived field must agree.

    Checked against the aggregate baselines and the effective geographies, so
    the three sets of numbers in an Instance cannot disagree with each other.
    Each mismatch below has the same shape: a document that looks internally
    complete while one figure came from somewhere the run will not go.
    """
    s1_entry = qualification["S1_district"]
    s2_entry = qualification["S2_district"]
    s3_entry = qualification["S3_sector"]

    s1_rows = _required_number(s1_entry, "measured_rows", "S1_district")
    if s1_rows != baselines["S1_full"]:
        raise InstanceRefused(
            f"qualification[S1_district].measured_rows is {s1_rows}, but "
            f"aggregate_baselines.S1_full is {baselines['S1_full']}; the same "
            f"count over the same geography cannot be two numbers")

    s3_rows = _required_number(s3_entry, "measured_rows", "S3_sector")
    if s3_rows != baselines["S3_full"]:
        raise InstanceRefused(
            f"qualification[S3_sector].measured_rows is {s3_rows}, but "
            f"aggregate_baselines.S3_full is {baselines['S3_full']}")
    s9_rows = _required_number(s3_entry, "measured_rows_category_all", "S3_sector")
    if s9_rows != baselines["S9_full"]:
        raise InstanceRefused(
            f"qualification[S3_sector].measured_rows_category_all is {s9_rows}, "
            f"but aggregate_baselines.S9_full is {baselines['S9_full']}")

    # The neighbour count appears twice -- once as S2's own measurement, once
    # as the input to S1's ratio. They are the same query.
    s2_rows = _required_number(s2_entry, "measured_rows", "S2_district")
    neighbour_rows = _required_number(
        s1_entry, "measured_neighbour_rows", "S1_district")
    if s2_rows != neighbour_rows:
        raise InstanceRefused(
            f"qualification[S2_district].measured_rows is {s2_rows} but "
            f"qualification[S1_district].measured_neighbour_rows is "
            f"{neighbour_rows}; they are the same count over the same "
            f"geography")

    neighbour_geography = str(s1_entry.get("neighbour_geography", "")).strip().upper()
    if neighbour_geography != effective["S2_neighbour_district"]:
        raise InstanceRefused(
            f"qualification[S1_district].neighbour_geography is "
            f"{neighbour_geography!r}, but this Instance's neighbour is "
            f"{effective['S2_neighbour_district']!r}; the ratio would describe "
            f"a district the run does not use")

    # Derived, so recomputed rather than trusted. A ratio edited to clear the
    # literal rule while the counts stayed put is exactly what this catches.
    #
    # Two ratios, deliberately. The EXACT one decides comparability; the
    # rounded one exists only to validate the four-decimal field the candidate
    # records for a human to read. Deciding from the rounded value puts a
    # rounding boundary inside a deployment gate: 20,000 rows against 20,001 is
    # 0.99995, which is not "comparable or greater" -- and rounds to 1.0. The
    # gate would then disagree with `qualify`, refusing a candidate that
    # correctly said `false` and accepting a hand-edited `true` that skips the
    # owner decision entirely.
    exact_ratio = (neighbour_rows / s1_rows) if s1_rows else 0.0
    expected_display_ratio = round(exact_ratio, 4)
    recorded_ratio = round(
        _required_number(s1_entry, "measured_neighbour_ratio", "S1_district"), 4)
    if recorded_ratio != expected_display_ratio:
        raise InstanceRefused(
            f"qualification[S1_district].measured_neighbour_ratio is "
            f"{recorded_ratio}, but {neighbour_rows} / {s1_rows} is "
            f"{expected_display_ratio}; a derived field must follow from the "
            f"counts recorded beside it")

    expected_comparable = bool(s1_rows > 0
                               and exact_ratio >= NEIGHBOUR_COMPARABLE_RATIO)
    if s1_entry.get("comparable_or_greater") is not expected_comparable:
        raise InstanceRefused(
            f"qualification[S1_district].comparable_or_greater is "
            f"{s1_entry.get('comparable_or_greater')!r}, but a ratio of "
            f"{exact_ratio!r} against the literal rule "
            f"({NEIGHBOUR_COMPARABLE_RATIO}) gives {expected_comparable}. This "
            f"field decides whether an owner decision is required, so it may "
            f"not be asserted independently of the measurement")

    inside = s3_entry.get("inside_s1_district")
    expected_inside = effective["S3_sector"].split()[0] == effective["S1_district"]
    if inside is not expected_inside:
        raise InstanceRefused(
            f"qualification[S3_sector].inside_s1_district is {inside!r}, but "
            f"{effective['S3_sector']!r} inside {effective['S1_district']!r} is "
            f"{expected_inside}")


def load_instance(path: Path, materialized: Materialized) -> Stage1Instance:
    """Validate the Instance and bind it to the artifact actually on this Machine.

    Structure first, then binding. A `rehearsal` instance is refused by kind, so
    a correctness exercise cannot be run through the Stage 1 path and filed as
    Stage 1 evidence -- which is the one substitution the Definition names.
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
    if missing := REQUIRED_INSTANCE_KEYS - keys:
        raise InstanceRefused(f"instance is missing required key(s): {sorted(missing)}")
    if unknown := keys - REQUIRED_INSTANCE_KEYS - OPTIONAL_INSTANCE_KEYS:
        raise InstanceRefused(f"instance carries unknown key(s): {sorted(unknown)}")

    if raw["instance_kind"] != INSTANCE_KIND:
        raise InstanceRefused(
            f"instance_kind is {raw['instance_kind']!r}; this tool runs "
            f"{INSTANCE_KIND!r} instances only. A rehearsal instance is a "
            f"correctness exercise and must not be run as Stage 1."
        )

    version, digest = validate_artifact_identity(
        raw["snapshot_version"], raw["bundle_sha256"])
    geographies = validate_geographies(raw["geographies"])
    baselines = validate_baselines(raw["aggregate_baselines"])
    substitutions = validate_substitutions(raw.get("substitutions"))

    bound = raw["staleness_bound_days"]
    if isinstance(bound, bool) or not isinstance(bound, int) or bound <= 0:
        raise InstanceRefused(
            f"staleness_bound_days is {bound!r}, not a positive number of days")

    # The bound is enforced, not merely recorded. An Instance carries measured
    # aggregate counts and selected geographies; the artifact is fixed, but the
    # frozen window moves forward every day, so counts qualified months ago
    # describe a query nobody now runs. Validating the field and never checking
    # it against the calendar would let a stale Instance qualify a Stage 1 run
    # while looking entirely well-formed.
    raw_qualified_at = raw["qualified_at"]
    # The round-trip is the load-bearing check, and it is the same rule
    # `validate_date_range` applies on the routing path. `fromisoformat` already
    # rejects a non-string, but it ACCEPTS spellings that are not the one the
    # Instance claims to carry: "20260901" parses, and so does the ISO week date
    # "2026-W36-2", which resolves silently to a real and quite different-looking
    # day. Requiring the value to round-trip is what keeps one spelling in the
    # field an operator reads.
    try:
        qualified_on = date.fromisoformat(raw_qualified_at)
        if qualified_on.isoformat() != raw_qualified_at:
            raise ValueError("not canonical")
    except (TypeError, ValueError) as exc:
        raise InstanceRefused(
            f"qualified_at {raw_qualified_at!r} is not a canonical ISO date "
            f"(YYYY-MM-DD); an Instance whose age cannot be established cannot "
            f"be checked against its own staleness bound") from exc
    age_days = (date.today() - qualified_on).days
    if age_days < 0:
        raise InstanceRefused(
            f"qualified_at {qualified_on.isoformat()} is in the future; the "
            f"Instance cannot have been qualified against this artifact yet")
    if age_days > bound:
        raise InstanceRefused(
            f"the Instance was qualified {age_days} days ago, beyond its own "
            f"staleness_bound_days of {bound}. Its aggregate counts and selected "
            f"geographies were measured over a window that has since moved; "
            f"re-run qualify against the artifact rather than reusing them")
    qualification = raw["qualification"]
    if not isinstance(qualification, dict):
        raise InstanceRefused("qualification must be a JSON object")
    supplied = set(qualification)
    if missing := REQUIRED_QUALIFICATION_KEYS - supplied:
        raise InstanceRefused(
            f"qualification is missing {sorted(missing)}; an Instance must "
            f"record, for EVERY case whose geography it fixes, the rule that "
            f"geography satisfied. A partial block says some cases qualified "
            f"and is silent about the rest, which qualifies nothing")
    if unknown := supplied - REQUIRED_QUALIFICATION_KEYS:
        raise InstanceRefused(
            f"qualification carries unknown key(s): {sorted(unknown)}; a typo "
            f"here would leave the case it was meant to qualify unqualified "
            f"while the block looked complete")
    for key in sorted(REQUIRED_QUALIFICATION_KEYS):
        entry = qualification[key]
        if not isinstance(entry, dict) or not str(entry.get("rule", "")).strip():
            raise InstanceRefused(
                f"qualification[{key}] records no rule; naming a geography is "
                f"not qualifying it")

    # -- the qualification must describe the geographies actually executed ---
    #
    # A substitution changes which geographies the thirteen cases run against.
    # Evidence measured over `B5`/`B50`/`B5 4` says nothing about a run over
    # `M3`/`M30`/`M3 7`, and a `substitutions` block bolted onto an otherwise
    # unchanged Instance would look complete while binding measurements to the
    # wrong places. Re-qualify against the artifact instead: `qualify
    # --substitutions` re-measures everything, and this refuses anything else.
    effective = {**DEFINITIONAL_GEOGRAPHIES, **substitutions}
    for entry_key, geography_key in sorted(GEOGRAPHY_BOUND_QUALIFICATIONS.items()):
        measured_over = qualification[entry_key].get("geography")
        expected = effective[geography_key]
        if not isinstance(measured_over, str) or not measured_over.strip():
            raise InstanceRefused(
                f"qualification[{entry_key}] does not record the geography it "
                f"was measured over; without it there is no way to tell whether "
                f"the measurement describes the run this Instance governs")
        if measured_over.strip().upper() != expected:
            raise InstanceRefused(
                f"qualification[{entry_key}] was measured over "
                f"{measured_over.strip().upper()!r}, but this Instance runs "
                f"{expected!r}. A substitution must be re-qualified against the "
                f"artifact -- evidence for one geography cannot be attached to "
                f"a run over another.")

    # -- the measurements and the baselines must be the same numbers --------
    #
    # Binding the geographies is half of it. The other half is that the counts
    # recorded beside them agree with the baselines the corpus is qualified on,
    # and that every derived field follows from those counts. Otherwise an
    # Instance can name the right places and carry figures from somewhere else
    # -- a re-qualification where one number was pasted from the previous run,
    # or a ratio edited to clear the literal rule without the counts moving.
    _cross_check_measurements(qualification, baselines, effective)


    # -- the neighbour rule: an explicit decision, or a refusal --------------
    #
    # Where the measurement meets the literal rule there is nothing to decide.
    # Where it does not, the Definition offers accept-with-recorded-decision or
    # substitute-with-recorded-justification, and `qualify` deliberately refers
    # rather than settles it. An Instance that simply carries the shortfall and
    # says nothing about it is that referral going unanswered.
    # `comparable_or_greater` has already been recomputed from the counts by
    # `_cross_check_measurements`, which refuses a missing or dishonest value,
    # so it can be read here as an established fact rather than re-guarded.
    s1_entry = qualification["S1_district"]
    if s1_entry["comparable_or_greater"] is False:
        decision = s1_entry.get("owner_decision")
        if not isinstance(decision, dict):
            raise InstanceRefused(
                f"the neighbour holds "
                f"{s1_entry.get('measured_neighbour_ratio')!r} of the "
                f"district's rows, below the literal 'comparable or greater', "
                f"and qualification[S1_district] records no owner_decision. "
                f"Adjudication is still pending, and a pending judgement is "
                f"not a qualification.")
        if str(decision.get("decision", "")).strip().lower() != "accepted":
            raise InstanceRefused(
                f"qualification[S1_district].owner_decision.decision is "
                f"{decision.get('decision')!r}; only 'accepted' qualifies the "
                f"case. Anything else leaves the Definition's other route -- "
                f"substitute with recorded justification -- untaken.")
        if not str(decision.get("justification", "")).strip():
            raise InstanceRefused(
                "qualification[S1_district].owner_decision records no "
                "justification; an accepted shortfall with no stated reason is "
                "a decision nobody can review")

    # `governs_run` is what ties this Instance to one Stage 1 run. Left blank or
    # left as the placeholder `qualify` wrote, it ties it to nothing -- and an
    # Instance nobody named a run for has not been through the review that field
    # exists to record.
    governs = raw["governs_run"]
    if not isinstance(governs, str) or not governs.strip():
        raise InstanceRefused(
            "governs_run is blank; an Instance must name the Stage 1 run it "
            "governs")
    if governs.strip() == GOVERNS_RUN_PLACEHOLDER or governs.strip().startswith("<"):
        raise InstanceRefused(
            f"governs_run is still the placeholder {governs.strip()!r}; the "
            f"candidate Instance has not been reviewed and named")

    # Binding. An Instance that is internally valid but describes a different
    # artifact would produce a report whose provenance is a fiction.
    if version != materialized.version:
        raise InstanceRefused(
            f"instance names snapshot_version {version}, but this Machine has "
            f"materialized {materialized.version}")
    if digest != materialized.bundle_sha256:
        raise InstanceRefused(
            "instance bundle_sha256 does not match the digest of the artifact "
            "materialized on this Machine; the instance describes a different "
            "artifact")

    return Stage1Instance(
        instance_kind=raw["instance_kind"],
        snapshot_version=version,
        bundle_sha256=digest,
        geographies=dict(geographies),
        aggregate_baselines=dict(baselines),
        qualified_at=str(raw["qualified_at"]),
        qualification=dict(raw["qualification"]),
        staleness_bound_days=int(bound),
        governs_run=str(raw["governs_run"]),
        substitutions=dict(substitutions),
    )


# ---------------------------------------------------------------------------
# qualify -- read-only aggregate counts against the materialized artifact
# ---------------------------------------------------------------------------

def _clamped_window(m: Materialized, months: int, today: date) -> tuple[str, str]:
    """The window a frozen case actually queries, as coverage clamps it.

    Comps sends no `to_date`, so routing clamps to `coverage_to` unconditionally
    and the lower bound is `today - months*30` narrowed up to `coverage_from`.
    Qualification must count over that same window or its baselines describe a
    query nobody runs.
    """
    lower = derived_from_date(today, months)
    if m.coverage_from and lower < m.coverage_from:
        lower = m.coverage_from
    return lower, (m.coverage_to or today.isoformat())


def _count(m: Materialized, where: str, params: list[Any]) -> int:
    """One aggregate COUNT over the adapter's own validated view.

    Deliberately the adapter's view, not a second one built here. The adapter
    creates it during `open()` having already validated every partition
    individually; rebuilding it would mean two definitions of "the snapshot",
    and the qualification counts would be over whichever one this file happened
    to describe. `tests/snapshot/test_stage1_shadow.py` pins the two adapter
    names this relies on, so a rename fails loudly here instead of silently
    counting something else.
    """
    from property_core.snapshot.adapter import VIEW

    sql = f"SELECT count(*) FROM {VIEW} WHERE {where}"
    return int(m.adapter._execute(sql, params).fetchone()[0])


def _frozen_where(*, months_window: tuple[str, str],
                  geography_sql: str,
                  property_types: Optional[tuple[str, ...]],
                  category: Optional[str]) -> tuple[str, list[Any]]:
    """The frozen parameters of Definition section 2, as a SQL predicate."""
    lower, upper = months_window
    where = [f"({geography_sql})", "transfer_date >= ?", "transfer_date <= ?"]
    params: list[Any] = [lower, upper]
    if property_types:
        placeholders = ", ".join("?" for _ in property_types)
        where.append(f"property_type IN ({placeholders})")
        params.extend(property_types)
    if category is not None:
        where.append("ppd_category = ?")
        params.append(category)
    return " AND ".join(where), params


def _aggregate(m: Materialized, *, geography_sql: str, geo_params: list[Any],
               months: int, today: date,
               property_types: Optional[tuple[str, ...]] = RESIDENTIAL_TYPES,
               category: Optional[str] = "A") -> int:
    where, params = _frozen_where(
        months_window=_clamped_window(m, months, today),
        geography_sql=geography_sql,
        property_types=property_types,
        category=category)
    return _count(m, where, geo_params + params)


def _rank(m: Materialized, column: str, *, months: int, today: date,
          property_types: Optional[tuple[str, ...]] = RESIDENTIAL_TYPES,
          category: Optional[str] = "A",
          having: str = "", having_params: Optional[list[Any]] = None,
          limit: int = 200) -> list[tuple[str, int]]:
    """Candidate geographies by row count under the frozen parameters.

    Ordered by count then value so selection is deterministic: the same
    artifact must qualify the same geographies on every run, or the Instance
    is not reproducible.

    `having` selects on the group's own aggregate, which is the only way to
    reach a population the `n DESC` ordering puts out of reach -- the sparse
    tail. Its placeholders bind after the WHERE clause's, in clause order, so a
    date in a HAVING predicate stays a bound parameter rather than becoming
    interpolated SQL.
    """
    from property_core.snapshot.adapter import VIEW

    lower, upper = _clamped_window(m, months, today)
    where = [f"{column} IS NOT NULL", "transfer_date >= ?", "transfer_date <= ?"]
    params: list[Any] = [lower, upper]
    if property_types:
        placeholders = ", ".join("?" for _ in property_types)
        where.append(f"property_type IN ({placeholders})")
        params.extend(property_types)
    if category is not None:
        where.append("ppd_category = ?")
        params.append(category)
    sql = (f"SELECT {column}, count(*) AS n FROM {VIEW} "
           f"WHERE {' AND '.join(where)} GROUP BY {column} "
           f"{having} ORDER BY n DESC, {column} ASC LIMIT {int(limit)}")
    params.extend(having_params or [])
    return [(r[0], int(r[1])) for r in m.adapter._execute(sql, params).fetchall()]


def _type_mix(m: Materialized, sector: str, *, months: int,
              today: date) -> dict[str, int]:
    from property_core.snapshot.adapter import VIEW

    lower, upper = _clamped_window(m, months, today)
    sql = (f"SELECT property_type, count(*) FROM {VIEW} WHERE sector = ? "
           f"AND transfer_date >= ? AND transfer_date <= ? AND ppd_category = 'A' "
           f"AND property_type IN ('F','D','S','T') GROUP BY property_type")
    rows = m.adapter._execute(sql, [sector, lower, upper]).fetchall()
    return {str(r[0]): int(r[1]) for r in rows}


def qualify(m: Materialized, *, today: Optional[date] = None,
            substitutions: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Select the seven placeholders and measure the three baselines.

    Read-only throughout: aggregate COUNT and GROUP BY only, no download, no
    live call, and nothing written into the snapshot. The output is a
    **candidate** Instance for review, never a runtime input.
    """
    today = today or date.today()
    # The block is carried through whole, justifications included, so the
    # candidate this emits is a document the loader accepts. Passing only the
    # resolved geographies dropped the justifications, and the candidate then
    # described substituted geographies while carrying no `substitutions` key
    # to declare them -- which the loader refuses, correctly, as evidence
    # attached to the wrong run.
    block = dict(substitutions or {})
    resolved = validate_substitutions(block) if block else {}
    definitional = {**DEFINITIONAL_GEOGRAPHIES, **resolved}
    qualification: dict[str, Any] = {}
    geo: dict[str, str] = {}

    # -- the three declared baselines, over the whole artifact ---------------
    s1 = _aggregate(m, geography_sql="outcode = ?",
                    geo_params=[definitional["S1_district"]],
                    months=24, today=today)
    s3 = _aggregate(m, geography_sql="sector = ?",
                    geo_params=[definitional["S3_sector"]],
                    months=24, today=today)
    s9 = _aggregate(m, geography_sql="sector = ?",
                    geo_params=[definitional["S3_sector"]],
                    months=24, today=today, category=None)
    baselines = {"S1_full": s1, "S3_full": s3, "S9_full": s9}

    # -- S1 and S2: definitional, but still qualified ------------------------
    # `B5` and `B50` are named in the Definition because the boundary is a
    # definitional choice rather than an artifact property -- but section 4 is
    # explicit that "an Instance must still qualify them". Measuring S1_full and
    # never checking the neighbour was qualifying neither: a B50 with no rows
    # makes S1 a test that cannot fail and S2 a case with nothing in it.
    unqualified_definitional: list[str] = []
    requires_adjudication: list[str] = []
    s2_full = _aggregate(m, geography_sql="outcode = ?",
                         geo_params=[definitional["S2_neighbour_district"]],
                         months=24, today=today)
    ratio = (s2_full / s1) if s1 else 0.0
    qualification["S1_district"] = {
        "rule": ("the longer neighbouring outcode holds comparable or greater "
                 "volume (Definition section 4)"),
        "geography": definitional["S1_district"],
        "measured_rows": s1,
        "neighbour_geography": definitional["S2_neighbour_district"],
        "measured_neighbour_rows": s2_full,
        "measured_neighbour_ratio": round(ratio, 4),
        "comparable_or_greater": bool(s1 > 0 and ratio >= NEIGHBOUR_COMPARABLE_RATIO),
    }
    if s1 <= 0:
        # No rows in the district at all: nothing to qualify, and no judgement
        # to refer.
        unqualified_definitional.append("S1_district")
    elif ratio < NEIGHBOUR_COMPARABLE_RATIO:
        # Below the literal rule. NOT auto-failed and NOT auto-passed: whether
        # this artifact's neighbour volume is "comparable" is the owner's
        # judgement, and the Definition offers accept-or-substitute. This tool
        # supplies the measurement and stops there.
        requires_adjudication.append("S1_district")
        qualification["S1_district"]["adjudication"] = (
            f"the neighbour holds {ratio:.1%} of the district's rows, which is "
            f"below the literal 'comparable or greater'. Accept it for this "
            f"artifact, or substitute a geography with recorded justification "
            f"(Definition section 4). This tool does not decide.")
    qualification["S2_district"] = {
        "rule": "non-empty under frozen parameters",
        "geography": definitional["S2_neighbour_district"],
        "measured_rows": s2_full,
    }
    if s2_full <= 0:
        unqualified_definitional.append("S2_district")
    # S3's sector carries the S3/S9 baselines, so it names the geography they
    # were counted over. Without this the baselines are three numbers with no
    # geography attached, and a substitution could not be checked against them.
    qualification["S3_sector"] = {
        "rule": ("a strict subset of S1's district, carrying the S3 and S9 "
                 "aggregate baselines"),
        "geography": definitional["S3_sector"],
        "measured_rows": s3,
        "measured_rows_category_all": s9,
        "inside_s1_district": definitional["S3_sector"].split()[0] == (
            definitional["S1_district"]),
    }
    if s3 <= 0:
        unqualified_definitional.append("S3_sector")

    # -- the dense candidate pool, for the placeholders defined by density ---
    # `n DESC ... LIMIT` is exactly right for S5/S6/S7/S8/S13 and structurally
    # wrong for S4 and S11, which live in the sparse tail this ordering
    # discards. Those two select over the same eligible population through
    # their own HAVING predicate rather than filtering this pool.
    sectors_ranked = _rank(m, "sector", months=24, today=today)

    # -- S4: thin market, strictly below the threshold ----------------------
    # `GROUP BY` cannot produce an empty group, so `count(*) < threshold` on a
    # returned row IS `0 < n < threshold`. Ordered `n DESC, sector ASC` like
    # every other selector, so the case chosen is the densest qualifying thin
    # sector -- the one closest to the boundary it exists to probe -- and the
    # tie-break keeps it reproducible.
    thin = _rank(m, "sector", months=24, today=today,
                 having=f"HAVING count(*) < {THIN_MARKET_THRESHOLD}", limit=1)
    if thin:
        geo["S4_thin"] = thin[0][0]
        qualification["S4_thin"] = {
            "rule": (f"non-empty and strictly below thin_market_threshold "
                     f"({THIN_MARKET_THRESHOLD}) under frozen parameters"),
            "measured_rows": thin[0][1]}

    # -- S5: dense, matching rows greatly exceed `limit` --------------------
    dense = [(s, n) for s, n in sectors_ranked if n > LIMIT * 4]
    if dense:
        geo["S5_dense"] = dense[0][0]
        qualification["S5_dense"] = {
            "rule": f"matching rows greatly exceed limit ({LIMIT})",
            "measured_rows": dense[0][1]}

    # -- S6: exact postcode, aggregate-dense so not individually identifying -
    units = _rank(m, "postcode", months=24, today=today)
    dense_units = [(p, n) for p, n in units if n >= MIN_UNIT_POSTCODE_ROWS]
    if dense_units:
        geo["S6_unit"] = dense_units[0][0]
        qualification["S6_unit"] = {
            "rule": (f"aggregate-dense (>= {MIN_UNIT_POSTCODE_ROWS} rows), so "
                     f"not individually identifying"),
            "measured_rows": dense_units[0][1]}

    # -- S7 / S8: a type filter that barely bites, and one that genuinely does
    for sector, total in sectors_ranked:
        if total < LIMIT:
            continue
        mix = _type_mix(m, sector, months=24, today=today)
        rows = sum(mix.values())
        if rows == 0:
            continue
        share_f = mix.get("F", 0) / rows
        if "S7_type_weak" not in geo and share_f >= 0.90:
            geo["S7_type_weak"] = sector
            qualification["S7_type_weak"] = {
                "rule": "at least 90% of the base is F",
                "measured_share_f": round(share_f, 4), "measured_rows": rows}
        # "A real spread across F/D/S/T": every type present, and F is not
        # dominant -- otherwise the filter barely bites and this is an S7.
        if ("S8_type_strong" not in geo
                and all(mix.get(t, 0) > 0 for t in RESIDENTIAL_TYPES)
                and share_f <= 0.60):
            geo["S8_type_strong"] = sector
            qualification["S8_type_strong"] = {
                "rule": "a real spread across F/D/S/T, F not dominant",
                "measured_share_f": round(share_f, 4),
                "measured_types_present": sorted(mix)}
        if "S7_type_weak" in geo and "S8_type_strong" in geo:
            break

    # -- S11: empty over a 6-month window that intersects the provisional tail
    # Active in the 24-month window (the group exists) and silent in the
    # 6-month one (the FILTER counts nothing). Both halves are asserted inside
    # one GROUP BY over the frozen predicate, so the two windows cannot be
    # measured under different filters -- and the 6-month bound is the one
    # `_clamped_window` returns, bound as a parameter.
    #
    # `>=` is the boundary comps itself queries on: a row dated exactly on the
    # lower bound is IN the window and disqualifies the sector.
    six = _clamped_window(m, 6, today)
    provisional_intersects = bool(
        m.provisional_from and m.coverage_to
        and not (six[1] < m.provisional_from or six[0] > m.coverage_to))
    empty_since = _rank(
        m, "sector", months=24, today=today,
        having="HAVING count(*) FILTER (WHERE transfer_date >= ?) = 0",
        having_params=[six[0]], limit=1)
    if empty_since:
        geo["S11_provisional_empty"] = empty_since[0][0]
        qualification["S11_provisional_empty"] = {
            "rule": ("returns zero rows over months=6 while the window "
                     "intersects the provisional period"),
            "measured_rows": 0,
            "window_intersects_provisional": provisional_intersects}

    # -- S13: a unit postcode non-empty under defaults with no `D` rows ------
    for postcode, total in dense_units:
        if _aggregate(m, geography_sql="postcode = ?", geo_params=[postcode],
                      months=24, today=today, property_types=("D",)) == 0:
            geo["S13_empty_unit"] = postcode
            qualification["S13_empty_unit"] = {
                "rule": ("non-empty under the residential default, zero rows "
                         "once filtered to property_type=D"),
                "measured_rows_default": total, "measured_rows_type_d": 0}
            break

    # The measured baselines must satisfy the very relations they exist to
    # establish, or the Instance built from them will be refused at load. Say so
    # here, while the operator is still choosing geographies, rather than
    # letting them find out from a refusal after the Instance is authored and
    # reviewed. A refusal is not a qualification failure by itself: the
    # Definition allows a geography to be substituted with recorded
    # justification, and this is the signal that one is needed.
    try:
        validate_baselines(baselines)
        baselines_refusal = None
    except InstanceRefused as exc:
        baselines_refusal = str(exc)

    candidate = {
        "instance_kind": INSTANCE_KIND,
        "snapshot_version": m.version,
        "bundle_sha256": m.bundle_sha256,
        "geographies": geo,
        "aggregate_baselines": baselines,
        "qualified_at": today.isoformat(),
        "qualification": qualification,
        "staleness_bound_days": 45,
        "governs_run": GOVERNS_RUN_PLACEHOLDER,
    }
    if block:
        # Verbatim, justifications and all. An operator must be able to take
        # this candidate, fill in `governs_run` (and any owner decision), and
        # have it load -- without reconstructing by hand a block the tool
        # already validated.
        candidate["substitutions"] = block
    return {
        "kind": "stage1_qualification_candidate",
        "is_instance": False,
        "note": (
            "A CANDIDATE Instance. It is reviewed and committed as its own "
            "change before Stage 1 runs; it is never read as runtime "
            "configuration and nothing here is hard-coded into the tool."),
        "definitional_geographies": dict(definitional),
        "substituted": definitional != DEFINITIONAL_GEOGRAPHIES,
        "coverage": {"coverage_from": m.coverage_from,
                     "coverage_to": m.coverage_to,
                     "provisional_from": m.provisional_from},
        "comparator_version": COMPARATOR_VERSION,
        "baselines_satisfy_their_relations": baselines_refusal is None,
        "baselines_refusal": baselines_refusal,
        "baselines_note": (
            f"S1 is measured over {definitional['S1_district']}, and S3/S9 over "
            f"{definitional['S3_sector']}. If they do not satisfy the "
            f"strict-subset and category-B relations, the Definition allows a "
            f"substituted geography with recorded justification -- which is an "
            f"authoring decision, not something this tool may make."),
        # Definitional cases that failed their own qualification rule. Kept
        # separate from the placeholders because they cannot be substituted by
        # choosing a different geography -- B5/B50 IS the contamination
        # boundary the corpus is built around.
        "unqualified_definitional_cases": sorted(unqualified_definitional),
        # Measured, not decided. A judgement the Definition reserves to the
        # owner, with the figures needed to make it.
        "requires_owner_adjudication": sorted(requires_adjudication),
        "substitution_route": (
            "Definition section 4 permits substituting a definitional geography "
            "with recorded justification. Supply all of "
            f"{sorted(DEFINITIONAL_GEOGRAPHIES)} under the Instance's "
            "`substitutions` key, each with a `geography` and a `justification`."),
        "unqualified_placeholders": sorted(
            {"S4_thin", "S5_dense", "S6_unit", "S7_type_weak", "S8_type_strong",
             "S11_provisional_empty", "S13_empty_unit"} - set(geo)),
        "candidate_instance": candidate,
    }


# ---------------------------------------------------------------------------
# Latency -- nearest rank, defined exactly
# ---------------------------------------------------------------------------

def nearest_rank(values: list[float], percentile: float) -> Optional[float]:
    """The nearest-rank percentile, spelled out so it cannot drift.

    Sort ascending; take the value at 1-based rank ``ceil(p/100 * N)``. For
    ``N = 390`` and ``p = 95`` that is rank 371, i.e. index 370 -- a value that
    was actually observed, never an interpolation between two observations.
    Interpolating would report a latency no request ever took, which is the
    wrong kind of number to hang a deployment gate on.
    """
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile / 100.0 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def latency_summary(values: list[float]) -> dict[str, Any]:
    return {
        "n": len(values),
        "p50_ms": nearest_rank(values, 50),
        "p95_ms": nearest_rank(values, 95),
        "p99_ms": nearest_rank(values, 99),
        "max_ms": max(values) if values else None,
        "method": "nearest rank: sorted ascending, 1-based rank ceil(p/100*N)",
    }


# ---------------------------------------------------------------------------
# Diffing -- ids and field values live in memory only
# ---------------------------------------------------------------------------

def _month(value: Any) -> str:
    text = str(value or "")
    return text[:7] if len(text) >= 7 else "unknown"


def _by_month(transactions: Any, keep: set[str]) -> dict[str, int]:
    """A month histogram over the rows whose ids are in `keep`.

    A month is the finest granularity that classification needs -- it answers
    "is this row in the provisional tail?" -- and is not identifying. The ids
    themselves are the argument, not the output.
    """
    counter: Counter[str] = Counter()
    for t in transactions:
        if getattr(t, "transaction_id", None) in keep:
            counter[_month(getattr(t, "date", None))] += 1
    return dict(sorted(counter.items()))


def _field_mismatches(live: Any, snap: Any, shared: set[str]) -> tuple[
        dict[str, int], dict[str, int], int]:
    """Per-field mismatch tallies over shared ids. Values never leave here.

    Returns the tally by field, a month histogram of the rows that disagreed,
    and how many rows disagreed at all. Comparison is on the values the models
    produced, with **no normalisation**: a systematic representational
    difference between the two sources is a finding, not something a harness
    should quietly paper over.
    """
    live_by_id = {t.transaction_id: t for t in live
                  if getattr(t, "transaction_id", None) in shared}
    snap_by_id = {t.transaction_id: t for t in snap
                  if getattr(t, "transaction_id", None) in shared}
    tally: Counter[str] = Counter()
    months: Counter[str] = Counter()
    rows = 0
    for tid in sorted(shared):
        a, b = live_by_id.get(tid), snap_by_id.get(tid)
        if a is None or b is None:
            continue
        differing = [f for f in COMPARED_FIELDS
                     if getattr(a, f, None) != getattr(b, f, None)]
        if differing:
            rows += 1
            months[_month(getattr(a, "date", None))] += 1
            for f in differing:
                tally[f] += 1
    return dict(sorted(tally.items())), dict(sorted(months.items())), rows


def classify(*, only_live_months: dict[str, int], only_snapshot_months: dict[str, int],
             mismatch_months: dict[str, int], provisional_from: Optional[str],
             live_saturated: bool, snapshot_saturated: bool,
             live_truncation_evidenced: bool) -> dict[str, Any]:
    """Definition section 7's four classes, and nothing else.

    Class 3 (**live truncation or ordering**) is assigned **only** from
    captured live transport evidence -- `raw_bindings_returned` against
    `fetch_limit`, which is a fact about what the upstream window returned.

    Page saturation is deliberately NOT evidence, on either side. A live page
    at `limit` says our own presentation limit was reached, not that the
    upstream window was; a saturated *snapshot* page says nothing whatever
    about live. Treating either as evidence is the "the snapshot returned more,
    so live must have truncated" assumption wearing a taxonomy label, which is
    exactly what the Definition forbids. Saturation is still recorded, as
    context an operator may weigh -- but it cannot classify anything.

    Class 2 (**later A/C/D revision**) cannot be evidenced from these two
    sources at all: confirming it needs the monthly change records published
    after the build. It is therefore proposed, never asserted, and carries
    `operator_confirmation_required`.
    """
    prov = provisional_from or ""
    # Captured transport evidence, and nothing else. With no evidence the
    # divergence stays unclassified and blocks exit -- which is the fail-closed
    # direction: an unexplained difference is a question, not a pass.
    truncation = live_truncation_evidenced

    provisional_tail_lag = 0
    unclassified = 0
    live_truncation = 0
    for month, n in only_live_months.items():
        if prov and month >= prov[:7]:
            provisional_tail_lag += n
        elif truncation:
            live_truncation += n
        else:
            unclassified += n
    for month, n in only_snapshot_months.items():
        if truncation:
            live_truncation += n
        elif prov and month >= prov[:7]:
            # A row the snapshot holds and live does not, inside the
            # provisional tail, is still the provisional period moving --
            # revision runs in both directions.
            provisional_tail_lag += n
        else:
            unclassified += n

    later_acd = 0
    for month, n in mismatch_months.items():
        if prov and month >= prov[:7]:
            provisional_tail_lag += n
        else:
            later_acd += n

    return {
        "provisional_tail_lag": provisional_tail_lag,
        "later_acd_revision": later_acd,
        "live_truncation_or_ordering": live_truncation,
        "unclassified": unclassified,
        "operator_confirmation_required": later_acd,
        "truncation_evidence": {
            # The only thing that may classify class 3.
            "live_raw_bindings_reached_fetch_limit": live_truncation_evidenced,
            # Context for an operator, explicitly not evidence. Recorded so a
            # reader can see saturation was considered and rejected as a basis.
            "context_not_evidence": {
                "live_page_saturated": live_saturated,
                "snapshot_page_saturated": snapshot_saturated,
            },
        },
    }


# ---------------------------------------------------------------------------
# Live transport evidence, captured without touching public models
# ---------------------------------------------------------------------------

class LiveEvidenceCapture:
    """Record `raw_bindings_returned` / `fetch_limit` for the live arm.

    Divergence class 3 must be *evidenced*, and those two numbers are the
    evidence. They are carried up the live path as `TransportEvidence` but are
    deliberately not exposed on `PPDCompsResponse`, so the only ways to see
    them are to widen a public response model or to observe the transport call.

    Widening the model would put a rollout-diagnostic field into every
    consumer's payload permanently, so this observes instead: it wraps the exact
    method the live path already calls, for the duration of this process only,
    and changes nothing about what that method does. The wrap is installed and
    removed around the live arm; the serving application is a different process
    and is untouched either way.
    """

    def __init__(self) -> None:
        self.last: dict[str, Any] = {}
        self._original: Optional[Callable[..., Any]] = None

    def __enter__(self) -> "LiveEvidenceCapture":
        from property_core.ppd_client import PricePaidDataClient

        self._original = PricePaidDataClient.search_with_evidence

        def _wrapped(inner_self, **kwargs):
            page = self._original(inner_self, **kwargs)
            evidence = getattr(page, "evidence", None)
            self.last = {
                "raw_bindings_returned": getattr(
                    evidence, "raw_bindings_returned", None),
                "fetch_limit": getattr(evidence, "fetch_limit", None),
                "source_exhausted": getattr(evidence, "source_exhausted", None),
            }
            return page

        PricePaidDataClient.search_with_evidence = _wrapped  # type: ignore[assignment]
        return self

    def __exit__(self, *exc_info) -> None:
        if self._original is not None:
            from property_core.ppd_client import PricePaidDataClient

            PricePaidDataClient.search_with_evidence = self._original  # type: ignore[assignment]
            self._original = None

    @property
    def truncation_evidenced(self) -> bool:
        raw = self.last.get("raw_bindings_returned")
        limit = self.last.get("fetch_limit")
        return raw is not None and limit is not None and raw >= limit


# ---------------------------------------------------------------------------
# Health and resource monitoring
# ---------------------------------------------------------------------------

def available_memory_bytes(meminfo: Optional[str] = None) -> Optional[int]:
    """`MemAvailable` from /proc/meminfo, or None where it cannot be read.

    None means "unknown", never "fine": the caller treats an unreadable value
    as a reason to keep going only because the floor check is a guard against a
    Machine under pressure, not the primary safety property.
    """
    try:
        text = meminfo if meminfo is not None else Path("/proc/meminfo").read_text()
    except OSError:
        return None
    for line in text.splitlines():
        if line.startswith("MemAvailable:"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1]) * 1024
    return None


def health_ok(url: str, timeout: float = 5.0) -> tuple[bool, str]:
    """Ask the serving application on this Machine whether it is still well.

    Localhost only: this is the app sharing the Machine with the run, and the
    point is to notice if the run is disturbing it.
    """
    try:
        import httpx

        response = httpx.get(url, timeout=timeout)
        return response.status_code == 200, f"{response.status_code}"
    except Exception as exc:  # noqa: BLE001 -- a monitor must not raise
        return False, f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# The Stage 1 run
# ---------------------------------------------------------------------------

@dataclass
class RunLimits:
    """Every bound the run may not exceed, in one place.

    Bounds rather than best effort: this process shares a 2 GB Machine with the
    application that is serving, so "shadow traffic cannot exhaust the Machine"
    has to be a refusal, not an intention.
    """

    live_delay_seconds: float = 2.0
    latency_repeats: int = REQUIRED_LATENCY_REPEATS
    #: Enforced, not advisory. The correctness pass takes one live observation
    #: per case; a value below 1 is refused outright, because a comparison with
    #: no live arm is not a comparison, and the budget is checked before every
    #: live call so the bound cannot be exceeded by a later code change without
    #: the run stopping.
    max_live_per_case: int = 1
    deadline_seconds: float = 3600.0
    min_available_memory_bytes: int = 256 * 1024 * 1024
    health_url: str = "http://127.0.0.1:8080/v1/health"
    stop_on_unclassified: bool = True


#: Bounded retry for an observation that straddles midnight. Three, matching
#: the local rehearsal, so the two tools behave the same way at the same
#: boundary. A crossing is possible once a day at most; three attempts either
#: clear it or prove something else is wrong.
MIDNIGHT_ATTEMPTS = 3


def check_live_budget(live_calls: int, limits: "RunLimits", corpus_size: int,
                      shape: str) -> None:
    """Refuse a live call that would exceed the run's declared budget.

    Checked before every live observation rather than assumed from the shape of
    the loop. The loop takes one per case today; this is what makes the bound
    survive a change that adds another, instead of quietly making more requests
    to HM Land Registry than the run declared.
    """
    budget = limits.max_live_per_case * corpus_size
    if live_calls >= budget:
        raise RunAborted(
            f"the live-call budget of {budget} ({limits.max_live_per_case} per "
            f"case x {corpus_size} cases) is exhausted at {shape}; a further "
            f"live observation needs separate authorisation")


def _observe(service: Any, case: Case, *,
             attempts: int = 1) -> tuple[Any, str, int, float]:
    """One comps call, guaranteed to lie inside a single calendar date.

    `comps` derives its window from `date.today()`, so an observation that
    straddles midnight silently describes a different window from the one
    recorded. Such an observation is **never skipped**: skipping it would leave
    a report claiming thirteen cases while holding twelve, and a latency sample
    short of its declared size. It is retried where retrying is free, and
    otherwise it aborts the run.

    `attempts` is 1 by default -- the caller decides whether a retry is
    affordable. The snapshot arm can retry for nothing; the live arm cannot,
    because a retry there is another request to HM Land Registry and the
    correctness pass is budgeted at one per case.
    """
    retries = 0
    for _ in range(max(1, attempts)):
        before = date.today()
        started = time.monotonic()
        response = service.comps(
            postcode=case.postcode,
            search_level=case.search_level,
            months=case.months,
            property_type=case.property_type,
            transaction_category=case.transaction_category,
            filter_outliers=False,
            limit=LIMIT,
            auto_escalate=True,
        )
        elapsed_ms = (time.monotonic() - started) * 1000.0
        after = date.today()
        if before == after:
            return response, before.isoformat(), retries, elapsed_ms
        retries += 1
    raise MidnightCrossed(
        f"{case.shape}: no same-date observation in {attempts} attempt(s); the "
        f"window recorded for this case would not describe the query that ran",
        retries=retries)


class MidnightCrossed(RunAborted):
    """An observation could not be taken within one calendar date.

    A subclass of `RunAborted`, deliberately: a crossing that survives its
    retries stops the run and writes a failed report. It is never absorbed as
    an exclusion, because a report that quietly dropped an observation is a
    report whose totals do not mean what they say.
    """

    def __init__(self, message: str, *, retries: int = 0) -> None:
        super().__init__(message)
        self.retries = retries


def _provenance_source(response: Any) -> Optional[str]:
    provenance = getattr(response, "provenance", None)
    if provenance is None:
        return None
    source = getattr(provenance, "source", None)
    return getattr(source, "value", None) or (str(source) if source else None)


def _arm_record(response: Any, case: Case, observed: str,
                latency_ms: float) -> dict[str, Any]:
    """What one arm produced -- aggregates, geography and provenance only."""
    provenance = getattr(response, "provenance", None)
    return {
        "count": response.count,
        "latency_ms": round(latency_ms, 2),
        "thin_market": response.thin_market,
        "outcodes_returned": _outcodes(response.transactions),
        "sectors_returned": _sectors(response.transactions),
        "warning_classes": _warning_classes(tuple(response.warnings or ())),
        "saturated_at_limit": response.count == LIMIT,
        "returned_date_from": returned_date_bounds(response.transactions)[0],
        "returned_date_to": returned_date_bounds(response.transactions)[1],
        "source": _provenance_source(response),
        "observed_at": observed,
        "derived_from_date": derived_from_date(date.fromisoformat(observed),
                                               case.months),
        "resolved_to_date": getattr(provenance, "coverage_to", None),
        "recent_period_provisional": getattr(
            provenance, "recent_period_provisional", None),
        "sample_complete": getattr(provenance, "sample_complete", None),
    }


def _geography_contamination(response: Any, case: Case) -> Optional[dict[str, Any]]:
    """Rows outside the requested geography, judged at the requested level.

    Returns `None` when clean. An outcode-only test would pass a `sector` case
    handed a neighbouring sector in the same outcode -- which is the sector
    isolation trap the Definition names in its own right.
    """
    violations = geography_violations(case, response.transactions)
    return violations if is_contaminated(violations) else None


def run_compare(*, instance: Stage1Instance, materialized: Materialized,
                limits: RunLimits, report_path: Path,
                live_service: Optional[Any] = None,
                snapshot_service: Optional[Any] = None) -> dict[str, Any]:
    """Execute the frozen corpus against both arms, then measure latency.

    Two passes, deliberately separate:

    * **correctness** -- every case once through each arm, giving the
      divergence, geography and error evidence. One rate-limited live
      observation per case: the live source is HM Land Registry's, and the
      corpus is a fixed thirteen, so there is no reason to ask it more.
    * **latency** -- the snapshot arm alone, repeated, giving the p95 sample
      with **no further live calls at all**.

    The run stops on a health, memory, snapshot-error or unclassified-divergence
    anomaly, and the partial report is still written.
    """
    from property_core.ppd_service import PPDService

    # Fail fast, before an adapter is used or a single request is made. An
    # option that silently does nothing is worse than no option: it tells an
    # operator they have a control they do not have.
    if limits.max_live_per_case < 1:
        raise ComparisonRefused(
            f"max_live_per_case is {limits.max_live_per_case}; the correctness "
            f"pass needs one live observation per case, and a comparison with "
            f"no live arm is not a comparison")
    if limits.latency_repeats < 1:
        raise ComparisonRefused(
            f"latency_repeats is {limits.latency_repeats}; a run that takes no "
            f"latency observation cannot produce the sample the gate is "
            f"defined over")

    live_service = live_service or PPDService()
    snapshot_service = snapshot_service or PPDService(adapter=materialized.adapter)

    identity = materialized.identity()
    started_at = time.monotonic()
    corpus = cases(instance.geographies, instance.substitutions)

    results: list[dict[str, Any]] = []
    snapshot_errors: list[dict[str, Any]] = []
    live_errors: list[dict[str, Any]] = []
    contamination: list[dict[str, Any]] = []
    excluded = {"health": 0, "memory": 0}
    midnight = {"retries": 0, "unrecoverable": False, "pair_date_mismatches": 0}
    aborted: Optional[str] = None
    live_calls = 0

    def _guard(stage: str) -> None:
        """Health, memory and deadline, checked between observations."""
        if time.monotonic() - started_at > limits.deadline_seconds:
            raise RunAborted(f"deadline of {limits.deadline_seconds}s exceeded at {stage}")
        available = available_memory_bytes()
        if available is not None and available < limits.min_available_memory_bytes:
            excluded["memory"] += 1
            raise RunAborted(
                f"available memory {available} B fell below the floor "
                f"{limits.min_available_memory_bytes} B at {stage}")
        ok, detail = health_ok(limits.health_url)
        if not ok:
            excluded["health"] += 1
            raise RunAborted(f"application health check failed at {stage}: {detail}")

    try:
        # -- pass A: correctness -------------------------------------------
        for case in corpus:
            _guard(f"correctness/{case.shape}")
            record: dict[str, Any] = {
                "shape": case.shape,
                "intent": case.intent,
                "request": {"wire": case.request(), "effective": case.effective()},
                "artifact": dict(identity),
            }

            # The snapshot arm may retry a midnight crossing: it costs nothing
            # but a local query. The live arm may not -- a retry there is
            # another request to HM Land Registry, and the correctness pass is
            # budgeted at one per case. Either way a surviving crossing aborts.
            snap_response = None
            try:
                snap_response, snap_observed, retries, snap_ms = _observe(
                    snapshot_service, case, attempts=MIDNIGHT_ATTEMPTS)
                midnight["retries"] += retries
                record["snapshot"] = _arm_record(snap_response, case,
                                                 snap_observed, snap_ms)
                record["snapshot_invariants"] = snapshot_invariants(
                    case, snap_response, getattr(snap_response, "provenance", None),
                    record["snapshot"]["warning_classes"])
            except MidnightCrossed as exc:
                midnight["retries"] += exc.retries
                midnight["unrecoverable"] = True
                results.append(record)
                raise
            except Exception as exc:  # noqa: BLE001 -- recorded, then stops the run
                # Recorded and then fatal. "Zero snapshot errors on the frozen
                # corpus" is already unreachable at this point, so every later
                # case is work whose result cannot change the verdict -- and
                # the live call this case would otherwise make is a request to
                # HM Land Registry for a comparison that can no longer happen.
                # The partial report is still written; a run that stopped for a
                # reason is evidence about that reason.
                snapshot_errors.append({"shape": case.shape,
                                        "error": f"{type(exc).__name__}: {exc}"})
                record["snapshot_error"] = f"{type(exc).__name__}: {exc}"
                results.append(record)
                raise RunAborted(
                    f"{case.shape}: the snapshot arm failed "
                    f"({type(exc).__name__}: {exc}); no live call is made for "
                    f"this case and no later case runs")

            live_response = None
            check_live_budget(live_calls, limits, len(corpus), case.shape)
            with LiveEvidenceCapture() as capture:
                try:
                    live_calls += 1
                    live_response, live_observed, _, live_ms = _observe(
                        live_service, case)
                    record["live"] = _arm_record(live_response, case,
                                                 live_observed, live_ms)
                    record["live"]["transport_evidence"] = dict(capture.last)
                    record["live_truncation_evidenced"] = capture.truncation_evidenced
                except MidnightCrossed:
                    midnight["unrecoverable"] = True
                    results.append(record)
                    raise
                except Exception as exc:  # noqa: BLE001 -- recorded, then stops
                    live_errors.append({"shape": case.shape,
                                        "error": f"{type(exc).__name__}: {exc}"})
                    record["live_error"] = f"{type(exc).__name__}: {exc}"
                    results.append(record)
                    raise RunAborted(
                        f"{case.shape}: the live arm failed "
                        f"({type(exc).__name__}: {exc}); completeness is already "
                        f"lost, so no later case runs")
            time.sleep(limits.live_delay_seconds)

            if snap_response is not None and live_response is not None:
                # Both arms must describe the same day. `comps` derives its
                # window from `date.today()`, so a pair straddling midnight is
                # two different questions being compared as though they were
                # one -- which no amount of downstream analysis can detect.
                if record["snapshot"]["observed_at"] != record["live"]["observed_at"]:
                    midnight["pair_date_mismatches"] += 1
                    midnight["unrecoverable"] = True
                    results.append(record)
                    raise RunAborted(
                        f"{case.shape}: the snapshot arm was observed on "
                        f"{record['snapshot']['observed_at']} and the live arm on "
                        f"{record['live']['observed_at']}; the pair straddles "
                        f"midnight and compares two different windows")

                record.update(_compare_arms(
                    case=case, live=live_response, snap=snap_response,
                    provisional_from=materialized.provisional_from,
                    live_truncation_evidenced=bool(
                        record.get("live_truncation_evidenced"))))
                # Both arms. Contamination is a defect in whichever source
                # produced it (Definition section 7), so neither arm is assumed
                # clean because the other is.
                for arm, response in (("live", live_response),
                                      ("snapshot", snap_response)):
                    stray = _geography_contamination(response, case)
                    if stray:
                        contamination.append({"shape": case.shape, "arm": arm,
                                              **stray})
                if (limits.stop_on_unclassified
                        and record.get("classification", {}).get("unclassified")):
                    results.append(record)
                    raise RunAborted(
                        f"{case.shape}: an unclassified divergence blocks Stage 1 "
                        f"exit and stops the run for investigation")

            results.append(record)

        # -- pass B: latency, snapshot arm only, no further live calls ------
        latency_ms: list[float] = []
        per_case: dict[str, list[float]] = {}
        for repeat in range(limits.latency_repeats):
            _guard(f"latency/{repeat + 1}")
            for case in corpus:
                try:
                    _, _, retries, elapsed = _observe(
                        snapshot_service, case, attempts=MIDNIGHT_ATTEMPTS)
                    midnight["retries"] += retries
                except MidnightCrossed as exc:
                    midnight["retries"] += exc.retries
                    midnight["unrecoverable"] = True
                    raise
                except Exception as exc:  # noqa: BLE001 -- recorded, then stops
                    # Same rule as the correctness pass. Continuing would leave
                    # this case short of its thirty repetitions, and the gate
                    # would then report `insufficient_evidence` for a reason
                    # buried in an error list rather than the snapshot error
                    # that actually caused it. `zero_snapshot_errors` is
                    # unreachable from here in any case.
                    snapshot_errors.append({"shape": case.shape,
                                            "error": f"{type(exc).__name__}: {exc}"})
                    raise RunAborted(
                        f"{case.shape}: the snapshot arm failed during the "
                        f"latency pass ({type(exc).__name__}: {exc}); the "
                        f"sample cannot be completed and no later repetition "
                        f"runs")
                latency_ms.append(elapsed)
                per_case.setdefault(case.shape, []).append(elapsed)

        # One last guard AFTER the final observation. Without it the run could
        # complete its last case on a Machine that had already gone unhealthy
        # or run out of memory, and report a clean pass measured under
        # conditions nobody checked.
        _guard("final")
    except RunAborted as exc:
        aborted = str(exc)
        latency_ms = locals().get("latency_ms", [])  # type: ignore[assignment]
        per_case = locals().get("per_case", {})  # type: ignore[assignment]

    report = _build_report(
        instance=instance, identity=identity, limits=limits, results=results,
        latency_ms=latency_ms, per_case=per_case, snapshot_errors=snapshot_errors,
        live_errors=live_errors, contamination=contamination, excluded=excluded,
        midnight=midnight, corpus=corpus, aborted=aborted, live_calls=live_calls)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=False))
    return report


def _compare_arms(*, case: Case, live: Any, snap: Any,
                  provisional_from: Optional[str],
                  live_truncation_evidenced: bool) -> dict[str, Any]:
    """One case's structured diff. Ids and values are discarded on return."""
    live_ids, snap_ids = _ids(live.transactions), _ids(snap.transactions)
    only_live, only_snapshot = live_ids - snap_ids, snap_ids - live_ids
    shared = live_ids & snap_ids

    only_live_months = _by_month(live.transactions, only_live)
    only_snapshot_months = _by_month(snap.transactions, only_snapshot)
    tally, mismatch_months, mismatch_rows = _field_mismatches(
        live.transactions, snap.transactions, shared)

    both_returned_rows = bool(live_ids) and bool(snap_ids)
    return {
        "diff": {
            "only_live": {"count": len(only_live), "by_month": only_live_months},
            "only_snapshot": {"count": len(only_snapshot),
                              "by_month": only_snapshot_months},
            "shared": {"count": len(shared)},
            "count_delta": snap.count - live.count,
            "field_mismatches": tally,
            "field_mismatch_rows": mismatch_rows,
            "field_mismatch_by_month": mismatch_months,
            "compared_fields": list(COMPARED_FIELDS),
        },
        # A snapshot that returns nothing where live returned rows, inside
        # coverage, is the criterion's "false empty".
        "snapshot_false_empty": snap.count == 0 and live.count > 0,
        # The vacuous-pass guard. "100% equality on shared ids" is trivially
        # true when no id is shared -- which is exactly what a systematic
        # difference in id spelling between the two sources would produce. An
        # empty intersection where both arms returned rows is a blocking
        # finding, never a pass.
        "empty_id_intersection_with_rows_on_both_sides": (
            both_returned_rows and not shared),
        "classification": classify(
            only_live_months=only_live_months,
            only_snapshot_months=only_snapshot_months,
            mismatch_months=mismatch_months,
            provisional_from=provisional_from,
            live_saturated=live.count == LIMIT,
            snapshot_saturated=snap.count == LIMIT,
            live_truncation_evidenced=live_truncation_evidenced),
    }


def _build_report(*, instance: Stage1Instance, identity: dict[str, Any],
                  limits: RunLimits, results: list[dict[str, Any]],
                  latency_ms: list[float], per_case: dict[str, list[float]],
                  snapshot_errors: list[dict[str, Any]],
                  live_errors: list[dict[str, Any]],
                  contamination: list[dict[str, Any]],
                  excluded: dict[str, int], midnight: dict[str, Any],
                  corpus: list[Case], aborted: Optional[str],
                  live_calls: int) -> dict[str, Any]:
    """The Stage 1 report, and its verdict against each exit criterion.

    Every criterion here can only move the verdict towards failure. There is no
    path by which a missing observation, an absent arm, a short latency sample
    or an unconfirmed classification produces a pass -- absence is never
    evidence of compliance.
    """
    unclassified = sum(r.get("classification", {}).get("unclassified", 0)
                       for r in results)
    confirmation = sum(
        r.get("classification", {}).get("operator_confirmation_required", 0)
        for r in results)
    false_empties = [r["shape"] for r in results if r.get("snapshot_false_empty")]
    vacuous = [r["shape"] for r in results
               if r.get("empty_id_intersection_with_rows_on_both_sides")]
    mismatch_rows = sum(r.get("diff", {}).get("field_mismatch_rows", 0)
                        for r in results)
    compared = [r for r in results if "diff" in r]

    # -- completeness ---------------------------------------------------
    expected = [c.shape for c in corpus]
    missing_snapshot = [r["shape"] for r in results if "snapshot" not in r]
    missing_live = [r["shape"] for r in results if "live" not in r]
    never_reached = sorted(set(expected) - {r["shape"] for r in results})
    complete = (len(compared) == REQUIRED_CASES
                and len(results) == REQUIRED_CASES
                and not missing_snapshot and not missing_live
                and not never_reached and not live_errors and not snapshot_errors
                and not midnight["unrecoverable"]
                and not midnight["pair_date_mismatches"])

    # -- corpus invariants (Definition section 3 and the case intents) ---
    invariant_failures = [
        {"shape": r["shape"],
         "failed": sorted(k for k, v in r["snapshot_invariants"].items() if not v)}
        for r in results
        if r.get("snapshot_invariants")
        and not all(r["snapshot_invariants"].values())]
    invariants_checked = sum(len(r.get("snapshot_invariants", {})) for r in results)

    # -- latency --------------------------------------------------------
    latency = latency_summary(latency_ms)
    p95 = latency["p95_ms"]
    short_cases = sorted(
        {shape for shape in expected
         if len(per_case.get(shape, [])) != REQUIRED_LATENCY_REPEATS})
    sample_complete = (latency["n"] == REQUIRED_LATENCY_OBSERVATIONS
                       and not short_cases)
    if not sample_complete:
        latency_verdict = "insufficient_evidence"
    elif p95 is not None and p95 < 1000.0:
        latency_verdict = "pass"
    else:
        latency_verdict = "fail"

    criteria = {
        "all_thirteen_cases_compared": {
            "passed": complete,
            "cases_recorded": len(results),
            "cases_compared": len(compared),
            "required": REQUIRED_CASES,
            "cases_missing_snapshot_arm": missing_snapshot,
            "cases_missing_live_arm": missing_live,
            "cases_never_reached": never_reached,
            "live_errors": len(live_errors),
            "snapshot_errors": len(snapshot_errors),
            "note": ("the frozen corpus is thirteen cases with two arms each; a "
                     "report covering fewer is not a smaller Stage 1 result, it "
                     "is not a Stage 1 result"),
        },
        "corpus_invariants_hold": {
            "passed": not invariant_failures and complete,
            "assertions_checked": invariants_checked,
            "failures": invariant_failures,
            "note": ("Definition section 3's universal invariants and each "
                     "shape's intent, asserted on the snapshot arm; a case "
                     "reporting sample_complete true is a defect, not a "
                     "divergence"),
        },
        "zero_unexplained_false_empties": {
            "passed": (not false_empties or unclassified == 0) and complete,
            "false_empty_shapes": false_empties,
            "note": ("a false empty is only a failure when it is unexplained; "
                     "these are checked against the classification below"),
        },
        "zero_geography_contamination": {
            "passed": not contamination and complete, "findings": contamination},
        "field_equality_on_shared_ids": {
            "passed": mismatch_rows == 0 and not vacuous and complete,
            "mismatch_rows": mismatch_rows,
            "vacuous_comparison_shapes": vacuous,
            "note": ("a shape listed under vacuous_comparison_shapes shared no "
                     "transaction id while both arms returned rows; equality "
                     "over an empty intersection proves nothing and is "
                     "reported as a failure, not a pass"),
        },
        "every_divergence_classified": {
            "passed": unclassified == 0 and complete, "unclassified": unclassified,
            "note": "an unclassified divergence blocks exit",
        },
        "no_unconfirmed_classifications": {
            # Blocking, not advisory. "Later A/C/D revision" is a PROPOSED
            # class: confirming one needs the monthly change records published
            # after the build, which this comparison cannot see. A verdict that
            # passed while carrying proposals would be recording a guess as a
            # result.
            "passed": confirmation == 0,
            "operator_confirmation_required": confirmation,
            "note": ("later A/C/D revision cannot be evidenced from these two "
                     "sources; while any remain proposed, Stage 1 cannot exit "
                     "on this report alone -- external confirmation is a "
                     "separately authorised step"),
        },
        "zero_snapshot_errors": {
            "passed": not snapshot_errors, "errors": snapshot_errors},
        "p95_under_one_second": {
            "passed": latency_verdict == "pass",
            "verdict": latency_verdict,
            "p95_ms": p95, "n": latency["n"],
            "required_observations": REQUIRED_LATENCY_OBSERVATIONS,
            "required_repeats_per_case": REQUIRED_LATENCY_REPEATS,
            "cases_short_of_the_required_repeats": short_cases,
            "criterion": ("p95 < 1 second on the deployed production Machine "
                          "and selected artifact, measured across the frozen "
                          "corpus request mix (governing spec rev 10)"),
            "note": ("a partial sample is insufficient_evidence, never a pass: "
                     "a percentile over fewer observations than the gate is "
                     "defined over is a different measurement"),
        },
    }

    return {
        "kind": "stage1_shadow_comparison",
        "stage_1_evidence": True,
        "latency_sample_kind": "deployed_machine_frozen_corpus",
        "not_organic_traffic": (
            "The request mix is the frozen thirteen-case corpus, chosen in "
            "advance, executed on the deployed production Machine against the "
            "selected artifact. It is not a sample of organic traffic and must "
            "never be described as one (governing spec rev 10)."),
        "definition": "docs/design/ppd-shadow-corpus.md",
        "artifact": dict(identity),
        "instance": {
            "instance_kind": instance.instance_kind,
            "qualified_at": instance.qualified_at,
            "governs_run": instance.governs_run,
            "staleness_bound_days": instance.staleness_bound_days,
            "aggregate_baselines": dict(instance.aggregate_baselines),
            "baselines_are": "declared during qualification, not measured here",
        },
        "isolation": {
            "installed_into_server_state": False,
            "snapshot_routing_enabled": False,
            "artifacts_downloaded": 0,
            "snapshot_written_to": False,
        },
        "limits": {
            "live_delay_seconds": limits.live_delay_seconds,
            "latency_repeats": limits.latency_repeats,
            "max_live_per_case": limits.max_live_per_case,
            "deadline_seconds": limits.deadline_seconds,
            "min_available_memory_bytes": limits.min_available_memory_bytes,
            "live_calls_made": live_calls,
        },
        "excluded": dict(excluded),
        "midnight": dict(midnight),
        "aborted": aborted,
        "cases_total": len(results),
        "cases_compared": len(compared),
        "live_errors": live_errors,
        "latency": {
            "snapshot_arm": latency,
            "per_case_ms": {k: latency_summary(v) for k, v in
                            sorted(per_case.items())},
        },
        "exit_criteria": criteria,
        "passed": (aborted is None
                   and all(c["passed"] for c in criteria.values())),
        "cases": results,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _default_cache_dir() -> str:
    from property_core.snapshot.bootstrap import DEFAULT_CACHE_DIR, SNAPSHOT_CACHE_ENV

    return os.getenv(SNAPSHOT_CACHE_ENV, DEFAULT_CACHE_DIR)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stage1_shadow",
        description=("Stage 1 shadow comparison, run out of band on the "
                     "deployed Machine. Off by default."))
    sub = parser.add_subparsers(dest="mode", required=True)

    q = sub.add_parser("qualify", help="read-only aggregate counts; emit a "
                                       "candidate Stage 1 Instance")
    q.add_argument("--cache-dir", default=None)
    q.add_argument("--out", required=True, type=Path)
    q.add_argument(
        "--substitutions", type=Path, default=None,
        help=("JSON file carrying a `substitutions` block, to RE-QUALIFY the "
              "artifact against substituted definitional geographies. Every "
              "measurement is then taken over those geographies, which is the "
              "only way a substituted Instance can carry evidence about the "
              "run it governs."))

    c = sub.add_parser("compare", help="execute the frozen corpus against both "
                                       "arms and write the Stage 1 report")
    c.add_argument("--cache-dir", default=None)
    c.add_argument("--instance", required=True, type=Path)
    c.add_argument("--report", required=True, type=Path)
    c.add_argument("--latency-repeats", type=int,
                   default=REQUIRED_LATENCY_REPEATS)
    c.add_argument("--max-live-per-case", type=int, default=1)
    c.add_argument("--live-delay-seconds", type=float, default=2.0)
    c.add_argument("--deadline-seconds", type=float, default=3600.0)
    c.add_argument("--health-url", default="http://127.0.0.1:8080/v1/health")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        require_enabled()
        cache_dir = Path(args.cache_dir or _default_cache_dir())
        materialized = open_materialized(cache_dir)
    except ComparisonRefused as exc:
        print(f"refused: {exc}")
        return 2

    try:
        if args.mode == "qualify":
            substitutions: dict[str, Any] = {}
            if args.substitutions is not None:
                try:
                    raw = json.loads(args.substitutions.read_text())
                except (OSError, ValueError) as exc:
                    print(f"refused: substitutions file unreadable: {exc}")
                    return 2
                if not isinstance(raw, dict):
                    # A list, a string or a bare number. `.get` on it raises
                    # AttributeError, which reached the operator as a traceback
                    # rather than a refusal.
                    print(f"refused: substitutions file must contain a JSON "
                          f"object, got {type(raw).__name__}")
                    return 2
                # A non-dict `substitutions` value needs no guard here:
                # `validate_substitutions` refuses anything that is not an
                # object, with a message naming the problem, and the refusal is
                # caught below. A second isinstance check would be unreachable.
                candidate_block = raw.get("substitutions", raw)
                try:
                    validate_substitutions(candidate_block)
                except InstanceRefused as exc:
                    print(f"refused: {exc}")
                    return 2
                substitutions = candidate_block
            out = qualify(materialized, substitutions=substitutions or None)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(out, indent=2, sort_keys=False))
            print(f"candidate instance written to {args.out}")
            # Non-zero on an unusable candidate. Printing a warning and exiting
            # 0 would let a scripted run treat "these baselines contradict the
            # relation they exist to establish" as success, and the refusal
            # would then surface much later, at load, after the Instance had
            # been authored and reviewed.
            failed = False
            if out["unqualified_placeholders"]:
                print(f"UNQUALIFIED placeholders: {out['unqualified_placeholders']}")
                failed = True
            if out["unqualified_definitional_cases"]:
                print("UNQUALIFIED definitional cases: "
                      f"{out['unqualified_definitional_cases']}")
                failed = True
            if not out["baselines_satisfy_their_relations"]:
                print(f"BASELINES UNUSABLE: {out['baselines_refusal']}")
                failed = True
            if out["requires_owner_adjudication"]:
                # Not a failure of the artifact, and not something this tool may
                # settle. Non-zero all the same: a candidate awaiting a
                # judgement is not a candidate ready to run.
                print("REQUIRES OWNER ADJUDICATION: "
                      f"{out['requires_owner_adjudication']}")
                failed = True
            return 1 if failed else 0

        try:
            instance = load_instance(args.instance, materialized)
        except InstanceRefused as exc:
            print(f"refused: {exc}")
            return 2

        limits = RunLimits(
            live_delay_seconds=args.live_delay_seconds,
            latency_repeats=args.latency_repeats,
            max_live_per_case=args.max_live_per_case,
            deadline_seconds=args.deadline_seconds,
            health_url=args.health_url,
        )
        report = run_compare(instance=instance, materialized=materialized,
                             limits=limits, report_path=args.report)
        print(f"report written to {args.report}")
        print(f"passed: {report['passed']}  aborted: {report['aborted']}")
        return 0 if report["passed"] else 1
    finally:
        materialized.adapter.close()


if __name__ == "__main__":
    raise SystemExit(main())
