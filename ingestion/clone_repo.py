from __future__ import annotations

from pathlib import Path

from git import Repo


def clone_repo(repo_url: str, target_dir: str) -> str:
    target_path = Path(target_dir)
    if target_path.exists() and (target_path / ".git").exists():
        return str(target_path)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    Repo.clone_from(repo_url, str(target_path))
    return str(target_path)


def update_repo(target_dir: str) -> None:
    repo = Repo(target_dir)
    for remote in repo.remotes:
        remote.fetch(prune=True)
    try:
        repo.remotes.origin.pull()
    except Exception:
        # Pull can fail on detached HEAD or local-only repos; fetch is enough for analysis.
        pass
