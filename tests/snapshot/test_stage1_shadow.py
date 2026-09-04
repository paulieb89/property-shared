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


#: One consistent set of figures, shared by the fixture Instance and its
#: qualification block so the loader's cross-checks pass.
BASELINES = {"S1_full": 100, "S3_full": 40, "S9_full": 55}
NEIGHBOUR_ROWS = 120


def _shortfall_block(ratio_numerator: int = 31, definitional=None,
                     **s1_overrides) -> dict:
    """A qualification block whose neighbour falls short of the literal rule.

    Still internally consistent -- the shortfall is in the measurement, not in
    the bookkeeping, which is what makes it an adjudication question rather
    than a malformed Instance.
    """
    block = _qualification_block(definitional)
    geo = block["S1_district"]["geography"]
    block["S1_district"] = {
        "rule": "the neighbour holds comparable or greater volume",
        "geography": geo,
        "measured_rows": BASELINES["S1_full"],
        "neighbour_geography": block["S2_district"]["geography"],
        "measured_neighbour_rows": ratio_numerator,
        "measured_neighbour_ratio": round(
            ratio_numerator / BASELINES["S1_full"], 4),
        "comparable_or_greater": False,
        **s1_overrides,
    }
    block["S2_district"]["measured_rows"] = ratio_numerator
    return block


def _qualification_block(definitional=None, **overrides) -> dict:
    """A complete qualification block bound to the effective geographies."""
    from tools.ppd_snapshot.corpus import DEFINITIONAL_GEOGRAPHIES

    geo = {**DEFINITIONAL_GEOGRAPHIES, **(definitional or {})}
    block = {key: {"rule": "qualified for the test fixture"}
             for key in sorted(s1.REQUIRED_QUALIFICATION_KEYS)}
    # Internally consistent with BASELINES below: the loader cross-checks every
    # one of these against the baselines and against the effective geographies,
    # so a fixture carrying arbitrary numbers is not a valid Instance either.
    block["S1_district"] = {
        "rule": "the neighbour holds comparable or greater volume",
        "geography": geo["S1_district"],
        "measured_rows": BASELINES["S1_full"],
        "neighbour_geography": geo["S2_neighbour_district"],
        "measured_neighbour_rows": NEIGHBOUR_ROWS,
        "measured_neighbour_ratio": round(
            NEIGHBOUR_ROWS / BASELINES["S1_full"], 4),
        "comparable_or_greater": True,
    }
    block["S2_district"] = {
        "rule": "non-empty under frozen parameters",
        "geography": geo["S2_neighbour_district"],
        "measured_rows": NEIGHBOUR_ROWS,
    }
    block["S3_sector"] = {
        "rule": "a strict subset of S1's district",
        "geography": geo["S3_sector"],
        "measured_rows": BASELINES["S3_full"],
        "measured_rows_category_all": BASELINES["S9_full"],
        "inside_s1_district": (
            geo["S3_sector"].split()[0] == geo["S1_district"]),
    }
    for key, value in overrides.items():
        block[key] = value
    return block


