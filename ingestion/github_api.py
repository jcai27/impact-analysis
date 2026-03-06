from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

import requests


class GitHubFetcher:
    """Fetches commit data from the GitHub REST API — no local clone required."""

    _BASE = "https://api.github.com"

    def __init__(self, owner: str, repo: str, token: str = "") -> None:
        self.owner = owner
        self.repo = repo
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "impact-analyzer/1.0",
            }
        )
        if token:
            self._session.headers["Authorization"] = f"Bearer {token}"

    def _get(self, path: str, **params: object) -> dict | list:
        url = f"{self._BASE}{path}"
        for attempt in range(4):
            r = self._session.get(url, params=params or None, timeout=30)
            if r.status_code in (403, 429):
                reset_ts = int(r.headers.get("X-RateLimit-Reset", 0))
                wait = max(reset_ts - time.time(), 0) + 2
                time.sleep(min(wait, 65))
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError(f"GitHub API request failed after retries: {url}")

    def fetch_commit_records(
        self,
        since_days: int = 90,
        max_commits: int = 500,
        progress: Callable[[str], None] | None = None,
    ) -> list[dict]:
        """Return a flat list of commit records ready for the analysis pipeline.

        Each record contains the same keys as the clone-based pipeline:
        commit_hash, author, timestamp, message, files_changed,
        lines_added, lines_deleted, diff_text.
        """
        since = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()

        # 1. Paginate the commit list.
        if progress:
            progress("Listing commits from GitHub API…")

        summaries: list[dict] = []
        page = 1
        while len(summaries) < max_commits:
            batch: list = self._get(  # type: ignore[assignment]
                f"/repos/{self.owner}/{self.repo}/commits",
                since=since,
                per_page=100,
                page=page,
            )
            if not batch:
                break
            summaries.extend(batch)
            if len(batch) < 100:
                break
            page += 1

        summaries = summaries[:max_commits]
        total = len(summaries)

        # 2. Fetch full detail (stats + file patches) for each commit.
        records: list[dict] = []
        for i, summary in enumerate(summaries):
            if progress and i % 25 == 0:
                progress(f"Fetching commit details… {i}/{total}")

            sha: str = summary["sha"]
            try:
                detail: dict = self._get(  # type: ignore[assignment]
                    f"/repos/{self.owner}/{self.repo}/commits/{sha}"
                )
            except Exception:
                continue

            commit_meta: dict = detail.get("commit") or {}
            author_meta: dict = commit_meta.get("author") or {}
            files: list[dict] = detail.get("files") or []
            stats: dict = detail.get("stats") or {}

            records.append(
                {
                    "commit_hash": sha,
                    "author": author_meta.get("name") or "unknown",
                    "timestamp": author_meta.get("date") or "",
                    "message": (commit_meta.get("message") or "").strip(),
                    "files_changed": [f["filename"] for f in files],
                    "lines_added": int(stats.get("additions", 0)),
                    "lines_deleted": int(stats.get("deletions", 0)),
                    # Patches are included in the per-commit detail response.
                    "diff_text": "\n\n".join(
                        f.get("patch", "") for f in files if f.get("patch")
                    ),
                }
            )
            # Small sleep to stay well within GitHub's secondary rate limits.
            time.sleep(0.05)

        if progress:
            progress(f"Fetched {len(records)} commits. Running analysis…")

        return records


def parse_github_url(repo_url: str) -> tuple[str, str] | None:
    """Return (owner, repo) from a GitHub URL, or None if it is not one."""
    m = re.match(
        r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$",
        repo_url.strip(),
    )
    return (m.group(1), m.group(2)) if m else None
