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

# Configure rotating JSONL logger
_logger = logging.getLogger("openai_connector")
_handler = RotatingFileHandler(
    LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
)
_handler.setFormatter(logging.Formatter("%(message)s"))
_logger.addHandler(_handler)
_logger.setLevel(logging.INFO)


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
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "event": "auth_error",
        "ip": ip,
        "provided": provided,
    }
    _logger.info(json.dumps(entry))


@app.route("/message", methods=["POST"])
def message() -> Response:
    if not _authorized():
        return "Forbidden", 403
    data = request.get_json(silent=True)
    if data is None:
        ip = request.headers.get("X-Forwarded-For", "unknown")
        _logger.info(
            json.dumps(
                {
                    "timestamp": datetime.utcnow().isoformat(),
                    "event": "message_error",
                    "ip": ip,
                    "error": "malformed_json",
                }
            )
        )
        return jsonify({"error": "malformed JSON"}), 400
    if not isinstance(data, dict) or "text" not in data:
        ip = request.headers.get("X-Forwarded-For", "unknown")
        _logger.info(
            json.dumps(
                {
                    "timestamp": datetime.utcnow().isoformat(),
                    "event": "message_error",
                    "ip": ip,
                    "error": "missing_field",
                }
            )
        )
        return jsonify({"error": "missing 'text' field"}), 400
    payload = json.dumps({"time": time.time(), "data": data})
    _events.put(payload)
    ip = request.headers.get("X-Forwarded-For", "unknown")
    _logger.info(
        json.dumps(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "event": "message",
                "ip": ip,
                "data": data,
            }
        )
    )
    return jsonify({"status": "queued"})


@app.route("/sse")
def sse() -> Response:
    if not _authorized():
        return "Forbidden", 403

    def gen():
        while True:
            if _events.empty():
                time.sleep(0.1)
                continue
            payload = _events.get()
            ip = request.headers.get("X-Forwarded-For", "unknown")
            _logger.info(
                json.dumps(
                    {
                        "timestamp": datetime.utcnow().isoformat(),
                        "event": "sse",
                        "ip": ip,
                        "data": json.loads(payload)["data"],
                    }
                )
            )
            yield f"data: {payload}\n\n"

    return Response(gen())


if __name__ == "__main__":  # pragma: no cover - manual launch
    app.run(debug=True)
