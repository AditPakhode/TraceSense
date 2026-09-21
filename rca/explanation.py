import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import networkx as nx

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rca.dependency_graph import find_causal_paths


def format_causal_chain(path: List[str]) -> str:
    """Format a list of nodes as a vertical arrow chain."""
    return "\n    |\n    v\n".join(path)


def explain_results(
    graph: nx.DiGraph,
    ranked_results: List[Dict[str, Any]],
    top_n: int = 1,
) -> str:
    """Generate deterministic, interpretable root cause explanation from graph and anomaly metrics."""
    if not ranked_results:
        return "No anomalies detected. System operating within normal parameters."

    top_candidate = ranked_results[0]
    candidate_name = top_candidate["service"]
    in_graph = top_candidate.get("in_graph", candidate_name in graph)
    timestamp = top_candidate.get("timestamp", "N/A")
    temporal_score = top_candidate.get("temporal_score", 0.0)
    downstream_anomalies = top_candidate.get("downstream_anomalies", [])
    coverage_score = top_candidate.get("coverage_score", 0.0)
    anomaly_score = top_candidate.get("anomaly_score", 0.0)
    metric = top_candidate.get("metric", "general")

    lines = [
        f"Root Cause Candidate: {candidate_name}",
        "",
        "Evidence:",
    ]

    # Timestamp & temporal evidence
    time_part = timestamp.split("T")[-1] if "T" in timestamp else timestamp
    if temporal_score >= 0.999:
        lines.append(f"- Earliest anomaly detected at {time_part} (temporal score: {temporal_score:.2f})")
    else:
        lines.append(f"- Anomaly detected at {time_part} (temporal decay score: {temporal_score:.2f})")

    # Topology and downstream evidence
    if not in_graph:
        lines.append("- Service is not present in dependency graph (topology analysis unavailable)")
    else:
        num_downstream = len(downstream_anomalies)
        lines.append(f"- {num_downstream} anomalous services occur downstream")
        coverage_pct = int(round(coverage_score * 100))
        lines.append(f"- Explains {coverage_pct}% of observed anomalous services")

    # Anomaly strength
    lines.append(f"- Anomaly score: {anomaly_score:.2f} ({metric})")

    # Causal chain
    lines.append("")
    lines.append("Causal chain:")
    lines.append("")

    if not in_graph:
        lines.append(f"{candidate_name} (unmapped service)")
    elif not downstream_anomalies:
        lines.append(f"{candidate_name} (isolated or leaf service, no downstream anomalies)")
    else:
        # Find path to the furthest downstream anomalous service
        all_paths = find_causal_paths(graph, candidate_name, downstream_anomalies)
        if all_paths:
            # Pick the longest path that covers the most downstream services
            longest_path = max(all_paths, key=lambda p: (len(p), len(set(p).intersection(downstream_anomalies))))
            lines.append(format_causal_chain(longest_path))
        else:
            lines.append(candidate_name)

    return "\n".join(lines)
