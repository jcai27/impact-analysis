from __future__ import annotations

from collections import defaultdict


def compute_maintenance_metrics(semantic_rows: list[dict]) -> dict[str, dict]:
    result: dict[str, dict] = defaultdict(lambda: {"bugfixes": 0, "refactors": 0, "tests": 0, "docs": 0})

    for row in semantic_rows:
        author = row["author"]
        kind = row["type"]
        if kind == "bugfix":
            result[author]["bugfixes"] += 1
        elif kind == "refactor":
            result[author]["refactors"] += 1
        elif kind == "tests":
            result[author]["tests"] += 1
        elif kind == "docs":
            result[author]["docs"] += 1

    return dict(result)
