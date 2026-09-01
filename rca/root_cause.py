import pandas as pd
import networkx as nx

# Load anomaly results
df = pd.read_csv("ml/anomaly_results.csv")

# Load dependency graph
G = nx.DiGraph()

G.add_edge("checkout-api", "cart-service")

G.add_edge("cart-service", "inventory-service")
G.add_edge("cart-service", "pricing-service")
G.add_edge("cart-service", "promotion-service")
G.add_edge("cart-service", "tax-service")
G.add_edge("cart-service", "receipt-service")


# Get only anomalous services
anomalies = df[df["status"] == "ANOMALY"].copy()

print("\nDetected Anomalies")
print("------------------")

for service in anomalies["service"].unique():
    print(service)


# Count anomalies for each service
anomaly_counts = (
    anomalies.groupby("service")
    .size()
    .sort_values(ascending=False)
)

print("\nAnomaly Frequency")
print("-----------------")

print(anomaly_counts)


# Calculate RCA score
scores = {}

for service in anomaly_counts.index:

    score = 0

    # More anomalies = stronger signal
    score += anomaly_counts[service]

    # Services that are upstream get higher importance
    for other_service in anomaly_counts.index:

        if service == other_service:
            continue

        if nx.has_path(G, service, other_service):
            score += 2

    scores[service] = score


# Sort services by RCA score
ranked = sorted(
    scores.items(),
    key=lambda x: x[1],
    reverse=True
)


print("\nRoot Cause Ranking")
print("------------------")

for service, score in ranked:
    print(f"{service}: {score}")


if ranked:
    print("\nLikely Root Cause:")
    print(ranked[0][0])
    