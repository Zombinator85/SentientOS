"""Authenticated WSL-core to Windows-edge avatar command delivery.

This owner is the reverse half of the companion bridge. TLS and the bridge
receiver authenticate transport identity and replay state; a separate
authority callback must verify the command's admission receipt before the
renderer sink can accept it. Sink acceptance is not evidence that a frame was
rendered or independently observed.
"""
from __future__ import annotations

import threading
import hashlib
import math
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol
from uuid import uuid4

from sentientos.control_api import require_authorization_for_request_types
from avatar_state import AvatarStateEmitter
from .gaming_companion_bridge import encode_message
from .gaming_companion_bridge import CompanionBridgeError, VerifiedBridgeMessage
from .gaming_companion_tls_transport import CompanionBridgeMutualTLSClient


class AvatarCommandRuntime(Protocol):
    def receive(self, timeout: float | None = None) -> VerifiedBridgeMessage: ...


ReceiptVerifier = Callable[[str, str, VerifiedBridgeMessage], bool]
RendererCommandSink = Callable[[Mapping[str, object], VerifiedBridgeMessage], bool]
AdmissionReceiptBuilder = Callable[[Any], Mapping[str, str]]


class MutualTLSAvatarCommandSender:
    """Send admitted chat output from WSL core to a Windows-edge mTLS peer.

    The authority receipt is resolved by an injected owner; this class does
    not turn a local authorization log into an independently verifiable
    receipt. Each call creates one envelope and never retries it.
    """

    def __init__(self, *, client: CompanionBridgeMutualTLSClient,
                 source_id: str, session_id: str | None, generation_id: str,
                 source_key: bytes,
                 admission_receipt_builder: AdmissionReceiptBuilder) -> None:
        if not isinstance(client, CompanionBridgeMutualTLSClient):
            raise CompanionBridgeError("avatar_command_mtls_client_required")
        if not isinstance(source_key, bytes) or len(source_key) < 32:
            raise CompanionBridgeError("bridge_key_too_short")
        if not callable(admission_receipt_builder):
            raise CompanionBridgeError("avatar_command_receipt_builder_required")
        if (session_id is not None
                and (not isinstance(session_id, str) or not session_id or len(session_id) > 128)):
            raise CompanionBridgeError("avatar_command_session_id_invalid")
        self._client = client
        self._source_id, self._session_id = source_id, session_id
        self._generation_id = generation_id
        self._source_key = bytearray(source_key)
        self._receipt = admission_receipt_builder
        self._sequence = 0
        self._lock = threading.Lock()
        self._closed = False

    def send_command(self, payload: Mapping[str, object], authorization: Any, *,
                     session_id: str | None = None) -> VerifiedBridgeMessage:
        require_authorization_for_request_types(authorization,
            allowed_request_types=("avatar_emission",))
        selected_session = session_id if session_id is not None else self._session_id
        if (not isinstance(selected_session, str) or not selected_session
                or len(selected_session) > 128
                or (self._session_id is not None and selected_session != self._session_id)):
            raise CompanionBridgeError("avatar_command_session_id_invalid")
        receipt = self._receipt(authorization)
        if not isinstance(receipt, Mapping):
            raise CompanionBridgeError("avatar_command_admission_receipt_invalid")
        with self._lock:
            if self._closed:
                raise CompanionBridgeError("avatar_command_sender_closed")
            sequence = self._sequence + 1
            encoded = encode_message(kind="avatar_command", source_id=self._source_id,
                session_id=selected_session, generation_id=self._generation_id,
                sequence=sequence, payload=payload, key=bytes(self._source_key),
                admission=receipt)
            # Do not advance on local encoding failure. Once send begins, keep
            # the sequence consumed even if delivery becomes indeterminate.
            self._sequence = sequence
            return self._client.send(encoded)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._source_key[:] = b"\x00" * len(self._source_key)


@dataclass(frozen=True, slots=True)
class AvatarCommandDispatchStatus:
    state: str
    received: int
    accepted: int
    rejected: int
    last_message_id: str | None
    last_failure: str | None
    renderer_effect_proven: bool = False


