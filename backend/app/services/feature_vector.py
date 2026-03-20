from typing import Dict, Any


def build_feature_vector(strategy: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract normalized feature vector from Tier 2 output.
    This is what will power monitoring + clustering later.
    """

    deployability = strategy.get("deployability_score")
    fragility = strategy.get("fragility_index")
    confidence = strategy.get("confidence")

    stability = strategy.get("stability_transparency") or {}
    regime_gap = stability.get("regime_gap")
    bootstrap_dispersion = stability.get("bootstrap_dispersion")

    breakdown = strategy.get("deployability_breakdown") or {}

    return {
        "deployability_score": deployability,
        "fragility_index": fragility,
        "confidence": confidence,
        "regime_gap": regime_gap,
        "bootstrap_dispersion": bootstrap_dispersion,
        "base_signal": breakdown.get("base_signal"),
        "stability_penalty": breakdown.get("stability_penalty"),
        "fragility_overlay": breakdown.get("fragility_overlay"),
    }