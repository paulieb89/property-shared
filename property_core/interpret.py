"""Optional interpretation helpers for property_core data.

These functions classify raw numbers into human-readable labels.
They are NOT called automatically by any property_core service —
consumers (API, CLI, MCP) opt in by calling them explicitly.

A data library returns numbers; these helpers interpret them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from property_core.models.report import PropertyReport


def classify_yield(
    gross_yield_pct: float,
    *,
    strong_pct: float = 6.0,
    average_pct: float = 4.0,
) -> str:
    """Classify gross yield percentage.

    Args:
        gross_yield_pct: The yield percentage to classify.
        strong_pct: Yield >= this is "strong" (default 6.0).
        average_pct: Yield >= this is "average" (default 4.0).

    Returns:
        "strong", "average", or "weak".
    """
    if gross_yield_pct >= strong_pct:
        return "strong"
    if gross_yield_pct >= average_pct:
        return "average"
    return "weak"


def classify_data_quality(
    sale_count: int,
    rental_count: int,
    *,
    min_good: int = 5,
) -> str:
    """Classify data quality based on sample sizes.

    Args:
        sale_count: Number of comparable sales.
        rental_count: Number of rental listings.
        min_good: Minimum of each for "good" quality (default 5).

    Returns:
        "good", "low", or "insufficient".
    """
    if sale_count >= min_good and rental_count >= min_good:
        return "good"
    if sale_count >= 2 and rental_count >= 2:
        return "low"
    return "insufficient"


def classify_price_position(
    diff_pct: float,
    *,
    threshold_pct: float = 5.0,
) -> str:
    """Classify a property's price position relative to the area median.

    Args:
        diff_pct: Percentage difference from median (positive = above).
        threshold_pct: Minimum difference to classify as above/below (default 5.0).

    Returns:
        "above", "below", or "at".
    """
    if diff_pct > threshold_pct:
        return "above"
    if diff_pct < -threshold_pct:
        return "below"
    return "at"


def estimate_value_range(
    median_price: int,
    *,
    range_pct: float = 15.0,
) -> tuple[int, int]:
    """Estimate a value range as median ± range_pct%.

    Args:
        median_price: Area median sale price.
        range_pct: Percentage band around median (default 15.0).

    Returns:
        (low, high) tuple of estimated values.
    """
    low_factor = 1 - (range_pct / 100)
    high_factor = 1 + (range_pct / 100)
    return int(median_price * low_factor), int(median_price * high_factor)


def generate_insights(report: PropertyReport) -> list[str]:
    """Generate key insight strings from a PropertyReport's structured data.

    Builds human-readable summary lines from the report's data fields.
    This is a presentation convenience — all data is already in the model.

    Args:
        report: A PropertyReport with populated data sections.

    Returns:
        List of insight strings.
    """
    insights: list[str] = []

    if report.sale_history and report.sale_history.last_sale:
        last = report.sale_history.last_sale
        insights.append(f"Last sold for \u00a3{last.price:,} on {last.date}")

    if report.energy_performance:
        ep = report.energy_performance
        insights.append(f"Energy rating: {ep.rating} (score {ep.score})")

    if report.rental_analysis and report.rental_analysis.gross_yield_pct:
        insights.append(
            f"Estimated gross yield: {report.rental_analysis.gross_yield_pct:.1f}%"
        )

    if report.market_analysis and report.market_analysis.median_price:
        ma = report.market_analysis
        insights.append(
            f"Area median: \u00a3{ma.median_price:,} "
            f"(range \u00a3{ma.min_price:,} - \u00a3{ma.max_price:,})"
        )

    return insights
