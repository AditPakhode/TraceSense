import os

from common.service_lib import (
    JsonServiceHandler,
    begin_trace,
    dependency_failure,
    log_event,
    post_json,
    read_json,
    serve,
    write_json,
)


SERVICE = os.environ.get("SERVICE_NAME", "inventory-service")
PRICING_SERVICE_URL = os.environ.get("PRICING_SERVICE_URL", "http://pricing-service:8080/process")

CATALOG = {
    "SENSOR-KIT": {
        "name": "TraceSense Sensor Kit",
        "unit_price_cents": 5000,
        "warehouse": "iad-2",
        "available_units": 37,
    },
    "TRACE-CABLE": {
        "name": "TraceSense Diagnostic Cable",
        "unit_price_cents": 1500,
        "warehouse": "iad-2",
        "available_units": 120,
    },
}


class Handler(JsonServiceHandler):
    service_name = SERVICE

    def do_POST(self):
        if self.path != "/process":
            write_json(self, 404, {"status": "not_found", "service": SERVICE})
            return

        try:
            payload = read_json(self)
        except ValueError as exc:
            write_json(self, 400, {"status": "bad_request", "service": SERVICE, "error": str(exc)})
            return

        trace = begin_trace(self, payload)
        enriched_items = []
        for item in payload["items"]:
            product = CATALOG.get(item["sku"])
            if not product:
                write_json(
                    self,
                    422,
                    {
                        "status": "unknown_sku",
                        "service": SERVICE,
                        "sku": item["sku"],
                        "trace_id": trace["trace_id"],
                    },
                    trace,
                )
                return

            enriched_items.append(
                {
                    **item,
                    "name": product["name"],
                    "unit_price_cents": product["unit_price_cents"],
                    "warehouse": product["warehouse"],
                    "stock_reserved": item["quantity"] <= product["available_units"],
                }
            )

        quote_subtotal = sum(item["quantity"] * item["unit_price_cents"] for item in enriched_items)
        payload["items"] = enriched_items
        payload["quote"] = {
            "currency": "USD",
            "catalog_subtotal_cents": quote_subtotal,
        }

        log_event(
            SERVICE,
            trace,
            "inventory_reserved",
            order_id=payload["order_id"],
            catalog_subtotal_cents=quote_subtotal,
            catalog_subtotal=f"${quote_subtotal / 100:.2f}",
            outcome="success",
        )

        try:
            downstream_status, downstream_body, _headers = post_json(PRICING_SERVICE_URL, payload, trace)
        except Exception as exc:
            write_json(self, 502, dependency_failure(SERVICE, trace, exc), trace)
            return

        log_event(
            SERVICE,
            trace,
            "inventory_forwarded",
            order_id=payload["order_id"],
            downstream_status=downstream_status,
            outcome="success" if downstream_status < 400 else "downstream_error",
        )
        write_json(self, downstream_status, downstream_body, trace)


if __name__ == "__main__":
    serve(Handler, SERVICE)

