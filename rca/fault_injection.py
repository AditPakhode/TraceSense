"""TraceSense Fault Injection Script.

Sends checkout requests to simulate traffic during fault conditions.
Can record incident ground-truth metadata strictly for offline evaluation.
NOTE: Ground truth is NEVER exposed to the RCA causal engine.
"""

import argparse
import datetime
from pathlib import Path
import sys
import time
from typing import Optional
import requests

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_URL = "http://localhost:8080/checkout"

DEFAULT_ORDER = {
    "order_id": "order-1001",
    "customer_id": "cust-42",
    "loyalty_tier": "gold",
    "region": "CA",
    "items": [
        {
            "sku": "SENSOR-KIT",
            "quantity": 2,
        }
    ],
}


def record_ground_truth(
    incident_id: str,
    root_cause: str = "pricing-service",
    fault_type: str = "logic",
    output_path: str = "evaluation/ground_truth.csv",
) -> None:
    """Record ground-truth root cause strictly for post-hoc evaluation."""
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

    header = "incident_id,root_cause,fault_type,fault_timestamp\n"
    line = f"{incident_id},{root_cause},{fault_type},{ts}\n"

    if not out_file.exists():
        out_file.write_text(header + line, encoding="utf-8")
    else:
        content = out_file.read_text(encoding="utf-8")
        if incident_id not in content:
            with open(out_file, "a", encoding="utf-8") as f:
                f.write(line)


def run_injection(
    url: str = DEFAULT_URL,
    count: int = 30,
    delay: float = 1.0,
    incident_id: Optional[str] = None,
    record_truth: bool = False,
) -> None:
    print("\n===================================")
    print(" TraceSense Fault Injection")
    print("===================================")
    print("\nTarget: pricing-service")
    print("Sending checkout requests...\n")

    start_time = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

    for i in range(count):
        try:
            response = requests.post(url, json=DEFAULT_ORDER, timeout=5)
            print(f"Request {i + 1}: HTTP {response.status_code}")
        except Exception as e:
            print(f"Request {i + 1}: ERROR - {e}")

        if i < count - 1 and delay > 0:
            time.sleep(delay)

    print("\nFault injection completed.")

    if record_truth and incident_id:
        record_ground_truth(incident_id=incident_id)
        print(f"Recorded ground truth metadata for {incident_id}.")


def main():
    parser = argparse.ArgumentParser(description="Inject checkout traffic during fault simulation.")
    parser.add_argument("--url", default=DEFAULT_URL, help="Checkout API endpoint URL")
    parser.add_argument("--count", type=int, default=30, help="Number of checkout requests")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay in seconds between requests")
    parser.add_argument("--incident-id", default=None, help="Optional incident identifier for recording ground truth")
    parser.add_argument("--record-truth", action="store_true", help="Record ground-truth incident metadata for evaluation")
    args = parser.parse_args()

    run_injection(
        url=args.url,
        count=args.count,
        delay=args.delay,
        incident_id=args.incident_id,
        record_truth=args.record_truth,
    )


if __name__ == "__main__":
    main()