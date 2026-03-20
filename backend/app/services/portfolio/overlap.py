"""
Portfolio Overlap Detector

Purpose
-------
Turn clusters + correlation data into allocator-facing overlap risk.

Output
------
- overlap groups
- risk level per cluster
- simple recommendation
"""

from typing import Dict, Any, List
import numpy as np


def detect_overlap_risk(
    correlation_matrix: np.ndarray,
    names: List[str],
    clusters: List[List[str]],
    high_corr_threshold: float = 0.7,
) -> Dict[str, Any]:
    """
    Parameters
    ----------
    correlation_matrix : np.ndarray
        NxN correlation matrix
    names : list[str]
        strategy names in matrix order
    clusters : list[list[str]]
        cluster output from cluster_strategies()
    high_corr_threshold : float
        correlation threshold for high overlap

    Returns
    -------
    dict with:
        overlap_groups
        portfolio_overlap_risk
        recommendation
    """

    if not isinstance(correlation_matrix, np.ndarray):
        raise TypeError("correlation_matrix must be a numpy array")

    name_to_idx = {name: i for i, name in enumerate(names)}

    overlap_groups: List[Dict[str, Any]] = []
    high_risk_count = 0

    for cluster in clusters:
        if len(cluster) == 1:
            overlap_groups.append(
                {
                    "members": cluster,
                    "average_internal_correlation": 0.0,
                    "risk": "LOW",
                }
            )
            continue

        vals: List[float] = []
        for i in range(len(cluster)):
            for j in range(i + 1, len(cluster)):
                a = name_to_idx[cluster[i]]
                b = name_to_idx[cluster[j]]
                vals.append(float(correlation_matrix[a, b]))

        avg_corr = float(np.mean(vals)) if vals else 0.0

        if avg_corr >= high_corr_threshold:
            risk = "HIGH"
            high_risk_count += 1
        elif avg_corr >= 0.4:
            risk = "MEDIUM"
        else:
            risk = "LOW"

        overlap_groups.append(
            {
                "members": cluster,
                "average_internal_correlation": round(avg_corr, 4),
                "risk": risk,
            }
        )

    if high_risk_count > 0:
        portfolio_overlap_risk = "HIGH"
        recommendation = "Reduce combined allocation to highly correlated clusters."
    elif any(g["risk"] == "MEDIUM" for g in overlap_groups):
        portfolio_overlap_risk = "MEDIUM"
        recommendation = "Monitor redundancy and avoid over-allocating similar strategies."
    else:
        portfolio_overlap_risk = "LOW"
        recommendation = "Portfolio appears diversified across current clusters."

    return {
        "overlap_groups": overlap_groups,
        "portfolio_overlap_risk": portfolio_overlap_risk,
        "recommendation": recommendation,
    }