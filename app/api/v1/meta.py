"""Meta endpoints for service introspection."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.services.epc_service import EPCService

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/integrations", summary="Integration configuration status")
async def integrations() -> dict[str, object]:
    """Return which integrations are configured/enabled.

    Intended for AI agents / clients to self-check capabilities before calling.
    """
    settings = get_settings()
    epc = EPCService()

    return {
        "environment": settings.environment,
        "integrations": {
            "ppd": {"available": True, "configured": True},
            "rightmove": {"available": True, "configured": True},
            "epc": {"available": True, "configured": epc.is_configured()},
            "location": {"available": True, "configured": True},
        },
    }
