"""Measure data quality and token cost across the MCP fleet.

Captures a snapshot of:
  1. property_comps response token cost (plain MCP and MCP App equivalents)
  2. Tool inventory on each MCP server (which tools exist where)
  3. property_yield docstring quality
  4. Thin-market behaviour for yield + rental (does auto_escalate exist?)

Output: prints a structured report and writes JSON to /tmp/mcp_quality_<timestamp>.json
so before/after comparisons are easy.

Usage:
    uv run --env-file .env --extra dev --extra apps python scripts/measure_mcp_quality.py
    uv run --env-file .env --extra dev --extra apps python scripts/measure_mcp_quality.py --label before
    uv run --env-file .env --extra dev --extra apps python scripts/measure_mcp_quality.py --label after

The --label tags the output file (e.g. /tmp/mcp_quality_before.json).
"""
from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import tiktoken

ENC = tiktoken.get_encoding("cl100k_base")


def _tok(text: str) -> int:
    return len(ENC.encode(text))


def _count_nulls(obj: Any) -> tuple[int, int]:
    """Return (null_fields, total_fields) recursively."""
    nulls = 0
    total = 0
    if isinstance(obj, dict):
        for v in obj.values():
            total += 1
            if v is None:
                nulls += 1
            else:
                sub_n, sub_t = _count_nulls(v)
                nulls += sub_n
                total += sub_t
    elif isinstance(obj, list):
        for item in obj:
            sub_n, sub_t = _count_nulls(item)
            nulls += sub_n
            total += sub_t
    return nulls, total


async def measure_property_comps() -> dict:
    """Call the plain MCP property_comps tool and measure cost."""
    from app.mcp.server import property_comps

    test_cases = [
        {"postcode": "NG1 2NS", "search_level": "sector", "limit": 30, "enrich_epc": False, "label": "thin-sector-default-limit"},
        {"postcode": "NG1 2NS", "search_level": "district", "limit": 50, "enrich_epc": False, "label": "district-50"},
        {"postcode": "E14 5", "search_level": "sector", "limit": 30, "enrich_epc": False, "label": "dense-sector-default-limit"},
    ]
    results = []
    for case in test_cases:
        label = case.pop("label")
        t0 = time.perf_counter()
        try:
            result = await property_comps(**case)
        except Exception as exc:
            results.append({"case": label, "params": case, "error": str(exc)})
            continue
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        body = json.dumps(result, ensure_ascii=False)
        bytes_ct = len(body.encode("utf-8"))
        tokens = _tok(body)
        nulls, total = _count_nulls(result)
        txn_count = len(result.get("transactions", []))
        per_txn = tokens // max(txn_count, 1)
        results.append({
            "case": label,
            "params": case,
            "elapsed_ms": elapsed_ms,
            "bytes": bytes_ct,
            "tokens": tokens,
            "null_fields": nulls,
            "total_fields": total,
            "null_ratio_pct": round(100 * nulls / max(total, 1), 1),
            "txn_count": txn_count,
            "tokens_per_txn": per_txn,
            "median": result.get("median"),
            "mean": result.get("mean"),
        })
    return {"tool": "property_comps (plain MCP)", "cases": results}


async def measure_property_yield() -> dict:
    """Capture yield docstring + thin-market behaviour."""
    from app.mcp.server import property_yield

    sig = inspect.signature(property_yield)
    docstring = inspect.getdoc(property_yield) or "(no docstring)"
    has_auto_escalate = "auto_escalate" in sig.parameters

    test_cases: list[dict[str, Any]] = [
        {"postcode": "NG1 2NS", "search_level": "sector", "label": "thin-sector"},
        {"postcode": "DE12 7DH", "search_level": "sector", "label": "dense-sector"},
        {"postcode": "NG11 9HD", "search_level": "sector", "label": "ng11-sector"},
    ]
    results = []
    for case in test_cases:
        label = case.pop("label")
        try:
            result = await property_yield(**case)  # type: ignore[arg-type]
        except Exception as exc:
            results.append({"case": label, "params": case, "error": str(exc)})
            continue
        body = json.dumps(result, ensure_ascii=False)
        results.append({
            "case": label,
            "params": case,
            "tokens": _tok(body),
            "gross_yield_pct": result.get("gross_yield_pct"),
            "median_sale_price": result.get("median_sale_price"),
            "median_monthly_rent": result.get("median_monthly_rent"),
            "sale_count": result.get("sale_count"),
            "rental_count": result.get("rental_count"),
            "thin_market_handled": result.get("gross_yield_pct") is not None,
        })
    return {
        "tool": "property_yield (plain MCP)",
        "signature_has_auto_escalate": has_auto_escalate,
        "docstring": docstring,
        "docstring_length_chars": len(docstring),
        "cases": results,
    }


async def measure_rental_analysis() -> dict:
    """Capture rental_analysis thin-market behaviour."""
    from app.mcp.server import rental_analysis

    sig = inspect.signature(rental_analysis)
    has_auto_escalate = "auto_escalate" in sig.parameters

    test_cases: list[dict[str, Any]] = [
        {"postcode": "NG1 2NS", "label": "thin-postcode"},
        {"postcode": "DE12 7DH", "label": "dense-postcode"},
        {"postcode": "NG11 9HD", "label": "ng11-postcode"},
    ]
    results = []
    for case in test_cases:
        label = case.pop("label")
        try:
            result = await rental_analysis(**case)
        except Exception as exc:
            results.append({"case": label, "params": case, "error": str(exc)})
            continue
        body = json.dumps(result, ensure_ascii=False)
        results.append({
            "case": label,
            "params": case,
            "tokens": _tok(body),
            # NOTE: RentalAnalysis uses "median_rent_monthly" and "rental_listings_count".
            # YieldAnalysis uses "median_monthly_rent" and "rental_count". Same concept,
            # different names — historical drift between the two models.
            "median_rent_monthly": result.get("median_rent_monthly"),
            "average_rent_monthly": result.get("average_rent_monthly"),
            "rental_listings_count": result.get("rental_listings_count"),
            "rent_range_low": result.get("rent_range_low"),
            "rent_range_high": result.get("rent_range_high"),
            "escalated_from": result.get("escalated_from"),
            "escalated_to": result.get("escalated_to"),
            "thin_market": result.get("thin_market"),
        })
    return {
        "tool": "rental_analysis (plain MCP)",
        "signature_has_auto_escalate": has_auto_escalate,
        "cases": results,
    }


