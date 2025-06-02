"""Simple actuator REST API.

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

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict

from flask_stub import Flask, Response, jsonify, request

from api import actuator as core_actuator
from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

AUDIT_LOG = Path(os.getenv("ACTUATOR_AUDIT_LOG", "logs/actuator_audit.jsonl"))
AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def _log(entry: Dict[str, Any]) -> None:
    entry["timestamp"] = time.time()
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


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
    require_admin_banner()
    app.run(debug=True)
