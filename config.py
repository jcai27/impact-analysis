from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("IMPACT_DB_URL", "sqlite:///impact_analyzer.db")
    default_branch: str = os.getenv("IMPACT_DEFAULT_BRANCH", "HEAD")
    default_max_commits: int = int(os.getenv("IMPACT_MAX_COMMITS", "500"))
    default_since_days: int = int(os.getenv("IMPACT_SINCE_DAYS", "90"))
    semantic_mode: str = os.getenv("IMPACT_SEMANTIC_MODE", "hybrid")
    semantic_confidence_threshold: float = float(
        os.getenv("IMPACT_SEMANTIC_CONFIDENCE_THRESHOLD", "0.75")
    )
    llm_max_calls: int = int(os.getenv("IMPACT_LLM_MAX_CALLS", "100"))

    # Hosted analysis target — configure via env vars for the deployed version
    repo_url: str = os.getenv("IMPACT_REPO_URL", "https://github.com/PostHog/posthog.git")
    repo_dir: str = os.getenv("IMPACT_REPO_DIR", "/tmp/posthog")
    db_path: str = os.getenv("IMPACT_DB_PATH", "impact_analyzer.db")

    # GitHub API token — when set, commits are fetched via API (no disk clone needed)
    github_token: str = os.getenv("GITHUB_TOKEN", "")


settings = Settings()
