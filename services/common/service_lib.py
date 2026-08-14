import datetime
import json
import os
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import error, request


def env(name, default):
    return os.environ.get(name, default)


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def cents_to_dollars(cents):
    return f"{cents / 100:.2f}"


def round_bps(amount_cents, bps):
    return (amount_cents * bps + 5000) // 10000


def begin_trace(handler, payload):
    trace_id = handler.headers.get("X-Trace-Id") or payload.get("trace_id") or uuid.uuid4().hex
    parent_span_id = handler.headers.get("X-Parent-Span-Id") or payload.get("span_id")
    return {
        "trace_id": trace_id,
        "span_id": uuid.uuid4().hex[:16],
        "parent_span_id": parent_span_id,
    }


def read_json(handler):
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length == 0:
        return {}

    raw_body = handler.rfile.read(length)
    if not raw_body:
        return {}

    try:
        return json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON body: {exc}") from exc


def write_json(handler, status, payload, trace=None):
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    if trace:
        handler.send_header("X-Trace-Id", trace["trace_id"])
        handler.send_header("X-Span-Id", trace["span_id"])
    handler.end_headers()
    handler.wfile.write(body)


def log_event(service, trace, event, **fields):
    record = {
        "timestamp": utc_now(),
        "service": service,
        "trace_id": trace["trace_id"],
        "span_id": trace["span_id"],
        "parent_span_id": trace.get("parent_span_id"),
        "event": event,
    }
    record.update(fields)
    print(json.dumps(record, sort_keys=True), flush=True)


def post_json(url, payload, trace, timeout=4):
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    req = request.Request(
        url,
        data=encoded,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Trace-Id": trace["trace_id"],
            "X-Parent-Span-Id": trace["span_id"],
        },
    )

    try:
        with request.urlopen(req, timeout=timeout) as response:
            return response.status, _decode_response(response.read()), dict(response.headers)
    except error.HTTPError as exc:
        return exc.code, _decode_response(exc.read()), dict(exc.headers)


def _decode_response(body):
    if not body:
        return {}
    try:
        return json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return {"raw_body": body.decode("utf-8", errors="replace")}


def dependency_failure(service, trace, exc):
    log_event(service, trace, "dependency_call_failed", outcome="error", error=str(exc))
    return {
        "status": "dependency_unavailable",
        "service": service,
        "error": str(exc),
        "trace_id": trace["trace_id"],
    }


class JsonServiceHandler(BaseHTTPRequestHandler):
    service_name = "service"

    def log_message(self, _format, *_args):
        return

    def do_GET(self):
        if self.path == "/health":
            write_json(self, 200, {"status": "ok", "service": self.service_name})
            return
        write_json(self, 404, {"status": "not_found", "service": self.service_name})


def serve(handler_class, service_name):
    port = int(env("PORT", "8080"))
    print(
        json.dumps(
            {
                "timestamp": utc_now(),
                "service": service_name,
                "event": "service_started",
                "port": port,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    ThreadingHTTPServer(("0.0.0.0", port), handler_class).serve_forever()
