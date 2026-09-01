"""Guards for the Stage 1 shadow comparator.

The comparator runs out of band on the deployed Machine, alongside a process
that is serving real requests, and produces the evidence a deployment gate is
decided on. Two families of property matter, and both are asserted here by
mutation -- breaking the mechanism and proving the test notices -- rather than
by reading the code:

**Safety.** Production keeps answering from the live source; the comparison is
off unless deliberately enabled; the scope is `comps` and nothing else; the run
is bounded; a failure in either arm is recorded rather than propagated; and the
tool never installs into, routes through, or writes to anything the server owns.

**Evidential honesty.** Every divergence is classified or counted as
unclassified; a comparison that shares no transaction id is a failure and never
a vacuous pass; and no id, address or price ever reaches a report.

Everything here runs against a synthetic parquet artifact built in `tmp_path`.
No Tigris, no production access, no network -- `conftest.py`'s autouse
`_no_network` fixture hard-fails sockets for the whole module.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

pytest.importorskip("duckdb")

from property_core.models.ppd import PPDTransaction  # noqa: E402
from property_core.provenance import TransportEvidence  # noqa: E402
from tools.ppd_snapshot import stage1_shadow as s1  # noqa: E402
from tools.ppd_snapshot.corpus import InstanceRefused, cases  # noqa: E402
from tests.snapshot.snapshot_fixtures import build_snapshot, row  # noqa: E402

REPO = Path(__file__).resolve().parents[2]

GEOGRAPHIES = {
    "S4_thin": "B5 6",
    "S5_dense": "B5 7",
    "S6_unit": "B5 7AA",
    "S7_type_weak": "B5 7",
    "S8_type_strong": "B5 6",
    "S11_provisional_empty": "B5 9",
    "S13_empty_unit": "B5 7AA",
}


def _rows() -> list[dict]:
    """Enough rows that the frozen cases have something to disagree about."""
    today = date.today()
    recent = (today - timedelta(days=120)).isoformat()
    older = (today - timedelta(days=400)).isoformat()
    rows = [
        row(f"T-B57-{i:03d}", "B5 7AA", recent, 200_000 + i,
            property_type="F") for i in range(30)
    ]
    rows += [row("T-B56-D", "B5 6QQ", older, 300_000, property_type="D"),
             row("T-B56-S", "B5 6QR", older, 310_000, property_type="S"),
             row("T-B56-T", "B5 6QS", older, 320_000, property_type="T"),
             row("T-B56-F", "B5 6QT", older, 330_000, property_type="F"),
             row("T-B50-A", "B50 4AA", older, 400_000),
             row("T-B57-CATB", "B5 7AB", recent, 999_000, ppd_category="B")]
    return rows


@pytest.fixture
def materialized(tmp_path):
    """A real materialized snapshot, opened exactly as the tool opens one."""
    build_snapshot(tmp_path, _rows(), version="v20260828T194003Z",
                   coverage_from="2016-01-01", coverage_to="2026-06-30",
                   provisional_from="2026-04-01")
    opened = s1.open_materialized(tmp_path)
    yield opened
    opened.adapter.close()


def _instance_dict(m) -> dict:
    return {
        "instance_kind": "stage1",
        "snapshot_version": m.version,
        "bundle_sha256": m.bundle_sha256,
        "geographies": dict(GEOGRAPHIES),
        "aggregate_baselines": {"S1_full": 100, "S3_full": 40, "S9_full": 55},
        "qualified_at": "2026-09-01",
        "qualification": {"S5_dense": {"rule": "dense", "measured_rows": 30}},
        "staleness_bound_days": 45,
        "governs_run": "stage-1-2026-09",
    }


@pytest.fixture
def instance(materialized, tmp_path):
    path = tmp_path / "instance.json"
    path.write_text(json.dumps(_instance_dict(materialized)))
    return s1.load_instance(path, materialized)


# ---------------------------------------------------------------------------
# Comparison is OFF by default
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", [None, "", "0", "false", "no", "nonsense", " "])
def test_the_comparison_refuses_unless_deliberately_enabled(value):
    """Anything unrecognised means off. A flag like this must fail CLOSED.

    Mutation: make `require_enabled` truthy-test the raw string instead of
    parsing it, and "nonsense" enables a production comparison run.
    """
    env = {} if value is None else {s1.SHADOW_COMPARE_ENABLED_ENV: value}
    with pytest.raises(s1.ComparisonRefused) as exc:
        s1.require_enabled(env)
    assert s1.SHADOW_COMPARE_ENABLED_ENV in str(exc.value)


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE"])
def test_the_comparison_runs_only_when_the_flag_parses_true(value):
    s1.require_enabled({s1.SHADOW_COMPARE_ENABLED_ENV: value})


def test_a_refused_invocation_opens_nothing_and_writes_nothing(tmp_path, monkeypatch):
    """The refusal must precede every side effect, not follow the first one."""
    monkeypatch.delenv(s1.SHADOW_COMPARE_ENABLED_ENV, raising=False)
    opened = []
    monkeypatch.setattr(s1, "open_materialized",
                        lambda *a, **k: opened.append(a) or pytest.fail("opened"))
    report = tmp_path / "report.json"
    code = s1.main(["compare", "--instance", str(tmp_path / "i.json"),
                    "--report", str(report), "--cache-dir", str(tmp_path)])
    assert code == 2
    assert not opened
    assert not report.exists()


# ---------------------------------------------------------------------------
# It observes what the server booted; it never materializes or mutates
# ---------------------------------------------------------------------------

def test_it_refuses_rather_than_materializing_its_own_snapshot(tmp_path):
    """A tool that would build its own artifact could measure a different one."""
    with pytest.raises(s1.ComparisonRefused) as exc:
        s1.open_materialized(tmp_path / "nothing-here")
    assert "never materializes one of its own" in str(exc.value)
    assert not (tmp_path / "nothing-here").exists()


def test_opening_the_snapshot_writes_nothing_into_it(tmp_path):
    """Read-only in the way that matters: the bytes on disk do not move."""
    build_snapshot(tmp_path, _rows(), version="v20260828T194003Z")
    directory = tmp_path / "snapshots" / "v20260828T194003Z"
    before = {p.relative_to(directory): (p.stat().st_size, p.stat().st_mtime_ns)
              for p in sorted(directory.rglob("*")) if p.is_file()}
    opened = s1.open_materialized(tmp_path)
    try:
        s1.qualify(opened)
    finally:
        opened.adapter.close()
    after = {p.relative_to(directory): (p.stat().st_size, p.stat().st_mtime_ns)
             for p in sorted(directory.rglob("*")) if p.is_file()}
    assert before == after, "qualification altered the materialized snapshot"


def test_it_never_installs_into_the_servers_process_state(materialized, instance,
                                                          tmp_path, monkeypatch):
    """The serving process owns `state`. This tool must not touch it.

    Mutation: add a `state.install(...)` anywhere in the run and this fails --
    which matters because an installed adapter plus the serving flag is exactly
    what routing production traffic to the snapshot would look like.
    """
    from property_core.snapshot import state

    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    _run(materialized, instance, tmp_path, monkeypatch, latency_repeats=1,
         stop_on_unclassified=False)
    assert state.installed_adapter() is None
    assert state.active_adapter() is None


def test_the_serving_flag_is_never_read_or_set(materialized, instance, tmp_path,
                                               monkeypatch):
    """`PPD_SNAPSHOT_ENABLED` stays absent throughout. Routing is not ours."""
    import os

    monkeypatch.delenv("PPD_SNAPSHOT_ENABLED", raising=False)
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    _run(materialized, instance, tmp_path, monkeypatch, latency_repeats=1,
         stop_on_unclassified=False)
    assert "PPD_SNAPSHOT_ENABLED" not in os.environ


def test_production_still_answers_from_live_while_the_comparator_runs(materialized):
    """The property the whole design turns on.

    An adapter is open in this process and the corpus is about to be run through
    it -- and a plain `PPDService()`, which is what every consumer constructs,
    must still route to the live source because the serving flag is off.
    """
    from property_core.ppd_service import PPDService

    assert PPDService()._active_adapter() is None
    assert PPDService(adapter=materialized.adapter)._active_adapter() is not None


# ---------------------------------------------------------------------------
# A controllable live arm
# ---------------------------------------------------------------------------

def _request_key(kwargs) -> tuple:
    """What distinguishes one frozen case from another on the wire.

    Keyed on the whole request, not the postcode: S6 and S13 share `B5 7AA` and
    differ only by `property_type`, so a postcode-keyed stub silently answers
    one case with the other's rows.
    """
    return (kwargs["postcode"], kwargs["search_level"], kwargs["months"],
            kwargs.get("property_type"), kwargs.get("transaction_category"))


class FakeLive:
    """A live arm whose answers, failures and latency the test chooses.

    The real live arm is HM Land Registry's SPARQL endpoint. Every property
    asserted below is about what the comparator *does* with an answer, so the
    answer is supplied rather than fetched -- and sockets are hard-failed for
    this module anyway.
    """

    def __init__(self, transactions=None, *, raises=None, per_shape=None):
        self.transactions = transactions if transactions is not None else []
        self.raises = raises
        self.per_shape = per_shape or {}
        self.calls: list[dict] = []

    def comps(self, **kwargs):
        from property_core.models.ppd import PPDCompsQuery, PPDCompsResponse
        from property_core.ppd_source import live_provenance

        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        rows = self.per_shape.get(_request_key(kwargs), self.transactions)
        return PPDCompsResponse(
            query=PPDCompsQuery(postcode=kwargs["postcode"],
                                months=kwargs["months"],
                                search_level=kwargs["search_level"]),
            count=len(rows), thin_market=len(rows) < 5, warnings=(),
            transactions=list(rows),
            provenance=live_provenance(
                evidence=TransportEvidence(raw_bindings_returned=len(rows),
                                           fetch_limit=50),
                sample_count=len(rows), sample_limit=50),
        )


def _run(materialized, instance, tmp_path, monkeypatch, *, live=None,
         latency_repeats=1, **limit_kwargs):
    monkeypatch.setattr(s1.time, "sleep", lambda *_: None)
    limits = s1.RunLimits(live_delay_seconds=0.0,
                          latency_repeats=latency_repeats, **limit_kwargs)
    return s1.run_compare(
        instance=instance, materialized=materialized, limits=limits,
        report_path=tmp_path / "report.json",
        live_service=live if live is not None else FakeLive(),
        snapshot_service=None)


# ---------------------------------------------------------------------------
# Scope: comps only
# ---------------------------------------------------------------------------

def test_the_only_service_method_the_comparator_calls_is_comps():
    """Stage 1 is `comps`-only. Nothing may quietly widen it.

    Mutation: add a `search_transactions(` or `analyze_blocks(` call to the
    module and this fails. Scope creep here would mean Stage 1 evidence about
    a surface the frozen corpus never agreed to cover.
    """
    source = (REPO / "tools" / "ppd_snapshot" / "stage1_shadow.py").read_text()
    for forbidden in ("search_transactions(", "analyze_blocks(", "get_transaction_record(",
                      "calculate_yield(", "analyze_rentals(", "PropertyReportService"):
        assert forbidden not in source, (
            f"the Stage 1 comparator reaches beyond comps: {forbidden!r}")
    assert ".comps(" in source


def test_every_frozen_case_is_a_comps_shape():
    corpus = cases(GEOGRAPHIES)
    assert len(corpus) == 13
    assert {c.shape for c in corpus} == {
        "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S11", "S12",
        "S13", "S14"}


# ---------------------------------------------------------------------------
# Bounded work
# ---------------------------------------------------------------------------

def test_the_run_is_sequential_with_no_concurrency_of_its_own():
    """One process, one adapter, one query at a time.

    The comparator shares a 2 GB Machine with the process that is serving. A
    thread pool or an async gather here is how a diagnostic run turns into an
    outage, so the absence of one is asserted rather than assumed.
    """
    source = (REPO / "tools" / "ppd_snapshot" / "stage1_shadow.py").read_text()
    for forbidden in ("threading", "ThreadPoolExecutor", "ProcessPoolExecutor",
                      "asyncio", "anyio", "multiprocessing", "concurrent.futures"):
        assert forbidden not in source, (
            f"the comparator introduces concurrency: {forbidden!r}")


def test_live_calls_are_capped_at_one_per_case(materialized, instance, tmp_path,
                                               monkeypatch):
    """The live source is HMLR's. Thirteen cases means thirteen calls, once.

    Mutation: move the live call inside the latency loop and this count jumps
    from 13 to 13 * repeats.
    """
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    live = FakeLive()
    report = _run(materialized, instance, tmp_path, monkeypatch, live=live,
                  latency_repeats=5, stop_on_unclassified=False)
    assert len(live.calls) == 13
    assert report["limits"]["live_calls_made"] == 13


def test_the_latency_pass_makes_no_live_call_at_all(materialized, instance,
                                                    tmp_path, monkeypatch):
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    live = FakeLive()
    report = _run(materialized, instance, tmp_path, monkeypatch, live=live,
                  latency_repeats=4, stop_on_unclassified=False)
    # 13 correctness observations, and 13 * 4 latency observations on top.
    assert report["latency"]["snapshot_arm"]["n"] == 13 * 4
    assert len(live.calls) == 13


def test_the_deadline_stops_the_run_and_still_writes_a_report(
        materialized, instance, tmp_path, monkeypatch):
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    report = _run(materialized, instance, tmp_path, monkeypatch,
                  latency_repeats=1, deadline_seconds=-1.0,
                  stop_on_unclassified=False)
    assert report["aborted"] and "deadline" in report["aborted"]
    assert report["passed"] is False
    assert (tmp_path / "report.json").is_file()


def test_a_memory_floor_breach_stops_the_run(materialized, instance, tmp_path,
                                             monkeypatch):
    """A Machine under memory pressure is a reason to stop, not to push on."""
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    monkeypatch.setattr(s1, "available_memory_bytes", lambda *a, **k: 1024)
    report = _run(materialized, instance, tmp_path, monkeypatch, latency_repeats=1,
                  stop_on_unclassified=False)
    assert report["aborted"] and "available memory" in report["aborted"]
    assert report["excluded"]["memory"] >= 1


def test_an_unhealthy_application_stops_the_run(materialized, instance, tmp_path,
                                                monkeypatch):
    """The serving app is the priority; the diagnostic yields to it."""
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (False, "503"))
    report = _run(materialized, instance, tmp_path, monkeypatch, latency_repeats=1,
                  stop_on_unclassified=False)
    assert report["aborted"] and "health" in report["aborted"]
    assert report["excluded"]["health"] >= 1


# ---------------------------------------------------------------------------
# Failure isolation
# ---------------------------------------------------------------------------

def test_a_failing_live_arm_is_recorded_and_the_run_continues(
        materialized, instance, tmp_path, monkeypatch):
    """A live failure is a fact about the run, not the end of it.

    Mutation: let the exception escape the per-arm `except` and the run dies
    with no report -- which is the outcome that leaves a gate undecidable.
    """
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    live = FakeLive(raises=RuntimeError("upstream exploded"))
    report = _run(materialized, instance, tmp_path, monkeypatch, live=live,
                  latency_repeats=1, stop_on_unclassified=False)
    assert report["aborted"] is None
    assert len(report["live_errors"]) == 13
    assert "upstream exploded" in report["live_errors"][0]["error"]
    assert report["cases_total"] == 13


def test_a_failing_snapshot_arm_is_recorded_and_fails_the_gate(
        materialized, instance, tmp_path, monkeypatch):
    """Recorded, not propagated -- and it must still fail the exit criterion.

    "Zero snapshot errors on the frozen corpus" is only meaningful if an error
    that was caught still counts. Swallowing it into a green report would be
    the worst of both.
    """
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))

    class Exploding:
        def comps(self, **kwargs):
            raise RuntimeError("snapshot query failed")

    report = s1.run_compare(
        instance=instance, materialized=materialized,
        limits=s1.RunLimits(live_delay_seconds=0.0, latency_repeats=1,
                            stop_on_unclassified=False),
        report_path=tmp_path / "report.json",
        live_service=FakeLive(), snapshot_service=Exploding())
    assert report["aborted"] is None
    assert report["exit_criteria"]["zero_snapshot_errors"]["passed"] is False
    assert report["passed"] is False


# ---------------------------------------------------------------------------
# Complete divergence recording
# ---------------------------------------------------------------------------

def test_an_unexplainable_divergence_is_counted_unclassified_not_excused():
    """The class that must never be quietly absorbed by another.

    A row present on one side only, outside the provisional tail, with no
    truncation evidence, has no explanation this comparison can offer. The
    taxonomy says an unclassified divergence blocks exit -- so it must be
    counted, not rounded into `live_truncation_or_ordering`.
    """
    result = s1.classify(
        only_live_months={"2019-05": 3}, only_snapshot_months={},
        mismatch_months={}, provisional_from="2026-04-01",
        live_saturated=False, snapshot_saturated=False,
        live_truncation_evidenced=False)
    assert result["unclassified"] == 3
    assert result["live_truncation_or_ordering"] == 0
    assert result["provisional_tail_lag"] == 0


def test_truncation_is_only_claimed_on_evidence():
    """Definition section 7: class 3 must be evidenced, never assumed.

    Mutation: let `classify` infer truncation from "the snapshot returned more"
    and the first case flips from unclassified to explained -- turning an open
    question into a fake answer.
    """
    without = s1.classify(
        only_live_months={"2019-05": 2}, only_snapshot_months={},
        mismatch_months={}, provisional_from="2026-04-01",
        live_saturated=False, snapshot_saturated=False,
        live_truncation_evidenced=False)
    with_evidence = s1.classify(
        only_live_months={"2019-05": 2}, only_snapshot_months={},
        mismatch_months={}, provisional_from="2026-04-01",
        live_saturated=False, snapshot_saturated=False,
        live_truncation_evidenced=True)
    assert without["unclassified"] == 2 and without["live_truncation_or_ordering"] == 0
    assert with_evidence["unclassified"] == 0
    assert with_evidence["live_truncation_or_ordering"] == 2


def test_a_provisional_tail_row_is_classified_as_lag():
    result = s1.classify(
        only_live_months={"2026-05": 4}, only_snapshot_months={},
        mismatch_months={}, provisional_from="2026-04-01",
        live_saturated=False, snapshot_saturated=False,
        live_truncation_evidenced=False)
    assert result["provisional_tail_lag"] == 4
    assert result["unclassified"] == 0


def test_a_revision_outside_the_provisional_tail_needs_operator_confirmation():
    """Class 2 cannot be evidenced from these two sources, and says so.

    Confirming an A/C/D revision needs the monthly change records published
    after the build. Asserting it from a field mismatch alone would be a guess
    wearing a taxonomy label.
    """
    result = s1.classify(
        only_live_months={}, only_snapshot_months={},
        mismatch_months={"2019-05": 2}, provisional_from="2026-04-01",
        live_saturated=False, snapshot_saturated=False,
        live_truncation_evidenced=False)
    assert result["later_acd_revision"] == 2
    assert result["operator_confirmation_required"] == 2


def test_an_unclassified_divergence_stops_the_run_by_default(
        materialized, instance, tmp_path, monkeypatch):
    """The default is to stop and investigate, not to accumulate mysteries."""
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    report = _run(materialized, instance, tmp_path, monkeypatch, latency_repeats=1)
    assert report["aborted"] and "unclassified divergence" in report["aborted"]
    assert report["passed"] is False


# ---------------------------------------------------------------------------
# The vacuous-pass guard
# ---------------------------------------------------------------------------

def test_sharing_no_transaction_id_is_a_failure_not_a_pass(
        materialized, instance, tmp_path, monkeypatch):
    """The single way this gate could go green while proving nothing.

    The live path takes `transactionId` straight from SPARQL; the snapshot
    strips `{}` from the CSV id. If those spellings ever differ, no id is
    shared, "100% equality on shared ids" is vacuously true, and a gate passes
    having compared zero rows. So an empty intersection with rows on both sides
    is recorded as a failure.

    Mutation: drop the `empty_id_intersection_with_rows_on_both_sides` term
    from the criterion and this test goes green with nothing compared.
    """
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    disjoint = [PPDTransaction(transaction_id="UUID-STYLE-LIVE-ONLY",
                               postcode="B5 7AA", date="2026-05-01", price=1)]
    live = FakeLive(transactions=disjoint)
    report = _run(materialized, instance, tmp_path, monkeypatch, live=live,
                  latency_repeats=1, stop_on_unclassified=False)
    criterion = report["exit_criteria"]["field_equality_on_shared_ids"]
    assert criterion["passed"] is False
    assert criterion["vacuous_comparison_shapes"], (
        "an empty id intersection with rows on both sides was not flagged")
    assert report["passed"] is False


def test_a_shared_id_with_a_differing_field_fails_the_equality_criterion(
        materialized, instance, tmp_path, monkeypatch):
    """The criterion it is actually there to test."""
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    # Same id as the snapshot holds, different price.
    live = FakeLive(transactions=[
        PPDTransaction(transaction_id="T-B57-000", postcode="B5 7AA",
                       date=(date.today() - timedelta(days=120)).isoformat(),
                       price=999_999, property_type="F")])
    report = _run(materialized, instance, tmp_path, monkeypatch, live=live,
                  latency_repeats=1, stop_on_unclassified=False)
    criterion = report["exit_criteria"]["field_equality_on_shared_ids"]
    assert criterion["mismatch_rows"] >= 1
    assert criterion["passed"] is False


# ---------------------------------------------------------------------------
# Nothing identifying is ever persisted
# ---------------------------------------------------------------------------

#: Every key the report is allowed to emit. Dynamic key spaces -- month
#: buckets, shape names and compared-field names -- are subtracted before the
#: comparison; see `_static_keys`.
#:
#: This is the assertion that actually protects the payload. A substring search
#: over the serialised JSON cannot: it fires on "400000" inside a latency float
#: while missing a genuinely new `transaction_ids` field whose values happen not
#: to collide with the fixture. A key that can carry a row cannot appear here
#: without someone adding it to this list on purpose.
ALLOWED_KEYS = {
    # document
    "kind", "stage_1_evidence", "latency_sample_kind", "not_organic_traffic",
    "definition", "artifact", "instance", "isolation", "limits", "excluded",
    "midnight", "aborted", "cases_total", "cases_compared", "live_errors",
    "latency", "exit_criteria", "passed", "cases", "note", "criterion",
    # artifact identity
    "snapshot_version", "bundle_sha256", "coverage_from", "coverage_to",
    "provisional_from", "comparator_version",
    # instance
    "instance_kind", "qualified_at", "governs_run", "staleness_bound_days",
    "aggregate_baselines", "baselines_are", "S1_full", "S3_full", "S9_full",
    # isolation / limits / counters
    "installed_into_server_state", "snapshot_routing_enabled",
    "artifacts_downloaded", "snapshot_written_to", "live_delay_seconds",
    "latency_repeats", "max_live_per_case", "deadline_seconds",
    "min_available_memory_bytes", "live_calls_made", "health", "memory",
    "retries", "unrecoverable", "pair_date_mismatches",
    # per case
    "shape", "intent", "request", "wire", "effective", "snapshot", "live",
    "snapshot_error", "live_error", "snapshot_invariants", "diff",
    "classification", "snapshot_false_empty", "live_truncation_evidenced",
    "empty_id_intersection_with_rows_on_both_sides",
    # request echo -- the geography ASKED FOR, never one returned
    "postcode", "search_level", "months", "limit", "transaction_category",
    "filter_outliers", "auto_escalate", "enrich_epc", "property_type", "address",
    # an arm: aggregates, geography membership and provenance only
    "count", "latency_ms", "thin_market", "outcodes_returned",
    "sectors_returned", "warning_classes", "saturated_at_limit",
    "returned_date_from", "returned_date_to", "source", "observed_at",
    "derived_from_date", "resolved_to_date", "recent_period_provisional",
    "sample_complete", "transport_evidence", "raw_bindings_returned",
    "fetch_limit", "source_exhausted",
    # invariants
    "coverage_clamp_warning_present", "sample_complete_is_false",
    "completeness_basis_is_null", "answered_by_snapshot", "provisional_flagged",
    "geography_isolation", "truncated_at_limit", "thin_market_flagged",
    "empty_result", "expected_empty",
    # diff -- cardinalities, histograms and tallies
    "only_live", "only_snapshot", "shared", "by_month", "count_delta",
    "field_mismatches", "field_mismatch_rows", "field_mismatch_by_month",
    "compared_fields",
    # classification
    "provisional_tail_lag", "later_acd_revision", "live_truncation_or_ordering",
    "unclassified", "operator_confirmation_required", "truncation_evidence",
    "live_raw_bindings_reached_fetch_limit", "context_not_evidence",
    "live_page_saturated", "snapshot_page_saturated",
    # verdict
    "all_thirteen_cases_compared", "corpus_invariants_hold",
    "zero_unexplained_false_empties", "zero_geography_contamination",
    "field_equality_on_shared_ids", "every_divergence_classified",
    "no_unconfirmed_classifications", "zero_snapshot_errors",
    "p95_under_one_second", "cases_recorded", "required",
    "cases_missing_snapshot_arm", "cases_missing_live_arm",
    "cases_never_reached", "snapshot_errors", "assertions_checked", "failures",
    "failed", "false_empty_shapes", "findings", "errors", "mismatch_rows",
    # a contamination finding: which arm, and the outcodes it strayed into.
    # Outcode granularity only -- never a unit postcode, never a row.
    "arm", "unexpected_outcodes",
    "vacuous_comparison_shapes", "verdict", "n", "p95_ms",
    "required_observations", "required_repeats_per_case",
    "cases_short_of_the_required_repeats",
    # latency
    "snapshot_arm", "per_case_ms", "p50_ms", "p99_ms", "max_ms", "method",
}

SHAPE_NAMES = {c.shape for c in cases(GEOGRAPHIES)}
#: Field names may legitimately appear as KEYS of `field_mismatches` and as
#: VALUES of `compared_fields`. Naming which field differed is not disclosing
#: what it differed to.
FIELD_NAMES = set(s1.COMPARED_FIELDS)
MONTH = __import__("re").compile(r"^\d{4}-\d{2}$")


def _scalars(node, path="$"):
    """Every scalar in the document, with the path it was reached by."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _scalars(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _scalars(value, f"{path}[{index}]")
    else:
        yield path, node


