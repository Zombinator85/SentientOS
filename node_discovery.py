"""LAN discovery beacon for SentientOS nodes."""

from __future__ import annotations

import base64
import hmac
import hashlib
import json
import logging
import os
import platform
import socket
import threading
import time
from typing import Dict, Optional

from dotenv import load_dotenv

from node_registry import NODE_TOKEN, registry
from pairing_service import pairing_service

load_dotenv()

LOGGER = logging.getLogger(__name__)

PORT = 9020
_BEACON_INTERVAL = 3.0
_BANNER_TEMPLATE = "[SentientOS] {count} nodes linked: {names}"
_DEFAULT_API_PORT = int(os.getenv("SENTIENTOS_API_PORT", "5000"))
_DEFAULT_UI_PORT = int(os.getenv("SENTIENTOS_UI_PORT", "5000"))
_ROLE = os.getenv("SENTIENTOS_ROLE", "core")
_DISCOVERY_SECRET = os.getenv("LAN_DISCOVERY_SECRET")


def _local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _default_capabilities() -> Dict[str, object]:
    caps: Dict[str, object] = {
        "gpu": bool(os.getenv("CUDA_VISIBLE_DEVICES") or os.getenv("NVIDIA_VISIBLE_DEVICES")),
        "voice": os.getenv("SENTIENTOS_DISABLE_AUDIO", "0") != "1",
        "storage": os.getenv("SENTIENTOS_STORAGE", "local"),
        "os": platform.platform(),
        "llm": os.getenv("SENTIENTOS_LLM_CAPABLE", "1") == "1",
        "stt": os.getenv("SENTIENTOS_STT_CAPABLE", "0") == "1",
        "tts": os.getenv("SENTIENTOS_TTS_CAPABLE", "0") == "1",
    }
    if os.getenv("SENTIENTOS_NODE_ONLY") == "1":
        caps["mode"] = "node_only"
    if _ROLE:
        caps.setdefault("role", _ROLE)
    return caps


def _compute_hmac(payload: Dict[str, object]) -> tuple[str, str]:
    nonce = base64.urlsafe_b64encode(os.urandom(9)).decode("ascii").rstrip("=")
    body = dict(payload)
    body["nonce"] = nonce
    message = json.dumps(body, sort_keys=True).encode("utf-8")
    signature = hmac.new(_DISCOVERY_SECRET.encode("utf-8"), message, hashlib.sha256).digest()
    mac = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return nonce, mac


