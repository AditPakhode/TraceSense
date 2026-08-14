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


SERVICE = os.environ.get("SERVICE_NAME", "pricing-service")
PROMOTION_SERVICE_URL = os.environ.get("PROMOTION_SERVICE_URL", "http://promotion-service:8080/process")
FAULT_MODE = os.environ.get("FAULT_MODE", "off").lower()
FAULT_SKU = os.environ.get("FAULT_SKU", "SENSOR-KIT")


def should_inject_fault():
    return FAULT_MODE in {"1", "true", "yes", "on", "faulty"}


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
        fault_active = should_inject_fault()
        line_totals = []
        subtotal = 0

        for item in payload["items"]:
            billable_quantity = item["quantity"]
            if fault_active and item["sku"] == FAULT_SKU:
                billable_quantity = max(item["quantity"] - 1, 0)

            line_total = billable_quantity * item["unit_price_cents"]
            subtotal += line_total
            line_totals.append(
                {
                    "line_id": item["line_id"],
                    "sku": item["sku"],
                    "quantity": item["quantity"],
                    "billable_quantity": billable_quantity,
                    "line_total_cents": line_total,
                }
            )

        payload["pricing"] = {
            "currency": payload["quote"]["currency"],
            "subtotal_cents": subtotal,
            "line_totals": line_totals,
        }

        quote_subtotal = payload["quote"]["catalog_subtotal_cents"]
        log_event(
            SERVICE,
            trace,
            "subtotal_calculated",
            order_id=payload["order_id"],
            quote_subtotal_cents=quote_subtotal,
            calculated_subtotal_cents=subtotal,
            subtotal_delta_cents=subtotal - quote_subtotal,
            fault_mode=FAULT_MODE,
            outcome="success",
        )

        try:
            downstream_status, downstream_body, _headers = post_json(PROMOTION_SERVICE_URL, payload, trace)
        except Exception as exc:
            write_json(self, 502, dependency_failure(SERVICE, trace, exc), trace)
            return

        log_event(
            SERVICE,
            trace,
            "pricing_forwarded",
            order_id=payload["order_id"],
            downstream_status=downstream_status,
            outcome="success" if downstream_status < 400 else "downstream_error",
        )
        write_json(self, downstream_status, downstream_body, trace)


if __name__ == "__main__":
    serve(Handler, SERVICE)

