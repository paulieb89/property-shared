"""API envelope schemas for PPD endpoints.

Domain models (PPDTransaction, etc.) live in property_core.models.ppd.
This file defines only the API response wrappers.
"""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field

# Re-export domain models for backward compatibility within app/
from property_core.models.ppd import (  # noqa: F401
    PPDCompsQuery,
    PPDCompsResponse,
    PPDTransaction,
    PPDTransactionRecord,
    SubjectProperty,
)


class PPDSearchResponse(BaseModel):
    """Search results for PPD transactions."""
    count: int
    limit: int
    offset: int
    results: List[PPDTransaction] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    raw: Optional[List[dict[str, Any]]] = None


class PPDDownloadURLResponse(BaseModel):
    """Direct download URL for PPD bulk datasets."""
    url: str


class PPDTransactionRecordResponse(BaseModel):
    """Normalized record with optional raw Linked Data payload."""
    record: PPDTransactionRecord
    raw: Optional[dict[str, Any]] = None
