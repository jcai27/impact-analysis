from __future__ import annotations

import argparse
import json

from analyzer import ImpactAnalyzer
from config import settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Git Impact Analyzer MVP")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="Analyze a repository")
    analyze.add_argument("--repo-url", required=True, help="Git repository URL")
    analyze.add_argument("--repo-dir", required=True, help="Local clone directory")
    analyze.add_argument(
        "--max-commits",
        type=int,
        default=settings.default_max_commits,
        help="Maximum commits to analyze",
    )
    analyze.add_argument(
        "--since-days",
        type=int,
        default=settings.default_since_days,
        help="Include commits from the last N days (default: 90)",
    )
    analyze.add_argument("--db-path", default="impact_analyzer.db", help="SQLite DB path")
    analyze.add_argument(
        "--semantic-mode",
        default=settings.semantic_mode,
        choices=["heuristic", "hybrid", "llm"],
        help="Semantic classifier mode",
    )
    analyze.add_argument(
        "--semantic-threshold",
        type=float,
        default=settings.semantic_confidence_threshold,
        help="Confidence threshold used in hybrid mode",
    )
    analyze.add_argument(
        "--llm-max-calls",
        type=int,
        default=settings.llm_max_calls,
        help="Maximum LLM calls per analysis run",
    )

    return parser


def format_report(result: dict) -> str:
    lines = ["Engineer Report", ""]

    ranked = sorted(
        result["engineers"].items(),
        key=lambda kv: kv[1].get("impact_score", 0.0),
        reverse=True,
    )

    for name, stats in ranked:
        lines.append(name)
        lines.append(f"Impact score: {stats.get('impact_score', 0.0)}")
        lines.append(f"Features: {stats.get('features', 0)}")
        lines.append(f"Bug fixes: {stats.get('bugfixes', 0)}")
        lines.append(f"Refactors: {stats.get('refactors', 0)}")
        lines.append(f"Subsystems touched: {stats.get('primary_subsystems', 0)}")
        lines.append(f"Collaboration: {stats.get('collaboration', 0.0):.2f}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "analyze":
        analyzer = ImpactAnalyzer(
            db_path=args.db_path,
            semantic_mode=args.semantic_mode,
            semantic_confidence_threshold=args.semantic_threshold,
            llm_max_calls=args.llm_max_calls,
        )
        result = analyzer.analyze_repo(
            repo_url=args.repo_url,
            repo_dir=args.repo_dir,
            max_commits=args.max_commits,
            since_days=args.since_days,
        )
        print(format_report(result))
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
