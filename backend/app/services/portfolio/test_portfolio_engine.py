import numpy as np
import pandas as pd

from backend.app.services.portfolio.report import build_portfolio_report


def main():

    dates = pd.date_range("2023-01-01", periods=250, freq="D")

    strat_a = pd.Series(np.random.normal(0.001, 0.01, size=250), index=dates)
    strat_b = pd.Series(np.random.normal(0.001, 0.01, size=250), index=dates)
    strat_c = pd.Series(np.random.normal(0.001, 0.01, size=250), index=dates)

    strategies = [
        ("strategy_A", strat_a),
        ("strategy_B", strat_b),
        ("strategy_C", strat_c),
    ]

    report = build_portfolio_report(strategies)

    print("\nPortfolio Intelligence Report")
    print("--------------------------------")
    print("Names:", report["names"])
    print("Matrix shape:", report["matrix_shape"])

    print("\nCorrelation")
    print("-----------")
    print("Average correlation:", report["correlation"]["average_correlation"])
    print("Diversification score:", report["correlation"]["diversification_score"])
    print(np.array(report["correlation"]["correlation_matrix"]))

    print("\nClustering")
    print("----------")
    print("Cluster count:", report["clustering"]["cluster_count"])
    print("Clusters:", report["clustering"]["clusters"])

    print("\nOverlap")
    print("-------")
    print("Portfolio overlap risk:", report["overlap"]["portfolio_overlap_risk"])
    print("Recommendation:", report["overlap"]["recommendation"])
    print("Overlap groups:")
    for group in report["overlap"]["overlap_groups"]:
        print(group)

    print("\nAllocator Recommendations")
    print("-------------------------")
    print("Summary:", report["recommendations"]["summary"])
    print("Action:", report["recommendations"]["action"])
    print("Bullets:")
    for bullet in report["recommendations"]["bullets"]:
        print("-", bullet)


if __name__ == "__main__":
    main()