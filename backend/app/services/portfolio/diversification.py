from typing import Dict, Any
import numpy as np


def score_strategy_addition(
    current_report: Dict[str, Any],
    candidate_report: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Compare a current portfolio report vs a portfolio report that includes
    a candidate strategy, and determine whether diversification improved.

    Inputs
    ------
    current_report : output of build_portfolio_report() for current portfolio
    candidate_report : output of build_portfolio_report() for portfolio + new strategy

    Output
    ------
    {
        "current_diversification_score": float,
        "candidate_diversification_score": float,
        "diversification_delta": float,
        "current_average_correlation": float,
        "candidate_average_correlation": float,
        "correlation_delta": float,
        "current_overlap_risk": str,
        "candidate_overlap_risk": str,
        "decision": str,
        "summary": str,
    }
    """

    current_corr = (current_report.get("correlation", {}) or {})
    candidate_corr = (candidate_report.get("correlation", {}) or {})

    current_overlap = (current_report.get("overlap", {}) or {})
    candidate_overlap = (candidate_report.get("overlap", {}) or {})

    current_div = float(current_corr.get("diversification_score", 0.0) or 0.0)
    candidate_div = float(candidate_corr.get("diversification_score", 0.0) or 0.0)
    div_delta = candidate_div - current_div

    current_avg_corr = float(current_corr.get("average_correlation", 0.0) or 0.0)
    candidate_avg_corr = float(candidate_corr.get("average_correlation", 0.0) or 0.0)
    corr_delta = candidate_avg_corr - current_avg_corr

    current_risk = str(current_overlap.get("portfolio_overlap_risk", "UNKNOWN"))
    candidate_risk = str(candidate_overlap.get("portfolio_overlap_risk", "UNKNOWN"))

    def _risk_rank(risk: str) -> int:
        r = str(risk).upper()
        if r == "HIGH":
            return 3
        if r == "MEDIUM":
            return 2
        if r == "LOW":
            return 1
        return 0

    current_risk_rank = _risk_rank(current_risk)
    candidate_risk_rank = _risk_rank(candidate_risk)

    # Decision logic
    if div_delta > 0.05 and corr_delta < 0 and candidate_risk_rank <= current_risk_rank:
        decision = "ADD"
        summary = "Candidate improves diversification and reduces effective portfolio correlation."
    elif div_delta > 0.0 and candidate_risk_rank <= current_risk_rank:
        decision = "WATCH"
        summary = "Candidate provides some diversification benefit, but improvement is modest."
    else:
        decision = "REJECT"
        summary = "Candidate does not improve diversification enough and may increase overlap risk."

    return {
        "current_diversification_score": round(current_div, 4),
        "candidate_diversification_score": round(candidate_div, 4),
        "diversification_delta": round(div_delta, 4),
        "current_average_correlation": round(current_avg_corr, 4),
        "candidate_average_correlation": round(candidate_avg_corr, 4),
        "correlation_delta": round(corr_delta, 4),
        "current_overlap_risk": current_risk,
        "candidate_overlap_risk": candidate_risk,
        "decision": decision,
        "summary": summary,
    }