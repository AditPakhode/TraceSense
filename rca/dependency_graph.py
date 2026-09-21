"""Service Dependency Graph representation and topological query utilities using NetworkX.

Edges represent invocations: A -> B means service A calls service B.
Pipeline topology:
checkout-api -> cart-service -> inventory-service -> pricing-service -> promotion-service -> tax-service -> receipt-service
"""

from typing import Iterable, List, Set
import networkx as nx

SERVICES = [
    "checkout-api",
    "cart-service",
    "inventory-service",
    "pricing-service",
    "promotion-service",
    "tax-service",
    "receipt-service",
]

DEFAULT_EDGES = [
    ("checkout-api", "cart-service"),
    ("cart-service", "inventory-service"),
    ("inventory-service", "pricing-service"),
    ("pricing-service", "promotion-service"),
    ("promotion-service", "tax-service"),
    ("tax-service", "receipt-service"),
]


def build_default_graph() -> nx.DiGraph:
    """Build and return the default directed dependency graph for TraceSense."""
    graph = nx.DiGraph()
    graph.add_nodes_from(SERVICES)
    graph.add_edges_from(DEFAULT_EDGES)
    return graph


def get_ancestors(graph: nx.DiGraph, service: str) -> Set[str]:
    """Return all upstream services that directly or indirectly call this service."""
    if service not in graph:
        return set()
    return nx.ancestors(graph, service)


def get_descendants(graph: nx.DiGraph, service: str) -> Set[str]:
    """Return all downstream services that are called directly or indirectly by this service."""
    if service not in graph:
        return set()
    return nx.descendants(graph, service)


def has_path(graph: nx.DiGraph, source: str, target: str) -> bool:
    """Check if there is a directed path from source to target in the graph."""
    if source not in graph or target not in graph:
        return False
    return nx.has_path(graph, source, target)


def get_downstream_anomalies(
    graph: nx.DiGraph, candidate: str, anomalous_services: Iterable[str]
) -> Set[str]:
    """Return the set of anomalous services that lie strictly downstream of the candidate."""
    descendants = get_descendants(graph, candidate)
    return set(anomalous_services).intersection(descendants)


def find_causal_paths(
    graph: nx.DiGraph, candidate: str, target_services: Iterable[str]
) -> List[List[str]]:
    """Find all simple directed paths from candidate to the specified target services."""
    if candidate not in graph:
        return []
    paths: List[List[str]] = []
    for target in target_services:
        if target != candidate and target in graph and nx.has_path(graph, candidate, target):
            for path in nx.all_simple_paths(graph, candidate, target):
                paths.append(path)
    return paths


# Default global instance for backwards compatibility
G = build_default_graph()


if __name__ == "__main__":
    print("\nService Dependency Graph")
    print("------------------------")
    for s in G.nodes:
        dependencies = list(G.successors(s))
        if dependencies:
            print(f"{s} -> {dependencies}")