def _static_keys(node):
    """Keys, minus the dynamic key spaces (months, shapes, field names)."""
    found = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if not (MONTH.match(str(key)) or key in SHAPE_NAMES
                    or key in FIELD_NAMES):
                found.add(key)
            found |= _static_keys(value)
    elif isinstance(node, list):
        for value in node:
            found |= _static_keys(value)
    return found


@pytest.fixture
def report_with_leaky_fixture_data(materialized, instance, tmp_path, monkeypatch):
    """A completed report over rows carrying ids, streets, towns and prices."""
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    live = FakeLive(transactions=[
        PPDTransaction(transaction_id="T-B57-A", postcode="B5 7AA",
                       date="2026-05-01", price=210_000, street="HIGH STREET",
                       town="BIRMINGHAM", paon="1", saon="FLAT 2")])
    _run(materialized, instance, tmp_path, monkeypatch, live=live,
         latency_repeats=1, stop_on_unclassified=False)
    return json.loads((tmp_path / "report.json").read_text())


def test_the_report_schema_admits_no_field_that_could_carry_a_row(
        report_with_leaky_fixture_data):
    """Structural, not textual: no unreviewed key may appear at all.

    Mutation: add `"only_live_ids": sorted(only_live)` to the diff and this
    fails on the new key -- whether or not its values happen to collide with
    anything a substring search was looking for.
    """
    unexpected = _static_keys(report_with_leaky_fixture_data) - ALLOWED_KEYS
    assert not unexpected, (
        f"the report emits un-reviewed key(s) {sorted(unexpected)}; every field "
        f"capable of carrying transaction data must be added deliberately")


