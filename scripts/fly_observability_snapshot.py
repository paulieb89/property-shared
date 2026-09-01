"""Read-only observability snapshot for a Fly.io app.

Replaces dashboard screenshots with repeatable, timestamped evidence: one
invocation writes a stable-schema JSON report plus a Markdown interpretation,
so a before/during/after comparison is a diff rather than a memory of what a
graph looked like.

Two sources, both read-only:

  * documented `flyctl` JSON commands (`status`, `checks list`, `image show`,
    and — only when asked for — a bounded `logs --no-tail`);
  * Fly's Prometheus-compatible HTTP API at
    `https://api.fly.io/prometheus/<org>/api/v1/{query,query_range}`.

Every metric name and every PromQL expression in `SERIES` was verified against
the live API for `app="property-shared"` on 2026-09-01 before being written
here (see `DASHBOARD_GAP_NOTE` for what was deliberately *not* included).

Three properties this script exists to hold, because the evidence is worthless
without them:

  1. **`0` and "no data" are different answers.** An absent series is reported
     as `no_data` with a null value, never as zero. `fly_app_concurrency` has
     no series for this app, and a report that renders that as `0 connections`
     is a lie about idle traffic. The same applies to NaN and ±Inf, which the
     API really does return and which `float()` accepts without complaint: a
     quantile over a histogram with no traffic is `NaN`, not a latency.
  2. **Partial failure stays partial.** One dead command or one unavailable
     series becomes a typed entry in the report; it never aborts the run and
     never silently becomes a number.
  3. **The token never lands anywhere.** It is read into memory, used only as
     an `Authorization` header, and scrubbed out of every string — including
     exception text — before anything is written or printed.

What this collector does *not* measure: transient disk during a short
operation. See `TRANSIENT_DISK_NOTE` — Fly stores one sample every 15 s, so
these figures corroborate the verifier's own 0.2 s sampling rather than
standing in for it.

Usage:
    uv run python scripts/fly_observability_snapshot.py \\
        --app property-shared --org personal --window 30m \\
        --output docs/ops/evidence/2026-09-01-baseline.json

    # opt in to a bounded, sanitised log excerpt
    ... --include-logs 50

Auth: reads `FLY_API_TOKEN` or `FLY_ACCESS_TOKEN` if set, otherwise captures
`fly auth token` into memory. The token is never passed as a command argument.
The `Authorization` scheme depends on the token type, so it is negotiated once
per run and cached; `--auth-scheme` pins it. The negotiated scheme is recorded
in the report, the token never is.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import string
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

SCHEMA_VERSION = "1"
PROMETHEUS_BASE = "https://api.fly.io/prometheus"
REDACTION_PLACEHOLDER = "<redacted>"
DEFAULT_TIMEOUT = 30.0

# The Authorization scheme depends on the *token type*, not on the endpoint.
# Verified 2026-09-01: a macaroon from `fly auth token` (fm2_...) is accepted
# as `FlyV1 <token>` and rejected 401 as `Bearer <token>` — with the message
# "something went wrong resolving organization", which reads like a
# permissions problem rather than an auth-scheme one. Tokens minted by
# `fly tokens create` take the other scheme. Only one token type has been
# observed here, so the scheme is negotiated once per run and cached rather
# than hard-coded; `--auth-scheme` overrides the negotiation.
AUTH_SCHEMES: tuple[str, ...] = ("FlyV1", "Bearer")

# Fly's stored resolution, measured on 2026-09-01 with
# `timestamp(fly_instance_filesystem_blocks_free{...})` over a range query:
# consecutive distinct sample timestamps are exactly 15 s apart, for both the
# built-in instance metrics and the app's own scraped metrics.
FLY_SCRAPE_INTERVAL_SECONDS = 15

DASHBOARD_GAP_NOTE = (
    "No Grafana dashboard titled 'BOUCH MCP Fleet' is checked in anywhere under "
    "the mcpfleet workspace; the only checked-in dashboard is "
    "monitoring/grafana-dashboard.json ('Property Shared API'), whose PromQL "
    "targets metric names that do not exist in Fly's Prometheus "
    "(http_request_duration_seconds_*, http_requests_inprogress, "
    "http_response_size_bytes_*, external_request_duration_seconds_*). That "
    "dashboard is written for a prometheus_fastapi_instrumentator naming scheme "
    "the deployed app does not use. No series here is sourced from it. The "
    "app_custom series below are taken from the live Fly label index and from "
    "the checked-in definitions in app/core/metrics.py, not from any dashboard."
)

Fetch = Callable[[str, dict[str, str], float], "tuple[int, bytes]"]
Runner = Callable[["list[str]", float], "tuple[int, str, str]"]


class ReadOnlyViolation(RuntimeError):
    """Raised when a flyctl invocation is not on the read-only allowlist."""


# ---------------------------------------------------------------------------
# Read-only enforcement
# ---------------------------------------------------------------------------

# Allowlist rather than a denylist: a new mutating flyctl verb must not become
# permitted just because nobody remembered to forbid it.
READ_ONLY_COMMANDS: tuple[tuple[str, ...], ...] = (
    ("status",),
    ("checks", "list"),
    ("image", "show"),
    ("logs",),
    ("version",),
)


def assert_read_only(argv: Sequence[str]) -> None:
    """Allow only documented read-only flyctl invocations.

    `argv` excludes the `fly`/`flyctl` binary itself.
    """
    words = [a for a in argv if not a.startswith("-")]
    for allowed in READ_ONLY_COMMANDS:
        if tuple(words[: len(allowed)]) == allowed:
            return
    raise ReadOnlyViolation(
        f"refusing to run non-read-only flyctl command: {' '.join(argv)!r}"
    )


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

# Fly macaroons are `fm2_...`, optionally behind the `FlyV1` scheme word. Both
# shapes are scrubbed even when the caller did not name the token, because the
# leak that matters is the one nobody anticipated — urllib, for instance, puts
# the failing URL into the exception it raises.
_TOKEN_PATTERNS = (
    re.compile(r"FlyV1\s+\S+"),
    re.compile(r"\bfm[12]_[A-Za-z0-9_\-=]+"),
)


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    """Remove known secrets and anything macaroon-shaped from `text`."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, REDACTION_PLACEHOLDER)
    for pattern in _TOKEN_PATTERNS:
        text = pattern.sub(REDACTION_PLACEHOLDER, text)
    return text


