import os

from common.service_lib import (
    JsonServiceHandler,
    begin_trace,
    dependency_failure,
    log_event,
    post_json,
    read_json,
    round_bps,
    serve,
    write_json,
)


SERVICE = os.environ.get("SERVICE_NAME", "promotion-service")
TAX_SERVICE_URL = os.environ.get("TAX_SERVICE_URL", "http://tax-service:8080/process")

DISCOUNT_BPS_BY_TIER = {
    "none": 0,
    "silver": 500,
    "gold": 1000,
    "platinum": 1500,
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
        tier = payload["customer"].get("loyalty_tier", "none")
        discount_bps = DISCOUNT_BPS_BY_TIER.get(tier, 0)
        subtotal = payload["pricing"]["subtotal_cents"]
        discount_cents = round_bps(subtotal, discount_bps)
        discounted_subtotal = subtotal - discount_cents

        payload["promotion"] = {
            "loyalty_tier": tier,
            "discount_bps": discount_bps,
            "discount_cents": discount_cents,
            "discounted_subtotal_cents": discounted_subtotal,
        }

        log_event(
            SERVICE,
            trace,
            "discount_applied",
            order_id=payload["order_id"],
            subtotal_cents=subtotal,
            discount_bps=discount_bps,
            discount_cents=discount_cents,
            discounted_subtotal_cents=discounted_subtotal,
            outcome="success",
        )

        try:
            downstream_status, downstream_body, _headers = post_json(TAX_SERVICE_URL, payload, trace)
        except Exception as exc:
            write_json(self, 502, dependency_failure(SERVICE, trace, exc), trace)
            return

        log_event(
            SERVICE,
            trace,
            "promotion_forwarded",
            order_id=payload["order_id"],
            downstream_status=downstream_status,
            outcome="success" if downstream_status < 400 else "downstream_error",
        )
        write_json(self, downstream_status, downstream_body, trace)


if __name__ == "__main__":
    serve(Handler, SERVICE)

