"""Tests for the read-only Fly observability collector.

The collector is an operator script, not a package module, so it is loaded by
path. Every test here drives it through injected transports — a fake Prometheus
`fetch` and a fake `flyctl` runner — so the suite never touches the network,
never shells out, and never needs a Fly token.

The negative tests carry most of the weight. This script exists to produce
evidence for a production rollout gate, so the failure modes that would quietly
corrupt that evidence — a missing series rendering as `0`, one dead command
erasing the rest of the report, a token reaching disk — are the ones asserted
hardest.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "fly_observability_snapshot.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("fly_observability_snapshot", _MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


fos = _load_module()

FAKE_TOKEN = "fm2_lJPECAAAAAAAtesttokenvalue0000000000000xyz"


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------


def _vector(*samples: tuple[dict[str, str], str]) -> dict[str, Any]:
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {"metric": labels, "value": [1788221858, value]} for labels, value in samples
            ],
        },
    }


_EMPTY_VECTOR = {"status": "success", "data": {"resultType": "vector", "result": []}}


class FakeFetch:
    """Stands in for the HTTP transport. Records every call it is given."""

    def __init__(self, responses: dict[str, Any] | None = None, default: Any = None) -> None:
        self.responses = responses or {}
        self.default = default if default is not None else _EMPTY_VECTOR
        self.calls: list[dict[str, Any]] = []

    def __call__(self, url: str, headers: dict[str, str], timeout: float) -> tuple[int, bytes]:
        self.calls.append({"url": url, "headers": dict(headers), "timeout": timeout})
        for needle, response in self.responses.items():
            if needle in url:
                if isinstance(response, Exception):
                    raise response
                status, payload = response
                return status, json.dumps(payload).encode()
        return 200, json.dumps(self.default).encode()


class FakeRunner:
    """Stands in for subprocess execution of `flyctl`."""

    def __init__(self, results: dict[str, tuple[int, str, str]] | None = None) -> None:
        self.results = results or {}
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str], timeout: float) -> tuple[int, str, str]:
        self.calls.append(list(argv))
        for needle, result in self.results.items():
            if needle in " ".join(argv):
                return result
        return 0, "{}", ""


def _collector(fetch: Any = None, runner: Any = None, **kwargs: Any) -> Any:
    return fos.Collector(
        app="property-shared",
        org="personal",
        window="30m",
        token=FAKE_TOKEN,
        fetch=fetch or FakeFetch(),
        runner=runner or FakeRunner(),
        **kwargs,
    )


# --------------------------------------------------------------------------
# Zero versus no_data — the distinction the whole report depends on
# --------------------------------------------------------------------------


def test_empty_prometheus_result_is_no_data_not_zero() -> None:
    """An absent series must never be reportable as the number 0."""
    spec = fos.MetricSpec(
        key="app_concurrency",
        title="App concurrency",
        promql='fly_app_concurrency{app="property-shared"}',
        unit="connections",
    )

    result = fos.parse_instant_response(spec, _EMPTY_VECTOR)

    assert result.status == "no_data"
    assert result.samples == []
    assert result.value is None


def test_zero_valued_sample_is_reported_as_a_real_zero() -> None:
    """A genuine 0 reading is data, and must survive as 0.0 with status ok."""
    spec = fos.MetricSpec(
        key="load5",
        title="Load average (5m)",
        promql='fly_instance_load_average{app="property-shared",minutes="5"}',
        unit="load",
    )
    payload = _vector(({"app": "property-shared", "minutes": "5"}, "0"))

    result = fos.parse_instant_response(spec, payload)

    assert result.status == "ok"
    assert result.value == 0.0
    assert result.samples[0]["value"] == 0.0


def test_markdown_renders_no_data_distinctly_from_zero() -> None:
    """The rendered report must not let a gap read as a measurement."""
    zero = fos.SeriesResult(
        key="load5", title="Load average (5m)", promql="q", unit="load",
        status="ok", samples=[{"labels": {}, "value": 0.0}], value=0.0,
    )
    missing = fos.SeriesResult(
        key="app_concurrency", title="App concurrency", promql="q", unit="connections",
        status="no_data", samples=[], value=None,
    )

    rendered = fos.render_markdown(
        fos.build_report(
            app="property-shared", org="personal", window="30m",
            started_at="2026-09-01T12:00:00Z", ended_at="2026-09-01T12:00:04Z",
            series=[zero, missing], commands=[], logs=None, notes=[],
        )
    )

    assert "no_data" in rendered
    load_line = next(ln for ln in rendered.splitlines() if "Load average (5m)" in ln)
    conc_line = next(ln for ln in rendered.splitlines() if "App concurrency" in ln)
    assert "0" in load_line
    assert "no_data" in conc_line
    assert "0" not in conc_line.split("no_data")[0].split("|")[-1]


# --------------------------------------------------------------------------
# Partial failure must stay partial
# --------------------------------------------------------------------------


def test_http_failure_on_one_series_does_not_erase_the_others() -> None:
    fetch = FakeFetch(
        responses={
            "fly_instance_memory_mem_available": (503, {"error": "upstream down"}),
        },
        default=_vector(({"app": "property-shared"}, "1"),),
    )
    collector = _collector(fetch=fetch)

    results = collector.collect_series()
    by_key = {r.key: r for r in results}
    failed = [r for r in results if r.status == "error"]
    succeeded = [r for r in results if r.status == "ok"]

    assert failed, "expected the injected 503 to surface as a typed error entry"
    assert succeeded, "one failed series must not erase the rest of the report"
    assert all(r.value is None for r in failed)
    assert any("503" in (r.error or "") for r in failed)
    assert "memory_available" in by_key


def test_transport_exception_becomes_a_typed_error_entry() -> None:
    fetch = FakeFetch(
        responses={"fly_instance_cpu": OSError("connection reset by peer")},
        default=_EMPTY_VECTOR,
    )
    collector = _collector(fetch=fetch)

    results = collector.collect_series()
    errored = [r for r in results if r.status == "error"]

    assert errored
    assert any("connection reset" in (r.error or "") for r in errored)


def test_prometheus_error_status_is_an_error_not_no_data() -> None:
    spec = fos.MetricSpec(key="k", title="T", promql="q", unit="u")
    payload = {"status": "error", "errorType": "bad_data", "error": "invalid expression"}

    result = fos.parse_instant_response(spec, payload)

    assert result.status == "error"
    assert "invalid expression" in (result.error or "")
    assert result.value is None


def test_malformed_flyctl_json_is_reported_not_crashed_on() -> None:
    runner = FakeRunner(results={"status": (0, "not json at all {{{", "")})
    collector = _collector(runner=runner)

    commands = collector.collect_commands()
    status_entry = next(c for c in commands if c["key"] == "status")

    assert status_entry["status"] == "error"
    assert "json" in status_entry["error"].lower()
    assert status_entry["data"] is None
    assert any(c["status"] == "ok" for c in commands), "other commands must still run"


def test_failing_flyctl_command_is_reported_with_its_exit_code() -> None:
    runner = FakeRunner(results={"image show": (1, "", "Error: no access to app")})
    collector = _collector(runner=runner)

    commands = collector.collect_commands()
    entry = next(c for c in commands if c["key"] == "image")

    assert entry["status"] == "error"
    assert "no access to app" in entry["error"]


# --------------------------------------------------------------------------
# Token safety
# --------------------------------------------------------------------------


def test_token_never_appears_in_rendered_report_or_json() -> None:
    fetch = FakeFetch(default=_vector(({"app": "property-shared"}, "1")))
    collector = _collector(fetch=fetch)

    report = collector.run()
    as_json = json.dumps(report)
    as_markdown = fos.render_markdown(report)

    assert FAKE_TOKEN not in as_json
    assert FAKE_TOKEN not in as_markdown
    assert "fm2_" not in as_json
    assert "fm2_" not in as_markdown


def test_token_is_never_passed_as_a_command_argument() -> None:
    runner = FakeRunner()
    collector = _collector(runner=runner)

    collector.collect_commands()

    for argv in runner.calls:
        joined = " ".join(argv)
        assert FAKE_TOKEN not in joined
        assert "fm2_" not in joined


def test_token_is_sent_only_as_an_in_memory_authorization_header() -> None:
    fetch = FakeFetch()
    collector = _collector(fetch=fetch)

    collector.collect_series()

    assert fetch.calls
    for call in fetch.calls:
        assert FAKE_TOKEN not in call["url"]
        assert call["headers"]["Authorization"] == f"FlyV1 {FAKE_TOKEN}"


def test_token_leaked_into_an_exception_is_redacted_before_it_is_stored() -> None:
    """urllib puts the failing URL in the exception; a token must not ride along."""
    leaky = RuntimeError(f"failed calling https://api.fly.io/x?token={FAKE_TOKEN}")
    fetch = FakeFetch(responses={"fly_instance_cpu": leaky}, default=_EMPTY_VECTOR)
    collector = _collector(fetch=fetch)

    results = collector.collect_series()
    blob = json.dumps([r.to_dict() for r in results])

    assert FAKE_TOKEN not in blob
    assert "fm2_" not in blob
    assert fos.REDACTION_PLACEHOLDER in blob


def test_redact_removes_macaroon_tokens_it_was_not_told_about() -> None:
    other = "FlyV1 fm2_lJPECAAAAAAAsomeothertokenvalue999"
    scrubbed = fos.redact(f"boom: {other}", secrets=[FAKE_TOKEN])

    assert "fm2_" not in scrubbed
    assert fos.REDACTION_PLACEHOLDER in scrubbed


# --------------------------------------------------------------------------
# Read-only enforcement
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["deploy"],
        ["secrets", "set", "PPD_SNAPSHOT_ENABLED=1"],
        ["machine", "update", "7849207a412608"],
        ["scale", "count", "2"],
        ["apps", "destroy", "property-shared"],
        ["ssh", "console"],
    ],
)
def test_mutating_fly_subcommands_are_refused(argv: list[str]) -> None:
    with pytest.raises(fos.ReadOnlyViolation):
        fos.assert_read_only(argv)


@pytest.mark.parametrize(
    "argv",
    [
        ["status", "--json"],
        ["checks", "list", "--json"],
        ["image", "show", "--json"],
        ["logs", "--json", "--no-tail"],
    ],
)
def test_documented_read_only_commands_are_allowed(argv: list[str]) -> None:
    fos.assert_read_only(argv)


def test_every_command_the_collector_issues_is_read_only() -> None:
    runner = FakeRunner()
    collector = _collector(runner=runner, include_logs=25)

    collector.collect_commands()

    assert runner.calls
    for argv in runner.calls:
        fos.assert_read_only([a for a in argv if a not in ("fly", "flyctl")])


# --------------------------------------------------------------------------
# Error percentages, derived values, provenance
# --------------------------------------------------------------------------


def test_error_percentage_is_paired_with_absolute_counts() -> None:
    responses = {
        "5xx": (200, _vector(({"status": "500"}, "3"))),
        "responses_total": (200, _vector(({}, "200"))),
    }
    summary = fos.summarise_http_errors(error_count=3.0, total_count=200.0)

    assert summary["error_count"] == 3.0
    assert summary["total_count"] == 200.0
    assert summary["error_pct"] == pytest.approx(1.5)
    assert responses  # fixture kept adjacent to the arithmetic it describes


def test_error_percentage_with_no_traffic_is_no_data_not_zero_percent() -> None:
    summary = fos.summarise_http_errors(error_count=0.0, total_count=0.0)

    assert summary["error_pct"] is None
    assert summary["status"] == "no_data"
    assert summary["total_count"] == 0.0


def test_derived_series_declare_their_derivation_and_promql() -> None:
    derived = [s for s in fos.SERIES if s.derived]

    assert derived, "free rootfs bytes is computed from blocks * block size"
    for spec in derived:
        assert spec.derivation, f"{spec.key} is derived but does not say how"
        assert spec.promql


def test_report_records_the_provenance_of_every_series() -> None:
    for spec in fos.SERIES:
        assert spec.provenance in {"fly_builtin", "app_custom"}


def test_no_series_is_sourced_from_the_missing_fleet_dashboard() -> None:
    """The BOUCH MCP Fleet dashboard was not found; nothing may claim it."""
    assert all(s.provenance != "dashboard" for s in fos.SERIES)
    assert fos.DASHBOARD_GAP_NOTE


# --------------------------------------------------------------------------
# Timestamps, window, schema, output
# --------------------------------------------------------------------------


def test_report_records_utc_query_start_and_end_and_the_window() -> None:
    report = fos.build_report(
        app="property-shared", org="personal", window="30m",
        started_at="2026-09-01T12:00:00Z", ended_at="2026-09-01T12:00:04Z",
        series=[], commands=[], logs=None, notes=[],
    )

    assert report["query"]["started_at"].endswith("Z")
    assert report["query"]["ended_at"].endswith("Z")
    assert report["query"]["window"] == "30m"
    assert report["schema_version"] == fos.SCHEMA_VERSION


def test_report_has_a_stable_top_level_schema() -> None:
    report = fos.build_report(
        app="a", org="o", window="30m",
        started_at="2026-09-01T12:00:00Z", ended_at="2026-09-01T12:00:04Z",
        series=[], commands=[], logs=None, notes=[],
    )

    assert set(report) == {
        "schema_version", "target", "query", "series", "commands", "logs", "notes",
    }


def test_writing_a_report_refuses_to_overwrite_an_existing_one(tmp_path: Path) -> None:
    """Before/after comparison is worthless if the baseline can be clobbered."""
    out = tmp_path / "baseline.json"
    out.write_text('{"schema_version": "1"}')

    with pytest.raises(FileExistsError):
        fos.write_outputs({"schema_version": "1"}, out, force=False)

    assert out.read_text() == '{"schema_version": "1"}'


def test_writing_a_report_creates_both_json_and_markdown(tmp_path: Path) -> None:
    out = tmp_path / "run.json"
    report = fos.build_report(
        app="property-shared", org="personal", window="30m",
        started_at="2026-09-01T12:00:00Z", ended_at="2026-09-01T12:00:04Z",
        series=[], commands=[], logs=None, notes=[],
    )

    written = fos.write_outputs(report, out, force=False)

    assert out.exists()
    assert out.with_suffix(".md").exists()
    assert set(written) == {out, out.with_suffix(".md")}


# --------------------------------------------------------------------------
# Logs are opt-in and bounded
# --------------------------------------------------------------------------


def test_logs_are_not_collected_by_default() -> None:
    runner = FakeRunner()
    collector = _collector(runner=runner)

    report = collector.run()

    assert report["logs"] is None
    assert not any("logs" in " ".join(argv) for argv in runner.calls)


def test_logs_when_requested_are_bounded_and_flagged_sensitive() -> None:
    log_lines = "\n".join(
        json.dumps({"timestamp": f"t{i}", "message": f"line {i}", "instance": "abc"})
        for i in range(50)
    )
    runner = FakeRunner(results={"logs": (0, log_lines, "")})
    collector = _collector(runner=runner, include_logs=10)

    report = collector.run()

    assert report["logs"] is not None
    assert report["logs"]["sensitive"] is True
    assert report["logs"]["requested_lines"] == 10
    assert len(report["logs"]["lines"]) == 10


# --------------------------------------------------------------------------
# Log stream parsing
# --------------------------------------------------------------------------

# Verified against `fly logs --json --no-tail -a property-shared` on 2026-09-01:
# the output is a stream of *pretty-printed* JSON objects, one after another —
# neither JSON-lines nor a JSON array. Splitting on newlines yields fragments
# like `"URL": {`, which is what an earlier revision of this collector stored.
_REAL_LOG_STREAM = """{
    "level": "info",
    "instance": "7849207a412608",
    "message": "INFO:     172.16.33.82:40526 - \\"POST /mcp HTTP/1.1\\" 202 Accepted",
    "region": "lhr",
    "timestamp": "2026-09-01T00:24:11.037797623Z",
    "meta": {
        "Instance": "7849207a412608",
        "HTTP": {"Request": {"ID": "", "Method": ""}}
    }
}
{
    "level": "info",
    "instance": "7849207a412608",
    "message": "Terminating session: None",
    "region": "lhr",
    "timestamp": "2026-09-01T00:24:11.038296725Z",
    "meta": {"Instance": "7849207a412608"}
}
"""


def test_pretty_printed_concatenated_json_log_stream_is_parsed() -> None:
    records = fos.parse_log_stream(_REAL_LOG_STREAM)

    assert len(records) == 2
    assert records[0]["message"].startswith("INFO:")
    assert records[1]["message"] == "Terminating session: None"
    assert records[0]["instance"] == "7849207a412608"


def test_log_lines_are_whole_records_not_newline_fragments() -> None:
    """The bug this guards: `"URL": {` stored as if it were a log message."""
    runner = FakeRunner(results={"logs": (0, _REAL_LOG_STREAM, "")})
    collector = _collector(runner=runner, include_logs=5)

    logs = collector.collect_logs()

    assert logs is not None
    assert logs["status"] == "ok"
    assert len(logs["lines"]) == 2
    for line in logs["lines"]:
        assert "message" in line
        assert not line["message"].strip().endswith("{")
        assert "timestamp" in line


def test_log_records_keep_only_selected_fields() -> None:
    """`meta` carries nested request detail that has no place in the report."""
    runner = FakeRunner(results={"logs": (0, _REAL_LOG_STREAM, "")})
    collector = _collector(runner=runner, include_logs=5)

    logs = collector.collect_logs()

    assert logs is not None
    for line in logs["lines"]:
        assert set(line) <= {"timestamp", "level", "instance", "region", "message"}
    assert "meta" not in json.dumps(logs["lines"])


def test_unparseable_log_output_is_reported_rather_than_silently_empty() -> None:
    runner = FakeRunner(results={"logs": (0, "totally not json", "")})
    collector = _collector(runner=runner, include_logs=5)

    logs = collector.collect_logs()

    assert logs is not None
    assert logs["status"] == "error"
    assert logs["error"]
    assert logs["lines"] == []


# --------------------------------------------------------------------------
# Field selection — flyctl payloads must be reduced, not dumped
# --------------------------------------------------------------------------


def test_checks_payload_keyed_by_machine_id_is_field_selected() -> None:
    """`fly checks list --json` returns {machine_id: [check, ...]}, not a list."""
    raw = {
        "7849207a412608": [
            {
                "name": "servicecheck-00-http-8080",
                "status": "passing",
                "output": '{"status":"ok"}',
                "updated_at": "2026-08-31T23:08:10.528Z",
                "unexpected_future_field": "must not be carried through",
            }
        ]
    }

    selected = fos._select_fields("checks", raw)

    assert selected == [
        {
            "machine": "7849207a412608",
            "name": "servicecheck-00-http-8080",
            "status": "passing",
            "output": '{"status":"ok"}',
        }
    ]


def test_image_payload_as_a_list_is_field_selected() -> None:
    """`fly image show --json` returns a list of image records."""
    raw = [
        {
            "Digest": "sha256:5c1c4039",
            "Labels": '{"GH_SHA":"176c401"}',
            "MachineID": "7849207a412608",
            "Registry": "registry.fly.io",
            "Repository": "property-shared",
            "Tag": "deployment-01M1D17A8J7WME8FKCDA8NK33W",
            "Version": "N/A",
            "SomeFutureSecretField": "must not be carried through",
        }
    ]

    selected = fos._select_fields("image", raw)

    assert isinstance(selected, list)
    assert "SomeFutureSecretField" not in selected[0]
    assert selected[0]["Digest"] == "sha256:5c1c4039"
    assert selected[0]["MachineID"] == "7849207a412608"


def test_machine_environment_is_never_carried_into_the_report() -> None:
    """A Machine's config carries its whole env; the report must not."""
    raw = {
        "Name": "property-shared",
        "Machines": [
            {
                "id": "7849207a412608",
                "state": "started",
                "region": "lhr",
                "config": {
                    "image": "registry.fly.io/property-shared:deployment-x",
                    "env": {"PPD_SNAPSHOT_S3_SECRET_ACCESS_KEY": "super-secret-value"},
                },
            }
        ],
    }

    selected = fos._select_fields("status", raw)

    assert "super-secret-value" not in json.dumps(selected)
    assert "env" not in json.dumps(selected)
    assert selected["machines"][0]["image"] == "registry.fly.io/property-shared:deployment-x"


