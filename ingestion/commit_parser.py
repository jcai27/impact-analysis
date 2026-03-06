from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from git import Commit, Repo


@dataclass
class CommitRecord:
    commit_hash: str
    author: str
    timestamp: datetime
    message: str
    files_changed: list[str]
    lines_added: int
    lines_deleted: int


def _files_changed(commit: Commit) -> list[str]:
    return list(commit.stats.files.keys())


def extract_commits(
    repo_path: str,
    rev: str = "HEAD",
    max_commits: int = 9999,
    since_days: int = 90,
) -> list[CommitRecord]:
    repo = Repo(repo_path)
    since_date = datetime.now(tz=timezone.utc) - timedelta(days=since_days)
    since_str = since_date.strftime("%Y-%m-%d")

    records: list[CommitRecord] = []

    for commit in repo.iter_commits(rev=rev, max_count=max_commits, after=since_str):
        stats_total: dict[str, Any] = commit.stats.total
        records.append(
            CommitRecord(
                commit_hash=commit.hexsha,
                author=getattr(commit.author, "name", "unknown") or "unknown",
                timestamp=commit.committed_datetime,
                message=commit.message.strip(),
                files_changed=_files_changed(commit),
                lines_added=int(stats_total.get("insertions", 0)),
                lines_deleted=int(stats_total.get("deletions", 0)),
            )
        )

    return records
