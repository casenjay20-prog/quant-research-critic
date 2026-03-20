def build_report(payload: dict) -> dict:
    """
    Converts /v1/analyze raw output into a UI-friendly, report-style structure.
    """
    return {
        "title": "Quant Research Critic Report",
        "summary": {
            "score": payload.get("scorecard", {}).get("score"),
            "grade": payload.get("scorecard", {}).get("grade"),
            "confidence": payload.get("scorecard", {}).get("confidence"),
            "flags": payload.get("flags", []),
        },
        "metrics": {
            "cagr": payload.get("cagr"),
            "sharpe": payload.get("sharpe"),
            "max_drawdown": payload.get("max_drawdown"),
            "normalized": payload.get("normalized", {}),
        },
        "period": {
            "start_date": payload.get("start_date"),
            "end_date": payload.get("end_date"),
            "rows": payload.get("rows"),
            "years": payload.get("years"),
        },
        "curves": {
            "equity_curve": payload.get("equity_curve", []),
        },
        "critic_text": payload.get("critic"),
    }
