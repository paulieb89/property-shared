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
from tests.snapshot.rehearsal_fixtures import FORBIDDEN_IN_REPORT  # noqa: E402
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
        rows = self.per_shape.get(kwargs["postcode"], self.transactions)
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

def test_no_id_address_or_price_reaches_the_report(materialized, instance,
                                                   tmp_path, monkeypatch):
    """Ids and field values exist for one comparison, then are discarded.

    The report is a file that gets pasted into a review. It carries counts,
    month histograms, field-mismatch tallies and geography -- enough to
    classify a divergence, and nothing that names a household's sale.
    """
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    live = FakeLive(transactions=[
        PPDTransaction(transaction_id="T-B57-A", postcode="B5 7AA",
                       date="2026-05-01", price=210_000, street="HIGH STREET")])
    _run(materialized, instance, tmp_path, monkeypatch, live=live,
         latency_repeats=1, stop_on_unclassified=False)
    body = (tmp_path / "report.json").read_text()
    for forbidden in FORBIDDEN_IN_REPORT:
        assert forbidden not in body, f"the report leaked {forbidden!r}"
    for forbidden in ("T-B57-000", "HIGH STREET", "200000", "999000"):
        assert forbidden not in body, f"the report leaked {forbidden!r}"


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
        contamination=[], excluded={}, aborted=None, live_calls=0)
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
