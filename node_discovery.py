"""LAN discovery beacon for SentientOS nodes."""

from __future__ import annotations

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

load_dotenv()

LOGGER = logging.getLogger(__name__)

PORT = 9020
_BEACON_INTERVAL = 3.0
_BANNER_TEMPLATE = "[SentientOS] {count} nodes linked: {names}"


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
    }
    if os.getenv("SENTIENTOS_NODE_ONLY") == "1":
        caps["mode"] = "node_only"
    return caps


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
            port=5000,
            capabilities=self._capabilities,
            last_seen=time.time(),
        )

    @property
    def hostname(self) -> str:
        return self._hostname

    @property
    def ip(self) -> str:
        return self._ip

    def start(self) -> None:
        if not self._token:
            LOGGER.warning("Node discovery requires NODE_TOKEN; discovery disabled.")
            return
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
            "id": self._hostname,
            "ip": self._ip,
            "port": 5000,
            "capabilities": self._capabilities,
            "token": self._token,
        }
        encoded = json.dumps(payload).encode("utf-8")
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
        token = payload.get("token")
        if not token or token != self._token:
            return
        hostname = payload.get("id") or payload.get("hostname")
        if hostname == self._hostname:
            return
        ip = payload.get("ip") or addr[0]
        port = int(payload.get("port", 5000))
        capabilities = payload.get("capabilities") if isinstance(payload.get("capabilities"), dict) else {}
        registry.register_or_update(
            str(hostname),
            str(ip),
            port=port,
            capabilities=capabilities,
            last_seen=time.time(),
        )
        LOGGER.info("Discovered node %s@%s:%s", hostname, ip, port)
        self._render_linked_banner()


discovery = NodeDiscovery()

__all__ = ["NodeDiscovery", "discovery", "PORT"]
