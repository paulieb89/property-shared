"""
Lightweight diagnostics for UK planning portals.
Tests accessibility and tab detection WITHOUT calling OpenAI Vision API.

Usage:
    python -m property_core.planning_diagnostics [council_code]
    python -m property_core.planning_diagnostics --all
"""
import json
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

# Load councils from JSON
COUNCILS_FILE = Path(__file__).parent / "planning_councils.json"

# Tab selectors by system type
TAB_SELECTORS = {
    "idox": [
        "a[href*='activeTab=summary']",
        "a[href*='activeTab=details']",
        "a[href*='activeTab=dates']",
        "a[href*='activeTab=map']",
        "a[href*='activeTab=constraints']",
        "a[href*='activeTab=documents']",
        "a[href*='activeTab=relatedCases']",
    ],
    "northgate": [
        "a[href*='TabIndex=0']",
        "a[href*='TabIndex=1']",
        "a[href*='TabIndex=2']",
        ".tabStrip a",
        "ul.tabs a",
    ],
    "generic": [
        "a:has-text('Summary')",
        "a:has-text('Details')",
        "a:has-text('Documents')",
        "[role='tab']",
    ],
}


def load_councils() -> dict:
    """Load councils from JSON file."""
    with open(COUNCILS_FILE) as f:
        return json.load(f)


def detect_system_from_url(url: str) -> str:
    """Detect likely system from URL patterns."""
    url_lower = url.lower()

    if "northgate" in url_lower or "planningexplorer" in url_lower:
        return "northgate"
    if "publicaccess" in url_lower or "online-applications" in url_lower or "idoxpa" in url_lower:
        return "idox"
    if "arcus" in url_lower:
        return "arcus"

    return "unknown"


