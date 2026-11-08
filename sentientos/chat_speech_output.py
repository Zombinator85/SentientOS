"""Explicit, local-only speech output for production chat replies."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol
from uuid import uuid4

from control_plane import Decision, RequestType
from control_plane.task_admission import AdmissionResponse, admit_request

LOGGER = logging.getLogger(__name__)
MAX_SPOKEN_CHARS = 600
MAX_PENDING_TIMING_EVENTS = 1024


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
        self._failure_code: str | None = None

    def available(self) -> bool:
        if importlib.util.find_spec("pyttsx3") is None:
            return False
        if sys.platform.startswith("linux"):
            return bool(shutil.which("espeak-ng") or shutil.which("espeak"))
        return True

    def playback_failure_code(self) -> str | None:
        return self._failure_code

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
                self._failure_code = "pyttsx3_backend_unavailable"
                return False
            engine.say(text)
            engine.runAndWait()
            self._failure_code = None
            return True
        except Exception:
            self._failure_code = "pyttsx3_playback_failed"
            LOGGER.exception("Local chat speech playback failed")
            return False

    def speak_with_timing(self, text: str, event_sink: Callable[[Mapping[str, Any]], None],
                          *, monotonic_clock: Callable[[], float] = time.monotonic) -> bool:
        """Speak locally and report backend word-start offsets when available.

        Word events are backend timing, not phoneme/viseme inference.  A
        backend without ``started-word`` support still reports utterance
        boundaries from this controller, but does not invent word timings.
        """
        callback_ids: list[str] = []
        disconnect_fn: Callable[[str], Any] | None = None
        try:
            engine = self._get_engine()
            if engine is None:
                self._failure_code = "pyttsx3_backend_unavailable"
                return False
            utterance_started = monotonic_clock()
            word_index = 0

            def started_word(name: str, location: int, length: int) -> None:
                nonlocal word_index
                del name
                if (type(location) is not int or type(length) is not int
                        or location < 0 or length < 0 or location + length > len(text)):
                    return
                word_index += 1
                event_sink({"event": "word_started", "word_index": word_index,
                    "char_start": location, "char_length": length,
                    "elapsed_seconds": max(0.0, monotonic_clock() - utterance_started),
                    "timing_quality": "backend_word_start"})

            connect = getattr(engine, "connect", None)
            disconnect_candidate = getattr(engine, "disconnect", None)
            if callable(connect) and callable(disconnect_candidate):
                disconnect_fn = disconnect_candidate
                try:
                    callback_ids.append(connect("started-word", started_word))
                except Exception:
                    # Some local TTS backends do not implement word timing.
                    callback_ids.clear()
            engine.say(text)
            engine.runAndWait()
            self._failure_code = None
            return True
        except Exception:
            self._failure_code = "pyttsx3_playback_failed"
            LOGGER.exception("Local chat speech playback failed")
            return False
        finally:
            if disconnect_fn is not None:
                for callback_id in locals().get("callback_ids", []):
                    try:
                        disconnect_fn(callback_id)
                    except Exception:
                        LOGGER.debug("Local TTS timing callback cleanup failed", exc_info=True)

    def stop(self) -> None:
        engine = self._engine
        if engine is not None:
            try:
                engine.stop()
            except Exception:
                LOGGER.exception("Local chat speech stop failed")


class WindowsSapiLocalSpeechPlayer:
    """Local Windows SAPI output, used when the WSL audio engine is unavailable."""

    _SCRIPT = (
        "$ErrorActionPreference = 'Stop'; "
        "[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false); "
        "$text = [Console]::In.ReadToEnd(); "
        "Add-Type -AssemblyName System.Speech; "
        "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "try { $synth.Speak($text) } finally { $synth.Dispose() }"
    )

    def __init__(self, *, powershell_path: str | None = None,
                 process_factory: Callable[..., Any] = subprocess.Popen,
                 timeout_seconds: float = 90.0) -> None:
        self._powershell_path = powershell_path or self._find_powershell()
        self._process_factory = process_factory
        self._timeout_seconds = timeout_seconds
        self._lock = threading.Lock()
        self._process: Any | None = None
        self._failure_code: str | None = None

    @staticmethod
    def _find_powershell() -> str | None:
        candidate = shutil.which("powershell.exe")
        if candidate:
            return candidate
        wsl_path = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
        return wsl_path if os.path.isfile(wsl_path) else None

    def available(self) -> bool:
        return self._powershell_path is not None

    def playback_failure_code(self) -> str | None:
        return self._failure_code

    def speak(self, text: str) -> bool:
        if not self.available():
            self._failure_code = "windows_sapi_backend_unavailable"
            return False
        try:
            process = self._process_factory(
                [self._powershell_path, "-NoLogo", "-NoProfile", "-NonInteractive",
                 "-WindowStyle", "Hidden", "-Command", self._SCRIPT],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
        except (OSError, subprocess.SubprocessError):
            self._failure_code = "windows_sapi_launch_failed"
            LOGGER.exception("Local Windows SAPI process launch failed")
            return False
        with self._lock:
            self._process = process
        try:
            process.communicate(input=text, timeout=self._timeout_seconds)
            if process.returncode != 0:
                self._failure_code = "windows_sapi_playback_failed"
                return False
            self._failure_code = None
            return True
        except subprocess.TimeoutExpired:
            self._failure_code = "windows_sapi_timeout"
            self._terminate(process)
            return False
        except (OSError, subprocess.SubprocessError):
            self._failure_code = "windows_sapi_playback_failed"
            LOGGER.exception("Local Windows SAPI playback failed")
            self._terminate(process)
            return False
        finally:
            with self._lock:
                if self._process is process:
                    self._process = None

    @staticmethod
    def _terminate(process: Any) -> None:
        try:
            process.terminate()
            process.wait(timeout=2.0)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def stop(self) -> None:
        with self._lock:
            process = self._process
        if process is not None:
            self._terminate(process)


class LocalSystemSpeechPlayer:
    """Prefer the host OS voice and retain a local pyttsx3 fallback."""

    def __init__(self, *, players: tuple[LocalSpeechPlayer, ...] | None = None) -> None:
        if players is None:
            sapi = WindowsSapiLocalSpeechPlayer()
            pyttsx3 = Pyttsx3LocalSpeechPlayer()
            players = ((sapi, pyttsx3) if sapi.available() and sys.platform.startswith("linux")
                       else (pyttsx3, sapi))
        self._players = players
        self._active_player: LocalSpeechPlayer | None = None
        self._failure_code: str | None = None
        self._lock = threading.Lock()

    def available(self) -> bool:
        return any(player.available() for player in self._players)

    def playback_failure_code(self) -> str | None:
        return self._failure_code

    def speak(self, text: str) -> bool:
        failure_code = "local_speech_backend_unavailable"
        for player in self._players:
            if not player.available():
                continue
            with self._lock:
                self._active_player = player
            try:
                if player.speak(text):
                    self._failure_code = None
                    return True
            finally:
                with self._lock:
                    if self._active_player is player:
                        self._active_player = None
            code_provider = getattr(player, "playback_failure_code", None)
            code = code_provider() if callable(code_provider) else None
            if isinstance(code, str) and code:
                failure_code = code
        self._failure_code = failure_code
        return False

    def stop(self) -> None:
        with self._lock:
            player = self._active_player
        if player is not None:
            player.stop()


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
    turn_id: str
    text: str
    cancelled: threading.Event


class ChatSpeechOutputController:
    """Play only explicitly opted-in chat responses through local system TTS."""

    SCOPE = "chat_response_local_speech"
    GRANT_SECONDS = 4 * 60 * 60

    def __init__(self, *, admission_provider: Callable[..., AdmissionResponse] = admit_request,
                 player: LocalSpeechPlayer | None = None,
                 monotonic_clock: Callable[[], float] = time.monotonic,
                 timing_event_sink: Callable[[Mapping[str, Any]], None] | None = None) -> None:
        self._admit = admission_provider
        self._player = player or LocalSystemSpeechPlayer()
        self._clock = monotonic_clock
        self._timing_event_sink = timing_event_sink
        self._timing_events: queue.Queue[Mapping[str, Any]] = queue.Queue(
            maxsize=MAX_PENDING_TIMING_EVENTS)
        self._timing_thread_stop = threading.Event()
        self._timing_event_drops = 0
        self._lock = threading.RLock()
        self._grants: dict[str, _SpeechGrant] = {}
        self._queue: queue.Queue[_SpeechRequest | None] = queue.Queue(maxsize=1)
        self._closed = False
        self._last_playback_status = "idle"
        self._last_playback_failure_code: str | None = None
        self._active_request: _SpeechRequest | None = None
        self._last_played_turn: tuple[str, str] | None = None
        self._worker = threading.Thread(target=self._run, name="local-chat-speech", daemon=True)
        self._worker.start()
        self._timing_worker: threading.Thread | None = None
        if self._timing_event_sink is not None:
            self._timing_worker = threading.Thread(target=self._run_timing_events,
                name="local-chat-speech-timing", daemon=True)
            self._timing_worker.start()

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
                "playback_failure_code": (self._last_playback_failure_code
                                           if grant is not None else None),
                "active_turn_id": (self._active_request.turn_id
                                   if self._active_request is not None
                                   and self._active_request.session_id == session_id else None),
                "last_played_turn_id": (self._last_played_turn[1]
                                        if self._last_played_turn is not None
                                        and self._last_played_turn[0] == session_id else None),
                "timing_event_drops": self._timing_event_drops,
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
            self._last_playback_failure_code = None
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
            request = _SpeechRequest(session_id, grant.grant_digest, turn_id,
                                      text[:MAX_SPOKEN_CHARS].strip(), threading.Event())
            if not request.text:
                return {"status": "empty"}
            try:
                self._queue.put_nowait(request)
            except queue.Full:
                self._last_playback_status = "speaker_busy"
                return {"status": "speaker_busy"}
            self._last_playback_status = "queued"
            self._last_playback_failure_code = None
            return {"status": "queued", "text_truncated": len(text) > MAX_SPOKEN_CHARS}

    def interrupt(self, session_id: str) -> dict[str, Any]:
        """Best-effort stop current speech and discard pending turns for a session."""
        self._validate_session(session_id)
        with self._lock:
            active = self._active_request
            if active is not None and active.session_id == session_id:
                active.cancelled.set()
                self._active_request = None
            had_pending = self._discard_pending(session_id)
            interrupted = (active is not None and active.session_id == session_id) or had_pending
            if interrupted:
                self._last_playback_status = "interrupted"
        if active is not None and active.session_id == session_id:
            self._player.stop()
        return {"status": "interrupted" if interrupted else "idle"}

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            grants = tuple(self._grants.items())
            self._grants.clear()
            active = self._active_request
            self._active_request = None
            if active is not None:
                active.cancelled.set()
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
        self._timing_thread_stop.set()
        if self._timing_worker is not None and self._timing_worker.is_alive():
            self._timing_worker.join(timeout=1.0)

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
                    self._active_request = request
                    self._last_playback_status = "speaking"
                utterance_started = self._clock()
                utterance_started_at = time.time()
                self._emit_timing_event(request, {"event": "speech_started",
                    "elapsed_seconds": 0.0, "started_at": utterance_started_at,
                    "timing_quality": "controller_boundary"})
                timed_speak = getattr(self._player, "speak_with_timing", None)
                if callable(timed_speak):
                    played = timed_speak(request.text,
                        lambda event: self._emit_timing_event(request,
                            {**event, "started_at": utterance_started_at}),
                        monotonic_clock=self._clock)
                else:
                    played = self._player.speak(request.text)
                with self._lock:
                    still_active = self._active_request is request
                    if still_active:
                        self._active_request = None
                    if request.cancelled.is_set() or not still_active:
                        self._last_playback_status = "interrupted"
                    elif self._last_playback_status != "speaker_busy":
                        self._last_playback_status = "played" if played else "playback_failed"
                        failure_provider = getattr(self._player,
                            "playback_failure_code", None)
                        failure_code = (failure_provider()
                            if callable(failure_provider) else None)
                        self._last_playback_failure_code = (
                            failure_code if not played and isinstance(failure_code, str)
                            else None)
                    if played and not request.cancelled.is_set() and still_active:
                        self._last_played_turn = (request.session_id, request.turn_id)
                self._emit_timing_event(request, {"event": "speech_interrupted"
                    if request.cancelled.is_set() or not still_active else
                    "speech_finished" if played else "speech_failed",
                    "elapsed_seconds": max(0.0, self._clock() - utterance_started),
                    "started_at": utterance_started_at,
                    "timing_quality": "controller_boundary"})
            except Exception:
                LOGGER.exception("Local chat speech worker failed")
                if request is not None:
                    with self._lock:
                        self._last_playback_status = (
                            "interrupted" if request.cancelled.is_set() else "playback_failed")
                        failure_provider = getattr(self._player,
                            "playback_failure_code", None)
                        failure_code = (failure_provider()
                            if callable(failure_provider) else None)
                        self._last_playback_failure_code = (
                            failure_code if isinstance(failure_code, str)
                            else "local_speech_playback_failed")
                    self._emit_timing_event(request, {"event": "speech_failed",
                        "elapsed_seconds": 0.0, "timing_quality": "controller_boundary"})
            finally:
                self._queue.task_done()

    def _emit_timing_event(self, request: _SpeechRequest,
                           event: Mapping[str, Any]) -> None:
        sink = self._timing_event_sink
        if sink is None or self._timing_thread_stop.is_set():
            return
        payload = dict(event)
        payload.update({"session_id": request.session_id, "turn_id": request.turn_id})
        try:
            self._timing_events.put_nowait(payload)
        except queue.Full:
            with self._lock:
                self._timing_event_drops += 1

    def _run_timing_events(self) -> None:
        sink = self._timing_event_sink
        if sink is None:
            return
        while not self._timing_thread_stop.is_set() or not self._timing_events.empty():
            try:
                event = self._timing_events.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                sink(event)
            except Exception as exc:
                # Avatar synchronization is ancillary; a failed renderer update
                # must never stop or replay the user's local speech.
                LOGGER.warning("Avatar speech timing publication failed: %s", type(exc).__name__)
            finally:
                self._timing_events.task_done()

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
        if self._active_request is not None and self._active_request.session_id == session_id:
            self._active_request.cancelled.set()
            self._active_request = None
        self._player.stop()
        self._last_playback_status = "stopped"

    def _discard_pending(self, session_id: str | None = None) -> bool:
        retained: list[_SpeechRequest | None] = []
        discarded = False
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item is not None and session_id is not None and item.session_id != session_id:
                retained.append(item)
            elif item is not None:
                item.cancelled.set()
                discarded = True
            self._queue.task_done()
        for item in retained:
            self._queue.put_nowait(item)
        return discarded
