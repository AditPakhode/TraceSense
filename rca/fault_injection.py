import time
import requests

URL = "http://localhost:8080/checkout"

ORDER = {
    "order_id": "order-1001",
    "customer_id": "cust-42",
    "loyalty_tier": "gold",
    "region": "CA",
    "items": [
        {
            "sku": "SENSOR-KIT",
            "quantity": 2
        }
    ]
}

print("\n===================================")
print(" TraceSense Fault Injection")
print("===================================")

print("\nTarget: pricing-service")
print("Sending checkout requests...\n")

for i in range(30):

    try:
        response = requests.post(
            URL,
            json=ORDER,
            timeout=5
        )

        print(
            f"Request {i + 1}: "
            f"HTTP {response.status_code}"
        )

    except Exception as e:

        print(
            f"Request {i + 1}: ERROR - {e}"
        )

    time.sleep(1)

print("\nFault injection completed.")