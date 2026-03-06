from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from analyzer import ImpactAnalyzer
from config import settings

router = APIRouter()

DIMENSION_KEYS = ["feature_delivery", "system_impact", "ownership", "maintenance", "collaboration"]


# ── Background analysis state ─────────────────────────────────────────────────

@dataclass
class AnalysisState:
    status: Literal["idle", "running", "done", "error"] = "idle"
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    commit_count: int = 0
    message: str = ""


_state = AnalysisState()
_lock = threading.Lock()

# LLM-generated summaries cached between requests; cleared on new analysis.
_summaries: dict[str, list[str]] = {}


def _run_analysis() -> None:
    global _state
    try:
        analyzer = ImpactAnalyzer(
            db_path=settings.db_path,
            semantic_mode=settings.semantic_mode,
            semantic_confidence_threshold=settings.semantic_confidence_threshold,
            llm_max_calls=settings.llm_max_calls,
        )

        def _progress(msg: str) -> None:
            _state.message = msg

        result = analyzer.analyze_repo(
            repo_url=settings.repo_url,
            repo_dir=settings.repo_dir,
            max_commits=settings.default_max_commits,
            since_days=settings.default_since_days,
            progress=_progress,
        )
        _state.commit_count = result["commit_count"]
        _state.status = "done"
        _state.finished_at = datetime.now(timezone.utc).isoformat()
        _state.message = f"Analysis complete — {result['commit_count']} commits processed."
    except Exception as exc:
        _state.status = "error"
        _state.finished_at = datetime.now(timezone.utc).isoformat()
        _state.error = str(exc)
        _state.message = f"Error: {exc}"


# ── Bot detection ─────────────────────────────────────────────────────────────

def _is_bot(name: str) -> bool:
    lower = name.lower()
    return (
        "[bot]" in lower
        or lower.endswith("-bot")
        or "github-actions" in lower
        or lower in {"dependabot", "renovate", "snyk-bot", "codecov-commenter"}
    )


# ── LLM summaries ─────────────────────────────────────────────────────────────

def _generate_llm_summaries(
    engineers: list[dict],
    author_stats: dict,
) -> dict[str, list[str]]:
    """Call OpenAI to generate rich per-engineer bullet summaries.

    Returns a dict mapping engineer name → list of bullet strings.
    Falls back gracefully to an empty dict on any error.
    """
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {}

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
    except Exception:
        return {}

    model = os.getenv("IMPACT_LLM_MODEL", "gpt-4.1-mini")
    summaries: dict[str, list[str]] = {}

    for eng in engineers:
        name = eng["name"]
        stats = eng["stats"]
        top_areas = eng["top_areas"]
        descriptions = author_stats.get(name, {}).get("descriptions", [])

        commits_text = "\n".join(
            f"- {d}" for d in descriptions[:20] if d and d.strip()
        )
        if not commits_text:
            continue

        prompt = (
            "You are writing for an engineering leadership dashboard at PostHog.\n\n"
            f"Engineer: {name}\n"
            f"Last 90 days: {stats['commits']} commits — "
            f"{stats['features']} features, {stats['bugfixes']} bug fixes, "
            f"{stats['refactors']} refactors, {stats['tests']} tests written\n"
            f"Key areas: {', '.join(top_areas) if top_areas else 'various'}\n\n"
            f"Recent commit messages:\n{commits_text}\n\n"
            "Write exactly 3 bullet points (start each line with •) describing what "
            "this engineer accomplished. Be specific about what they built or fixed based "
            "on the commits above. Focus on technical and business impact. "
            "Each bullet is one sentence, max 110 characters. Plain text only."
        )

        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=220,
                temperature=0.3,
            )
            text = (resp.choices[0].message.content or "").strip()
            bullets = [
                line.lstrip("•·- ").strip()
                for line in text.splitlines()
                if line.strip() and not line.strip().startswith("#")
            ][:3]
            if bullets:
                summaries[name] = bullets
        except Exception:
            pass

    return summaries


# ── Heuristic highlights fallback ─────────────────────────────────────────────

def _generate_highlights(
    stats: dict,
    types: dict,
    complexities: dict,
    normalized_radar: dict,
    top_areas: list[str],
) -> list[str]:
    highlights: list[str] = []

    features = types.get("feature", 0)
    high_complex = complexities.get("high", 0)
    bugfixes = types.get("bugfix", 0)
    refactors = types.get("refactor", 0)

    if features > 0:
        if high_complex > 0:
            highlights.append(f"Shipped {features} features — {high_complex} high-complexity")
        else:
            highlights.append(f"Shipped {features} new features")

    if bugfixes > 0:
        highlights.append(f"Resolved {bugfixes} bug{'s' if bugfixes > 1 else ''}, improving stability")

    if refactors > 0 and not bugfixes:
        highlights.append(f"Drove {refactors} refactor{'s' if refactors > 1 else ''}, reducing tech debt")

    if normalized_radar.get("ownership", 0) >= 65 and top_areas:
        highlights.append(f"Deep ownership in {', '.join(top_areas[:2])}")

    if normalized_radar.get("system_impact", 0) >= 65:
        highlights.append("Touched high-centrality, cross-cutting code")

    if normalized_radar.get("collaboration", 0) >= 65:
        highlights.append("Strong cross-team collaborator")

    if not highlights:
        commits = stats.get("commits", 0)
        highlights.append(f"Contributed {commits} commits across {len(top_areas)} areas")

    return highlights[:3]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/status")
def analysis_status() -> dict:
    return {
        "status": _state.status,
        "started_at": _state.started_at,
        "finished_at": _state.finished_at,
        "commit_count": _state.commit_count,
        "message": _state.message,
        "error": _state.error,
    }


