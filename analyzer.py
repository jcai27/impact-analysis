from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import timezone
from typing import Callable

from analysis.llm_backends import build_llm_backend
from analysis.semantic_engine import SemanticEngine, SemanticEngineConfig
from ingestion.clone_repo import clone_repo, update_repo
from ingestion.commit_parser import extract_commits
from ingestion.diff_parser import extract_commit_file_diffs
from ingestion.github_api import GitHubFetcher, parse_github_url
from metrics.feature_metrics import compute_feature_metrics
from metrics.impact_score import compute_impact_score
from metrics.maintenance_metrics import compute_maintenance_metrics
from metrics.ownership_metrics import compute_ownership_metrics
from storage.database import Database

try:
    from git import Repo as _GitRepo  # type: ignore[import-untyped]
except ImportError:
    _GitRepo = None  # type: ignore[assignment,misc]


class ImpactAnalyzer:
    def __init__(
        self,
        db_path: str = "impact_analyzer.db",
        *,
        semantic_mode: str = "hybrid",
        semantic_confidence_threshold: float = 0.75,
        llm_max_calls: int = 100,
    ) -> None:
        self.db = Database(db_path)
        self.db.init_schema()
        self.semantic_engine = SemanticEngine(
            config=SemanticEngineConfig(
                mode=semantic_mode,
                confidence_threshold=semantic_confidence_threshold,
                llm_max_calls=llm_max_calls,
            ),
            llm_backend=build_llm_backend(),
        )

    # ── Public entry point ────────────────────────────────────────────────────

    def analyze_repo(
        self,
        repo_url: str,
        repo_dir: str,
        max_commits: int = 500,
        since_days: int = 90,
        progress: Callable[[str], None] | None = None,
    ) -> dict:
        from config import settings

        github_pair = parse_github_url(repo_url)

        if github_pair and settings.github_token:
            # ── GitHub API path: no disk space required ──────────────────────
            owner, repo_name = github_pair
            fetcher = GitHubFetcher(owner, repo_name, token=settings.github_token)
            raw_records = fetcher.fetch_commit_records(
                since_days=since_days,
                max_commits=max_commits,
                progress=progress,
            )
        else:
            # ── Clone path ───────────────────────────────────────────────────
            if progress:
                progress("Cloning / updating repository…")
            clone_repo(repo_url, repo_dir, since_days=since_days)
            update_repo(repo_dir)
            raw_records = self._records_from_clone(repo_dir, max_commits, since_days)

        return self._analyze_records(raw_records, repo_url, since_days)

    # ── Clone-based record extraction ─────────────────────────────────────────

    def _records_from_clone(
        self, repo_dir: str, max_commits: int, since_days: int
    ) -> list[dict]:
        commits = extract_commits(repo_dir, max_commits=max_commits, since_days=since_days)
        repo = _GitRepo(repo_dir)
        records: list[dict] = []

        for commit in commits:
            git_commit = repo.commit(commit.commit_hash)
            file_diffs = extract_commit_file_diffs(repo, git_commit)
            diff_text = "\n\n".join(d.diff for d in file_diffs)
            records.append(
                {
                    "commit_hash": commit.commit_hash,
                    "author": commit.author,
                    "timestamp": commit.timestamp.astimezone(timezone.utc).isoformat(),
                    "message": commit.message,
                    "files_changed": commit.files_changed,
                    "lines_added": commit.lines_added,
                    "lines_deleted": commit.lines_deleted,
                    "diff_text": diff_text,
                }
            )

        return records

    # ── Shared analysis pipeline ──────────────────────────────────────────────

    def _analyze_records(
        self, raw_records: list[dict], repo_url: str, since_days: int
    ) -> dict:
        semantic_rows: list[dict] = []

        for record in raw_records:
            semantic = self.semantic_engine.classify(
                message=record["message"],
                changed_files=record["files_changed"],
                lines_added=record["lines_added"],
                lines_deleted=record["lines_deleted"],
                diff_text=record.get("diff_text", ""),
            )

            commit_row = {
                "commit_hash": record["commit_hash"],
                "author": record["author"],
                "timestamp": record["timestamp"],
                "message": record["message"],
                "files_changed": record["files_changed"],
                "lines_added": record["lines_added"],
                "lines_deleted": record["lines_deleted"],
            }
            semantic_row = {
                "commit_hash": record["commit_hash"],
                "author": record["author"],
                **asdict(semantic),
            }

            self.db.upsert_commit(commit_row)
            self.db.upsert_semantic({k: v for k, v in semantic_row.items() if k != "author"})
            semantic_rows.append(semantic_row)

        # Centrality: files touched more often by more commits are more "central".
        # This works for any language (replaces the Python-only import graph).
        file_touch_counts: Counter[str] = Counter()
        for r in raw_records:
            for f in r["files_changed"]:
                file_touch_counts[f] += 1
        max_touches = max(file_touch_counts.values(), default=1)
        centrality: dict[str, float] = {
            f: c / max_touches for f, c in file_touch_counts.items()
        }

        commit_rows = [{"author": r["author"], "files_changed": r["files_changed"]} for r in raw_records]

        feature = compute_feature_metrics(semantic_rows)
        ownership = compute_ownership_metrics(commit_rows)
        maintenance = compute_maintenance_metrics(semantic_rows)

        # Per-author centrality: mean centrality of all files touched.
        centrality_by_author: dict[str, float] = defaultdict(float)
        touched_counts: dict[str, int] = defaultdict(int)
        for r in raw_records:
            for f in r["files_changed"]:
                centrality_by_author[r["author"]] += centrality.get(f, 0.0)
                touched_counts[r["author"]] += 1

        # Collaboration: unique co-contributors on shared files, normalized.
        file_authors: dict[str, set[str]] = defaultdict(set)
        author_files: dict[str, set[str]] = defaultdict(set)
        for r in raw_records:
            for f in r["files_changed"]:
                file_authors[f].add(r["author"])
                author_files[r["author"]].add(f)

        author_co_contributors: dict[str, set[str]] = defaultdict(set)
        for author, files in author_files.items():
            for f in files:
                for other in file_authors[f]:
                    if other != author:
                        author_co_contributors[author].add(other)

        max_co = max((len(v) for v in author_co_contributors.values()), default=1) or 1
        collaboration_scores: dict[str, float] = {
            a: len(v) / max_co for a, v in author_co_contributors.items()
        }

        engineer_scores: dict[str, dict] = {}
        all_authors = {r["author"] for r in raw_records}

        for author in all_authors:
            feature_delivery = float(feature.get(author, {}).get("feature_complexity", 0.0))
            system_impact = (
                centrality_by_author[author] / touched_counts[author]
                if touched_counts[author]
                else 0.0
            )
            ownership_score = float(ownership.get(author, {}).get("avg_module_ownership", 0.0))
            maint = maintenance.get(author, {})
            maintenance_score = float(
                maint.get("bugfixes", 0) * 1.0
                + maint.get("refactors", 0) * 0.7
                + maint.get("tests", 0) * 0.5
                + maint.get("docs", 0) * 0.2
            )
            collaboration = collaboration_scores.get(author, 0.0)

            impact = compute_impact_score(
                feature_delivery=feature_delivery,
                system_impact=system_impact,
                ownership=ownership_score,
                maintenance=maintenance_score,
                collaboration=collaboration,
            )

            self.db.upsert_metric(author, "impact_score", impact)
            self.db.upsert_metric(author, "feature_delivery", feature_delivery)
            self.db.upsert_metric(author, "system_impact", system_impact)
            self.db.upsert_metric(author, "ownership", ownership_score)
            self.db.upsert_metric(author, "maintenance", maintenance_score)
            self.db.upsert_metric(author, "collaboration", collaboration)

            engineer_scores[author] = {
                "impact_score": impact,
                "features": feature.get(author, {}).get("features", 0),
                "bugfixes": maint.get("bugfixes", 0),
                "refactors": maint.get("refactors", 0),
                "primary_subsystems": feature.get(author, {}).get("subsystems_touched", 0),
                "collaboration": collaboration,
            }

        return {
            "repo_url": repo_url,
            "commit_count": len(raw_records),
            "since_days": since_days,
            "semantic_mode": self.semantic_engine.config.mode,
            "semantic_llm_calls": self.semantic_engine.llm_calls,
            "semantic_llm_successes": self.semantic_engine.llm_successes,
            "engineers": engineer_scores,
        }
