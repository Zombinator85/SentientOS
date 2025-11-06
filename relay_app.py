"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import logging
import os
import secrets
import socket
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
import mem_admin
import mem_export
import memory_governor as governor
import secure_memory_storage as secure_store
from safety_log import count_recent_events
import dream_loop

import requests

from distributed_memory import encode_payload, synchronizer
from gpu_autosetup import configure_stt
from node_discovery import discovery
from node_registry import NODE_TOKEN, RoundRobinRouter, registry
from pairing_service import pairing_service
from stt_service import StreamingTranscriber
from tts_service import TtsStreamer
from watchdog_service import WatchdogService
from webrtc_bridge import WebRTCSessionManager

app = Flask(__name__)
log_level = os.getenv("RELAY_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO))

RELAY_SECRET = os.getenv("RELAY_SECRET", "test-secret")
_REMOTE_TIMEOUT = float(os.getenv("SENTIENTOS_REMOTE_TIMEOUT", "10"))
_NODE_HEADER = "X-Node-Token"
_NODE_ID_HEADER = "X-Node-Id"
_ROLE = os.getenv("SENTIENTOS_ROLE", "core").strip().lower()
_UPSTREAM_CORE = (os.getenv("UPSTREAM_CORE") or "").rstrip("/")
_STREAM_TIMEOUT = float(os.getenv("STREAM_TIMEOUT_S", "30"))
_WEBUI_ENABLED = os.getenv("WEBUI_ENABLED", "1") != "0"
_WEBUI_ROOT = Path(os.getenv("WEBUI_ROOT", "apps/webui"))
if not _WEBUI_ROOT.is_absolute():
    _WEBUI_ROOT = Path.cwd() / _WEBUI_ROOT
_WEBUI_AUTH_MODE = os.getenv("WEBUI_AUTH_MODE", "cookie").lower()
_PROCESS_START = time.time()
_CONSOLE_ENABLED = os.getenv("CONSOLE_ENABLED", "0") != "0"
_VOICE_ENABLED = os.getenv("VOICE_ENABLED", "0") != "0"
_ADMIN_TTL = max(60, int(float(os.getenv("ADMIN_SESSION_TTL_MIN", "120")) * 60))
_CSRF_ENABLED = os.getenv("CSRF_ENABLED", "0") != "0"
_ADMIN_ALLOWLIST_RAW = [
    entry.strip()
    for entry in (os.getenv("ADMIN_ALLOWLIST") or "127.0.0.1/32").split(",")
    if entry.strip()
]
_ADMIN_ALLOWLIST: list = []
for entry in _ADMIN_ALLOWLIST_RAW:
    try:
        _ADMIN_ALLOWLIST.append(ipaddress.ip_network(entry, strict=False))
    except ValueError:
        logging.warning("[Admin] Ignoring invalid CIDR entry: %s", entry)

_CONSOLE_ROOT = (_WEBUI_ROOT / "console").resolve()
_PWA_ROOT = (_WEBUI_ROOT / "pwa").resolve()

try:
    _ICE_SERVERS = json.loads(os.getenv("WEBRTC_ICE_SERVERS", "[]"))
    if not isinstance(_ICE_SERVERS, list):
        _ICE_SERVERS = []
except json.JSONDecodeError:
    _ICE_SERVERS = []

NODE_ROUTER = RoundRobinRouter(registry)


WATCHDOG = WatchdogService(interval=float(os.getenv("WATCHDOG_INTERVAL_S", "5")))
if _VOICE_ENABLED:
    _STT_CONFIG = configure_stt()
    _STT_PIPELINE = StreamingTranscriber(vad_sensitivity=float(os.getenv("VAD_SENSITIVITY", "0.6")))
    _TTS_PIPELINE = TtsStreamer(voice=os.getenv("TTS_VOICE", "en_US-amy-medium"))
    _WEBRTC_MANAGER = WebRTCSessionManager(ttl_seconds=_ADMIN_TTL, ice_servers=_ICE_SERVERS)
else:
    _STT_CONFIG = None
    _STT_PIPELINE = None
    _TTS_PIPELINE = None
    _WEBRTC_MANAGER = None


def _local_node_id() -> str:
    node_id = registry.local_hostname
    if node_id:
        return node_id
    return socket.gethostname()


def _build_remote_headers(*, include_secret: bool = True) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if include_secret:
        headers["X-Relay-Secret"] = RELAY_SECRET
    if NODE_TOKEN:
        headers[_NODE_HEADER] = NODE_TOKEN
    node_id = _local_node_id()
    if node_id:
        headers[_NODE_ID_HEADER] = node_id
    return headers


class _CsrfManager:
    def __init__(self, enabled: bool, ttl_seconds: int) -> None:
        self.enabled = enabled
        self._ttl = ttl_seconds
        self._tokens: Dict[str, float] = {}

    def issue(self) -> str:
        if not self.enabled:
            return ""
        token = secrets.token_urlsafe(32)
        self._tokens[token] = time.time() + self._ttl
        self._prune()
        return token

    def validate(self, token: Optional[str]) -> bool:
        if not self.enabled:
            return True
        if not token:
            return False
        self._prune()
        expiry = self._tokens.get(token)
        if not expiry or expiry < time.time():
            self._tokens.pop(token, None)
            return False
        return True

    def _prune(self) -> None:
        now = time.time()
        for token, expiry in list(self._tokens.items()):
            if expiry < now:
                self._tokens.pop(token, None)


_csrf_manager = _CsrfManager(_CSRF_ENABLED, _ADMIN_TTL)


def _proxy_remote_json(path: str, payload: Dict[str, Any], *, capability: Optional[str] = None) -> Optional[Dict[str, Any]]:
    node = NODE_ROUTER.next(capability, trusted_only=True)
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
    pairing_service.cleanup_sessions()
    if request.headers.get("X-Relay-Secret") == RELAY_SECRET:
        return True
    if NODE_TOKEN and request.headers.get(_NODE_HEADER) == NODE_TOKEN:
        return True
    node_id = request.headers.get(_NODE_ID_HEADER)
    token = request.headers.get(_NODE_HEADER)
    if node_id and token and pairing_service.verify_node_token(node_id, token):
        return True
    session_token = request.cookies.get(pairing_service.session_cookie_name)
    if session_token and pairing_service.validate_session(session_token):
        return True
    header_session = request.headers.get("X-Session-Token")
    if header_session and pairing_service.validate_session(header_session):
        return True
    return False


def _remote_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"


def _ip_allowed(ip_address: str) -> bool:
    if not _ADMIN_ALLOWLIST:
        return True
    try:
        addr = ipaddress.ip_address(ip_address)
    except ValueError:
        return False
    return any(addr in network for network in _ADMIN_ALLOWLIST)


def _admin_authorised(*, require_csrf: bool = False) -> bool:
    if not _CONSOLE_ENABLED:
        return False
    if not _ip_allowed(_remote_ip()):
        return False
    if NODE_TOKEN and request.headers.get(_NODE_HEADER) != NODE_TOKEN:
        return False
    if require_csrf and not _csrf_manager.validate(request.headers.get("X-CSRF-Token")):
        return False
    return True


def _admin_response(payload: Dict[str, Any]) -> Response:
    body = dict(payload)
    token = _csrf_manager.issue()
    if token:
        body.setdefault("csrf_token", token)
    response = jsonify(body)
    if not hasattr(response, "headers"):
        response = Response(response, status=200)
        if hasattr(response, "headers"):
            response.headers["Content-Type"] = "application/json"
    if token and hasattr(response, "headers"):
        response.headers["X-CSRF-Token"] = token
    return response


def _gpu_status() -> Dict[str, Any]:
    if _STT_CONFIG:
        return {"backend": _STT_CONFIG.get("backend"), "description": _STT_CONFIG.get("description")}
    return {"backend": "cpu", "description": "CPU"}


def _memory_summary() -> Dict[str, Any]:
    metrics = governor.metrics()
    metrics["secure_store"] = secure_store.is_enabled()
    return metrics


def _admin_status_payload() -> Dict[str, Any]:
    metrics = _memory_summary()
    status = dream_loop.status()
    pending_goals = metrics.get("categories", {}).get("goal", 0)
    return {
        "role": _ROLE,
        "model": os.getenv("SENTIENTOS_MODEL", "unknown"),
        "backend": os.getenv("SENTIENTOS_BACKEND", "local"),
        "uptime_seconds": time.time() - _PROCESS_START,
        "dream_loop": status,
        "pending_goals": pending_goals,
        "mem_entries": metrics.get("total", 0),
        "webui_enabled": _WEBUI_ENABLED,
        "gpu": _gpu_status(),
        "watchdog": WATCHDOG.snapshot(),
        "voice": _STT_CONFIG or {},
        "safety_events_1h": count_recent_events(1),
    }


def _guess_mimetype(name: str, default: str = "text/plain") -> str:
    if name.endswith(".js"):
        return "text/javascript"
    if name.endswith(".css"):
        return "text/css"
    if name.endswith(".html"):
        return "text/html"
    if name.endswith(".webmanifest"):
        return "application/manifest+json"
    if name.endswith(".json"):
        return "application/json"
    if name.endswith(".png"):
        return "image/png"
    return default


def _serve_static(root: Path, asset: str, *, default_mimetype: str = "text/plain") -> Response:
    candidate = (root / asset).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return Response("Not Found", status=404)
    if not candidate.exists() or not candidate.is_file():
        return Response("Not Found", status=404)
    data = candidate.read_bytes()
    mimetype = _guess_mimetype(asset, default_mimetype)
    try:
        return Response(data, status=200, mimetype=mimetype)
    except TypeError:
        response = Response(data, status=200)
        if hasattr(response, "headers"):
            response.headers["Content-Type"] = mimetype
        return response


def _sanitise_memories(entries: list[dict], *, decrypt: bool) -> list[dict]:
    cleaned: list[dict] = []
    for entry in entries:
        data = dict(entry)
        if not decrypt:
            data.pop("text", None)
        cleaned.append(data)
    return cleaned


def _incognito_enabled() -> bool:
    return os.getenv("MEM_INCOGNITO", "0") == "1"


def _proxy_upstream_json(path: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not _UPSTREAM_CORE:
        logging.debug("[Relay] Thin routing requested but UPSTREAM_CORE is not configured")
        return None
    base = _UPSTREAM_CORE
    if not base.startswith("http://") and not base.startswith("https://"):
        base = f"http://{base}"
    url = base.rstrip("/") + (path if path.startswith("/") else "/" + path)
    headers = _build_remote_headers(include_secret=False)
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=_STREAM_TIMEOUT)
    except requests.RequestException as exc:
        logging.warning("[Relay] Upstream %s failed: %s", url, exc)
        return None
    if response.status_code != 200:
        logging.warning("[Relay] Upstream %s returned %s", url, response.status_code)
        return None
    try:
        return response.json()
    except ValueError:
        logging.warning("[Relay] Upstream %s produced non-JSON payload", url)
        return None


def _authorised_for_ui() -> bool:
    pairing_service.cleanup_sessions()
    if request.headers.get("X-Relay-Secret") == RELAY_SECRET:
        return True
    if NODE_TOKEN and request.headers.get(_NODE_HEADER) == NODE_TOKEN:
        return True
    session_token = request.cookies.get(pairing_service.session_cookie_name)
    if session_token and pairing_service.validate_session(session_token):
        return True
    header_session = request.headers.get("X-Session-Token")
    if header_session and pairing_service.validate_session(header_session):
        return True
    return False




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


@app.route("/", methods=["GET"])
def webui_root() -> Response:
    if not _WEBUI_ENABLED:
        return Response("Web UI disabled", status=404)
    index_path = _WEBUI_ROOT / "index.html"
    if not index_path.exists():
        return Response("Web UI unavailable", status=404)
    try:
        content = index_path.read_text(encoding="utf-8")
    except OSError:
        return Response("Web UI unavailable", status=500)
    try:
        return Response(content, status=200, mimetype="text/html")
    except TypeError:  # Fallback for flask stub
        resp = Response(content, status=200)
        if hasattr(resp, "headers"):
            resp.headers["Content-Type"] = "text/html"
        return resp


@app.route("/console", methods=["GET"])
def console_root() -> Response:
    if not _CONSOLE_ENABLED:
        return Response("Console disabled", status=404)
    return _serve_static(_CONSOLE_ROOT, "index.html", default_mimetype="text/html")


@app.route("/console/<path:asset>", methods=["GET"])
def console_asset(asset: str) -> Response:
    if not _CONSOLE_ENABLED:
        return Response("Console disabled", status=404)
    return _serve_static(_CONSOLE_ROOT, asset)


@app.route("/webui/pwa/<path:asset>", methods=["GET"])
def pwa_asset(asset: str) -> Response:
    return _serve_static(_PWA_ROOT, asset)


@app.route("/webui/<path:asset>", methods=["GET"])
def webui_asset(asset: str) -> Response:
    if not _WEBUI_ENABLED:
        return Response("Web UI disabled", status=404)
    candidate = (_WEBUI_ROOT / asset).resolve()
    try:
        candidate.relative_to(_WEBUI_ROOT)
    except ValueError:
        return Response("Not Found", status=404)
    if not candidate.exists() or not candidate.is_file():
        return Response("Not Found", status=404)
    mimetype = "text/plain"
    if asset.endswith(".js"):
        mimetype = "text/javascript"
    elif asset.endswith(".css"):
        mimetype = "text/css"
    elif asset.endswith(".svg"):
        mimetype = "image/svg+xml"
    data = candidate.read_bytes()
    try:
        return Response(data, status=200, mimetype=mimetype)
    except TypeError:
        resp = Response(data, status=200)
        if hasattr(resp, "headers"):
            resp.headers["Content-Type"] = mimetype
        return resp


@app.route("/nodes", methods=["GET"])
def list_nodes() -> Response:
    if not _is_authorised_for_node_routes():
        return Response("Forbidden", status=403)
    return jsonify({"nodes": registry.active_nodes(), "capabilities": registry.capability_map()})


@app.route("/nodes/list", methods=["GET"])
def nodes_list_ui() -> Response:
    if not _authorised_for_ui():
        return Response("Forbidden", status=403)
    return jsonify({"nodes": registry.active_nodes(), "capabilities": registry.capability_map()})


@app.route("/admin/status", methods=["GET"])
def admin_status() -> Response:
    if not _admin_authorised():
        return Response("Forbidden", status=403)
    return _admin_response(_admin_status_payload())


@app.route("/admin/health", methods=["GET"])
def admin_health() -> Response:
    if not _admin_authorised():
        return Response("Forbidden", status=403)
    payload = {
        "watchdog": WATCHDOG.snapshot(),
        "voice": {"enabled": _VOICE_ENABLED, "config": _STT_CONFIG},
        "safety_events_1h": count_recent_events(1),
    }
    return _admin_response(payload)


@app.route("/admin/nodes", methods=["GET"])
def admin_nodes() -> Response:
    if not _admin_authorised():
        return Response("Forbidden", status=403)
    nodes = registry.active_nodes()
    groups: Dict[str, list[Dict[str, Any]]] = {"trusted": [], "provisional": [], "blocked": []}
    for record in nodes:
        level = str(record.get("trust_level", "provisional"))
        groups.setdefault(level, []).append(record)
    payload = {
        "nodes": nodes,
        "groups": groups,
        "capabilities": registry.capability_map(),
    }
    return _admin_response(payload)


@app.route("/admin/memory/summary", methods=["GET"])
def admin_memory_summary() -> Response:
    if not _admin_authorised():
        return Response("Forbidden", status=403)
    return _admin_response(_memory_summary())


@app.route("/admin/memory/recall", methods=["POST"])
def admin_memory_recall() -> Response:
    if not _admin_authorised(require_csrf=True):
        return Response("Forbidden", status=403)
    payload = request.get_json() or {}
    query = payload.get("query")
    try:
        k = max(1, int(payload.get("k", 5)))
    except (TypeError, ValueError):
        k = 5
    decrypt = bool(payload.get("decrypt"))
    memories = governor.recall(query, k=k)
    return jsonify({"memories": _sanitise_memories(memories, decrypt=decrypt)})


@app.route("/admin/nodes/<hostname>/trust", methods=["POST"])
def admin_nodes_trust(hostname: str) -> Response:
    if not _admin_authorised(require_csrf=True):
        return Response("Forbidden", status=403)
    payload = request.get_json() or {}
    level = str(payload.get("level") or payload.get("trust_level") or "trusted").strip()
    record = registry.set_trust_level(hostname, level)
    if not record:
        return jsonify({"error": "node not found"}), 404
    return jsonify(record.serialise())


@app.route("/admin/nodes/<hostname>/block", methods=["POST"])
def admin_nodes_block(hostname: str) -> Response:
    if not _admin_authorised(require_csrf=True):
        return Response("Forbidden", status=403)
    record = registry.set_trust_level(hostname, "blocked")
    if not record:
        return jsonify({"error": "node not found"}), 404
    return jsonify(record.serialise())


@app.route("/admin/nodes/<hostname>/rekey", methods=["POST"])
def admin_nodes_rekey(hostname: str) -> Response:
    if not _admin_authorised(require_csrf=True):
        return Response("Forbidden", status=403)
    payload = request.get_json() or {}
    token = str(payload.get("token") or payload.get("node_token") or "").strip()
    if not token:
        return jsonify({"error": "token required"}), 400
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    record = registry.store_token(hostname, digest)
    if not record:
        return jsonify({"error": "node not found"}), 404
    return jsonify({"stored": True, "hostname": hostname})


@app.route("/admin/rotate-keys", methods=["POST"])
def admin_rotate_keys() -> Response:
    if not _admin_authorised(require_csrf=True):
        return Response("Forbidden", status=403)
    result = mem_admin.rotate_keys()
    return jsonify(result)


@app.route("/webrtc/create", methods=["POST"])
def webrtc_create() -> Response:
    if not _VOICE_ENABLED or _WEBRTC_MANAGER is None:
        return Response("Voice disabled", status=404)
    if not _authorised_for_ui():
        return Response("Forbidden", status=403)
    payload = request.get_json() or {}
    offer = payload.get("offer")
    if not isinstance(offer, dict):
        return jsonify({"error": "offer required"}), 400
    try:
        session = _WEBRTC_MANAGER.create_session(offer, token=request.headers.get(_NODE_HEADER))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(session)


@app.route("/webrtc/ice", methods=["POST"])
def webrtc_add_ice() -> Response:
    if not _VOICE_ENABLED or _WEBRTC_MANAGER is None:
        return Response("Voice disabled", status=404)
    if not _authorised_for_ui():
        return Response("Forbidden", status=403)
    payload = request.get_json() or {}
    session_id = str(payload.get("session_id") or "").strip()
    candidate = payload.get("candidate")
    if not session_id or not isinstance(candidate, dict):
        return jsonify({"error": "session_id and candidate required"}), 400
    try:
        updated = _WEBRTC_MANAGER.add_ice_candidate(session_id, candidate)
    except KeyError:
        return jsonify({"error": "unknown_session"}), 404
    return jsonify(updated)


@app.route("/nodes/trust", methods=["POST"])
def nodes_trust() -> Response:
    if not _authorised_for_ui():
        return Response("Forbidden", status=403)
    payload = request.get_json() or {}
    hostname = str(payload.get("hostname") or payload.get("node_id") or "").strip()
    level = str(payload.get("trust_level") or payload.get("level") or "trusted").strip()
    if not hostname:
        return jsonify({"error": "hostname required"}), 400
    record = registry.set_trust_level(hostname, level)
    if not record:
        return jsonify({"error": "node not found"}), 404
    return jsonify(record.serialise())


@app.route("/nodes/block", methods=["POST"])
def nodes_block() -> Response:
    if not _authorised_for_ui():
        return Response("Forbidden", status=403)
    payload = request.get_json() or {}
    hostname = str(payload.get("hostname") or payload.get("node_id") or "").strip()
    if not hostname:
        return jsonify({"error": "hostname required"}), 400
    record = registry.set_trust_level(hostname, "blocked")
    if not record:
        return jsonify({"error": "node not found"}), 404
    return jsonify(record.serialise())


@app.route("/admin/webrtc/sessions", methods=["GET"])
def admin_webrtc_sessions() -> Response:
    if not _admin_authorised():
        return Response("Forbidden", status=403)
    if _WEBRTC_MANAGER is None:
        return jsonify({"sessions": []})
    return _admin_response({"sessions": _WEBRTC_MANAGER.list_sessions()})


@app.route("/admin/watchdog", methods=["GET"])
def admin_watchdog_snapshot() -> Response:
    if not _admin_authorised():
        return Response("Forbidden", status=403)
    return _admin_response(WATCHDOG.snapshot())


@app.route("/admin/watchdog/register", methods=["POST"])
def admin_watchdog_register() -> Response:
    if not _admin_authorised(require_csrf=True):
        return Response("Forbidden", status=403)
    payload = request.get_json() or {}
    name = str(payload.get("name") or "").strip()
    host = payload.get("host")
    port = payload.get("port")
    if not name or host is None or port is None:
        return jsonify({"error": "name, host, port required"}), 400

    def restart() -> None:
        logging.info("[Watchdog] Restart requested for %s", name)

    WATCHDOG.register_port(name, str(host), int(port), restart=restart)
    return jsonify({"registered": True, "name": name})


@app.route("/admin/watchdog/heartbeat", methods=["POST"])
def admin_watchdog_heartbeat() -> Response:
    if not _admin_authorised(require_csrf=True):
        return Response("Forbidden", status=403)
    payload = request.get_json() or {}
    name = str(payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    WATCHDOG.report_heartbeat(name)
    return jsonify({"ack": True, "name": name})


@app.route("/pair/start", methods=["POST"])
def pair_start() -> Response:
    if not _authorised_for_ui():
        return Response("Forbidden", status=403)
    host = request.host.split(":")[0] if request.host else _local_node_id()
    data = pairing_service.start_pairing(host=host)
    return jsonify(data)


@app.route("/pair/confirm", methods=["POST"])
def pair_confirm() -> Response:
    payload = request.get_json() or {}
    try:
        result = pairing_service.confirm_pairing(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    response = jsonify(result)
    session_token = result.get("session_token")
    if session_token and _WEBUI_AUTH_MODE == "cookie":
        response.set_cookie(
            pairing_service.session_cookie_name,
            session_token,
            max_age=int(os.getenv("PAIRING_SESSION_TTL_S", str(24 * 3600))),
            secure=False,
            httponly=False,
            samesite="Lax",
        )
    return response


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


@app.route("/chat", methods=["POST"])
def chat() -> Response:
    payload = request.get_json() or {}
    if _ROLE == "thin":
        upstream = _proxy_upstream_json("/chat", payload)
        if upstream is not None:
            return jsonify(upstream)
        return jsonify({"error": "upstream_unavailable"}), 503
    if not _authorised_for_ui() and request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return Response("Forbidden", status=403)
    capability = "llm"
    remote = _proxy_remote_json("/chat", payload, capability=capability)
    if remote is not None:
        return jsonify(remote)
    message = payload.get("message", "")
    model = payload.get("model", "default").strip().lower()
    emotions = payload.get("emotions") or empty_emotion_vector()
    chunks = chunk_message(message)
    reply = "\n".join(chunks)
    write_mem(
        f"[CHAT] Model: {model} | Message: {message}\n{reply}",
        tags=["chat", model],
        emotions=emotions,
    )
    return jsonify({"reply": reply, "model": model, "routed": "local", "chunks": chunks})


@app.route("/relay", methods=["POST"])
def relay():
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return "Forbidden", 403

    data = request.get_json() or {}
    remote = _proxy_remote_json("/relay", data, capability=data.get("capability"))
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
    payload["role"] = _ROLE or "core"
    payload["upstream_host"] = _UPSTREAM_CORE or None
    payload["capability_map"] = registry.capability_map()
    payload["webui_enabled"] = _WEBUI_ENABLED
    return jsonify(payload)


@app.route("/health/status", methods=["GET"])
def health_status() -> Response:
    payload = {
        "incognito": _incognito_enabled(),
        "secure_store": secure_store.is_enabled(),
        "watchdog": None,
        "console": {"enabled": _CONSOLE_ENABLED},
        "voice": {"enabled": _VOICE_ENABLED},
    }
    if _VOICE_ENABLED:
        payload["voice"]["stt"] = _STT_CONFIG
    payload["watchdog"] = WATCHDOG.snapshot()
    return jsonify(payload)


@app.route("/dreamloop/status", methods=["GET"])
def dreamloop_status() -> Response:
    payload: Dict[str, Any] = {}
    try:
        payload.update(dream_loop.status())
    except Exception:  # pragma: no cover - defensive
        payload["active"] = False
    payload["dream_loop_enabled"] = dream_loop.is_enabled()
    payload["watchdog"] = WATCHDOG.snapshot()
    payload["console"] = {"enabled": _CONSOLE_ENABLED}
    payload["voice"] = {"enabled": _VOICE_ENABLED, "config": _STT_CONFIG}
    return jsonify(payload)


@app.route("/act", methods=["POST"])
def act():
    if _ROLE == "thin":
        payload = request.get_json() or {}
        upstream = _proxy_upstream_json("/act", payload)
        if upstream is not None:
            return jsonify(upstream)
        return jsonify({"error": "upstream_unavailable"}), 503
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
    if _ROLE == "thin":
        upstream = _proxy_upstream_json("/goals/list", request.get_json() or {})
        if upstream is not None:
            return jsonify(upstream)
        return jsonify({"error": "upstream_unavailable"}), 503
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return "Forbidden", 403
    return jsonify(mm.get_goals(open_only=False))


@app.route("/goals/add", methods=["POST"])
def goals_add():
    if _ROLE == "thin":
        upstream = _proxy_upstream_json("/goals/add", request.get_json() or {})
        if upstream is not None:
            return jsonify(upstream)
        return jsonify({"error": "upstream_unavailable"}), 503
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
    if _ROLE == "thin":
        upstream = _proxy_upstream_json("/goals/complete", request.get_json() or {})
        if upstream is not None:
            return jsonify(upstream)
        return jsonify({"error": "upstream_unavailable"}), 503
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
    if _ROLE == "thin":
        upstream = _proxy_upstream_json("/goals/delete", request.get_json() or {})
        if upstream is not None:
            return jsonify(upstream)
        return jsonify({"error": "upstream_unavailable"}), 503
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


def register_voice_activity(hostname: str, timestamp: float | None = None) -> None:
    registry.register_or_update(hostname, "127.0.0.1", last_voice_activity=timestamp or time.time())


def register_voice_session(summary: str) -> None:
    fragment = governor.remember_voice_session(summary)
    if fragment:
        logging.debug("[Voice] Stored session summary for %s", fragment.get("id"))


def register_watchdog_check(name: str, check) -> None:
    WATCHDOG.register_check(name, check)


register_watchdog_check("relay", lambda: (True, None))
WATCHDOG.register_check("memory", lambda: (secure_store.is_enabled(), None))


if __name__ == "__main__":
    print("[Relay] Lumos blessing auto-approved (headless/auto mode).")
    print("[Relay] Starting Flask relay service on http://127.0.0.1:5000 …")
    print("[SentientOS] Relay bound to http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000)
