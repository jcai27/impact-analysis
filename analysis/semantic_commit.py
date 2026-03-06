from __future__ import annotations

from dataclasses import dataclass


COMMIT_TYPES = {"feature", "bugfix", "refactor", "tests", "docs", "infrastructure"}


@dataclass
class SemanticCommit:
    type: str
    complexity: str
    area: str
    description: str
    confidence: float
    source: str = "heuristic"


def infer_type(message: str, changed_files: list[str]) -> tuple[str, float]:
    m = message.lower()

    # Conventional commit prefixes — highest confidence, check first.
    if m.startswith(("fix:", "fix(", "fix!:")):
        return "bugfix", 0.97
    if m.startswith(("feat:", "feat(", "feat!:")):
        return "feature", 0.97
    if m.startswith(("docs:", "docs(")):
        return "docs", 0.97
    if m.startswith(("chore:", "chore(")):
        return "infrastructure", 0.95
    if m.startswith(("revert:", "revert(")):
        return "refactor", 0.95
    if m.startswith(("refactor:", "refactor(")):
        return "refactor", 0.97
    if m.startswith(("test:", "test(", "tests:", "tests(")):
        return "tests", 0.97
    if m.startswith(("ci:", "ci(", "build:", "build(")):
        return "infrastructure", 0.95

    # Keyword fallback for non-conventional messages.
    if any(k in m for k in ("fix", "bug", "hotfix", "error")):
        return "bugfix", 0.9
    if any(k in m for k in ("refactor", "cleanup", "restructure")):
        return "refactor", 0.9
    if any(k in m for k in ("test", "spec")) or all("test" in f.lower() for f in changed_files if changed_files):
        return "tests", 0.85
    if any(k in m for k in ("doc", "readme", "comment")):
        return "docs", 0.85
    if any(k in m for k in ("ci", "docker", "k8s", "infra", "terraform", "deploy")):
        return "infrastructure", 0.85
    if any(k in m for k in ("add", "implement", "introduce", "feature")):
        return "feature", 0.8

    joined = " ".join(changed_files).lower()
    if any(k in joined for k in ("readme", "docs/")):
        return "docs", 0.7
    if any(k in joined for k in ("test", "spec")):
        return "tests", 0.7
    if any(k in joined for k in (".github", "docker", "infra", "deploy")):
        return "infrastructure", 0.7

    return "feature", 0.55


def infer_complexity(lines_added: int, lines_deleted: int, files_changed_count: int) -> str:
    churn = lines_added + lines_deleted
    if churn < 40 and files_changed_count <= 2:
        return "low"
    if churn < 250 and files_changed_count <= 8:
        return "medium"
    return "high"


def infer_area(changed_files: list[str]) -> str:
    if not changed_files:
        return "unknown"

    top = changed_files[0].split("/")[0]
    if top in {"src", "app", "lib"} and len(changed_files[0].split("/")) > 1:
        return changed_files[0].split("/")[1]
    return top


def classify_semantic_commit(
    message: str,
    changed_files: list[str],
    lines_added: int,
    lines_deleted: int,
) -> SemanticCommit:
    commit_type, confidence = infer_type(message, changed_files)
    complexity = infer_complexity(lines_added, lines_deleted, len(changed_files))
    area = infer_area(changed_files)
    description = message.split("\n", 1)[0][:280]

    if commit_type not in COMMIT_TYPES:
        commit_type = "feature"

    return SemanticCommit(
        type=commit_type,
        complexity=complexity,
        area=area,
        description=description,
        confidence=confidence,
        source="heuristic",
    )
