# backend/app/services/fragility.py
from __future__ import annotations

from typing import Any, Dict, Tuple, Optional
import numpy as np


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    try:
        v = float(x)
    except Exception:
        return lo
    return max(lo, min(hi, v))


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _rolling_sharpe_instability(r: np.ndarray, window: int = 63, freq: int = 252) -> float:
    """
    Deterministic proxy for regime sensitivity:
    compute rolling Sharpe, then measure dispersion and sign flips.
    Returns a 0..100 score (higher = more unstable).
    """
    if r is None or r.size < max(window + 5, 30):
        return 65.0  # not enough data -> assume unstable

    x = r.astype(float)
    n = x.size
    if n < window:
        return 65.0

    # rolling mean/std
    means = []
    sharpes = []
    for i in range(window, n + 1):
        seg = x[i - window : i]
        mu = float(np.mean(seg))
        sd = float(np.std(seg, ddof=1)) if seg.size > 1 else 0.0
        s = float((mu / sd) * np.sqrt(freq)) if sd > 0 else 0.0
        sharpes.append(s)

    if not sharpes:
        return 65.0

    arr = np.array(sharpes, dtype=float)
    disp = float(np.std(arr, ddof=1)) if arr.size > 1 else 0.0

    # sign flip rate
    signs = np.sign(arr)
    flips = 0
    for i in range(1, signs.size):
        if signs[i] != 0 and signs[i - 1] != 0 and signs[i] != signs[i - 1]:
            flips += 1
    flip_rate = flips / max(1, (signs.size - 1))

    # map dispersion + flips into 0..100
    # these cutoffs are heuristic, deterministic, and easy to tune later
    disp_score = _clamp((disp / 1.5) * 60.0)  # std 1.5 -> ~60
    flip_score = _clamp(flip_rate * 100.0)    # 0..100

    return _clamp(0.65 * disp_score + 0.35 * flip_score)


def _tail_risk_score(payload: Dict[str, Any]) -> float:
    """
    Deterministic tail fragility proxy: max drawdown + volatility interaction.
    """
    mdd = _safe_float(payload.get("max_drawdown"))
    vol = _safe_float(payload.get("volatility"))

    if mdd is None and vol is None:
        return 50.0

    # mdd is negative typically; convert magnitude
    mdd_mag = abs(mdd) if mdd is not None else 0.0
    vol_mag = abs(vol) if vol is not None else 0.0

    # map to 0..100
    # mdd 30% -> 60, 50% -> 100
    mdd_score = _clamp((mdd_mag / 0.30) * 60.0)
    if mdd_mag >= 0.50:
        mdd_score = 100.0

    # vol 30% -> 50, 60% -> 90
    vol_score = _clamp((vol_mag / 0.30) * 50.0)
    if vol_mag >= 0.60:
        vol_score = 90.0

    return _clamp(0.7 * mdd_score + 0.3 * vol_score)


def _sample_stability_score(payload: Dict[str, Any]) -> float:
    """
    Deterministic stability penalty driven by sample length, history, and confidence.
    Higher = more fragile.
    """
    rows = int(payload.get("rows", 0) or 0)
    years = float(payload.get("years", 0.0) or 0.0)

    conf = None
    try:
        conf = float((payload.get("scorecard", {}) or {}).get("confidence"))
    except Exception:
        conf = None

    score = 0.0
    # rows: <50 very fragile, 50-252 moderate, >=252 less fragile
    if rows <= 0:
        score += 60.0
    elif rows < 50:
        score += 80.0
    elif rows < 252:
        score += 55.0
    else:
        score += 25.0

    # years: <0.5 fragile, 0.5-2 moderate
    if years <= 0:
        score += 60.0
    elif years < 0.5:
        score += 80.0
    elif years < 2.0:
        score += 45.0
    else:
        score += 20.0

    # confidence: <0.35 fragile
    if conf is None:
        score += 30.0
    elif conf < 0.35:
        score += 70.0
    elif conf < 0.55:
        score += 45.0
    else:
        score += 20.0

    return _clamp(score / 3.0)


def compute_fragility(returns: np.ndarray, payload: Dict[str, Any]) -> Tuple[float, Dict[str, float]]:
    """
    Returns:
      fragility_index (0..100; higher = more fragile)
      fragility_breakdown (component scores 0..100)
    """
    sample = _sample_stability_score(payload)
    regime = _rolling_sharpe_instability(returns)
    tails = _tail_risk_score(payload)

    # Weighted total (tunable later)
    fragility = _clamp(0.40 * sample + 0.35 * regime + 0.25 * tails)

    breakdown = {
        "sample_stability": float(sample),
        "regime_sensitivity": float(regime),
        "tail_risk": float(tails),
        "fragility_index": float(fragility),
    }
    return float(fragility), breakdown