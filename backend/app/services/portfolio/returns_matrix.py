"""
Portfolio Returns Matrix Engine

Purpose
-------
Take multiple strategies (each with dates + returns) and align them into a
single returns matrix so portfolio statistics can be computed.

Output
------
matrix: T x N aligned return matrix
dates: shared timeline
names: strategy labels
"""

from typing import List, Tuple
import pandas as pd
import numpy as np


def build_returns_matrix(
    strategies: List[Tuple[str, pd.Series]]
) -> Tuple[np.ndarray, List[str], List[str]]:
    """
    Parameters
    ----------
    strategies : list of (name, returns_series)
        returns_series must be a pandas Series indexed by datetime

    Returns
    -------
    matrix : np.ndarray
        shape (T, N) return matrix
    dates : list[str]
        aligned date index
    names : list[str]
        strategy names
    """

    if not strategies:
        raise ValueError("No strategies provided")

    frames = []
    names = []

    for name, series in strategies:

        if not isinstance(series, pd.Series):
            raise TypeError(f"{name} returns must be pandas Series")

        s = series.copy()
        s.name = name

        frames.append(s)
        names.append(name)

    # Align all strategies on shared dates
    df = pd.concat(frames, axis=1, join="inner")

    # Drop NaNs if any remain
    df = df.dropna()

    if df.shape[0] < 10:
        raise ValueError("Not enough overlapping data between strategies")

    matrix = df.values
    dates = [str(d) for d in df.index]

    return matrix, dates, names