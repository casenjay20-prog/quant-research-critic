from typing import Dict, List


def select_top_flags(payload: Dict, max_flags: int = 3) -> List[Dict[str, str]]:
    """
    Selects the top-N red flags for Page 1.
    Assumes flags are already severity-ordered upstream.
    """

    flags = payload.get("flags", [])

    selected = []
    for f in flags[:max_flags]:
        selected.append(
            {
                "flag": f,
                "severity": _infer_severity(f),
            }
        )

    return selected


def _infer_severity(flag_text: str) -> str:
    """
    Lightweight severity labeling for presentation.
    No scoring logic lives here.
    """

    text = flag_text.lower()

    if any(k in text for k in ["tiny sample", "overfit", "regime", "unstable"]):
        return "HIGH"
    if any(k in text for k in ["drawdown", "concentration", "tail"]):
        return "MEDIUM"
    return "LOW"
