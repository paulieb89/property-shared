#!/usr/bin/env python3
"""
Update planning_councils.json with verification results.

Reads the verification CSV and updates the councils database:
- Moves verified councils from untested to councils array
- Adds postcodes_io_name field where captured
- Marks failed councils with appropriate status
"""

import csv
import json
from datetime import date
from pathlib import Path


def load_verification_results(csv_path: Path) -> dict:
    """Load verification results from CSV."""
    results = {}
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row['code']
            results[code] = {
                'status': row['status'],
                'success': row['success'] == 'True',
                'postcodes_io_name': row.get('postcodes_io_name', '').strip() or None,
                'applications_found': int(row.get('applications_found', 0) or 0),
                'error': row.get('error', '').strip() or None,
            }
    return results


def main():
    # Paths
    csv_path = Path(__file__).parent.parent / "verification_idox_20.csv"
    councils_path = Path(__file__).parent.parent / "property_core" / "planning_councils.json"

    # Load data
    print(f"Loading verification results from: {csv_path}")
    verification = load_verification_results(csv_path)
    print(f"  Found {len(verification)} results")

    print(f"Loading councils from: {councils_path}")
    with open(councils_path) as f:
        data = json.load(f)

    original_verified = len(data.get('councils', []))
    original_untested = len(data.get('untested', []))
    print(f"  Original: {original_verified} verified, {original_untested} untested")

    # Track changes
    moved_to_verified = []
    updated_with_name = []
    marked_as_failed = []

    # Process untested councils
    new_untested = []
    new_councils = data.get('councils', []).copy()

    for council in data.get('untested', []):
        code = council.get('code')

        if code not in verification:
            # Not tested yet
            new_untested.append(council)
            continue

        result = verification[code]

        if result['success']:
            # Move to verified councils
            council['status'] = 'verified'
            council['verified_date'] = date.today().isoformat()

            # Add postcodes_io_name if captured
            if result['postcodes_io_name']:
                council['postcodes_io_name'] = result['postcodes_io_name']
                updated_with_name.append(code)

            new_councils.append(council)
            moved_to_verified.append(code)
        else:
            # Mark with failure status
            status = result['status']
            if status == 'dns_failed':
                council['status'] = 'dns_failed'
            elif status in ('timeout', 'error'):
                council['status'] = 'needs_investigation'
            elif status == 'no_match':
                council['status'] = 'postcode_mapping_issue'
            elif status == 'no_postcode':
                council['status'] = 'no_test_postcode'
            else:
                council['status'] = status

            # Still add postcodes_io_name if captured
            if result['postcodes_io_name']:
                council['postcodes_io_name'] = result['postcodes_io_name']

            new_untested.append(council)
            marked_as_failed.append((code, status))

    # Update data
    data['councils'] = new_councils
    data['untested'] = new_untested

    # Save
    with open(councils_path, 'w') as f:
        json.dump(data, f, indent=2)

    # Report
    print(f"\n=== Update Summary ===")
    print(f"Moved to verified: {len(moved_to_verified)}")
    print(f"Updated with postcodes_io_name: {len(updated_with_name)}")
    print(f"Marked as failed: {len(marked_as_failed)}")

    print(f"\nNew totals: {len(new_councils)} verified, {len(new_untested)} untested")

    if moved_to_verified:
        print(f"\n✅ Newly verified councils:")
        for code in moved_to_verified[:10]:
            print(f"  - {code}")
        if len(moved_to_verified) > 10:
            print(f"  ... and {len(moved_to_verified) - 10} more")

    if marked_as_failed:
        print(f"\n❌ Failed councils:")
        for code, status in marked_as_failed:
            print(f"  - {code}: {status}")


if __name__ == "__main__":
    main()
