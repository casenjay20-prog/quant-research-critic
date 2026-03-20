# backend/app/services/reporting/page1/allocator.py
from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_capital_allocation_lens(
    payload: Dict[str, Any],
    key_metrics: List[Dict[str, Any]],
    top_flags: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Existing lens builder (leave as-is).
    Returns allocator-facing guidance like allocation_band.
    """
    scorecard = payload.get("scorecard", {}) or {}
    score = float(scorecard.get("score", 0.0) or 0.0)

    years = float(payload.get("years", 0.0) or 0.0)
    rows = int(payload.get("rows", 0) or 0)

    # Default bands (simple, tweak later)
    if rows < 50 or years < 0.5:
        band = "0–2% of risk budget (validate stability)"
    elif score >= 80:
        band = "5–10% of risk budget (subject to DD + correlation)"
    elif score >= 60:
        band = "2–5% of risk budget (monitor stability)"
    else:
        band = "0–2% of risk budget (research / improve robustness)"

    return {
        "allocation_band": band,
        "score": score,
    }


def recommend_deployment_sizing(
    *,
    deployability_score: float,
    fragility_index: Optional[float],
    confidence: Optional[float],
    years: float,
    rows: int,
) -> Dict[str, Any]:
    """
    Tier 2 deterministic sizing guidance.

    This is what your Tier 2 PDF should render.
    Keep keys stable across API + PDF:
      - suggested_band: str
      - max_risk_pct: float
      - gating_conditions: List[str]
      - rationale: str
    """
    # normalize inputs safely
    fi: Optional[float]
    try:
        fi = float(fragility_index) if fragility_index is not None else None
    except Exception:
        fi = None

    conf: Optional[float]
    try:
        conf = float(confidence) if confidence is not None else None
    except Exception:
        conf = None

    s = float(deployability_score)

    gating: List[str] = []
    # These are “hard brakes” that should show up in the PDF
    if rows < 50:
        gating.append("needs ≥50 rows")
    if years < 0.5:
        gating.append("needs ≥0.5 years")
    if conf is not None and conf < 0.35:
        gating.append("confidence must be ≥0.35")

    # default recommendation (conservative)
    suggested_band = "Research only"
    max_risk_pct = 0.25
    rationale = "Fails deployability screen; do not allocate beyond minimal pilot sizing."

    # --- hard safety brakes (override everything) ---
    if rows < 50 or years < 0.5:
        return {
            "suggested_band": "Pilot only",
            "max_risk_pct": 0.25,
            "gating_conditions": gating[:3],
            "rationale": "Insufficient history/sample for institutional sizing; run as pilot/research until history improves.",
        }

    if fi is not None and fi >= 67:
        return {
            "suggested_band": "Pilot only",
            "max_risk_pct": 0.50,
            "gating_conditions": gating[:3],
            "rationale": "High fragility index indicates unstable backtest; cap sizing tightly until robustness improves.",
        }

    if conf is not None and conf < 0.35:
        return {
            "suggested_band": "Pilot only",
            "max_risk_pct": 0.50,
            "gating_conditions": gating[:3],
            "rationale": "Low confidence/stability signal; cap sizing pending validation.",
        }

    # --- scaled sizing by deployability + fragility ---
    if s >= 75 and (fi is None or fi < 34):
        suggested_band = "Core"
        max_risk_pct = 3.0
        rationale = "High deployability with low fragility; eligible for core sizing subject to correlation + DD constraints."
    elif s >= 60:
        suggested_band = "Scaled"
        max_risk_pct = 2.0
        rationale = "Deployable but not top-tier; size moderately and monitor stability + regime sensitivity."
        # if fragility is medium, clip slightly
        if fi is not None and fi >= 34:
            suggested_band = "Scaled (conservative)"
            max_risk_pct = 1.0
            rationale = "Deployable but fragility is elevated; size conservatively and require validation."
    elif s >= 30:
        suggested_band = "Watchlist"
        max_risk_pct = 1.0
        rationale = "Borderline deployability; allow small allocation only with strict monitoring."
    else:
        suggested_band = "Research only"
        max_risk_pct = 0.25
        rationale = "Fails deployability screen; do not allocate beyond minimal pilot sizing."

    return {
        "suggested_band": suggested_band,
        "max_risk_pct": float(max_risk_pct),
        "gating_conditions": gating[:3],
        "rationale": rationale,
    }