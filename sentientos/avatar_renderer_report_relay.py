"""Opt-in Windows-edge relay for Godot renderer self-reports.

Godot sends bounded JSON to an IPv4/IPv6 loopback UDP port. This process
validates the report, then forwards the exact payload over an injected mTLS
client and HMAC bridge identity. Loopback UDP does not authenticate Godot; the
authenticated principal is the edge relay and the report remains a renderer
self-report.
"""
from __future__ import annotations

import ipaddress
import json
import socket
import threading
from dataclasses import dataclass
from typing import Any

from .avatar_renderer_report_ingress import (
    MAX_RENDERER_REPORT_BYTES,
    RendererReportIngressError,
    renderer_report_observation,
)
from .gaming_companion_bridge import CompanionBridgeError, encode_message
from .gaming_companion_bridge_runtime import (
    CompanionBridgeLoopbackClient,
    CompanionBridgeTransportError,
)
from .gaming_companion_tls_transport import CompanionBridgeMutualTLSClient


@dataclass(frozen=True, slots=True)
class RendererReportRelayStatus:
    running: bool
    received: int
    forwarded: int
    rejected: int
    indeterminate: int
    last_message_id: str | None
    last_failure: str | None
    last_delivery_state: str | None


class WindowsRendererReportRelay:
    """Accept one exact renderer identity over loopback and forward via mTLS."""

    def __init__(self, *, client: CompanionBridgeMutualTLSClient,
                 source_id: str, session_id: str, generation_id: str,
                 source_key: bytes, renderer_generation_id: str,
                 bind_address: str = "127.0.0.1", port: int = 0) -> None:
        if not isinstance(client, CompanionBridgeMutualTLSClient):
            raise CompanionBridgeError("renderer_relay_mutual_tls_client_required")
        try:
            address = ipaddress.ip_address(bind_address)
        except ValueError as exc:
            raise CompanionBridgeError("renderer_relay_loopback_address_invalid") from exc
        if not address.is_loopback:
            raise CompanionBridgeError("renderer_relay_loopback_address_required")
        if type(port) is not int or not 0 <= port <= 65535:
            raise CompanionBridgeError("renderer_relay_udp_port_invalid")
        if not isinstance(source_key, bytes) or len(source_key) < 32:
            raise CompanionBridgeError("bridge_key_too_short")
        if not isinstance(renderer_generation_id, str) or not renderer_generation_id.startswith("godot-demo-"):
            raise CompanionBridgeError("renderer_relay_renderer_generation_invalid")
        # Validate configured bridge identities before binding the local socket.
        encode_message(kind="renderer_report", source_id=source_id,
            session_id=session_id, generation_id=generation_id, sequence=1,
            payload={"probe": True}, key=source_key,
            created_at="2000-01-01T00:00:00+00:00")
        self._client = client
        self._source_id = source_id
        self._session_id = session_id
        self._generation_id = generation_id
        self._source_key = bytearray(source_key)
        self._renderer_generation_id = renderer_generation_id
        self._bind_address = str(address)
        self._family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
        self._requested_port = port
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._received = 0
        self._forwarded = 0
        self._rejected = 0
        self._indeterminate = 0
        self._last_message_id: str | None = None
        self._last_failure: str | None = None
        self._last_delivery_state: str | None = None
        self._started_once = False

    def start(self) -> int:
        with self._lock:
            if self._started_once:
                raise CompanionBridgeError("renderer_relay_generation_rotation_required")
            self._started_once = True
            listener = socket.socket(self._family, socket.SOCK_DGRAM)
            try:
                listener.bind((self._bind_address, self._requested_port))
                listener.settimeout(0.2)
            except OSError:
                listener.close()
                raise
            self._socket = listener
            self._stop.clear()
            self._thread = threading.Thread(target=self._run,
                name="sentientos-renderer-report-edge-relay", daemon=True)
            self._thread.start()
            return int(listener.getsockname()[1])

    def status(self) -> RendererReportRelayStatus:
        with self._lock:
            return RendererReportRelayStatus(
                bool(self._thread and self._thread.is_alive() and not self._stop.is_set()),
                self._received, self._forwarded, self._rejected, self._indeterminate,
                self._last_message_id, self._last_failure, self._last_delivery_state,
            )

    def close(self) -> None:
        with self._lock:
            self._stop.set()
            listener, thread = self._socket, self._thread
        if listener is not None:
            listener.close()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        if thread is not None and thread.is_alive():
            raise CompanionBridgeError("renderer_relay_shutdown_timeout")
        with self._lock:
            self._socket = None
            self._thread = None
            self._source_key[:] = b"\x00" * len(self._source_key)

    def _run(self) -> None:
        listener = self._socket
        if listener is None:
            return
        while not self._stop.is_set():
            try:
                packet, peer = listener.recvfrom(MAX_RENDERER_REPORT_BYTES + 1)
            except socket.timeout:
                continue
            except OSError:
                if not self._stop.is_set():
                    self._record_failure("renderer_relay_socket_failed", "not_sent")
                return
            with self._lock:
                self._received += 1
            try:
                if not ipaddress.ip_address(peer[0].split("%", 1)[0]).is_loopback:
                    raise RendererReportIngressError("renderer_relay_peer_not_loopback")
                if not packet or len(packet) > MAX_RENDERER_REPORT_BYTES:
                    raise RendererReportIngressError("renderer_relay_packet_size_invalid")
                report: Any = json.loads(packet.decode("utf-8"))
                if not isinstance(report, dict):
                    raise RendererReportIngressError("renderer_relay_report_invalid")
                renderer_report_observation(report)
                if report["renderer_generation_id"] != self._renderer_generation_id:
                    raise RendererReportIngressError("renderer_relay_renderer_generation_mismatch")
                report_session = report["session_id"] or self._session_id
                encoded = encode_message(kind="renderer_report", source_id=self._source_id,
                    session_id=report_session, generation_id=self._generation_id,
                    sequence=report["sequence"], payload=report,
                    key=bytes(self._source_key), created_at=report["reported_at"])
                acknowledgment = self._client.send(encoded)
            except CompanionBridgeTransportError as exc:
                self._record_failure(exc.code, exc.delivery_state, indeterminate=True)
            except (UnicodeError, json.JSONDecodeError, RendererReportIngressError,
                    CompanionBridgeError, OSError, ValueError, TypeError) as exc:
                label = str(exc.args[0]) if exc.args else type(exc).__name__
                self._record_failure(label[:128], "not_sent")
            else:
                with self._lock:
                    self._forwarded += 1
                    self._last_message_id = str(acknowledgment.payload.get("message_id") or "")
                    self._last_failure = None
                    self._last_delivery_state = "accepted"

    def _record_failure(self, reason: str, delivery_state: str,
                        *, indeterminate: bool = False) -> None:
        with self._lock:
            self._rejected += 1
            if indeterminate:
                self._indeterminate += 1
            self._last_failure = reason[:128]
            self._last_delivery_state = delivery_state


__all__ = ["RendererReportRelayStatus", "WindowsRendererReportRelay"]