class WindowsEdgeAvatarCommandDispatchOwner:
    """Deliver verified core commands to an edge renderer queue at most once."""

    def __init__(self, *, runtime: AvatarCommandRuntime,
                 receipt_verifier: ReceiptVerifier,
                 renderer_sink: RendererCommandSink,
                 poll_interval_seconds: float = 0.05,
                 max_consumed_receipts: int = 8192) -> None:
        if not callable(getattr(runtime, "receive", None)):
            raise CompanionBridgeError("avatar_command_runtime_required")
        if not callable(receipt_verifier) or not callable(renderer_sink):
            raise CompanionBridgeError("avatar_command_authority_callbacks_required")
        if (isinstance(poll_interval_seconds, bool)
                or not isinstance(poll_interval_seconds, (int, float))
                or not 0.01 <= poll_interval_seconds <= 1.0):
            raise CompanionBridgeError("avatar_command_poll_interval_invalid")
        if (isinstance(max_consumed_receipts, bool)
                or not isinstance(max_consumed_receipts, int)
                or max_consumed_receipts < 1):
            raise CompanionBridgeError("avatar_command_receipt_window_invalid")
        self._runtime = runtime
        self._verify = receipt_verifier
        self._sink = renderer_sink
        self._poll = float(poll_interval_seconds)
        self._max_consumed_receipts = max_consumed_receipts
        self._consumed_receipts: set[str] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        self._started = False
        self._state = "stopped"
        self._received = 0
        self._accepted = 0
        self._rejected = 0
        self._last_message_id: str | None = None
        self._last_failure: str | None = None

    def start(self) -> AvatarCommandDispatchStatus:
        with self._lock:
            if self._started:
                raise CompanionBridgeError("avatar_command_dispatch_already_started")
            self._started = True
            self._state = "running"
            self._worker = threading.Thread(target=self._run,
                name="sentientos-windows-edge-avatar-command-dispatch", daemon=True)
            self._worker.start()
        return self.status()

    def status(self) -> AvatarCommandDispatchStatus:
        with self._lock:
            return AvatarCommandDispatchStatus(self._state, self._received,
                self._accepted, self._rejected, self._last_message_id,
                self._last_failure)

    def close(self) -> None:
        self._stop.set()
        with self._lock:
            worker = self._worker
            if self._state != "failed":
                self._state = "stopping" if worker is not None else "stopped"
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=max(1.0, self._poll * 10))
        with self._lock:
            if worker is not None and worker.is_alive():
                self._state = "failed"
                self._last_failure = "avatar_command_dispatch_shutdown_timeout"
            elif self._state != "failed":
                self._state = "stopped"
            self._worker = None

    def dispatch_one(self, message: VerifiedBridgeMessage) -> bool:
        """Validate and deliver one authenticated command without retrying it."""
        if not isinstance(message, VerifiedBridgeMessage):
            raise CompanionBridgeError("avatar_command_verified_message_required")
        with self._lock:
            self._received += 1
            self._last_message_id = message.message_id
        try:
            if message.kind != "avatar_command" or not isinstance(message.admission, Mapping):
                raise CompanionBridgeError("avatar_command_message_required")
            receipt_id = message.admission.get("receipt_id")
            semantic_digest = message.admission.get("semantic_digest")
            if not isinstance(receipt_id, str) or not isinstance(semantic_digest, str):
                raise CompanionBridgeError("avatar_command_admission_unverified")
            with self._lock:
                if receipt_id in self._consumed_receipts:
                    raise CompanionBridgeError("avatar_command_admission_receipt_replayed")
                if len(self._consumed_receipts) >= self._max_consumed_receipts:
                    raise CompanionBridgeError("avatar_command_receipt_window_exhausted")
            if self._verify(receipt_id, semantic_digest, message) is not True:
                raise CompanionBridgeError("avatar_command_admission_unverified")
            with self._lock:
                if receipt_id in self._consumed_receipts:
                    raise CompanionBridgeError("avatar_command_admission_receipt_replayed")
                if len(self._consumed_receipts) >= self._max_consumed_receipts:
                    raise CompanionBridgeError("avatar_command_receipt_window_exhausted")
                self._consumed_receipts.add(receipt_id)
            if self._sink(message.payload, message) is not True:
                raise CompanionBridgeError("avatar_command_renderer_queue_rejected")
        except Exception as exc:
            reason = str(exc.args[0]) if exc.args else type(exc).__name__
            with self._lock:
                self._rejected += 1
                self._last_failure = reason[:128]
            return False
        with self._lock:
            self._accepted += 1
            self._last_failure = None
        return True

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                message = self._runtime.receive(timeout=self._poll)
            except CompanionBridgeError as exc:
                if exc.args and exc.args[0] == "bridge_receive_timeout":
                    continue
                with self._lock:
                    self._state = "failed"
                    self._last_failure = (str(exc.args[0]) if exc.args else type(exc).__name__)[:128]
                return
            except Exception as exc:
                with self._lock:
                    self._state = "failed"
                    self._last_failure = type(exc).__name__
                return
            self.dispatch_one(message)


