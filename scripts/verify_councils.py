#!/usr/bin/env python3
"""
Council Verification Script

Systematically verifies untested councils in the planning_councils.json database.
For each council, finds a representative postcode and runs a planning search
to verify the portal works with our vision-guided scraper.

Usage:
    uv run python scripts/verify_councils.py --system idox --limit 10
    uv run python scripts/verify_councils.py --all
    uv run python scripts/verify_councils.py --resume
    uv run python scripts/verify_councils.py --dry-run
"""

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from property_core.planning_scraper import search_planning_by_postcode
from property_core.postcode_client import PostcodeClient


# Postcode mappings for councils (council_code -> postcode)
# These are city-center postcodes that map back to each council via postcodes.io
COUNCIL_POSTCODES = {
    # Scotland
    "aberdeen": "AB10 1AB",
    "edinburgh": "EH1 1BB",
    "glasgow": "G1 1AA",
    # Wales
    "cardiff": "CF10 1AA",
    # Northern Ireland
    "northern-ireland": "BT1 1AA",
    # London boroughs
    "city-of-london": "EC1A 1AA",
    "barking-and-dagenham": "IG11 7LZ",
    "barnet": "N2 0AB",
    "bedford": "MK40 1AA",
    "bexley": "DA5 1AA",
    "brent": "NW10 1AA",
    "bromley": "BR1 1AA",
    "camden": "NW1 1AA",
    "croydon": "CR0 1AA",
    "ealing": "W5 1AA",
    "enfield": "EN1 1AA",
    "greenwich": "SE10 9LS",
    "hackney": "E8 1AA",
    "hammersmith-and-fulham": "W6 9AA",
    "haringey": "N8 0AA",
    "harrow": "HA1 1AA",
    "havering": "RM1 1AA",
    "hillingdon": "UB8 1AA",
    "hounslow": "TW3 1AA",
    "islington": "N1 1AA",
    "kensington-and-chelsea": "W8 4AA",
    "kingston-upon-thames": "KT1 1AA",
    "lambeth": "SW9 6AA",
    "lewisham": "SE13 5AA",
    "merton": "SW19 1AA",
    "newham": "E15 1AA",
    "redbridge": "IG1 1AA",
    "richmond": "TW9 1AA",
    "southwark": "SE1 1AA",
    "sutton": "SM1 1AA",
    "tower-hamlets": "E1 1AA",
    "waltham-forest": "E17 1AA",
    "wandsworth": "SW18 1AA",
    "westminster": "SW1A 1AA",
    # Major cities
    "birmingham": "B2 4QA",
    "bradford": "BD1 1HX",
    "brighton-and-hove": "BN1 1AA",
    "bristol": "BS1 5TJ",
    "cambridge": "CB1 1AA",
    "coventry": "CV1 1AA",
    "derby": "DE1 1AA",
    "hull": "HU1 1AA",
    "leeds": "LS1 1AA",
    "leicester": "LE1 1AA",
    "liverpool": "L1 1AA",
    "manchester": "M1 3NJ",
    "newcastle-upon-tyne": "NE1 3AF",
    "nottingham": "NG1 1AA",
    "oxford": "OX1 1AA",
    "peterborough": "PE1 1AA",
    "plymouth": "PL1 1AA",
    "portsmouth": "PO1 1AA",
    "reading": "RG1 1AA",
    "sheffield": "S1 2HH",
    "southampton": "SO14 1AA",
    "stoke-on-trent": "ST1 1AA",
    "sunderland": "SR1 1AA",
    "wolverhampton": "WV1 1AA",
    "york": "YO1 1AA",
    # Metropolitan boroughs
    "bolton": "BL1 1AA",
    "bury": "BL9 0EY",
    "calderdale": "HX1 1AA",
    "doncaster": "DN1 1AA",
    "dudley": "DY1 1AA",
    "gateshead": "NE8 1AA",
    "kirklees": "HD1 1AA",
    "knowsley": "L36 1AA",
    "oldham": "OL1 1AA",
    "rochdale": "OL16 1AA",
    "rotherham": "S60 1AA",
    "salford": "M3 5AA",
    "sandwell": "B70 8AA",
    "sefton": "L20 1AA",
    "solihull": "B91 1AA",
    "south-tyneside": "NE33 1AA",
    "st-helens": "WA10 1AA",
    "stockport": "SK1 1AA",
    "tameside": "OL6 1AA",
    "trafford": "M32 0AA",
    "wakefield": "WF1 1AA",
    "walsall": "WS1 1AA",
    "wigan": "WN1 1AA",
    "wirral": "CH41 1AA",
    # Unitary authorities and districts
    "adur-and-worthing": "BN11 1AA",
    "allerdale": "CA14 1AA",
    "aylesbury-vale": "HP20 1AA",
    "babergh": "IP7 5AA",
    "blackpool": "FY1 1EZ",
    "bracknell-forest": "RG12 1AA",
    "cheshire-west-and-chester": "CH1 2HJ",
    "cornwall": "TR1 1AA",
    "county-durham": "DH1 3TF",
    "darlington": "DL1 1AA",
    "east-riding-of-yorkshire": "HU17 1AA",
    "epsom-and-ewell": "KT17 1AA",
    "milton-keynes": "MK9 1AA",
    "north-east-lincolnshire": "DN31 1AA",
    "north-lincolnshire": "DN15 1AA",
    "north-somerset": "BS23 1AA",
    "north-tyneside": "NE29 1AA",
    "northumberland": "NE61 1AA",
    "poole": "BH15 1AA",
    "rutland": "LE15 6AA",
    "south-downs": "GU29 9AA",
    "south-gloucestershire": "BS16 1AA",
    "southend-on-sea": "SS1 1AA",
    "stockton-on-tees": "TS18 1AA",
    "swindon": "SN1 1AA",
    "thurrock": "RM17 1AA",
    "torbay": "TQ1 1AA",
    "west-berkshire": "RG14 1AA",
    "windsor-and-maidenhead": "SL4 1AA",
}


