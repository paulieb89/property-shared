"""EPC Register API client."""

import base64
import re

import httpx

from ..config import settings
from ..models.enrichment import EPCData


def _normalize_address(address: str) -> str:
    """Normalize address for comparison."""
    # Lowercase, remove punctuation, normalize whitespace
    addr = address.lower()
    addr = re.sub(r"[,.'\"()-]", " ", addr)
    addr = re.sub(r"\s+", " ", addr).strip()
    return addr


def _extract_number(address: str) -> str | None:
    """Extract house number from address."""
    match = re.match(r"^(\d+[a-zA-Z]?)\b", address.strip())
    return match.group(1).lower() if match else None


def _extract_street(address: str) -> str | None:
    """Extract street name from address."""
    # Remove house number and normalize
    addr = re.sub(r"^\d+[a-zA-Z]?\s*", "", address.strip())
    addr = _normalize_address(addr)
    # Take first part (street name)
    parts = addr.split()
    if len(parts) >= 2:
        return " ".join(parts[:2])  # e.g., "jade close"
    return parts[0] if parts else None


def _match_score(cert_address: str, target_address: str) -> int:
    """Score how well a certificate address matches the target."""
    cert_norm = _normalize_address(cert_address)
    target_norm = _normalize_address(target_address)

    score = 0

    # Exact match
    if cert_norm == target_norm:
        return 100

    # House number match (most important)
    cert_num = _extract_number(cert_address)
    target_num = _extract_number(target_address)
    if cert_num and target_num and cert_num == target_num:
        score += 50

    # Street name match
    cert_street = _extract_street(cert_address)
    target_street = _extract_street(target_address)
    if cert_street and target_street:
        if cert_street == target_street:
            score += 30
        elif cert_street in target_street or target_street in cert_street:
            score += 15

    # Partial word overlap
    cert_words = set(cert_norm.split())
    target_words = set(target_norm.split())
    overlap = len(cert_words & target_words)
    score += min(overlap * 3, 15)

    return score


class EPCClient:
    """Client for UK EPC Register API."""

    BASE_URL = "https://epc.opendatacommunities.org/api/v1"

    def __init__(self, email: str | None = None, api_key: str | None = None):
        self.email = email or settings.epc_api_email
        self.api_key = api_key or settings.epc_api_key

    def _auth_header(self) -> dict[str, str]:
        """Generate Basic Auth header."""
        if not self.email or not self.api_key:
            return {}
        creds = base64.b64encode(f"{self.email}:{self.api_key}".encode()).decode()
        return {"Authorization": f"Basic {creds}"}

    def _parse_certificate(self, cert: dict) -> EPCData:
        """Parse a certificate dict into EPCData with all fields."""

        def safe_int(val) -> int | None:
            if val is None or val == "":
                return None
            try:
                return int(float(val))
            except (ValueError, TypeError):
                return None

        def safe_float(val) -> float | None:
            if val is None or val == "":
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        return EPCData(
            # Core ratings
            rating=cert.get("current-energy-rating", "?"),
            score=safe_int(cert.get("current-energy-efficiency")) or 0,
            potential_rating=cert.get("potential-energy-rating"),
            potential_score=safe_int(cert.get("potential-energy-efficiency")),
            # Property details
            address=cert.get("address"),
            floor_area=safe_float(cert.get("total-floor-area")),
            built_form=cert.get("built-form"),
            property_type=cert.get("property-type"),
            construction_age=cert.get("construction-age-band"),
            # Running costs
            heating_cost_current=safe_int(cert.get("heating-cost-current")),
            heating_cost_potential=safe_int(cert.get("heating-cost-potential")),
            hot_water_cost_current=safe_int(cert.get("hot-water-cost-current")),
            hot_water_cost_potential=safe_int(cert.get("hot-water-cost-potential")),
            lighting_cost_current=safe_int(cert.get("lighting-cost-current")),
            lighting_cost_potential=safe_int(cert.get("lighting-cost-potential")),
            # Heating system
            main_fuel=cert.get("main-fuel"),
            main_heating=cert.get("mainheat-description"),
            hot_water=cert.get("hotwater-description"),
            # Component efficiency
            walls_efficiency=cert.get("walls-energy-eff"),
            roof_efficiency=cert.get("roof-energy-eff"),
            floor_efficiency=cert.get("floor-energy-eff"),
            windows_efficiency=cert.get("windows-energy-eff"),
            windows_description=cert.get("windows-description"),
            # Environmental
            co2_emissions_current=safe_float(cert.get("co2-emissions-current")),
            co2_emissions_potential=safe_float(cert.get("co2-emissions-potential")),
            # Metadata
            inspection_date=cert.get("inspection-date"),
            certificate_hash=cert.get("lmk-key"),
        )

    async def search_by_postcode(
        self, postcode: str, address: str | None = None
    ) -> EPCData | None:
        """Search for EPC by postcode, optionally matching address.

        Args:
            postcode: UK postcode to search
            address: Optional address to match against results

        Returns:
            Best matching EPCData or most recent if no address provided
        """
        if not self.email or not self.api_key:
            return None  # Not configured

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(
                    f"{self.BASE_URL}/domestic/search",
                    params={"postcode": postcode.replace(" ", "")},
                    headers={
                        "Accept": "application/json",
                        **self._auth_header(),
                    },
                )
                resp.raise_for_status()
                data = resp.json()

                rows = data.get("rows", [])
                if not rows:
                    return None

                # If address provided, find best match
                if address:
                    best_cert = None
                    best_score = -1

                    for cert in rows:
                        cert_addr = cert.get("address", "")
                        score = _match_score(cert_addr, address)
                        if score > best_score:
                            best_score = score
                            best_cert = cert

                    # Only use match if score is reasonable (>= 30)
                    if best_cert and best_score >= 30:
                        return self._parse_certificate(best_cert)

                # Fall back to most recent certificate
                return self._parse_certificate(rows[0])

            except (httpx.HTTPError, KeyError, ValueError):
                return None
