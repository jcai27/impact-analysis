from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CodeContext:
    module: str
    functions_changed: list[str]
    classes_changed: list[str]


def _parse_python_symbols(path: Path) -> tuple[list[str], list[str]]:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception:
        return [], []

    funcs: list[str] = []
    classes: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            funcs.append(node.name)
        elif isinstance(node, ast.AsyncFunctionDef):
            funcs.append(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
    return funcs, classes


def build_code_context(repo_path: str, changed_files: list[str]) -> list[CodeContext]:
    contexts: list[CodeContext] = []
    root = Path(repo_path)

    for relative in changed_files:
        p = root / relative
        module = relative.split("/")[0] if "/" in relative else relative
        funcs: list[str] = []
        classes: list[str] = []

        if p.exists() and p.suffix == ".py":
            funcs, classes = _parse_python_symbols(p)

        contexts.append(CodeContext(module=module, functions_changed=funcs[:20], classes_changed=classes[:20]))

    return contexts
