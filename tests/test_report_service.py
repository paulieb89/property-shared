import asyncio
from unittest.mock import AsyncMock, patch

from property_core.report_service import PropertyReportService


EMPTY = {"success": False}


def _run(coro):
    return asyncio.run(coro)


def test_generate_report_calls_both_tasks_when_both_enabled():
    """Both _fetch_rental_data and _fetch_sales_market run when both include flags are True."""
    service = PropertyReportService()
    with (
        patch.object(service, "_fetch_ppd_data", new_callable=AsyncMock, return_value=EMPTY),
        patch.object(service, "_fetch_epc_data", new_callable=AsyncMock, return_value=EMPTY),
        patch.object(service, "_fetch_rental_data", new_callable=AsyncMock, return_value=EMPTY) as mock_rental,
        patch.object(service, "_fetch_sales_market", new_callable=AsyncMock, return_value=EMPTY) as mock_sales,
    ):
        report = _run(service.generate_report(
            "1 Test Street SW1A 1AA",
            include_rentals=True,
            include_sales_market=True,
        ))

    mock_rental.assert_called_once()
    mock_sales.assert_called_once()
    assert report is not None


def test_generate_report_only_rental_when_sales_disabled():
    """_fetch_sales_market is not called when include_sales_market=False."""
    service = PropertyReportService()
    with (
        patch.object(service, "_fetch_ppd_data", new_callable=AsyncMock, return_value=EMPTY),
        patch.object(service, "_fetch_epc_data", new_callable=AsyncMock, return_value=EMPTY),
        patch.object(service, "_fetch_rental_data", new_callable=AsyncMock, return_value=EMPTY) as mock_rental,
        patch.object(service, "_fetch_sales_market", new_callable=AsyncMock, return_value=EMPTY) as mock_sales,
    ):
        _run(service.generate_report(
            "1 Test Street SW1A 1AA",
            include_rentals=True,
            include_sales_market=False,
        ))

    mock_rental.assert_called_once()
    mock_sales.assert_not_called()


def test_generate_report_only_sales_when_rentals_disabled():
    """_fetch_rental_data is not called when include_rentals=False."""
    service = PropertyReportService()
    with (
        patch.object(service, "_fetch_ppd_data", new_callable=AsyncMock, return_value=EMPTY),
        patch.object(service, "_fetch_epc_data", new_callable=AsyncMock, return_value=EMPTY),
        patch.object(service, "_fetch_rental_data", new_callable=AsyncMock, return_value=EMPTY) as mock_rental,
        patch.object(service, "_fetch_sales_market", new_callable=AsyncMock, return_value=EMPTY) as mock_sales,
    ):
        _run(service.generate_report(
            "1 Test Street SW1A 1AA",
            include_rentals=False,
            include_sales_market=True,
        ))

    mock_rental.assert_not_called()
    mock_sales.assert_called_once()


def test_generate_report_invalid_address_raises():
    """ValueError is raised when the address contains no parseable postcode."""
    service = PropertyReportService()
    try:
        _run(service.generate_report("No Postcode Here"))
        assert False, "Expected ValueError"
    except ValueError:
        pass
