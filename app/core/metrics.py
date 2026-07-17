"""Prometheus metrics for HTTP traffic and metrics endpoint."""

from __future__ import annotations

import time

from fastapi import FastAPI, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.types import ASGIApp, Message, Receive, Scope, Send

TOOL_CALLS_TOTAL = Counter(
    "property_shared_tool_calls_total",
    "Count of MCP tool invocations for property-shared.",
    labelnames=("tool", "status"),
)

TOOL_DURATION_SECONDS = Histogram(
    "property_shared_tool_duration_seconds",
    "MCP tool invocation latency in seconds for property-shared.",
    labelnames=("tool",),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

# Deliberately carries transport/region even though nothing else here does: this
# metric's whole purpose is fleet-wide aggregation, and the identical counter now
# exists on uk-legal, uk-due-diligence, govuk, uk-property and whatdotheyknow. One
# shape across every server is what lets a single sweep of the public /metrics
# endpoints answer "who calls the fleet?".
CLIENT_CONNECTIONS_TOTAL = Counter(
    "property_shared_client_connections_total",
    "Count of MCP client initialize handshakes for property-shared.",
    labelnames=("client_name", "client_version", "transport", "region"),
)

HTTP_REQUESTS_TOTAL = Counter(
    "property_shared_http_requests_total",
    "Total HTTP requests handled by property-shared.",
    labelnames=("surface", "route", "method", "status", "status_class"),
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "property_shared_http_request_duration_seconds",
    "HTTP request duration in seconds for property-shared.",
    labelnames=("surface", "route", "method", "status_class"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)


def _surface(path: str) -> str:
    if path in {"/metrics", "/health", "/v1/health"}:
        return "infra"
    if path == "/mcp" or path.startswith("/mcp/"):
        return "mcp_proxy"
    if path.startswith("/v1/"):
        return "api"
    return "web"


def _route_label(request: Request, surface: str) -> str:
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if isinstance(route_path, str) and route_path:
        return route_path

    if surface == "mcp_proxy":
        return "/mcp"
    if surface == "api":
        return "/v1/<unmatched>"
    if surface == "infra":
        return "/infra"
    return "/web"


class HTTPMetricsMiddleware:
    """ASGI middleware that records low-cardinality HTTP metrics."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path == "/metrics":
            await self.app(scope, receive, send)
            return

        surface = _surface(path)
        method = scope.get("method", "GET")

        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 500))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed = time.perf_counter() - start
            status = str(status_code)
            status_class = f"{status_code // 100}xx"

            request = Request(scope)
            route = _route_label(request, surface)

            HTTP_REQUESTS_TOTAL.labels(
                surface=surface,
                route=route,
                method=method,
                status=status,
                status_class=status_class,
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(
                surface=surface,
                route=route,
                method=method,
                status_class=status_class,
            ).observe(elapsed)


def setup_metrics(app: FastAPI) -> None:
    """Expose /metrics endpoint backed by the global prometheus-client registry."""

    @app.get("/metrics", include_in_schema=False)
    async def metrics_endpoint() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
