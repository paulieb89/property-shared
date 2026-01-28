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
# MCP integration (optional — requires mcp extra)
# ---------------------------------------------------------------------------
_mcp_session_manager = None
_mcp_asgi_handler: Any = None


def _setup_mcp() -> None:
    """Prepare MCP Streamable HTTP ASGI handler (optional)."""
    global _mcp_session_manager, _mcp_asgi_handler
    try:
        from mcp_server.server import mcp as mcp_server

        starlette_app = mcp_server.streamable_http_app()
        _mcp_session_manager = mcp_server._session_manager
        _mcp_asgi_handler = getattr(starlette_app.routes[0], "endpoint", None)
    except (ImportError, IndexError):
        pass


class MCPMiddleware:
    """ASGI middleware that routes /mcp to the MCP handler."""

    def __init__(self, app: ASGIApp, mcp_handler: Any) -> None:
        self.app = app
        self.mcp_handler = mcp_handler

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("path") == "/mcp":
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

    if _mcp_session_manager is not None:
        async with _mcp_session_manager.run():
            yield
    else:
        yield


def create_app() -> FastAPI:
    _setup_mcp()

    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(api_router)
    app.include_router(demo_router)

    if _mcp_asgi_handler is not None:
        app.add_middleware(MCPMiddleware, mcp_handler=_mcp_asgi_handler)

    return app


app = create_app()


def run() -> None:
    """Entry point for property-api/property-demo scripts."""
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
