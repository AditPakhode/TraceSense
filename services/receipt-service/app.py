import os

from common.service_lib import (
    JsonServiceHandler,
    begin_trace,
    log_event,
    read_json,
    round_bps,
    serve,
    write_json,
)


SERVICE = os.environ.get("SERVICE_NAME", "receipt-service")


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
        quote_subtotal = payload["quote"]["catalog_subtotal_cents"]
        discount_bps = payload["promotion"]["discount_bps"]
        tax_bps = payload["tax"]["tax_bps"]
        expected_discount = round_bps(quote_subtotal, discount_bps)
        expected_taxable = quote_subtotal - expected_discount
        expected_tax = round_bps(expected_taxable, tax_bps)
        expected_total = expected_taxable + expected_tax
        actual_total = payload["tax"]["total_cents"]

        if actual_total != expected_total:
            log_event(
                SERVICE,
                trace,
                "receipt_validation_failed",
                order_id=payload["order_id"],
                actual_total_cents=actual_total,
                expected_total_cents=expected_total,
                delta_cents=actual_total - expected_total,
                outcome="error",
            )
            write_json(
                self,
                422,
                {
                    "status": "validation_failed",
                    "service": SERVICE,
                    "error": "TOTAL_RECONCILIATION_FAILED",
                    "message": "Receipt total does not match the catalog quote invariant.",
                    "order_id": payload["order_id"],
                    "actual_total_cents": actual_total,
                    "expected_total_cents": expected_total,
                    "delta_cents": actual_total - expected_total,
                    "trace_id": trace["trace_id"],
                },
                trace,
            )
            return

        receipt = {
            "receipt_id": f"rcpt-{payload['order_id']}",
            "order_id": payload["order_id"],
            "currency": payload["quote"]["currency"],
            "subtotal_cents": payload["pricing"]["subtotal_cents"],
            "discount_cents": payload["promotion"]["discount_cents"],
            "tax_cents": payload["tax"]["tax_cents"],
            "total_cents": actual_total,
        }
        log_event(
            SERVICE,
            trace,
            "receipt_issued",
            order_id=payload["order_id"],
            total_cents=actual_total,
            outcome="success",
        )
        write_json(
            self,
            200,
            {
                "status": "receipt_issued",
                "service": SERVICE,
                "receipt": receipt,
                "trace_id": trace["trace_id"],
            },
            trace,
        )


if __name__ == "__main__":
    serve(Handler, SERVICE)

