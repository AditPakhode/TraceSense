#!/usr/bin/env python3
"""TraceSense RCA Demonstration Script.

Demonstrates:
1. Loading the dependency graph
2. Loading synthetic anomaly events for Incident INC001
3. Running TraceSense Causal RCA engine
4. Running Baseline 1 (Highest Anomaly Score) and Baseline 2 (Earliest Anomaly)
5. Printing ranked candidate breakdown
6. Printing interpretable evidence and causal chain
7. Comparing results across all 3 methods
"""

import sys
from pathlib import Path
import pandas as pd

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rca.baselines import predict_earliest_timestamp, predict_highest_score
from rca.causal_engine import CausalRCA
from rca.dependency_graph import build_default_graph


# Ensure UTF-8 stdout if possible
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run_demo(incident_id: str = "INC001", csv_path: str = "ml/anomaly_results.csv") -> None:
    csv_file = Path(csv_path)
    if not csv_file.exists():
        # Fallback to absolute or generate
        from ml.generate_sample_anomalies import generate
        generate()

    df = pd.read_csv(csv_file)
    incident_df = df[df["incident_id"] == incident_id]
    if incident_df.empty:
        print(f"Error: No anomaly records found for incident '{incident_id}'.")
        return

    graph = build_default_graph()
    engine = CausalRCA(graph=graph)

    # 1. Run TraceSense Causal RCA
    ranked_candidates = engine.rank(incident_df)

    # 2. Run Baselines
    baseline_highest_score = predict_highest_score(incident_df)
    baseline_earliest_time = predict_earliest_timestamp(incident_df)

    top_tracesense = ranked_candidates[0]["service"] if ranked_candidates else "None"

    # Display Output
    print("\n==================================================")
    print(" TRACESENSE RCA DEMO")
    print("==================================================")
    print(f"Incident: {incident_id}\n")

    anomalous_services = incident_df["service"].unique().tolist()
    print("Anomalous Services:")
    for s in anomalous_services:
        print(f"  - {s}")

    print("\n--------------------------------------------------")
    print(" TraceSense Ranking")
    print("--------------------------------------------------")
    print(f"{'Rank':<6}{'Service':<22}{'RCA Score':<12}{'Temporal':<10}{'Topology':<10}{'Coverage':<10}{'Strength':<10}")
    print("-" * 80)
    for c in ranked_candidates:
        print(
            f"{c['rank']:<6}{c['service']:<22}{c['rca_score']:<12.4f}"
            f"{c['temporal_score']:<10.4f}{c['topology_score']:<10.4f}"
            f"{c['coverage_score']:<10.4f}{c['anomaly_score']:<10.4f}"
        )

    print("\n--------------------------------------------------")
    print(" Root Cause Candidate & Explanation")
    print("--------------------------------------------------")
    explanation = engine.explain(ranked_candidates)
    print(explanation)

    print("\n--------------------------------------------------")
    print(" Baseline Comparison")
    print("--------------------------------------------------")
    print(f"Highest Anomaly Score : {baseline_highest_score}")
    print(f"Earliest Anomaly      : {baseline_earliest_time}")
    print(f"TraceSense (Causal)   : {top_tracesense}")
    print("==================================================\n")


if __name__ == "__main__":
    incident = sys.argv[1] if len(sys.argv) > 1 else "INC001"
    run_demo(incident)