def _instance_dict(m) -> dict:
    return {
        "instance_kind": "stage1",
        "snapshot_version": m.version,
        "bundle_sha256": m.bundle_sha256,
        "geographies": dict(GEOGRAPHIES),
        "aggregate_baselines": dict(BASELINES),
        "qualified_at": "2026-09-01",
        # Complete: every case whose geography the Instance fixes, with the
        # three definitional entries bound to the geographies they measured.
        "qualification": _qualification_block(),
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

def test_a_failing_snapshot_arm_aborts_before_any_live_call(
        materialized, instance, tmp_path, monkeypatch):
    """Recorded, then fatal -- and the live call for that case never happens.

    Once the snapshot arm has failed, "zero snapshot errors on the frozen
    corpus" is unreachable, so every later case is work whose result cannot
    change the verdict. Making the live call anyway would be a request to HM
    Land Registry for a comparison that can no longer take place.

    Mutation: keep recording the error and fall through, and this run makes
    thirteen live calls in service of a verdict already decided.
    """
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    monkeypatch.setattr(s1.time, "sleep", lambda *_: None)

    class Exploding:
        def comps(self, **kwargs):
            raise RuntimeError("snapshot query failed")

    live = FakeLive()
    report = s1.run_compare(
        instance=instance, materialized=materialized,
        limits=s1.RunLimits(live_delay_seconds=0.0, latency_repeats=1,
                            stop_on_unclassified=False),
        report_path=tmp_path / "report.json",
        live_service=live, snapshot_service=Exploding())
    assert report["aborted"] and "snapshot arm failed" in report["aborted"]
    assert "no live call is made" in report["aborted"]
    assert live.calls == [], "a live call was made after the snapshot arm failed"
    assert len(report["cases"]) == 1, "a later case ran after the first failure"
    assert report["exit_criteria"]["zero_snapshot_errors"]["passed"] is False
    assert report["passed"] is False
    assert (tmp_path / "report.json").is_file(), (
        "the run aborted without writing the partial failed report")


def test_a_failing_live_arm_aborts_and_no_later_case_runs(
        materialized, instance, tmp_path, monkeypatch):
    """Completeness is already lost, so continuing gathers nothing usable.

    Mutation: record the error and continue, and the report accumulates twelve
    more cases whose comparisons cannot rescue a verdict that has already
    failed `all_thirteen_cases_compared`.
    """
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    monkeypatch.setattr(s1.time, "sleep", lambda *_: None)
    live = FakeLive(raises=RuntimeError("upstream exploded"))
    report = s1.run_compare(
        instance=instance, materialized=materialized,
        limits=s1.RunLimits(live_delay_seconds=0.0, latency_repeats=1,
                            stop_on_unclassified=False),
        report_path=tmp_path / "report.json",
        live_service=live, snapshot_service=None)
    assert report["aborted"] and "live arm failed" in report["aborted"]
    assert len(report["live_errors"]) == 1, "more than one case was attempted"
    assert len(live.calls) == 1
    assert len(report["cases"]) == 1
    assert report["passed"] is False
    assert (tmp_path / "report.json").is_file()


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
    # live-arm diagnostics: request timing and the failure description
    "live_timing", "started_at", "finished_at", "elapsed_ms", "outcome",
    "live_error_detail", "type", "message", "status", "reason", "headers",
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
    # a contamination finding: which arm, the level the case asked at, and the
    # geographies it strayed into. Sector and outcode granularity only; a
    # unit-level violation inside the requested sector is a COUNT, never a
    # named postcode.
    "arm", "level", "unexpected_outcodes", "unexpected_sectors",
    "same_sector_unit_violations", "rows_without_postcode",
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


def _is_allowed_header_name(key) -> bool:
    """Whether a key is a response-header name the comparator may retain.

    Deliberately asks the production allow-list rather than restating it: a
    header the comparator would refuse to keep is still an un-reviewed key
    here, so the two cannot drift apart.
    """
    name = str(key).strip().lower()
    return (name in s1.LIVE_ERROR_HEADERS_EXACT
            or name.startswith(s1.LIVE_ERROR_HEADER_PREFIXES))


def _static_keys(node):
    """Keys, minus the dynamic key spaces (months, shapes, field names,
    allow-listed response-header names)."""
    found = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if not (MONTH.match(str(key)) or key in SHAPE_NAMES
                    or key in FIELD_NAMES or _is_allowed_header_name(key)):
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
    """An Instance file with the given fields overridden."""
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
    """A report is not allowed to pass while an arm failed.

    The run now stops at the first failure, so the evidence is one error and
    twelve cases never reached -- both of which block completeness.
    """
    live = FakeLive(raises=RuntimeError("upstream exploded"))
    report = _full_run(materialized, instance, tmp_path, monkeypatch,
                       live=live, repeats=s1.REQUIRED_LATENCY_REPEATS)
    criterion = report["exit_criteria"]["all_thirteen_cases_compared"]
    assert criterion["passed"] is False
    assert criterion["live_errors"] == 1
    assert len(criterion["cases_never_reached"]) == 12
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


def test_the_default_repeat_count_is_the_count_the_gate_requires():
    """A default run must be able to satisfy the gate it is measured against.

    Three independent literals -- the dataclass default, the CLI default and
    the gate constant -- would drift, and the symptom would be a full run that
    reports `insufficient_evidence` for no reason an operator could see.
    """
    assert s1.RunLimits().latency_repeats == s1.REQUIRED_LATENCY_REPEATS
    parsed = s1.build_parser().parse_args(
        ["compare", "--instance", "i.json", "--report", "r.json"])
    assert parsed.latency_repeats == s1.REQUIRED_LATENCY_REPEATS
    assert (s1.REQUIRED_LATENCY_REPEATS * s1.REQUIRED_CASES
            == s1.REQUIRED_LATENCY_OBSERVATIONS == 390)


# ---------------------------------------------------------------------------
# Geography containment, judged at the level the case asked at
# ---------------------------------------------------------------------------

def _case(shape, postcode, level):
    from tools.ppd_snapshot.corpus import Case
    return Case(shape, "test", postcode, level)


def test_a_same_outcode_neighbouring_sector_is_contamination():
    """The trap an outcode-only check calls clean.

    `B5 4` asked at sector level and handed a `B5 6` row shares the outcode, so
    `all(o == "B5")` passes -- while the Definition names sector isolation
    (`M3 7` returns only `M3 7`) as a trap in its own right.

    Mutation: compare outcodes only and this row reads as in-area.
    """
    rows = [PPDTransaction(transaction_id="A", postcode="B5 4AA", date="2026-05-01"),
            PPDTransaction(transaction_id="B", postcode="B5 6QQ", date="2026-05-01")]
    violations = s1.geography_violations(_case("S3", "B5 4", "sector"), rows)
    assert violations["unexpected_outcodes"] == []
    assert violations["unexpected_sectors"] == ["B5 6"]
    assert s1.is_contaminated(violations) is True


def test_a_same_sector_neighbouring_unit_is_contamination():
    """A `postcode` case handed a different unit in the same sector.

    Both an outcode check and a sector check call this clean.
    """
    rows = [PPDTransaction(transaction_id="A", postcode="B5 7AA", date="2026-05-01"),
            PPDTransaction(transaction_id="B", postcode="B5 7AB", date="2026-05-01")]
    violations = s1.geography_violations(_case("S6", "B5 7AA", "postcode"), rows)
    assert violations["unexpected_outcodes"] == []
    assert violations["unexpected_sectors"] == []
    assert violations["same_sector_unit_violations"] == 1
    assert s1.is_contaminated(violations) is True


def test_a_unit_violation_is_counted_never_named():
    """Hygiene: sector and outcode granularity only.

    The offending unit postcode would be the most identifying thing in the
    report, and the count is what proves the contamination.
    """
    rows = [PPDTransaction(transaction_id="B", postcode="B5 7AB", date="2026-05-01")]
    violations = s1.geography_violations(_case("S6", "B5 7AA", "postcode"), rows)
    assert "B5 7AB" not in json.dumps(violations)
    assert violations["same_sector_unit_violations"] == 1


def test_a_district_case_is_still_judged_by_outcode():
    """A district case legitimately spans every sector inside its outcode."""
    rows = [PPDTransaction(transaction_id="A", postcode="B5 4AA", date="2026-05-01"),
            PPDTransaction(transaction_id="B", postcode="B5 6QQ", date="2026-05-01")]
    clean = s1.geography_violations(_case("S1", "B5", "district"), rows)
    assert s1.is_contaminated(clean) is False
    dirty = s1.geography_violations(
        _case("S1", "B5", "district"),
        rows + [PPDTransaction(transaction_id="C", postcode="B50 4AA",
                               date="2026-05-01")])
    assert dirty["unexpected_outcodes"] == ["B50"]
    assert s1.is_contaminated(dirty) is True


def test_sector_contamination_on_either_arm_fails_the_verdict(
        materialized, instance, tmp_path, monkeypatch, agreeing_live):
    """End to end, on the LIVE arm -- contamination is a defect in whichever
    source produced it, so neither arm is assumed clean because the other is."""
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    monkeypatch.setattr(s1.time, "sleep", lambda *_: None)
    real = s1._geography_contamination

    def dirty(response, case):
        if case.shape == "S3":
            return {"level": "sector", "unexpected_outcodes": [],
                    "unexpected_sectors": ["B5 6"],
                    "same_sector_unit_violations": 0}
        return real(response, case)

    monkeypatch.setattr(s1, "_geography_contamination", dirty)
    report = _full_run(materialized, instance, tmp_path, monkeypatch,
                       live=agreeing_live, repeats=1)
    criterion = report["exit_criteria"]["zero_geography_contamination"]
    assert criterion["passed"] is False
    assert {f["arm"] for f in criterion["findings"]} == {"live", "snapshot"}
    assert report["passed"] is False


# ---------------------------------------------------------------------------
# B5 / B50 qualification
# ---------------------------------------------------------------------------

def test_qualification_fails_when_b50_is_empty(tmp_path, monkeypatch):
    """S2 is "non-empty under frozen parameters", and B50 empty breaks S1 too.

    Against a near-empty neighbour a clean S1 result proves nothing: the
    contamination boundary is a test that cannot fail. Mutation: measure
    `S1_full` and never look at the neighbour, and both cases qualify silently.
    """
    rows = [row(f"T-B57-{i:03d}", "B5 7AA", "2026-05-04", 200_000 + i)
            for i in range(20)]
    build_snapshot(tmp_path, rows, version="v20260828T194003Z")
    monkeypatch.setenv(s1.SHADOW_COMPARE_ENABLED_ENV, "1")
    code = s1.main(["qualify", "--cache-dir", str(tmp_path),
                    "--out", str(tmp_path / "candidate.json")])
    assert code == 1
    out = json.loads((tmp_path / "candidate.json").read_text())
    # S2 has nothing in it: an outright qualification failure.
    assert "S2_district" in out["unqualified_definitional_cases"]
    assert out["candidate_instance"]["qualification"]["S2_district"][
        "measured_rows"] == 0
    # S1's district is populated, so the question is not "did it fail" but
    # "is a neighbour holding 0% comparable?" -- which is the owner's call.
    assert "S1_district" in out["requires_owner_adjudication"]
    assert "S1_district" not in out["unqualified_definitional_cases"]


def test_a_definitional_failure_alone_makes_qualify_exit_non_zero(
        tmp_path, monkeypatch, materialized):
    """Isolated from the placeholder branch, which would otherwise mask it.

    On a small artifact several placeholders also fail to qualify, so a run
    exits 1 either way and the definitional branch could be dead without any
    test noticing. This drives the exit code from a definitional failure alone.
    """
    payload = s1.qualify(materialized)
    # Every OTHER reason to exit non-zero is cleared, so the exit code can only
    # be coming from the definitional branch. Leaving adjudication populated
    # masked this: the run exited 1 either way and the branch could have been
    # dead without any test noticing.
    payload["unqualified_placeholders"] = []
    payload["baselines_satisfy_their_relations"] = True
    payload["baselines_refusal"] = None
    payload["requires_owner_adjudication"] = []
    payload["unqualified_definitional_cases"] = ["S2_district"]
    monkeypatch.setattr(s1, "qualify", lambda *a, **k: payload)
    monkeypatch.setenv(s1.SHADOW_COMPARE_ENABLED_ENV, "1")
    code = s1.main(["qualify", "--cache-dir", str(materialized.directory.parents[1]),
                    "--out", str(tmp_path / "candidate.json")])
    assert code == 1


def test_qualification_records_the_neighbour_ratio_it_judged_on(tmp_path):
    """The threshold is an operationalisation, so the measurement is recorded.

    The Definition states "comparable or greater volume" qualitatively; a tool
    needs a number, so the number is named and the measured ratio published
    beside it for a reviewer to judge rather than trust.
    """
    rows = [row(f"T-B57-{i:03d}", "B5 7AA", "2026-05-04", 200_000 + i)
            for i in range(20)]
    rows += [row(f"T-B50-{i:03d}", "B50 4AA", "2026-05-04", 400_000 + i)
             for i in range(20)]
    build_snapshot(tmp_path, rows, version="v20260828T194003Z")
    opened = s1.open_materialized(tmp_path)
    try:
        out = s1.qualify(opened, today=date(2026, 6, 15))
    finally:
        opened.adapter.close()
    s1_block = out["candidate_instance"]["qualification"]["S1_district"]
    assert s1_block["measured_neighbour_rows"] == 20
    assert s1_block["measured_neighbour_ratio"] == 1.0
    # Equal volume IS "comparable or greater", so this one qualifies outright
    # and needs no judgement from anybody.
    assert s1_block["comparable_or_greater"] is True
    assert "S1_district" not in out["unqualified_definitional_cases"]
    assert "S2_district" not in out["unqualified_definitional_cases"]
    assert "S1_district" not in out["requires_owner_adjudication"]


# ---------------------------------------------------------------------------
# Instance staleness
# ---------------------------------------------------------------------------

def test_a_stale_instance_is_refused(materialized, tmp_path):
    """The bound is enforced against the calendar, not merely type-checked.

    The artifact is fixed, but the frozen window moves forward every day, so
    counts qualified months ago describe a query nobody now runs. Mutation:
    validate `staleness_bound_days` and never compare it to `qualified_at`, and
    a months-old Instance qualifies a Stage 1 run while looking well-formed.
    """
    old = (date.today() - timedelta(days=90)).isoformat()
    path = _write(tmp_path, materialized, qualified_at=old,
                  staleness_bound_days=45)
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert "staleness_bound_days" in str(exc.value)
    assert "90 days ago" in str(exc.value)


def test_an_instance_inside_its_staleness_bound_is_accepted(materialized, tmp_path):
    fresh = (date.today() - timedelta(days=10)).isoformat()
    path = _write(tmp_path, materialized, qualified_at=fresh,
                  staleness_bound_days=45)
    assert s1.load_instance(path, materialized).qualified_at == fresh


@pytest.mark.parametrize("qualified_at", [
    "", "not-a-date", "2026-13-45", "01/09/2026", None, 20260901,
    # Both of these PARSE. `fromisoformat` accepts basic format and ISO week
    # dates, so "2026-W36-2" resolves silently to 2026-09-01 -- a real date,
    # spelled in a way no operator reading the Instance would recognise. Only
    # the canonical round-trip rejects them.
    "20260901", "2026-W36-2",
])
def test_a_malformed_qualified_at_is_refused(materialized, tmp_path, qualified_at):
    """An Instance whose age cannot be established cannot be checked at all."""
    path = _write(tmp_path, materialized, qualified_at=qualified_at)
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert "qualified_at" in str(exc.value)


def test_a_future_qualified_at_is_refused(materialized, tmp_path):
    """It cannot have been qualified against this artifact yet."""
    ahead = (date.today() + timedelta(days=3)).isoformat()
    path = _write(tmp_path, materialized, qualified_at=ahead)
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert "future" in str(exc.value)


# ---------------------------------------------------------------------------
# The live-call bound is real
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", [0, -1])
def test_max_live_per_case_below_one_is_refused_before_any_work(
        materialized, instance, tmp_path, value):
    """An option that silently does nothing is worse than no option.

    `max_live_per_case=0` previously left the run making thirteen live calls
    anyway -- the field was recorded in the report and enforced nowhere, so it
    told an operator they had a control they did not have.
    """
    with pytest.raises(s1.ComparisonRefused) as exc:
        s1.run_compare(
            instance=instance, materialized=materialized,
            limits=s1.RunLimits(max_live_per_case=value, latency_repeats=1),
            report_path=tmp_path / "report.json",
            live_service=FakeLive(), snapshot_service=None)
    assert "max_live_per_case" in str(exc.value)
    assert not (tmp_path / "report.json").exists(), (
        "a refused run still wrote a report")


def test_zero_latency_repeats_is_refused(materialized, instance, tmp_path):
    """A run taking no latency observation cannot produce the gate's sample."""
    with pytest.raises(s1.ComparisonRefused) as exc:
        s1.run_compare(
            instance=instance, materialized=materialized,
            limits=s1.RunLimits(latency_repeats=0),
            report_path=tmp_path / "report.json",
            live_service=FakeLive(), snapshot_service=None)
    assert "latency_repeats" in str(exc.value)


def test_the_live_budget_refuses_a_call_that_would_exceed_it():
    """Checked before every live call, so the bound survives a code change.

    The loop takes one observation per case today, so the budget is never
    reached by the current path -- which is exactly why it is a separate,
    directly tested guard rather than an assumption about the loop's shape. A
    change that added a second live call would stop the run instead of quietly
    making more requests to HM Land Registry than the run declared.
    """
    limits = s1.RunLimits(max_live_per_case=1)
    # Inside budget: silent.
    s1.check_live_budget(0, limits, 13, "S1")
    s1.check_live_budget(12, limits, 13, "S13")
    # At and beyond it: refused.
    with pytest.raises(s1.RunAborted) as exc:
        s1.check_live_budget(13, limits, 13, "S14")
    assert "live-call budget of 13" in str(exc.value)
    assert "separate authorisation" in str(exc.value)


def test_the_budget_scales_with_an_authorised_retry_allowance():
    """A higher allowance is the documented route for an authorised retry."""
    s1.check_live_budget(13, s1.RunLimits(max_live_per_case=2), 13, "S1")
    with pytest.raises(s1.RunAborted):
        s1.check_live_budget(26, s1.RunLimits(max_live_per_case=2), 13, "S1")


# ---------------------------------------------------------------------------
# The runbook describes the deploy path that actually exists
# ---------------------------------------------------------------------------

RUNBOOK = REPO / "docs" / "ops" / "ppd-stage1-shadow-runbook.md"


def test_the_runbook_uses_the_release_workflow_not_a_manual_deploy():
    """A local `fly deploy` ships the working directory, not a commit.

    Stage 1 evidence has to be attributable to a revision. An image built from
    whatever was on a laptop makes "which code produced this p95?"
    unanswerable, which is precisely what a deployment gate cannot afford.
    """
    body = RUNBOOK.read_text()
    assert "release.yml" in body
    assert "publish a GitHub release" in body
    assert "ships **the working directory, not a commit**" in body
    assert "fly deploy --ha=false" not in body, (
        "the runbook still tells an operator to deploy from a working directory")


def test_the_runbook_states_that_a_release_redeploys_propertydata():
    """Honest about the shared workflow rather than repeating "untouched".

    `release.yml` deploys both apps on every release. Claiming propertydata is
    untouched full stop would be wrong; what is true is that its configuration
    and scope do not change.
    """
    body = RUNBOOK.read_text()
    assert "redeploys `propertydata` too" in body
    assert "untouched in configuration and scope" in body


def test_the_release_workflow_still_deploys_both_apps():
    """Pins the fact the runbook's honesty depends on.

    If release.yml ever stopped deploying propertydata, the runbook's warning
    would become misleading in the other direction.
    """
    workflow = (REPO / ".github" / "workflows" / "release.yml").read_text()
    assert "release:" in workflow and "published" in workflow

    # Both apps are named explicitly in the workflow. This previously asserted
    # the literal `flyctl deploy --remote-only --ha=false`, which lived inline;
    # the retry ladder moved that invocation into scripts/deploy_fly.py, so the
    # flags are pinned there instead (below) and the app/config pairing is
    # pinned here. The fact being guarded is unchanged: every release still
    # deploys propertydata as well as property-shared.
    assert "--app property-shared --config fly.toml" in workflow
    assert "--app propertydata --config fly.app.toml" in workflow

    deploy_script = (REPO / "scripts" / "deploy_fly.py").read_text()
    assert '"--remote-only"' in deploy_script
    assert '"--ha=false"' in deploy_script


def test_the_runbook_documents_the_search_level_containment_rule():
    body = RUNBOOK.read_text()
    assert "at the level each case asked at" in body
    assert "same_sector_unit_violations" in body
    assert "never named" in body


def test_the_runbook_documents_enforced_staleness_and_b50_qualification():
    body = RUNBOOK.read_text()
    assert "enforced at load, not merely recorded" in body
    assert "unqualified_definitional_cases" in body
    assert "NEIGHBOUR_COMPARABLE_RATIO" in body


# ---------------------------------------------------------------------------
# A row with no usable postcode is a containment failure
# ---------------------------------------------------------------------------

def test_a_row_with_no_postcode_is_a_containment_violation():
    """Skipping it would decide an open question in the weakest direction.

    Definition section 11 lists rows with no geography as a known limit and
    leaves the question open. Silently skipping them settles it: a source could
    return arbitrary rows with the postcode blanked and every containment check
    would pass. Mutation: `continue` past them and this returns clean.
    """
    rows = [PPDTransaction(transaction_id="A", postcode="B5 4AA", date="2026-05-01"),
            PPDTransaction(transaction_id="B", postcode=None, date="2026-05-01"),
            PPDTransaction(transaction_id="C", postcode="   ", date="2026-05-01")]
    violations = s1.geography_violations(_case("S3", "B5 4", "sector"), rows)
    assert violations["rows_without_postcode"] == 2
    assert s1.is_contaminated(violations) is True


def test_a_postcode_less_row_is_counted_never_described():
    """Only a count. The row is by definition the one whose geography cannot
    be stated, so there is nothing safe to record about it beyond how many."""
    rows = [PPDTransaction(transaction_id="SECRET-ID", postcode=None,
                           date="2026-05-01", price=999_000, street="HIGH STREET")]
    violations = s1.geography_violations(_case("S1", "B5", "district"), rows)
    body = json.dumps(violations)
    assert "SECRET-ID" not in body and "HIGH STREET" not in body
    assert "999000" not in body
    assert violations["rows_without_postcode"] == 1


def test_postcode_less_rows_block_the_verdict_on_either_arm(
        materialized, instance, tmp_path, monkeypatch, agreeing_live):
    """End to end, on the live arm."""
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    monkeypatch.setattr(s1.time, "sleep", lambda *_: None)
    blank = FakeLive(transactions=[
        PPDTransaction(transaction_id="X", postcode=None, date="2026-05-01")])
    report = _full_run(materialized, instance, tmp_path, monkeypatch,
                       live=blank, repeats=1)
    criterion = report["exit_criteria"]["zero_geography_contamination"]
    assert criterion["passed"] is False
    assert any(f["rows_without_postcode"] > 0 for f in criterion["findings"])
    assert report["passed"] is False


# ---------------------------------------------------------------------------
# The qualification block must be complete and exact
# ---------------------------------------------------------------------------

def test_a_partial_qualification_block_is_refused(materialized, tmp_path):
    """Silent about the cases it omits, while looking like evidence.

    Mutation: accept any non-empty dict and an Instance naming one rule for one
    case qualifies all thirteen.
    """
    partial = {"S5_dense": {"rule": "dense"}}
    path = _write(tmp_path, materialized, qualification=partial)
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert "qualification is missing" in str(exc.value)
    assert "S1_district" in str(exc.value)


def test_an_unknown_qualification_key_is_refused(materialized, tmp_path):
    """A typo leaves the case it meant to qualify unqualified, block complete."""
    block = _qualification_block()
    block["S5_dnese"] = {"rule": "typo"}
    path = _write(tmp_path, materialized, qualification=block)
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert "unknown key" in str(exc.value)
    assert "S5_dnese" in str(exc.value)


def test_a_qualification_entry_with_no_rule_is_refused(materialized, tmp_path):
    """Naming a geography is not qualifying it."""
    block = _qualification_block()
    block["S4_thin"] = {"measured_rows": 3}
    path = _write(tmp_path, materialized, qualification=block)
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert "records no rule" in str(exc.value)


def test_the_required_qualification_keys_cover_every_fixed_geography():
    """Placeholders plus the definitional cases -- nothing fixed goes unrecorded."""
    from tools.ppd_snapshot.corpus import REQUIRED_GEOGRAPHIES

    assert s1.REQUIRED_QUALIFICATION_KEYS == (
        set(REQUIRED_GEOGRAPHIES)
        | {"S1_district", "S2_district", "S3_sector"})


def test_a_qualify_candidate_satisfies_the_loader_it_will_be_checked_by(
        tmp_path):
    """The two halves of the same rule, again: what qualify writes, load accepts.

    Mutation: add a key to one side only and a freshly generated candidate is
    refused by the tool that generated it.
    """
    rows = [row(f"T-B54-{i:03d}", "B5 4AA", "2026-05-04", 200_000 + i)
            for i in range(30)]
    rows += [row(f"T-B50-{i:03d}", "B50 4AA", "2026-05-04", 400_000 + i)
             for i in range(60)]
    rows += [row("T-B54-CATB", "B5 4AB", "2026-05-04", 900_000, ppd_category="B")]
    rows += [row(f"T-B56-{i:03d}", "B5 6QQ", "2026-05-04", 300_000 + i,
                 property_type=t) for i, t in enumerate("DST")]
    build_snapshot(tmp_path, rows, version="v20260828T194003Z")
    opened = s1.open_materialized(tmp_path)
    try:
        candidate = s1.qualify(opened)["candidate_instance"]
        assert set(candidate["qualification"]) == s1.REQUIRED_QUALIFICATION_KEYS - (
            s1.REQUIRED_QUALIFICATION_KEYS - set(candidate["qualification"])), (
            "qualify emitted qualification keys the loader does not expect")
        assert not (set(candidate["qualification"])
                    - s1.REQUIRED_QUALIFICATION_KEYS), (
            "qualify emits a qualification key load_instance would refuse")
    finally:
        opened.adapter.close()


# ---------------------------------------------------------------------------
# The Definition's B5/B50 rule, unredefined; its substitution route, restored
# ---------------------------------------------------------------------------

def test_the_neighbour_rule_is_the_literal_one_not_a_weaker_threshold():
    """A tenth is not "comparable or greater", and the tool no longer says so.

    An earlier version auto-qualified S1 at a 10% neighbour ratio, quietly
    redefining a frozen rule downwards inside an implementation. Mutation: set
    this back below 1.0 and the deferral tests below stop deferring -- the tool
    resumes deciding a question that is not its to decide.
    """
    assert s1.NEIGHBOUR_COMPARABLE_RATIO == 1.0
    source = (REPO / "tools" / "ppd_snapshot" / "stage1_shadow.py").read_text()
    assert "MIN_NEIGHBOUR_VOLUME_RATIO" not in source
    assert "threshold_is_an_operationalisation" not in source


def test_a_thin_neighbour_is_referred_to_the_owner_not_decided(tmp_path):
    """Neither auto-passed nor auto-failed: measured, and handed over.

    "Is 6% comparable for this artifact?" is a judgement about the corpus, and
    the Definition already provides the two ways to settle it -- accept it, or
    substitute a geography with recorded justification.
    """
    rows = [row(f"T-B54-{i:03d}", "B5 4AA", "2026-05-04", 200_000 + i)
            for i in range(30)]
    rows += [row("T-B50-001", "B50 4AA", "2026-05-04", 400_000)]
    build_snapshot(tmp_path, rows, version="v20260828T194003Z")
    opened = s1.open_materialized(tmp_path)
    try:
        out = s1.qualify(opened, today=date(2026, 6, 15))
    finally:
        opened.adapter.close()
    block = out["candidate_instance"]["qualification"]["S1_district"]
    assert block["comparable_or_greater"] is False
    assert 0 < block["measured_neighbour_ratio"] < 1.0
    assert "S1_district" in out["requires_owner_adjudication"]
    # Not silently failed either -- the distinction is the point.
    assert "S1_district" not in out["unqualified_definitional_cases"]
    assert "This tool does not decide" in block["adjudication"]


def test_adjudication_pending_makes_qualify_exit_non_zero(materialized, tmp_path,
                                                          monkeypatch):
    """A candidate awaiting a judgement is not a candidate ready to run."""
    payload = s1.qualify(materialized)
    # Symmetrically: every other reason cleared, so only adjudication remains.
    payload["unqualified_placeholders"] = []
    payload["unqualified_definitional_cases"] = []
    payload["baselines_satisfy_their_relations"] = True
    payload["baselines_refusal"] = None
    payload["requires_owner_adjudication"] = ["S1_district"]
    monkeypatch.setattr(s1, "qualify", lambda *a, **k: payload)
    monkeypatch.setenv(s1.SHADOW_COMPARE_ENABLED_ENV, "1")
    code = s1.main(["qualify", "--cache-dir", str(materialized.directory.parents[1]),
                    "--out", str(tmp_path / "candidate.json")])
    assert code == 1


def test_the_substitution_route_the_definition_documents_still_exists():
    """Section 4 permits substituting a definitional geography WITH justification.

    A previous revision asserted these "cannot be substituted", which removed a
    route the frozen contract grants. Mutation: drop `validate_substitutions`
    and an Instance exercising the documented route is refused.
    """
    from tools.ppd_snapshot.corpus import DEFINITIONAL_GEOGRAPHIES, cases

    assert set(DEFINITIONAL_GEOGRAPHIES) == {
        "S1_district", "S2_neighbour_district", "S3_sector"}
    substituted = {"S1_district": "M3", "S2_neighbour_district": "M30",
                   "S3_sector": "M3 7"}
    shapes = {c.shape: c.postcode for c in cases(GEOGRAPHIES, substituted)}
    assert shapes["S1"] == "M3" and shapes["S12"] == "M3"
    assert shapes["S2"] == "M30"
    assert shapes["S3"] == "M3 7" and shapes["S9"] == "M3 7"
    assert shapes["S14"] == "M3 7"
    # Defaults still apply when nothing is substituted.
    assert {c.shape: c.postcode for c in cases(GEOGRAPHIES)}["S1"] == "B5"


def test_a_substitution_must_supply_all_three_linked_geographies():
    """S3 is a sector inside S1's district; S2 is its neighbour.

    Substituting one alone leaves S3 outside S1 and the containment relation
    the baselines exist to establish silently false.
    """
    from tools.ppd_snapshot.corpus import validate_substitutions

    with pytest.raises(InstanceRefused) as exc:
        validate_substitutions({"S1_district": {"geography": "M3",
                                                "justification": "why"}})
    assert "all of" in str(exc.value)
    assert "silently false" in str(exc.value)


def test_a_substitution_without_a_justification_is_refused():
    """The Definition permits substitution *with recorded justification*."""
    from tools.ppd_snapshot.corpus import validate_substitutions

    entry = {key: {"geography": geo, "justification": "recorded reason"}
             for key, geo in (("S1_district", "M3"),
                              ("S2_neighbour_district", "M30"),
                              ("S3_sector", "M3 7"))}
    assert validate_substitutions(entry) == {
        "S1_district": "M3", "S2_neighbour_district": "M30",
        "S3_sector": "M3 7"}
    entry["S3_sector"] = {"geography": "M3 7", "justification": "  "}
    with pytest.raises(InstanceRefused) as exc:
        validate_substitutions(entry)
    assert "records no justification" in str(exc.value)


def test_absent_substitutions_are_the_normal_case():
    from tools.ppd_snapshot.corpus import validate_substitutions

    assert validate_substitutions(None) == {}
    assert validate_substitutions({}) == {}


def test_an_instance_carrying_a_substitution_drives_the_corpus(
        materialized, tmp_path):
    """End to end: the Instance's substitution reaches the executed cases."""
    raw = _instance_dict(materialized)
    raw["governs_run"] = "substituted-run"
    substituted = {"S1_district": "M3", "S2_neighbour_district": "M30",
                   "S3_sector": "M3 7"}
    raw["substitutions"] = {
        "S1_district": {"geography": "M3", "justification": "B50 too thin"},
        "S2_neighbour_district": {"geography": "M30", "justification": "ditto"},
        "S3_sector": {"geography": "M3 7", "justification": "inside M3"},
    }
    # Re-qualified: the evidence names the geographies the run will execute.
    raw["qualification"] = _qualification_block(substituted)
    path = tmp_path / "substituted.json"
    path.write_text(json.dumps(raw))
    loaded = s1.load_instance(path, materialized)
    assert loaded.substitutions["S1_district"] == "M3"
    from tools.ppd_snapshot.corpus import cases as build

    assert {c.shape: c.postcode
            for c in build(loaded.geographies, loaded.substitutions)}["S1"] == "M3"


def test_the_runbook_carries_post_release_checks_for_propertydata():
    """It is redeployed by the same release, so it is checked, not assumed.

    "Out of scope" is a statement about what changes, not a reason to skip
    verifying that nothing did.
    """
    body = RUNBOOK.read_text()
    assert "Post-release checks — `propertydata`" in body
    assert "must be checked, not assumed" in body
    for check in ("propertydata.fly.dev/health", "fly secrets list -a propertydata",
                  "fly status -a propertydata", "stage1_shadow.py",
                  "fly image show -a propertydata"):
        assert check in body, f"the runbook omits the propertydata check: {check}"
    assert "stop" in body.lower()


def test_the_runbook_documents_abort_on_first_arm_error():
    body = RUNBOOK.read_text()
    assert "the first error on\neither arm" in body or \
        "**the first error on" in body
    assert "before that case makes its live call" in body


def test_the_runbook_documents_the_postcode_less_row_rule():
    body = RUNBOOK.read_text()
    assert "no usable postcode" in body
    assert "rows_without_postcode" in body


def test_the_runbook_documents_adjudication_and_substitution():
    body = RUNBOOK.read_text()
    assert "requires_owner_adjudication" in body
    assert "NEIGHBOUR_COMPARABLE_RATIO = 1.0" in body
    assert "auto-qualified at a 10% ratio" in body
    assert '"substitutions"' in body


# ---------------------------------------------------------------------------
# Evidence binding: falsification tests
# ---------------------------------------------------------------------------

def test_a_latency_pass_snapshot_error_aborts_and_writes_the_partial_report(
        materialized, instance, tmp_path, monkeypatch, agreeing_live):
    """The latency pass stops on the first error, exactly as the first pass does.

    Continuing would leave that case short of its thirty repetitions, and the
    gate would then report `insufficient_evidence` for a reason buried in an
    error list rather than the snapshot error that actually caused it.

    Mutation: `continue` past the error and this run finishes with a short
    sample and no abort.
    """
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    monkeypatch.setattr(s1.time, "sleep", lambda *_: None)
    from property_core.ppd_service import PPDService

    real = PPDService(adapter=materialized.adapter)
    state = {"correctness_done": False, "calls": 0}

    class FailsInLatencyPass:
        def comps(self, **kwargs):
            state["calls"] += 1
            if state["correctness_done"] and state["calls"] > 13:
                raise RuntimeError("snapshot query failed mid-sample")
            if state["calls"] == 13:
                state["correctness_done"] = True
            return real.comps(**kwargs)

    report = s1.run_compare(
        instance=instance, materialized=materialized,
        limits=s1.RunLimits(live_delay_seconds=0.0, latency_repeats=5,
                            stop_on_unclassified=False),
        report_path=tmp_path / "report.json",
        live_service=agreeing_live, snapshot_service=FailsInLatencyPass())
    assert report["aborted"], "a latency-pass snapshot error did not abort"
    assert "during the latency pass" in report["aborted"]
    assert report["exit_criteria"]["zero_snapshot_errors"]["passed"] is False
    assert report["exit_criteria"]["p95_under_one_second"][
        "verdict"] == "insufficient_evidence"
    assert report["passed"] is False
    assert (tmp_path / "report.json").is_file(), (
        "the run aborted without writing the partial report")


def test_a_pending_adjudication_is_refused_not_carried(materialized, tmp_path):
    """An Instance recording the shortfall and nothing else leaves it pending.

    `qualify` deliberately refers the judgement rather than settling it. If the
    Instance may then carry the referral unanswered, the referral achieves
    nothing. Mutation: accept a False `comparable_or_greater` with no
    `owner_decision` and a pending judgement qualifies a Stage 1 run.
    """
    block = _shortfall_block()
    path = _write(tmp_path, materialized, qualification=block)
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert "records no owner_decision" in str(exc.value)
    assert "pending judgement is not a qualification" in str(exc.value)


def test_an_accepted_shortfall_needs_a_justification(materialized, tmp_path):
    """A decision nobody can review is not a decision that was recorded."""
    block = _shortfall_block(owner_decision={"decision": "accepted",
                                             "justification": "   "})
    path = _write(tmp_path, materialized, qualification=block)
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert "records no justification" in str(exc.value)


def test_a_recorded_acceptance_with_a_reason_qualifies_the_case(materialized,
                                                                tmp_path):
    """The route the Definition offers, taken properly, is accepted."""
    block = _shortfall_block(owner_decision={
        "decision": "accepted",
        "justification": ("B50 is a small rural outcode; 31% still returns "
                          "hundreds of rows, enough for contamination to "
                          "show. Reviewed 2026-09-01."),
    })
    path = _write(tmp_path, materialized, qualification=block)
    assert s1.load_instance(path, materialized).governs_run


@pytest.mark.parametrize("decision", ["pending", "rejected", "deferred", ""])
def test_only_an_explicit_acceptance_qualifies(materialized, tmp_path, decision):
    block = _shortfall_block(owner_decision={"decision": decision,
                                             "justification": "a reason"})
    path = _write(tmp_path, materialized, qualification=block)
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert "only 'accepted' qualifies" in str(exc.value)


def test_an_instance_that_does_not_record_comparability_is_refused(
        materialized, tmp_path):
    """It is the fact an adjudication would be answering.

    Refused by the cross-check, which recomputes the field from the counts --
    a missing value cannot equal the recomputed one. There is deliberately no
    second guard for it: an unreachable check is not a safety net.
    """
    block = _qualification_block()
    block["S1_district"].pop("comparable_or_greater")
    path = _write(tmp_path, materialized, qualification=block)
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert "comparable_or_greater" in str(exc.value)
    assert "may not be asserted independently" in str(exc.value)


def test_a_substitution_bolted_onto_unchanged_evidence_is_refused(
        materialized, tmp_path):
    """The exact shortcut the runbook must not invite.

    An Instance qualified over `B5`/`B50`/`B5 4` with a `substitutions` block
    added afterwards looks complete: every required key is present and every
    rule is stated. It is evidence about one set of geographies attached to a
    run that will execute another.

    Mutation: drop the geography binding and this Instance is accepted, and
    Stage 1 runs `M3` while its baselines describe `B5`.
    """
    raw = _instance_dict(materialized)
    raw["governs_run"] = "bolted-on"
    raw["substitutions"] = {
        "S1_district": {"geography": "M3", "justification": "why"},
        "S2_neighbour_district": {"geography": "M30", "justification": "why"},
        "S3_sector": {"geography": "M3 7", "justification": "why"},
    }
    # qualification left as generated for B5/B50/B5 4 -- deliberately unchanged.
    path = tmp_path / "bolted.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert "must be re-qualified against the artifact" in str(exc.value)
    assert "cannot be attached to a run over another" in str(exc.value)


def test_a_partially_requalified_substitution_is_refused(materialized, tmp_path):
    """Re-qualifying S1 and forgetting S3 leaves the baselines misattributed."""
    substituted = {"S1_district": "M3", "S2_neighbour_district": "M30",
                   "S3_sector": "M3 7"}
    raw = _instance_dict(materialized)
    raw["governs_run"] = "partial"
    raw["substitutions"] = {
        "S1_district": {"geography": "M3", "justification": "why"},
        "S2_neighbour_district": {"geography": "M30", "justification": "why"},
        "S3_sector": {"geography": "M3 7", "justification": "why"},
    }
    block = _qualification_block(substituted)
    block["S3_sector"]["geography"] = "B5 4"   # forgotten
    raw["qualification"] = block
    path = tmp_path / "partial.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert "S3_sector" in str(exc.value)
    assert "re-qualified" in str(exc.value)


def test_a_qualification_entry_that_names_no_geography_is_refused(
        materialized, tmp_path):
    block = _qualification_block()
    block["S2_district"] = {"rule": "non-empty"}
    path = _write(tmp_path, materialized, qualification=block)
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert "does not record the geography it was measured over" in str(exc.value)


# --- structural geometry of a substitution ---------------------------------

@pytest.mark.parametrize("geographies,expected", [
    # S2 does not extend S1: two unrelated districts test nothing.
    ({"S1_district": "M3", "S2_neighbour_district": "B50", "S3_sector": "M3 7"},
     "does not extend"),
    # S2 equal to S1 is not longer.
    ({"S1_district": "M3", "S2_neighbour_district": "M3", "S3_sector": "M3 7"},
     "does not extend"),
    # S3 outside S1's district breaks both baseline relations.
    ({"S1_district": "M3", "S2_neighbour_district": "M30", "S3_sector": "B5 4"},
     "does not lie inside"),
    # S1 given as a sector: a district case needs a district.
    ({"S1_district": "M3 7", "S2_neighbour_district": "M30", "S3_sector": "M3 7"},
     "is not an outward code"),
    # S3 given as an outcode: S3 and S9 are sector cases.
    ({"S1_district": "M3", "S2_neighbour_district": "M30", "S3_sector": "M3"},
     "is not a sector"),
])
def test_a_substitution_breaking_the_corpus_geometry_is_refused(
        geographies, expected):
    """Substituting is permitted; substituting into a shape that tests nothing
    is not. Each of these is structurally well-formed and semantically empty.
    """
    from tools.ppd_snapshot.corpus import validate_definitional_geometry

    with pytest.raises(InstanceRefused) as exc:
        validate_definitional_geometry(geographies)
    assert expected in str(exc.value)


def test_the_default_definitional_geometry_satisfies_its_own_rules():
    """B5 / B50 / B5 4 -- the geometry every substitution is measured against."""
    from tools.ppd_snapshot.corpus import (
        DEFINITIONAL_GEOGRAPHIES, validate_definitional_geometry)

    validate_definitional_geometry(DEFINITIONAL_GEOGRAPHIES)


def test_a_geometrically_valid_substitution_is_accepted():
    from tools.ppd_snapshot.corpus import validate_substitutions

    resolved = validate_substitutions({
        "S1_district": {"geography": "M3", "justification": "r"},
        "S2_neighbour_district": {"geography": "M30", "justification": "r"},
        "S3_sector": {"geography": "M3 7", "justification": "r"},
    })
    assert resolved == {"S1_district": "M3", "S2_neighbour_district": "M30",
                        "S3_sector": "M3 7"}


def test_geometry_is_enforced_through_the_instance_loader(materialized, tmp_path):
    """End to end: a broken geometry is refused at load, not at run time."""
    raw = _instance_dict(materialized)
    raw["governs_run"] = "broken-geometry"
    raw["substitutions"] = {
        "S1_district": {"geography": "M3", "justification": "why"},
        "S2_neighbour_district": {"geography": "M30", "justification": "why"},
        "S3_sector": {"geography": "B5 4", "justification": "why"},
    }
    path = tmp_path / "geometry.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert "does not lie inside" in str(exc.value)


def test_qualify_re_measures_against_a_substitution(tmp_path):
    """The supported route: re-qualify, do not re-label.

    Every measurement in the candidate is taken over the substituted
    geographies, which is what makes a substituted Instance carry evidence
    about the run it governs.
    """
    rows = [row(f"T-M37-{i:03d}", "M3 7AA", "2026-05-04", 200_000 + i,
                town="MANCHESTER") for i in range(30)]
    rows += [row(f"T-M30-{i:03d}", "M30 4AA", "2026-05-04", 300_000 + i,
                 town="MANCHESTER") for i in range(40)]
    rows += [row("T-M37-CATB", "M3 7AB", "2026-05-04", 900_000,
                 ppd_category="B", town="MANCHESTER")]
    build_snapshot(tmp_path, rows, version="v20260828T194003Z")
    opened = s1.open_materialized(tmp_path)
    try:
        out = s1.qualify(opened, today=date(2026, 6, 15), substitutions={
            "S1_district": {"geography": "M3", "justification": "r"},
            "S2_neighbour_district": {"geography": "M30", "justification": "r"},
            "S3_sector": {"geography": "M3 7", "justification": "r"}})
    finally:
        opened.adapter.close()
    assert out["substituted"] is True
    assert out["definitional_geographies"]["S1_district"] == "M3"
    block = out["candidate_instance"]["qualification"]
    assert block["S1_district"]["geography"] == "M3"
    assert block["S2_district"]["geography"] == "M30"
    assert block["S3_sector"]["geography"] == "M3 7"
    assert block["S3_sector"]["inside_s1_district"] is True
    # Measured over M3, not B5: the baselines describe the substituted run.
    assert out["candidate_instance"]["aggregate_baselines"]["S1_full"] == 30
    assert block["S1_district"]["measured_neighbour_rows"] == 40


def test_the_runbook_does_not_invite_bolting_a_substitution_onto_old_evidence():
    """The shortcut the runbook must actively steer away from.

    Telling an operator to "add a substitutions block" would produce exactly
    the Instance the loader refuses -- complete-looking, and describing
    geographies the run will never touch.
    """
    body = RUNBOOK.read_text()
    assert "A substitution is a re-qualification, not an annotation" in body
    assert "qualify --substitutions" in body
    assert "geographies the run will never touch" in body


def test_the_runbook_documents_the_substitution_geometry_rules():
    body = RUNBOOK.read_text()
    for rule in ("extends", "lies **inside**", "test nothing",
                 "still look like numbers"):
        assert rule in body, f"the runbook omits the geometry rule: {rule}"


def test_the_runbook_documents_the_owner_decision_requirement():
    body = RUNBOOK.read_text()
    assert "the Instance must\nanswer the referral" in body or \
        "answer the referral" in body
    assert "owner_decision" in body
    assert 'Only `"accepted"` qualifies' in body


def test_the_runbook_documents_the_latency_pass_abort():
    body = RUNBOOK.read_text()
    assert "This applies to the latency pass too" in body
    assert "short of\nits thirty observations" in body or \
        "short of" in body


def test_the_qualify_cli_re_measures_against_the_substitutions_file(
        tmp_path, monkeypatch):
    """End to end through `main`, not just the function it calls.

    Testing `qualify(definitional=...)` directly leaves the CLI wiring
    unexercised: the flag could be parsed and then dropped, and the candidate
    would silently describe `B5` while the operator believed they had
    re-qualified against `M3`.
    """
    rows = [row(f"T-M37-{i:03d}", "M3 7AA", "2026-05-04", 200_000 + i,
                town="MANCHESTER") for i in range(30)]
    rows += [row(f"T-M30-{i:03d}", "M30 4AA", "2026-05-04", 300_000 + i,
                 town="MANCHESTER") for i in range(40)]
    rows += [row("T-M37-CATB", "M3 7AB", "2026-05-04", 900_000,
                 ppd_category="B", town="MANCHESTER")]
    build_snapshot(tmp_path, rows, version="v20260828T194003Z")
    subs = tmp_path / "subs.json"
    subs.write_text(json.dumps({"substitutions": {
        "S1_district": {"geography": "M3", "justification": "B50 too thin"},
        "S2_neighbour_district": {"geography": "M30", "justification": "ditto"},
        "S3_sector": {"geography": "M3 7", "justification": "inside M3"},
    }}))
    monkeypatch.setenv(s1.SHADOW_COMPARE_ENABLED_ENV, "1")
    out_path = tmp_path / "candidate.json"
    s1.main(["qualify", "--cache-dir", str(tmp_path),
             "--substitutions", str(subs), "--out", str(out_path)])
    out = json.loads(out_path.read_text())
    assert out["substituted"] is True
    assert out["definitional_geographies"]["S1_district"] == "M3"
    block = out["candidate_instance"]["qualification"]
    assert block["S1_district"]["geography"] == "M3"
    assert block["S2_district"]["geography"] == "M30"
    assert block["S3_sector"]["geography"] == "M3 7"


def test_the_qualify_cli_refuses_a_geometrically_broken_substitutions_file(
        tmp_path, monkeypatch):
    """Refused before anything is measured, with exit 2."""
    build_snapshot(tmp_path, _rows(), version="v20260828T194003Z")
    subs = tmp_path / "subs.json"
    subs.write_text(json.dumps({"substitutions": {
        "S1_district": {"geography": "M3", "justification": "r"},
        "S2_neighbour_district": {"geography": "M30", "justification": "r"},
        "S3_sector": {"geography": "B5 4", "justification": "r"},
    }}))
    monkeypatch.setenv(s1.SHADOW_COMPARE_ENABLED_ENV, "1")
    out_path = tmp_path / "candidate.json"
    code = s1.main(["qualify", "--cache-dir", str(tmp_path),
                    "--substitutions", str(subs), "--out", str(out_path)])
    assert code == 2
    assert not out_path.exists(), "a refused qualification still wrote output"


# ---------------------------------------------------------------------------
# The emitted candidate is a document the loader accepts
# ---------------------------------------------------------------------------

#: Inside the frozen 24-month window and inside the 6-month one.
RECENT = "2026-05-04"
#: Inside the 24-month window, outside the 6-month one -- which is what makes a
#: sector empty for S11 while still being a sector the artifact knows about.
OLDER = "2025-01-15"


def _fully_qualifiable_rows() -> list[dict]:
    """Rows that satisfy every qualification rule, so `qualify` emits a
    complete candidate.

    Each group exists for one placeholder, and the comments say which -- a
    fixture that qualifies by accident is one nobody can repair when a rule
    changes.
    """
    rows: list[dict] = []
    # The definitional trio, twice over: B5/B50/B5 4 and the M3/M30/M3 7 set a
    # substitution moves to. Both need S3 < S1 strictly and S9 > S3.
    for district, sector, neighbour in (("B5", "B5 4", "B50"),
                                        ("M3", "M3 7", "M30")):
        rows += [row(f"T-{sector}-{i:03d}", f"{sector}AA", RECENT, 200_000 + i)
                 for i in range(30)]
        rows.append(row(f"T-{sector}-CATB", f"{sector}AB", RECENT, 900_000,
                        ppd_category="B"))
        rows += [row(f"T-{neighbour}-{i:03d}", f"{neighbour} 4AA", RECENT,
                     400_000 + i) for i in range(60)]
        # A second, thin sector inside the district: S4, and it keeps S3 a
        # STRICT subset of S1 rather than equal to it.
        rows += [row(f"T-{district}6-{i}", f"{district} 6QQ", RECENT,
                     300_000 + i, property_type=t)
                 for i, t in enumerate("DSTF")]
    # S5 (dense, well past limit), S7 (>=90% F) and S6/S13 (a dense unit with
    # no D rows) all come from one deliberately large single-type sector.
    rows += [row(f"T-NG11-{i:03d}", "NG1 1AA", RECENT, 250_000 + i)
             for i in range(260)]
    # S8: a real spread across F/D/S/T with F well under half.
    rows += [row(f"T-NG21-{i:03d}", "NG2 1AA", RECENT, 260_000 + i,
                 property_type="FDST"[i % 4]) for i in range(60)]
    # S11: known to the artifact over 24 months, empty over 6.
    rows += [row(f"T-NG41-{i:03d}", "NG4 1AA", OLDER, 270_000 + i)
             for i in range(20)]
    return rows


def _emit_candidate(tmp_path, monkeypatch, substitutions=None) -> dict:
    """Run the CLI and return the candidate instance it wrote."""
    build_snapshot(tmp_path, _fully_qualifiable_rows(),
                   version="v20260828T194003Z")
    argv = ["qualify", "--cache-dir", str(tmp_path),
            "--out", str(tmp_path / "candidate.json")]
    if substitutions is not None:
        subs = tmp_path / "subs.json"
        subs.write_text(json.dumps({"substitutions": substitutions}))
        argv += ["--substitutions", str(subs)]
    monkeypatch.setenv(s1.SHADOW_COMPARE_ENABLED_ENV, "1")
    code = s1.main(argv)
    written = json.loads((tmp_path / "candidate.json").read_text())
    assert not written["unqualified_placeholders"], (
        f"the fixture does not qualify every placeholder: "
        f"{written['unqualified_placeholders']}")
    assert not written["unqualified_definitional_cases"], (
        written["unqualified_definitional_cases"])
    assert code in (0, 1)   # 1 only if adjudication is pending
    return written["candidate_instance"]

def test_a_cli_candidate_round_trips_into_a_loadable_substituted_instance(
        tmp_path, monkeypatch):
    """The acceptance test for the whole qualify -> review -> run path.

    Run the CLI against a substitution, take exactly what it wrote, change
    ONLY the two fields a reviewer is meant to fill in -- `governs_run`, and
    the owner decision where the neighbour falls short -- and load it. Then
    confirm the corpus actually executes the substituted trio.

    Everything else is used verbatim. If the tool emitted a document its own
    loader rejects, an operator would have to hand-reconstruct a block the tool
    had already validated, and any hand-reconstruction is a place for the
    evidence and the run to drift apart. Before this test the candidate carried
    substituted measurements and no `substitutions` key, so it was refused by
    the very check that exists to keep those two together.
    """
    candidate = _emit_candidate(tmp_path, monkeypatch, substitutions={
        "S1_district": {"geography": "M3",
                        "justification": "B50 too thin on this artifact"},
        "S2_neighbour_district": {"geography": "M30",
                                  "justification": "the longer neighbour of M3"},
        "S3_sector": {"geography": "M3 7", "justification": "inside M3"},
    })

    # The substitution survives into the candidate, justifications intact.
    assert candidate["substitutions"]["S1_district"]["geography"] == "M3"
    assert candidate["substitutions"]["S1_district"]["justification"] == (
        "B50 too thin on this artifact")
    assert set(candidate["substitutions"]) == {
        "S1_district", "S2_neighbour_district", "S3_sector"}

    # --- the only edits a reviewer makes -------------------------------------
    candidate["governs_run"] = "stage-1-substituted"
    if candidate["qualification"]["S1_district"]["comparable_or_greater"] is False:
        candidate["qualification"]["S1_district"]["owner_decision"] = {
            "decision": "accepted",
            "justification": "reviewed and accepted for this artifact",
        }

    instance_path = tmp_path / "instance.json"
    instance_path.write_text(json.dumps(candidate))
    opened = s1.open_materialized(tmp_path)
    try:
        loaded = s1.load_instance(instance_path, opened)
    finally:
        opened.adapter.close()

    assert loaded.governs_run == "stage-1-substituted"
    assert loaded.substitutions == {
        "S1_district": "M3", "S2_neighbour_district": "M30",
        "S3_sector": "M3 7"}

    # --- and the corpus executes the substituted trio ------------------------
    from tools.ppd_snapshot.corpus import cases as build

    shapes = {c.shape: (c.postcode, c.search_level)
              for c in build(loaded.geographies, loaded.substitutions)}
    assert shapes["S1"] == ("M3", "district")
    assert shapes["S2"] == ("M30", "district")
    assert shapes["S3"] == ("M3 7", "sector")
    assert shapes["S9"] == ("M3 7", "sector")
    assert shapes["S12"] == ("M3", "district")
    assert shapes["S14"] == ("M3 7", "sector")
    # Only the six shapes the definitional trio drives. The seven placeholders
    # are selected independently and may legitimately sit anywhere in the
    # artifact -- S4's thin sector here is `B5 6`, which is not a leftover.
    driven = ("S1", "S2", "S3", "S9", "S12", "S14")
    assert not any(shapes[shape][0].split()[0] in {"B5", "B50"}
                   for shape in driven), (
        f"a default B5/B50 geography survived into a substituted run: "
        f"{ {k: shapes[k] for k in driven} }")


def test_an_unsubstituted_candidate_round_trips_too(tmp_path, monkeypatch):
    """The same path with no substitution: no `substitutions` key is emitted."""
    candidate = _emit_candidate(tmp_path, monkeypatch)
    assert "substitutions" not in candidate
    candidate["governs_run"] = "stage-1-default"
    if candidate["qualification"]["S1_district"]["comparable_or_greater"] is False:
        candidate["qualification"]["S1_district"]["owner_decision"] = {
            "decision": "accepted", "justification": "reviewed"}
    path = tmp_path / "instance.json"
    path.write_text(json.dumps(candidate))
    opened = s1.open_materialized(tmp_path)
    try:
        loaded = s1.load_instance(path, opened)
    finally:
        opened.adapter.close()
    assert loaded.substitutions == {}
    from tools.ppd_snapshot.corpus import cases as build

    assert {c.shape: c.postcode
            for c in build(loaded.geographies, loaded.substitutions)}["S1"] == "B5"


# ---------------------------------------------------------------------------
# Measurements, baselines and geographies must be the same numbers
# ---------------------------------------------------------------------------

def test_a_measurement_disagreeing_with_its_baseline_is_refused(materialized,
                                                                tmp_path):
    """The same count over the same geography cannot be two numbers.

    Mutation: skip the cross-check and an Instance can name the right places
    while carrying a figure pasted from a previous run.
    """
    block = _qualification_block()
    block["S1_district"]["measured_rows"] = BASELINES["S1_full"] + 1
    path = _write(tmp_path, materialized, qualification=block)
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert "S1_full" in str(exc.value)
    assert "cannot be two numbers" in str(exc.value)


@pytest.mark.parametrize("field,baseline", [
    ("measured_rows", "S3_full"),
    ("measured_rows_category_all", "S9_full"),
])
def test_the_sector_measurements_must_match_their_baselines(
        materialized, tmp_path, field, baseline):
    block = _qualification_block()
    block["S3_sector"][field] = BASELINES[baseline] + 7
    path = _write(tmp_path, materialized, qualification=block)
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert baseline in str(exc.value)


def test_the_neighbour_count_must_agree_with_itself(materialized, tmp_path):
    """It appears twice -- as S2's measurement and as S1's ratio input."""
    block = _qualification_block()
    block["S2_district"]["measured_rows"] = NEIGHBOUR_ROWS + 5
    path = _write(tmp_path, materialized, qualification=block)
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert "same count over the same geography" in str(exc.value)


def test_a_ratio_edited_to_clear_the_rule_is_refused(materialized, tmp_path):
    """The most consequential single edit anyone could make to an Instance.

    Raising the ratio past 1.0 without moving the counts turns a case that
    needs an owner decision into one that appears to qualify outright.
    Mutation: trust the recorded ratio instead of recomputing it, and this
    Instance loads.
    """
    block = _shortfall_block()
    block["S1_district"]["measured_neighbour_ratio"] = 1.5
    block["S1_district"]["comparable_or_greater"] = True
    path = _write(tmp_path, materialized, qualification=block)
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert "must follow from the counts" in str(exc.value)


def test_comparability_asserted_against_the_measurement_is_refused(
        materialized, tmp_path):
    """`comparable_or_greater` decides whether a decision is required.

    Asserting it independently of the counts would let an Instance skip the
    adjudication entirely while every number beside it stayed honest.
    """
    block = _shortfall_block()
    block["S1_district"]["comparable_or_greater"] = True
    path = _write(tmp_path, materialized, qualification=block)
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert "may not be asserted independently of the measurement" in str(exc.value)


def test_the_neighbour_geography_must_be_the_effective_one(materialized,
                                                           tmp_path):
    """Otherwise the ratio describes a district the run does not use."""
    block = _qualification_block()
    block["S1_district"]["neighbour_geography"] = "M30"
    path = _write(tmp_path, materialized, qualification=block)
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert "the ratio would describe" in str(exc.value)


def test_a_false_inside_s1_district_claim_is_refused(materialized, tmp_path):
    block = _qualification_block()
    block["S3_sector"]["inside_s1_district"] = False
    path = _write(tmp_path, materialized, qualification=block)
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert "inside_s1_district" in str(exc.value)


@pytest.mark.parametrize("entry,field", [
    ("S1_district", "measured_rows"),
    ("S1_district", "measured_neighbour_rows"),
    ("S1_district", "measured_neighbour_ratio"),
    ("S2_district", "measured_rows"),
    ("S3_sector", "measured_rows"),
    ("S3_sector", "measured_rows_category_all"),
])
def test_a_missing_definitional_measurement_is_refused(materialized, tmp_path,
                                                       entry, field):
    """The baselines cannot be checked against a measurement not recorded."""
    block = _qualification_block()
    block[entry].pop(field)
    path = _write(tmp_path, materialized, qualification=block)
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert field in str(exc.value)


# ---------------------------------------------------------------------------
# Malformed substitution JSON refuses cleanly
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload", ["[]", '"a string"', "42", "null", "true",
                                     '{"substitutions": []}',
                                     '{"substitutions": "M3"}'])