def test_no_report_value_equals_a_transaction_identifier(
        report_with_leaky_fixture_data):
    """Exact equality against the fixture's identifying values.

    Equality, never substring -- that distinction is the whole point. A latency
    of 1.400000 ms contains the digits of a 400000 price and leaks nothing; a
    value that IS "T-B57-A" leaks a transaction.
    """
    identifying = {"T-B57-A", "T-B57-000", "T-B50-A", "T-B56-D",
                   "HIGH STREET", "BIRMINGHAM", "WEST MIDLANDS", "FLAT 2"}
    for path, value in _scalars(report_with_leaky_fixture_data):
        if isinstance(value, str):
            assert value not in identifying, f"{path} leaked {value!r}"


def test_no_price_reaches_the_report_as_a_value(report_with_leaky_fixture_data):
    """Prices are compared in memory and never recorded.

    Restricted to values inside `cases`, and excluding measured timings, so a
    latency or a byte count can never be mistaken for a sale price -- the
    false positive that failed CI on the previous text-matching version.
    """
    prices = {210_000, 999_000, 400_000, 300_000, 310_000, 320_000, 330_000}
    prices |= {200_000 + n for n in range(30)}
    for path, value in _scalars(report_with_leaky_fixture_data["cases"], "$.cases"):
        if path.endswith("latency_ms"):
            continue
        assert value not in prices, f"{path} leaked the price {value!r}"


