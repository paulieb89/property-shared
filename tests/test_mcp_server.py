import json
from unittest.mock import patch, MagicMock

from app.mcp.server import ppd_transactions


def test_ppd_transactions_results_are_json_serializable():
    """results must be plain dicts, not Pydantic models — regression check for model_dump() fix."""
    mock_tx = MagicMock()
    mock_tx.model_dump.return_value = {
        "transaction_id": "abc",
        "price": 250000,
        "date": "2024-01-15",
        "postcode": "SW1A 1AA",
        "property_type": "F",
        "new_build": False,
        "estate_type": "L",
        "paon": "1",
        "saon": None,
        "street": "TEST ST",
        "locality": None,
        "town": "LONDON",
        "district": "WESTMINSTER",
        "county": "GREATER LONDON",
        "transaction_category": "A",
        "record_status": "A",
        "raw": None,
    }
    mock_result = {
        "count": 1,
        "limit": 10,
        "offset": 0,
        "results": [mock_tx],
        "warnings": [],
        "raw": None,
    }
    with patch("property_core.PPDService") as MockService:
        MockService.return_value.search_transactions.return_value = mock_result
        result = ppd_transactions(postcode="SW1A 1AA")

    assert all(isinstance(r, dict) for r in result["results"]), \
        "results items must be plain dicts after model_dump()"
    json.dumps(result)


def test_ppd_transactions_passes_kwargs():
    """postcode, limit, and property_type are forwarded to PPDService.search_transactions."""
    mock_result = {
        "count": 0,
        "limit": 5,
        "offset": 0,
        "results": [],
        "warnings": [],
        "raw": None,
    }
    with patch("property_core.PPDService") as MockService:
        MockService.return_value.search_transactions.return_value = mock_result
        result = ppd_transactions(postcode="NG1 1AA", limit=5, property_type="F")
        call_kwargs = MockService.return_value.search_transactions.call_args.kwargs

    assert call_kwargs["postcode"] == "NG1 1AA"
    assert call_kwargs["limit"] == 5
    assert call_kwargs["property_type"] == "F"
    assert result["count"] == 0
