"""Session-scoped, visual-only chat output to the local avatar state channel."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol
from uuid import uuid4

from control_plane import Decision, RequestType
from control_plane.task_admission import AdmissionResponse, admit_request
from speech_emitter import MAX_AVATAR_DISPLAY_PHRASE_CHARS

LOGGER = logging.getLogger(__name__)


class ChatAvatarStateEmitter(Protocol):
    """Local or authenticated remote sink for governed chat avatar state."""

    def emit_display_text(self, phrase: str, *, authorization: Any = None,
                          metadata: Mapping[str, Any] | None = None) -> Any: ...
    def emit_phrase(self, phrase: str, *, started_at: float | None = None,
                    speaking: bool | None = None, muted: bool = False,
                    metadata: Mapping[str, Any] | None = None,
                    authorization: Any = None) -> Any: ...
    def emit_idle(self, *, authorization: Any = None,
                  metadata: Mapping[str, Any] | None = None) -> Any: ...


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class _SessionGrant:
    grant_digest: str
    session_id: str
    approved_by: str
    expires_at: float
    timer: threading.Timer


class ChatAvatarOutputController:
    """Require an explicit local-session grant before showing chat in the avatar."""

    SCOPE = "chat_response_visual_only"
    GRANT_SECONDS = 4 * 60 * 60

    def __init__(self, emitter: ChatAvatarStateEmitter, *,
                 admission_provider: Callable[..., AdmissionResponse] = admit_request,
                 monotonic_clock: Callable[[], float] = time.monotonic) -> None:
        self._emitter = emitter
        self._admit = admission_provider
        self._clock = monotonic_clock
        self._lock = threading.RLock()
        self._grants: dict[str, _SessionGrant] = {}
        self._pending_clears: dict[str, _SessionGrant | None] = {}
        self._last_responses: dict[str, tuple[str, str, str]] = {}
        self._probe_requests: dict[tuple[str, str], None] = {}
        self._speech_started_at: dict[tuple[str, str], float] = {}
        self._workload_modes: dict[str, str] = {}

    @staticmethod
    def _validate_session_id(session_id: str) -> None:
        if not isinstance(session_id, str) or not session_id or len(session_id) > 128:
            raise ValueError("avatar_output_session_id_invalid")

    def set_enabled(self, session_id: str, enabled: bool) -> dict[str, Any]:
        self._validate_session_id(session_id)
        if type(enabled) is not bool:
            raise ValueError("avatar_output_enabled_invalid")
        with self._lock:
            grant = self._grants.get(session_id)
            if not enabled:
                if grant is not None:
                    self._grants.pop(session_id, None)
                    grant.timer.cancel()
                self._last_responses.pop(session_id, None)
                self._workload_modes.pop(session_id, None)
                if grant is None and self._grants:
                    return {"configured": True, "enabled": False, "scope": self.SCOPE,
                            "state_cleared": False, "reason": "another_avatar_session_is_active"}
                pending = self._pending_clears.pop(session_id, None)
                clear_grant = grant if grant is not None else pending
                try:
                    cleared = self._clear_state(session_id, clear_grant,
                        approval_method="local_chat_ui_revoke")
                except Exception:
                    self._pending_clears[session_id] = clear_grant
                    raise
                if not cleared:
                    self._pending_clears[session_id] = clear_grant
                return {"configured": True, "enabled": False, "scope": self.SCOPE,
                        "state_cleared": cleared}

            if grant is not None and grant.expires_at > self._clock():
                return {"configured": True, "enabled": True, "scope": self.SCOPE,
                        "expires_in_seconds": max(0, int(grant.expires_at - self._clock()))}
            if grant is not None:
                if not self._retire_grant(session_id, grant,
                        approval_method="session_grant_expiry"):
                    return {"configured": True, "enabled": False,
                            "reason": "previous_avatar_state_clear_denied", "scope": self.SCOPE}
            if any(active_session != session_id for active_session in self._grants):
                return {"configured": True, "enabled": False,
                        "reason": "another_avatar_session_is_active", "scope": self.SCOPE}

            # Clear any stale phrase before assigning the single shared display
            # channel to a different conversation. A denial keeps activation off.
            for stale_session, stale_grant in tuple(self._pending_clears.items()):
                if not self._clear_state(stale_session, stale_grant,
                        approval_method="pending_clear_before_new_grant"):
                    return {"configured": True, "enabled": False,
                            "reason": "previous_avatar_state_clear_denied", "scope": self.SCOPE}
                self._pending_clears.pop(stale_session, None)

            grant_id = str(uuid4())
            grant_context = _digest({"grant_id": grant_id, "session_id": session_id, "scope": self.SCOPE})
            admission = self._admit(
                request_type=RequestType.AVATAR_EMISSION,
                requester_id="bridge",
                intent_hash=_digest({"grant_id": grant_id, "intent": "grant_visual_chat_output"}),
                context_hash=grant_context,
                policy_version="v1-static",
                metadata={"approved_by": "operator", "approval_method": "local_chat_ui",
                          "approval_scope": self.SCOPE, "session_id": session_id},
            )
            if admission.decision is not Decision.ALLOW:
                return {"configured": True, "enabled": False,
                        "reason": admission.reason.value, "scope": self.SCOPE}
            record = admission.record
            metadata = record.metadata if isinstance(record.metadata, Mapping) else {}
            approved_by = metadata.get("approved_by")
            if (record.request_type is not RequestType.AVATAR_EMISSION
                    or record.context_hash != grant_context
                    or approved_by != "operator"):
                raise RuntimeError("avatar_output_grant_binding_invalid")
            grant_digest = _digest({"record": dict(record.as_log_entry()), "grant_context": grant_context})
            expires_at = self._clock() + self.GRANT_SECONDS
            timer = threading.Timer(self.GRANT_SECONDS, self._expire_session,
                                    args=(session_id, grant_digest))
            timer.daemon = True
            grant = _SessionGrant(grant_digest, session_id, "operator", expires_at, timer)
            self._grants[session_id] = grant
            self._last_responses.pop(session_id, None)
            self._workload_modes.pop(session_id, None)
            timer.start()
            return {"configured": True, "enabled": True, "scope": self.SCOPE,
                    "expires_in_seconds": self.GRANT_SECONDS}

    def state(self, session_id: str) -> dict[str, Any]:
        self._validate_session_id(session_id)
        with self._lock:
            grant = self._grants.get(session_id)
            if grant is not None and grant.expires_at <= self._clock():
                self._retire_grant(session_id, grant, approval_method="session_grant_expiry")
                grant = None
        return {"configured": True, "enabled": grant is not None, "scope": self.SCOPE,
                "expires_in_seconds": (max(0, int(grant.expires_at - self._clock()))
                                       if grant is not None else 0),
                "clear_pending": session_id in self._pending_clears}

    def publish_response(self, *, session_id: str, turn_id: str, text: str,
                         output_digest: str, workload_mode: str | None = None) -> dict[str, Any]:
        self._validate_session_id(session_id)
        if not isinstance(turn_id, str) or not turn_id or not isinstance(text, str):
            raise ValueError("avatar_output_response_invalid")
        if (not isinstance(output_digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", output_digest) is None):
            raise ValueError("avatar_output_digest_invalid")
        effective_workload_mode = (workload_mode if isinstance(workload_mode, str)
            and workload_mode in {"normal", "gaming"} else None)
        with self._lock:
            grant = self._grants.get(session_id)
            if grant is None:
                return {"status": "disabled"}
            if grant.expires_at <= self._clock():
                cleared = self._retire_grant(session_id, grant,
                    approval_method="session_grant_expiry")
                return {"status": "grant_expired", "state_cleared": cleared}
            context = {"grant_digest": grant.grant_digest,
                "session_id": session_id, "turn_id": turn_id, "scope": self.SCOPE}
            if effective_workload_mode is not None:
                context["workload_mode"] = effective_workload_mode
            context_hash = _digest(context)
            admission_metadata = {"approved_by": grant.approved_by,
                "approval_method": "session_grant", "approval_scope": self.SCOPE,
                "approval_grant_digest": grant.grant_digest,
                "session_id": session_id, "source_turn_id": turn_id}
            if effective_workload_mode is not None:
                admission_metadata["workload_mode"] = effective_workload_mode
            admission = self._admit(
                request_type=RequestType.AVATAR_EMISSION,
                requester_id="bridge", intent_hash=output_digest,
                context_hash=context_hash, policy_version="v1-static",
                metadata=admission_metadata,
            )
            if admission.decision is not Decision.ALLOW:
                return {"status": "admission_denied", "reason": admission.reason.value}
            record = admission.record
            if (record.request_type is not RequestType.AVATAR_EMISSION
                    or record.intent_hash != output_digest or record.context_hash != context_hash):
                raise RuntimeError("avatar_output_response_binding_invalid")
            visible = text[:MAX_AVATAR_DISPLAY_PHRASE_CHARS]
            metadata = {
                "source": "governed_chat_response", "session_id": session_id,
                "turn_id": turn_id, "output_digest": output_digest,
                # Keep complete response identity distinct from the possibly
                # truncated renderer-visible phrase.
                "displayed_text_digest": _digest({"text": visible}),
                "approval_grant_digest": grant.grant_digest,
                "phrase_truncated": len(text) > MAX_AVATAR_DISPLAY_PHRASE_CHARS,
                "output_mode": self.SCOPE,
            }
            # This is a renderer hint only. Accept the closed effective-mode
            # vocabulary; never persist arbitrary workload metadata.
            if effective_workload_mode is not None:
                metadata["workload_mode"] = effective_workload_mode
            self._emitter.emit_display_text(visible, authorization=record, metadata=metadata)
            self._last_responses[session_id] = (visible, turn_id, output_digest)
            for timing_key in tuple(self._speech_started_at):
                if timing_key[0] == session_id:
                    self._speech_started_at.pop(timing_key, None)
            if effective_workload_mode is not None:
                self._workload_modes[session_id] = effective_workload_mode
            else:
                self._workload_modes.pop(session_id, None)
        return {"status": "emitted", "phrase_truncated": len(text) > MAX_AVATAR_DISPLAY_PHRASE_CHARS}

    def publish_consequence_probe(self, *, session_id: str, turn_id: str,
                                  request_id: str,
                                  assistant_response_digest: str) -> dict[str, Any]:
        """Admit one operator-confirmed visual nod for immediate measurement."""
        self._validate_session_id(session_id)
        if (not isinstance(turn_id, str)
                or re.fullmatch(r"turn-[0-9a-f]{24}", turn_id) is None
                or not isinstance(request_id, str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", request_id) is None
                or not isinstance(assistant_response_digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", assistant_response_digest) is None):
            raise ValueError("avatar_consequence_probe_binding_invalid")
        # A separate local UI confirmation is required by the endpoint. The
        # session grant must also remain active; neither condition alone is
        # sufficient to emit the visual command.
        with self._lock:
            grant = self._grants.get(session_id)
            if grant is None or grant.expires_at <= self._clock():
                return {"status": "disabled"}
            request_key = (session_id, request_id)
            if request_key in self._probe_requests:
                return {"status": "duplicate_request"}
            # Bound this request-scoped replay ledger to recent one-shot probes.
            if len(self._probe_requests) >= 512:
                self._probe_requests.pop(next(iter(self._probe_requests)))
            self._probe_requests[request_key] = None
            context = {"grant_digest": grant.grant_digest,
                "session_id": session_id, "turn_id": turn_id,
                "scope": self.SCOPE, "action": "one_shot_consequence_nod",
                "measurement_request_id": request_id}
            context_hash = _digest(context)
            output_digest = _digest({"text": ""})[len("sha256:"):]
            admission_metadata = {"approved_by": grant.approved_by,
                "approval_method": "local_developmental_cycle_confirmation",
                "approval_scope": self.SCOPE,
                "approval_grant_digest": grant.grant_digest,
                "session_id": session_id, "source_turn_id": turn_id,
                "action_kind": "avatar_consequence_probe",
                "measurement_request_id": request_id}
            admission = self._admit(
                request_type=RequestType.AVATAR_EMISSION,
                requester_id="bridge", intent_hash=output_digest,
                context_hash=context_hash, policy_version="v1-static",
                metadata=admission_metadata)
            if admission.decision is not Decision.ALLOW:
                return {"status": "admission_denied",
                    "reason": admission.reason.value}
            record = admission.record
            if (record.request_type is not RequestType.AVATAR_EMISSION
                    or record.intent_hash != output_digest
                    or record.context_hash != context_hash):
                raise RuntimeError("avatar_consequence_probe_authority_binding_invalid")
            metadata = {"source": "governed_avatar_consequence_probe",
                "session_id": session_id, "turn_id": turn_id,
                "output_digest": output_digest,
                "displayed_text_digest": _digest({"text": ""}),
                "phrase_truncated": False, "output_mode": self.SCOPE,
                "measurement_request_id": request_id,
                "assistant_response_digest": assistant_response_digest}
            self._emitter.emit_display_text("", authorization=record,
                metadata=metadata)
        return {"status": "emitted", "action": "one_shot_visual_nod",
            "game_input_authorized": False, "renderer_effect_proven": False}

    def publish_speech_timing(self, event: Mapping[str, Any]) -> Mapping[str, Any]:
        """Publish actual local playback timing for the currently displayed turn.

        This conveys utterance/word timing only.  It deliberately does not
        synthesize phonemes or claim independent audio observation.
        """
        session_id = event.get("session_id")
        turn_id = event.get("turn_id")
        kind = event.get("event")
        if (not isinstance(session_id, str) or not isinstance(turn_id, str)
                or kind not in {"speech_started", "word_started", "speech_finished",
                                "speech_interrupted", "speech_failed"}):
            return {"status": "invalid_event"}
        with self._lock:
            grant = self._grants.get(session_id)
            current = self._last_responses.get(session_id)
            if (grant is None or grant.expires_at <= self._clock()
                    or current is None or current[1] != turn_id):
                return {"status": "stale_or_ungranted"}
            timing: dict[str, Any] = {
                "schema": "sentientos.local_speech_timing:v1",
                "event": kind,
                "session_id": session_id,
                "turn_id": turn_id,
                "timing_quality": ("backend_word_start" if kind == "word_started"
                    else "controller_boundary"),
            }
            elapsed = event.get("elapsed_seconds")
            if isinstance(elapsed, (int, float)) and not isinstance(elapsed, bool):
                if 0 <= float(elapsed) <= 3600:
                    timing["elapsed_seconds"] = float(elapsed)
            started_at = event.get("started_at")
            if isinstance(started_at, (int, float)) and not isinstance(started_at, bool):
                now = time.time()
                if now - 3600 < float(started_at) < now + 60:
                    timing["started_at"] = float(started_at)
            timing_key = (session_id, turn_id)
            if kind == "speech_started" and "started_at" in timing:
                self._speech_started_at[timing_key] = float(timing["started_at"])
            elif timing_key in self._speech_started_at:
                timing["started_at"] = self._speech_started_at[timing_key]
            if kind == "word_started":
                word_index = event.get("word_index")
                char_start = event.get("char_start")
                char_length = event.get("char_length")
                if (type(word_index) is not int or type(char_start) is not int
                        or type(char_length) is not int or word_index < 0
                        or char_start < 0 or char_length < 0):
                    return {"status": "invalid_event"}
                if (word_index > len(current[0]) or char_start > len(current[0])
                        or char_length > len(current[0])
                        or char_start + char_length > len(current[0])):
                    return {"status": "invalid_event"}
                timing.update({"word_index": word_index, "char_start": char_start,
                               "char_length": char_length})
            context_hash = _digest({"grant_digest": grant.grant_digest,
                "session_id": session_id, "turn_id": turn_id,
                "scope": self.SCOPE, "speech_timing": timing})
            admission = self._admit(
                request_type=RequestType.AVATAR_EMISSION, requester_id="bridge",
                intent_hash=_digest({"speech_timing": timing}), context_hash=context_hash,
                policy_version="v1-static",
                metadata={"approved_by": grant.approved_by,
                    "approval_method": "session_grant_speech_timing",
                    "approval_scope": self.SCOPE,
                    "approval_grant_digest": grant.grant_digest,
                    "session_id": session_id, "source_turn_id": turn_id},
            )
            if admission.decision is not Decision.ALLOW:
                return {"status": "admission_denied", "reason": admission.reason.value}
            record = admission.record
            if (record.request_type is not RequestType.AVATAR_EMISSION
                    or record.context_hash != context_hash
                    or record.intent_hash != _digest({"speech_timing": timing})):
                raise RuntimeError("avatar_speech_timing_binding_invalid")
            metadata = {"source": "governed_chat_response_speech_timing",
                "session_id": session_id, "turn_id": turn_id,
                "output_digest": current[2], "approval_grant_digest": grant.grant_digest,
                "output_mode": self.SCOPE, "speech_timing": timing}
            speaking = kind not in {"speech_finished", "speech_interrupted", "speech_failed"}
            self._emitter.emit_phrase(current[0],
                started_at=(float(timing["started_at"])
                            if "started_at" in timing else None),
                speaking=speaking, muted=False, metadata=metadata, authorization=record)
            if not speaking:
                self._speech_started_at.pop(timing_key, None)
        return {"status": "emitted", "speaking": speaking}

    def set_workload_mode(self, session_id: str, workload_mode: str) -> dict[str, Any]:
        """Update the opted-in renderer from the current effective local workload mode."""
        self._validate_session_id(session_id)
        if not isinstance(workload_mode, str) or workload_mode not in {"normal", "gaming"}:
            raise ValueError("avatar_output_workload_mode_invalid")
        with self._lock:
            grant = self._grants.get(session_id)
            if grant is None:
                return {"status": "disabled"}
            if grant.expires_at <= self._clock():
                cleared = self._retire_grant(session_id, grant,
                    approval_method="session_grant_expiry")
                return {"status": "grant_expired", "state_cleared": cleared}
            if self._workload_modes.get(session_id) == workload_mode:
                return {"status": "unchanged", "workload_mode": workload_mode}
            intent_hash = _digest({"operation": "sync_renderer_workload_mode",
                "session_id": session_id, "workload_mode": workload_mode})
            context_hash = _digest({"grant_digest": grant.grant_digest,
                "session_id": session_id, "scope": self.SCOPE,
                "workload_mode": workload_mode})
            admission = self._admit(request_type=RequestType.AVATAR_EMISSION,
                requester_id="bridge", intent_hash=intent_hash,
                context_hash=context_hash, policy_version="v1-static",
                metadata={"approved_by": grant.approved_by,
                    "approval_method": "session_grant_workload_sync",
                    "approval_scope": self.SCOPE,
                    "approval_grant_digest": grant.grant_digest,
                    "session_id": session_id, "workload_mode": workload_mode})
            if admission.decision is not Decision.ALLOW:
                return {"status": "admission_denied", "reason": admission.reason.value}
            record = admission.record
            if (record.request_type is not RequestType.AVATAR_EMISSION
                    or record.intent_hash != intent_hash or record.context_hash != context_hash):
                raise RuntimeError("avatar_output_workload_binding_invalid")
            metadata: dict[str, Any] = {"source": "governed_chat_workload_status",
                "session_id": session_id, "workload_mode": workload_mode,
                "approval_grant_digest": grant.grant_digest,
                "approval_method": "session_grant_workload_sync",
                "output_mode": self.SCOPE}
            previous = self._last_responses.get(session_id)
            if previous is None:
                self._emitter.emit_idle(authorization=record, metadata=metadata)
            else:
                phrase, turn_id, output_digest = previous
                metadata.update({"turn_id": turn_id, "output_digest": output_digest})
                self._emitter.emit_display_text(phrase, authorization=record, metadata=metadata)
            self._workload_modes[session_id] = workload_mode
            return {"status": "updated", "workload_mode": workload_mode}

    def close(self) -> None:
        """Revoke ephemeral grants and clear visible phrases on shutdown."""
        with self._lock:
            grants = dict(self._pending_clears)
            grants.update(self._grants)
            for grant in self._grants.values():
                grant.timer.cancel()
            for session_id, grant_to_clear in grants.items():
                try:
                    if not self._clear_state(session_id, grant_to_clear,
                            approval_method="chat_service_shutdown"):
                        LOGGER.warning("Avatar phrase clear denied during shutdown for session %s",
                                       session_id)
                except Exception:
                    LOGGER.exception("Avatar phrase clear failed during shutdown for session %s",
                                     session_id)
            self._grants.clear()
            self._pending_clears.clear()

    def _expire_session(self, session_id: str, grant_digest: str) -> None:
        with self._lock:
            grant = self._grants.get(session_id)
            if grant is None or grant.grant_digest != grant_digest:
                return
            if grant.expires_at > self._clock():
                return
            try:
                self._retire_grant(session_id, grant, approval_method="session_grant_expiry")
            except Exception:
                # The grant is no longer valid by its deadline even if clearing
                # the display fails. Retain a pending clear so no new session can
                # inherit stale output without another admitted clear operation.
                self._grants.pop(session_id, None)
                self._last_responses.pop(session_id, None)
                self._workload_modes.pop(session_id, None)
                grant.timer.cancel()
                self._pending_clears[session_id] = grant
                LOGGER.exception("Avatar phrase clear failed at grant expiry for session %s",
                                 session_id)

    def _retire_grant(self, session_id: str, grant: _SessionGrant, *,
                      approval_method: str) -> bool:
        try:
            cleared = self._clear_state(session_id, grant, approval_method=approval_method)
        except Exception:
            self._grants.pop(session_id, None)
            self._last_responses.pop(session_id, None)
            self._workload_modes.pop(session_id, None)
            grant.timer.cancel()
            self._pending_clears[session_id] = grant
            raise
        self._grants.pop(session_id, None)
        self._last_responses.pop(session_id, None)
        self._workload_modes.pop(session_id, None)
        grant.timer.cancel()
        if not cleared:
            self._pending_clears[session_id] = grant
            LOGGER.warning("Avatar phrase clear denied; display channel remains reserved for session %s",
                           session_id)
        return cleared

    def _clear_state(self, session_id: str, grant: _SessionGrant | None, *,
                     approval_method: str) -> bool:
        grant_digest = grant.grant_digest if grant is not None else "no_active_grant"
        approved_by = grant.approved_by if grant is not None else "operator"
        intent_hash = _digest({"session_id": session_id, "grant_digest": grant_digest,
                               "intent": "clear_chat_avatar_display"})
        context_hash = _digest({"session_id": session_id, "scope": self.SCOPE,
                                "grant_digest": grant_digest})
        admission = self._admit(
            request_type=RequestType.AVATAR_EMISSION, requester_id="bridge",
            intent_hash=intent_hash, context_hash=context_hash, policy_version="v1-static",
            metadata={"approved_by": approved_by, "approval_method": approval_method,
                "approval_scope": self.SCOPE, "approval_grant_digest": grant_digest,
                "session_id": session_id, "operation": "clear_display"},
        )
        if admission.decision is not Decision.ALLOW:
            return False
        record = admission.record
        if (record.request_type is not RequestType.AVATAR_EMISSION
                or record.intent_hash != intent_hash or record.context_hash != context_hash):
            raise RuntimeError("avatar_output_clear_binding_invalid")
        self._emitter.emit_idle(authorization=record, metadata={
            "source": "governed_chat_avatar_output_clear", "session_id": session_id,
            "approval_grant_digest": grant_digest, "approval_method": approval_method,
        })
        return True
