from typing import Dict, List


def select_key_metrics(payload: Dict) -> List[Dict[str, str]]:
    """
    Selects and formats the small, opinionated metric set
    shown on Page 1 of the scorecard.
    No new math. Presentation only.
    """

    normalized = payload.get("normalized", {})

    metrics = [
        {
            "label": "CAGR",
            "value": _fmt_pct(payload.get("cagr")),
        },
        {
            "label": "Max Drawdown",
            "value": _fmt_pct(payload.get("max_drawdown")),
        },
        {
            "label": "Sharpe",
            "value": _fmt_num(payload.get("sharpe"), 2),
        },
        {
            "label": "Volatility",
            "value": _fmt_pct(payload.get("volatility")),
        },
        {
            "label": "Confidence",
            "value": _fmt_num(normalized.get("score_confidence"), 2),
        },
    ]

    return metrics


# -----------------
# Formatting helpers
# -----------------

def _fmt_pct(x) -> str:
    if x is None:
        return "—"
    try:
        return f"{float(x):.2%}"
    except Exception:
        return "—"


def _fmt_num(x, decimals: int = 2) -> str:
    if x is None:
        return "—"
    try:
        return f"{float(x):.{decimals}f}"
    except Exception:
        return "—"
