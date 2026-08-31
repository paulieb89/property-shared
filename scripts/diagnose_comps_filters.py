"""Diagnose data quality of PPDService.comps() output.

Goal: characterise the gap between the current (unfiltered) behaviour and the
proposed defaults (residential standard sales only, outlier-filtered). Run this
before and after the data-parity fix to see the delta.

Usage:
    uv run python scripts/diagnose_comps_filters.py
    uv run python scripts/diagnose_comps_filters.py NG1 2NS
    uv run python scripts/diagnose_comps_filters.py SW1A 1AA --level district
"""
from __future__ import annotations

import argparse
from collections import Counter
from statistics import mean, median, quantiles

from property_core import PPDService


RESIDENTIAL_TYPES = {"F", "D", "S", "T"}


def iqr_filter(prices: list[int]) -> tuple[list[int], list[int]]:
    """Return (kept, excluded) using 1.5 * IQR rule. Needs >= 4 prices."""
    if len(prices) < 4:
        return prices, []
    q = quantiles(prices, n=4)
    q1, q3 = q[0], q[2]
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    kept = [p for p in prices if lo <= p <= hi]
    excluded = [p for p in prices if p < lo or p > hi]
    return kept, excluded


def stats_block(label: str, prices: list[int]) -> None:
    if not prices:
        print(f"  {label}: (no prices)")
        return
    print(f"  {label}: n={len(prices)}")
    print(f"    min    £{min(prices):>10,}")
    print(f"    p25    £{int(round(quantiles(prices, n=4)[0])):>10,}" if len(prices) >= 4 else "")
    print(f"    median £{int(median(prices)):>10,}")
    print(f"    mean   £{int(round(mean(prices))):>10,}")
    print(f"    p75    £{int(round(quantiles(prices, n=4)[2])):>10,}" if len(prices) >= 4 else "")
    print(f"    max    £{max(prices):>10,}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("postcode", nargs="*", default=["NG1", "2NS"])
    parser.add_argument("--level", default="sector", choices=["postcode", "sector", "district"])
    parser.add_argument("--months", type=int, default=24)
    args = parser.parse_args()
    postcode = " ".join(args.postcode)

    print(f"\n{'='*70}")
    print(f"  Postcode: {postcode}    Level: {args.level}    Months: {args.months}")
    print(f"{'='*70}\n")

    service = PPDService()
    resp = service.comps(
        postcode=postcode,
        search_level=args.level,
        months=args.months,
        auto_escalate=False,
    )

    txns = resp.transactions
    print(f"Raw transactions returned by comps(): {len(txns)}\n")

    # --- Breakdown by transaction_category ---
    print("Breakdown by transaction_category:")
    cat_counts = Counter(t.transaction_category for t in txns)
    for cat, n in sorted(cat_counts.items(), key=lambda x: -x[1]):
        label = {"A": "standard sales", "B": "bulk/non-standard transfers"}.get(cat or "", "unknown")
        print(f"  {cat or '<null>':<6} {n:>3}   ({label})")
    print()

    # --- Breakdown by property_type ---
    print("Breakdown by property_type:")
    pt_counts = Counter(t.property_type for t in txns)
    pt_names = {"F": "Flat", "D": "Detached", "S": "Semi", "T": "Terraced", "O": "Other/commercial"}
    for pt, n in sorted(pt_counts.items(), key=lambda x: -x[1]):
        print(f"  {pt or '<null>':<6} {n:>3}   ({pt_names.get(pt or '', '?')})")
    print()

    # --- Current stats (what the API returns right now) ---
    print("CURRENT stats (no category/commercial/outlier filtering):")
    print(f"  Returned by service: count={resp.count}  median=£{resp.median or 0:,}  mean=£{resp.mean or 0:,}")
    print(f"                       min=£{resp.min or 0:,}  max=£{resp.max or 0:,}")
    print(f"                       p25=£{resp.percentile_25 or 0:,}  p75=£{resp.percentile_75 or 0:,}")
    print()

    # --- Apply proposed filters step-by-step ---
    print("PROPOSED filters applied step-by-step:\n")

    step1 = [t for t in txns if t.transaction_category == "A"]
    dropped_cat = len(txns) - len(step1)
    print(f"  Step 1 — keep transaction_category=='A':  {len(step1)} left ({dropped_cat} dropped)")

    step2 = [t for t in step1 if t.property_type in RESIDENTIAL_TYPES]
    dropped_comm = len(step1) - len(step2)
    print(f"  Step 2 — drop property_type=='O' (commercial):  {len(step2)} left ({dropped_comm} dropped)")

    prices_step2 = [t.price for t in step2 if t.price is not None]
    kept_prices, excluded_prices = iqr_filter(prices_step2)
    print(f"  Step 3 — IQR outlier filter (1.5*IQR):  {len(kept_prices)} left ({len(excluded_prices)} dropped)")
    if excluded_prices:
        print(f"           excluded: {[f'£{p:,}' for p in sorted(excluded_prices)]}")
    print()

    # --- Show what dropped at each step ---
    if dropped_cat > 0:
        print("Examples of category-B transactions dropped:")
        for t in [x for x in txns if x.transaction_category != "A"][:5]:
            print(f"  £{t.price or 0:>10,}  {t.date}  {t.property_type}  {t.paon or ''} {t.saon or ''} {t.street or ''}".rstrip())
        print()

    if dropped_comm > 0:
        print("Examples of commercial (property_type=O) transactions dropped:")
        for t in [x for x in step1 if x.property_type == "O"][:5]:
            print(f"  £{t.price or 0:>10,}  {t.date}  cat={t.transaction_category}  {t.paon or ''} {t.street or ''}".rstrip())
        print()

    # --- Final stats comparison ---
    print("="*70)
    print("STATS COMPARISON: current vs proposed")
    print("="*70)
    all_prices = [t.price for t in txns if t.price is not None]
    stats_block("CURRENT  (no filters)", all_prices)
    print()
    stats_block("PROPOSED (filters on)", kept_prices)
    print()

    if all_prices and kept_prices:
        cur_median = int(median(all_prices))
        new_median = int(median(kept_prices))
        cur_mean = int(round(mean(all_prices)))
        new_mean = int(round(mean(kept_prices)))
        print("Delta:")
        print(f"  median: £{cur_median:,}  -->  £{new_median:,}   ({(new_median-cur_median)/cur_median*100:+.1f}%)")
        print(f"  mean:   £{cur_mean:,}  -->  £{new_mean:,}   ({(new_mean-cur_mean)/cur_mean*100:+.1f}%)")
    print()


if __name__ == "__main__":
    main()
