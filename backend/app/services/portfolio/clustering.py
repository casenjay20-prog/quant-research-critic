"""
Portfolio Clustering Engine

Purpose
-------
Group strategies by behavioral similarity using the correlation matrix.

Method
------
Simple threshold-based clustering on correlation:
- if corr(i, j) >= threshold, treat strategies as linked
- clusters are connected components of that graph

This is a clean first-pass institutional prototype.
"""

from typing import Dict, Any, List
import numpy as np


def cluster_strategies(
    correlation_matrix: np.ndarray,
    names: List[str],
    threshold: float = 0.7,
) -> Dict[str, Any]:
    """
    Parameters
    ----------
    correlation_matrix : np.ndarray
        NxN correlation matrix
    names : list[str]
        strategy names in matching order
    threshold : float
        minimum correlation to connect two strategies

    Returns
    -------
    dict with:
        clusters: list[list[str]]
        cluster_count: int
        threshold: float
    """

    if not isinstance(correlation_matrix, np.ndarray):
        raise TypeError("correlation_matrix must be a numpy array")

    if correlation_matrix.ndim != 2:
        raise ValueError("correlation_matrix must be 2-dimensional")

    n, m = correlation_matrix.shape
    if n != m:
        raise ValueError("correlation_matrix must be square")

    if len(names) != n:
        raise ValueError("names length must match matrix dimension")

    visited = [False] * n
    clusters: List[List[str]] = []

    def dfs(start: int, current_cluster: List[str]) -> None:
        visited[start] = True
        current_cluster.append(names[start])

        for j in range(n):
            if start == j:
                continue
            if visited[j]:
                continue
            if correlation_matrix[start, j] >= threshold:
                dfs(j, current_cluster)

    for i in range(n):
        if not visited[i]:
            cluster: List[str] = []
            dfs(i, cluster)
            clusters.append(cluster)

    return {
        "clusters": clusters,
        "cluster_count": len(clusters),
        "threshold": threshold,
    }