"""Unit tests for property_epc_search and get_epc_certificate in app/mcp/server.py."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# property_epc_search
# ---------------------------------------------------------------------------


def test_property_epc_search_is_deprecated_with_an_actionable_message():
    """The full-row tool cannot be honoured: search returns no score/floor area."""
    from property_core.epc.errors import EPCUnsupportedOperationError

    from app.mcp.server import property_epc_search

    with pytest.raises(EPCUnsupportedOperationError) as exc:
        asyncio.run(property_epc_search("NG7 1FN"))
    msg = str(exc.value)
    assert "property_epc_summaries" in msg, "must name the replacement tool"
    assert "epc_certificate" in msg, "must name the follow-up call"


def test_property_epc_summaries_returns_summary_fields_only():
    """The summary-native tool exposes what search actually provides."""
    from app.mcp.server import property_epc_summaries

    page = SimpleNamespace(
        results=[SimpleNamespace(
            certificate_number="1111-2222-3333-4444-5555",
            address="Flat 2, 42 Example Boulevard",
            uprn="100000000001",
            current_energy_efficiency_band="D",
            registration_date="2023-03-05",
            schema_type="RdSAP-Schema-20.0.0",
        )],
        pagination=SimpleNamespace(total_records=1),
        returned_distinct_count=1, duplicates_removed=0,
        unusable_rows=0, complete=True, warnings=[],
    )
    with patch("property_core.EPCClient") as mock_cls:
        mock_cls.return_value.search_summaries = AsyncMock(return_value=page)
        result = asyncio.run(property_epc_summaries("NG7 1FN"))

    assert result["total_records"] == 1 and result["complete"] is True
    row = result["results"][0]
    assert set(row) == {"certificate_number", "address", "uprn",
                        "energy_band", "registration_date", "schema_type"}
    for absent in ("score", "floor_area", "property_type"):
        assert absent not in row, f"{absent} is not available from a summary search"


def test_property_epc_summaries_reports_incompleteness():
    from app.mcp.server import property_epc_summaries

    page = SimpleNamespace(
        results=[], pagination=SimpleNamespace(total_records=500),
        returned_distinct_count=0, duplicates_removed=0, unusable_rows=0,
        complete=False, warnings=["bounded page"],
    )
    with patch("property_core.EPCClient") as mock_cls:
        mock_cls.return_value.search_summaries = AsyncMock(return_value=page)
        result = asyncio.run(property_epc_summaries("NG7 1FN"))
    assert result["complete"] is False and result["warnings"]


# ---------------------------------------------------------------------------
# epc_certificate
# ---------------------------------------------------------------------------


def test_epc_certificate_returns_none_when_not_found():
    """epc_certificate returns None when the lmk_key is not recognised."""
    from app.mcp.server import epc_certificate

    with patch("property_core.EPCClient") as mock_cls:
        mock_cls.return_value.get_certificate = AsyncMock(return_value=None)
        result = asyncio.run(epc_certificate("nonexistent-key"))
        assert result is None
        mock_cls.return_value.get_certificate.assert_awaited_once_with("nonexistent-key")


def test_epc_certificate_returns_full_slim_cert():
    """epc_certificate returns a slimmed full cert dict with raw stripped."""
    from app.mcp.server import epc_certificate

    mock_epc = MagicMock()
    mock_epc.model_dump.return_value = {
        "address": "FLAT 1, 10 TEST STREET",
        "postcode": "SW1A 1AA",
        "rating": "C",
        "lmk_key": "abc123",
        "floor_area": 55.0,
        "raw": {"should": "be stripped"},
    }

    with patch("property_core.EPCClient") as mock_cls:
        mock_cls.return_value.get_certificate = AsyncMock(return_value=mock_epc)
        result = asyncio.run(epc_certificate("abc123"))

    assert isinstance(result, dict)
    assert result["lmk_key"] == "abc123"
    assert result["floor_area"] == 55.0
    assert "raw" not in result