def test_non_object_substitution_json_is_refused_with_exit_two(
        tmp_path, monkeypatch, payload):
    """A clean refusal, not an AttributeError traceback.

    `raw.get(...)` on a list or a string raises, and that reached the operator
    as a stack trace from inside the tool rather than a sentence saying what
    was wrong with their file.
    """
    build_snapshot(tmp_path, _rows(), version="v20260828T194003Z")
    subs = tmp_path / "subs.json"
    subs.write_text(payload)
    monkeypatch.setenv(s1.SHADOW_COMPARE_ENABLED_ENV, "1")
    out_path = tmp_path / "candidate.json"
    code = s1.main(["qualify", "--cache-dir", str(tmp_path),
                    "--substitutions", str(subs), "--out", str(out_path)])
    assert code == 2
    assert not out_path.exists(), "a refused qualification still wrote output"


def test_unreadable_substitution_json_is_refused_with_exit_two(
        tmp_path, monkeypatch):
    build_snapshot(tmp_path, _rows(), version="v20260828T194003Z")
    subs = tmp_path / "subs.json"
    subs.write_text("{not json at all")
    monkeypatch.setenv(s1.SHADOW_COMPARE_ENABLED_ENV, "1")
    code = s1.main(["qualify", "--cache-dir", str(tmp_path),
                    "--substitutions", str(subs),
                    "--out", str(tmp_path / "candidate.json")])
    assert code == 2


