# TraceSense Simulation

This repository contains a lightweight dummy microservice environment for testing TraceSense root-cause analysis against silent cascading failures.

## Service Graph

```text
checkout-api
  -> cart-service
  -> inventory-service
  -> pricing-service        # root cause when FAULT_MODE=on
  -> promotion-service      # propagates incorrect subtotal successfully
  -> tax-service            # compounds incorrect total successfully
  -> receipt-service        # first visible validation failure
```

The scenario models a checkout pipeline for a TraceSense hardware order. `inventory-service` creates a trusted catalog quote. `pricing-service` is responsible for turning that quote into chargeable line totals. `promotion-service` and `tax-service` then apply normal business logic to whatever subtotal they receive.

## Silent Fault

The root cause is seeded in `pricing-service` with `FAULT_MODE=on`.

In faulty mode, `pricing-service` has an off-by-one quantity normalization bug for `SENSOR-KIT`. It still returns HTTP 200 and emits normal-looking pricing output, but the subtotal is too low. The next services also return HTTP 200:

```text
inventory-service quote subtotal:      10000 cents
pricing-service faulty subtotal:        5000 cents
promotion-service discounted subtotal:  4500 cents
tax-service final total:                4871 cents
receipt-service expected final total:   9743 cents
```

The only business error surfaces at `receipt-service` as `TOTAL_RECONCILIATION_FAILED`.

## Run Healthy Mode

```bash
docker compose up --build
```

If your Docker install uses the legacy Compose binary, replace `docker compose` with `docker-compose` in the commands below.

Then call the public service:

```bash
curl -sS -X POST http://localhost:8080/checkout \
  -H 'Content-Type: application/json' \
  -d '{"order_id":"order-1001","customer_id":"cust-42","loyalty_tier":"gold","region":"CA","items":[{"sku":"SENSOR-KIT","quantity":2}]}'
```

Expected result: HTTP 200 with `status: "completed"` and a receipt.

You can also run:

```bash
python scripts/smoke_test.py --expect healthy
```

## Run Faulty Mode

Restart the stack with the seeded logical fault:

```bash
docker compose down
FAULT_MODE=on docker compose up --build
```

Then send the same request:

```bash
curl -sS -X POST http://localhost:8080/checkout \
  -H 'Content-Type: application/json' \
  -d '{"order_id":"order-1001","customer_id":"cust-42","loyalty_tier":"gold","region":"CA","items":[{"sku":"SENSOR-KIT","quantity":2}]}'
```

Expected result: HTTP 422. The response from `checkout-api` wraps the downstream `receipt-service` validation error. The visible symptom is several hops downstream from the root cause.

You can also run:

```bash
python scripts/smoke_test.py --expect faulty
```

## Logs and Trace Hooks

Every service writes structured JSON logs to stdout. Each request gets:

- `trace_id`
- `span_id`
- `parent_span_id`
- `service`
- `event`
- `outcome`
- domain fields such as `subtotal_cents`, `discount_cents`, `tax_cents`, or validation deltas

Useful log commands:

```bash
docker compose logs -f
docker compose logs pricing-service receipt-service
```

In faulty mode, the important non-error anomaly appears in `pricing-service` logs as a nonzero `subtotal_delta_cents`. The visible error appears later in `receipt-service` logs as `receipt_validation_failed`.
