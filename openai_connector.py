from admin_utils import require_admin_banner, require_lumos_approval
from logging_config import get_log_path
import logging
from logging.handlers import RotatingFileHandler
import requests
from schema_validation import validate_payload

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
# Set ``LUMOS_AUTO_APPROVE=1`` to bypass the interactive blessing prompt
require_lumos_approval()

import os
import json
import time
from datetime import datetime
from queue import SimpleQueue
from flask_stub import Flask, jsonify, request, Response


CONNECTOR_TOKEN = os.getenv("CONNECTOR_TOKEN", "test-token")
app = Flask(__name__)
_events: SimpleQueue[str] = SimpleQueue()
# Override the default connector log path with ``OPENAI_CONNECTOR_LOG``
LOG_PATH = get_log_path("openai_connector.jsonl", "OPENAI_CONNECTOR_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
SSE_TIMEOUT = float(os.getenv("SSE_TIMEOUT", "30"))  # seconds
LOG_STDOUT = os.getenv("LOG_STDOUT", "0") in {"1", "true", "True"}
LOG_COLLECTOR_URL = os.getenv("LOG_COLLECTOR_URL")

_METRICS = {"connections": 0, "events": 0, "errors": 0}

# Configure rotating JSONL logger
_logger = logging.getLogger("openai_connector")
_handler = RotatingFileHandler(
    LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
)
_handler.setFormatter(logging.Formatter("%(message)s"))
_logger.addHandler(_handler)
_logger.setLevel(logging.INFO)


def _log_event(event: str, ip: str, **extra: object) -> None:
    """Write a structured JSON entry to the connector log and optional sinks."""
    entry: dict[str, object] = {
        "timestamp": datetime.utcnow().isoformat(),
        "event": event,
        "ip": ip,
    }
    entry.update(extra)
    _logger.info(json.dumps(entry))
    if LOG_STDOUT:
        print(json.dumps(entry))
    if LOG_COLLECTOR_URL:
        try:
            requests.post(LOG_COLLECTOR_URL, json=entry, timeout=2)
        except Exception:
            pass
    _METRICS["events"] += 1
    if event in {"auth_error", "disconnect", "message_error", "schema_violation"}:
        _METRICS["errors"] += 1


def _authorized() -> bool:
    auth = request.headers.get("Authorization", "")
    if not auth or not auth.startswith("Bearer "):
        _log_auth_error(auth or "<missing>")
        return False
    token = auth.split(" ", 1)[1]
    if token != CONNECTOR_TOKEN:
        _log_auth_error(auth)
        return False
    return True


def _log_auth_error(provided: str) -> None:
    ip = request.headers.get("X-Forwarded-For", "unknown")
    _log_event("auth_error", ip, provided=provided)


def _log_disconnect(ip: str, reason: str) -> None:
    _log_event("disconnect", ip, reason=reason)


_MESSAGE_SCHEMA = {"text": str}


def _validate_message(data: object) -> tuple[bool, str | None]:
    return validate_payload(data, _MESSAGE_SCHEMA)


@app.route("/message", methods=["POST"])
def message() -> Response:
    if not _authorized():
        return "Forbidden", 403
    data = request.get_json(silent=True)
    valid, err = _validate_message(data)
    if not valid:
        ip = request.headers.get("X-Forwarded-For", "unknown")
        _log_event("schema_violation", ip, error=err)
        _log_event("message_error", ip, error=err)
        msg = {
            "malformed_json": "malformed JSON",
            "missing_field": "missing 'text' field",
            "invalid_type": "'text' must be a string",
        }[err]
        return jsonify({"error": msg}), 400
    payload = json.dumps({"time": time.time(), "data": data})
    _events.put(payload)
    ip = request.headers.get("X-Forwarded-For", "unknown")
    _log_event("message", ip, data=data)
    return jsonify({"status": "queued"})


@app.route("/sse")
def sse() -> Response:
    if not _authorized():
        return "Forbidden", 403

    def gen():
        ip = request.headers.get("X-Forwarded-For", "unknown")
        _METRICS["connections"] += 1
        last = time.time()
        try:
            while True:
                if _events.empty():
                    if time.time() - last > SSE_TIMEOUT:
                        _log_disconnect(ip, "timeout")
                        break
                    time.sleep(0.1)
                    continue
                payload = _events.get()
                last = time.time()
                _log_event("sse", ip, data=json.loads(payload)["data"])
                yield f"data: {payload}\n\n"
        except GeneratorExit:
            _log_disconnect(ip, "client_closed")
            raise

    return Response(gen())


@app.route("/healthz")
def healthz() -> Response:
    return jsonify({"status": "ok"})


@app.route("/metrics")
def metrics() -> Response:
    lines = [
        "# HELP connections_total Number of SSE connections",
        "# TYPE connections_total counter",
        f"connections_total {_METRICS['connections']}",
        "# HELP events_total Number of logged events",
        "# TYPE events_total counter",
        f"events_total {_METRICS['events']}",
        "# HELP errors_total Number of error events",
        "# TYPE errors_total counter",
        f"errors_total {_METRICS['errors']}",
    ]
    return Response("\n".join(lines), 200)


if __name__ == "__main__":  # pragma: no cover - manual launch
    app.run(debug=True)