def test_a_missing_substitutions_file_is_refused_with_exit_two(
        tmp_path, monkeypatch):
    build_snapshot(tmp_path, _rows(), version="v20260828T194003Z")
    monkeypatch.setenv(s1.SHADOW_COMPARE_ENABLED_ENV, "1")
    code = s1.main(["qualify", "--cache-dir", str(tmp_path),
                    "--substitutions", str(tmp_path / "nope.json"),
                    "--out", str(tmp_path / "candidate.json")])
    assert code == 2


def test_a_non_object_substitutions_value_is_refused_by_the_validator():
    """Not by a second isinstance check in the CLI, which would be unreachable.

    Pins where the refusal comes from, so removing the validator's own guard
    fails here rather than silently relying on a CLI check that no longer
    exists.
    """
    from tools.ppd_snapshot.corpus import validate_substitutions

    for value in ([], "M3", 42, True):
        with pytest.raises(InstanceRefused) as exc:
            validate_substitutions(value)
        assert "must be a JSON object" in str(exc.value)


def test_the_runbook_says_the_candidate_is_taken_as_written():
    body = RUNBOOK.read_text()
    assert "justifications included" in body
    assert "hand-reconstructing any of it" in body


def test_the_runbook_documents_the_measurement_cross_checks():
    body = RUNBOOK.read_text()
    assert "must agree with each other" in body
    assert "recomputed from the counts" in body
    assert "most consequential edit" in body


