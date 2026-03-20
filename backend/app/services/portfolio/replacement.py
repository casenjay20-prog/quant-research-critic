from typing import Dict, Any, List, Tuple

import pandas as pd

from backend.app.services.portfolio.report import build_portfolio_report


def evaluate_replacement(
    current_strategies: List[Tuple[str, pd.Series]],
    candidate_name: str,
    candidate_series: pd.Series,
) -> Dict[str, Any]:
    """
    Evaluate whether a candidate strategy should be added, rejected,
    or used to replace an existing sleeve.

    Logic:
    - Build the current portfolio report
    - Test every one-for-one replacement
    - Compare average correlation
    - Pick the best outcome

    Returns:
    {
        "current_average_correlation": float,
        "best_candidate_average_correlation": float,
        "diversification_improvement": float,
        "decision": str,
        "replaced_strategy": str | None,
        "summary": str,
    }
    """

    if not current_strategies:
        candidate_report = build_portfolio_report([(candidate_name, candidate_series)])
        return {
            "current_average_correlation": 0.0,
            "best_candidate_average_correlation": float(
                candidate_report["correlation"]["average_correlation"]
            ),
            "diversification_improvement": 0.0,
            "decision": "ADD",
            "replaced_strategy": None,
            "summary": "No existing portfolio detected. Candidate can be added as the first strategy.",
        }

    current_report = build_portfolio_report(current_strategies)
    current_corr = float(current_report["correlation"]["average_correlation"])

    # First test simple ADD
    add_portfolio = current_strategies + [(candidate_name, candidate_series)]
    add_report = build_portfolio_report(add_portfolio)
    add_corr = float(add_report["correlation"]["average_correlation"])

    best_decision = "REJECT"
    best_replaced_strategy = None
    best_corr = current_corr

    if add_corr < best_corr:
        best_decision = "ADD"
        best_corr = add_corr

    # Now test one-for-one replacements
    for i, (existing_name, _existing_series) in enumerate(current_strategies):
        trial_portfolio = current_strategies.copy()
        trial_portfolio[i] = (candidate_name, candidate_series)

        trial_report = build_portfolio_report(trial_portfolio)
        trial_corr = float(trial_report["correlation"]["average_correlation"])

        if trial_corr < best_corr:
            best_decision = "REPLACE"
            best_replaced_strategy = existing_name
            best_corr = trial_corr

    diversification_improvement = current_corr - best_corr

    if best_decision == "REPLACE" and best_replaced_strategy is not None:
        summary = (
            f"Candidate improves diversification most by replacing "
            f"{best_replaced_strategy}."
        )
    elif best_decision == "ADD":
        summary = "Candidate improves diversification as an additive sleeve."
    else:
        summary = "Candidate does not improve diversification enough to justify inclusion."

    return {
        "current_average_correlation": round(current_corr, 4),
        "best_candidate_average_correlation": round(best_corr, 4),
        "diversification_improvement": round(diversification_improvement, 4),
        "decision": best_decision,
        "replaced_strategy": best_replaced_strategy,
        "summary": summary,
    }