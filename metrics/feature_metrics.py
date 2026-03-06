from __future__ import annotations

from collections import defaultdict


def compute_feature_metrics(semantic_rows: list[dict]) -> dict[str, dict]:
    result: dict[str, dict] = defaultdict(lambda: {"features": 0, "feature_complexity": 0.0, "subsystems_touched": set()})

    complexity_weight = {"low": 0.5, "medium": 1.0, "high": 1.5}

    for row in semantic_rows:
        author = row["author"]
        if row["type"] == "feature":
            result[author]["features"] += 1
            result[author]["feature_complexity"] += complexity_weight.get(row["complexity"], 1.0)
        result[author]["subsystems_touched"].add(row["area"])

    final: dict[str, dict] = {}
    for author, data in result.items():
        final[author] = {
            "features": data["features"],
            "feature_complexity": round(data["feature_complexity"], 3),
            "subsystems_touched": len(data["subsystems_touched"]),
        }
    return final