def test_an_unrecognised_payload_shape_is_dropped_rather_than_dumped() -> None:
    """Selection is enforced: an unknown shape yields nothing, not everything."""
    selected = fos._select_fields("image", {"AnythingAtAll": "including secrets"})

    assert "including secrets" not in json.dumps(selected)


def test_single_sample_info_series_renders_its_identifying_labels() -> None:
    """Machine identity is carried in labels; a bare `1` is useless evidence."""
    info = fos.SeriesResult(
        key="instance_info", title="Machine identity", promql="q", unit="info",
        status="ok", value=1.0,
        samples=[{
            "labels": {
                "app": "property-shared", "instance": "7849207a412608",
                "memory_mb": "2048", "cpu_kind": "shared", "region": "lhr",
            },
            "value": 1.0,
        }],
    )

    rendered = fos.render_markdown(
        fos.build_report(
            app="property-shared", org="personal", window="30m",
            started_at="2026-09-01T12:00:00Z", ended_at="2026-09-01T12:00:04Z",
            series=[info], commands=[], logs=None, notes=[],
        )
    )

    assert "7849207a412608" in rendered
    assert "memory_mb=2048" in rendered


# --------------------------------------------------------------------------
# Live collection — one bounded, read-only run against the real app
# --------------------------------------------------------------------------


