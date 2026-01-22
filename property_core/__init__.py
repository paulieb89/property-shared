"""Pure-Python core library for property tooling.

This package contains reusable domain logic with minimal assumptions (no FastAPI,
no database/redis). The API service in `app/` wraps this package.
"""

from property_core.epc_client import EPCClient
from property_core.postcode_client import PostcodeClient
from property_core.ppd_client import PricePaidDataClient
from property_core.rightmove_location import RightmoveLocationAPI
from property_core.rightmove_scraper import fetch_listings

__all__ = [
    "EPCClient",
    "PostcodeClient",
    "PricePaidDataClient",
    "RightmoveLocationAPI",
    "fetch_listings",
]

