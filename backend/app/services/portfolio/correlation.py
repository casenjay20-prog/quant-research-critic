"""
Portfolio Correlation Engine

Purpose
-------
Compute correlation statistics from an aligned returns matrix.

Input
-----
matrix: np.ndarray with shape (T, N)

Output
------
correlation matrix
average off-diagonal correlation
simple diversification score
"""

from typing import Dict, Any
import numpy as np


def compute_correlation_report(matrix: np.ndarray) -> Dict[str, Any]:
    """
    Parameters
    ----------
    matrix : np.ndarray
        shape (T, N), aligned return matrix

    Returns
    -------
    dict with:
        correlation_matrix: list[list[float]]
        average_correlation: float
        diversification_score: float
    """

    if not isinstance(matrix, np.ndarray):
        raise TypeError("matrix must be a numpy array")

    if matrix.ndim != 2:
        raise ValueError("matrix must be 2-dimensional")

    t, n = matrix.shape
    if t < 2 or n < 2:
        raise ValueError("matrix must have at least 2 rows and 2 columns")

    corr = np.corrcoef(matrix, rowvar=False)

    # Numerical cleanup
    corr = np.nan_to_num(corr, nan=0.0, posinf=0.0, neginf=0.0)
    corr = np.clip(corr, -1.0, 1.0)

    # Average off-diagonal correlation
    off_diag = corr[~np.eye(n, dtype=bool)]
    avg_corr = float(np.mean(off_diag)) if off_diag.size else 0.0

    # Simple diversification score:
    # higher when average correlation is lower
    diversification_score = float(1.0 - max(0.0, avg_corr))

    return {
        "correlation_matrix": corr.round(4).tolist(),
        "average_correlation": round(avg_corr, 4),
        "diversification_score": round(diversification_score, 4),
    }