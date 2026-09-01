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


SERVICE = os.environ.get("SERVICE_NAME", "checkout-api")
CART_SERVICE_URL = os.environ.get("CART_SERVICE_URL", "http://cart-service:8080/process")


def normalize_order(payload):
    return {
        "order_id": payload.get("order_id", "order-1001"),
        "customer": {
            "id": payload.get("customer_id", "cust-42"),
            "loyalty_tier": payload.get("loyalty_tier", "gold"),
            "region": payload.get("region", "CA"),
        },
        "items": payload.get(
            "items",
            [
                {
                    "sku": "SENSOR-KIT",
                    "quantity": 2,
                }
            ],
        ),
    }


class Handler(JsonServiceHandler):
    service_name = SERVICE

    def do_POST(self):
        if self.path != "/checkout":
            write_json(self, 404, {"status": "not_found", "service": SERVICE})
            return

        try:
            payload = read_json(self)
        except ValueError as exc:
            write_json(self, 400, {"status": "bad_request", "service": SERVICE, "error": str(exc)})
            return

        trace = begin_trace(self, payload)
        order = normalize_order(payload)
        log_event(
            SERVICE,
            trace,
            "checkout_received",
            order_id=order["order_id"],
            item_count=len(order["items"]),
            outcome="accepted",
        )

        try:
            downstream_status, downstream_body, _headers = post_json(CART_SERVICE_URL, order, trace)
        except Exception as exc:
            write_json(self, 502, dependency_failure(SERVICE, trace, exc), trace)
            return

        log_event(
            SERVICE,
            trace,
            "checkout_completed",
            order_id=order["order_id"],
            downstream_status=downstream_status,
            outcome="success" if downstream_status < 400 else "visible_failure",
        )

        response_status = downstream_status
        response_body = {
            "status": "completed" if downstream_status < 400 else "failed",
            "service": SERVICE,
            "trace_id": trace["trace_id"],
            "pipeline_result": downstream_body,
        }
        write_json(self, response_status, response_body, trace)


if __name__ == "__main__":
    serve(Handler, SERVICE)

