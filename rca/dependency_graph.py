import networkx as nx

# Create directed graph
G = nx.DiGraph()

# Add services
services = [
    "checkout-api",
    "cart-service",
    "inventory-service",
    "pricing-service",
    "promotion-service",
    "tax-service",
    "receipt-service"
]

G.add_nodes_from(services)

# Define service dependencies
G.add_edges_from([
    ("checkout-api", "cart-service"),
    ("cart-service", "inventory-service"),
    ("cart-service", "pricing-service"),
    ("cart-service", "promotion-service"),
    ("cart-service", "tax-service"),
    ("cart-service", "receipt-service")
])

print("\nService Dependency Graph")
print("------------------------")

for service in G.nodes:
    dependencies = list(G.successors(service))

    if dependencies:
        print(f"{service} -> {dependencies}")

        