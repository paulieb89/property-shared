"""Unit tests for property_epc_search and get_epc_certificate in app/mcp/server.py."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# property_epc_search
# ---------------------------------------------------------------------------


def test_property_epc_search_returns_none_when_no_certs():
    """property_epc_search returns None when postcode has no EPC records."""
    from app.mcp.server import property_epc_search

    with patch("property_core.EPCClient") as mock_cls:
        mock_cls.return_value.search_all_by_postcode = AsyncMock(return_value=[])
        result = asyncio.run(property_epc_search("ZZ99 9ZZ"))
        assert result is None


def test_property_epc_search_returns_slim_list():
    """property_epc_search returns slim list with exactly the 9 documented fields."""
    from app.mcp.server import property_epc_search

    def make_cert(**kwargs):
        m = MagicMock()
        m.model_dump.return_value = {
            "address": kwargs.get("address", "1 TEST STREET"),
            "rating": kwargs.get("rating", "C"),
            "score": 72,
            "floor_area": kwargs.get("floor_area", 55.0),
            "property_type": "Flat",
            "floor_level": "2nd floor",
            "habitable_rooms": 3,
            "inspection_date": "2023-01-01",
            "lmk_key": kwargs.get("lmk_key", "abc123"),
            "raw": {"noise": True},
            "uprn": "1234567890",
        }
        return m

    certs = [
        make_cert(address="FLAT 1, 10 TEST ST", lmk_key="aaa111", floor_area=55.0),
        make_cert(address="FLAT 2, 10 TEST ST", lmk_key="bbb222", floor_area=60.0),
    ]

    with patch("property_core.EPCClient") as mock_cls:
        mock_cls.return_value.search_all_by_postcode = AsyncMock(return_value=certs)
        result = asyncio.run(property_epc_search("SW1A 1AA"))

    assert isinstance(result, list)
    assert len(result) == 2

    first = result[0]
    # Must have the 9 documented fields
    for field in ("address", "rating", "score", "floor_area", "property_type",
                  "floor_level", "habitable_rooms", "inspection_date", "lmk_key"):
        assert field in first, f"missing field: {field}"

    # Must strip raw and other non-slim fields
    assert "raw" not in first
    assert "uprn" not in first
    assert first["lmk_key"] == "aaa111"
    assert first["floor_area"] == 55.0


def test_property_epc_search_filters_to_keep_fields_only():
    """property_epc_search strips any fields outside the documented 9-field keep set."""
    from app.mcp.server import property_epc_search

    m = MagicMock()
    # Simulate what model_dump(exclude_none=True) returns for a real cert
    m.model_dump.return_value = {
        "address": "10 TEST STREET",
        "rating": "C",
        "score": 72,
        "property_type": "Flat",
        "inspection_date": "2023-01-01",
        "lmk_key": "abc123",
        # Fields outside keep set that should be dropped
        "uprn": "1234567890",
        "country": "England",
        "local_authority": "Westminster",
    }

    with patch("property_core.EPCClient") as mock_cls:
        mock_cls.return_value.search_all_by_postcode = AsyncMock(return_value=[m])
        result = asyncio.run(property_epc_search("SW1A 1AA"))

    assert result is not None
    first = result[0]
    assert "uprn" not in first
    assert "country" not in first
    assert "local_authority" not in first
    assert first["lmk_key"] == "abc123"


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