def get_representative_postcode(council: dict) -> str | None:
    """
    Get a postcode that maps to this council.
    Uses the pre-built COUNCIL_POSTCODES mapping.
    """
    code = council.get("code", "")
    return COUNCIL_POSTCODES.get(code)


def verify_council(council: dict, postcode: str, delay_after: float = 5.0, postcode_client: PostcodeClient = None) -> dict:
    """
    Run planning search for a council and record results.

    Returns dict with verification results.
    """
    result = {
        "code": council.get("code"),
        "name": council.get("name"),
        "system": council.get("system"),
        "base_url": council.get("base_url"),
        "postcode_tested": postcode,
        "postcodes_io_name": None,  # Will be populated from postcodes.io lookup
        "success": False,
        "status": "failed",
        "applications_found": 0,
        "error": None,
        "duration_seconds": 0,
        "timestamp": datetime.now().isoformat()
    }

    # Look up postcodes.io admin_district for this postcode
    if postcode_client:
        try:
            la_info = postcode_client.get_local_authority(postcode)
            if la_info:
                result["postcodes_io_name"] = la_info.get("name")
        except Exception:
            pass  # Non-critical, continue with verification

    start = time.time()

    try:
        # Build the search URL directly from council info (no postcodes.io lookup)
        base_url = council.get("base_url", "").rstrip("/")
        system = council.get("system", "").lower()
        postcode_clean = postcode.replace(" ", "").upper()

        if not base_url:
            result["error"] = "No base URL available"
            result["status"] = "no_url"
            return result

        # Build portal URL based on system type
        if system == "idox":
            portal_url = f"{base_url}/search.do?action=simple&searchType=Application&PostCode={postcode_clean}"
        else:
            # For non-Idox, just use base URL (will need form filling)
            portal_url = base_url

        # Run the search
        applications = search_planning_by_postcode(
            portal_url=portal_url,
            postcode=postcode,
            max_results=5,  # Just need to verify it works
            system=system,
        )

        result["applications_found"] = len(applications) if applications else 0

        # Determine success
        if applications and len(applications) > 0:
            result["success"] = True
            result["status"] = "verified"
        elif applications is not None:
            # Empty list is valid (no applications in that area)
            result["success"] = True
            result["status"] = "verified_empty"
        else:
            result["error"] = "No applications extracted"
            result["status"] = "extraction_failed"

    except Exception as e:
        error_str = str(e)
        result["error"] = error_str[:200]  # Truncate long errors

        # Categorize error
        if "reCAPTCHA" in error_str or "captcha" in error_str.lower():
            result["status"] = "blocked_captcha"
        elif "403" in error_str or "Access Denied" in error_str:
            result["status"] = "blocked_403"
        elif "timeout" in error_str.lower() or "Timeout" in error_str:
            result["status"] = "timeout"
        elif "ERR_NAME_NOT_RESOLVED" in error_str or "DNS" in error_str:
            result["status"] = "dns_failed"
        elif "SSL" in error_str or "certificate" in error_str.lower():
            result["status"] = "ssl_error"
        else:
            result["status"] = "error"

    finally:
        result["duration_seconds"] = round(time.time() - start, 1)

        # Add delay between requests
        if delay_after > 0:
            time.sleep(delay_after)

    return result


def load_councils(councils_path: Path) -> dict:
    """Load councils database."""
    with open(councils_path) as f:
        return json.load(f)


def save_results(results: list[dict], output_path: Path):
    """Save results to CSV."""
    if not results:
        return

    fieldnames = [
        "code", "name", "system", "status", "success", "postcode_tested",
        "postcodes_io_name", "applications_found", "error", "duration_seconds", "timestamp", "base_url"
    ]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nResults saved to: {output_path}")