def test_a_latency_float_sharing_digits_with_a_price_is_not_treated_as_a_leak():
    """Regression: the exact false positive that failed CI on PR #51.

    `"latency_ms": 1.400000000000001` made a substring search for "400000"
    fire, and the test passed or failed on timing noise. A structural check
    cannot express that mistake.
    """
    document = {"cases": [{"snapshot": {"latency_ms": 1.400000000000001,
                                        "count": 3}}]}
    values = [v for path, v in _scalars(document["cases"], "$.cases")
              if not path.endswith("latency_ms")]
    assert 400_000 not in values
    assert all(isinstance(v, (int, float, str, bool)) or v is None for v in values)


def test_field_names_may_appear_but_only_as_names(report_with_leaky_fixture_data):
    """`field_mismatches` names which field differed; that is not disclosure.

    The distinction a key allowlist has to get right: "price" as a KEY of the
    mismatch tally is a field name, while "price" carrying 210000 would be the
    sale. The first is required evidence, the second is forbidden.
    """
    for case in report_with_leaky_fixture_data["cases"]:
        tally = case.get("diff", {}).get("field_mismatches", {})
        assert set(tally) <= set(s1.COMPARED_FIELDS)
        assert all(isinstance(v, int) for v in tally.values())


def test_a_month_histogram_is_the_finest_granularity_recorded():
    """Month, not date: enough to answer "is this in the provisional tail?"."""
    rows = [PPDTransaction(transaction_id="A", date="2026-05-14", price=1),
            PPDTransaction(transaction_id="B", date="2026-05-30", price=2),
            PPDTransaction(transaction_id="C", date="2026-06-01", price=3)]
    assert s1._by_month(rows, {"A", "B", "C"}) == {"2026-05": 2, "2026-06": 1}


def test_field_values_never_leave_the_comparison():
    """The tally names the field that differed, never what it differed to."""
    live = [PPDTransaction(transaction_id="X", price=100, postcode="B5 7AA",
                           date="2026-05-01")]
    snap = [PPDTransaction(transaction_id="X", price=200, postcode="B5 7AA",
                           date="2026-05-01")]
    tally, months, rows = s1._field_mismatches(live, snap, {"X"})
    assert tally == {"price": 1}
    assert months == {"2026-05": 1}
    assert rows == 1
    assert "100" not in json.dumps(tally) and "200" not in json.dumps(tally)


# ---------------------------------------------------------------------------
# Latency: nearest rank, exactly
# ---------------------------------------------------------------------------

def test_nearest_rank_is_an_observed_value_not_an_interpolation():
    """A gate should not be decided by a latency no request ever took."""
    values = [float(n) for n in range(1, 101)]  # 1..100
    assert s1.nearest_rank(values, 95) == 95.0
    assert s1.nearest_rank(values, 50) == 50.0
    assert s1.nearest_rank(values, 99) == 99.0
    assert s1.nearest_rank(values, 100) == 100.0