def diagnose_portal(
    base_url: str,
    name: str,
    system: Optional[str] = None,
    example_app: Optional[str] = None,
) -> dict:
    """
    Run diagnostics on a council portal WITHOUT using Vision API.

    Tests:
    1. URL accessibility (HTTP response)
    2. Page rendering in headless browser
    3. Tab selector detection
    4. System fingerprinting
    """
    if sync_playwright is None:
        return {"error": "playwright not installed"}

    result = {
        "name": name,
        "base_url": base_url,
        "declared_system": system,
        "detected_system": detect_system_from_url(base_url),
        "tests": {},
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        page = context.new_page()

        # Test 1: Can we load the base URL?
        try:
            response = page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
            result["tests"]["base_url_accessible"] = True
            result["tests"]["http_status"] = response.status if response else None
        except Exception as e:
            result["tests"]["base_url_accessible"] = False
            result["tests"]["base_url_error"] = str(e)[:100]
            browser.close()
            return result

        # Test 2: Check for blocking (Cloudflare, captcha, etc.)
        try:
            page.wait_for_timeout(2000)
            html = page.content().lower()
            title = page.title().lower()

            blocking_indicators = []
            # Only count cloudflare if it's a challenge page
            if "cloudflare" in html and ("challenge" in html or "ray id" in html):
                blocking_indicators.append("cloudflare_challenge")
            # Only count captcha if it's actively blocking (not just mentioned in scripts)
            if ("captcha" in title or "verify" in title) or ("g-recaptcha" in html and "data-sitekey" in html):
                # Check if it's actually a challenge page vs just having recaptcha on a form
                if "robot" in html or "verify you" in html or "human" in html:
                    blocking_indicators.append("captcha_challenge")
            if "access denied" in html or "403 forbidden" in html:
                blocking_indicators.append("access_denied")
            if "please enable javascript" in title:
                blocking_indicators.append("js_required")

            result["tests"]["blocking_detected"] = blocking_indicators if blocking_indicators else None
            result["tests"]["page_title"] = page.title()[:100]
        except Exception as e:
            result["tests"]["blocking_check_error"] = str(e)[:100]

        # Test 3: System fingerprinting from page content
        try:
            fingerprints = []
            if "idox" in html or "public access" in html:
                fingerprints.append("idox")
            if "northgate" in html or "planning explorer" in html:
                fingerprints.append("northgate")
            if "arcus" in html:
                fingerprints.append("arcus")
            if "ocella" in html:
                fingerprints.append("ocella")

            result["tests"]["page_fingerprints"] = fingerprints if fingerprints else None
        except Exception:
            pass

        # Test 4: If we have an example app URL, test tab detection
        if example_app:
            try:
                page.goto(example_app, wait_until="networkidle", timeout=45000)
                page.wait_for_timeout(2000)

                result["tests"]["example_app_loaded"] = True

                # Test each system's tab selectors
                detected_system = result["detected_system"]
                selectors = TAB_SELECTORS.get(detected_system, TAB_SELECTORS["generic"])

                tabs_found = []
                for selector in selectors:
                    try:
                        count = page.locator(selector).count()
                        if count > 0:
                            tabs_found.append({"selector": selector, "count": count})
                    except Exception:
                        pass

                result["tests"]["tabs_found"] = tabs_found
                result["tests"]["tab_detection_success"] = len(tabs_found) > 0

                # Also try generic selectors as fallback
                generic_tabs = []
                for selector in TAB_SELECTORS["generic"]:
                    try:
                        count = page.locator(selector).count()
                        if count > 0:
                            generic_tabs.append({"selector": selector, "count": count})
                    except Exception:
                        pass
                result["tests"]["generic_tabs_found"] = generic_tabs

            except Exception as e:
                result["tests"]["example_app_loaded"] = False
                result["tests"]["example_app_error"] = str(e)[:100]

        browser.close()

    # Overall verdict
    tests = result["tests"]
    blocking = tests.get("blocking_detected")
    if not tests.get("base_url_accessible"):
        result["verdict"] = "UNREACHABLE"
    elif blocking and len(blocking) > 0:
        result["verdict"] = f"BLOCKED ({', '.join(blocking)})"
    elif tests.get("tab_detection_success"):
        result["verdict"] = "LIKELY_COMPATIBLE"
    elif example_app and tests.get("example_app_loaded"):
        result["verdict"] = "NEEDS_CUSTOM_SELECTORS"
    elif tests.get("base_url_accessible"):
        result["verdict"] = "ACCESSIBLE"
    else:
        result["verdict"] = "UNKNOWN"

    return result


def run_all_diagnostics() -> list[dict]:
    """Run diagnostics on all councils in the JSON file."""
    data = load_councils()
    results = []

    all_councils = [
        (c, "VERIFIED") for c in data.get("councils", [])
    ] + [
        (c, "UNTESTED") for c in data.get("untested", [])
    ]

    for council, status in all_councils:
        print(f"\n{'='*60}")
        print(f"Testing: {council['name']} ({status})")
        try:
            result = diagnose_portal(
                base_url=council["base_url"],
                name=council["name"],
                system=council.get("system"),
                example_app=council.get("example_app"),
            )
            results.append(result)
            print(f"  Verdict: {result.get('verdict', 'ERROR')}")
        except Exception as e:
            print(f"  ERROR: {str(e)[:80]}")
            results.append({
                "name": council["name"],
                "verdict": f"CRASHED ({str(e)[:50]})",
            })

    return results


def diagnose_single(code: str) -> dict:
    """Diagnose a single council by code."""
    data = load_councils()

    # Check verified councils
    for council in data.get("councils", []):
        if council["code"] == code:
            return diagnose_portal(
                base_url=council["base_url"],
                name=council["name"],
                system=council.get("system"),
                example_app=council.get("example_app"),
            )

    # Check untested councils
    for council in data.get("untested", []):
        if council["code"] == code:
            return diagnose_portal(
                base_url=council["base_url"],
                name=council["name"],
                system=council.get("system"),
                example_app=council.get("example_app"),
            )

    return {"error": f"Council '{code}' not found"}


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--all":
            results = run_all_diagnostics()
            print(f"\n{'='*60}")
            print("SUMMARY")
            print("="*60)
            for r in results:
                print(f"  {r.get('name', 'Unknown')}: {r.get('verdict', 'UNKNOWN')}")
        else:
            result = diagnose_single(sys.argv[1])
            print(json.dumps(result, indent=2))
    else:
        print("Usage:")
        print("  python -m property_core.planning_diagnostics [council_code]")
        print("  python -m property_core.planning_diagnostics --all")
        print("\nAvailable council codes:")
        data = load_councils()
        for c in data.get("councils", []) + data.get("untested", []):
            print(f"  - {c['code']}")
