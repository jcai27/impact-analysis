from __future__ import annotations

from dataclasses import dataclass

from git import Commit, Repo
from git.diff import NULL_TREE
from unidiff import PatchSet


@dataclass
class FileDiffRecord:
    file: str
    added_lines: int
    removed_lines: int
    diff: str


def extract_commit_file_diffs(repo: Repo, commit: Commit) -> list[FileDiffRecord]:
    parent = commit.parents[0] if commit.parents else None
    if parent is None:
        raw = commit.diff(NULL_TREE, create_patch=True)
    else:
        raw = parent.diff(commit, create_patch=True)

    records: list[FileDiffRecord] = []
    for item in raw:
        patch_text = item.diff.decode("utf-8", errors="replace") if item.diff else ""
        if not patch_text:
            continue

        try:
            patch = PatchSet(patch_text)
            added = sum(hunk.added for f in patch for hunk in f)
            removed = sum(hunk.removed for f in patch for hunk in f)
        except Exception:
            added = 0
            removed = 0

        path = item.b_path or item.a_path or "unknown"
        records.append(FileDiffRecord(file=path, added_lines=added, removed_lines=removed, diff=patch_text))

    return records