# ---------------------------------------------------------------------------
# Metric specifications
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetricSpec:
    """One series to collect.

    `promql` is a `string.Template` with `$app`, `$window` and `$prefix`
    placeholders, so the braces of a PromQL label matcher need no escaping.
    """

    key: str
    title: str
    promql: str
    unit: str
    kind: str = "instant"
    provenance: str = "fly_builtin"
    derived: bool = False
    derivation: str = ""
    note: str = ""

    def render(self, *, app: str, window: str, prefix: str) -> str:
        return string.Template(self.promql).safe_substitute(
            app=app, window=window, prefix=prefix
        )


_FS_FREE = (
    'fly_instance_filesystem_blocks_free{app="$app"} '
    '* fly_instance_filesystem_block_size{app="$app"}'
)

SERIES: tuple[MetricSpec, ...] = (
    # -- identity and liveness -------------------------------------------
    MetricSpec(
        key="instance_up",
        title="Instance up",
        promql='fly_instance_up{app="$app"}',
        unit="bool",
    ),
    MetricSpec(
        key="instance_info",
        title="Machine identity",
        promql='fly_instance_info{app="$app"}',
        unit="info",
        note="Labels carry instance (Machine ID), cpu_kind, cpu_count, memory_mb, process_group.",
    ),
    MetricSpec(
        key="instance_uptime_seconds",
        title="Instance uptime",
        promql='fly_instance_uptime_seconds{app="$app"}',
        unit="seconds",
        note="Resets on Machine restart — the cheapest check that a restart actually happened.",
    ),
    MetricSpec(
        key="scrape_up",
        title="Metrics scrape up",
        promql='up{app="$app"}',
        unit="bool",
        note="0 here means Fly could not scrape the app's /metrics; app_custom series then go stale.",
    ),
    # -- concurrency and load --------------------------------------------
    MetricSpec(
        key="app_concurrency",
        title="App concurrency",
        promql='fly_app_concurrency{app="$app"}',
        unit="connections",
        note=(
            "Verified absent for property-shared and propertydata on 2026-09-01 while "
            "present for five other fleet apps. Expect no_data, and do not read it as zero."
        ),
    ),
    MetricSpec(
        key="load_average_5m",
        title="Load average (5m)",
        promql='fly_instance_load_average{app="$app",minutes="5"}',
        unit="load",
    ),
    MetricSpec(
        key="load_average_5m_peak",
        title="Load average (5m) peak over window",
        promql='max_over_time(fly_instance_load_average{app="$app",minutes="5"}[$window])',
        unit="load",
        derived=True,
        derivation="max_over_time over the collection window of the kernel 5-minute load average.",
    ),
    # -- CPU ---------------------------------------------------------------
    MetricSpec(
        key="cpu_busy_pct",
        title="CPU busy",
        promql=(
            '100 * (1 - sum(rate(fly_instance_cpu{app="$app",mode="idle"}[$window])) '
            '/ sum(rate(fly_instance_cpu{app="$app"}[$window])))'
        ),
        unit="percent",
        derived=True,
        derivation=(
            "100 * (1 - idle_rate / total_rate) across all cpu modes and cpu_ids over the window."
        ),
    ),
    MetricSpec(
        key="cpu_throttle",
        title="CPU throttle",
        promql='fly_instance_cpu_throttle{app="$app"}',
        unit="count",
    ),
    # -- memory ------------------------------------------------------------
    MetricSpec(
        key="memory_total",
        title="Machine memory total",
        promql='fly_instance_memory_mem_total{app="$app"}',
        unit="bytes",
    ),
    MetricSpec(
        key="memory_available",
        title="Machine memory available",
        promql='fly_instance_memory_mem_available{app="$app"}',
        unit="bytes",
    ),
    MetricSpec(
        key="memory_available_min",
        title="Machine memory available, minimum over window",
        promql='min_over_time(fly_instance_memory_mem_available{app="$app"}[$window])',
        unit="bytes",
        derived=True,
        derivation="min_over_time of MemAvailable over the window — the Machine-wide low-water mark.",
        note="This is the G1a Machine-wide available-memory figure, not process RSS.",
    ),
    MetricSpec(
        key="instance_exit_oom",
        title="OOM exits",
        promql='fly_instance_exit_oom{app="$app"}',
        unit="count",
        note="Absent unless an OOM kill has occurred; no_data here is the healthy reading.",
    ),
    # -- root filesystem (the G1a disk constraint) -------------------------
    MetricSpec(
        key="rootfs_free_bytes",
        title="Root filesystem free",
        promql=_FS_FREE,
        unit="bytes",
        derived=True,
        derivation="blocks_free * block_size, per mount. Mount label identifies the filesystem.",
        note=(
            "Fly's ephemeral rootfs reports as mount /.fly-upper-layer. This is the free-space "
            "figure the snapshot preflight (bundle_bytes * 2.5) is measured against."
        ),
    ),
    MetricSpec(
        key="rootfs_free_bytes_min",
        title="Root filesystem free, minimum over window",
        promql=(
            f"min_over_time(({_FS_FREE})[$window:{FLY_SCRAPE_INTERVAL_SECONDS}s])"
        ),
        unit="bytes",
        derived=True,
        derivation=(
            "min_over_time of (blocks_free * block_size) on the same mount, sampled at "
            f"{FLY_SCRAPE_INTERVAL_SECONDS}s (Fly's real stored resolution) over the "
            "window. This is the free-space low-water mark, nothing more. The "
            "additional space a run consumed is baseline_free - minimum_free on that "
            "mount — see summarise_transient_disk(). It is NOT total_bytes - "
            "minimum_free, which is total disk in use including the image and "
            "everything already present."
        ),
        note=(
            f"Corroborating only. At {FLY_SCRAPE_INTERVAL_SECONDS}s resolution a "
            "materialisation lasting ~20 s yields one or two samples and its true peak "
            "can fall entirely between them. The verifier's own 0.2 s directory "
            "sampling is the authoritative transient-disk measurement."
        ),
    ),
    MetricSpec(
        key="rootfs_total_bytes",
        title="Root filesystem total",
        promql=(
            'fly_instance_filesystem_blocks{app="$app"} '
            '* fly_instance_filesystem_block_size{app="$app"}'
        ),
        unit="bytes",
        derived=True,
        derivation="blocks * block_size, per mount.",
    ),
    # -- network -----------------------------------------------------------
    MetricSpec(
        key="net_recv_bytes_rate",
        title="Network received",
        promql='sum(rate(fly_instance_net_recv_bytes{app="$app",device="eth0"}[$window]))',
        unit="bytes/sec",
        derived=True,
        derivation="rate() of the eth0 counter over the window, summed.",
    ),
    MetricSpec(
        key="net_sent_bytes_rate",
        title="Network sent",
        promql='sum(rate(fly_instance_net_sent_bytes{app="$app",device="eth0"}[$window]))',
        unit="bytes/sec",
        derived=True,
        derivation="rate() of the eth0 counter over the window, summed.",
    ),
    # -- HTTP: Fly proxy, app side and edge side ---------------------------
    MetricSpec(
        key="app_http_responses_by_status",
        title="App HTTP responses by status",
        promql='sum by (status) (increase(fly_app_http_responses_count{app="$app"}[$window]))',
        unit="responses",
        derived=True,
        derivation="increase() of the Fly proxy app-side response counter over the window, by status.",
    ),
    MetricSpec(
        key="edge_http_responses_by_status",
        title="Edge HTTP responses by status",
        promql='sum by (status) (increase(fly_edge_http_responses_count{app="$app"}[$window]))',
        unit="responses",
        derived=True,
        derivation="increase() of the Fly edge response counter over the window, by status.",
        note="Edge series carry no instance label — they are per-PoP, not per-Machine.",
    ),
    MetricSpec(
        key="app_http_p95",
        title="App HTTP p95 latency",
        promql=(
            "histogram_quantile(0.95, sum by (le) "
            '(rate(fly_app_http_response_time_seconds_bucket{app="$app"}[$window])))'
        ),
        unit="seconds",
        derived=True,
        derivation="histogram_quantile(0.95) over the Fly proxy app-side latency histogram.",
    ),
    MetricSpec(
        key="app_http_p99",
        title="App HTTP p99 latency",
        promql=(
            "histogram_quantile(0.99, sum by (le) "
            '(rate(fly_app_http_response_time_seconds_bucket{app="$app"}[$window])))'
        ),
        unit="seconds",
        derived=True,
        derivation="histogram_quantile(0.99) over the Fly proxy app-side latency histogram.",
    ),
    MetricSpec(
        key="edge_http_p95",
        title="Edge HTTP p95 latency",
        promql=(
            "histogram_quantile(0.95, sum by (le) "
            '(rate(fly_edge_http_response_time_seconds_bucket{app="$app"}[$window])))'
        ),
        unit="seconds",
        derived=True,
        derivation="histogram_quantile(0.95) over the Fly edge latency histogram.",
    ),
    MetricSpec(
        key="hard_limit_reached",
        title="Concurrency hard limit reached",
        promql='sum(increase(fly_app_hard_limit_reached_count{app="$app"}[$window]))',
        unit="events",
        derived=True,
        derivation="increase() over the window.",
    ),
    MetricSpec(
        key="soft_limit_reached",
        title="Concurrency soft limit reached",
        promql='sum(increase(fly_app_soft_limit_reached_count{app="$app"}[$window]))',
        unit="events",
        derived=True,
        derivation="increase() over the window.",
    ),
    # -- app-exposed process and application metrics -----------------------
    MetricSpec(
        key="process_rss",
        title="Process RSS",
        promql='process_resident_memory_bytes{app="$app"}',
        unit="bytes",
        provenance="app_custom",
        note="Scraped from the app's own /metrics; single uvicorn process (see gate G2).",
    ),
    MetricSpec(
        key="process_rss_peak",
        title="Process RSS peak over window",
        promql='max_over_time(process_resident_memory_bytes{app="$app"}[$window])',
        unit="bytes",
        provenance="app_custom",
        derived=True,
        derivation="max_over_time of the scraped RSS gauge over the window.",
        note=(
            "Bounded below by the scrape interval: a spike shorter than one scrape is invisible "
            "here. Not a substitute for measuring RSS inside the process under test."
        ),
    ),
    MetricSpec(
        key="process_open_fds",
        title="Open file descriptors",
        promql='process_open_fds{app="$app"}',
        unit="count",
        provenance="app_custom",
    ),
    MetricSpec(
        key="app_requests_by_route",
        title="App requests by surface/route/status class",
        promql=(
            "sum by (surface, route, status_class) "
            '(increase(${prefix}_http_requests_total{app="$app"}[$window]))'
        ),
        unit="requests",
        provenance="app_custom",
        derived=True,
        derivation="increase() of the app's own request counter over the window.",
    ),
    MetricSpec(
        key="app_request_p95",
        title="App-measured request p95 latency",
        promql=(
            "histogram_quantile(0.95, sum by (le) "
            '(rate(${prefix}_http_request_duration_seconds_bucket{app="$app"}[$window])))'
        ),
        unit="seconds",
        provenance="app_custom",
        derived=True,
        derivation="histogram_quantile(0.95) over the app's own request-duration histogram.",
    ),
    MetricSpec(
        key="app_tool_calls",
        title="MCP tool calls by tool and status",
        promql=(
            "sum by (tool, status) "
            '(increase(${prefix}_tool_calls_total{app="$app"}[$window]))'
        ),
        unit="calls",
        provenance="app_custom",
        derived=True,
        derivation="increase() of the MCP tool-call counter over the window.",
        note=(
            "Verified to have no live series for property-shared on 2026-09-01 despite "
            "the duration histogram existing — the counter is stale, not zero."
        ),
    ),
    MetricSpec(
        key="app_client_connections",
        title="MCP client handshakes by client",
        promql=(
            "sum by (client_name) "
            '(increase(${prefix}_client_connections_total{app="$app"}[$window]))'
        ),
        unit="handshakes",
        provenance="app_custom",
        derived=True,
        derivation="increase() of the MCP initialize-handshake counter over the window.",
    ),
)