def load_checkpoint(checkpoint_path: Path) -> tuple[set, list[dict]]:
    """Load already-verified council codes and results from checkpoint."""
    if not checkpoint_path.exists():
        return set(), []

    verified = set()
    results = []
    with open(checkpoint_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            verified.add(row.get("code"))
            results.append(row)
    return verified, results


def main():
    parser = argparse.ArgumentParser(description="Verify council planning portals")
    parser.add_argument("--system", help="Filter by system type (idox, northgate, ocella, custom)")
    parser.add_argument("--limit", type=int, help="Max councils to verify")
    parser.add_argument("--all", action="store_true", help="Verify all untested councils")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be tested")
    parser.add_argument("--delay", type=float, default=5.0, help="Delay between requests (seconds)")
    parser.add_argument("--output", help="Output CSV path", default="verification_results.csv")

    args = parser.parse_args()

    # Paths
    councils_path = Path(__file__).parent.parent / "property_core" / "planning_councils.json"
    output_path = Path(args.output)
    checkpoint_path = output_path  # Use same file as checkpoint

    # Load councils
    print(f"Loading councils from: {councils_path}")
    data = load_councils(councils_path)

    untested = data.get("untested", [])
    print(f"Total untested councils: {len(untested)}")

    # Filter by system if specified
    if args.system:
        untested = [c for c in untested if c.get("system") == args.system]
        print(f"Filtered to {args.system}: {len(untested)}")

    # Load checkpoint if resuming
    already_verified = set()
    previous_results = []
    if args.resume:
        already_verified, previous_results = load_checkpoint(checkpoint_path)
        untested = [c for c in untested if c.get("code") not in already_verified]
        print(f"Resuming - skipping {len(already_verified)} already verified")
        print(f"Remaining to verify: {len(untested)}")

    # Apply limit
    if args.limit:
        untested = untested[:args.limit]
        print(f"Limited to: {len(untested)}")

    if args.dry_run:
        print("\n--- DRY RUN ---")
        print(f"Would verify {len(untested)} councils:")
        for c in untested[:20]:
            print(f"  - {c.get('name')} ({c.get('system')})")
        if len(untested) > 20:
            print(f"  ... and {len(untested) - 20} more")
        return

    if not untested:
        print("No councils to verify")
        return

    # Initialize with previous results if resuming
    results = previous_results.copy() if args.resume else []

    # Create postcode client for looking up admin_district names
    postcode_client = PostcodeClient()

    # Verify each council
    print(f"\n--- Starting verification of {len(untested)} councils ---\n")

    for i, council in enumerate(untested, 1):
        code = council.get("code")
        name = council.get("name")
        system = council.get("system")

        print(f"[{i}/{len(untested)}] {name} ({system})")

        # Get postcode
        postcode = get_representative_postcode(council)
        if not postcode:
            print(f"  Skipping - no postcode found")
            results.append({
                "code": code,
                "name": name,
                "system": system,
                "base_url": council.get("base_url"),
                "postcode_tested": None,
                "postcodes_io_name": None,
                "success": False,
                "status": "no_postcode",
                "applications_found": 0,
                "error": "Could not find representative postcode",
                "duration_seconds": 0,
                "timestamp": datetime.now().isoformat()
            })
            continue

        print(f"  Postcode: {postcode}")

        # Verify
        result = verify_council(council, postcode, delay_after=args.delay, postcode_client=postcode_client)
        results.append(result)

        # Report
        status = result.get("status")
        apps = result.get("applications_found", 0)
        duration = result.get("duration_seconds", 0)
        postcodes_io_name = result.get("postcodes_io_name", "")

        if result.get("success"):
            print(f"  ✅ {status} - {apps} apps found ({duration}s)")
            if postcodes_io_name:
                print(f"     postcodes.io name: {postcodes_io_name}")
        else:
            error = result.get("error", "Unknown error")[:60]
            print(f"  ❌ {status} - {error} ({duration}s)")
            if postcodes_io_name:
                print(f"     postcodes.io name: {postcodes_io_name}")

        # Save checkpoint periodically
        if i % 5 == 0:
            save_results(results, output_path)

    # Final save
    save_results(results, output_path)

    # Summary
    print("\n--- Summary ---")
    success = [r for r in results if r.get("success")]
    blocked = [r for r in results if "blocked" in r.get("status", "")]
    errors = [r for r in results if not r.get("success") and "blocked" not in r.get("status", "")]

    print(f"Verified: {len(success)}")
    print(f"Blocked: {len(blocked)}")
    print(f"Errors: {len(errors)}")

    if success:
        print(f"\n✅ Verified councils:")
        for r in success[:10]:
            print(f"  - {r.get('name')} ({r.get('applications_found')} apps)")
        if len(success) > 10:
            print(f"  ... and {len(success) - 10} more")

    if blocked:
        print(f"\n❌ Blocked councils:")
        for r in blocked[:5]:
            print(f"  - {r.get('name')}: {r.get('status')}")


if __name__ == "__main__":
    main()
