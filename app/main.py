from contextlib import asynccontextmanager

from fastapi import FastAPI
import uvicorn

from app.api.routes import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.web.routes import router as demo_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ = get_settings()
    configure_logging()

    try:
        yield
    finally:
        return


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(api_router)
    app.include_router(demo_router)
    return app


app = create_app()


def run() -> None:
    """Entry point for property-api/property-demo scripts."""
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
