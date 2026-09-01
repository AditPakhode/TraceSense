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


SERVICE = os.environ.get("SERVICE_NAME", "cart-service")
INVENTORY_SERVICE_URL = os.environ.get("INVENTORY_SERVICE_URL", "http://inventory-service:8080/process")


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
        items = [
            {
                "line_id": f"line-{index + 1}",
                "sku": item["sku"],
                "quantity": int(item.get("quantity", 1)),
            }
            for index, item in enumerate(payload["items"])
        ]
        payload["items"] = items
        payload["cart"] = {
            "line_count": len(items),
            "total_quantity": sum(item["quantity"] for item in items),
        }

        log_event(
            SERVICE,
            trace,
            "cart_normalized",
            order_id=payload["order_id"],
            line_count=payload["cart"]["line_count"],
            total_quantity=payload["cart"]["total_quantity"],
            outcome="success",
        )

        try:
            downstream_status, downstream_body, _headers = post_json(INVENTORY_SERVICE_URL, payload, trace)
        except Exception as exc:
            write_json(self, 502, dependency_failure(SERVICE, trace, exc), trace)
            return

        log_event(
            SERVICE,
            trace,
            "cart_forwarded",
            order_id=payload["order_id"],
            downstream_status=downstream_status,
            outcome="success" if downstream_status < 400 else "downstream_error",
        )
        write_json(self, downstream_status, downstream_body, trace)


if __name__ == "__main__":
    serve(Handler, SERVICE)

