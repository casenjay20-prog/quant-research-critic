from __future__ import annotations

import numpy as np
import pandas as pd


def load_returns_from_upload(file) -> tuple[np.ndarray, pd.DataFrame]:
    """
    Accepts FastAPI UploadFile (or anything with .file) and returns:
      - returns: np.ndarray (float)
      - df: the raw dataframe (so routes.py can optionally use it)
    """
    df = pd.read_csv(file.file)

    if "returns" not in df.columns:
        raise ValueError("CSV must contain a 'returns' column")

    # Clean + coerce
    returns = pd.to_numeric(df["returns"], errors="coerce").dropna().to_numpy(dtype=float)

    if returns.size == 0:
        raise ValueError("No valid numeric values found in 'returns' column")

    return returns, df


def confidence_from_years(years: float, y_min: float = 0.5, y_full: float = 5.0) -> float:
    if years <= 0:
        return 0.0

    x = max(0.0, min(years, y_full))

    if x <= y_min:
        return 0.15 * (x / y_min)

    t = (x - y_min) / (y_full - y_min)
    return 0.15 + 0.85 * (3 * t * t - 2 * t * t * t)


def stability_factor_from_rolling_sharpe(
    returns: np.ndarray,
    freq_per_year: int,
    window: int = 63
) -> float:
    r = np.asarray(returns, dtype=float)

    if r.size < window * 2:
        return 0.75

    roll_means = np.convolve(r, np.ones(window) / window, mode="valid")
    roll_stds = np.array([
        np.std(r[i:i + window], ddof=1)
        for i in range(0, r.size - window + 1)
    ])

    eps = 1e-12
    roll_sharpes = (roll_means / (roll_stds + eps)) * np.sqrt(freq_per_year)

    s = np.std(roll_sharpes)

    if s <= 0.5:
        return 1.0
    if s >= 2.0:
        return 0.4

    return 1.0 - (s - 0.5) * (0.6 / (2.0 - 0.5))


def normalized_metrics(
    returns: np.ndarray,
    freq_per_year: int,
    cagr: float,
    sharpe: float
) -> dict:
    r = np.asarray(returns, dtype=float)
    n = int(r.size)
    years = n / float(freq_per_year) if freq_per_year else 0.0

    length_conf = confidence_from_years(years)
    stability = stability_factor_from_rolling_sharpe(r, freq_per_year)

    score_confidence = 0.7 * length_conf + 0.3 * stability
    score_confidence = max(0.0, min(1.0, score_confidence))

    sharpe_adj = sharpe * score_confidence if sharpe is not None else None
    cagr_adj = cagr * score_confidence if cagr is not None else None

    notes = []
    if years < 1.0:
        notes.append("Short sample (<1 year): normalized metrics heavily penalized.")
    if n < 100:
        notes.append("Low observation count: results may be noisy.")
    if score_confidence < 0.6:
        notes.append("Low confidence due to limited history and/or unstable performance.")

    return {
        "n": n,
        "years": round(years, 4),
        "confidence_length": round(length_conf, 4),
        "confidence_stability": round(stability, 4),
        "score_confidence": round(score_confidence, 4),
        "sharpe_adj": None if sharpe_adj is None else round(sharpe_adj, 4),
        "cagr_adj": None if cagr_adj is None else round(cagr_adj, 4),
        # benchmark-relative normalized signal (routes.py can overwrite)
        "relative_strength": 0.0,
        "notes": notes,
    }


def critic_score(normalized: dict, max_drawdown: float) -> dict:
    """
    Returns a 0–100 score and A–F grade using normalized metrics.
    """
    score = 0.0

    sharpe_adj = float(normalized.get("sharpe_adj") or 0.0)
    cagr_adj = float(normalized.get("cagr_adj") or 0.0)
    confidence = float(normalized.get("score_confidence", 0.0) or 0.0)

    # Sharpe contribution (max ~40)
    score += max(0.0, min(sharpe_adj, 2.0)) / 2.0 * 40.0

    # CAGR contribution (max ~30)
    score += max(0.0, min(cagr_adj, 0.30)) / 0.30 * 30.0

    # Drawdown penalty (up to -20)
    dd_penalty = min(abs(float(max_drawdown)), 0.40) / 0.40 * 20.0
    score -= dd_penalty

    # Confidence scaling
    score *= confidence

    # Benchmark-relative contribution (max about ±10)
    relative_strength = float(normalized.get("relative_strength", 0.0) or 0.0)
    relative_strength = max(-1.0, min(1.0, relative_strength))
    score += 10.0 * relative_strength

    score = max(0.0, min(100.0, score))

    if score >= 90:
        grade = "A"
    elif score >= 80:
        grade = "B"
    elif score >= 70:
        grade = "C"
    elif score >= 60:
        grade = "D"
    else:
        grade = "F"

    return {
        "score": round(score, 1),
        "grade": grade,
        "confidence": round(confidence, 2),
    }


def red_flags(rows: int, years: float, sharpe: float, max_drawdown: float, normalized: dict) -> list[str]:
    flags: list[str] = []

    if rows < 50:
        flags.append("Tiny sample size (<50 rows): metrics are extremely unstable.")
    elif rows < 252:
        flags.append("Short sample (<1 trading year): results may not generalize.")

    if years < 0.5:
        flags.append("Less than ~6 months of data: Sharpe/CAGR can be very misleading.")

    conf = float(normalized.get("score_confidence", 0.0) or 0.0)
    if conf < 0.6:
        flags.append("Low confidence: normalized metrics heavily penalized due to limited history/instability.")

    rel = normalized.get("relative_strength", None)
    if rel is not None:
        rel_f = float(rel or 0.0)
        if rel_f <= -0.33:
            flags.append("Underperformed benchmark materially (negative relative strength).")

    dd = abs(float(max_drawdown))
    if dd >= 0.30:
        flags.append("High max drawdown (>=30%): strategy may be hard to hold through.")
    elif dd >= 0.20:
        flags.append("Moderate max drawdown (>=20%): risk may be high relative to returns.")

    if years < 1.0 and sharpe >= 2.0:
        flags.append("Very high Sharpe on short history: possible overfitting or regime luck.")
    if sharpe < 0:
        flags.append("Negative Sharpe: returns not compensating for risk.")

    return flags