# ---------------------------------------------------------------------------
# The rounding boundary
# ---------------------------------------------------------------------------

def test_comparability_is_decided_on_the_exact_ratio_not_the_rounded_one(
        materialized, tmp_path):
    """20,000 against 20,001: the regression this boundary exists to catch.

    The exact ratio is 0.99995 -- the neighbour is smaller, so it is NOT
    "comparable or greater" -- and it rounds to 1.0 at four decimals. Deciding
    from the rounded value put a rounding boundary inside a deployment gate:
    the loader would compute `True` while `qualify` recorded `False`, refusing
    a correct candidate, and would equally accept a hand-edited `True` that
    skips the owner decision altogether.

    Mutation: derive `expected_comparable` from the rounded ratio again and
    this fails in both directions below.
    """
    block = _qualification_block()
    block["S1_district"]["measured_rows"] = 20_001
    block["S1_district"]["measured_neighbour_rows"] = 20_000
    block["S1_district"]["measured_neighbour_ratio"] = round(20_000 / 20_001, 4)
    block["S1_district"]["comparable_or_greater"] = False
    block["S2_district"]["measured_rows"] = 20_000
    baselines = {**BASELINES, "S1_full": 20_001}

    # The recorded display field really does round to 1.0 -- the case is only
    # interesting because those two values differ.
    assert block["S1_district"]["measured_neighbour_ratio"] == 1.0
    assert (20_000 / 20_001) < s1.NEIGHBOUR_COMPARABLE_RATIO

    # `false` is correct here, and must load. Because the neighbour falls
    # short, the Instance must also answer the referral.
    block["S1_district"]["owner_decision"] = {
        "decision": "accepted",
        "justification": "one row short of parity; reviewed and accepted",
    }
    path = _write(tmp_path, materialized, qualification=block,
                  aggregate_baselines=baselines)
    assert s1.load_instance(path, materialized).governs_run

    # `true` is wrong here, and must be refused -- it would skip the decision.
    block["S1_district"]["comparable_or_greater"] = True
    block["S1_district"].pop("owner_decision")
    path = _write(tmp_path, materialized, qualification=block,
                  aggregate_baselines=baselines)
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert "may not be asserted independently of the measurement" in str(exc.value)