@pytest.mark.skipif(os.getenv("RUN_LIVE_TESTS") != "1", reason="Set RUN_LIVE_TESTS=1")
def test_live_collection_against_property_shared(tmp_path: Path) -> None:
    """One bounded read-only collection. Touches no secrets and no state.

    Skips rather than fails when no Fly token is available, so a developer
    without Fly access still gets a green suite.
    """
    try:
        token = fos.resolve_token()
    except RuntimeError as exc:
        pytest.skip(f"no Fly token available: {exc}")

    collector = fos.Collector(
        app="property-shared", org="personal", window="30m", token=token
    )
    try:
        report = collector.run()
    except OSError as exc:
        pytest.skip(f"Fly API unavailable: {exc}")

    assert report["schema_version"] == fos.SCHEMA_VERSION
    statuses = {s["key"]: s["status"] for s in report["series"]}

    # Something must have been measured, or the run proved nothing.
    assert any(v == "ok" for v in statuses.values()), statuses

    # The Machine is up and its rootfs is reported: the two readings Phase D
    # depends on. A collector that silently returned an empty report would
    # otherwise pass every offline test in this file.
    assert statuses["instance_up"] == "ok"
    assert statuses["rootfs_free_bytes"] == "ok"

    written = fos.write_outputs(report, tmp_path / "live.json", force=False)
    for path in written:
        assert "fm2_" not in path.read_text()
