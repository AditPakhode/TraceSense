import pandas as pd
import networkx as nx

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rca.dependency_graph import build_default_graph

# Load anomaly results
df = pd.read_csv("ml/anomaly_results.csv")

# Convert timestamp to datetime
df["timestamp"] = pd.to_datetime(df["timestamp"])

# Create dependency graph
G = build_default_graph()

# Get anomalous records
if "status" in df.columns:
    anomalies = df[df["status"] == "ANOMALY"].copy()
else:
    anomalies = df.copy()

print("\nFirst Anomaly Time")
print("------------------")

first_anomaly = (
    anomalies
    .groupby("service")["timestamp"]
    .min()
    .sort_values()
)

print(first_anomaly)


# Calculate RCA score
scores = {}

for service in first_anomaly.index:

    score = 0

    # --------------------------------
    # 1. Frequency score
    # --------------------------------

    frequency = len(
        anomalies[anomalies["service"] == service]
    )

    score += frequency


    # --------------------------------
    # 2. Early anomaly score
    # --------------------------------

    earliest_time = first_anomaly[service]

    seconds_from_start = (
        earliest_time - first_anomaly.min()
    ).total_seconds()

    # Earlier anomaly = higher score
    if seconds_from_start == 0:
        score += 10
    elif seconds_from_start <= 10:
        score += 7
    elif seconds_from_start <= 20:
        score += 4


    # --------------------------------
    # 3. Upstream influence
    # --------------------------------

    for other_service in first_anomaly.index:

        if service == other_service:
            continue

        if nx.has_path(G, service, other_service):
            score += 5


    scores[service] = score


# Rank services
ranking = sorted(
    scores.items(),
    key=lambda x: x[1],
    reverse=True
)


print("\nTime-Based Root Cause Ranking")
print("-----------------------------")

for service, score in ranking:
    print(f"{service}: {score}")


if ranking:

    print("\nLikely Root Cause:")
    print(ranking[0][0])
    