def test_the_other_side_of_the_boundary_is_comparable(materialized, tmp_path):
    """20,001 against 20,000 exceeds parity, so no decision is required."""
    block = _qualification_block()
    block["S1_district"]["measured_rows"] = 20_000
    block["S1_district"]["measured_neighbour_rows"] = 20_001
    block["S1_district"]["measured_neighbour_ratio"] = round(20_001 / 20_000, 4)
    block["S1_district"]["comparable_or_greater"] = True
    block["S2_district"]["measured_rows"] = 20_001
    path = _write(tmp_path, materialized, qualification=block,
                  aggregate_baselines={**BASELINES, "S1_full": 20_000,
                                       "S3_full": 40, "S9_full": 55})
    assert s1.load_instance(path, materialized).governs_run


def test_exact_parity_is_comparable(materialized, tmp_path):
    """"comparable or GREATER" -- equal volume qualifies."""
    block = _qualification_block()
    block["S1_district"]["measured_rows"] = 20_000
    block["S1_district"]["measured_neighbour_rows"] = 20_000
    block["S1_district"]["measured_neighbour_ratio"] = 1.0
    block["S1_district"]["comparable_or_greater"] = True
    block["S2_district"]["measured_rows"] = 20_000
    path = _write(tmp_path, materialized, qualification=block,
                  aggregate_baselines={**BASELINES, "S1_full": 20_000})
    assert s1.load_instance(path, materialized).governs_run


def test_the_display_ratio_is_still_validated_at_four_decimals(materialized,
                                                               tmp_path):
    """Rounding keeps its one job: checking the human-readable field.

    Dropping the exact ratio into that field instead would make the check
    reject every candidate `qualify` writes.
    """
    block = _qualification_block()
    block["S1_district"]["measured_rows"] = 20_001
    block["S1_district"]["measured_neighbour_rows"] = 20_000
    block["S1_district"]["measured_neighbour_ratio"] = 0.9999   # wrong rounding
    block["S1_district"]["comparable_or_greater"] = False
    block["S1_district"]["owner_decision"] = {"decision": "accepted",
                                              "justification": "reviewed"}
    block["S2_district"]["measured_rows"] = 20_000
    path = _write(tmp_path, materialized, qualification=block,
                  aggregate_baselines={**BASELINES, "S1_full": 20_001})
    with pytest.raises(InstanceRefused) as exc:
        s1.load_instance(path, materialized)
    assert "must follow from the counts" in str(exc.value)


def test_the_baselines_note_names_the_effective_geographies(materialized):
    """A substituted run's note must not claim B5 / B5 4.

    The note tells a reviewer which geographies the three baselines were
    counted over. Hard-coding the defaults made it wrong for exactly the runs
    where getting it right matters most.
    """
    default = s1.qualify(materialized)
    assert "B5" in default["baselines_note"]
    assert "B5 4" in default["baselines_note"]


def test_the_baselines_note_follows_a_substitution(tmp_path):
    rows = [row(f"T-M37-{i:03d}", "M3 7AA", "2026-05-04", 200_000 + i,
                town="MANCHESTER") for i in range(30)]
    rows += [row(f"T-M30-{i:03d}", "M30 4AA", "2026-05-04", 300_000 + i,
                 town="MANCHESTER") for i in range(40)]
    build_snapshot(tmp_path, rows, version="v20260828T194003Z")
    opened = s1.open_materialized(tmp_path)
    try:
        out = s1.qualify(opened, today=date(2026, 6, 15), substitutions={
            "S1_district": {"geography": "M3", "justification": "r"},
            "S2_neighbour_district": {"geography": "M30", "justification": "r"},
            "S3_sector": {"geography": "M3 7", "justification": "r"}})
    finally:
        opened.adapter.close()
    note = out["baselines_note"]
    assert "M3 7" in note and "M3" in note
    assert "B5" not in note, f"the note still claims a default geography: {note}"


def test_qualify_decides_comparability_on_the_exact_ratio(materialized,
                                                          monkeypatch):
    """The same boundary, on the writing side rather than the reading side.

    `qualify` and `load_instance` must agree at 20,000/20,001 or a correct
    candidate is refused by the tool that produced it. Reaching this through a
    real artifact would need 40,001 rows; the counts are substituted instead,
    which isolates exactly the arithmetic under test.

    Mutation: round the ratio before comparing it and `comparable_or_greater`
    flips to true, the adjudication disappears, and the shortfall is never put
    to anybody.
    """
    real = s1._aggregate

    def counted(m, *, geography_sql, geo_params, **kwargs):
        if geography_sql == "outcode = ?" and geo_params == ["B5"]:
            return 20_001
        if geography_sql == "outcode = ?" and geo_params == ["B50"]:
            return 20_000
        return real(m, geography_sql=geography_sql, geo_params=geo_params,
                    **kwargs)

    monkeypatch.setattr(s1, "_aggregate", counted)
    out = s1.qualify(materialized, today=date(2026, 6, 15))
    block = out["candidate_instance"]["qualification"]["S1_district"]
    assert block["measured_rows"] == 20_001
    assert block["measured_neighbour_rows"] == 20_000
    # The display field rounds to parity; the decision does not.
    assert block["measured_neighbour_ratio"] == 1.0
    assert block["comparable_or_greater"] is False, (
        "qualify treated a smaller neighbour as comparable because the ratio "
        "rounded to 1.0")
    assert "S1_district" in out["requires_owner_adjudication"]


def test_qualify_treats_exact_parity_as_comparable(materialized, monkeypatch):
    """The boundary is >=, so equal volume needs no adjudication."""
    real = s1._aggregate

    def counted(m, *, geography_sql, geo_params, **kwargs):
        if geography_sql == "outcode = ?" and geo_params in (["B5"], ["B50"]):
            return 20_000
        return real(m, geography_sql=geography_sql, geo_params=geo_params,
                    **kwargs)

    monkeypatch.setattr(s1, "_aggregate", counted)
    out = s1.qualify(materialized, today=date(2026, 6, 15))
    block = out["candidate_instance"]["qualification"]["S1_district"]
    assert block["comparable_or_greater"] is True
    assert "S1_district" not in out["requires_owner_adjudication"]


# ---------------------------------------------------------------------------
# The sparse tail: S4 and S11 (regression -- v1.18.0 selection defect)
#
# Both placeholders are defined by SCARCITY, and both were selected by
# filtering the dense `n DESC ... LIMIT 200` pool. On the real artifact that
# pool's floor was 368 rows against S4's ceiling of 5, so neither could ever be
# found: 155 thin sectors and 309 silent ones existed, none of them reachable.
#
# The fixture below reproduces that shape -- a dense population larger than the
# pool, with the valid candidates in the tail beneath it -- and every negative
# is built to WIN under the corresponding broken behaviour, so a test that
# passes cannot be passing by accident.
# ---------------------------------------------------------------------------

TODAY = date(2026, 9, 2)
COVERAGE_FROM = "2016-01-01"
COVERAGE_TO = "2026-06-30"
PROVISIONAL_FROM = "2026-03-01"


def _bounds(months: int, coverage_from: str = COVERAGE_FROM,
            coverage_to: str = COVERAGE_TO) -> tuple[str, str]:
    """The window through the real function, so fixture dates cannot drift.

    `_clamped_window` reads `coverage_from` and `coverage_to` and nothing else,
    so a `Materialized` carrying no adapter answers it exactly as a real one
    would -- and if that ever stops being true, every test here fails loudly
    rather than quietly measuring a different window from the query.
    """
    m = s1.Materialized(adapter=None, version="v20260828T194003Z",
                        bundle_sha256="0" * 64, coverage_from=coverage_from,
                        coverage_to=coverage_to,
                        provisional_from=PROVISIONAL_FROM, directory=Path("."))
    return s1._clamped_window(m, months, TODAY)


