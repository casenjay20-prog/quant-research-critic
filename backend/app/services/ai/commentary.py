from typing import Dict, Any, List
import os
import json

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_str(value: Any, default: str = "") -> str:
    try:
        s = str(value)
        return s if s else default
    except Exception:
        return default


def _format_pct_from_unit(value: float) -> str:
    return f"{value * 100:.1f}%"


def _get_gemini_client():
    try:
        import google.generativeai as genai
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return None
        genai.configure(api_key=api_key)
        return genai.GenerativeModel("gemini-1.5-flash")
    except Exception:
        return None


def _call_gemini(prompt: str, fallback: str) -> str:
    try:
        model = _get_gemini_client()
        if not model:
            return fallback
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception:
        return fallback


def generate_portfolio_commentary(portfolio_report: Dict[str, Any]) -> Dict[str, str]:
    correlation = portfolio_report.get("correlation", {}) or {}
    clustering = portfolio_report.get("clustering", {}) or {}
    overlap = portfolio_report.get("overlap", {}) or {}
    allocation = portfolio_report.get("allocation", {}) or {}
    recommendations = portfolio_report.get("recommendations", {}) or {}

    avg_corr = _safe_float(correlation.get("average_correlation"), 0.0)
    diversification_score = _safe_float(correlation.get("diversification_score"), 0.0)
    overlap_risk = _safe_str(overlap.get("portfolio_overlap_risk"), "UNKNOWN").upper()
    cluster_count = int(clustering.get("cluster_count", 0) or 0)

    weights: List[Dict[str, Any]] = allocation.get("weights", []) or []
    top_weight_name = "N/A"
    top_weight_value = 0.0
    if weights:
        top_weight = max(weights, key=lambda x: _safe_float(x.get("weight"), 0.0))
        top_weight_name = _safe_str(top_weight.get("name"), "N/A")
        top_weight_value = _safe_float(top_weight.get("weight"), 0.0)

    recommendation_summary = _safe_str(recommendations.get("summary"), "")
    rec_bullets = recommendations.get("bullets", []) or []

    prompt = f"""You are a senior quant analyst reviewing a systematic trading portfolio. 
Your job is to write a concise, direct diagnostic commentary for an allocator or systematic trader.

Here are the deterministic portfolio statistics:
- Overlap Risk: {overlap_risk}
- Diversification Score: {_format_pct_from_unit(diversification_score)}
- Average Pairwise Correlation: {avg_corr:.2f}
- Number of Strategy Clusters: {cluster_count}
- Number of Strategies: {len(weights)}
- Highest-weighted strategy: {top_weight_name} at {top_weight_value:.1f}%
- Recommendation summary: {recommendation_summary}
- Risk flags: {', '.join(rec_bullets[:3]) if rec_bullets else 'None'}

Write 3-4 sentences of sharp, institutional-quality portfolio commentary. 
Be specific about what the numbers mean for deployment risk.
Do not use bullet points. Do not hedge excessively. 
Write as if briefing a fund manager who has 30 seconds to read this.
Do not mention that you are an AI."""

    fallback = (
        f"Portfolio shows {overlap_risk.lower()} overlap risk with a diversification score of "
        f"{_format_pct_from_unit(diversification_score)} and average correlation of {avg_corr:.2f}. "
        f"The {cluster_count} detected clusters suggest the portfolio has limited independent sleeves. "
        f"Highest allocation goes to {top_weight_name} at {top_weight_value:.1f}%."
    )

    commentary = _call_gemini(prompt, fallback)

    return {
        "portfolio_commentary": commentary,
    }


def generate_strategy_diligence_summary(strategy_payload: Dict[str, Any]) -> Dict[str, str]:
    scorecard = strategy_payload.get("scorecard", {}) or {}
    rows = int(strategy_payload.get("rows", 0) or 0)
    years = _safe_float(strategy_payload.get("years"), 0.0)
    sharpe = _safe_float(strategy_payload.get("sharpe"), 0.0)
    max_dd = _safe_float(strategy_payload.get("max_drawdown"), 0.0)
    cagr = _safe_float(strategy_payload.get("cagr"), 0.0)
    grade = _safe_str(scorecard.get("grade"), "N/A")
    score = _safe_float(scorecard.get("score"), 0.0)
    flags = strategy_payload.get("flags", []) or []

    prompt = f"""You are a quant analyst writing a brief due-diligence note on a systematic strategy.

Strategy statistics (deterministic, not estimated):
- Score: {score:.1f}/100
- Grade: {grade}
- Sharpe Ratio: {sharpe:.2f}
- CAGR: {_format_pct_from_unit(cagr)}
- Max Drawdown: {_format_pct_from_unit(max_dd)}
- History: {years:.1f} years ({rows} daily rows)
- Risk flags triggered: {len(flags)}

Write 2-3 sentences of direct due-diligence commentary.
State clearly whether this strategy is deployment-ready, needs more history, or should stay in research.
Be specific. No bullet points. No hedging. Write for a systematic fund manager."""

    fallback = (
        f"Strategy graded {grade} with a score of {score:.1f}. "
        f"Sharpe of {sharpe:.2f} over {years:.1f} years with {max_dd*100:.1f}% max drawdown. "
        f"{'Sufficient history for initial review.' if years >= 1.0 else 'Insufficient history — treat as research only.'}"
    )

    summary = _call_gemini(prompt, fallback)

    return {
        "strategy_summary": summary,
        "strengths": "",
        "weaknesses": "",
        "deployment_view": summary,
    }


