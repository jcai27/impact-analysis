from __future__ import annotations

from dataclasses import dataclass

from analysis.semantic_commit import COMMIT_TYPES, SemanticCommit, classify_semantic_commit


@dataclass(frozen=True)
class SemanticEngineConfig:
    mode: str = "hybrid"  # heuristic | hybrid | llm
    confidence_threshold: float = 0.75
    llm_max_calls: int = 100


class LLMBackend:
    def classify(
        self,
        *,
        message: str,
        changed_files: list[str],
        lines_added: int,
        lines_deleted: int,
        diff_text: str,
    ) -> SemanticCommit | None:
        return None


class SemanticEngine:
    def __init__(self, config: SemanticEngineConfig | None = None, llm_backend: LLMBackend | None = None) -> None:
        self.config = config or SemanticEngineConfig()
        self.llm_backend = llm_backend or LLMBackend()
        self.llm_calls = 0
        self.llm_successes = 0

    def _validate_llm_result(self, result: SemanticCommit | None) -> SemanticCommit | None:
        if result is None:
            return None
        if result.type not in COMMIT_TYPES:
            return None
        return result

    def _try_llm(
        self,
        *,
        message: str,
        changed_files: list[str],
        lines_added: int,
        lines_deleted: int,
        diff_text: str,
    ) -> SemanticCommit | None:
        if self.llm_calls >= self.config.llm_max_calls:
            return None

        self.llm_calls += 1
        llm_result = self.llm_backend.classify(
            message=message,
            changed_files=changed_files,
            lines_added=lines_added,
            lines_deleted=lines_deleted,
            diff_text=diff_text,
        )
        llm_result = self._validate_llm_result(llm_result)
        if llm_result is not None:
            self.llm_successes += 1
        return llm_result

    def classify(
        self,
        *,
        message: str,
        changed_files: list[str],
        lines_added: int,
        lines_deleted: int,
        diff_text: str,
    ) -> SemanticCommit:
        heuristic = classify_semantic_commit(
            message=message,
            changed_files=changed_files,
            lines_added=lines_added,
            lines_deleted=lines_deleted,
        )

        mode = self.config.mode.lower().strip()

        if mode == "heuristic":
            return heuristic

        if mode == "llm":
            llm_only = self._try_llm(
                message=message,
                changed_files=changed_files,
                lines_added=lines_added,
                lines_deleted=lines_deleted,
                diff_text=diff_text,
            )
            return llm_only or heuristic

        # Hybrid default: only use LLM for uncertain heuristic classifications.
        if heuristic.confidence < self.config.confidence_threshold:
            llm_result = self._try_llm(
                message=message,
                changed_files=changed_files,
                lines_added=lines_added,
                lines_deleted=lines_deleted,
                diff_text=diff_text,
            )
            if llm_result is not None:
                return llm_result

        return heuristic