SIX_LOWER, WINDOW_UPPER = _bounds(6)
M24_LOWER, _ = _bounds(24)


def _shift(iso: str, days: int) -> str:
    return (date.fromisoformat(iso) + timedelta(days=days)).isoformat()


#: Inside the six-month window: disqualifies a sector from S11.
IN_SIX = _shift(SIX_LOWER, 30)
#: One day before the inclusive lower bound: does NOT disqualify.
DAY_BEFORE_SIX = _shift(SIX_LOWER, -1)
#: Comfortably inside 24 months, outside six.
WELL_BEFORE_SIX = _shift(SIX_LOWER, -60)
#: Outside the 24-month window entirely, but inside coverage.
OUTSIDE_24M = _shift(M24_LOWER, -30)

#: More than the 200 `_rank` returns, each denser than every sparse candidate,
#: so the valid S4/S11 cases are provably outside the pool.
FILLER_SECTORS = 205
FILLER_ROWS_EACH = 12


def _sparse_tail_rows() -> list[dict]:
    rows: list[dict] = []

    # -- dense filler: >200 sectors, all active inside the six-month window so
    #    none of them can become an S11 candidate.
    for i in range(FILLER_SECTORS):
        rows += [row(f"T-F{i:03d}-{j:02d}", f"ZZ{i:03d} 1AA", IN_SIX)
                 for j in range(FILLER_ROWS_EACH)]

    # -- S5 / S6 / S7 / S13: one very dense sector at one very dense unit.
    rows += [row(f"T-DA-{i:03d}", "DA1 1AA", IN_SIX, 200_000 + i)
             for i in range(260)]
    # -- S8: >= LIMIT rows with a real spread and F not dominant.
    for i in range(60):
        rows.append(row(f"T-DB-{i:03d}", "DB2 2AA", IN_SIX, 300_000 + i,
                        property_type="FFDDSSTT"[i % 8] if i % 8 < 2 else
                        ("F", "F", "D", "D", "S", "S", "T", "T")[i % 8]))

    # -- definitional B5 / B50 / B5 4, so qualify() can exit 0.
    rows += [row(f"T-B54A-{i:03d}", "B5 4AA", IN_SIX, 210_000 + i)
             for i in range(30)]
    rows += [row(f"T-B54B-{i:03d}", "B5 4AB", IN_SIX, 900_000 + i,
                 ppd_category="B") for i in range(10)]
    rows += [row(f"T-B57-{i:03d}", "B5 7AA", IN_SIX, 220_000 + i)
             for i in range(20)]
    rows += [row(f"T-B50-{i:03d}", "B50 4AA", IN_SIX, 400_000 + i)
             for i in range(55)]

    # -- S4 valid: three qualifying rows, in the tail.
    rows += [row(f"T-THIN-{i}", "YA1 1AA", WELL_BEFORE_SIX) for i in range(3)]

    # -- S4 negatives. FOUR rows each and sectors sorting before `YA1 1`, so a
    #    broken filter does not merely admit them -- it makes them WIN.
    rows += [row(f"T-NCAT-{i}", "XA1 1AA", WELL_BEFORE_SIX, ppd_category="B")
             for i in range(4)]
    rows += [row(f"T-NTYP-{i}", "XA2 2AA", WELL_BEFORE_SIX, property_type="O")
             for i in range(4)]
    rows += [row(f"T-NDAT-{i}", "XA3 3AA", OUTSIDE_24M) for i in range(4)]

    # -- S11 valid: eight rows, the most recent exactly one day before the
    #    inclusive lower bound, plus non-qualifying rows INSIDE the window.
    #    Correct filtering ignores those; a dropped category or type filter
    #    makes this sector fail and `ZC1 1` win instead.
    rows += [row(f"T-Q-{i}", "YB2 2AA", DAY_BEFORE_SIX) for i in range(8)]
    rows += [row(f"T-QCAT-{i}", "YB2 2AB", IN_SIX, ppd_category="B")
             for i in range(2)]
    rows += [row(f"T-QTYP-{i}", "YB2 2AC", IN_SIX, property_type="O")
             for i in range(2)]

    # -- S11 boundary negative: ten rows -- more than the valid eight, sorting
    #    earlier -- one of them EXACTLY on the lower bound. `>=` rejects it;
    #    an off-by-one `>` would qualify it and it would outrank the valid case.
    rows += [row(f"T-ONB-{i}", "XB1 1AA", WELL_BEFORE_SIX) for i in range(9)]
    rows.append(row("T-ONB-BOUND", "XB1 1AA", SIX_LOWER))

    # -- the named wrong answer: legitimately silent, but ranked below.
    rows += [row(f"T-ZC-{i}", "ZC1 1AA", WELL_BEFORE_SIX) for i in range(6)]
    return rows


@pytest.fixture(scope="module")
def sparse_tail(tmp_path_factory):
    """~2.9k rows over 214 sectors. Built once: it is the expensive fixture."""
    root = tmp_path_factory.mktemp("sparse-tail")
    build_snapshot(root, _sparse_tail_rows(), version="v20260828T194003Z",
                   coverage_from=COVERAGE_FROM, coverage_to=COVERAGE_TO,
                   provisional_from=PROVISIONAL_FROM)
    opened = s1.open_materialized(root)
    yield opened
    opened.adapter.close()


def test_the_dense_pool_does_not_contain_the_thin_or_empty_candidates(
        sparse_tail):
    """The defect's precondition, pinned.

    If this ever fails the later assertions stop proving anything: they would
    be satisfied by the old pool-filtering code too.
    """
    pool = dict(s1._rank(sparse_tail, "sector", months=24, today=TODAY))
    assert len(pool) == 200, "the pool is the capped dense ranking"
    for tail_sector in ("YA1 1", "YB2 2", "XB1 1", "ZC1 1"):
        assert tail_sector not in pool, (
            f"{tail_sector} is inside the dense pool; the fixture no longer "
            f"reproduces the defect")
    assert min(pool.values()) > 10, "the pool floor must exceed every candidate"


def test_qualify_selects_a_thin_sector_outside_the_dense_pool(sparse_tail):
    out = s1.qualify(sparse_tail, today=TODAY)
    geo = out["candidate_instance"]["geographies"]
    assert geo["S4_thin"] == "YA1 1"
    assert out["candidate_instance"]["qualification"][
        "S4_thin"]["measured_rows"] == 3


def test_qualify_selects_a_provisional_empty_sector_outside_the_dense_pool(
        sparse_tail):
    out = s1.qualify(sparse_tail, today=TODAY)
    geo = out["candidate_instance"]["geographies"]
    entry = out["candidate_instance"]["qualification"]["S11_provisional_empty"]
    assert geo["S11_provisional_empty"] == "YB2 2"
    assert entry["measured_rows"] == 0
    assert entry["window_intersects_provisional"] is True


def test_every_placeholder_is_qualified_and_qualify_exits_zero(
        sparse_tail, tmp_path, monkeypatch):
    """The assertion the suite never made, and the one the defect would fail.

    No fixture in this module has ever produced a complete qualification, which
    is exactly why two unreachable placeholders shipped.
    """
    out = s1.qualify(sparse_tail, today=TODAY)
    assert out["unqualified_placeholders"] == []
    assert out["unqualified_definitional_cases"] == []
    assert out["requires_owner_adjudication"] == []
    assert out["baselines_satisfy_their_relations"] is True
    assert set(out["candidate_instance"]["geographies"]) == set(
        s1.REQUIRED_GEOGRAPHIES)


def test_selection_is_deterministic_under_ties(sparse_tail):
    first = s1.qualify(sparse_tail, today=TODAY)["candidate_instance"]
    second = s1.qualify(sparse_tail, today=TODAY)["candidate_instance"]
    assert first == second


def test_s4_enforces_strictly_below_the_thin_threshold(sparse_tail):
    """`0 < n < threshold`, both ends."""
    thin = s1._rank(sparse_tail, "sector", months=24, today=TODAY,
                    having=f"HAVING count(*) < {s1.THIN_MARKET_THRESHOLD}",
                    limit=10_000)
    assert thin, "no thin sector selected at all"
    for _, n in thin:
        assert 0 < n < s1.THIN_MARKET_THRESHOLD


def test_s4_ignores_wrong_category_type_and_out_of_window_rows(sparse_tail):
    """Each negative holds FOUR rows against the valid three and sorts earlier.

    Mutation: drop the category, property-type or lower-bound filter from
    `_rank` and the corresponding negative is selected instead -- it wins on
    count, so this cannot pass by luck.
    """
    out = s1.qualify(sparse_tail, today=TODAY)
    assert out["candidate_instance"]["geographies"]["S4_thin"] == "YA1 1"
    pool = dict(s1._rank(sparse_tail, "sector", months=24, today=TODAY,
                         limit=10_000))
    for excluded in ("XA1 1", "XA2 2", "XA3 3"):
        assert excluded not in pool, (
            f"{excluded} survived the frozen filters and would outrank YA1 1")


def test_s11_requires_activity_in_24m_and_silence_in_6m(sparse_tail):
    out = s1.qualify(sparse_tail, today=TODAY)
    chosen = out["candidate_instance"]["geographies"]["S11_provisional_empty"]
    pool = dict(s1._rank(sparse_tail, "sector", months=24, today=TODAY,
                         limit=10_000))
    # Active over 24 months.
    assert pool[chosen] > 0
    # Silent over the clamped six-month window.
    assert s1._aggregate(sparse_tail, geography_sql="sector = ?",
                         geo_params=[chosen], months=6, today=TODAY) == 0
    # A sector active inside the window is never chosen.
    assert chosen != "DA1 1"


def test_s11_category_and_type_rows_in_window_do_not_disqualify(sparse_tail):
    """`YB2 2` carries category-B and type-`O` rows inside the six-month window.

    Correct filtering ignores them and the sector qualifies. Drop either filter
    and it is disqualified, and `ZC1 1` -- the next silent sector -- is chosen
    instead. This is a false-NEGATIVE guard: a dropped filter counts more rows,
    so it can only ever remove a candidate, never manufacture one.
    """
    out = s1.qualify(sparse_tail, today=TODAY)
    assert out["candidate_instance"]["geographies"][
        "S11_provisional_empty"] == "YB2 2", (
        "expected YB2 2; ZC1 1 means a category or property-type filter was "
        "dropped and the non-qualifying in-window rows were counted")


@pytest.mark.parametrize("months, coverage_from, expect_lower", [
    # The derived bound sits inside coverage: returned unchanged.
    (6, "2016-01-01", "2026-03-06"),
    (24, "2016-01-01", "2024-09-12"),
    # Coverage edge: the derived bound precedes coverage_from, narrowed UP.
    (6, "2026-06-01", "2026-06-01"),
    (24, "2026-06-01", "2026-06-01"),
])
def test_clamped_window_returns_the_documented_bounds(
        months, coverage_from, expect_lower):
    """`max(today - months*30, coverage_from)` and `coverage_to`.

    The clamp only ever narrows, which is why no selector that got it wrong
    could produce a false positive -- the failure mode it guards is the
    opposite one.
    """
    lower, upper = _bounds(months, coverage_from=coverage_from)
    assert lower == expect_lower
    assert upper == COVERAGE_TO
    assert lower >= coverage_from


def test_s11_rejects_a_row_exactly_on_the_six_month_lower_bound(sparse_tail):
    """The bound is inclusive: a row dated exactly on it is IN the window.

    Mutation: weaken the FILTER to `>` and `XB1 1` -- ten rows against the
    valid eight, sorting earlier -- qualifies and is selected instead.
    """
    out = s1.qualify(sparse_tail, today=TODAY)
    geo = out["candidate_instance"]["geographies"]
    assert geo["S11_provisional_empty"] == "YB2 2"

    # The on-bound sector was a live candidate, and was rejected for its row
    # rather than being absent for some unrelated reason.
    pool = dict(s1._rank(sparse_tail, "sector", months=24, today=TODAY,
                         limit=10_000))
    assert pool["XB1 1"] == 10
    assert geo["S11_provisional_empty"] != "XB1 1"
    assert s1._aggregate(sparse_tail, geography_sql="sector = ?",
                         geo_params=["XB1 1"], months=6, today=TODAY) == 1


def test_dense_placeholder_selections_are_unchanged(sparse_tail, materialized):
    """The dense pool and its five placeholders are untouched by this fix."""
    geo = s1.qualify(sparse_tail, today=TODAY)["candidate_instance"][
        "geographies"]
    assert geo["S5_dense"] == "DA1 1"
    assert geo["S6_unit"] == "DA1 1AA"
    assert geo["S7_type_weak"] == "DA1 1"
    assert geo["S8_type_strong"] == "DB2 2"
    assert geo["S13_empty_unit"] == "DA1 1AA"

    # And on the pre-existing fixture the dense selections are what they were:
    # only `B5 7AA` clears MIN_UNIT_POSTCODE_ROWS there.
    legacy = s1.qualify(materialized, today=TODAY)["candidate_instance"][
        "geographies"]
    assert legacy["S6_unit"] == "B5 7AA"
    assert legacy["S13_empty_unit"] == "B5 7AA"