# Range series exist so the report carries shape, not just endpoints — a flat
# line and a spike that returned to baseline produce the same instant reading.
RANGE_SERIES: tuple[MetricSpec, ...] = (
    MetricSpec(
        key="range_memory_available",
        title="Machine memory available over time",
        promql='fly_instance_memory_mem_available{app="$app"}',
        unit="bytes",
        kind="range",
    ),
    MetricSpec(
        key="range_rootfs_free",
        title="Root filesystem free over time",
        promql=_FS_FREE,
        unit="bytes",
        kind="range",
        derived=True,
        derivation="blocks_free * block_size, per mount, sampled across the window.",
    ),
    MetricSpec(
        key="range_process_rss",
        title="Process RSS over time",
        promql='process_resident_memory_bytes{app="$app"}',
        unit="bytes",
        kind="range",
        provenance="app_custom",
    ),
)


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@dataclass
class SeriesResult:
    """The outcome of collecting one series.

    `status` is one of `ok`, `no_data` or `error`. `value` is populated only
    when the result is a single sample; it is `None` for `no_data`, for `error`
    and for multi-sample results, so a caller can never read a missing series
    as a number.
    """

    key: str
    title: str
    promql: str
    unit: str
    status: str
    samples: list[dict[str, Any]] = field(default_factory=list)
    value: float | None = None
    error: str | None = None
    # Why a no_data result is empty: `empty_result` (the query matched no
    # series at all) or `non_finite` (series matched, but every value was NaN
    # or ±Inf). The two mean different things to a reader.
    no_data_reason: str | None = None
    kind: str = "instant"
    provenance: str = "fly_builtin"
    derived: bool = False
    derivation: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "promql": self.promql,
            "unit": self.unit,
            "kind": self.kind,
            "status": self.status,
            "value": self.value,
            "samples": self.samples,
            "error": self.error,
            "no_data_reason": self.no_data_reason,
            "provenance": self.provenance,
            "derived": self.derived,
            "derivation": self.derivation,
            "note": self.note,
        }


