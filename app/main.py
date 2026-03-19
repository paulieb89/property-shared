from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from starlette.types import ASGIApp, Receive, Scope, Send
import uvicorn

from app.api.routes import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.web.routes import router as demo_router


# ---------------------------------------------------------------------------
# MCP integration (optional — requires mcp extra, uses FastMCP v3)
#
# Can't use app.mount("/mcp") — Starlette always 307-redirects /mcp → /mcp/
# and neither Claude.ai nor ChatGPT follow 307 for POST requests.
# Middleware routes /mcp directly without redirect.
# ---------------------------------------------------------------------------
_mcp_app: Any = None


def _setup_mcp() -> None:
    """Prepare MCP HTTP ASGI app (optional)."""
    global _mcp_app
    try:
        from mcp_server.server import mcp as mcp_server

        _mcp_app = mcp_server.http_app(path="/mcp")
    except ImportError:
        pass


class MCPMiddleware:
    """Route /mcp requests to the MCP app without Starlette mount redirect."""

    def __init__(self, app: ASGIApp, mcp_handler: Any) -> None:
        self.app = app
        self.mcp_handler = mcp_handler

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] == "http" and (path == "/mcp" or path.startswith("/mcp/")):
            await self.mcp_handler(scope, receive, send)
        else:
            await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    _ = get_settings()
    configure_logging()
    yield


def create_app() -> FastAPI:
    _setup_mcp()

    # Combine our lifespan with MCP's if available (required for session manager)
    app_lifespan = lifespan
    if _mcp_app is not None:
        try:
            from fastmcp.utilities.lifespan import combine_lifespans
            app_lifespan = combine_lifespans(lifespan, _mcp_app.lifespan)
        except ImportError:
            app_lifespan = _mcp_app.lifespan

    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=app_lifespan,
    )
    app.include_router(api_router)
    app.include_router(demo_router)

    if _mcp_app is not None:
        app.add_middleware(MCPMiddleware, mcp_handler=_mcp_app)

    return app


app = create_app()


def run() -> None:
    """Entry point for property-api/property-demo scripts."""
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
