# paste the full constraints.py content here# backend/app/services/constraints.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np


def _fees_breakeven_bps_from_returns(
    returns: np.ndarray,
    *,
    target_sharpe: float = 1.0,
    freq_per_year: int = 252,
) -> Optional[float]:
    """
    Rough estimate: annual bps of drag (fees+slippage) that would push Sharpe down to target_sharpe.
    If already below target, returns 0.
    """
    r = np.asarray(returns, dtype=float)
    if r.size < 10:
        return None

    mu = float(np.mean(r))
    sd = float(np.std(r, ddof=1)) if r.size > 1 else 0.0
    if sd <= 0:
        return None

    # sharpe = (mu - drag_per_period)/sd * sqrt(freq)
    drag_per_period = mu - (target_sharpe * sd / np.sqrt(freq_per_year))
    # If drag_per_period is negative, it means even with *negative* drag you can't hit target → already below.
    if drag_per_period <= 0:
        return 0.0

    annual_drag = drag_per_period * freq_per_year  # in return units
    bps = annual_drag * 10000.0
    return float(max(0.0, bps))


def compute_deployability_constraints(
    *,
    payload: Dict[str, Any],
    returns: np.ndarray,
) -> Dict[str, Any]:
    """
    Capacity + implementation sanity checks (heuristic / conservative).
    """
    rows = int(payload.get("rows", 0) or 0)
    years = float(payload.get("years", 0.0) or 0.0)

    checklist: List[str] = [
        "Confirm strategy turnover and holding period (capacity depends on it).",
        "Estimate trading cost model (fees + slippage) and re-run metrics net of costs.",
        "Validate live execution constraints (locates, borrow, venue access, lot sizes).",
        "Check correlation overlap versus existing book (true diversification).",
    ]

    capacity_badge = "Unknown (needs strategy metadata)"
    if rows < 252 or years < 1.0:
        capacity_badge = "Unknown (insufficient history)"

    breakeven_bps = _fees_breakeven_bps_from_returns(returns, target_sharpe=1.0)

    return {
        "capacity_badge": capacity_badge,
        "checklist": checklist,
        "fees_slippage_breakeven_bps_per_year": breakeven_bps,
        "notes": "Capacity cannot be inferred reliably from returns alone; treat as required diligence item.",
    }