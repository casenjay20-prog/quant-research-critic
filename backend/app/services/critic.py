def score_strategy(metrics: dict) -> dict:
    sharpe = metrics.get("sharpe", 0)
    max_dd = abs(metrics.get("max_drawdown", 0))

    # Simple first-pass logic (we will improve later)
    if sharpe >= 2.0 and max_dd <= 0.15:
        grade = "A"
        fragility = "low"
    elif sharpe >= 1.2 and max_dd <= 0.25:
        grade = "B+"
        fragility = "moderate"
    else:
        grade = "C"
        fragility = "high"

    summary = [
        f"Sharpe ratio of {sharpe:.2f} indicates {'strong' if sharpe > 1.5 else 'moderate'} risk-adjusted returns.",
        f"Maximum drawdown of {max_dd:.2%} suggests {fragility} fragility.",
    ]

    return {
        "grade": grade,
        "fragility": fragility,
        "summary": summary,
    }