def _from_spec(spec: MetricSpec, promql: str, **kwargs: Any) -> SeriesResult:
    return SeriesResult(
        key=spec.key,
        title=spec.title,
        promql=promql,
        unit=spec.unit,
        kind=spec.kind,
        provenance=spec.provenance,
        derived=spec.derived,
        derivation=spec.derivation,
        note=spec.note,
        **kwargs,
    )


def _labels(metric: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in metric.items() if k != "__name__"}


def _coerce_finite(raw: Any) -> float | None:
    """Parse a Prometheus sample value, rejecting anything non-finite.

    Prometheus returns values as strings, and `float()` cheerfully accepts
    `"NaN"`, `"+Inf"` and `"-Inf"` — all three of which the live API does emit
    (`1/0` returns `+Inf`; a quantile over a histogram with no traffic returns
    `NaN`). Reporting those as measurements is precisely the confusion this
    script exists to prevent, and `json.dumps` would then write bare `NaN` /
    `Infinity`, which is not valid JSON. `None` means "not a measurement".
    """
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return value


def parse_instant_response(
    spec: MetricSpec, payload: dict[str, Any], promql: str | None = None
) -> SeriesResult:
    """Turn a Prometheus instant-query payload into a typed result."""
    promql = promql if promql is not None else spec.promql

    if payload.get("status") != "success":
        detail = payload.get("error") or payload.get("errorType") or "unknown error"
        return _from_spec(spec, promql, status="error", error=f"prometheus: {detail}")

    result = payload.get("data", {}).get("result", []) or []
    if not result:
        return _from_spec(spec, promql, status="no_data", no_data_reason="empty_result")

    samples: list[dict[str, Any]] = []
    for entry in result:
        raw = entry.get("value")
        if not raw or len(raw) < 2:
            continue
        value = _coerce_finite(raw[1])
        if value is None:
            continue
        samples.append(
            {
                "labels": _labels(entry.get("metric", {})),
                "value": value,
                "timestamp": raw[0],
            }
        )

    if not samples:
        # The query matched series but every value was NaN, ±Inf or
        # unparseable — a different fact from "there is no such series".
        return _from_spec(spec, promql, status="no_data", no_data_reason="non_finite")

    single = samples[0]["value"] if len(samples) == 1 else None
    return _from_spec(spec, promql, status="ok", samples=samples, value=single)


def parse_range_response(
    spec: MetricSpec, payload: dict[str, Any], promql: str | None = None
) -> SeriesResult:
    """Turn a Prometheus range-query payload into a typed result."""
    promql = promql if promql is not None else spec.promql

    if payload.get("status") != "success":
        detail = payload.get("error") or payload.get("errorType") or "unknown error"
        return _from_spec(spec, promql, status="error", error=f"prometheus: {detail}")

    result = payload.get("data", {}).get("result", []) or []
    if not result:
        return _from_spec(spec, promql, status="no_data", no_data_reason="empty_result")

    samples: list[dict[str, Any]] = []
    for entry in result:
        points: list[tuple[Any, float]] = []
        for raw in entry.get("values", []) or []:
            if not raw or len(raw) < 2:
                continue
            value = _coerce_finite(raw[1])
            if value is None:
                # A single +Inf must not become the reported maximum.
                continue
            points.append((raw[0], value))
        if not points:
            continue
        values = [v for _, v in points]
        samples.append(
            {
                "labels": _labels(entry.get("metric", {})),
                "points": len(points),
                "min": min(values),
                "max": max(values),
                "first": values[0],
                "last": values[-1],
            }
        )

    if not samples:
        return _from_spec(spec, promql, status="no_data", no_data_reason="non_finite")
    return _from_spec(spec, promql, status="ok", samples=samples)


TRANSIENT_DISK_NOTE = (
    "Transient disk from this collector is corroborating evidence, never the "
    "measurement. The additional space a run consumed on a mount is "
    "baseline_free - minimum_free on that same mount; total_bytes - minimum_free "
    "would instead report total disk in use at the low-water mark, including the "
    f"image and everything already present. Fly stores samples every "
    f"{FLY_SCRAPE_INTERVAL_SECONDS}s, so a ~20 s materialisation yields one or two "
    "samples and its true peak can fall entirely between them. "
    "/app/boot_only_verify.py samples the verifier directory every 0.2 s and is the "
    "authoritative transient-disk measurement."
)


