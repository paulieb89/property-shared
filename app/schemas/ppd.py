"""API envelope schemas for PPD endpoints.

Domain models (PPDTransaction, etc.) live in property_core.models.ppd.
This file defines only the API response wrappers.
"""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field

# Convenience re-exports for API layer imports
from property_core.models.ppd import (  # noqa: F401
    PPDCompsQuery,
    PPDCompsResponse,
    PPDTransaction,
    PPDTransactionRecord,
    SubjectProperty,
)
from property_core.provenance import PPDProvenance  # noqa: F401


class PPDSearchResponse(BaseModel):
    """Search results for PPD transactions."""
    count: int
    limit: int
    offset: int
    results: List[PPDTransaction] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    raw: Optional[List[dict[str, Any]]] = None
    #: Where these rows came from, over what coverage, and how much of the
    #: source was examined. Additive and nullable, so an existing caller that
    #: ignores it sees no change.
    provenance: Optional[PPDProvenance] = None


class PPDDownloadURLResponse(BaseModel):
    """Direct download URL for PPD bulk datasets."""
    url: str


class PPDTransactionRecordResponse(BaseModel):
    """Normalized record with optional raw Linked Data payload."""
    record: PPDTransactionRecord
    raw: Optional[dict[str, Any]] = None
    #: Always `linked_data`: exact-ID lookup never routes to the snapshot, so it
    #: keeps working for transactions older than coverage.
    provenance: Optional[PPDProvenance] = None