# ---------------------------------------------------------------------------
# Live-arm diagnostics: status, allow-listed headers and request timing
#
# The first authorised Stage 1 run recorded `"HTTPError: HTTP Error 429: Too
# Many Requests"` and nothing else. The status, the reason and any `Retry-After`
# were on the exception at that moment and were discarded, so the question the
# failure raised -- how long before the next authorised run -- could not be
# answered from the evidence. Everything below is synthetic; the module's
# `_no_network` fixture hard-fails sockets.
# ---------------------------------------------------------------------------

def _http_error(status=429, reason="Too Many Requests", headers=None, body=None):
    """A real `urllib.error.HTTPError`, shaped like the one Stage 1 hit."""
    import io
    import urllib.error
    from http.client import HTTPMessage

    message = HTTPMessage()
    for name, value in (headers or {}).items():
        message[name] = value
    return urllib.error.HTTPError(
        "https://landregistry.example.invalid/sparql", status, reason, message,
        io.BytesIO(body if body is not None else b""))


class RaisingSeamLive:
    """`comps()` fails *through the transport seam the capture wraps*.

    The point of the exercise: a 429 raises out of the transport rather than
    returning, so a wrapper that only records on the way back records nothing
    about the one case that needs explaining. Driving the failure through
    `search_with_evidence` is what proves the capture sees it.
    """

    def __init__(self):
        self.calls = 0

    def comps(self, **kwargs):
        from property_core.ppd_client import PricePaidDataClient

        self.calls += 1
        client = PricePaidDataClient.__new__(PricePaidDataClient)
        return PricePaidDataClient.search_with_evidence(client, **kwargs)


@pytest.fixture
def seam_raises(monkeypatch):
    """Make the wrapped transport method raise, before the capture wraps it."""
    def _install(exc):
        from property_core.ppd_client import PricePaidDataClient

        def _raiser(self, **kwargs):
            raise exc

        monkeypatch.setattr(PricePaidDataClient, "search_with_evidence", _raiser)
        return RaisingSeamLive()

    return _install


# -- 1. a synthetic 429 with allowed headers is recorded ---------------------

def test_a_429_records_its_status_reason_and_allowed_headers(
        materialized, instance, tmp_path, monkeypatch, seam_raises):
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    live = seam_raises(_http_error(headers={
        "Retry-After": "120",
        "RateLimit-Limit": "100",
        "RateLimit-Remaining": "0",
        "X-RateLimit-Reset": "1756820000",
    }))
    report = _run(materialized, instance, tmp_path, monkeypatch, live=live,
                  latency_repeats=1, stop_on_unclassified=False)

    assert report["passed"] is False
    entry = report["live_errors"][0]
    assert entry["status"] == 429
    assert entry["reason"] == "Too Many Requests"
    assert entry["headers"] == {
        "retry-after": "120",
        "ratelimit-limit": "100",
        "ratelimit-remaining": "0",
        "x-ratelimit-reset": "1756820000",
    }

    failed = [c for c in report["cases"] if "live_error_detail" in c][-1]
    assert failed["live_error_detail"]["status"] == 429
    assert failed["live_error_detail"]["headers"]["retry-after"] == "120"


def test_a_non_http_failure_records_null_status_and_no_headers(
        materialized, instance, tmp_path, monkeypatch, seam_raises):
    """A timeout is a different fact from a status of zero."""
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    live = seam_raises(TimeoutError("timed out"))
    report = _run(materialized, instance, tmp_path, monkeypatch, live=live,
                  latency_repeats=1, stop_on_unclassified=False)

    entry = report["live_errors"][0]
    assert entry["status"] is None
    assert entry["reason"] is None
    assert entry["headers"] == {}
    assert entry["type"] == "TimeoutError"


# -- 2. arbitrary headers and the response body are excluded -----------------

def test_arbitrary_headers_and_the_response_body_are_never_retained(
        materialized, instance, tmp_path, monkeypatch, seam_raises):
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    live = seam_raises(_http_error(headers={
        "Retry-After": "60",
        "Set-Cookie": "session=SECRET-SESSION-VALUE",
        "Authorization": "Bearer SECRET-TOKEN",
        "Server": "upstream-internal-hostname",
        "X-Request-Id": "0123456789",
        "Content-Type": "application/json",
    }, body=b'{"rows":[{"transaction_id":"SECRET-TXN","price":123456}]}'))
    report = _run(materialized, instance, tmp_path, monkeypatch, live=live,
                  latency_repeats=1, stop_on_unclassified=False)

    assert report["live_errors"][0]["headers"] == {"retry-after": "60"}
    serialized = json.dumps(report)
    for forbidden in ("SECRET-SESSION-VALUE", "SECRET-TOKEN", "SECRET-TXN",
                      "upstream-internal-hostname", "set-cookie", "Set-Cookie",
                      "authorization", "Authorization", "123456",
                      "0123456789", "application/json"):
        assert forbidden not in serialized, f"leaked {forbidden!r} into the report"


def test_the_header_allow_list_is_exactly_the_three_documented_shapes():
    kept = s1.allowed_response_headers({
        "Retry-After": "1", "RateLimit-Policy": "2", "X-RateLimit-Used": "3",
        "Retry-After-Ms": "4", "Cookie": "5", "X-Rate-Limit": "6",
    })
    assert kept == {"retry-after": "1", "ratelimit-policy": "2",
                    "x-ratelimit-used": "3"}


def test_missing_headers_are_an_empty_mapping_not_a_null():
    assert s1.allowed_response_headers(None) == {}
    assert s1.allowed_response_headers({}) == {}


def test_a_retained_header_value_is_bounded():
    kept = s1.allowed_response_headers({"Retry-After": "9" * 5000})
    assert len(kept["retry-after"]) == s1.LIVE_ERROR_HEADER_VALUE_MAX


def test_describing_an_error_never_reads_the_response_body():
    class Exploding:
        code = 429
        reason = "Too Many Requests"
        headers = {"Retry-After": "30"}

        def read(self, *a, **k):
            raise AssertionError("the response body must never be read")

    detail = s1.describe_live_error(Exploding())
    assert detail["status"] == 429
    assert detail["headers"] == {"retry-after": "30"}


# -- 3. one observation, no retry, abort, partial report still written -------

def test_a_429_consumes_one_observation_is_not_retried_and_aborts(
        materialized, instance, tmp_path, monkeypatch, seam_raises):
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    live = seam_raises(_http_error(headers={"Retry-After": "120"}))
    report = _run(materialized, instance, tmp_path, monkeypatch, live=live,
                  latency_repeats=1, stop_on_unclassified=False)

    assert live.calls == 1, "the failed live observation was retried"
    assert report["limits"]["live_calls_made"] == 1
    assert report["aborted"]
    assert "no later case runs" in report["aborted"]
    assert len(report["live_errors"]) == 1
    assert report["cases_compared"] == 0


def test_the_partial_report_is_still_written_to_disk(
        materialized, instance, tmp_path, monkeypatch, seam_raises):
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    live = seam_raises(_http_error(headers={"Retry-After": "120"}))
    _run(materialized, instance, tmp_path, monkeypatch, live=live,
         latency_repeats=1, stop_on_unclassified=False)

    written = json.loads((tmp_path / "report.json").read_text())
    assert written["live_errors"][0]["status"] == 429
    assert written["live_errors"][0]["headers"] == {"retry-after": "120"}


# -- 4. successful records keep the transport evidence they always had -------

def test_the_capture_still_records_transport_evidence_on_success(monkeypatch):
    """The success path is unchanged: the same three fields, from the same seam."""
    from property_core.ppd_client import PricePaidDataClient, SearchPage

    page = SearchPage(transactions=[],
                      evidence=TransportEvidence(raw_bindings_returned=7,
                                                 fetch_limit=50))
    monkeypatch.setattr(PricePaidDataClient, "search_with_evidence",
                        lambda self, **kwargs: page)

    with s1.LiveEvidenceCapture() as capture:
        client = PricePaidDataClient.__new__(PricePaidDataClient)
        PricePaidDataClient.search_with_evidence(client, postcode="B5 7")

    assert capture.last == {"raw_bindings_returned": 7, "fetch_limit": 50,
                            "source_exhausted": True}
    assert capture.last_error is None
    assert capture.truncation_evidenced is False


def test_the_capture_records_a_failure_and_re_raises_it_untouched(monkeypatch):
    """Observing a failure must not change what the caller sees, or retry it."""
    from property_core.ppd_client import PricePaidDataClient

    boom = _http_error(headers={"Retry-After": "90", "Set-Cookie": "s=SECRET"})
    calls = []

    def _raiser(self, **kwargs):
        calls.append(kwargs)
        raise boom

    monkeypatch.setattr(PricePaidDataClient, "search_with_evidence", _raiser)

    with s1.LiveEvidenceCapture() as capture:
        client = PricePaidDataClient.__new__(PricePaidDataClient)
        with pytest.raises(type(boom)) as caught:
            PricePaidDataClient.search_with_evidence(client, postcode="B5 7")

    assert caught.value is boom, "the exception was replaced, not re-raised"
    assert len(calls) == 1, "the capture retried the failed request"
    assert capture.last_error["status"] == 429
    assert capture.last_error["headers"] == {"retry-after": "90"}


def test_a_successful_run_records_no_failure_detail(
        materialized, instance, tmp_path, monkeypatch):
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    report = _run(materialized, instance, tmp_path, monkeypatch,
                  latency_repeats=1, stop_on_unclassified=False)

    for case in report["cases"]:
        assert "transport_evidence" in case["live"]
        assert "live_error_detail" not in case
    assert report["live_errors"] == []


# -- 5. timing permits spacing between live requests to be calculated --------

def test_every_live_observation_records_when_it_started_and_finished(
        materialized, instance, tmp_path, monkeypatch):
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    report = _run(materialized, instance, tmp_path, monkeypatch,
                  latency_repeats=1, stop_on_unclassified=False)

    from datetime import datetime

    stamps = []
    for case in report["cases"]:
        timing = case["live_timing"]
        assert set(timing) == {"started_at", "finished_at", "elapsed_ms",
                               "outcome"}
        assert timing["outcome"] == "ok"
        started = datetime.fromisoformat(timing["started_at"])
        finished = datetime.fromisoformat(timing["finished_at"])
        assert started.tzinfo is not None and finished >= started
        stamps.append((started, finished))

    # The whole point: spacing between consecutive live requests is computable.
    assert len(stamps) == 13
    spacings = [(stamps[i][0] - stamps[i - 1][1]).total_seconds()
                for i in range(1, len(stamps))]
    assert all(gap >= 0 for gap in spacings)


def test_a_failed_live_observation_is_also_timed(
        materialized, instance, tmp_path, monkeypatch, seam_raises):
    """Without this the one request worth explaining is the one with no clock."""
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    live = seam_raises(_http_error(headers={"Retry-After": "120"}))
    report = _run(materialized, instance, tmp_path, monkeypatch, live=live,
                  latency_repeats=1, stop_on_unclassified=False)

    timing = report["cases"][-1]["live_timing"]
    assert timing["outcome"] == "error"
    assert timing["started_at"] and timing["finished_at"]
    assert isinstance(timing["elapsed_ms"], float)


# -- 6. the budget guard is untouched ---------------------------------------

def test_the_live_budget_guard_still_refuses_beyond_one_per_case(
        materialized, instance, tmp_path, monkeypatch):
    limits = s1.RunLimits(max_live_per_case=1)
    with pytest.raises(s1.RunAborted, match="live-call budget"):
        s1.check_live_budget(13, limits, 13, "S14")
    # Under budget, it does not refuse.
    s1.check_live_budget(12, limits, 13, "S14")


def test_instrumentation_did_not_change_the_live_call_count(
        materialized, instance, tmp_path, monkeypatch):
    monkeypatch.setattr(s1, "health_ok", lambda *a, **k: (True, "200"))
    live = FakeLive()
    report = _run(materialized, instance, tmp_path, monkeypatch, live=live,
                  latency_repeats=5, stop_on_unclassified=False)
    assert len(live.calls) == 13
    assert report["limits"]["live_calls_made"] == 13


def test_the_comparator_never_retries_or_backs_off_a_live_failure():
    """No sleep-and-reissue may appear on the live path.

    `Retry-After` is captured so a human can pace the NEXT authorised run. A
    run that honours it by waiting and re-issuing has made a second live
    observation for one case, which is the rule this gate exists to hold.
    """
    source = (REPO / "tools" / "ppd_snapshot" / "stage1_shadow.py").read_text()
    for forbidden in ("retry_live", "max_retries", "backoff", "tenacity",
                      "while attempt", "for attempt"):
        assert forbidden not in source, f"a retry mechanism appeared: {forbidden!r}"
