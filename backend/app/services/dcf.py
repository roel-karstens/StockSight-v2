"""
dcf.py — DCF valuation, reverse DCF, and quality scoring service.

All functions take plain Python types (floats, dicts, lists) rather than
DataFrames — designed for use from FastAPI routes.

Ported from StockSight's data/metrics.py (DCF, reverse DCF, quality scoring).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger


# ---------------------------------------------------------------------------
# Data classes for typed inputs/outputs
# ---------------------------------------------------------------------------


@dataclass
class DCFInput:
    """User-adjustable DCF assumptions."""

    wacc: float = 0.10
    terminal_growth: float = 0.03
    fcf_growth_years_1_5: float = 0.15
    fcf_growth_years_6_10: float = 0.08
    years: int = 10


@dataclass
class DCFOutput:
    """Result of a DCF calculation."""

    intrinsic_value_per_share: float = 0.0
    current_price: float | None = None
    margin_of_safety: float | None = None  # percent, positive = undervalued
    projected_fcfs: list[dict] = field(default_factory=list)  # [{year, fcf, pv, growth_rate}]
    terminal_value: float = 0.0  # PV of terminal value
    total_pv: float = 0.0


@dataclass
class ReverseDCFOutput:
    """Result of a reverse DCF calculation."""

    implied_growth_rate: float = 0.0
    current_price: float = 0.0
    wacc: float = 0.0
    sensitivity: list[dict] = field(default_factory=list)  # [{growth_rate, implied_price}]


# ---------------------------------------------------------------------------
# DCF Model — 2-stage
# ---------------------------------------------------------------------------


def calculate_dcf(
    base_fcf: float,
    shares_outstanding: float,
    current_price: float | None,
    inputs: DCFInput,
) -> DCFOutput:
    """Calculate DCF intrinsic value using a 2-stage model.

    Stage 1 (years 1–5): grow FCF at fcf_growth_years_1_5.
    Stage 2 (years 6–10): grow FCF at fcf_growth_years_6_10.
    Terminal value: Gordon Growth Model.

    Ported from data/metrics.py dcf_margin_of_safety + _dcf_intrinsic_per_share.

    Parameters
    ----------
    base_fcf : float
        Most recent fiscal year's free cash flow (absolute, not per-share).
    shares_outstanding : float
        Diluted shares outstanding.
    current_price : float | None
        Current market price per share. None if unknown.
    inputs : DCFInput
        User-adjustable DCF assumptions.

    Returns
    -------
    DCFOutput
    """
    wacc = inputs.wacc
    terminal_growth = inputs.terminal_growth
    years = inputs.years

    projected_fcfs: list[dict] = []
    fcf = base_fcf
    total_yearly_pv = 0.0

    for yr in range(1, years + 1):
        # Determine growth rate for this year
        if yr <= 5:
            growth_rate = inputs.fcf_growth_years_1_5
        else:
            growth_rate = inputs.fcf_growth_years_6_10

        fcf = fcf * (1 + growth_rate)
        pv = fcf / (1 + wacc) ** yr
        total_yearly_pv += pv

        projected_fcfs.append(
            {
                "year": yr,
                "fcf": round(fcf, 2),
                "pv": round(pv, 2),
                "growth_rate": growth_rate,
            }
        )

    # Terminal value (Gordon Growth Model)
    terminal_fcf = fcf * (1 + terminal_growth)
    terminal_value = terminal_fcf / (wacc - terminal_growth)
    terminal_pv = terminal_value / (1 + wacc) ** years

    total_pv = total_yearly_pv + terminal_pv
    intrinsic_value = total_pv / shares_outstanding

    margin_of_safety = None
    if current_price is not None and current_price > 0:
        margin_of_safety = (intrinsic_value - current_price) / current_price * 100

    return DCFOutput(
        intrinsic_value_per_share=round(intrinsic_value, 2),
        current_price=current_price,
        margin_of_safety=round(margin_of_safety, 2) if margin_of_safety is not None else None,
        projected_fcfs=projected_fcfs,
        terminal_value=round(terminal_pv, 2),
        total_pv=round(total_pv, 2),
    )


# ---------------------------------------------------------------------------
# Reverse DCF — Implied Growth Rate
# ---------------------------------------------------------------------------


def calculate_reverse_dcf(
    current_price: float,
    shares_outstanding: float,
    base_fcf: float,
    wacc: float = 0.10,
    terminal_growth: float = 0.03,
    years: int = 10,
) -> ReverseDCFOutput:
    """Find the implied FCF growth rate priced into the market.

    Uses binary search over growth rate range [-0.30, 1.00].

    Ported from data/metrics.py _solve_implied_growth.

    Parameters
    ----------
    current_price : float
        Current market price per share.
    shares_outstanding : float
        Diluted shares outstanding.
    base_fcf : float
        Most recent fiscal year's free cash flow.
    wacc : float
        Weighted average cost of capital.
    terminal_growth : float
        Terminal perpetual growth rate.
    years : int
        Number of projection years.

    Returns
    -------
    ReverseDCFOutput
    """
    target = current_price * shares_outstanding  # market cap

    def _dcf_value(growth_rate: float) -> float:
        """Compute total DCF enterprise value for a single growth rate."""
        fcf = base_fcf
        total = 0.0
        for yr in range(1, years + 1):
            fcf = fcf * (1 + growth_rate)
            total += fcf / (1 + wacc) ** yr
        # Terminal value
        tv_fcf = fcf * (1 + terminal_growth)
        tv = tv_fcf / (wacc - terminal_growth)
        tv_pv = tv / (1 + wacc) ** years
        return total + tv_pv

    # Binary search for implied growth rate
    lo, hi = -0.30, 1.00
    implied_growth = 0.0

    for _ in range(100):
        mid = (lo + hi) / 2
        try:
            val = _dcf_value(mid)
        except (ZeroDivisionError, OverflowError):
            lo = mid
            continue
        if abs(val - target) < 1e4:
            implied_growth = mid
            break
        if val < target:
            lo = mid
        else:
            hi = mid
        implied_growth = mid

    # Sensitivity table
    sensitivity_rates = [-0.05, 0.0, 0.05, 0.10, 0.15, 0.18, 0.20, 0.25, 0.30]
    sensitivity: list[dict] = []
    for rate in sensitivity_rates:
        try:
            total_ev = _dcf_value(rate)
            implied_price = total_ev / shares_outstanding
            sensitivity.append(
                {
                    "growth_rate": rate,
                    "implied_price": round(implied_price, 2),
                }
            )
        except (ZeroDivisionError, OverflowError):
            continue

    return ReverseDCFOutput(
        implied_growth_rate=round(implied_growth, 4),
        current_price=current_price,
        wacc=wacc,
        sensitivity=sensitivity,
    )


# ---------------------------------------------------------------------------
# Quality Criteria Scoring
# ---------------------------------------------------------------------------


# Quality thresholds — these map directly to the frontend lib/quality.js CRITERIA
QUALITY_CRITERIA = [
    {"key": "roce", "threshold": 10, "direction": "above"},
    {"key": "revenue_growth", "threshold": 0.10, "direction": "above"},
    {"key": "fcf_growth", "threshold": 0.10, "direction": "above"},
    {"key": "eps_growth", "threshold": 0.10, "direction": "above"},
    {"key": "lt_debt_to_fcf", "threshold": 4, "direction": "below"},
    {"key": "peg_ratio", "threshold": 2, "direction": "below"},
]


def compute_quality_criteria(
    fundamentals: list[dict],
    window: int = 10,
) -> dict:
    """Compute quality criteria pass/fail/score from fundamentals data.

    Takes the last `window` years, computes average of each metric,
    then checks against thresholds.

    Ported from StockSight's ui/indicators.py threshold logic.

    Parameters
    ----------
    fundamentals : list[dict]
        List of annual fundamental dicts, sorted by fiscal_year ascending.
        Each dict must have keys matching QUALITY_CRITERIA keys.
    window : int
        Number of recent years to average over (3 or 10).

    Returns
    -------
    dict with keys: roce_ok, revenue_growth_ok, fcf_growth_ok, eps_growth_ok,
         lt_debt_fcf_ok, peg_ok, score (0-6), plus the avg values.
    """
    # Take the last `window` years
    recent = fundamentals[-window:] if len(fundamentals) > window else fundamentals

    result: dict[str, Any] = {}
    score = 0

    for criterion in QUALITY_CRITERIA:
        key = criterion["key"]
        threshold = criterion["threshold"]
        direction = criterion["direction"]

        # Collect non-None values for this metric
        values = [
            r[key] for r in recent
            if r.get(key) is not None
        ]

        if values:
            avg = sum(values) / len(values)
        else:
            avg = None

        # Store the average value
        result[f"{key}_avg"] = round(avg, 4) if avg is not None else None

        # Check pass/fail
        if avg is not None:
            if direction == "above":
                passed = avg > threshold
            else:  # below
                passed = avg < threshold
        else:
            passed = False

        ok_key = key + "_ok"
        # Special case: lt_debt_to_fcf → lt_debt_fcf_ok
        if key == "lt_debt_to_fcf":
            ok_key = "lt_debt_fcf_ok"
        else:
            ok_key = key + "_ok"

        result[ok_key] = passed
        if passed:
            score += 1

    result["score"] = score
    return result
