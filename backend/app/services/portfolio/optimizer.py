from typing import Dict, Any, List
import numpy as np


def suggest_portfolio_allocation(
    report: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build a simple allocator-facing portfolio sizing suggestion from the
    portfolio intelligence report.

    Philosophy
    ----------
    - start from equal weight
    - penalize highly correlated strategies
    - reward more independent strategies
    - normalize to 100%

    Input
    -----
    report : output of build_portfolio_report()

    Output
    ------
    {
        "weights": [
            {"name": ..., "weight": ...},
            ...
        ],
        "method": str,
        "expected_diversification_improvement": float,
        "notes": List[str],
    }
    """

    names = report.get("names", []) or []
    correlation = report.get("correlation", {}) or {}
    corr_matrix = np.array(correlation.get("correlation_matrix", []), dtype=float)

    if not names:
        return {
            "weights": [],
            "method": "equal_weight_fallback",
            "expected_diversification_improvement": 0.0,
            "notes": ["No strategies available."],
        }

    n = len(names)

    if corr_matrix.size == 0 or corr_matrix.shape != (n, n):
        equal_w = round(100.0 / n, 2)
        return {
            "weights": [{"name": name, "weight": equal_w} for name in names],
            "method": "equal_weight_fallback",
            "expected_diversification_improvement": 0.0,
            "notes": ["Correlation matrix unavailable; used equal weights."],
        }

    # Average correlation per strategy excluding self-correlation
    avg_corr_by_strategy: List[float] = []
    for i in range(n):
        row = [float(corr_matrix[i, j]) for j in range(n) if j != i]
        avg_corr = float(np.mean(row)) if row else 0.0
        avg_corr_by_strategy.append(avg_corr)

    # Convert correlation burden into raw score:
    # lower average correlation => higher weight
    raw_scores = []
    for avg_corr in avg_corr_by_strategy:
        score = 1.0 - max(0.0, avg_corr)
        score = max(score, 0.05)  # keep a tiny minimum so nobody goes to zero
        raw_scores.append(score)

    total_score = float(sum(raw_scores)) if raw_scores else 0.0
    if total_score <= 0:
        raw_scores = [1.0] * n
        total_score = float(n)

    weights = []
    for name, score in zip(names, raw_scores):
        weight = (score / total_score) * 100.0
        weights.append({"name": name, "weight": round(weight, 2)})

    # Estimate "improvement" relative to equal weighting under redundancy penalty
    equal_weight_penalty = float(np.mean(avg_corr_by_strategy)) if avg_corr_by_strategy else 0.0
    optimized_penalty = 0.0
    for i, w in enumerate(weights):
        optimized_penalty += (w["weight"] / 100.0) * avg_corr_by_strategy[i]

    improvement = max(0.0, equal_weight_penalty - optimized_penalty)
    improvement_pct = round(improvement * 100.0, 2)

    notes: List[str] = []
    if n == 1:
        notes.append("Single-strategy portfolio; allocation optimization is not meaningful.")
    else:
        notes.append("Weights are reduced for strategies with higher average correlation to the rest of the book.")
        notes.append("This is a first-pass diversification optimizer, not a full mean-variance allocator.")

    return {
        "weights": weights,
        "method": "correlation_penalized_equal_weight",
        "expected_diversification_improvement": improvement_pct,
        "notes": notes,
    }