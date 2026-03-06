from __future__ import annotations

from ingestion.commit_parser import CommitRecord
from analysis.semantic_commit import SemanticCommit, classify_semantic_commit


def classify_commit(commit: CommitRecord) -> SemanticCommit:
    return classify_semantic_commit(
        message=commit.message,
        changed_files=commit.files_changed,
        lines_added=commit.lines_added,
        lines_deleted=commit.lines_deleted,
    )
