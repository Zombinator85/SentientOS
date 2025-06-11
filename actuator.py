from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details.

Simple actuator REST API.

This module exposes minimal endpoints for executing commands via the
existing ``api.actuator`` helpers. It is intended as a lightweight
bridge that other services can call.

Endpoints
---------
/act : queue or execute an action. Supports ``shell``, ``http`` and
    ``file`` intents. POST JSON payloads with optional ``async`` flag.
/act_status : query the status of an async action.
/act_stream : server-sent events stream of action status updates.

Every execution is logged to ``logs/actuator_audit.jsonl`` with the
requesting user, full intent, and resulting status. The underlying
``api.actuator`` module enforces whitelists for shell/HTTP/file access
via ``config/act_whitelist.yml``.

Integration Notes: mount these endpoints under an existing Flask app or run this module directly. Dashboard clients may poll ``/act_status`` or stream ``/act_stream`` for progress updates.
"""

require_admin_banner()
require_lumos_approval()

from logging_config import get_log_path
import json
import time
from typing import Any, Dict

from cathedral_const import log_json

from flask_stub import Flask, Response, jsonify, request

from api import actuator as core_actuator

AUDIT_LOG = get_log_path("actuator_audit.jsonl", "ACTUATOR_AUDIT_LOG")
AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def _log(entry: Dict[str, Any]) -> None:
    log_json(AUDIT_LOG, {"timestamp": time.time(), "data": entry})


@app.route("/act", methods=["POST"])
def act_endpoint() -> Response:
    payload = request.get_json() or {}
    user = request.headers.get("X-User", "anonymous")
    explanation = payload.pop("why", None)
    if payload.pop("async", False):
        action_id = core_actuator.start_async(payload, explanation=explanation, user=user)
        _log({"user": user, "intent": payload, "status": "queued", "id": action_id})
        return jsonify({"status": "queued", "id": action_id})

    result = core_actuator.act(payload, explanation=explanation, user=user)
    _log({"user": user, "intent": payload, "result": result})
    return jsonify(result)


@app.route("/act_status", methods=["POST"])
def act_status_endpoint() -> Response:
    aid = (request.get_json() or {}).get("id", "")
    return jsonify(core_actuator.get_status(aid))


@app.route("/act_stream", methods=["POST"])
def act_stream_endpoint() -> Response:
    aid = (request.get_json() or {}).get("id", "")

    def gen():
        last = None
        while True:
            status = core_actuator.get_status(aid)
            if status != last:
                yield f"data: {json.dumps(status)}\n\n"
                last = status
            if status.get("status") in {"finished", "failed", "unknown"}:
                break
            time.sleep(0.5)

    return Response(gen(), mimetype="text/event-stream")


if __name__ == "__main__":  # pragma: no cover - manual launch
    app.run(debug=True)
