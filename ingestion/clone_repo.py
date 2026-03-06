from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from git import Repo


def clone_repo(repo_url: str, target_dir: str, since_days: int = 90) -> str:
    target_path = Path(target_dir)
    if target_path.exists() and (target_path / ".git").exists():
        return str(target_path)

    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Shallow clone: only fetch commits within the analysis window plus a small
    # buffer. Combined with --single-branch this keeps the clone tiny (~50-200 MB
    # for large monorepos vs multiple GB for a full clone).
    since_date = datetime.now(tz=timezone.utc) - timedelta(days=since_days + 7)
    since_str = since_date.strftime("%Y-%m-%d")

    Repo.clone_from(
        repo_url,
        str(target_path),
        shallow_since=since_str,
        single_branch=True,
    )
    return str(target_path)


def update_repo(target_dir: str) -> None:
    repo = Repo(target_dir)
    for remote in repo.remotes:
        try:
            # --update-shallow extends the shallow boundary when pulling new commits.
            remote.fetch(prune=True, update_shallow=True)
        except Exception:
            pass
    try:
        repo.remotes.origin.pull(update_shallow=True)
    except Exception:
        # Pull can fail on detached HEAD or local-only repos; fetch is enough.
        pass
