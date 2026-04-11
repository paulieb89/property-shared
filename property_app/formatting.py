"""Shared formatting helpers for Prefab views."""
from __future__ import annotations


def fmt_gbp(n: int | float | None) -> str:
    if n is None:
        return "\u2014"
    return f"\u00a3{int(n):,}"


def fmt_pct(n: float | None, decimals: int = 1) -> str:
    if n is None:
        return "\u2014"
    return f"{n:.{decimals}f}%"


def fmt_date(d: str | None) -> str:
    if not d:
        return "\u2014"
    parts = d.split("T")[0].split("-")
    if len(parts) == 3:
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    return d
