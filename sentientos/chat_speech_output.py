"""Explicit, local-only speech output for production chat replies."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol
from uuid import uuid4

from control_plane import Decision, RequestType
from control_plane.task_admission import AdmissionResponse, admit_request

LOGGER = logging.getLogger(__name__)
MAX_SPOKEN_CHARS = 600


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


class LocalSpeechPlayer(Protocol):
    def available(self) -> bool: ...
    def speak(self, text: str) -> bool: ...
    def stop(self) -> None: ...


class Pyttsx3LocalSpeechPlayer:
    """Lazy adapter to the local OS voice backend; never selects network TTS."""

    def __init__(self) -> None:
        self._engine: Any | None = None
        self._lock = threading.Lock()

    def available(self) -> bool:
        return importlib.util.find_spec("pyttsx3") is not None

    def _get_engine(self) -> Any | None:
        if self._engine is not None:
            return self._engine
        if not self.available():
            return None
        with self._lock:
            if self._engine is not None:
                return self._engine
            import pyttsx3

            self._engine = pyttsx3.init()
        return self._engine

    def speak(self, text: str) -> bool:
        try:
            engine = self._get_engine()
            if engine is None:
                return False
            engine.say(text)
            engine.runAndWait()
            return True
        except Exception:
            LOGGER.exception("Local chat speech playback failed")
            return False

    def stop(self) -> None:
        engine = self._engine
        if engine is not None:
            try:
                engine.stop()
            except Exception:
                LOGGER.exception("Local chat speech stop failed")


@dataclass(frozen=True, slots=True)
class _SpeechGrant:
    grant_digest: str
    session_id: str
    expires_at: float
    timer: threading.Timer


@dataclass(frozen=True, slots=True)
class _SpeechRequest:
    session_id: str
    grant_digest: str
    text: str


class ChatSpeechOutputController:
    """Play only explicitly opted-in chat responses through local system TTS."""

    SCOPE = "chat_response_local_speech"
    GRANT_SECONDS = 4 * 60 * 60

    def __init__(self, *, admission_provider: Callable[..., AdmissionResponse] = admit_request,
                 player: LocalSpeechPlayer | None = None,
                 monotonic_clock: Callable[[], float] = time.monotonic) -> None:
        self._admit = admission_provider
        self._player = player or Pyttsx3LocalSpeechPlayer()
        self._clock = monotonic_clock
        self._lock = threading.RLock()
        self._grants: dict[str, _SpeechGrant] = {}
        self._queue: queue.Queue[_SpeechRequest | None] = queue.Queue(maxsize=1)
        self._closed = False
        self._last_playback_status = "idle"
        self._worker = threading.Thread(target=self._run, name="local-chat-speech", daemon=True)
        self._worker.start()

    @staticmethod
    def _validate_session(session_id: str) -> None:
        if not isinstance(session_id, str) or not session_id or len(session_id) > 128:
            raise ValueError("chat_speech_session_id_invalid")

    def state(self, session_id: str | None) -> dict[str, Any]:
        configured = not self._closed
        available = self._player.available() if configured else False
        with self._lock:
            grant = self._grants.get(session_id) if session_id else None
            if grant is not None and grant.expires_at <= self._clock():
                self._expire_session(grant.session_id, grant.grant_digest)
                grant = None
            return {
                "configured": configured,
                "backend_available": available,
                "enabled": grant is not None,
                "scope": self.SCOPE,
                "expires_in_seconds": (max(0, int(grant.expires_at - self._clock()))
                                       if grant is not None else 0),
                "playback_status": self._last_playback_status if grant is not None else "idle",
            }

    def set_enabled(self, session_id: str, enabled: bool) -> dict[str, Any]:
        self._validate_session(session_id)
        if type(enabled) is not bool:
            raise ValueError("chat_speech_enabled_invalid")
        with self._lock:
            if self._closed:
                return {"configured": False, "enabled": False, "reason": "service_closed"}
            current = self._grants.get(session_id)
            if not enabled:
                if current is not None:
                    self._revoke(session_id, current)
                return {"configured": True, "enabled": False, "scope": self.SCOPE}
            if not self._player.available():
                return {"configured": True, "enabled": False,
                        "reason": "local_voice_backend_unavailable", "scope": self.SCOPE}
            if current is not None and current.expires_at > self._clock():
                return {"configured": True, "enabled": True, "scope": self.SCOPE,
                        "expires_in_seconds": max(0, int(current.expires_at - self._clock()))}
            if current is not None:
                self._revoke(session_id, current)
            if self._grants:
                return {"configured": True, "enabled": False,
                        "reason": "another_speech_session_is_active", "scope": self.SCOPE}

            grant_id = str(uuid4())
            grant_context = _digest({"grant_id": grant_id, "session_id": session_id,
                                     "scope": self.SCOPE})
            admission = self._admit(
                request_type=RequestType.SPEECH_TTS,
                requester_id="narrator",
                intent_hash=_digest({"grant_id": grant_id, "intent": "grant_local_chat_speech"}),
                context_hash=grant_context,
                policy_version="v1-static",
                metadata={"approved_by": "operator", "approval_method": "local_chat_ui",
                          "approval_scope": self.SCOPE, "session_id": session_id,
                          "backend": "pyttsx3_local"},
            )
            record = admission.record
            metadata = record.metadata if isinstance(record.metadata, Mapping) else {}
            if admission.decision is not Decision.ALLOW:
                return {"configured": True, "enabled": False,
                        "reason": admission.reason.value, "scope": self.SCOPE}
            if (record.request_type is not RequestType.SPEECH_TTS
                    or record.context_hash != grant_context
                    or metadata.get("approved_by") != "operator"):
                raise RuntimeError("chat_speech_grant_binding_invalid")
            grant_digest = _digest({"record": dict(record.as_log_entry()),
                                    "grant_context": grant_context})
            expires_at = self._clock() + self.GRANT_SECONDS
            timer = threading.Timer(self.GRANT_SECONDS, self._expire_session,
                                    args=(session_id, grant_digest))
            timer.daemon = True
            grant = _SpeechGrant(grant_digest, session_id, expires_at, timer)
            self._grants[session_id] = grant
            timer.start()
            self._last_playback_status = "idle"
            return {"configured": True, "enabled": True, "scope": self.SCOPE,
                    "expires_in_seconds": self.GRANT_SECONDS}

    def publish_response(self, *, session_id: str, turn_id: str, text: str,
                         output_digest: str) -> dict[str, Any]:
        self._validate_session(session_id)
        if not isinstance(turn_id, str) or not turn_id or not isinstance(text, str):
            raise ValueError("chat_speech_response_invalid")
        if not isinstance(output_digest, str) or len(output_digest) != 64:
            raise ValueError("chat_speech_output_digest_invalid")
        try:
            int(output_digest, 16)
        except ValueError as exc:
            raise ValueError("chat_speech_output_digest_invalid") from exc
        with self._lock:
            grant = self._grants.get(session_id)
            if grant is None:
                return {"status": "disabled"}
            if grant.expires_at <= self._clock():
                self._expire_session(session_id, grant.grant_digest)
                return {"status": "grant_expired"}
            context_hash = _digest({"grant_digest": grant.grant_digest,
                "session_id": session_id, "turn_id": turn_id, "scope": self.SCOPE})
            admission = self._admit(
                request_type=RequestType.SPEECH_TTS, requester_id="narrator",
                intent_hash="sha256:" + output_digest, context_hash=context_hash,
                policy_version="v1-static",
                metadata={"approved_by": "operator", "approval_method": "session_grant",
                          "approval_scope": self.SCOPE, "approval_grant_digest": grant.grant_digest,
                          "session_id": session_id, "source_turn_id": turn_id,
                          "backend": "pyttsx3_local"},
            )
            record = admission.record
            metadata = record.metadata if isinstance(record.metadata, Mapping) else {}
            if admission.decision is not Decision.ALLOW:
                return {"status": "admission_denied", "reason": admission.reason.value}
            if (record.request_type is not RequestType.SPEECH_TTS
                    or record.intent_hash != "sha256:" + output_digest
                    or record.context_hash != context_hash
                    or metadata.get("approval_grant_digest") != grant.grant_digest):
                raise RuntimeError("chat_speech_response_binding_invalid")
            request = _SpeechRequest(session_id, grant.grant_digest,
                                      text[:MAX_SPOKEN_CHARS].strip())
            if not request.text:
                return {"status": "empty"}
            try:
                self._queue.put_nowait(request)
            except queue.Full:
                self._last_playback_status = "speaker_busy"
                return {"status": "speaker_busy"}
            self._last_playback_status = "queued"
            return {"status": "queued", "text_truncated": len(text) > MAX_SPOKEN_CHARS}

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            grants = tuple(self._grants.items())
            self._grants.clear()
            for _, grant in grants:
                grant.timer.cancel()
            self._discard_pending()
            self._player.stop()
            try:
                self._queue.put_nowait(None)
            except queue.Full:
                pass
            self._last_playback_status = "stopped"
        if self._worker.is_alive():
            self._worker.join(timeout=1.0)

    def _run(self) -> None:
        while True:
            request = self._queue.get()
            try:
                if request is None:
                    return
                with self._lock:
                    grant = self._grants.get(request.session_id)
                    active = (not self._closed and grant is not None
                        and grant.grant_digest == request.grant_digest
                        and grant.expires_at > self._clock())
                    if not active:
                        continue
                    self._last_playback_status = "speaking"
                played = self._player.speak(request.text)
                with self._lock:
                    if self._last_playback_status != "speaker_busy":
                        self._last_playback_status = "played" if played else "playback_failed"
            except Exception:
                LOGGER.exception("Local chat speech worker failed")
                with self._lock:
                    self._last_playback_status = "playback_failed"
            finally:
                self._queue.task_done()

    def _expire_session(self, session_id: str, grant_digest: str) -> None:
        with self._lock:
            grant = self._grants.get(session_id)
            if grant is None or grant.grant_digest != grant_digest:
                return
            if grant.expires_at > self._clock():
                return
            self._revoke(session_id, grant)

    def _revoke(self, session_id: str, grant: _SpeechGrant) -> None:
        self._grants.pop(session_id, None)
        grant.timer.cancel()
        self._discard_pending(session_id)
        self._player.stop()
        self._last_playback_status = "stopped"

    def _discard_pending(self, session_id: str | None = None) -> None:
        retained: list[_SpeechRequest | None] = []
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item is not None and session_id is not None and item.session_id != session_id:
                retained.append(item)
            self._queue.task_done()
        for item in retained:
            self._queue.put_nowait(item)
