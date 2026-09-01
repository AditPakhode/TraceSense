#!/usr/bin/env python3
import argparse
import json
import sys
from urllib import error, request


DEFAULT_PAYLOAD = {
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


def post_checkout(url):
    req = request.Request(
        url,
        data=json.dumps(DEFAULT_PAYLOAD).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=8) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description="Smoke-test the TraceSense simulation checkout chain.")
    parser.add_argument("--url", default="http://localhost:8080/checkout")
    parser.add_argument("--expect", choices=["healthy", "faulty"], default="healthy")
    args = parser.parse_args()

    status, body = post_checkout(args.url)
    print(json.dumps({"status": status, "body": body}, indent=2, sort_keys=True))

    if args.expect == "healthy" and status != 200:
        print(f"expected healthy status 200, got {status}", file=sys.stderr)
        return 1
    if args.expect == "faulty" and status != 422:
        print(f"expected faulty status 422, got {status}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