def measure_tool_inventory() -> dict:
    """Compare which @mcp.tool() decorators are registered on each server."""
    plain_tools = _list_mcp_tools_from_module("app.mcp.server")
    mcp_app_tools = _list_mcp_tools_from_module("property_app.server", import_dashboards=True)

    plain_set = set(plain_tools)
    app_set = set(mcp_app_tools)

    return {
        "plain_mcp_tools": sorted(plain_tools),
        "mcp_app_tools": sorted(mcp_app_tools),
        "only_in_plain": sorted(plain_set - app_set),
        "only_in_mcp_app": sorted(app_set - plain_set),
        "in_both": sorted(plain_set & app_set),
    }


def _list_mcp_tools_from_module(module_name: str, import_dashboards: bool = False) -> list[str]:
    """Grep MCP tool decorators in the source files (most reliable across FastMCP versions)."""
    import re
    import importlib

    if module_name == "app.mcp.server":
        sources = ["app/mcp/server.py"]
    elif module_name == "property_app.server":
        sources = [
            "property_app/tools.py",
            "property_app/dashboards/comps.py",
            "property_app/dashboards/yield_view.py",
            "property_app/dashboards/rental.py",
            "property_app/dashboards/listings.py",
            "property_app/dashboards/unified.py",
        ]
    else:
        return []

    # Match @mcp.tool(...) followed by optional extra decorators, then def/async def.
    # The decorator args may span multiple lines.
    pattern = re.compile(
        r"@mcp\.tool\([^)]*(?:\([^)]*\)[^)]*)*\)\s*\n"
        r"(?:\s*@[^\n]+\n)*"
        r"\s*(?:async\s+)?def\s+(\w+)\s*\(",
    )
    tools = []
    for src in sources:
        path = Path(src)
        if not path.exists():
            continue
        text = path.read_text()
        for name in pattern.findall(text):
            if not name.startswith("_"):
                tools.append(name)
    return tools


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    print(f"\n{'='*70}\n  MCP Quality Snapshot  —  label={args.label}\n{'='*70}\n")

    print("== Tool inventory ==")
    inventory = measure_tool_inventory()
    print(f"  Plain MCP tools ({len(inventory['plain_mcp_tools'])}): {inventory['plain_mcp_tools']}")
    print(f"  MCP App tools  ({len(inventory['mcp_app_tools'])}): {inventory['mcp_app_tools']}")
    print(f"  Only in plain MCP: {inventory['only_in_plain']}")
    print(f"  Only in MCP App:   {inventory['only_in_mcp_app']}")
    print()

    print("== property_comps token cost ==")
    comps = await measure_property_comps()
    for case in comps["cases"]:
        if "error" in case:
            print(f"  {case['case']}: ERROR {case['error']}")
            continue
        print(f"  {case['case']:35s}  n={case['txn_count']:>3}  tokens={case['tokens']:>5,}  "
              f"per_txn={case['tokens_per_txn']:>4}  nulls={case['null_ratio_pct']:>5}%  "
              f"median=£{case['median'] or 0:,}")
    print()

    print("== property_yield ==")
    py = await measure_property_yield()
    print(f"  auto_escalate param: {py['signature_has_auto_escalate']}")
    print(f"  docstring ({py['docstring_length_chars']} chars):")
    for line in py["docstring"].splitlines()[:6]:
        print(f"    {line}")
    for case in py["cases"]:
        if "error" in case:
            print(f"  {case['case']}: ERROR {case['error']}")
            continue
        print(f"  {case['case']:18s}  yield={case['gross_yield_pct']}%  "
              f"price=£{case['median_sale_price'] or 0:,}  rent=£{case['median_monthly_rent'] or 0:,}  "
              f"thin_handled={case['thin_market_handled']}")
    print()

    print("== rental_analysis ==")
    rental = await measure_rental_analysis()
    print(f"  auto_escalate param: {rental['signature_has_auto_escalate']}")
    for case in rental["cases"]:
        if "error" in case:
            print(f"  {case['case']}: ERROR {case['error']}")
            continue
        print(f"  {case['case']:18s}  median_rent=£{case['median_rent_monthly'] or 0:,}/mo  "
              f"n={case['rental_listings_count']}  "
              f"range=£{case['rent_range_low'] or 0:,}–£{case['rent_range_high'] or 0:,}  "
              f"escalated={case['escalated_from']}→{case['escalated_to']}  "
              f"thin={case['thin_market']}")
    print()

    summary = {
        "label": args.label,
        "timestamp": datetime.now().isoformat(),
        "inventory": inventory,
        "property_comps": comps,
        "property_yield": py,
        "rental_analysis": rental,
    }

    out_path = Path(f"/tmp/mcp_quality_{args.label}.json")
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nWrote: {out_path}\n")


if __name__ == "__main__":
    asyncio.run(main())