class NodeDiscovery:
    """Background UDP broadcaster/listener for SentientOS nodes."""

    def __init__(
        self,
        *,
        port: int = PORT,
        beacon_interval: float = _BEACON_INTERVAL,
        token: Optional[str] = None,
        capabilities: Optional[Dict[str, object]] = None,
    ) -> None:
        self.port = port
        self._hostname = socket.gethostname()
        self._ip = _local_ip()
        self._token = token or NODE_TOKEN
        self._capabilities = capabilities or _default_capabilities()
        self._interval = beacon_interval
        self._stop = threading.Event()
        self._broadcast_thread: Optional[threading.Thread] = None
        self._listen_thread: Optional[threading.Thread] = None
        self._last_banner: Optional[str] = None
        registry.set_local_identity(self._hostname)
        registry.register_or_update(
            self._hostname,
            self._ip,
            port=_DEFAULT_API_PORT,
            capabilities=self._capabilities,
            last_seen=time.time(),
            roles=[_ROLE] if _ROLE else None,
            pubkey_fingerprint=pairing_service.public_key_fingerprint,
        )

    @property
    def hostname(self) -> str:
        return self._hostname

    @property
    def ip(self) -> str:
        return self._ip

    def start(self) -> None:
        if self._broadcast_thread and self._broadcast_thread.is_alive():
            return
        self._broadcast_thread = threading.Thread(target=self._broadcast_loop, daemon=True)
        self._listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._broadcast_thread.start()
        self._listen_thread.start()
        banner = f"[SentientOS] Node discovery active on {self._ip}:{self.port}"
        LOGGER.info(banner)
        print(banner)
        self._render_linked_banner()

    def stop(self) -> None:
        self._stop.set()
        for thread in (self._broadcast_thread, self._listen_thread):
            if thread and thread.is_alive():
                thread.join(timeout=0.5)

    def _render_linked_banner(self) -> None:
        nodes = registry.active_nodes()
        names = ", ".join(node.get("hostname", "?") for node in nodes) or "none"
        banner = _BANNER_TEMPLATE.format(count=len(nodes), names=names)
        if banner != self._last_banner:
            self._last_banner = banner
            print(banner)

    def _broadcast_loop(self) -> None:
        payload = {
            "node_id": self._hostname,
            "hostname": self._hostname,
            "ip": self._ip,
            "api_port": _DEFAULT_API_PORT,
            "ui_port": _DEFAULT_UI_PORT,
            "capabilities": self._capabilities,
            "roles": [_ROLE] if _ROLE else [],
            "public_key_fpr": pairing_service.public_key_fingerprint,
        }
        encoded_payload = dict(payload)
        if _DISCOVERY_SECRET:
            nonce, mac = _compute_hmac(payload)
            encoded_payload["nonce"] = nonce
            encoded_payload["hmac"] = mac
        encoded = json.dumps(encoded_payload).encode("utf-8")
        while not self._stop.is_set():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    sock.settimeout(self._interval)
                    sock.sendto(encoded, ("<broadcast>", self.port))
            except OSError as exc:
                LOGGER.debug("Beacon broadcast failed: %s", exc, exc_info=True)
            self._stop.wait(self._interval)

    def _listen_loop(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("", self.port))
            except OSError as exc:
                LOGGER.warning("Unable to bind discovery listener on %s: %s", self.port, exc)
                return
            while not self._stop.is_set():
                try:
                    sock.settimeout(1.0)
                    data, addr = sock.recvfrom(4096)
                except socket.timeout:
                    continue
                except OSError as exc:
                    LOGGER.debug("Discovery listener error: %s", exc)
                    continue
                self._handle_packet(data, addr)

    def _handle_packet(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            payload = json.loads(data.decode("utf-8"))
        except json.JSONDecodeError:
            LOGGER.debug("Discarded malformed beacon from %s", addr)
            return
        if _DISCOVERY_SECRET:
            nonce = payload.get("nonce")
            mac = payload.get("hmac")
            if not isinstance(nonce, str) or not isinstance(mac, str):
                LOGGER.debug("Discarded unsigned beacon from %s", addr)
                return
            check_body = dict(payload)
            check_body.pop("hmac", None)
            message = json.dumps(check_body, sort_keys=True).encode("utf-8")
            expected = hmac.new(_DISCOVERY_SECRET.encode("utf-8"), message, hashlib.sha256).digest()
            compare = base64.urlsafe_b64encode(expected).decode("ascii").rstrip("=")
            if compare != mac:
                LOGGER.debug("Discarded beacon with invalid signature from %s", addr)
                return
        hostname = payload.get("node_id") or payload.get("hostname")
        if hostname == self._hostname:
            return
        ip = payload.get("ip") or addr[0]
        port = int(payload.get("api_port", payload.get("port", 5000)))
        capabilities = payload.get("capabilities") if isinstance(payload.get("capabilities"), dict) else {}
        roles = payload.get("roles") if isinstance(payload.get("roles"), list) else []
        fingerprint = payload.get("public_key_fpr")
        trust_level = payload.get("trust_level") if isinstance(payload.get("trust_level"), str) else None
        upstream_host = payload.get("upstream_host") if isinstance(payload.get("upstream_host"), str) else None
        registry.register_or_update(
            str(hostname),
            str(ip),
            port=port,
            capabilities=capabilities,
            last_seen=time.time(),
            roles=roles,
            pubkey_fingerprint=fingerprint,
            trust_level=trust_level,
            upstream_host=upstream_host,
        )
        LOGGER.info("Discovered node %s@%s:%s", hostname, ip, port)
        self._render_linked_banner()


discovery = NodeDiscovery()

__all__ = ["NodeDiscovery", "discovery", "PORT"]
