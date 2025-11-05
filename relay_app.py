"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

from sentientos.privilege import require_admin_banner, require_lumos_approval

load_dotenv()

require_admin_banner()
if not (os.getenv("LUMOS_AUTO_APPROVE") == "1" or os.getenv("SENTIENTOS_HEADLESS") == "1"):
    require_lumos_approval()
else:
    print("[Lumos] Blessing auto-approved (headless mode).")

from logging_config import get_log_path

try:
    from flask import Flask, Response, jsonify, request
except ImportError:  # pragma: no cover - runtime fallback
    from flask_stub import Flask, Response, jsonify, request

import epu
import memory_manager as mm
from api import actuator
from emotions import empty_emotion_vector
from memory_manager import write_mem
from utils import chunk_message
import mem_export
import secure_memory_storage as secure_store
from safety_log import count_recent_events
import dream_loop

import requests

from distributed_memory import encode_payload, synchronizer
from node_discovery import discovery
from node_registry import NODE_TOKEN, RoundRobinRouter, registry

app = Flask(__name__)
log_level = os.getenv("RELAY_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO))

RELAY_SECRET = os.getenv("RELAY_SECRET", "test-secret")
_REMOTE_TIMEOUT = float(os.getenv("SENTIENTOS_REMOTE_TIMEOUT", "10"))
_NODE_HEADER = "X-Node-Token"

NODE_ROUTER = RoundRobinRouter(registry)


def _build_remote_headers() -> Dict[str, str]:
    headers = {"X-Relay-Secret": RELAY_SECRET}
    if NODE_TOKEN:
        headers[_NODE_HEADER] = NODE_TOKEN
    return headers


def _proxy_remote_json(path: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    node = NODE_ROUTER.next()
    if not node:
        return None
    url = f"http://{node.ip}:{node.port}{path}"
    try:
        response = requests.post(url, json=payload, headers=_build_remote_headers(), timeout=_REMOTE_TIMEOUT)
    except requests.RequestException as exc:
        logging.warning("[Relay] Remote %s failed for %s (%s): %s", path, node.hostname, node.ip, exc)
        return None
    if response.status_code != 200:
        logging.warning(
            "[Relay] Remote %s returned %s for %s (%s)", path, response.status_code, node.hostname, node.ip
        )
        return None
    logging.info("[Relay] Routed %s to %s (%s)", path, node.hostname, node.ip)
    try:
        return response.json()
    except ValueError:
        logging.warning("[Relay] Remote %s produced non-JSON payload", path)
        return None


def _is_authorised_for_node_routes() -> bool:
    if request.headers.get("X-Relay-Secret") == RELAY_SECRET:
        return True
    if NODE_TOKEN and request.headers.get(_NODE_HEADER) == NODE_TOKEN:
        return True
    return False


def _incognito_enabled() -> bool:
    return os.getenv("MEM_INCOGNITO", "0") == "1"


def _ensure_background_services() -> None:
    if os.getenv("SENTIENTOS_DISABLE_DISCOVERY") == "1":
        return
    try:
        discovery.start()
    except Exception as exc:  # pragma: no cover - defensive
        logging.warning("Failed to start node discovery: %s", exc, exc_info=True)
    try:
        synchronizer.start()
    except Exception as exc:  # pragma: no cover - defensive
        logging.warning("Failed to start distributed memory sync: %s", exc, exc_info=True)


_ensure_background_services()


@app.route("/nodes", methods=["GET"])
def list_nodes() -> Response:
    if not _is_authorised_for_node_routes():
        return Response("Forbidden", status=403)
    return jsonify({"nodes": registry.active_nodes()})


@app.route("/nodes/register", methods=["POST"])
def register_node() -> Response:
    if not _is_authorised_for_node_routes():
        return Response("Forbidden", status=403)
    data = request.get_json() or {}
    token = data.get("token") or request.headers.get(_NODE_HEADER)
    if NODE_TOKEN and token != NODE_TOKEN:
        return Response("Forbidden", status=403)
    hostname = str(data.get("hostname") or data.get("id") or "").strip()
    ip = str(data.get("ip") or request.remote_addr or "").strip()
    if not hostname or not ip:
        return jsonify({"error": "hostname and ip are required"}), 400
    try:
        port = int(data.get("port", 5000))
    except (TypeError, ValueError):
        port = 5000
    capabilities = data.get("capabilities") if isinstance(data.get("capabilities"), dict) else {}
    record = registry.register_or_update(hostname, ip, port=port, capabilities=capabilities, last_seen=time.time())
    return jsonify(record.serialise()), 201


@app.route("/memory/export", methods=["GET", "POST"])
def memory_export() -> Response:
    if request.method == "GET":
        if NODE_TOKEN and request.headers.get(_NODE_HEADER) != NODE_TOKEN:
            return Response("Forbidden", status=403)
        limit_arg = request.args.get("limit")
        limit = None
        if limit_arg:
            try:
                limit = max(1, int(limit_arg))
            except ValueError:
                limit = None
        fragments = list(mm.iter_fragments(limit=limit, reverse=False))
        payload = {"fragments": fragments}
        allow_compression = "zstd" in (request.headers.get("Accept-Encoding", "").lower())
        body, headers = encode_payload(payload, allow_compression=allow_compression)
        response = Response(body, status=200, mimetype="application/json")
        for key, value in headers.items():
            response.headers[key] = value
        return response

    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return Response("Forbidden", status=403)
    options = request.get_json() or {}
    include_insights = bool(options.get("include_insights", True))
    include_dreams = bool(options.get("include_dreams", True))
    passphrase = options.get("passphrase")
    archive = mem_export.export_encrypted(
        None,
        include_insights=include_insights,
        include_dreams=include_dreams,
        passphrase=passphrase,
    )
    response = Response(archive, status=200, mimetype="application/octet-stream")
    response.headers["Content-Disposition"] = "attachment; filename=sentientos_memory.bin"
    return response


@app.route("/relay", methods=["POST"])
def relay():
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return "Forbidden", 403

    data = request.get_json() or {}
    remote = _proxy_remote_json("/relay", data)
    if remote is not None:
        return jsonify(remote)

    message = data.get("message", "")
    model = data.get("model", "default").strip().lower()
    emotion_vector = data.get("emotions") or empty_emotion_vector()

    reply = f"Echo: {message} ({model})"
    write_mem(
        f"[RELAY] → Model: {model} | Message: {message}\n{reply}",
        tags=["relay", model],
        source="relay",
        emotions=emotion_vector,
    )
    return jsonify({"reply_chunks": chunk_message(reply)})


@app.route("/memory/import", methods=["POST"])
def memory_import() -> Response:
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return Response("Forbidden", status=403)
    payload: bytes | None = None
    passphrase = request.form.get("passphrase") if request.form else None
    if "archive" in request.files:
        payload = request.files["archive"].read()
        if not passphrase:
            passphrase = request.form.get("passphrase") if request.form else None
    elif request.data:
        payload = request.data
    elif request.is_json:
        data = request.get_json() or {}
        archive_b64 = data.get("archive")
        if archive_b64:
            payload = base64.b64decode(archive_b64)
        passphrase = passphrase or data.get("passphrase")
    if payload is None:
        return jsonify({"error": "archive payload required"}), 400
    stats = mem_export.import_encrypted(payload, passphrase=passphrase)
    return jsonify(stats)


@app.route("/memory/stats", methods=["GET"])
def memory_stats() -> Response:
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return Response("Forbidden", status=403)
    if secure_store.is_enabled():
        categories = secure_store.category_counts()
        count = secure_store.fragment_count()
    else:
        categories = {}
        count = sum(1 for _ in mm.iter_fragments(limit=5000, reverse=False))
    return jsonify({"categories": categories, "count": count})


@app.route("/status", methods=["GET"])
def status() -> Response:
    loop_status: Dict[str, Any] = {}
    try:
        loop_status = dream_loop.status()
    except Exception:  # pragma: no cover - defensive
        loop_status = {"active": False}
    payload: Dict[str, Any] = {
        "incognito": _incognito_enabled(),
        "dream_loop_active": bool(loop_status.get("active")),
        "safety_events_1h": count_recent_events(1),
    }
    if secure_store.is_enabled():
        payload.update(
            {
                "memory_db_size_bytes": secure_store.db_size_bytes(),
                "mem_entries": secure_store.fragment_count(),
                "active_key_id": secure_store.get_backend().get_active_key_id(),
                "last_rotation_at": secure_store.get_meta("last_rotation_at"),
                "last_reflection_at": secure_store.get_meta("last_reflection_at"),
            }
        )
    else:
        payload.update(
            {
                "memory_db_size_bytes": 0,
                "mem_entries": sum(1 for _ in mm.iter_fragments(limit=1000, reverse=False)),
                "active_key_id": None,
                "last_rotation_at": None,
                "last_reflection_at": None,
            }
        )
    payload["dream_loop"] = loop_status
    return jsonify(payload)


@app.route("/act", methods=["POST"])
def act():
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return "Forbidden", 403

    payload = request.get_json() or {}
    if not payload.get("async"):
        remote = _proxy_remote_json("/act", payload)
        if remote is not None:
            return jsonify(remote)

    payload = dict(payload)
    explanation = payload.pop("why", None)
    user = request.headers.get("X-User", "relay")
    call_id = write_mem(
        f"[ACT REQUEST] {json.dumps(payload)}",
        tags=["act", "request"],
        source=user,
    )
    if payload.pop("async", False):
        action_id = actuator.start_async(payload, explanation=explanation, user=user)
        return jsonify({"status": "queued", "action_id": action_id, "request_log_id": call_id})

    result = actuator.act(payload, explanation=explanation, user=user)
    result["request_log_id"] = call_id
    return jsonify(result)


@app.route("/act_status", methods=["POST"])
def act_status():
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return "Forbidden", 403
    aid = (request.get_json() or {}).get("id", "")
    return jsonify(actuator.get_status(aid))


@app.route("/act_stream", methods=["POST"])
def act_stream():
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return "Forbidden", 403
    aid = (request.get_json() or {}).get("id", "")

    def gen():
        last = None
        while True:
            status = actuator.get_status(aid)
            if status != last:
                yield f"data: {json.dumps(status)}\n\n"
                last = status
            if status.get("status") in {"finished", "failed", "unknown"}:
                break
            time.sleep(0.5)

    return Response(gen(), mimetype="text/event-stream")


@app.route("/goals/list", methods=["POST"])
def goals_list():
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return "Forbidden", 403
    return jsonify(mm.get_goals(open_only=False))


@app.route("/goals/add", methods=["POST"])
def goals_add():
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return "Forbidden", 403
    data = request.get_json() or {}
    intent = data.get("intent") or {}
    goal = mm.add_goal(
        data.get("text", ""),
        intent=intent,
        priority=int(data.get("priority", 1)),
        deadline=data.get("deadline"),
        schedule_at=data.get("schedule_at"),
    )
    return jsonify(goal)


@app.route("/goals/complete", methods=["POST"])
def goals_complete():
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return "Forbidden", 403
    gid = (request.get_json() or {}).get("id")
    goal = mm.get_goal(gid)
    if not goal:
        return "not found", 404
    goal["status"] = "completed"
    mm.save_goal(goal)
    return jsonify({"status": "ok"})


@app.route("/goals/delete", methods=["POST"])
def goals_delete():
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return "Forbidden", 403
    gid = (request.get_json() or {}).get("id")
    mm.delete_goal(gid)
    return jsonify({"status": "deleted"})


@app.route("/agent/run", methods=["POST"])
def agent_run():
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return "Forbidden", 403
    cycles = int((request.get_json() or {}).get("cycles", 1))
    import autonomous_reflector as ar
    ar.run_loop(iterations=cycles, interval=0.01)
    return jsonify({"status": "ran", "cycles": cycles})


def _read_last(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        line = path.read_text(encoding="utf-8").strip().splitlines()[-1]
        return json.loads(line)
    except Exception:
        return {}


@app.route("/mood")
def mood() -> Response:
    data = _read_last(epu.MOOD_LOG)
    return jsonify(data.get("mood", {}))


@app.route("/current_emotion")
def current_emotion() -> Response:
    return mood()


@app.route("/eeg")
def eeg_state() -> Response:
    path = get_log_path("eeg_events.jsonl", "EEG_LOG")
    return jsonify(_read_last(path))


@app.route("/haptics")
def haptics_state() -> Response:
    path = get_log_path("haptics_events.jsonl", "HAPTIC_LOG")
    return jsonify(_read_last(path))


@app.route("/bio")
def bio_state() -> Response:
    path = get_log_path("bio_events.jsonl", "BIO_LOG")
    return jsonify(_read_last(path))


if __name__ == "__main__":
    print("[Relay] Lumos blessing auto-approved (headless/auto mode).")
    print("[Relay] Starting Flask relay service on http://127.0.0.1:5000 …")
    print("[SentientOS] Relay bound to http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000)
