from admin_utils import require_admin_banner
from logging_config import get_log_path
import logging
from logging.handlers import RotatingFileHandler

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.

import os
import json
import time
from datetime import datetime
from queue import SimpleQueue
from flask_stub import Flask, jsonify, request, Response


CONNECTOR_TOKEN = os.getenv("CONNECTOR_TOKEN", "test-token")
app = Flask(__name__)
_events: SimpleQueue[str] = SimpleQueue()
LOG_PATH = get_log_path("openai_connector.jsonl", "OPENAI_CONNECTOR_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
SSE_TIMEOUT = float(os.getenv("SSE_TIMEOUT", "30"))  # seconds

# Configure rotating JSONL logger
_logger = logging.getLogger("openai_connector")
_handler = RotatingFileHandler(
    LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
)
_handler.setFormatter(logging.Formatter("%(message)s"))
_logger.addHandler(_handler)
_logger.setLevel(logging.INFO)


def _log_event(event: str, ip: str, **extra: object) -> None:
    """Write a structured JSON entry to the connector log."""
    entry: dict[str, object] = {
        "timestamp": datetime.utcnow().isoformat(),
        "event": event,
        "ip": ip,
    }
    entry.update(extra)
    _logger.info(json.dumps(entry))


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


def _validate_message(data: object) -> tuple[bool, str | None]:
    if not isinstance(data, dict):
        return False, "malformed_json"
    text = data.get("text") if isinstance(data, dict) else None
    if text is None:
        return False, "missing_field"
    if not isinstance(text, str):
        return False, "invalid_type"
    return True, None


@app.route("/message", methods=["POST"])
def message() -> Response:
    if not _authorized():
        return "Forbidden", 403
    data = request.get_json(silent=True)
    valid, err = _validate_message(data)
    if not valid:
        ip = request.headers.get("X-Forwarded-For", "unknown")
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


if __name__ == "__main__":  # pragma: no cover - manual launch
    app.run(debug=True)
