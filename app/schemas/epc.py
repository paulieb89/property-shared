"""API envelope schemas for EPC endpoints.

Domain model (EPCData) lives in property_core.models.epc.
This file defines only the API response wrappers.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

# Convenience re-exports for API layer imports
from property_core.models.epc import EPCData  # noqa: F401


class EPCRecordResponse(BaseModel):
    """Normalized EPC record with optional raw payload."""

    record: EPCData
    raw: Optional[dict[str, Any]] = None


class EPCAreaSummary(BaseModel):
    """Aggregated statistics for EPC certificates in a postcode area.

    `None` means "not available from this source" — deliberately distinct from
    `{}` or `0`, which assert that the area genuinely has none. Floor-area and
    property-type statistics exist only on full certificates, so producing them
    would require one upstream request per certificate.
    """

    count: int | None = None  # None = unknown (missing upstream metadata), never 0
    rating_distribution: dict[str, int] | None = None
    rating_distribution_sample: dict[str, int] | None = None
    rating_distribution_sample_size: int | None = None
    floor_area_min: float | None = None
    floor_area_max: float | None = None
    floor_area_avg: float | None = None
    property_type_breakdown: dict[str, int] | None = None


class EPCAreaResponse(BaseModel):
    """EPC area search results with summary statistics.

    `certificates` is `None` when per-certificate detail is unavailable from a
    summary search — never `[]`, which would assert the area holds none.
    """

    postcode: str
    summary: EPCAreaSummary
    certificates: list[EPCData] | None = None
    complete: bool = False
    warnings: list[str] = Field(default_factory=list)
