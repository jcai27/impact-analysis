from __future__ import annotations

import json
import sqlite3
from pathlib import Path


class Database:
    def __init__(self, db_path: str = "impact_analyzer.db") -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS engineers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL
                );

                CREATE TABLE IF NOT EXISTS commits (
                    commit_hash TEXT PRIMARY KEY,
                    author TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    message TEXT NOT NULL,
                    files_changed TEXT NOT NULL,
                    lines_added INTEGER NOT NULL,
                    lines_deleted INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS semantic_commits (
                    commit_hash TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    complexity TEXT NOT NULL,
                    area TEXT NOT NULL,
                    description TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    FOREIGN KEY (commit_hash) REFERENCES commits(commit_hash)
                );

                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    engineer TEXT NOT NULL,
                    metric_key TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    UNIQUE (engineer, metric_key)
                );
                """
            )

    def upsert_commit(self, row: dict) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO commits (commit_hash, author, timestamp, message, files_changed, lines_added, lines_deleted)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(commit_hash) DO UPDATE SET
                    author=excluded.author,
                    timestamp=excluded.timestamp,
                    message=excluded.message,
                    files_changed=excluded.files_changed,
                    lines_added=excluded.lines_added,
                    lines_deleted=excluded.lines_deleted
                """,
                (
                    row["commit_hash"],
                    row["author"],
                    row["timestamp"],
                    row["message"],
                    json.dumps(row.get("files_changed", [])),
                    row["lines_added"],
                    row["lines_deleted"],
                ),
            )

    def upsert_semantic(self, row: dict) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO semantic_commits (commit_hash, type, complexity, area, description, confidence)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(commit_hash) DO UPDATE SET
                    type=excluded.type,
                    complexity=excluded.complexity,
                    area=excluded.area,
                    description=excluded.description,
                    confidence=excluded.confidence
                """,
                (
                    row["commit_hash"],
                    row["type"],
                    row["complexity"],
                    row["area"],
                    row["description"],
                    row["confidence"],
                ),
            )

    def upsert_metric(self, engineer: str, metric_key: str, metric_value: float) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO metrics (engineer, metric_key, metric_value)
                VALUES (?, ?, ?)
                ON CONFLICT(engineer, metric_key) DO UPDATE SET
                    metric_value=excluded.metric_value
                """,
                (engineer, metric_key, metric_value),
            )

    def list_engineers(self) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute("SELECT DISTINCT author FROM commits ORDER BY author").fetchall()
            return [r[0] for r in rows]

    def get_engineer_metrics(self, engineer: str) -> dict[str, float]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT metric_key, metric_value FROM metrics WHERE engineer = ? ORDER BY metric_key",
                (engineer,),
            ).fetchall()
            return {r["metric_key"]: float(r["metric_value"]) for r in rows}

    def get_dashboard_data(self) -> dict:
        """Return all data needed to render the dashboard, aggregated per author."""
        from collections import Counter, defaultdict

        with self.connect() as conn:
            commit_rows = conn.execute(
                """
                SELECT c.author, c.commit_hash, c.timestamp,
                       sc.type, sc.complexity, sc.area, sc.description
                FROM commits c
                LEFT JOIN semantic_commits sc ON c.commit_hash = sc.commit_hash
                ORDER BY c.author, c.timestamp DESC
                """
            ).fetchall()

            metric_rows = conn.execute(
                "SELECT engineer, metric_key, metric_value FROM metrics"
            ).fetchall()

            date_row = conn.execute(
                "SELECT MIN(timestamp) as earliest, MAX(timestamp) as latest FROM commits"
            ).fetchone()

        author_data: dict = defaultdict(
            lambda: {
                "commits": 0,
                "types": Counter(),
                "complexities": Counter(),
                "areas": Counter(),
                "descriptions": [],
            }
        )

        for row in commit_rows:
            author = row["author"]
            author_data[author]["commits"] += 1
            if row["type"]:
                author_data[author]["types"][row["type"]] += 1
            if row["complexity"]:
                author_data[author]["complexities"][row["complexity"]] += 1
            if row["area"]:
                author_data[author]["areas"][row["area"]] += 1
            if row["description"] and len(author_data[author]["descriptions"]) < 20:
                author_data[author]["descriptions"].append(row["description"])

        author_stats: dict = {
            author: {
                "commits": data["commits"],
                "types": dict(data["types"]),
                "complexities": dict(data["complexities"]),
                "areas": dict(data["areas"]),
                "descriptions": data["descriptions"],
            }
            for author, data in author_data.items()
        }

        author_metrics: dict = defaultdict(dict)
        for row in metric_rows:
            author_metrics[row["engineer"]][row["metric_key"]] = float(row["metric_value"])

        return {
            "author_stats": author_stats,
            "author_metrics": dict(author_metrics),
            "date_range": {
                "earliest": date_row["earliest"] if date_row else None,
                "latest": date_row["latest"] if date_row else None,
            },
        }