def generate_allocation_rationale(portfolio_report: Dict[str, Any]) -> Dict[str, str]:
    correlation = portfolio_report.get("correlation", {}) or {}
    clustering = portfolio_report.get("clustering", {}) or {}
    allocation = portfolio_report.get("allocation", {}) or {}
    overlap = portfolio_report.get("overlap", {}) or {}

    avg_corr = _safe_float(correlation.get("average_correlation"), 0.0)
    diversification_score = _safe_float(correlation.get("diversification_score"), 0.0)
    cluster_count = int(clustering.get("cluster_count", 0) or 0)
    overlap_risk = _safe_str(overlap.get("portfolio_overlap_risk"), "UNKNOWN").upper()

    weights: List[Dict[str, Any]] = allocation.get("weights", []) or []

    if not weights:
        return {
            "allocation_rationale": "No allocation output was available to explain.",
        }

    sorted_weights = sorted(weights, key=lambda x: _safe_float(x.get("weight"), 0.0), reverse=True)
    weights_str = ", ".join([
        f"{_safe_str(w.get('name'), 'unknown')} ({_safe_float(w.get('weight'), 0.0):.1f}%)"
        for w in sorted_weights
    ])

    prompt = f"""You are a quant analyst explaining a correlation-penalized portfolio allocation to a fund manager.

The allocation engine uses only realized correlation structure — no return forecasts, no volatility forecasts.
Strategies with more independent return streams receive higher weights.

Portfolio allocation output:
- Weights (highest to lowest): {weights_str}
- Average pairwise correlation: {avg_corr:.2f}
- Diversification score: {_format_pct_from_unit(diversification_score)}
- Strategy clusters detected: {cluster_count}
- Overlap risk: {overlap_risk}

Write 3-4 sentences explaining why the allocation looks this way.
Be specific about which strategies are penalized for overlap and which are rewarded for independence.
No bullet points. Write for a sophisticated allocator who understands correlation math."""

    fallback = (
        f"Allocation weights reflect correlation-penalized sizing across {len(weights)} strategies. "
        f"With average correlation of {avg_corr:.2f} and {cluster_count} clusters, "
        f"the engine rewards independent sleeves and penalizes overlapping exposures. "
        f"Diversification score of {_format_pct_from_unit(diversification_score)} constrains overall position sizing."
    )

    rationale = _call_gemini(prompt, fallback)

    return {
        "allocation_rationale": rationale,
    }


def generate_copilot_response(
    question: str,
    portfolio_report: Dict[str, Any],
    conversation_history: List[Dict[str, str]] = None
) -> str:
    """
    Quant Copilot — answers follow-up questions about the specific portfolio.
    Receives the full deterministic portfolio report as context.
    """
    if conversation_history is None:
        conversation_history = []

    correlation = portfolio_report.get("correlation", {}) or {}
    clustering = portfolio_report.get("clustering", {}) or {}
    overlap = portfolio_report.get("overlap", {}) or {}
    allocation = portfolio_report.get("allocation", {}) or {}
    recommendations = portfolio_report.get("recommendations", {}) or {}

    avg_corr = _safe_float(correlation.get("average_correlation"), 0.0)
    diversification_score = _safe_float(correlation.get("diversification_score"), 0.0)
    overlap_risk = _safe_str(overlap.get("portfolio_overlap_risk"), "UNKNOWN").upper()
    cluster_count = int(clustering.get("cluster_count", 0) or 0)
    weights: List[Dict[str, Any]] = allocation.get("weights", []) or []
    names = portfolio_report.get("names", []) or []
    corr_matrix = correlation.get("correlation_matrix", []) or []
    rec_summary = _safe_str(recommendations.get("summary"), "")
    rec_bullets = recommendations.get("bullets", []) or []

    weights_str = ", ".join([
        f"{_safe_str(w.get('name'), 'unknown')} ({_safe_float(w.get('weight'), 0.0):.1f}%)"
        for w in sorted(weights, key=lambda x: _safe_float(x.get("weight"), 0.0), reverse=True)
    ])

    corr_str = ""
    if names and corr_matrix:
        pairs = []
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                try:
                    val = float(corr_matrix[i][j])
                    pairs.append(f"{names[i]} vs {names[j]}: {val:.2f}")
                except Exception:
                    pass
        corr_str = ", ".join(pairs[:10])

    history_str = ""
    if conversation_history:
        history_str = "\n".join([
            f"{'User' if m['role'] == 'user' else 'Copilot'}: {m['content']}"
            for m in conversation_history[-6:]
        ])

    prompt = f"""You are Quant Copilot, an expert systematic trading analyst embedded in a portfolio analysis tool.
You have access to the full deterministic analysis of this specific portfolio.

PORTFOLIO DATA:
- Strategy names: {', '.join(names) if names else 'N/A'}
- Overlap risk: {overlap_risk}
- Diversification score: {_format_pct_from_unit(diversification_score)}
- Average correlation: {avg_corr:.2f}
- Clusters: {cluster_count}
- Allocation weights: {weights_str}
- Pairwise correlations: {corr_str if corr_str else 'N/A'}
- Recommendation: {rec_summary}
- Risk flags: {', '.join(rec_bullets[:3]) if rec_bullets else 'None'}

{f'CONVERSATION HISTORY:{chr(10)}{history_str}{chr(10)}' if history_str else ''}

USER QUESTION: {question}

Answer directly and specifically using the portfolio data above.
Be concise — 2-4 sentences unless the question requires more detail.
If the question cannot be answered from the available data, say so clearly.
Do not use bullet points unless listing specific strategies.
Do not mention that you are an AI or that you are using a language model.
Write as a senior quant analyst would speak."""

    fallback = "I don't have enough information to answer that question based on the current portfolio data."

    return _call_gemini(prompt, fallback)