def summarise_transient_disk(
    baseline_free_bytes: float | None,
    minimum_free_bytes: float | None,
    total_bytes: float | None = None,
) -> dict[str, Any]:
    """Describe the free-space delta across a window, with its limits.

    `total_bytes` is accepted and echoed for context only; it deliberately
    plays no part in the delta, because subtracting the low-water mark from
    the filesystem size measures total occupancy rather than what a particular
    run added.
    """
    if baseline_free_bytes is None or minimum_free_bytes is None:
        delta: float | None = None
        status = "no_data"
    else:
        delta = baseline_free_bytes - minimum_free_bytes
        status = "ok"

    return {
        "status": status,
        "baseline_free_bytes": baseline_free_bytes,
        "minimum_free_bytes": minimum_free_bytes,
        "total_bytes": total_bytes,
        "delta_bytes": delta,
        "method": (
            "delta_bytes = baseline_free - minimum_free, on one mount. Not "
            "total_bytes - minimum_free, which measures total occupancy."
        ),
        "resolution_caveat": (
            f"Fly stores one sample per {FLY_SCRAPE_INTERVAL_SECONDS}s. A "
            "materialisation lasting ~20 s produces one or two samples, so this "
            "delta may understate the true peak or miss it entirely."
        ),
        "authoritative_source": (
            "/app/boot_only_verify.py, which samples the verifier directory every "
            "0.2 s, is the authoritative transient-disk measurement; this delta only "
            "corroborates it."
        ),
    }


def summarise_http_errors(error_count: float, total_count: float) -> dict[str, Any]:
    """Pair an error percentage with the absolute counts behind it.

    With no traffic there is no error rate to report. Returning `0%` there
    would claim a healthy service on the strength of nobody having asked it
    anything, so the percentage is `None` and the status is `no_data`.
    """
    if total_count <= 0:
        return {
            "status": "no_data",
            "error_count": error_count,
            "total_count": total_count,
            "error_pct": None,
        }
    return {
        "status": "ok",
        "error_count": error_count,
        "total_count": total_count,
        "error_pct": 100.0 * error_count / total_count,
    }


# ---------------------------------------------------------------------------
# Transports
# ---------------------------------------------------------------------------


def default_fetch(url: str, headers: dict[str, str], timeout: float) -> tuple[int, bytes]:
    """Perform one HTTP GET. Returns (status_code, body)."""
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as exc:  # a response, not a transport failure
        return int(exc.code), exc.read()


def default_runner(argv: list[str], timeout: float) -> tuple[int, str, str]:
    """Run a command. Returns (returncode, stdout, stderr)."""
    completed = subprocess.run(  # noqa: S603 - argv is allowlisted by assert_read_only
        argv, capture_output=True, text=True, timeout=timeout, check=False
    )
    return completed.returncode, completed.stdout, completed.stderr


def resolve_token(runner: Runner | None = None, env: dict[str, str] | None = None) -> str:
    """Obtain a Fly API token without letting it touch the filesystem.

    Prefers an existing environment token; otherwise captures `fly auth token`.
    The value is returned for in-memory use as a header only.
    """
    import os

    env = env if env is not None else dict(os.environ)
    for name in ("FLY_API_TOKEN", "FLY_ACCESS_TOKEN"):
        value = env.get(name)
        if value:
            return value.strip()

    runner = runner or default_runner
    code, out, err = runner(["fly", "auth", "token"], DEFAULT_TIMEOUT)
    if code != 0 or not out.strip():
        raise RuntimeError(
            "could not obtain a Fly token: set FLY_API_TOKEN or run `fly auth login` "
            f"(exit {code}: {redact(err.strip())})"
        )
    return out.strip()


# ---------------------------------------------------------------------------
# Window handling
# ---------------------------------------------------------------------------

_WINDOW_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_window_seconds(window: str) -> int:
    """Convert a PromQL-style duration such as `30m` or `6h` to seconds."""
    match = re.fullmatch(r"(\d+)([smhd])", window.strip())
    if not match:
        raise ValueError(f"invalid window {window!r}: expected a form like 30m, 6h or 1d")
    return int(match.group(1)) * _WINDOW_UNITS[match.group(2)]