class BridgeChatAvatarOutputEmitter:
    """SpeechEmitter-compatible visual-only output over the reverse bridge."""

    def __init__(self, sender: MutualTLSAvatarCommandSender) -> None:
        if not isinstance(sender, MutualTLSAvatarCommandSender):
            raise CompanionBridgeError("avatar_command_sender_required")
        self._sender = sender

    @staticmethod
    def _session_id(authorization: Any, metadata: Mapping[str, Any]) -> str | None:
        session_id = metadata.get("session_id")
        authorization_metadata = getattr(authorization, "metadata", None)
        if (isinstance(authorization_metadata, Mapping)
                and authorization_metadata.get("session_id") not in (None, session_id)):
            raise CompanionBridgeError("avatar_command_session_authorization_mismatch")
        if session_id is not None and (
                not isinstance(session_id, str) or not session_id or len(session_id) > 128):
            raise CompanionBridgeError("avatar_command_session_id_invalid")
        return session_id

    def emit_display_text(self, phrase: str, *, authorization: Any = None,
                          metadata: Mapping[str, Any] | None = None) -> dict[str, object]:
        require_authorization_for_request_types(authorization,
            allowed_request_types=("avatar_emission",))
        metadata = metadata if isinstance(metadata, Mapping) else {}
        session_id = self._session_id(authorization, metadata)
        output_digest = metadata.get("output_digest")
        turn_id = metadata.get("turn_id")
        if not isinstance(phrase, str) or not isinstance(output_digest, str):
            raise CompanionBridgeError("avatar_command_chat_output_binding_invalid")
        if turn_id is not None and not isinstance(turn_id, str):
            raise CompanionBridgeError("avatar_command_chat_output_binding_invalid")
        payload: dict[str, object] = {
            "output_mode": "chat_response_visual_only",
            "phrase": phrase[:2048], "expression": "rest", "motion": "nod",
            "mood": "calm", "intensity": 0.25,
            "output_digest": output_digest,
        }
        if turn_id:
            payload["turn_id"] = turn_id
        workload_mode = metadata.get("workload_mode")
        if workload_mode in {"normal", "gaming"}:
            payload["workload_mode"] = workload_mode
        acknowledgment = self._sender.send_command(payload, authorization, session_id=session_id)
        return {"status": "sent", "acknowledgment_message_id": acknowledgment.message_id,
                "renderer_effect_proven": False}

    def emit_phrase(self, phrase: str, *, authorization: Any = None,
                    metadata: Mapping[str, Any] | None = None,
                    started_at: float | None = None, speaking: bool | None = None,
                    muted: bool = False) -> dict[str, object]:
        """Carry local TTS timing boundaries to the edge without phoneme claims."""
        del started_at, speaking, muted
        require_authorization_for_request_types(authorization,
            allowed_request_types=("avatar_emission",))
        metadata = metadata if isinstance(metadata, Mapping) else {}
        session_id = self._session_id(authorization, metadata)
        output_digest, turn_id = metadata.get("output_digest"), metadata.get("turn_id")
        timing = metadata.get("speech_timing")
        if (not isinstance(phrase, str) or not isinstance(output_digest, str)
                or not isinstance(turn_id, str) or not isinstance(timing, Mapping)):
            raise CompanionBridgeError("avatar_command_chat_output_binding_invalid")
        payload: dict[str, object] = {
            "output_mode": "chat_response_visual_only", "phrase": phrase[:2048],
            "expression": "rest", "motion": "nod", "mood": "calm",
            "intensity": 0.25, "output_digest": output_digest,
            "turn_id": turn_id, "speech_timing": dict(timing),
        }
        workload_mode = metadata.get("workload_mode")
        if workload_mode in {"normal", "gaming"}:
            payload["workload_mode"] = workload_mode
        acknowledgment = self._sender.send_command(payload, authorization, session_id=session_id)
        return {"status": "sent", "acknowledgment_message_id": acknowledgment.message_id,
                "renderer_effect_proven": False}

    def emit_idle(self, *, authorization: Any = None,
                  metadata: Mapping[str, Any] | None = None) -> dict[str, object]:
        metadata = metadata if isinstance(metadata, Mapping) else {}
        session_id = self._session_id(authorization, metadata)
        turn_id = metadata.get("turn_id")
        payload: dict[str, object] = {
            "output_mode": "chat_response_visual_only", "phrase": "",
            "expression": "rest", "motion": "idle", "mood": "calm",
            "intensity": 0.0,
            "output_digest": hashlib.sha256(b"sentientos-avatar-idle-v1").hexdigest(),
            "turn_id": turn_id if isinstance(turn_id, str) and turn_id else "clear-" + uuid4().hex,
        }
        acknowledgment = self._sender.send_command(payload, authorization, session_id=session_id)
        return {"status": "sent", "acknowledgment_message_id": acknowledgment.message_id,
                "renderer_effect_proven": False}


