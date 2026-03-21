"""API envelope schemas for EPC endpoints.

Domain model (EPCData) lives in property_core.models.epc.
This file defines only the API response wrapper.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

# Convenience re-exports for API layer imports
from property_core.models.epc import EPCData  # noqa: F401


class EPCRecordResponse(BaseModel):
    """Normalized EPC record with optional raw payload."""

    record: EPCData
    raw: Optional[dict[str, Any]] = None
