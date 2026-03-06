from __future__ import annotations

import networkx as nx


def compute_centrality(graph: nx.DiGraph) -> dict[str, float]:
    if graph.number_of_nodes() == 0:
        return {}

    undirected = graph.to_undirected()
    return nx.degree_centrality(undirected)