def test_nearest_rank_at_the_stage_1_sample_size():
    """390 observations: 13 frozen cases x 30 repetitions. Rank 371, index 370."""
    values = [float(n) for n in range(390)]
    assert s1.nearest_rank(values, 95) == 370.0


def test_nearest_rank_on_an_empty_sample_is_unknown_not_zero():
    """`0` and "no observations" are different answers."""
    assert s1.nearest_rank([], 95) is None
    assert s1.latency_summary([])["p95_ms"] is None


def test_the_p95_criterion_fails_when_there_is_no_sample():
    """No latency sample cannot pass a latency gate."""
    values: list[float] = []
    summary = s1.latency_summary(values)
    assert summary["n"] == 0
    assert summary["p95_ms"] is None


def test_the_report_labels_its_latency_as_the_corpus_mix_not_organic_traffic(
        instance):
    """Rev 10's concession, carried in the evidence itself.

    A report read six months later must say what its percentile was measured
    over. Without this the number is indistinguishable from an organic-traffic
    p95, which is exactly the claim rev 10 refused to make.
    """
    report = s1._build_report(
        instance=instance, identity={}, limits=s1.RunLimits(), results=[],
        latency_ms=[1.0], per_case={}, snapshot_errors=[], live_errors=[],
        contamination=[], excluded={},
        midnight={"retries": 0, "unrecoverable": False, "pair_date_mismatches": 0},
        corpus=cases(GEOGRAPHIES), aborted=None, live_calls=0)
    assert report["latency_sample_kind"] == "deployed_machine_frozen_corpus"
    assert "not a sample of organic traffic" in report["not_organic_traffic"]


# ---------------------------------------------------------------------------
# The Instance binds to the artifact actually on this Machine
# ---------------------------------------------------------------------------

def _write(tmp_path, materialized, **overrides):
    raw = _instance_dict(materialized)
    raw.update(overrides)
    path = tmp_path / "instance.json"
    path.write_text(json.dumps(raw))
    return path


def test_a_rehearsal_instance_cannot_be_run_as_stage_1(materialized, tmp_path):
    """The one substitution the Definition names, refused by kind.

    A rehearsal has no live arm and runs on a workstation. Letting one through
    here is how a correctness exercise gets filed as Stage 1 evidence.
    """
    path = _write(tmp_path, materialized, instance_kind="rehearsal")
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert "must not be run as Stage 1" in str(exc.value)


def test_an_instance_describing_another_artifact_is_refused(materialized, tmp_path):
    """Binding, not just validity. Otherwise the provenance is a fiction."""
    path = _write(tmp_path, materialized, bundle_sha256="a" * 64)
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert "different artifact" in str(exc.value)


def test_an_instance_naming_another_version_is_refused(materialized, tmp_path):
    path = _write(tmp_path, materialized, snapshot_version="v20200101T000000Z")
    with pytest.raises(InstanceRefused):
        s1.load_instance(path, materialized)


@pytest.mark.parametrize("baselines", [
    {"S1_full": 40, "S3_full": 40, "S9_full": 55},   # S3 not a STRICT subset
    {"S1_full": 100, "S3_full": 40, "S9_full": 40},  # category B cannot shrink
    {"S1_full": 100, "S3_full": 40, "S9_full": 30},
])
def test_baselines_contradicting_what_they_qualify_are_refused(
        materialized, tmp_path, baselines):
    """A baseline set that contradicts its own relation qualifies nothing.

    Worse than absent: it would look like evidence. The strict-subset rule in
    particular -- equal counts would say the sector is the whole district.
    """
    path = _write(tmp_path, materialized, aggregate_baselines=baselines)
    with pytest.raises(InstanceRefused):
        s1.load_instance(path, materialized)


def test_an_instance_that_does_not_say_how_it_qualified_is_refused(
        materialized, tmp_path):
    path = _write(tmp_path, materialized, qualification={})
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert "qualified nothing" in str(exc.value) or "qualifies nothing" in str(exc.value)


def test_unknown_instance_keys_are_refused_not_ignored(materialized, tmp_path):
    """A typo in an Instance is a silently different run."""
    path = _write(tmp_path, materialized, sample_rate=0.5)
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert "unknown key" in str(exc.value)


# ---------------------------------------------------------------------------
# qualify
# ---------------------------------------------------------------------------

def test_qualify_measures_the_baselines_and_emits_a_candidate(materialized):
    """Read-only aggregate counts, bound to the artifact, marked as candidate."""
    out = s1.qualify(materialized)
    assert out["kind"] == "stage1_qualification_candidate"
    assert out["is_instance"] is False
    candidate = out["candidate_instance"]
    assert candidate["snapshot_version"] == materialized.version
    assert candidate["bundle_sha256"] == materialized.bundle_sha256
    assert set(candidate["aggregate_baselines"]) == {"S1_full", "S3_full", "S9_full"}
    assert candidate["instance_kind"] == "stage1"


def test_qualify_makes_no_live_call_and_downloads_nothing(materialized):
    """Sockets are hard-failed for this module; qualification must not need one."""
    out = s1.qualify(materialized)
    assert out["candidate_instance"]["qualified_at"]


def test_qualify_reports_placeholders_it_could_not_qualify(materialized):
    """Silence about an unqualified placeholder would produce an unusable
    Instance that looked complete."""
    out = s1.qualify(materialized)
    assert isinstance(out["unqualified_placeholders"], list)
    qualified = set(out["candidate_instance"]["geographies"])
    unqualified = set(out["unqualified_placeholders"])
    assert not (qualified & unqualified)


def test_qualify_never_selects_a_sparse_unit_postcode(materialized):
    """The Definition requires S6 to be aggregate-dense, "so not individually
    identifying". Made executable so qualification cannot pick a postcode that
    names one household's sale history.
    """
    out = s1.qualify(materialized)
    geo = out["candidate_instance"]["geographies"]
    if "S6_unit" in geo:
        measured = out["candidate_instance"]["qualification"]["S6_unit"]
        assert measured["measured_rows"] >= s1.MIN_UNIT_POSTCODE_ROWS


def test_qualify_output_carries_no_ids_prices_or_addresses(materialized):
    body = json.dumps(s1.qualify(materialized))
    for forbidden in ("T-B57", "HIGH STREET", "transaction_id", "200000"):
        assert forbidden not in body, f"qualification leaked {forbidden!r}"


def test_qualification_is_deterministic_for_one_artifact(materialized):
    """An Instance nobody can reproduce is not qualification evidence."""
    today = date(2026, 9, 1)
    first = s1.qualify(materialized, today=today)["candidate_instance"]
    second = s1.qualify(materialized, today=today)["candidate_instance"]
    assert first == second


# ---------------------------------------------------------------------------
# The adapter internals qualification relies on
# ---------------------------------------------------------------------------

def test_the_adapter_names_qualification_depends_on_still_exist():
    """`qualify` counts over the adapter's own validated view rather than
    building a second one. That reuse is only safe while these two names hold,
    so a rename fails here loudly instead of silently counting something else.
    """
    from property_core.snapshot.adapter import VIEW, SnapshotAdapter

    assert VIEW == "ppd"
    assert callable(getattr(SnapshotAdapter, "_execute", None))


# ---------------------------------------------------------------------------
# Image delivery
# ---------------------------------------------------------------------------

def test_the_api_image_carries_the_comparator_and_its_corpus():
    """Both files, or the comparator cannot import its own frozen corpus.

    A repository-config lint, and labelled as one: it proves what the Dockerfile
    says, never that the wheel resolved or the module imports on that platform.
    `tests/snapshot/image_smoke.py stage1` is what actually invokes it in the
    built image.
    """
    dockerfile = (REPO / "Dockerfile").read_text()
    for path in ("tools/ppd_snapshot/corpus.py",
                 "tools/ppd_snapshot/stage1_shadow.py",
                 "tools/ppd_snapshot/__init__.py"):
        assert path in dockerfile, f"the API image does not copy {path}"


def test_propertydata_does_not_carry_the_comparator():
    """Stage 1 is `property-shared` only; `propertydata` stays untouched."""
    app_dockerfile = (REPO / "Dockerfile.app").read_text()
    assert "stage1_shadow" not in app_dockerfile
    assert "ppd_snapshot" not in app_dockerfile


