from admin_utils import require_admin_banner
from logging_config import get_log_path

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
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "error": "invalid_token",
        "provided": provided,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


@app.route("/message", methods=["POST"])
def message() -> Response:
    if not _authorized():
        return "Forbidden", 403
    data = request.get_json() or {}
    payload = json.dumps({"time": time.time(), "data": data})
    _events.put(payload)
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
            yield f"data: {_events.get()}\n\n"

    return Response(gen())


if __name__ == "__main__":  # pragma: no cover - manual launch
    app.run(debug=True)
