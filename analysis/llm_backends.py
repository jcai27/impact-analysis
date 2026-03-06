from __future__ import annotations

import json
import os
from typing import Any

from analysis.semantic_commit import COMMIT_TYPES, SemanticCommit
from analysis.semantic_engine import LLMBackend


class NoOpLLMBackend(LLMBackend):
    """Default backend used when no LLM provider is configured."""


class OpenAIJSONBackend(LLMBackend):
    """
    Optional OpenAI backend.

    This is lazy-imported and only used when explicitly enabled.
    It returns None on provider/decode errors so the engine can safely fallback.
    """

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.getenv("IMPACT_LLM_MODEL", "gpt-4.1-mini")
        self.api_key = os.getenv("OPENAI_API_KEY")

    def classify(
        self,
        *,
        message: str,
        changed_files: list[str],
        lines_added: int,
        lines_deleted: int,
        diff_text: str,
    ) -> SemanticCommit | None:
        if not self.api_key:
            return None

        # Optional dependency: import only when this backend is used.
        try:
            from openai import OpenAI
        except Exception:
            return None

        prompt = (
            "Classify the git commit into JSON with fields: "
            "type, complexity, area, description, confidence. "
            "Allowed types: feature, bugfix, refactor, tests, docs, infrastructure.\n\n"
            f"Message: {message}\n"
            f"Changed files: {changed_files}\n"
            f"Lines added: {lines_added}, Lines deleted: {lines_deleted}\n"
            f"Diff (truncated): {diff_text[:12000]}"
        )

        try:
            client = OpenAI(api_key=self.api_key)
            resp = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            text = resp.choices[0].message.content or ""
            obj: dict[str, Any] = json.loads(text)
        except Exception:
            return None

        commit_type = str(obj.get("type", "feature")).strip().lower()
        if commit_type not in COMMIT_TYPES:
            return None

        return SemanticCommit(
            type=commit_type,
            complexity=str(obj.get("complexity", "medium")).strip().lower(),
            area=str(obj.get("area", "unknown"))[:120],
            description=str(obj.get("description", message.split("\n", 1)[0]))[:280],
            confidence=float(obj.get("confidence", 0.7)),
            source="llm",
        )


def build_llm_backend() -> LLMBackend:
    provider = os.getenv("IMPACT_LLM_PROVIDER", "").strip().lower()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    # Auto-enable OpenAI when the key is present unless explicitly disabled.
    if provider == "openai" or (api_key and provider not in ("none", "noop")):
        return OpenAIJSONBackend()
    return NoOpLLMBackend()
