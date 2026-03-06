from __future__ import annotations

import ast
from pathlib import Path

import networkx as nx


def _module_from_path(root: Path, file_path: Path) -> str:
    rel = file_path.relative_to(root)
    no_suffix = rel.with_suffix("")
    return ".".join(no_suffix.parts)


def build_dependency_graph(repo_path: str) -> nx.DiGraph:
    root = Path(repo_path)
    graph = nx.DiGraph()

    for py_file in root.rglob("*.py"):
        if ".git" in py_file.parts:
            continue

        module = _module_from_path(root, py_file)
        graph.add_node(module)

        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    graph.add_edge(module, alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    graph.add_edge(module, node.module)

    return graph