class WindowsGodotAvatarStateQueue:
    """Map an admitted visual-only command to the local Godot state file.

    The normal avatar-state forwarder can carry this state to the same-host
    Godot renderer. State-file acceptance is not proof of a displayed frame.
    """

    def __init__(self, *, state_emitter: AvatarStateEmitter) -> None:
        if not isinstance(state_emitter, AvatarStateEmitter):
            raise CompanionBridgeError("avatar_command_state_emitter_required")
        self._emitter = state_emitter
        self._lock = threading.Lock()
        self._accepted = 0

    @property
    def accepted_count(self) -> int:
        with self._lock:
            return self._accepted

    def enqueue(self, payload: Mapping[str, object],
                message: VerifiedBridgeMessage) -> bool:
        if (type(message) is not VerifiedBridgeMessage
                or not isinstance(payload, Mapping)
                or payload.get("output_mode") != "chat_response_visual_only"):
            return False
        phrase = payload.get("phrase")
        expression, motion, mood = (payload.get(name) for name in
                                    ("expression", "motion", "mood"))
        intensity = payload.get("intensity")
        output_digest = payload.get("output_digest")
        turn_id = payload.get("turn_id")
        if isinstance(intensity, bool) or not isinstance(intensity, (int, float)):
            return False
        try:
            intensity_value = float(intensity)
            valid_intensity = math.isfinite(intensity_value) and 0 <= intensity_value <= 1
        except (OverflowError, TypeError, ValueError):
            valid_intensity = False
        if (not isinstance(phrase, str) or len(phrase) > 2048
                or any(not isinstance(value, str) or len(value) > 128
                       for value in (expression, motion, mood))
                or not valid_intensity
                or not isinstance(output_digest, str)
                or len(output_digest) != 64
                or any(char not in "0123456789abcdef" for char in output_digest)
                or (turn_id is not None and (not isinstance(turn_id, str) or len(turn_id) > 128))):
            return False
        metadata: dict[str, object] = {
            "source": "authenticated_sentientos_core_chat_command",
            "session_id": message.session_id,
            "output_mode": "chat_response_visual_only",
            "output_digest": output_digest,
            "transport_message_id": message.message_id,
            "transport_source_id": message.source_id,
            "transport_generation_id": message.generation_id,
            "transport_sequence": message.sequence,
            "renderer_effect_proven": False,
        }
        if turn_id:
            metadata["turn_id"] = turn_id
        workload = payload.get("workload_mode")
        if workload in {"normal", "gaming"}:
            metadata["workload_mode"] = workload
        speech_timing = payload.get("speech_timing")
        if speech_timing is not None:
            if (not isinstance(speech_timing, Mapping)
                    or speech_timing.get("session_id") != message.session_id
                    or speech_timing.get("turn_id") != turn_id):
                return False
            metadata["speech_timing"] = dict(speech_timing)
        state = {
            "mood": mood, "intensity": intensity_value,
            "expression": expression, "motion": motion,
            "current_phrase": phrase, "phrase_started_at": None,
            "is_speaking": False, "speaking": False, "muted": False,
            "viseme_timeline": [], "viseme_events": [],
            "metadata": metadata, "timestamp": time.time(),
        }
        try:
            self._emitter.emit(state)
        except (OSError, TypeError, ValueError):
            return False
        with self._lock:
            self._accepted += 1
        return True

__all__ = ["AvatarCommandDispatchStatus", "WindowsEdgeAvatarCommandDispatchOwner",
           "BridgeChatAvatarOutputEmitter", "WindowsGodotAvatarStateQueue",
           "MutualTLSAvatarCommandSender"]
