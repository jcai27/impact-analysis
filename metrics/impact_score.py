from __future__ import annotations


def compute_impact_score(
    feature_delivery: float,
    system_impact: float,
    ownership: float,
    maintenance: float,
    collaboration: float = 0.5,
) -> float:
    score = (
        0.35 * feature_delivery
        + 0.25 * system_impact
        + 0.20 * ownership
        + 0.15 * maintenance
        + 0.05 * collaboration
    )
    return round(score, 3)