@router.post("/analyze/trigger")
def trigger_analysis() -> dict:
    global _state, _summaries

    with _lock:
        if _state.status == "running":
            return {"queued": False, "message": "Analysis already running."}

        _state = AnalysisState(
            status="running",
            started_at=datetime.now(timezone.utc).isoformat(),
            message="Starting analysis…",
        )
        _summaries = {}  # invalidate cached summaries on new analysis

    t = threading.Thread(target=_run_analysis, daemon=True)
    t.start()

    return {"queued": True, "message": "Analysis started."}


@router.post("/repo/analyze")
def analyze_repo(payload: "AnalyzeRequest") -> dict:
    analyzer = ImpactAnalyzer(
        db_path=payload.db_path,
        semantic_mode=payload.semantic_mode,
        semantic_confidence_threshold=payload.semantic_threshold,
        llm_max_calls=payload.llm_max_calls,
    )
    return analyzer.analyze_repo(
        repo_url=payload.repo_url,
        repo_dir=payload.repo_dir,
        max_commits=payload.max_commits,
        since_days=payload.since_days,
    )


@router.get("/engineers")
def list_engineers(db_path: str = settings.db_path) -> dict:
    analyzer = ImpactAnalyzer(db_path=db_path)
    return {"engineers": analyzer.db.list_engineers()}


@router.get("/engineer/{name}")
def engineer_detail(name: str, db_path: str = settings.db_path) -> dict:
    analyzer = ImpactAnalyzer(db_path=db_path)
    return {"engineer": name, "metrics": analyzer.db.get_engineer_metrics(name)}


@router.get("/metrics")
def metrics(db_path: str = settings.db_path) -> dict:
    analyzer = ImpactAnalyzer(db_path=db_path)
    engineers = analyzer.db.list_engineers()
    return {"metrics": {name: analyzer.db.get_engineer_metrics(name) for name in engineers}}


@router.get("/top5")
def top5_engineers(db_path: str = settings.db_path) -> dict:
    global _summaries

    analyzer = ImpactAnalyzer(db_path=db_path)
    data = analyzer.db.get_dashboard_data()

    author_metrics = data["author_metrics"]
    author_stats = data["author_stats"]
    date_range = data["date_range"]

    if not author_metrics:
        raise HTTPException(status_code=404, detail="No analysis data found. Run analysis first.")

    # Filter bots before ranking.
    human_metrics = {n: m for n, m in author_metrics.items() if not _is_bot(n)}

    ranked = sorted(
        human_metrics.items(),
        key=lambda kv: kv[1].get("impact_score", 0.0),
        reverse=True,
    )[:5]

    max_vals: dict[str, float] = {
        k: max((m.get(k, 0.0) for _, m in human_metrics.items()), default=1.0) or 1.0
        for k in DIMENSION_KEYS
    }
    max_impact = max(m.get("impact_score", 0.0) for _, m in human_metrics.items()) or 1.0

    engineers = []
    for rank, (name, eng_metrics) in enumerate(ranked, start=1):
        stats = author_stats.get(name, {})
        types = stats.get("types", {})
        complexities = stats.get("complexities", {})
        areas = stats.get("areas", {})

        top_areas = [
            area
            for area, _ in sorted(areas.items(), key=lambda x: x[1], reverse=True)
            if area and area not in ("unknown", "")
        ][:4]

        raw_scores = {k: eng_metrics.get(k, 0.0) for k in DIMENSION_KEYS}
        normalized_radar = {k: round(raw_scores[k] / max_vals[k] * 100) for k in DIMENSION_KEYS}

        engineers.append(
            {
                "rank": rank,
                "name": name,
                "impact_score": round(eng_metrics.get("impact_score", 0.0), 3),
                "display_score": round(eng_metrics.get("impact_score", 0.0) / max_impact * 10, 1),
                "radar": normalized_radar,
                "stats": {
                    "commits": stats.get("commits", 0),
                    "features": types.get("feature", 0),
                    "bugfixes": types.get("bugfix", 0),
                    "refactors": types.get("refactor", 0),
                    "tests": types.get("tests", 0),
                    "docs": types.get("docs", 0),
                    "infrastructure": types.get("infrastructure", 0),
                    "high_complexity": complexities.get("high", 0),
                },
                "top_areas": top_areas,
                # Heuristic highlights as baseline; replaced below if LLM succeeds.
                "highlights": _generate_highlights(
                    stats, types, complexities, normalized_radar, top_areas
                ),
                "summary_source": "heuristic",
            }
        )

    # Generate LLM summaries for engineers not yet cached.
    need_summaries = [e for e in engineers if e["name"] not in _summaries]
    if need_summaries:
        new = _generate_llm_summaries(need_summaries, author_stats)
        _summaries.update(new)

    # Attach cached LLM summaries (overwrite heuristic highlights when available).
    for eng in engineers:
        llm_bullets = _summaries.get(eng["name"])
        if llm_bullets:
            eng["highlights"] = llm_bullets
            eng["summary_source"] = "llm"

    total_commits = sum(s.get("commits", 0) for s in author_stats.values())

    return {
        "meta": {
            "commit_count": total_commits,
            "engineer_count": len(human_metrics),
            "date_range": date_range,
        },
        "engineers": engineers,
    }


class AnalyzeRequest(BaseModel):
    repo_url: str = Field(..., description="Repository clone URL")
    repo_dir: str = Field(..., description="Local path to clone/update repo")
    max_commits: int = Field(default=9999, ge=1, le=99999)
    since_days: int = Field(default=90, ge=1, le=3650)
    db_path: str = Field(default=settings.db_path)
    semantic_mode: str = Field(default="hybrid", pattern="^(heuristic|hybrid|llm)$")
    semantic_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    llm_max_calls: int = Field(default=100, ge=0, le=10000)
