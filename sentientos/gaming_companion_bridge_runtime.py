"""Loopback-only transport lifecycle for authenticated companion messages.

This module receives and acknowledges verified envelopes. It does not execute
commands, grant authority, persist keys, or claim that a renderer report is an
independent observation. Callers supply already-custodied keys, active source
generations, and the existing :class:`CompanionBridgeReceiver`.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import queue
import socket
import threading
from typing import Any

from .gaming_companion_bridge import (
    MAX_ENVELOPE_BYTES,
    CompanionBridgeError,
    CompanionBridgeReceiver,
    VerifiedBridgeMessage,
    _canonical,
    encode_message,
    read_frame,
    send_frame,
)

_ACCEPT_TIMEOUT_SECONDS = 0.2


class CompanionBridgeTransportError(CompanionBridgeError):
    """Transport result with an explicit indication whether delivery is known."""

    def __init__(self, code: str, *, delivery_state: str) -> None:
        self.code = code
        self.delivery_state = delivery_state
        super().__init__(code)


def bridge_message_id(encoded: bytes) -> str:
    """Return the protocol message ID for a canonical encoded envelope.

    This helper identifies the message for acknowledgment correlation. It does
    not authenticate it; :class:`CompanionBridgeReceiver` does that separately.
    """
    if not isinstance(encoded, bytes) or not encoded or len(encoded) > MAX_ENVELOPE_BYTES:
        raise CompanionBridgeError("bridge_envelope_size_invalid")
    try:
        value = json.loads(encoded.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise CompanionBridgeError("bridge_envelope_json_invalid") from exc
    required = {"schema_version", "kind", "source_id", "session_id", "generation_id",
                "sequence", "created_at", "payload", "payload_digest", "admission", "signature"}
    if not isinstance(value, dict) or set(value) != required:
        raise CompanionBridgeError("bridge_envelope_schema_invalid")
    body = dict(value)
    body.pop("signature")
    if _canonical(value) != encoded:
        raise CompanionBridgeError("bridge_envelope_noncanonical")
    return hashlib.sha256(_canonical(body)).hexdigest()


@dataclass(frozen=True, slots=True)
class BridgeRuntimeStatus:
    running: bool
    port: int | None
    accepted_messages: int
    rejected_connections: int
    acknowledgment_failures: int


class CompanionBridgeLoopbackRuntime:
    """Receive one authenticated frame per loopback connection into a bounded queue."""

    def __init__(self, *, receiver: CompanionBridgeReceiver, acknowledgment_source_id: str,
                 acknowledgment_generation_id: str, acknowledgment_key: bytes,
                 port: int = 0, queue_capacity: int = 16, socket_timeout_seconds: float = 1.0,
                 clock: Any = None) -> None:
        if not isinstance(receiver, CompanionBridgeReceiver):
            raise CompanionBridgeError("bridge_receiver_required")
        if type(port) is not int or not 0 <= port <= 65535:
            raise CompanionBridgeError("bridge_loopback_port_invalid")
        if type(queue_capacity) is not int or not 1 <= queue_capacity <= 1024:
            raise CompanionBridgeError("bridge_queue_capacity_invalid")
        if (isinstance(socket_timeout_seconds, bool)
                or not isinstance(socket_timeout_seconds, (int, float))
                or not math.isfinite(float(socket_timeout_seconds))
                or socket_timeout_seconds <= 0 or socket_timeout_seconds > 30):
            raise CompanionBridgeError("bridge_socket_timeout_invalid")
        if not isinstance(acknowledgment_key, bytes) or len(acknowledgment_key) < 32:
            raise CompanionBridgeError("bridge_key_too_short")
        self._receiver = receiver
        self._ack_source_id = acknowledgment_source_id
        self._ack_generation_id = acknowledgment_generation_id
        self._ack_key = bytes(acknowledgment_key)
        self._clock = clock
        self._requested_port = port
        self._socket_timeout = float(socket_timeout_seconds)
        self._messages: queue.Queue[VerifiedBridgeMessage] = queue.Queue(maxsize=queue_capacity)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._listener: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._started_once = False
        self._accepted = 0
        self._rejected = 0
        self._acknowledgment_failures = 0
        self._ack_sequence = 0
        # Validate the acknowledgment identity and key before opening a socket.
        encode_message(kind="acknowledgment", source_id=self._ack_source_id,
            session_id="preflight", generation_id=self._ack_generation_id, sequence=1,
            payload={"message_id": "0" * 64}, key=self._ack_key,
            created_at="2000-01-01T00:00:00+00:00")

    def start(self) -> int:
        with self._lock:
            if self._thread is not None or self._started_once:
                raise CompanionBridgeError("bridge_runtime_generation_rotation_required")
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.settimeout(_ACCEPT_TIMEOUT_SECONDS)
            try:
                # Deliberately fixed to IPv4 loopback. No configurable bind host.
                listener.bind(("127.0.0.1", self._requested_port))
                listener.listen(8)
            except OSError:
                listener.close()
                raise
            self._listener = listener
            self._started_once = True
            self._stop.clear()
            self._thread = threading.Thread(target=self._serve, name="sentientos-companion-bridge",
                                            daemon=True)
            self._thread.start()
            return int(listener.getsockname()[1])

    def receive(self, timeout: float | None = None) -> VerifiedBridgeMessage:
        """Return the next verified transport message; this does not execute it."""
        try:
            return self._messages.get(timeout=timeout)
        except queue.Empty as exc:
            raise CompanionBridgeError("bridge_receive_timeout") from exc

    def status(self) -> BridgeRuntimeStatus:
        with self._lock:
            listener = self._listener
            thread = self._thread
            port = int(listener.getsockname()[1]) if listener is not None else None
            running = bool(thread is not None and thread.is_alive() and not self._stop.is_set())
            return BridgeRuntimeStatus(running, port, self._accepted, self._rejected,
                                       self._acknowledgment_failures)

    def close(self) -> None:
        with self._lock:
            listener = self._listener
            thread = self._thread
            self._stop.set()
        if listener is None:
            return
        # Wake accept without opening any non-loopback path.
        try:
            with socket.create_connection(("127.0.0.1", int(listener.getsockname()[1])),
                                          timeout=0.25):
                pass
        except OSError:
            pass
        listener.close()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(1.0, self._socket_timeout + 0.5))
        with self._lock:
            self._listener = None
            self._thread = None

    def __enter__(self) -> "CompanionBridgeLoopbackRuntime":
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _ack(self, message: VerifiedBridgeMessage, *, disposition: str = "accepted") -> bytes:
        return self._encode_ack(message.message_id, message.session_id, disposition)

    def _encode_ack(self, message_id: str, session_id: str, disposition: str) -> bytes:
        self._ack_sequence += 1
        if self._clock is None:
            created_at = None
        else:
            now = self._clock()
            created_at = now.isoformat() if hasattr(now, "isoformat") else str(now)
        return encode_message(kind="acknowledgment", source_id=self._ack_source_id,
            session_id=session_id, generation_id=self._ack_generation_id,
            sequence=self._ack_sequence,
            payload={"message_id": message_id, "disposition": disposition},
            key=self._ack_key, created_at=created_at)

    def _backpressure_ack(self, encoded: bytes) -> bytes:
        try:
            envelope = json.loads(encoded.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
            raise CompanionBridgeError("bridge_envelope_json_invalid") from exc
        if not isinstance(envelope, dict) or not isinstance(envelope.get("session_id"), str):
            raise CompanionBridgeError("bridge_envelope_schema_invalid")
        return self._encode_ack(bridge_message_id(encoded), envelope["session_id"],
                                "rejected_backpressure")

    def _serve(self) -> None:
        listener = self._listener
        if listener is None:
            return
        while not self._stop.is_set():
            try:
                connection, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                if not self._stop.is_set():
                    with self._lock:
                        self._rejected += 1
                break
            with connection:
                if self._messages.full():
                    with self._lock:
                        self._rejected += 1
                    try:
                        connection.settimeout(self._socket_timeout)
                        encoded = read_frame(connection)
                    except (CompanionBridgeError, OSError):
                        continue
                    try:
                        send_frame(connection, self._backpressure_ack(encoded))
                    except (CompanionBridgeError, OSError):
                        with self._lock:
                            self._acknowledgment_failures += 1
                    continue
                try:
                    connection.settimeout(self._socket_timeout)
                    encoded = read_frame(connection)
                    message = self._receiver.accept(encoded)
                    self._messages.put_nowait(message)
                except (CompanionBridgeError, OSError, queue.Full):
                    # The queue-full check occurs before receiver.accept, so a
                    # rejected backpressure frame does not consume its sequence.
                    with self._lock:
                        self._rejected += 1
                    continue
                with self._lock:
                    self._accepted += 1
                try:
                    send_frame(connection, self._ack(message))
                except (CompanionBridgeError, OSError):
                    # The message is already queued; a lost acknowledgment is
                    # an indeterminate client outcome, not a rejected message.
                    with self._lock:
                        self._acknowledgment_failures += 1


class CompanionBridgeLoopbackClient:
    """Send one frame to the fixed loopback endpoint and authenticate its ACK."""

    def __init__(self, *, port: int, acknowledgment_receiver: CompanionBridgeReceiver,
                 timeout_seconds: float = 1.0) -> None:
        if type(port) is not int or not 1 <= port <= 65535:
            raise CompanionBridgeError("bridge_loopback_port_invalid")
        if not isinstance(acknowledgment_receiver, CompanionBridgeReceiver):
            raise CompanionBridgeError("bridge_acknowledgment_receiver_required")
        if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
                or not math.isfinite(float(timeout_seconds))
                or timeout_seconds <= 0 or timeout_seconds > 30):
            raise CompanionBridgeError("bridge_socket_timeout_invalid")
        self._port = port
        self._ack_receiver = acknowledgment_receiver
        self._timeout = float(timeout_seconds)

    def send(self, encoded: bytes) -> VerifiedBridgeMessage:
        expected_message_id = bridge_message_id(encoded)
        try:
            connection = socket.create_connection(("127.0.0.1", self._port), timeout=self._timeout)
        except OSError as exc:
            raise CompanionBridgeTransportError("bridge_connection_unavailable",
                delivery_state="not_sent") from exc
        try:
            with connection:
                connection.settimeout(self._timeout)
                try:
                    send_frame(connection, encoded)
                    acknowledgment_bytes = read_frame(connection)
                except (OSError, CompanionBridgeError) as exc:
                    # Once connected, a partial send or lost ACK cannot prove
                    # whether the receiver queued the message.
                    raise CompanionBridgeTransportError("bridge_delivery_indeterminate",
                        delivery_state="indeterminate") from exc
        except CompanionBridgeTransportError:
            raise
        try:
            acknowledgment = self._ack_receiver.accept(acknowledgment_bytes)
        except CompanionBridgeError as exc:
            raise CompanionBridgeTransportError("bridge_acknowledgment_invalid",
                delivery_state="indeterminate") from exc
        if (acknowledgment.kind != "acknowledgment"
                or acknowledgment.payload.get("message_id") != expected_message_id):
            raise CompanionBridgeTransportError("bridge_acknowledgment_mismatch",
                delivery_state="indeterminate")
        disposition = acknowledgment.payload.get("disposition")
        if disposition == "rejected_backpressure":
            raise CompanionBridgeTransportError("bridge_backpressure_rejected",
                delivery_state="not_accepted")
        if disposition != "accepted":
            raise CompanionBridgeTransportError("bridge_acknowledgment_disposition_invalid",
                delivery_state="indeterminate")
        return acknowledgment
