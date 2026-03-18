"""Domain models for postcode data."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel


class PostcodeResult(BaseModel):
    """Normalized result from postcodes.io API."""
    postcode: str | None = None
    admin_district: str | None = None
    admin_county: str | None = None
    region: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    codes: dict[str, str] | None = None
    rural_urban: str | None = None
    raw: dict[str, Any] | None = None

    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> PostcodeResult:
        """Construct a PostcodeResult from a postcodes.io response ``result`` dict.

        The ``data`` parameter is the ``result`` object returned by the API,
        not the outer envelope.
        """
        codes_raw = data.get("codes")
        codes = (
            {str(k): str(v) for k, v in codes_raw.items()}
            if isinstance(codes_raw, dict)
            else None
        )
        return cls(
            postcode=data.get("postcode"),
            admin_district=data.get("admin_district"),
            admin_county=data.get("admin_county"),
            region=data.get("region"),
            country=data.get("country"),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            codes=codes,
            rural_urban=data.get("ruc21"),
            raw=data,
        )
