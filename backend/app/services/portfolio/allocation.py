from typing import Dict, Any
import numpy as np


def compute_allocation_from_correlation(
    correlation_matrix,
    names
) -> Dict[str, Any]:
    """
    Simple correlation-penalized allocation engine.

    Idea:
    - strategies that are highly correlated with the rest of the portfolio
      receive smaller weights
    - strategies that are more independent receive larger weights

    This is intentionally simple and deterministic.
    """

    corr = np.array(correlation_matrix, dtype=float)

    if corr.ndim != 2:
        raise ValueError("Correlation matrix must be 2D")

    n = corr.shape[0]

    if n != len(names):
        raise ValueError("Names length must match correlation matrix size")

    if n == 1:
        return {
            "weights": [
                {"name": names[0], "weight": 100.0}
            ],
            "method": "single_strategy",
        }

    avg_corr = []

    for i in range(n):
        others = [corr[i, j] for j in range(n) if j != i]
        avg_corr.append(float(np.mean(others)))

    penalties = [max(0.01, 1 - c) for c in avg_corr]

    total = sum(penalties)

    weights = [(p / total) * 100 for p in penalties]

    allocation = [
        {"name": names[i], "weight": round(weights[i], 2)}
        for i in range(n)
    ]

    diversification_score = float(np.mean(penalties))

    return {
        "weights": allocation,
        "method": "correlation_penalized_equal_weight",
        "diversification_score": round(diversification_score, 4),
        "notes": [
            "Strategies with higher average correlation receive smaller weights.",
            "This is a deterministic diversification-first allocator."
        ]
    }