def test_the_comparator_is_not_wired_into_the_serving_entrypoint():
    """Never imported by the app, never in CMD. Out of band means out of band.

    Mutation: import it from `app/` and this fails -- which matters because an
    import is all it would take for rollout tooling to start loading inside the
    process that serves requests.
    """
    dockerfile = (REPO / "Dockerfile").read_text()
    cmd = [line for line in dockerfile.splitlines() if line.startswith("CMD")]
    assert cmd and "stage1_shadow" not in cmd[0]
    for package in ("app", "property_core", "property_app", "property_cli"):
        for source in (REPO / package).rglob("*.py"):
            assert "stage1_shadow" not in source.read_text(), (
                f"{source} imports the Stage 1 comparator into shipped code")


def test_qualify_says_when_the_measured_baselines_would_be_refused(materialized):
    """An operator must learn this while choosing geographies, not at load time.

    The baselines are measured over the definitional `B5` / `B5 4` geographies.
    If those do not satisfy the strict-subset and category-B relations on this
    artifact, the Instance built from them will be refused -- and the Definition's
    remedy is a substituted geography with recorded justification, which is an
    authoring decision this tool must surface rather than make.
    """
    out = s1.qualify(materialized)
    assert "baselines_satisfy_their_relations" in out
    if not out["baselines_satisfy_their_relations"]:
        assert out["baselines_refusal"], (
            "qualification reported unusable baselines without saying why")
    else:
        assert out["baselines_refusal"] is None


def test_qualified_baselines_that_pass_here_are_accepted_by_the_loader(
        tmp_path, monkeypatch):
    """The two sides of the same rule must agree.

    Mutation: loosen `validate_baselines` on one side only and a candidate that
    qualification called usable is refused at load, or vice versa.
    """
    rows = [row(f"T-B54-{i:03d}", "B5 4AA", "2026-05-04", 200_000 + i)
            for i in range(20)]
    rows += [row(f"T-B57-{i:03d}", "B5 7AA", "2026-05-04", 200_000 + i)
             for i in range(20)]
    rows += [row("T-B54-CATB", "B5 4AB", "2026-05-04", 900_000, ppd_category="B")]
    build_snapshot(tmp_path, rows, version="v20260828T194003Z")
    opened = s1.open_materialized(tmp_path)
    try:
        out = s1.qualify(opened, today=date(2026, 6, 15))
        assert out["baselines_satisfy_their_relations"] is True
        from tools.ppd_snapshot.corpus import validate_baselines
        validate_baselines(out["candidate_instance"]["aggregate_baselines"])
    finally:
        opened.adapter.close()


# ---------------------------------------------------------------------------
# Return-live: the flag gate, tested one layer at a time
# ---------------------------------------------------------------------------
#
# `PPD_SNAPSHOT_ENABLED` is checked twice on the way to a routable adapter --
# in `ppd_source.active_adapter()` before `state` is even imported, and again
# inside `state.active_adapter()`. `ppd_source`'s docstring says that redundancy
# is deliberate, "because either call site alone must fail closed".
#
# That is exactly what makes an end-to-end assertion a weak guard here: remove
# either check on its own and the other still returns None, so the behaviour
# never changes and no behavioural test can notice. The risk is erosion -- one
# layer removed now, the other later. So each layer is tested with the other
# one deliberately made permissive, and each test fails if its own layer goes.

def test_the_routing_layer_fails_closed_even_if_state_were_permissive(monkeypatch):
    """`ppd_source.active_adapter()` must refuse before it consults `state`.

    Mutation: delete its `ppd_snapshot_enabled()` check and this fails, even
    though the process-state check downstream would still have caught it.
    """
    from property_core import ppd_source
    from property_core.snapshot import state

    monkeypatch.delenv("PPD_SNAPSHOT_ENABLED", raising=False)
    monkeypatch.setattr(state, "active_adapter", lambda: "SENTINEL-ADAPTER")
    assert ppd_source.active_adapter() is None


def test_process_state_fails_closed_even_if_the_routing_layer_were_permissive(
        materialized, monkeypatch):
    """`state.active_adapter()` must refuse independently of its caller.

    Mutation: delete its `ppd_snapshot_enabled()` check and this fails. An
    installed adapter must not outlive the flag that authorised routing to it.
    """
    from property_core.snapshot import state

    monkeypatch.delenv("PPD_SNAPSHOT_ENABLED", raising=False)
    state.install(materialized.adapter, None)
    try:
        assert state.installed_adapter() is not None
        assert state.active_adapter() is None
    finally:
        # Hand back an empty state without closing an adapter we do not own.
        state.install(None, None)


# ---------------------------------------------------------------------------
# End-to-end: every one of these must make the TOP-LEVEL verdict false
# ---------------------------------------------------------------------------
#
# Asserting a helper returns the right number is not the same as asserting the
# report says "failed". The wiring between the two is where a gate silently
# goes green: a criterion computed correctly and then not consulted, or
# consulted and then overridden. Each test below reads `report["passed"]`.

def _full_run(materialized, instance, tmp_path, monkeypatch, *, live=None,
              repeats=s1.REQUIRED_LATENCY_REPEATS, snapshot_service=None,
              **limit_kwargs):
    """A run sized as the real gate defines it: 13 cases x 30 repetitions."""
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    monkeypatch.setattr(s1.time, "sleep", lambda *_: None)
    limits = s1.RunLimits(live_delay_seconds=0.0, latency_repeats=repeats,
                          stop_on_unclassified=False, **limit_kwargs)
    return s1.run_compare(
        instance=instance, materialized=materialized, limits=limits,
        report_path=tmp_path / "report.json",
        live_service=live if live is not None else FakeLive(),
        snapshot_service=snapshot_service)


@pytest.fixture
def agreeing_live(materialized):
    """A live arm that returns exactly what the snapshot holds, per case.

    The only configuration in which a pass is even reachable -- so it is the
    baseline every negative test below perturbs by one thing.
    """
    from property_core.ppd_service import PPDService

    snapshot = PPDService(adapter=materialized.adapter)
    per_shape = {}
    for case in cases(GEOGRAPHIES):
        request = dict(postcode=case.postcode, search_level=case.search_level,
                       months=case.months, property_type=case.property_type,
                       transaction_category=case.transaction_category)
        response = snapshot.comps(filter_outliers=False, limit=50,
                                  auto_escalate=True, **request)
        per_shape[_request_key(request)] = list(response.transactions)
    return FakeLive(per_shape=per_shape)


def test_a_live_arm_error_makes_the_verdict_false(materialized, instance,
                                                  tmp_path, monkeypatch):
    """Item 1. A report is not allowed to pass while an arm failed."""
    live = FakeLive(raises=RuntimeError("upstream exploded"))
    report = _full_run(materialized, instance, tmp_path, monkeypatch,
                       live=live, repeats=s1.REQUIRED_LATENCY_REPEATS)
    assert report["exit_criteria"]["all_thirteen_cases_compared"]["passed"] is False
    assert report["exit_criteria"]["all_thirteen_cases_compared"]["live_errors"] == 13
    assert report["passed"] is False


def test_a_missing_arm_makes_the_verdict_false(materialized, instance, tmp_path,
                                               monkeypatch, agreeing_live):
    """Item 1. `cases_compared != 13` blocks passage on its own."""
    class OneShort:
        def __init__(self, real):
            self._real = real
        def comps(self, **kwargs):
            if kwargs["postcode"] == "B50":
                raise RuntimeError("no snapshot answer for this case")
            return self._real.comps(**kwargs)

    from property_core.ppd_service import PPDService

    report = _full_run(materialized, instance, tmp_path, monkeypatch,
                       live=agreeing_live, repeats=1,
                       snapshot_service=OneShort(
                           PPDService(adapter=materialized.adapter)))
    criterion = report["exit_criteria"]["all_thirteen_cases_compared"]
    assert criterion["cases_compared"] < s1.REQUIRED_CASES
    assert criterion["cases_missing_snapshot_arm"] == ["S2"]
    assert criterion["passed"] is False
    assert report["passed"] is False


