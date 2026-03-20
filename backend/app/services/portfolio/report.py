from typing import Dict, Any, List, Tuple
import numpy as np
import pandas as pd

from backend.app.services.portfolio.returns_matrix import build_returns_matrix
from backend.app.services.portfolio.correlation import compute_correlation_report
from backend.app.services.portfolio.clustering import cluster_strategies
from backend.app.services.portfolio.overlap import detect_overlap_risk
from backend.app.services.portfolio.recommendations import build_portfolio_recommendations
from backend.app.services.portfolio.allocation import compute_allocation_from_correlation


def build_portfolio_report(
    strategies: List[Tuple[str, pd.Series]],
    cluster_threshold: float = 0.7,
) -> Dict[str, Any]:
    """
    Build a single portfolio intelligence report from multiple strategies.

    Parameters
    ----------
    strategies : list of (name, returns_series)
        returns_series must be a pandas Series indexed by datetime
    cluster_threshold : float
        correlation threshold used for clustering / overlap logic

    Returns
    -------
    dict with:
        names
        dates
        matrix_shape
        correlation
        clustering
        overlap
        recommendations
        allocation
    """

    matrix, dates, names = build_returns_matrix(strategies)

    correlation = compute_correlation_report(matrix)

    corr_matrix = np.array(correlation["correlation_matrix"], dtype=float)

    clustering = cluster_strategies(
        correlation_matrix=corr_matrix,
        names=names,
        threshold=cluster_threshold,
    )

    overlap = detect_overlap_risk(
        correlation_matrix=corr_matrix,
        names=names,
        clusters=clustering["clusters"],
        high_corr_threshold=cluster_threshold,
    )

    allocation = compute_allocation_from_correlation(
        correlation_matrix=correlation["correlation_matrix"],
        names=names,
    )

    base_report = {
        "names": names,
        "dates": dates,
        "matrix_shape": list(matrix.shape),
        "correlation": correlation,
        "clustering": clustering,
        "overlap": overlap,
        "allocation": allocation,
    }

    # existing recommendations engine
    recommendations = build_portfolio_recommendations(base_report)

    base_report["recommendations"] = recommendations

    return base_report