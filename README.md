# git-impact-analyzer

MVP tool to analyze a Git repository and estimate engineer impact using commit metadata, diffs, semantic classification, and lightweight system-impact signals.

## What this MVP includes

- Git ingestion (`clone`, `update`)
- Commit and diff parsing
- Low-cost semantic commit analyzer (heuristic first, optional LLM hook later)
- Dependency graph + centrality
- Metric engine + final impact score
- SQLite persistence
- FastAPI endpoints
- CLI report generation

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run analysis from CLI:

```bash
python main.py analyze --repo-url https://github.com/pallets/flask.git --repo-dir /tmp/flask --max-commits 200
```

Serve API:

```bash
uvicorn api.server:app --reload
```

Run health check:

```bash
curl -s http://127.0.0.1:8000/health
```

Analyze via API:

```bash
curl -s -X POST http://127.0.0.1:8000/repo/analyze \
  -H "content-type: application/json" \
  -d '{"repo_url":"https://github.com/pallets/flask.git","repo_dir":"/tmp/flask","max_commits":100}'
```

## Notes

- Semantic analysis is hybrid by default:
  - `heuristic`: zero API cost.
  - `hybrid`: heuristic first, LLM only for low-confidence commits.
  - `llm`: always try LLM first, fallback to heuristic on errors.
- Configure with env vars:
  - `IMPACT_SEMANTIC_MODE=hybrid|heuristic|llm`
  - `IMPACT_SEMANTIC_CONFIDENCE_THRESHOLD=0.75`
  - `IMPACT_LLM_MAX_CALLS=100`
  - `IMPACT_DATA_DIR=data` (stores cached `/top5` payload at `latest_analysis.json`)
  - `IMPACT_LLM_PROVIDER=openai` (optional)
  - `IMPACT_LLM_MODEL=gpt-4.1-mini` (optional)
  - `OPENAI_API_KEY=...` (required only when provider is enabled)

## Low-Cost Semantic Strategy

1. Run heuristic classifier on every commit (free).
2. Send only uncertain commits (`confidence < threshold`) to LLM.
3. Cache/store semantic result in DB so re-runs avoid repeated LLM calls.

This keeps cost low now while preserving a clear upgrade path to full LLM mode later.

OpenAI SDK is included in `requirements.txt`; set `OPENAI_API_KEY` to enable LLM summaries.
