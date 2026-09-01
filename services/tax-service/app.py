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


SERVICE = os.environ.get("SERVICE_NAME", "tax-service")
RECEIPT_SERVICE_URL = os.environ.get("RECEIPT_SERVICE_URL", "http://receipt-service:8080/process")

TAX_BPS_BY_REGION = {
    "CA": 825,
    "NY": 887,
    "TX": 625,
    "WA": 650,
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
        region = payload["customer"].get("region", "CA")
        tax_bps = TAX_BPS_BY_REGION.get(region, 0)
        taxable_amount = payload["promotion"]["discounted_subtotal_cents"]
        tax_cents = round_bps(taxable_amount, tax_bps)
        total_cents = taxable_amount + tax_cents

        payload["tax"] = {
            "region": region,
            "tax_bps": tax_bps,
            "taxable_amount_cents": taxable_amount,
            "tax_cents": tax_cents,
            "total_cents": total_cents,
        }

        log_event(
            SERVICE,
            trace,
            "tax_calculated",
            order_id=payload["order_id"],
            taxable_amount_cents=taxable_amount,
            tax_bps=tax_bps,
            tax_cents=tax_cents,
            total_cents=total_cents,
            outcome="success",
        )

        try:
            downstream_status, downstream_body, _headers = post_json(RECEIPT_SERVICE_URL, payload, trace)
        except Exception as exc:
            write_json(self, 502, dependency_failure(SERVICE, trace, exc), trace)
            return

        log_event(
            SERVICE,
            trace,
            "tax_forwarded",
            order_id=payload["order_id"],
            downstream_status=downstream_status,
            outcome="success" if downstream_status < 400 else "downstream_error",
        )
        write_json(self, downstream_status, downstream_body, trace)


if __name__ == "__main__":
    serve(Handler, SERVICE)