def test_a_short_latency_sample_is_insufficient_evidence_never_a_pass(
        materialized, instance, tmp_path, monkeypatch, agreeing_live):
    """Item 3. Fewer than 13 x 30 observations cannot pass the latency gate.

    Mutation: compute the verdict from `p95 < 1000` alone and this run -- whose
    latencies are microseconds -- flips straight to a pass on 13 observations.
    """
    report = _full_run(materialized, instance, tmp_path, monkeypatch,
                       live=agreeing_live, repeats=1)
    criterion = report["exit_criteria"]["p95_under_one_second"]
    assert criterion["n"] == 13
    assert criterion["required_observations"] == 390
    assert criterion["verdict"] == "insufficient_evidence"
    assert criterion["passed"] is False
    assert report["passed"] is False


def test_the_full_sample_is_exactly_thirteen_by_thirty(
        materialized, instance, tmp_path, monkeypatch, agreeing_live):
    """Item 3, the positive half: 390 observations, 30 for every case."""
    report = _full_run(materialized, instance, tmp_path, monkeypatch,
                       live=agreeing_live)
    criterion = report["exit_criteria"]["p95_under_one_second"]
    assert criterion["n"] == 390
    assert criterion["cases_short_of_the_required_repeats"] == []
    assert criterion["verdict"] in {"pass", "fail"}
    per_case = report["latency"]["per_case_ms"]
    assert len(per_case) == 13
    assert all(v["n"] == 30 for v in per_case.values())


def test_an_unconfirmed_revision_makes_the_verdict_false(
        materialized, instance, tmp_path, monkeypatch, agreeing_live):
    """Item 5. A proposed A/C/D revision blocks the verdict, never annotates it.

    Mutation: drop `no_unconfirmed_classifications` from the criteria and this
    report passes while carrying a classification nothing has confirmed.
    """
    # One shared id whose price differs, dated well before the provisional
    # period -- the A/C/D signature, which this comparison cannot evidence.
    old = "2019-05-01"
    rows = [row("T-OLD-001", "B5 7AA", old, 250_000, property_type="F")]
    build_snapshot(tmp_path / "art", rows, version="v20260828T194003Z")
    opened = s1.open_materialized(tmp_path / "art")
    try:
        path = tmp_path / "i.json"
        raw = _instance_dict(opened)
        raw["governs_run"] = "negative-test"
        path.write_text(json.dumps(raw))
        bound = s1.load_instance(path, opened)
        live = FakeLive(transactions=[
            PPDTransaction(transaction_id="T-OLD-001", postcode="B5 7AA",
                           date=old, price=999_111, property_type="F",
                           estate_type="L", transaction_category="A",
                           new_build=False)])
        report = _full_run(opened, bound, tmp_path, monkeypatch, live=live,
                           repeats=1)
    finally:
        opened.adapter.close()
    criterion = report["exit_criteria"]["no_unconfirmed_classifications"]
    assert criterion["operator_confirmation_required"] >= 1
    assert criterion["passed"] is False
    assert report["passed"] is False


def test_a_broken_corpus_invariant_makes_the_verdict_false(
        materialized, instance, tmp_path, monkeypatch, agreeing_live):
    """Item 9. Section 3's universal invariants are enforced, not just recorded.

    `sample_complete: true` on a comps case is a defect, not a divergence.
    Mutation: record the invariants without consulting them in the verdict and
    this passes with a broken structural guarantee.
    """
    real = s1.snapshot_invariants

    def broken(case, response, provenance, classes):
        result = real(case, response, provenance, classes)
        if case.shape == "S3":
            result["sample_complete_is_false"] = False
        return result

    monkeypatch.setattr(s1, "snapshot_invariants", broken)
    report = _full_run(materialized, instance, tmp_path, monkeypatch,
                       live=agreeing_live, repeats=1)
    criterion = report["exit_criteria"]["corpus_invariants_hold"]
    assert criterion["passed"] is False
    assert criterion["failures"], "a broken invariant was not reported"
    assert criterion["failures"][0]["shape"] == "S3"
    assert "sample_complete_is_false" in criterion["failures"][0]["failed"]
    assert report["passed"] is False


def test_the_report_records_returned_date_bounds_for_both_arms(
        materialized, instance, tmp_path, monkeypatch, agreeing_live):
    """Item 9. Definition section 9 requires the date bounds of returned rows.

    Two dates are not a transaction, and they are what shows a window was
    honoured.
    """
    report = _full_run(materialized, instance, tmp_path, monkeypatch,
                       live=agreeing_live, repeats=1)
    non_empty = [c for c in report["cases"] if c["snapshot"]["count"] > 0]
    assert non_empty
    for case in non_empty:
        for arm in ("snapshot", "live"):
            assert case[arm]["returned_date_from"] is not None, (case["shape"], arm)
            assert case[arm]["returned_date_to"] is not None, (case["shape"], arm)
            assert case[arm]["returned_date_from"] <= case[arm]["returned_date_to"]


def test_a_midnight_crossing_aborts_with_a_written_failed_report(
        materialized, instance, tmp_path, monkeypatch):
    """Item 2. Never silently skipped.

    An observation that straddles midnight describes a different window from
    the one recorded. Skipping it would leave a report claiming thirteen cases
    while holding twelve and a latency sample short of its declared size --
    both of which the totals would conceal. Mutation: swallow `MidnightCrossed`
    into an exclusion counter and this run reports a clean thirteen.
    """
    real_today = date.today
    flips = iter([real_today(), real_today() + timedelta(days=1)] * 40)

    class _AlwaysCrossing:
        today = staticmethod(lambda: next(flips))
        fromisoformat = staticmethod(date.fromisoformat)

    monkeypatch.setattr(s1, "date", _AlwaysCrossing)
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    monkeypatch.setattr(s1.time, "sleep", lambda *_: None)
    report = s1.run_compare(
        instance=instance, materialized=materialized,
        limits=s1.RunLimits(live_delay_seconds=0.0, latency_repeats=1,
                            stop_on_unclassified=False),
        report_path=tmp_path / "report.json",
        live_service=FakeLive(), snapshot_service=None)
    assert report["aborted"], "a surviving midnight crossing did not abort the run"
    assert report["midnight"]["unrecoverable"] is True
    assert report["midnight"]["retries"] >= 1, "the bounded retry never ran"
    assert report["passed"] is False
    assert (tmp_path / "report.json").is_file(), (
        "the run aborted without writing the failed report")


def test_the_snapshot_arm_retries_a_crossing_before_giving_up(materialized):
    """Item 2. The documented bounded retry, on the arm where it is free."""
    real_today = date.today
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        # Cross on the first observation's second read, then settle.
        return real_today() + timedelta(days=1) if calls["n"] == 2 else real_today()

    from property_core.ppd_service import PPDService
    import tools.ppd_snapshot.stage1_shadow as module

    original = module.date
    try:
        class _Date:
            today = staticmethod(flaky)
            fromisoformat = staticmethod(original.fromisoformat)
        module.date = _Date
        case = cases(GEOGRAPHIES)[0]
        _, observed, retries, _ = module._observe(
            PPDService(adapter=materialized.adapter), case,
            attempts=module.MIDNIGHT_ATTEMPTS)
    finally:
        module.date = original
    assert retries == 1, "the crossing was not retried"
    assert observed


def test_arms_observed_on_different_days_abort_rather_than_compare(
        materialized, instance, tmp_path, monkeypatch):
    """Item 2. A pair straddling midnight compares two different windows.

    Nothing downstream can detect this: both arms look internally consistent,
    and the diff between them is just wrong. Mutation: drop the pair-date check
    and the run compares a snapshot window against a live window one day apart
    and reports the difference as a divergence.
    """
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    monkeypatch.setattr(s1.time, "sleep", lambda *_: None)
    real = s1._arm_record

    def shifted(response, case, observed, latency_ms):
        record = real(response, case, observed, latency_ms)
        # Only the live arm is moved, so the pair disagrees.
        if getattr(response, "provenance", None) is not None and \
                "snapshot" not in str(response.provenance.source).lower():
            record["observed_at"] = (
                date.fromisoformat(observed) + timedelta(days=1)).isoformat()
        return record

    monkeypatch.setattr(s1, "_arm_record", shifted)
    report = s1.run_compare(
        instance=instance, materialized=materialized,
        limits=s1.RunLimits(live_delay_seconds=0.0, latency_repeats=1,
                            stop_on_unclassified=False),
        report_path=tmp_path / "report.json",
        live_service=FakeLive(), snapshot_service=None)
    assert report["aborted"] and "straddles midnight" in report["aborted"]
    assert report["midnight"]["pair_date_mismatches"] == 1
    assert report["passed"] is False


