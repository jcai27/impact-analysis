from __future__ import annotations

from datetime import datetime


def isoformat_or_empty(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator
