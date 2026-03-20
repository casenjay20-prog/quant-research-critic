from typing import Dict


# --- Grade → Decision (static, explainable) ---
GRADE_TO_DECISION = {
    "A+": "Proceed",
    "A":  "Proceed",
    "A-": "Proceed",
    "B+": "Proceed",
    "B":  "Proceed with Caution",
    "B-": "Proceed with Caution",
    "C":  "Proceed with Caution",
    "D":  "Do Not Deploy",
    "F":  "Do Not Deploy",
}


def build_verdict(payload: Dict) -> Dict:
    """
    Deterministic verdict builder for Page 1.
    Consumes ONLY the analysis payload. No new math.
    """

    scorecard = payload.get("scorecard", {})
    normalized = payload.get("normalized", {})
    flags = payload.get("flags", [])

    grade = scorecard.get("grade", "F")
    decision = GRADE_TO_DECISION.get(grade, "Do Not Deploy")

    # --- Primary signals (already computed upstream) ---
    sharpe_adj = float(normalized.get("sharpe_adj") or 0.0)
    max_dd = abs(float(payload.get("max_drawdown") or 0.0))
    confidence = float(normalized.get("score_confidence") or 0.0)

    # --- Strength / risk descriptors (rule-based) ---
    # Strength
    if sharpe_adj >= 1.5 and confidence >= 0.75:
        strength = "strong risk-adjusted returns"
    elif sharpe_adj >= 1.0:
        strength = "moderate risk-adjusted returns"
    else:
        strength = "weak risk-adjusted returns"

    # Risk
    if max_dd >= 0.30:
        risk = "material drawdown risk"
    elif max_dd >= 0.20:
        risk = "elevated drawdown risk"
    else:
        risk = "contained drawdown risk"

    # Flag influence (escalates risk wording, never softens)
    if flags:
        risk = "multiple structural risk signals"

    # --- Final one-sentence verdict (no hedging) ---
    sentence = f"{strength.capitalize()} with {risk}."

    return {
        "grade": grade,
        "decision": decision,
        "sentence": sentence,
    }
