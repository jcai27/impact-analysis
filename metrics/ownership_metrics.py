from __future__ import annotations

from collections import Counter, defaultdict


def compute_ownership_metrics(commit_rows: list[dict]) -> dict[str, dict]:
    module_totals: Counter = Counter()
    author_module_totals: dict[str, Counter] = defaultdict(Counter)

    for row in commit_rows:
        author = row["author"]
        for file_path in row.get("files_changed", []):
            module = file_path.split("/")[0] if "/" in file_path else file_path
            module_totals[module] += 1
            author_module_totals[author][module] += 1

    result: dict[str, dict] = {}
    for author, mod_counts in author_module_totals.items():
        ownership_shares = []
        maintainer_modules = 0
        for module, count in mod_counts.items():
            total = module_totals[module]
            share = count / total if total else 0.0
            ownership_shares.append(share)
            if share >= 0.4:
                maintainer_modules += 1

        result[author] = {
            "avg_module_ownership": round(sum(ownership_shares) / len(ownership_shares), 3) if ownership_shares else 0.0,
            "maintainer_modules": maintainer_modules,
        }

    return result