# ---------------------------------------------------------------------------
# Item 4: saturation is context, never evidence
# ---------------------------------------------------------------------------

def test_page_saturation_alone_cannot_classify_live_truncation():
    """Item 4. Neither side's saturated page is evidence about the live window.

    A live page at `limit` says our own presentation limit was reached, not
    that the upstream window was. A saturated snapshot page says nothing about
    live at all. Mutation: OR either flag back into the evidence test and these
    divergences become "explained" without a single transport fact.
    """
    for live_saturated, snapshot_saturated in ((True, False), (False, True),
                                               (True, True)):
        result = s1.classify(
            only_live_months={"2019-05": 2}, only_snapshot_months={"2019-06": 1},
            mismatch_months={}, provisional_from="2026-04-01",
            live_saturated=live_saturated, snapshot_saturated=snapshot_saturated,
            live_truncation_evidenced=False)
        assert result["live_truncation_or_ordering"] == 0, (
            live_saturated, snapshot_saturated)
        assert result["unclassified"] == 3


def test_saturation_is_still_recorded_as_context(materialized):
    """Considered and rejected as a basis -- visibly, so a reader can tell."""
    result = s1.classify(
        only_live_months={}, only_snapshot_months={}, mismatch_months={},
        provisional_from="2026-04-01", live_saturated=True,
        snapshot_saturated=True, live_truncation_evidenced=False)
    context = result["truncation_evidence"]["context_not_evidence"]
    assert context["live_page_saturated"] is True
    assert context["snapshot_page_saturated"] is True
    assert result["truncation_evidence"][
        "live_raw_bindings_reached_fetch_limit"] is False


def test_transport_evidence_comes_from_the_captured_live_call():
    """Item 4. The evidence is `raw_bindings_returned` against `fetch_limit`."""
    capture = s1.LiveEvidenceCapture()
    capture.last = {"raw_bindings_returned": 50, "fetch_limit": 50}
    assert capture.truncation_evidenced is True
    capture.last = {"raw_bindings_returned": 12, "fetch_limit": 50}
    assert capture.truncation_evidenced is False
    capture.last = {"raw_bindings_returned": None, "fetch_limit": None}
    assert capture.truncation_evidenced is False


# ---------------------------------------------------------------------------
# Item 6: qualify exit codes, and governs_run
# ---------------------------------------------------------------------------

def test_qualify_exits_non_zero_when_the_baselines_are_unusable(
        tmp_path, monkeypatch):
    """Item 6. Printing a warning and exiting 0 lets a script call it success."""
    # No B5 4 rows at all, so S3_full == S9_full == 0 and the relation fails.
    build_snapshot(tmp_path, [row("T-B57-1", "B5 7AA", "2026-05-04", 200_000)],
                   version="v20260828T194003Z")
    monkeypatch.setenv(s1.SHADOW_COMPARE_ENABLED_ENV, "1")
    code = s1.main(["qualify", "--cache-dir", str(tmp_path),
                    "--out", str(tmp_path / "candidate.json")])
    assert code == 1
    written = json.loads((tmp_path / "candidate.json").read_text())
    assert written["baselines_satisfy_their_relations"] is False
    assert written["baselines_refusal"]


@pytest.mark.parametrize("governs", ["", "   ", s1.GOVERNS_RUN_PLACEHOLDER])
def test_a_blank_or_unchanged_governs_run_is_refused(materialized, tmp_path,
                                                     governs):
    """Item 6. The field ties an Instance to one run; unfilled, it ties nothing.

    A candidate still carrying the placeholder has not been through the review
    the field exists to record.
    """
    path = _write(tmp_path, materialized, governs_run=governs)
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert "governs_run" in str(exc.value)


def test_the_candidate_instance_carries_the_placeholder_qualify_writes(
        materialized):
    """The two halves of the same rule: what qualify writes is what load refuses."""
    candidate = s1.qualify(materialized)["candidate_instance"]
    assert candidate["governs_run"] == s1.GOVERNS_RUN_PLACEHOLDER


# ---------------------------------------------------------------------------
# Item 7: a guard after the final observation
# ---------------------------------------------------------------------------

def test_a_guard_runs_after_the_final_observation(materialized, instance,
                                                  tmp_path, monkeypatch):
    """Item 7. Otherwise a run can finish on a Machine nobody re-checked.

    Health is fine for every observation and fails only afterwards. Without a
    closing guard the report is a clean pass measured under conditions that had
    already gone bad.
    """
    monkeypatch.setattr(s1.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    def health(url, timeout=5.0):
        calls["n"] += 1
        # Healthy for every guard the observations need; unhealthy only for the
        # extra one that can exist solely at the end.
        return (True, "200") if calls["n"] <= 13 + 1 else (False, "503")

    monkeypatch.setattr(s1, "health_ok", health)
    report = s1.run_compare(
        instance=instance, materialized=materialized,
        limits=s1.RunLimits(live_delay_seconds=0.0, latency_repeats=1,
                            stop_on_unclassified=False),
        report_path=tmp_path / "report.json",
        live_service=FakeLive(), snapshot_service=None)
    assert report["aborted"] and "health" in report["aborted"]
    assert report["passed"] is False


def test_the_final_guard_is_reached_on_an_otherwise_clean_run(
        materialized, instance, tmp_path, monkeypatch, agreeing_live):
    """The closing guard exists and is called with its own stage name."""
    seen: list[str] = []
    monkeypatch.setattr(s1.time, "sleep", lambda *_: None)

    def health(url, timeout=5.0):
        seen.append(url)
        return (True, "200")

    monkeypatch.setattr(s1, "health_ok", health)
    s1.run_compare(
        instance=instance, materialized=materialized,
        limits=s1.RunLimits(live_delay_seconds=0.0, latency_repeats=1,
                            stop_on_unclassified=False),
        report_path=tmp_path / "report.json",
        live_service=agreeing_live, snapshot_service=None)
    # 13 correctness guards + 1 latency-repeat guard + 1 final guard.
    assert len(seen) == 15


def test_a_correct_total_with_one_short_case_is_still_insufficient(instance):
    """Item 3. 390 observations is not the same as 30 for every case.

    A total that happens to come out right can hide a case measured 29 times
    and another measured 31 -- and the p95 would then be weighted towards
    whichever shapes were over-sampled, which is a different measurement from
    the one the gate is defined over.

    Mutation: check only `n == 390` and drop the per-case test, and this
    skewed sample reports a pass.
    """
    shapes = [c.shape for c in cases(GEOGRAPHIES)]
    per_case = {shape: [1.0] * s1.REQUIRED_LATENCY_REPEATS for shape in shapes}
    per_case[shapes[0]] = [1.0] * (s1.REQUIRED_LATENCY_REPEATS - 1)
    per_case[shapes[1]] = [1.0] * (s1.REQUIRED_LATENCY_REPEATS + 1)
    latency_ms = [v for values in per_case.values() for v in values]
    assert len(latency_ms) == s1.REQUIRED_LATENCY_OBSERVATIONS

    report = s1._build_report(
        instance=instance, identity={}, limits=s1.RunLimits(), results=[],
        latency_ms=latency_ms, per_case=per_case, snapshot_errors=[],
        live_errors=[], contamination=[], excluded={},
        midnight={"retries": 0, "unrecoverable": False, "pair_date_mismatches": 0},
        corpus=cases(GEOGRAPHIES), aborted=None, live_calls=0)
    criterion = report["exit_criteria"]["p95_under_one_second"]
    assert criterion["n"] == s1.REQUIRED_LATENCY_OBSERVATIONS
    assert criterion["verdict"] == "insufficient_evidence"
    assert criterion["passed"] is False
    assert sorted(criterion["cases_short_of_the_required_repeats"]) == sorted(
        [shapes[0], shapes[1]])
    assert report["passed"] is False
