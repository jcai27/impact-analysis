from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Engineer:
    name: str


@dataclass
class CommitRow:
    commit_hash: str
    author: str
    timestamp: datetime
    message: str
    lines_added: int
    lines_deleted: int


@dataclass
class SemanticCommitRow:
    commit_hash: str
    commit_type: str
    complexity: str
    area: str
    description: str
    confidence: float
