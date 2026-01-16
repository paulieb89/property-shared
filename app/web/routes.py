"""Simple demo pages calling API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/web/templates")
router = APIRouter(prefix="/demo", tags=["demo"])


@router.get("/", response_class=HTMLResponse)
async def demo_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