def _range_step(window_seconds: int) -> int:
    """Pick a step that keeps a range query to roughly 100 points."""
    return max(15, (window_seconds // 100 // 15 + 1) * 15)


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Collector:
    """Gathers one read-only observability snapshot for a single Fly app."""

    def __init__(
        self,
        *,
        app: str,
        org: str,
        window: str,
        token: str,
        fetch: Fetch | None = None,
        runner: Runner | None = None,
        include_logs: int = 0,
        metrics_prefix: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        fly_binary: str = "fly",
        auth_scheme: str | None = None,
    ) -> None:
        self.app = app
        self.org = org
        self.window = window
        self.window_seconds = parse_window_seconds(window)
        self._token = token
        self.fetch = fetch or default_fetch
        self.runner = runner or default_runner
        self.include_logs = include_logs
        self.metrics_prefix = metrics_prefix or app.replace("-", "_")
        self.timeout = timeout
        self.fly_binary = fly_binary
        # None until negotiated on the first Prometheus request, then cached
        # for the rest of the run. An explicit scheme skips negotiation.
        self.auth_scheme: str | None = auth_scheme
        self._auth_failed: str | None = None

    # -- redaction helper ------------------------------------------------

    def _scrub(self, text: str) -> str:
        return redact(text, secrets=[self._token])

    # -- Prometheus ------------------------------------------------------

    def _prom_url(self, path: str, params: dict[str, Any]) -> str:
        base = f"{PROMETHEUS_BASE}/{urllib.parse.quote(self.org)}/api/v1/{path}"
        return f"{base}?{urllib.parse.urlencode(params)}"

    def _attempt(
        self, url: str, scheme: str
    ) -> tuple[int, bytes]:
        """One authenticated GET. The token exists only in this header."""
        headers = {
            "Authorization": f"{scheme} {self._token}",
            "Accept": "application/json",
        }
        try:
            return self.fetch(url, headers, self.timeout)
        except Exception as exc:  # noqa: BLE001 - re-raised scrubbed below
            raise RuntimeError(
                f"{type(exc).__name__}: {self._scrub(str(exc))}"
            ) from None

    def _prom_get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """Query Prometheus. Raises with a scrubbed message on any failure.

        On the first request the Authorization scheme is negotiated: each
        candidate is tried in turn until one is not rejected, and the winner
        is cached for the rest of the run. Only an auth rejection (401/403)
        advances to the next candidate — any other status is that request's
        real answer and is reported as such.
        """
        url = self._prom_url(path, params)
        if self._auth_failed:
            # Every scheme was already rejected once. Re-probing per series
            # would hammer the API with a token that cannot work.
            raise RuntimeError(self._auth_failed)

        candidates = [self.auth_scheme] if self.auth_scheme else list(AUTH_SCHEMES)

        status, body = -1, b""
        for scheme in candidates:
            assert scheme is not None
            status, body = self._attempt(url, scheme)
            if status not in (401, 403):
                self.auth_scheme = scheme
                break
        else:
            detail = self._scrub(body.decode("utf-8", "replace"))[:200]
            self._auth_failed = (
                f"HTTP {status} from Prometheus for every Authorization scheme tried "
                f"({', '.join(str(c) for c in candidates)}): {detail}"
            )
            raise RuntimeError(self._auth_failed)

        if status != 200:
            detail = self._scrub(body.decode("utf-8", "replace"))[:300]
            raise RuntimeError(f"HTTP {status} from Prometheus: {detail}")
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"malformed JSON from Prometheus: {exc}") from None

    def _collect_one(self, spec: MetricSpec) -> SeriesResult:
        promql = spec.render(app=self.app, window=self.window, prefix=self.metrics_prefix)
        try:
            if spec.kind == "range":
                end = int(time.time())
                payload = self._prom_get(
                    "query_range",
                    {
                        "query": promql,
                        "start": end - self.window_seconds,
                        "end": end,
                        "step": f"{_range_step(self.window_seconds)}s",
                    },
                )
                return parse_range_response(spec, payload, promql)
            payload = self._prom_get("query", {"query": promql})
            return parse_instant_response(spec, payload, promql)
        except Exception as exc:  # noqa: BLE001 - one series must not end the run
            return _from_spec(spec, promql, status="error", error=self._scrub(str(exc)))

    def collect_series(self) -> list[SeriesResult]:
        """Collect every instant series. Never raises for a single failure."""
        return [self._collect_one(spec) for spec in SERIES]

    def collect_ranges(self) -> list[SeriesResult]:
        """Collect every range series. Never raises for a single failure."""
        return [self._collect_one(spec) for spec in RANGE_SERIES]

    # -- flyctl ----------------------------------------------------------

    def _run_fly(self, key: str, args: list[str]) -> dict[str, Any]:
        assert_read_only(args)
        argv = [self.fly_binary, *args]
        entry: dict[str, Any] = {
            "key": key,
            "command": self._scrub(" ".join(argv)),
            "status": "ok",
            "data": None,
            "error": None,
        }
        try:
            code, out, err = self.runner(argv, self.timeout)
        except Exception as exc:  # noqa: BLE001 - one command must not end the run
            entry["status"] = "error"
            entry["error"] = f"{type(exc).__name__}: {self._scrub(str(exc))}"
            return entry

        if code != 0:
            entry["status"] = "error"
            entry["error"] = self._scrub((err or out).strip())[:500] or f"exit {code}"
            return entry

        try:
            entry["data"] = json.loads(out)
        except json.JSONDecodeError as exc:
            entry["status"] = "error"
            entry["error"] = f"malformed JSON from flyctl: {exc}"
        return entry

    def collect_commands(self) -> list[dict[str, Any]]:
        """Run the documented read-only flyctl commands.

        Full payloads are reduced to selected fields — a Machine's config
        carries its whole environment, and this report is meant to be readable
        and shareable rather than a dump.
        """
        commands = [
            self._run_fly("status", ["status", "--json", "-a", self.app]),
            self._run_fly("checks", ["checks", "list", "--json", "-a", self.app]),
            self._run_fly("image", ["image", "show", "--json", "-a", self.app]),
        ]
        for entry in commands:
            if entry["status"] == "ok":
                entry["data"] = _select_fields(entry["key"], entry["data"])
        return commands

    def collect_logs(self) -> dict[str, Any] | None:
        """Collect a bounded log excerpt. Returns None unless opted in."""
        if self.include_logs <= 0:
            return None

        args = ["logs", "--json", "--no-tail", "-a", self.app]
        assert_read_only(args)
        argv = [self.fly_binary, *args]

        block: dict[str, Any] = {
            "sensitive": True,
            "requested_lines": self.include_logs,
            "status": "ok",
            "error": None,
            "lines": [],
            "command": self._scrub(" ".join(argv)),
            "note": (
                "Log lines are application output and may contain request detail. "
                "Review before sharing; they are collected only on --include-logs."
            ),
        }

        try:
            code, out, err = self.runner(argv, self.timeout)
        except Exception as exc:  # noqa: BLE001 - logs must not end the run
            block["status"] = "error"
            block["error"] = f"{type(exc).__name__}: {self._scrub(str(exc))}"
            return block

        if code != 0:
            block["status"] = "error"
            block["error"] = self._scrub((err or out).strip())[:500] or f"exit {code}"
            return block

        records = parse_log_stream(out)
        if not records and out.strip():
            block["status"] = "error"
            block["error"] = (
                "could not parse any JSON record from flyctl log output "
                f"({len(out)} bytes); the --json shape may have changed"
            )
            return block

        block["lines"] = _sanitise_log_records(records, self.include_logs, self._scrub)
        return block

    # -- the whole run ---------------------------------------------------

    def run(self) -> dict[str, Any]:
        started_at = _utc_now()
        series = self.collect_series() + self.collect_ranges()
        commands = self.collect_commands()
        logs = self.collect_logs()
        ended_at = _utc_now()

        notes = [DASHBOARD_GAP_NOTE, TRANSIENT_DISK_NOTE]
        notes.extend(_interpretation_notes(series))

        return build_report(
            app=self.app,
            org=self.org,
            window=self.window,
            started_at=started_at,
            ended_at=ended_at,
            series=series,
            commands=commands,
            logs=logs,
            notes=notes,
            metrics_prefix=self.metrics_prefix,
            auth_scheme=self.auth_scheme,
        )


# ---------------------------------------------------------------------------
# Field selection and sanitisation
# ---------------------------------------------------------------------------


def _select_fields(key: str, data: Any) -> Any:
    """Keep the identity and health fields; drop config and environment."""
    if key == "status" and isinstance(data, dict):
        machines = data.get("Machines") or data.get("machines") or []
        return {
            "name": data.get("Name") or data.get("name"),
            "hostname": data.get("Hostname") or data.get("hostname"),
            "machines": [
                {
                    "id": m.get("id"),
                    "state": m.get("state"),
                    "region": m.get("region"),
                    "image": ((m.get("config") or {}).get("image")),
                    "created_at": m.get("created_at"),
                    "updated_at": m.get("updated_at"),
                }
                for m in machines
                if isinstance(m, dict)
            ],
        }
    if key == "checks":
        # `fly checks list --json` returns {machine_id: [check, ...]}. Older
        # flyctl builds returned a flat list, so both shapes are accepted.
        if isinstance(data, dict):
            pairs = [
                (machine, check)
                for machine, checks in data.items()
                if isinstance(checks, list)
                for check in checks
                if isinstance(check, dict)
            ]
        elif isinstance(data, list):
            pairs = [(None, c) for c in data if isinstance(c, dict)]
        else:
            return None
        return [
            {
                "machine": machine or c.get("Machine") or c.get("machine"),
                "name": c.get("Name") or c.get("name"),
                "status": c.get("Status") or c.get("status"),
                "output": (c.get("Output") or c.get("output") or "")[:200],
            }
            for machine, c in pairs
        ]
    if key == "image":
        # `fly image show --json` returns a list of image records.
        records = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
        selected = [
            {
                k: record.get(k)
                for k in ("Registry", "Repository", "Tag", "Digest", "Labels", "Version", "MachineID")
                if k in record
            }
            for record in records
            if isinstance(record, dict)
        ]
        return selected if isinstance(data, list) else (selected[0] if selected else None)
    return None


_LOG_FIELDS = ("timestamp", "level", "instance", "region", "message")


def parse_log_stream(text: str) -> list[dict[str, Any]]:
    """Parse `fly logs --json` output into records.

    Verified against flyctl v0.4.95: the output is a stream of *pretty-printed*
    JSON objects written one after another — not JSON-lines, and not a JSON
    array. Splitting on newlines produces fragments such as `"URL": {`, so the
    objects are decoded incrementally with `raw_decode` instead.
    """
    decoder = json.JSONDecoder()
    records: list[dict[str, Any]] = []
    index = 0
    length = len(text)

    while index < length:
        while index < length and text[index] in " \t\r\n":
            index += 1
        if index >= length:
            break
        try:
            obj, end = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            # Skip to the next plausible object start; a single malformed
            # record must not discard the ones after it.
            next_start = text.find("{", index + 1)
            if next_start == -1:
                break
            index = next_start
            continue
        if isinstance(obj, dict):
            records.append(obj)
        index = end

    return records


def _sanitise_log_records(
    records: list[Any], limit: int, scrub: Callable[[str], str]
) -> list[dict[str, Any]]:
    """Keep the most recent `limit` records, selected fields only, scrubbed."""
    selected = []
    for record in records[-limit:]:
        if not isinstance(record, dict):
            selected.append({"message": scrub(str(record))})
            continue
        selected.append(
            {k: scrub(str(record[k])) for k in _LOG_FIELDS if k in record}
        )
    return selected


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


def _interpretation_notes(series: list[SeriesResult]) -> list[str]:
    notes = []
    missing = [s.key for s in series if s.status == "no_data"]
    errored = [s.key for s in series if s.status == "error"]
    if missing:
        notes.append(
            "no_data (absent series, NOT zero): " + ", ".join(sorted(missing))
        )
    if errored:
        notes.append("collection errors: " + ", ".join(sorted(errored)))
    return notes


def build_report(
    *,
    app: str,
    org: str,
    window: str,
    started_at: str,
    ended_at: str,
    series: list[SeriesResult],
    commands: list[dict[str, Any]],
    logs: dict[str, Any] | None,
    notes: list[str],
    metrics_prefix: str | None = None,
    auth_scheme: str | None = None,
) -> dict[str, Any]:
    """Assemble the stable-schema report."""
    return {
        "schema_version": SCHEMA_VERSION,
        "target": {
            "app": app,
            "org": org,
            "metrics_prefix": metrics_prefix or app.replace("-", "_"),
        },
        "query": {
            "window": window,
            "started_at": started_at,
            "ended_at": ended_at,
            "prometheus_base": f"{PROMETHEUS_BASE}/{org}/api/v1",
            # Which Authorization scheme the token turned out to need. The
            # scheme is not a secret; the token it accompanied never appears.
            "auth_scheme": auth_scheme,
            "scrape_interval_seconds": FLY_SCRAPE_INTERVAL_SECONDS,
        },
        "series": [s.to_dict() for s in series],
        "commands": commands,
        "logs": logs,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _format_value(value: float | None, unit: str) -> str:
    if value is None:
        return "—"
    if unit == "bytes":
        return f"{value:,.0f} ({value / 1024 ** 3:.2f} GiB)" if abs(value) >= 1024**2 else f"{value:,.0f}"
    if value == int(value) and abs(value) < 1e15:
        return f"{int(value):,}"
    return f"{value:,.4g}"


def _render_samples(result: SeriesResult) -> str:
    if result.status != "ok" or not result.samples:
        return ""
    lines = []
    for sample in result.samples:
        labels = sample.get("labels", {})
        label_text = ", ".join(f"{k}={v}" for k, v in sorted(labels.items())) or "(no labels)"
        if result.kind == "range":
            lines.append(
                f"  - {label_text}: min={_format_value(sample['min'], result.unit)}, "
                f"max={_format_value(sample['max'], result.unit)}, "
                f"last={_format_value(sample['last'], result.unit)} "
                f"({sample['points']} points)"
            )
        else:
            lines.append(f"  - {label_text}: {_format_value(sample['value'], result.unit)}")
    return "\n".join(lines)


def render_markdown(report: dict[str, Any]) -> str:
    """Render a concise interpretation of the report."""
    target = report["target"]
    query = report["query"]
    out: list[str] = []

    out.append(f"# Fly observability snapshot — `{target['app']}`")
    out.append("")
    out.append(f"- **App**: `{target['app']}` (org `{target['org']}`)")
    out.append(f"- **Window**: `{query['window']}`")
    out.append(f"- **Collected**: {query['started_at']} → {query['ended_at']} (UTC)")
    out.append(f"- **Schema**: `{report['schema_version']}`")
    out.append("")
    out.append(
        "`no_data` means the series has no samples — it is **not** a reading of zero. "
        "`error` means collection failed and nothing was measured."
    )
    out.append("")

    out.append("## Readings")
    out.append("")
    out.append("| Metric | Unit | Value | Status |")
    out.append("|---|---|---|---|")
    for entry in report["series"]:
        status = entry["status"]
        if status == "ok":
            if entry["value"] is not None:
                value = _format_value(entry["value"], entry["unit"])
            else:
                value = f"{len(entry['samples'])} series"
        else:
            value = "—"
        title = entry["title"] + (" *(derived)*" if entry["derived"] else "")
        out.append(f"| {title} | {entry['unit']} | {value} | `{status}` |")
    out.append("")

    # Single-sample `info` series carry everything they are worth in their
    # labels — Machine ID, memory_mb, cpu_kind. Rendering just the value `1`
    # would drop exactly the identity Phase D needs to record.
    detailed = [
        e
        for e in report["series"]
        if e["status"] == "ok" and (len(e["samples"]) > 1 or e["unit"] == "info")
    ]
    if detailed:
        out.append("## Breakdowns")
        out.append("")
        for entry in detailed:
            out.append(f"**{entry['title']}**")
            result = SeriesResult(
                key=entry["key"], title=entry["title"], promql=entry["promql"],
                unit=entry["unit"], status=entry["status"], samples=entry["samples"],
                kind=entry["kind"],
            )
            out.append(_render_samples(result))
            out.append("")

    problems = [e for e in report["series"] if e["status"] != "ok"]
    if problems:
        out.append("## Not measured")
        out.append("")
        out.append("| Metric | Status | Detail |")
        out.append("|---|---|---|")
        for entry in problems:
            reason = entry.get("no_data_reason")
            if reason == "non_finite":
                prefix = "series matched but every value was NaN or ±Inf — not a reading. "
            elif reason == "empty_result":
                prefix = "query matched no series. "
            else:
                prefix = ""
            detail = prefix + (entry["error"] or entry["note"] or "no samples in window")
            out.append(f"| {entry['title']} | `{entry['status']}` | {detail} |")
        out.append("")

    out.append("## Commands")
    out.append("")
    for entry in report["commands"]:
        out.append(f"- `{entry['command']}` → `{entry['status']}`"
                   + (f" — {entry['error']}" if entry["error"] else ""))
    out.append("")

    if report["logs"] is not None:
        logs = report["logs"]
        out.append("## Logs")
        out.append("")
        out.append(
            f"{len(logs['lines'])} line(s), requested {logs['requested_lines']}. "
            "**Potentially sensitive** — review before sharing."
        )
        out.append("")

    out.append("## Notes")
    out.append("")
    for note in report["notes"]:
        out.append(f"- {note}")
    out.append("")

    out.append("## PromQL used")
    out.append("")
    for entry in report["series"]:
        out.append(f"- **{entry['title']}** (`{entry['provenance']}`"
                   + (", derived" if entry["derived"] else "") + ")")
        out.append(f"  ```")
        out.append(f"  {entry['promql']}")
        out.append(f"  ```")
        if entry["derivation"]:
            out.append(f"  Derivation: {entry['derivation']}")
    out.append("")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def write_outputs(report: dict[str, Any], path: Path, force: bool = False) -> list[Path]:
    """Write the JSON report and its Markdown rendering.

    Refuses to overwrite by default: a before/after comparison is only worth
    anything if the "before" is still there when the "after" is written.
    """
    json_path = Path(path)
    md_path = json_path.with_suffix(".md")

    if not force:
        for existing in (json_path, md_path):
            if existing.exists():
                raise FileExistsError(
                    f"{existing} already exists; pass --force to overwrite, or choose "
                    "another --output so the earlier report survives"
                )

    # allow_nan=False: Python would otherwise emit bare `NaN` / `Infinity`,
    # which no strict JSON parser accepts. A non-finite value reaching here
    # means the parser guards were bypassed, and that must fail loudly rather
    # than produce a report that reads fine and cannot be loaded.
    serialised = json.dumps(report, indent=2, sort_keys=False, allow_nan=False)

    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(serialised + "\n")
    md_path.write_text(render_markdown(report))
    return [json_path, md_path]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect a read-only observability snapshot for a Fly.io app.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--app", required=True, help="Fly app name, e.g. property-shared")
    parser.add_argument("--org", default="personal", help="Fly org slug (default: personal)")
    parser.add_argument(
        "--window", default="30m", help="Lookback window, e.g. 30m, 6h, 1d (default: 30m)"
    )
    parser.add_argument(
        "--output", required=True, help="Path for the JSON report; .md is written alongside"
    )
    parser.add_argument(
        "--include-logs",
        type=int,
        default=0,
        metavar="N",
        help="Opt in to the most recent N sanitised log lines (default: 0, none)",
    )
    parser.add_argument(
        "--metrics-prefix",
        default=None,
        help="Prefix for app-exposed metrics (default: the app name with - replaced by _)",
    )
    parser.add_argument(
        "--auth-scheme",
        choices=("auto", *AUTH_SCHEMES),
        default="auto",
        help=(
            "Authorization scheme for the Prometheus API. Default 'auto' tries "
            f"{' then '.join(AUTH_SCHEMES)} and caches whichever the token accepts."
        ),
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite an existing report at --output"
    )
    parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT, help="Per-request timeout in seconds"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        token = resolve_token()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    collector = Collector(
        app=args.app,
        org=args.org,
        window=args.window,
        token=token,
        include_logs=args.include_logs,
        metrics_prefix=args.metrics_prefix,
        timeout=args.timeout,
        auth_scheme=None if args.auth_scheme == "auto" else args.auth_scheme,
    )
    report = collector.run()
    written = write_outputs(report, Path(args.output), force=args.force)

    counts: dict[str, int] = {}
    for entry in report["series"]:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
    print(f"collected {len(report['series'])} series ({summary})")
    for path in written:
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
