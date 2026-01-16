"""Quick test script for ppd_client functionality."""

from ppd_client import PricePaidDataClient, PROPERTY_TYPE_URIS, ESTATE_TYPE_URIS
from urllib.error import HTTPError, URLError


def test_url_builders():
    """Test URL construction (no network needed)."""
    client = PricePaidDataClient()

    # Complete URL
    assert "pp-complete.csv" in client.complete_url()
    assert "pp-complete.txt" in client.complete_url(fmt="txt")

    # Year URL
    assert "pp-2024.csv" in client.year_url(2024)
    assert "pp-2023-part1.csv" in client.year_url(2023, part=1)
    assert "pp-2023-part2.txt" in client.year_url(2023, part=2, fmt="txt")

    # Monthly change URL
    assert "pp-monthly-update" in client.monthly_change_url()

    print("✓ URL builders work")


def test_postcode_sector_parsing():
    """Test postcode parsing in get_comps_summary (no network needed)."""
    # We can't call the full method without network, but we can test the logic

    def parse_sector(postcode: str) -> str:
        """Extract sector from postcode."""
        pc = postcode.upper().strip()
        parts = pc.split()
        if len(parts) == 2 and len(parts[1]) >= 1:
            return f"{parts[0]} {parts[1][0]}"
        return parts[0] if parts else pc

    def parse_district(postcode: str) -> str:
        """Extract district from postcode."""
        pc = postcode.upper().strip()
        return pc.split()[0] if " " in pc else pc

    # Test sector parsing
    assert parse_sector("DE12 6DZ") == "DE12 6"
    assert parse_sector("SW1A 1AA") == "SW1A 1"
    assert parse_sector("M1 1AA") == "M1 1"
    assert parse_sector("de12 6dz") == "DE12 6"  # lowercase input

    # Test district parsing
    assert parse_district("DE12 6DZ") == "DE12"
    assert parse_district("SW1A 1AA") == "SW1A"
    assert parse_district("M1 1AA") == "M1"

    print("✓ Postcode parsing works")


def test_uri_resolution():
    """Test URI resolution for property/estate types."""
    client = PricePaidDataClient()

    # Property types
    assert client._resolve_uri("D", PROPERTY_TYPE_URIS) == PROPERTY_TYPE_URIS["D"]
    assert client._resolve_uri("d", PROPERTY_TYPE_URIS) == PROPERTY_TYPE_URIS["D"]
    assert client._resolve_uri("detached", PROPERTY_TYPE_URIS) == PROPERTY_TYPE_URIS["D"]

    # Estate types
    assert client._resolve_uri("F", ESTATE_TYPE_URIS) == ESTATE_TYPE_URIS["F"]
    assert client._resolve_uri("freehold", ESTATE_TYPE_URIS) == ESTATE_TYPE_URIS["F"]
    assert client._resolve_uri("L", ESTATE_TYPE_URIS) == ESTATE_TYPE_URIS["L"]

    # Full URI passthrough
    full_uri = "http://landregistry.data.gov.uk/def/common/detached"
    assert client._resolve_uri(full_uri, PROPERTY_TYPE_URIS) == full_uri

    print("✓ URI resolution works")


def test_sparql_search_live():
    """Test SPARQL search (requires network)."""
    client = PricePaidDataClient()

    try:
        rows = client.sparql_search(postcode_prefix="DE12", limit=3)
        bindings = rows.get("results", {}).get("bindings", [])

        assert len(bindings) <= 3
        if bindings:
            # Check expected fields exist
            first = bindings[0]
            assert "pricePaid" in first
            assert "postcode" in first
            assert "transactionDate" in first
            print(f"✓ SPARQL search works ({len(bindings)} results)")
        else:
            print("✓ SPARQL search works (no results, but no error)")

    except HTTPError as e:
        if e.code == 503:
            print("⚠ SPARQL endpoint unavailable (503) - skipping live test")
        else:
            raise
    except URLError as e:
        print(f"⚠ Network error - skipping live test: {e}")


def test_get_comps_summary_live():
    """Test comps summary (requires network)."""
    client = PricePaidDataClient()

    try:
        comps = client.get_comps_summary(
            postcode="DE12 6DZ",
            property_type="D",
            months=24,
            limit=10,
            search_level="sector"
        )

        # Check structure
        assert "query" in comps
        assert "count" in comps
        assert "median" in comps
        assert "mean" in comps
        assert "transactions" in comps
        assert "thin_market" in comps

        # Check query params recorded
        assert comps["query"]["postcode"] == "DE12 6DZ"
        assert comps["query"]["property_type"] == "D"
        assert comps["query"]["search_level"] == "sector"

        if comps["count"] > 0:
            # Check transaction structure
            t = comps["transactions"][0]
            assert "price" in t
            assert "date" in t
            assert "postcode" in t
            assert "property_type" in t

            print(f"✓ Comps summary works: {comps['count']} results, median £{comps['median']:,}")
        else:
            print("✓ Comps summary works (no results in area)")

    except HTTPError as e:
        if e.code == 503:
            print("⚠ SPARQL endpoint unavailable (503) - skipping live test")
        else:
            raise
    except URLError as e:
        print(f"⚠ Network error - skipping live test: {e}")


if __name__ == "__main__":
    print("Running ppd_client tests...\n")

    # Offline tests (always run)
    test_url_builders()
    test_postcode_sector_parsing()
    test_uri_resolution()

    print()

    # Live tests (may skip if API down)
    test_sparql_search_live()
    test_get_comps_summary_live()

    print("\nDone.")
