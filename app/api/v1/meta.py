"""Meta endpoints for service introspection."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from property_core.attribution import HMLR_LICENCE_URL, hmlr_attribution
from property_core.epc_client import EPCClient
from property_core.snapshot.bootstrap import snapshot_status

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("", summary="Service metadata and data attribution")
async def meta() -> dict[str, object]:
    """Dataset metadata, including the required HM Land Registry attribution.

    This is what every PPD response's `attribution_ref` points at. Attribution
    lives here rather than in each payload: the licence requires the statement
    to be discoverable, not that it be repeated in every row of data, and
    inlining it would put a paragraph of prose into an LLM's context on every
    single call.
    """
    return {
        "attribution": hmlr_attribution(),
        "licence_url": HMLR_LICENCE_URL,
        "snapshot": snapshot_status(),
    }


@router.get("/integrations", summary="Integration configuration status")
async def integrations() -> dict[str, object]:
    """Return which integrations are configured/enabled.

    Intended for AI agents / clients to self-check capabilities before calling.
    """
    settings = get_settings()
    epc = EPCClient()

    return {
        "environment": settings.environment,
        "integrations": {
            "ppd": {"available": True, "configured": True},
            "rightmove": {"available": True, "configured": True},
            "epc": {"available": True, "configured": epc.is_configured()},
        },
    }
