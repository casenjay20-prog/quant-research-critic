from typing import Dict, Any, List


def build_portfolio_recommendations(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert raw portfolio math into allocator-facing recommendations.

    Input
    -----
    report : output of build_portfolio_report()

    Output
    ------
    {
        "summary": str,
        "bullets": List[str],
        "action": str,
    }
    """

    correlation = report.get("correlation", {}) or {}
    clustering = report.get("clustering", {}) or {}
    overlap = report.get("overlap", {}) or {}

    avg_corr = correlation.get("average_correlation", 0.0)
    diversification = correlation.get("diversification_score", 0.0)
    cluster_count = clustering.get("cluster_count", 0)
    overlap_risk = overlap.get("portfolio_overlap_risk", "UNKNOWN")

    bullets: List[str] = []

    # Diversification interpretation
    if diversification >= 0.8:
        bullets.append("Portfolio appears well diversified based on current pairwise correlation structure.")
    elif diversification >= 0.5:
        bullets.append("Portfolio shows moderate diversification; monitor correlation drift over time.")
    else:
        bullets.append("Portfolio diversification is weak; current strategies may represent overlapping bets.")

    # Correlation interpretation
    try:
        avg_corr_f = float(avg_corr)
    except Exception:
        avg_corr_f = 0.0

    if avg_corr_f >= 0.7:
        bullets.append("Average correlation is very high; capital may be concentrated in one effective bet.")
    elif avg_corr_f >= 0.4:
        bullets.append("Average correlation is elevated; strategy overlap should be reviewed before scaling.")
    else:
        bullets.append("Average correlation is low enough to support diversification across sleeves.")

    # Cluster interpretation
    if cluster_count <= 1:
        bullets.append("Strategies collapse into a single cluster, suggesting limited independence.")
    elif cluster_count == 2:
        bullets.append("Portfolio contains two distinct strategy groups.")
    else:
        bullets.append(f"Portfolio contains {cluster_count} distinct clusters, indicating multiple independent exposures.")

    # Overlap interpretation
    if overlap_risk == "HIGH":
        bullets.append("Overlap risk is high; consider reducing combined allocation to correlated strategies.")
        action = "Reduce combined allocation to highly correlated clusters."
        summary = "Portfolio overlap is HIGH."
    elif overlap_risk == "MEDIUM":
        bullets.append("Overlap risk is moderate; avoid over-sizing similar clusters.")
        action = "Monitor redundancy and cap correlated sleeves."
        summary = "Portfolio overlap is MEDIUM."
    else:
        bullets.append("Overlap risk is low under current thresholds.")
        action = "Maintain allocation structure and continue monitoring."
        summary = "Portfolio overlap is LOW."

    return {
        "summary": summary,
        "bullets": bullets,
        "action": action,
    }