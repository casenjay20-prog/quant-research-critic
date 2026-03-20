import numpy as np
import pandas as pd

from backend.app.services.portfolio.report import build_portfolio_report
from backend.app.services.portfolio.diversification import score_strategy_addition


def main():
    dates = pd.date_range("2023-01-01", periods=250, freq="D")

    # Current portfolio: two highly similar strategies
    base_a = np.random.normal(0.001, 0.01, size=250)
    base_b = base_a + np.random.normal(0.0, 0.001, size=250)

    # Candidate: more independent strategy
    candidate = np.random.normal(0.0008, 0.012, size=250)

    strat_a = pd.Series(base_a, index=dates)
    strat_b = pd.Series(base_b, index=dates)
    strat_c = pd.Series(candidate, index=dates)

    current_strategies = [
        ("strategy_A", strat_a),
        ("strategy_B", strat_b),
    ]

    candidate_strategies = [
        ("strategy_A", strat_a),
        ("strategy_B", strat_b),
        ("strategy_C", strat_c),
    ]

    current_report = build_portfolio_report(current_strategies)
    candidate_report = build_portfolio_report(candidate_strategies)

    score = score_strategy_addition(current_report, candidate_report)

    print("\nDiversification Score Engine")
    print("----------------------------")
    print("Current diversification score:", score["current_diversification_score"])
    print("Candidate diversification score:", score["candidate_diversification_score"])
    print("Diversification delta:", score["diversification_delta"])
    print("Current average correlation:", score["current_average_correlation"])
    print("Candidate average correlation:", score["candidate_average_correlation"])
    print("Correlation delta:", score["correlation_delta"])
    print("Current overlap risk:", score["current_overlap_risk"])
    print("Candidate overlap risk:", score["candidate_overlap_risk"])
    print("Decision:", score["decision"])
    print("Summary:", score["summary"])


if __name__ == "__main__":
    main()