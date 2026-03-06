from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import timezone

from git import Repo

from analysis.llm_backends import build_llm_backend
from analysis.semantic_engine import SemanticEngine, SemanticEngineConfig
from graph.centrality_analysis import compute_centrality
from graph.dependency_graph import build_dependency_graph
from ingestion.clone_repo import clone_repo, update_repo
from ingestion.commit_parser import extract_commits
from ingestion.diff_parser import extract_commit_file_diffs
from metrics.feature_metrics import compute_feature_metrics
from metrics.impact_score import compute_impact_score
from metrics.maintenance_metrics import compute_maintenance_metrics
from metrics.ownership_metrics import compute_ownership_metrics
from storage.database import Database


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

    def analyze_repo(
        self,
        repo_url: str,
        repo_dir: str,
        max_commits: int = 500,
        since_days: int = 90,
    ) -> dict:
        clone_repo(repo_url, repo_dir)
        update_repo(repo_dir)

        commits = extract_commits(repo_dir, max_commits=max_commits, since_days=since_days)
        repo = Repo(repo_dir)
        semantic_rows: list[dict] = []
        total_diff_files = 0

        for commit in commits:
            git_commit = repo.commit(commit.commit_hash)
            file_diffs = extract_commit_file_diffs(repo, git_commit)
            diff_text = "\n\n".join(d.diff for d in file_diffs)
            semantic = self.semantic_engine.classify(
                message=commit.message,
                changed_files=commit.files_changed,
                lines_added=commit.lines_added,
                lines_deleted=commit.lines_deleted,
                diff_text=diff_text,
            )
            total_diff_files += len(file_diffs)
            commit_row = {
                "commit_hash": commit.commit_hash,
                "author": commit.author,
                "timestamp": commit.timestamp.astimezone(timezone.utc).isoformat(),
                "message": commit.message,
                "files_changed": commit.files_changed,
                "lines_added": commit.lines_added,
                "lines_deleted": commit.lines_deleted,
            }
            semantic_row = {
                "commit_hash": commit.commit_hash,
                "author": commit.author,
                **asdict(semantic),
            }

            self.db.upsert_commit(commit_row)
            self.db.upsert_semantic({k: v for k, v in semantic_row.items() if k != "author"})
            semantic_rows.append(semantic_row)

        graph = build_dependency_graph(repo_dir)
        centrality = compute_centrality(graph)

        commit_rows = [
            {
                "author": c.author,
                "files_changed": c.files_changed,
            }
            for c in commits
        ]

        feature = compute_feature_metrics(semantic_rows)
        ownership = compute_ownership_metrics(commit_rows)
        maintenance = compute_maintenance_metrics(semantic_rows)

        centrality_by_author: dict[str, float] = defaultdict(float)
        touched_counts: dict[str, int] = defaultdict(int)

        for c in commits:
            for file_path in c.files_changed:
                mod = file_path.replace("/", ".").rsplit(".", 1)[0]
                centrality_by_author[c.author] += centrality.get(mod, 0.0)
                touched_counts[c.author] += 1

        # Compute collaboration: fraction of co-contributors on shared files,
        # normalized to [0, 1] across all authors.
        file_authors: dict[str, set[str]] = defaultdict(set)
        author_files: dict[str, set[str]] = defaultdict(set)
        for c in commits:
            for f in c.files_changed:
                file_authors[f].add(c.author)
                author_files[c.author].add(f)

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
        for author in {c.author for c in commits}:
            feature_delivery = float(feature.get(author, {}).get("feature_complexity", 0.0))
            system_impact = (
                centrality_by_author[author] / touched_counts[author] if touched_counts[author] else 0.0
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
                "bugfixes": maintenance.get(author, {}).get("bugfixes", 0),
                "refactors": maintenance.get(author, {}).get("refactors", 0),
                "primary_subsystems": feature.get(author, {}).get("subsystems_touched", 0),
                "collaboration": collaboration,
            }

        return {
            "repo_url": repo_url,
            "repo_dir": repo_dir,
            "commit_count": len(commits),
            "since_days": since_days,
            "parsed_diff_files": total_diff_files,
            "semantic_mode": self.semantic_engine.config.mode,
            "semantic_llm_calls": self.semantic_engine.llm_calls,
            "semantic_llm_successes": self.semantic_engine.llm_successes,
            "engineers": engineer_scores,
        }
