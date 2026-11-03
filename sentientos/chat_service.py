# mypy: disable-error-code=untyped-decorator
from __future__ import annotations

import argparse
import ipaddress
import logging
import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, List, Mapping, Protocol

from .fastapi_stub import FastAPI, HTMLResponse, HTTPException, Request

if TYPE_CHECKING:
    class BaseModel:
        def __init__(self, **data: object) -> None: ...
else:
    from pydantic import BaseModel

from .change_narrator import ChangeNarrator, build_default_change_narrator
from .event_stream import history as boot_history
from .foreground_game_bridge import BridgeForegroundGameDetector
from .avatar_renderer_report_ingress import RendererReportCaptureOwner
from .foreground_game_detection import normalize_game_process_names
from .governed_local_model_invocation import (
    GovernedLocalModelInvoker, LocalModelInvocationBudget,
    LocalModelInvocationReceipt, LocalModelPostEffectCustodyError,
)
from .installation_state import InstallationIdentity, InstallationStateRegistry
from .control_plane_kernel import ControlPlaneKernel
from .local_model_production_serving import ProductionServingController
from .local_model_serving_inference import ProductionServingInferenceController
from .chat_process_generation import open_chat_process_handoff
from .production_chat_resource_context import (
    ProductionChatResourceContextOwner,
    ResourceBackedProductionChatInference,
)
from .gaming_workload_policy import GamingWorkloadPolicy, WorkloadMode
from .conversation_session import (
    ConversationChatLockTimeout, ConversationSessionStore, assemble_local_chat_context,
    compact_runtime_generation_attribution,
)
from .canonical_memory import (AdmittedRetentionWriter, CanonicalMemoryStore, CANDIDATE_TYPE,
    ExplicitRetentionAdmissionGate, retention_request_id,
    sentientos_data_dir, sentientos_memory_dir)
from .local_model_authority import digest_payload

LOGGER = logging.getLogger(__name__)


def _is_recent_session_recall_request(message: str) -> bool:
    """Keep cross-session memories out of explicit recent-turn questions."""
    normalized = " ".join(message.casefold().split())
    markers = (
        "in this conversation", "in this chat", "earlier in this chat",
        "earlier in this conversation", "just before", "before you asked",
        "what did i just say", "what was my last message",
        "what was my previous message",
    )
    return any(marker in normalized for marker in markers)


def _is_social_checkin_request(message: str) -> bool:
    """Avoid treating casual check-ins as requests for topic-matched advice."""
    normalized = " ".join(message.casefold().split())
    markers = (
        "how are you", "how's it going", "how is it going", "how are things",
        "how do you feel", "just checking in", "just saying hi",
        "just saying hello", "how about you",
    )
    return any(marker in normalized for marker in markers)


APP = FastAPI(title="SentientOS Chat", version="1.0")
_CONVERSATION_SERVICE: "PersistentConversationService | None" = None
_PRODUCTION_COMPOSITION: "ProductionChatComposition | None" = None
try:
    _CHANGE_NARRATOR: ChangeNarrator | None = build_default_change_narrator()
except Exception:  # pragma: no cover - defensive initialization
    LOGGER.exception("Unable to initialise change narrator")
    _CHANGE_NARRATOR = None




class ChatInference(Protocol):
    def current_conversation_model_identity(self) -> Mapping[str, Any]: ...
    def generate(self, *, prompt: str, caller: str, correlation_id: str,
                 budget: LocalModelInvocationBudget,
                 caller_linkage: Mapping[str, Any]) -> LocalModelInvocationReceipt: ...


class ChatAvatarOutput(Protocol):
    def set_enabled(self, session_id: str, enabled: bool) -> dict[str, Any]: ...
    def state(self, session_id: str) -> dict[str, Any]: ...
    def publish_response(self, *, session_id: str, turn_id: str, text: str,
                         output_digest: str, workload_mode: str | None = None) -> Mapping[str, Any]: ...
    def set_workload_mode(self, session_id: str, workload_mode: str) -> Mapping[str, Any]: ...
    def publish_speech_timing(self, event: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def close(self) -> None: ...


class ChatSpeechOutput(Protocol):
    def set_enabled(self, session_id: str, enabled: bool) -> dict[str, Any]: ...
    def state(self, session_id: str | None) -> dict[str, Any]: ...
    def publish_response(self, *, session_id: str, turn_id: str, text: str,
                         output_digest: str) -> Mapping[str, Any]: ...
    def close(self) -> None: ...


class DevelopmentLocalChatInference:
    """Affirmative local development adapter; never selected by production."""
    __slots__ = ("_delegate", "_workload_mode", "_workload_lock",
                 "_residency_release", "_model_profiles", "_foreground_game_detector",
                 "_game_process_names", "_effective_workload_mode")
    def __init__(self, invoker: GovernedLocalModelInvoker,
                 model_profiles: Mapping[str, Any] | None = None,
                 foreground_game_detector: Any | None = None) -> None:
        self._delegate = invoker
        self._workload_mode: WorkloadMode = "normal"
        self._workload_lock = threading.RLock()
        self._residency_release: Mapping[str, Any] | None = None
        self._foreground_game_detector = foreground_game_detector
        self._game_process_names: tuple[str, ...] = ()
        self._effective_workload_mode = "normal"
        profiles = dict(model_profiles or {})
        if set(profiles) - {"normal", "gaming"}:
            raise ValueError("unsupported_local_model_profile")
        if any(value is None for value in profiles.values()):
            raise ValueError("local_model_profile_required")
        if "normal" in profiles:
            invoker.model = profiles["normal"]
        self._model_profiles = profiles
    def current_conversation_model_identity(self) -> Mapping[str, Any]:
        identity = getattr(self._delegate.model, "active_identity", None)
        return identity.to_dict() if identity is not None else {}
    def current_conversation_model_label(self) -> str | None:
        identity = getattr(self._delegate.model, "active_identity", None)
        authority_map = getattr(self._delegate, "authority_map", None)
        resolver = getattr(authority_map, "record_for_active_identity", None)
        if identity is None or not callable(resolver):
            return None
        record = resolver(identity, "local_user_chat")
        label = getattr(record, "name", None)
        return label if isinstance(label, str) and label else None
    def current_workload_mode(self) -> WorkloadMode:
        return self.current_workload_state()["effective_mode"]
    def current_workload_state(self) -> dict[str, Any]:
        with self._workload_lock:
            configured = self._workload_mode
            names = self._game_process_names
            detector = self._foreground_game_detector
            release = (dict(self._residency_release)
                if self._residency_release is not None else None)
        if configured == "automatic":
            try:
                observed = detector.observe(names) if detector is not None else None
            except Exception:
                observed = None
            if observed is not None and observed.status == "available":
                foreground = observed.game_foreground
                effective = "gaming" if foreground is True else "normal"
                source = ("foreground_allowlist_match" if foreground is True
                          else "foreground_allowlist_no_match")
                evidence = {
                    "status": observed.status, "source": source,
                    "game_foreground": foreground,
                    "process_name_digest": observed.process_name_digest,
                    "observed_at": observed.observed_at,
                    "transport_provenance": (dict(observed.transport_provenance)
                        if observed.transport_provenance is not None else None),
                }
            else:
                effective = "gaming"
                evidence = {
                    "status": (getattr(observed, "status", None)
                               or "observation_unavailable"),
                    "source": "foreground_observation_unavailable_conservative_gaming",
                    "game_foreground": None, "process_name_digest": None,
                    "observed_at": getattr(observed, "observed_at", None),
                    "transport_provenance": None,
                }
            source = evidence["source"]
        else:
            effective = configured
            source = "local_development_operator_selection"
            evidence = {"status": "operator_selected",
                "source": "local_development_session", "game_foreground": None,
                "process_name_digest": None, "observed_at": None,
                "transport_provenance": None}
        state: dict[str, Any] = {
            "mode": configured, "effective_mode": effective,
            "mode_source": source,
            "observation_status": evidence["status"],
            "game_foreground": evidence["game_foreground"],
            "foreground_game_detected": evidence["game_foreground"] is True,
            "workload_evidence": evidence,
        }
        if release is not None:
            state["residency_release"] = release
        return state
    def set_workload_mode(self, mode: str,
                          game_process_names: tuple[str, ...] | list[str] = ()) -> str:
        selected = GamingWorkloadPolicy.validate_mode(mode)
        names = (normalize_game_process_names(game_process_names)
                 if selected == "automatic" else ())
        target_mode = "gaming" if selected == "automatic" else selected
        with self._workload_lock:
            self._select_profile_locked(target_mode)
            self._workload_mode = selected
            self._game_process_names = names
        return selected
    def _select_profile_locked(self, selected: str) -> None:
        current_model = self._delegate.model
        target_model = self._model_profiles.get(selected)
        profile_changes = target_model is not None and target_model is not current_model
        identity = getattr(current_model, "active_identity", None)
        should_release = (
            profile_changes
            or (selected == "gaming" and self._effective_workload_mode != "gaming"
                and getattr(identity, "engine", None) == "ollama")
        )
        if should_release:
            receipt = self._delegate.release_model_residency()
            if receipt.status not in {"released", "already_unloaded", "not_applicable"}:
                raise RuntimeError("local_model_profile_release_unconfirmed")
            self._residency_release = receipt.to_dict()
        if profile_changes:
            target_identity = getattr(target_model, "active_identity", None)
            authority_map = getattr(self._delegate, "authority_map", None)
            resolver = getattr(authority_map, "record_for_active_identity", None)
            if (target_identity is None or not callable(resolver)
                    or resolver(target_identity, "local_user_chat") is None):
                raise RuntimeError("local_model_profile_authority_missing")
            self._delegate.model = target_model
        self._effective_workload_mode = selected
    def generate(self, *, prompt: str, caller: str, correlation_id: str,
                 budget: LocalModelInvocationBudget,
                 caller_linkage: Mapping[str, Any]) -> LocalModelInvocationReceipt:
        workload_state = self.current_workload_state()
        with self._workload_lock:
            if workload_state["mode"] != self._workload_mode:
                workload_state = self.current_workload_state()
            mode = workload_state["effective_mode"]
            if workload_state["mode"] == "automatic":
                self._select_profile_locked(mode)
            effective_prompt = GamingWorkloadPolicy.apply_chat_response_style(prompt, mode)
            effective_budget = GamingWorkloadPolicy.constrain_budget(mode, budget)
            linkage = {**dict(caller_linkage), "workload_mode": mode,
                "workload_evidence": workload_state["workload_evidence"]}
            identity = getattr(self._delegate.model, "active_identity", None)
            if mode == "gaming" and getattr(identity, "engine", None) == "ollama":
                linkage["ollama_keep_alive"] = "0"
            request = self._delegate.build_request(purpose="local_user_chat",
                prompt=effective_prompt, caller=caller, correlation_id=correlation_id,
                budget=effective_budget, linkage=linkage)
            return self._delegate.invoke(request)


# Backwards-compatible name for callers that used this adapter with test-only
# echo/null models before it also supported explicitly authorized local engines.
DevelopmentSimulationInference = DevelopmentLocalChatInference


class ProductionChatComposition:
    __slots__ = ("service", "_serving", "_resource_owner", "_foreground_game_detector",
                 "_renderer_report_capture_owner", "_avatar_output_owner")
    def __init__(self, service: "PersistentConversationService", serving: ProductionServingController,
                 resource_owner: ProductionChatResourceContextOwner | None = None,
                 foreground_game_detector: BridgeForegroundGameDetector | None = None,
                 renderer_report_capture_owner: RendererReportCaptureOwner | None = None,
                 avatar_output_owner: Any | None = None) -> None:
        self.service, self._serving = service, serving
        self._resource_owner = resource_owner
        self._foreground_game_detector = foreground_game_detector
        self._renderer_report_capture_owner = renderer_report_capture_owner
        self._avatar_output_owner = avatar_output_owner
    def close(self) -> None:
        try:
            self.service.close_outputs()
        finally:
            try:
                self._serving.close()
            finally:
                try:
                    if self._resource_owner is not None:
                        self._resource_owner.close()
                finally:
                    try:
                        if self._foreground_game_detector is not None:
                            self._foreground_game_detector.close()
                    finally:
                        try:
                            if self._renderer_report_capture_owner is not None:
                                self._renderer_report_capture_owner.close()
                        finally:
                            if self._avatar_output_owner is not None:
                                self._avatar_output_owner.close()
    def ready(self) -> bool:
        return self._serving.serving_is_current()

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    retain: bool = False
    request_id: str | None = None
    observe_screen: bool = False


class ChatResponse(BaseModel):
    response: str
    session_id: str
    turn_id: str
    context: dict[str, object]
    retention: dict[str, object]


class ChatWorkloadModeRequest(BaseModel):
    mode: str
    game_process_names: tuple[str, ...] = ()


class ChatAvatarOutputRequest(BaseModel):
    session_id: str
    enabled: bool


class ChatSpeechOutputRequest(BaseModel):
    session_id: str
    enabled: bool


class ChatRequestStateError(ValueError):
    """A replay conflict or an intentionally unreplayed interrupted request."""


class PersistentConversationService:
    """One transaction boundary for durable turns and governed inference.

    A denied/failed invocation intentionally preserves the user turn as an
    unanswered turn and never manufactures an assistant turn.
    """
    def __init__(self, *, inference: ChatInference, session_store: ConversationSessionStore,
                 memory_store: CanonicalMemoryStore, context_budget_chars: int = 4000,
                 memory_budget_chars: int = 1600, admission_gate: ExplicitRetentionAdmissionGate | None = None,
                 avatar_output: ChatAvatarOutput | None = None,
                 speech_output: ChatSpeechOutput | None = None,
                 screen_observer: Callable[[], Mapping[str, object] | None] | None = None) -> None:
        self._inference = inference; self.sessions = session_store; self.memories = memory_store
        self._avatar_output = avatar_output
        self._avatar_workload_sync_lock = threading.Lock()
        self._avatar_workload_mode_apply_lock = threading.Lock()
        self._avatar_workload_sync: dict[str, tuple[threading.Event, threading.Thread]] = {}
        self._avatar_workload_modes_observed: dict[str, str] = {}
        self._speech_output = speech_output
        self._screen_observer = screen_observer
        self.admission_gate = admission_gate or ExplicitRetentionAdmissionGate()
        self.retention_writer = AdmittedRetentionWriter(
            memory_store, admission_gate=self.admission_gate)
        self.context_budget_chars = context_budget_chars; self.memory_budget_chars = memory_budget_chars

    def create_session(self) -> str:
        """Create an empty session so clients can bind their first request idempotently."""
        identity = self._inference.current_conversation_model_identity()
        if not isinstance(identity, Mapping):
            raise RuntimeError("conversation_model_identity_unavailable")
        return str(self.sessions.create(model_identity=identity)["session_id"])

    def set_workload_mode(self, mode: str,
                          game_process_names: tuple[str, ...] | list[str] = ()) -> str:
        setter = getattr(self._inference, "set_workload_mode", None)
        if not callable(setter):
            raise RuntimeError("chat_workload_mode_unavailable")
        return str(setter(GamingWorkloadPolicy.validate_mode(mode), game_process_names))

    def current_workload_mode(self) -> str:
        getter = getattr(self._inference, "current_workload_mode", None)
        if not callable(getter):
            raise RuntimeError("chat_workload_mode_unavailable")
        return str(getter())

    def current_workload_state(self) -> dict[str, Any]:
        getter = getattr(self._inference, "current_workload_state", None)
        if not callable(getter):
            raise RuntimeError("chat_workload_mode_unavailable")
        return dict(getter())

    def screen_observation_configured(self) -> bool:
        return self._screen_observer is not None

    def _verified_runtime_context(self, *, identity: Mapping[str, Any],
                                  history: Any, memory: Mapping[str, Any],
                                  session_id: str,
                                  screen_observation: Mapping[str, Any] | None) -> dict[str, Any]:
        """Build small user-facing facts from live, already-owned runtime state."""
        model = {key: identity[key] for key in (
            "engine", "semantic_artifact_identity", "posture", "fallback")
            if key in identity and isinstance(identity[key], (str, bool))}
        label_resolver = getattr(self._inference, "current_conversation_model_label", None)
        if callable(label_resolver):
            try:
                label = label_resolver()
            except Exception:
                label = None
            if isinstance(label, str) and label:
                model["configured_candidate_label"] = label

        try:
            workload = self.current_workload_state()
            workload_context = {key: workload[key] for key in (
                "mode", "effective_mode", "mode_source", "observation_status")
                if key in workload and isinstance(workload[key], str)}
            observation_status = workload.get("observation_status")
            if observation_status == "available" and type(workload.get("game_foreground")) is bool:
                workload_context["game_foreground"] = workload["game_foreground"]
            elif workload.get("mode_source") == "local_development_operator_selection":
                workload_context["foreground_game_observation"] = "not_observed"
        except Exception:
            workload_context = {"availability": "unavailable"}

        try:
            avatar = self.avatar_output_state(session_id)
            avatar_context: dict[str, object] = {
                key: avatar.get(key) is True for key in ("configured", "enabled")}
        except Exception:
            avatar_context = {"configured": False, "enabled": False,
                              "status": "unavailable"}
        try:
            speech = self.speech_output_state(session_id)
            speech_context: dict[str, object] = {
                key: speech.get(key) is True
                for key in ("configured", "enabled", "backend_available")}
        except Exception:
            speech_context = {"configured": False, "enabled": False,
                              "backend_available": False, "status": "unavailable"}

        return {
            "system": {"name": "SentientOS", "runtime_posture": identity.get("posture", "unknown")},
            "assistant_role": "the active local model providing conversation inside SentientOS",
            "active_model": model,
            "workload": workload_context,
            "capabilities": {
                "local_conversation": "available",
                "conversation_history": {
                    "persisted_locally": True,
                    "prior_turns_included": len(history.turns),
                    "selected_history_truncated": bool(history.truncated),
                },
                "retrieved_memories_included": len(memory.get("memories", [])),
                "godot_avatar_output": avatar_context,
                "local_speech_output": speech_context,
                "screen_observation": {
                    "configured": self._screen_observer is not None,
                    "included_this_turn": screen_observation is not None,
                    "requires_per_message_opt_in": True,
                },
            },
        }

    def avatar_output_state(self, session_id: str | None) -> dict[str, Any]:
        if self._avatar_output is None:
            return {"configured": False, "enabled": False}
        if session_id is None:
            return {"configured": True, "enabled": False}
        self.sessions.load(session_id)
        return self._avatar_output.state(session_id)

    def set_avatar_output_enabled(self, session_id: str, enabled: bool) -> dict[str, Any]:
        if self._avatar_output is None:
            raise RuntimeError("chat_avatar_output_not_configured")
        self.sessions.load(session_id)
        result = self._avatar_output.set_enabled(session_id, enabled)
        if result.get("enabled") is True:
            self._sync_avatar_workload_mode(session_id)
            self._start_avatar_workload_sync(session_id)
        else:
            self._stop_avatar_workload_sync(session_id)
        return result

    def _sync_avatar_workload_mode(self, session_id: str) -> None:
        output = self._avatar_output
        setter = getattr(output, "set_workload_mode", None)
        if not callable(setter):
            return
        with self._avatar_workload_mode_apply_lock:
            try:
                state = self.current_workload_state()
                mode = state.get("effective_mode")
                if isinstance(mode, str) and mode in {"normal", "gaming"}:
                    with self._avatar_workload_sync_lock:
                        if self._avatar_workload_modes_observed.get(session_id) == mode:
                            return
                    result = setter(session_id, mode)
                    with self._avatar_workload_sync_lock:
                        self._avatar_workload_modes_observed[session_id] = mode
                    if result.get("status") == "admission_denied":
                        LOGGER.warning("Avatar workload update was denied by admission")
            except Exception as exc:
                LOGGER.warning("Avatar workload synchronization failed: %s", type(exc).__name__)

    def _start_avatar_workload_sync(self, session_id: str) -> None:
        if not callable(getattr(self._avatar_output, "set_workload_mode", None)):
            return
        with self._avatar_workload_sync_lock:
            current = self._avatar_workload_sync.get(session_id)
            if current is not None and current[1].is_alive():
                return
            stop_event = threading.Event()
            thread = threading.Thread(target=self._avatar_workload_sync_loop,
                args=(session_id, stop_event), name="chat-avatar-workload-sync", daemon=True)
            self._avatar_workload_sync[session_id] = (stop_event, thread)
            thread.start()

    def _stop_avatar_workload_sync(self, session_id: str) -> None:
        with self._avatar_workload_sync_lock:
            current = self._avatar_workload_sync.pop(session_id, None)
            self._avatar_workload_modes_observed.pop(session_id, None)
        if current is None:
            return
        stop_event, thread = current
        stop_event.set()
        if thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2)

    def _avatar_workload_sync_loop(self, session_id: str, stop_event: threading.Event) -> None:
        try:
            while not stop_event.is_set():
                try:
                    state = self.avatar_output_state(session_id)
                    if state.get("enabled") is not True:
                        return
                    self._sync_avatar_workload_mode(session_id)
                except Exception as exc:
                    LOGGER.warning("Avatar workload synchronization failed: %s", type(exc).__name__)
                if stop_event.wait(1.0):
                    return
        finally:
            with self._avatar_workload_sync_lock:
                current = self._avatar_workload_sync.get(session_id)
                if current is not None and current[0] is stop_event:
                    self._avatar_workload_sync.pop(session_id, None)
                    self._avatar_workload_modes_observed.pop(session_id, None)

    def speech_output_state(self, session_id: str | None) -> dict[str, Any]:
        if self._speech_output is None:
            return {"configured": False, "enabled": False, "backend_available": False}
        if session_id is not None:
            self.sessions.load(session_id)
        return self._speech_output.state(session_id)

    def set_speech_output_enabled(self, session_id: str, enabled: bool) -> dict[str, Any]:
        if self._speech_output is None:
            raise RuntimeError("chat_speech_output_not_configured")
        self.sessions.load(session_id)
        return self._speech_output.set_enabled(session_id, enabled)

    def close_avatar_output(self) -> None:
        with self._avatar_workload_sync_lock:
            sessions = tuple(self._avatar_workload_sync)
        for session_id in sessions:
            self._stop_avatar_workload_sync(session_id)
        if self._avatar_output is not None:
            self._avatar_output.close()

    def close_outputs(self) -> None:
        try:
            self.close_avatar_output()
        finally:
            if self._speech_output is not None:
                self._speech_output.close()

    def _recover_idempotent_response(self, session_id: str,
                                     user_turn: Mapping[str, Any]) -> ChatResponse:
        session = self.sessions.load(session_id)
        user_turn_id = str(user_turn.get("turn_id", ""))
        assistants = [turn for turn in session["turns"]
            if turn.get("role") == "assistant"
            and isinstance(turn.get("linkage"), Mapping)
            and turn["linkage"].get("source_user_turn_id") == user_turn_id]
        if not assistants:
            inspector = getattr(self._inference, "inspect_interrupted_chat_invocation", None)
            if callable(inspector):
                user_linkage = user_turn.get("linkage")
                client_digest = (user_linkage.get("client_request_id_digest")
                    if isinstance(user_linkage, Mapping) else None)
                try:
                    custody = inspector(session_id=session_id, user_turn_id=user_turn_id,
                        client_request_id_digest=client_digest)
                except Exception as exc:
                    raise ChatRequestStateError(
                        "chat_request_interrupted_invocation_recovery_unavailable_no_replay") from exc
                posture = custody.get("status") if isinstance(custody, Mapping) else None
                if posture == "completed_response_body_not_retained":
                    raise ChatRequestStateError(
                        "chat_request_interrupted_completed_invocation_response_not_retained_no_replay")
                if posture == "matching_invocation_receipt_incomplete":
                    raise ChatRequestStateError(
                        "chat_request_interrupted_matching_invocation_receipt_incomplete_no_replay")
                if posture == "no_matching_verified_invocation_receipt":
                    raise ChatRequestStateError(
                        "chat_request_interrupted_no_matching_invocation_receipt_no_replay")
                raise ChatRequestStateError(
                    "chat_request_interrupted_invocation_recovery_posture_invalid_no_replay")
            raise ChatRequestStateError("chat_request_interrupted_no_replay")
        if len(assistants) != 1:
            raise ChatRequestStateError("chat_request_response_identity_conflict")
        assistant = assistants[0]
        linkage = assistant.get("linkage", {})
        if not isinstance(linkage, Mapping):
            raise ChatRequestStateError("chat_request_response_lineage_invalid")
        verifier = getattr(self._inference, "verify_stored_chat_invocation", None)
        if callable(verifier):
            try:
                verified = verifier(
                    receipt_id=linkage["invocation_receipt_id"],
                    receipt_digest=linkage["invocation_receipt_digest"],
                    session_id=session_id,
                    user_turn_id=user_turn_id,
                    assistant_text=str(assistant.get("text", "")),
                    client_request_id_digest=(
                        user_turn.get("linkage", {}).get("client_request_id_digest")
                        if isinstance(user_turn.get("linkage"), Mapping) else None
                    ),
                )
            except Exception as exc:
                raise ChatRequestStateError("chat_request_response_receipt_unavailable") from exc
            active_identity = linkage.get("active_model_identity")
            loaded_identity = linkage.get("loaded_model_identity")
            stored_runtime_lineage = linkage.get("software_generation_attribution")
            observed_runtime_lineage = verified.get("software_generation_attribution")
            verified_caller_linkage = verified.get("caller_linkage")
            observed_predecessor_reference = (
                verified_caller_linkage.get("verified_predecessor_invocation")
                if isinstance(verified_caller_linkage, Mapping) else None)
            predecessor_reference_matches = (
                "predecessor_invocation_reference" not in linkage
                or linkage.get("predecessor_invocation_reference")
                    == observed_predecessor_reference)
            runtime_lineage_matches = (
                stored_runtime_lineage is None
                or (isinstance(stored_runtime_lineage, Mapping)
                    and isinstance(observed_runtime_lineage, Mapping)
                    and (dict(observed_runtime_lineage) == dict(stored_runtime_lineage)
                        or compact_runtime_generation_attribution(observed_runtime_lineage)
                            == dict(stored_runtime_lineage)))
            )
            if (not isinstance(active_identity, Mapping) or not isinstance(loaded_identity, Mapping)
                    or dict(verified.get("serving_identity", {})) != dict(active_identity)
                    or dict(verified.get("loaded_model_identity", {})) != dict(loaded_identity)
                    or not predecessor_reference_matches
                    or not runtime_lineage_matches
                    or (linkage.get("assistant_output_lineage") is not None
                        and dict(verified.get("assistant_output_lineage", {}))
                            != dict(linkage["assistant_output_lineage"]))):
                raise ChatRequestStateError("chat_request_response_receipt_conflict")
        elif not isinstance(self._inference, DevelopmentLocalChatInference):
            raise ChatRequestStateError("chat_request_recovery_verifier_unavailable")
        retention_state = user_turn.get("retention_state")
        if retention_state == "requested":
            recovery = self.retention_writer.recover_existing_artifact(user_turn, session_id)
            if (recovery.get("artifact_status") == "verified"
                    and isinstance(recovery.get("receipt"), Mapping)):
                recovered_receipt = dict(recovery.pop("receipt"))
                self.sessions.update_turn_retention(
                    session_id, user_turn_id, state="retained", receipt=recovered_receipt)
                retention = {
                    "status": ("retained_artifact_completed_from_verified_stage"
                        if recovery.get("staged_artifact_published") is True
                        else "retained_artifact_reconciled_no_write"),
                    "recovery_verification": recovery,
                }
            elif recovery.get("artifact_status") == "conflict":
                retention = {
                    "status": "retention_interrupted_artifact_conflict_no_replay",
                    "recovery_verification": recovery,
                }
            else:
                retention = {"status": "retention_interrupted_no_replay"}
        elif retention_state == "retained":
            verifier = getattr(self.retention_writer, "verify_committed_artifact", None)
            stored_receipt = user_turn.get("retention_receipt")
            if callable(verifier) and isinstance(stored_receipt, Mapping):
                try:
                    verification = verifier(stored_receipt, user_turn, session_id)
                except Exception:
                    verification = {"artifact_status": "unavailable",
                        "reason_code": "artifact_verifier_failed",
                        "admission_status": "not_independently_recoverable",
                        "write_replayed": False}
            else:
                verification = {"artifact_status": "unavailable",
                    "reason_code": "artifact_verifier_unavailable",
                    "admission_status": "not_independently_recoverable",
                    "write_replayed": False}
            if (verification.get("artifact_status") == "verified"
                    and verification.get("admission_status")
                        == "policy_recomputed_not_execution_attested"):
                status = "retained_artifact_verified_policy_recomputed"
            elif (verification.get("artifact_status") == "verified"
                    and verification.get("admission_status") == "conflict"):
                status = "retained_artifact_admission_conflict"
            else:
                status = "retained_state_unverified_no_replay"
            retention = {"status": status, "recovery_verification": verification}
        elif retention_state == "retention_failed":
            retention = {"status": "retention_failed_historical_no_replay"}
        elif retention_state == "not_requested":
            retention = {"status": "not_requested"}
        else:
            retention = {"status": "retention_state_unknown_no_replay"}
        return ChatResponse(
            response=str(assistant["text"]), session_id=session_id,
            turn_id=str(assistant["turn_id"]),
            context={
                "conversation_snapshot_digest": linkage.get("context_snapshot_digest"),
                "memory_snapshot_digest": linkage.get("memory_snapshot_digest"),
                "memory_retrieval_posture": linkage.get("memory_retrieval_posture", "unknown_legacy"),
                "legacy_sidecar_posture": linkage.get("legacy_sidecar_posture", "unknown_legacy"),
                "memory_selection_posture": linkage.get("memory_selection_posture", "unknown_legacy"),
                "omitted_memory_count": linkage.get("omitted_memory_count"),
                "active_model_identity_digest": linkage.get("active_model_identity_digest"),
                "loaded_model_identity_digest": linkage.get("loaded_model_identity_digest"),
                "recovered_without_inference": True,
            },
            retention=retention,
        )

    def chat(self, message: str, *, session_id: str | None = None, retain: bool = False,
             request_id: str | None = None, observe_screen: bool = False) -> ChatResponse:
        if session_id is None:
            return self._chat_unlocked(message, session_id=None, retain=retain,
                request_id=request_id, observe_screen=observe_screen)
        try:
            with self.sessions.serialize_chat_requests(session_id):
                return self._chat_unlocked(message, session_id=session_id,
                    retain=retain, request_id=request_id, observe_screen=observe_screen)
        except ConversationChatLockTimeout as exc:
            raise ChatRequestStateError("chat_session_request_lock_timeout") from exc

    def _chat_unlocked(self, message: str, *, session_id: str | None = None,
                       retain: bool = False, request_id: str | None = None,
                       observe_screen: bool = False) -> ChatResponse:
        if type(observe_screen) is not bool:
            raise ChatRequestStateError("screen_observation_request_invalid")
        request_options_digest = (hashlib.sha256(json.dumps(
            {"observe_screen": True}, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest() if observe_screen else None)
        if request_id is not None:
            if session_id is None:
                raise ChatRequestStateError("idempotent_request_requires_existing_session")
            try:
                existing = self.sessions.find_user_request(session_id,
                    request_id=request_id, text=message, retain=retain,
                    request_options_digest=request_options_digest)
            except FileNotFoundError:
                raise
            except ValueError as exc:
                raise ChatRequestStateError(str(exc)) from exc
            if existing is not None:
                return self._recover_idempotent_response(session_id, existing)
        screen_observation: Mapping[str, object] | None = None
        if observe_screen:
            if self._screen_observer is None:
                raise RuntimeError("screen_observation_not_configured")
            screen_observation = self._screen_observer()
            if not isinstance(screen_observation, Mapping):
                raise RuntimeError("screen_observation_unavailable")
            screen_text = screen_observation.get("text")
            capture_digest = screen_observation.get("capture_digest")
            captured_at = screen_observation.get("captured_at")
            if (screen_observation.get("modality") != "screen"
                    or screen_observation.get("raw_frame_retained") is not False
                    or not isinstance(screen_text, str) or not screen_text.strip()
                    or len(screen_text) > 1200
                    or not isinstance(captured_at, str) or len(captured_at) > 64
                    or screen_observation.get("capture_scope")
                        != "allowlisted_foreground_game_client_area"
                    or not isinstance(capture_digest, str) or len(capture_digest) != 64
                    or any(character not in "0123456789abcdef" for character in capture_digest)):
                raise RuntimeError("screen_observation_contract_invalid")
        identity_payload = self._inference.current_conversation_model_identity()
        session = self.sessions.create(model_identity=identity_payload) if session_id is None else self.sessions.load(session_id)
        if request_id is None:
            user_turn = self.sessions.append_turn(session["session_id"], role="user", text=message,
                retention_state="requested" if retain else "not_requested")
        else:
            try:
                user_turn, created = self.sessions.append_user_request(session["session_id"],
                    request_id=request_id, text=message, retain=retain,
                    request_options_digest=request_options_digest)
            except ValueError as exc:
                raise ChatRequestStateError(str(exc)) from exc
            if not created:
                return self._recover_idempotent_response(session["session_id"], user_turn)
        if self._speech_output is not None:
            interrupt_speech = getattr(self._speech_output, "interrupt", None)
            if callable(interrupt_speech):
                try:
                    interrupt_speech(session["session_id"])
                except Exception as exc:
                    LOGGER.warning("Local speech interruption failed: %s", type(exc).__name__)
        prior_assistant = next((turn for turn in reversed(session.get("turns", ()))
            if turn.get("role") == "assistant"), None)
        predecessor_identity_digest = str(session.get("model_identity_digest", ""))
        predecessor_identity: Mapping[str, Any] | None = None
        predecessor_runtime_lineage: Mapping[str, Any] | None = None
        predecessor_invocation_reference: Mapping[str, str] | None = None
        predecessor_invocation_verified = False
        if prior_assistant is not None and isinstance(prior_assistant.get("linkage"), Mapping):
            prior_linkage = prior_assistant["linkage"]
            predecessor_identity_digest = str(prior_linkage.get("active_model_identity_digest", ""))
            stored_identity = prior_linkage.get("active_model_identity")
            prior_source_user_turn_id = prior_linkage.get("source_user_turn_id")
            prior_user_turn = next((turn for turn in reversed(session.get("turns", ()))
                if turn.get("role") == "user"
                and turn.get("turn_id") == prior_source_user_turn_id), None)
            prior_user_linkage = (prior_user_turn.get("linkage")
                if isinstance(prior_user_turn, Mapping) else None)
            prior_client_request_digest = (prior_user_linkage.get("client_request_id_digest")
                if isinstance(prior_user_linkage, Mapping) else None)
            prior_client_digest_valid = (prior_client_request_digest is None
                or (isinstance(prior_client_request_digest, str)
                    and len(prior_client_request_digest) == 64
                    and all(character in "0123456789abcdef"
                        for character in prior_client_request_digest)))
            verifier = getattr(self._inference, "verify_stored_chat_invocation", None)
            if (callable(verifier) and isinstance(stored_identity, Mapping)
                    and isinstance(prior_linkage.get("invocation_receipt_id"), str)
                    and isinstance(prior_linkage.get("invocation_receipt_digest"), str)
                    and isinstance(prior_source_user_turn_id, str)
                    and isinstance(prior_user_turn, Mapping) and prior_client_digest_valid):
                try:
                    verified_prior = verifier(receipt_id=prior_linkage["invocation_receipt_id"],
                        receipt_digest=prior_linkage["invocation_receipt_digest"],
                        session_id=session["session_id"], user_turn_id=prior_source_user_turn_id,
                        assistant_text=str(prior_assistant.get("text", "")),
                        client_request_id_digest=prior_client_request_digest)
                    observed_prior_identity = verified_prior.get("serving_identity")
                    observed_loaded_identity = verified_prior.get("loaded_model_identity")
                    stored_loaded_identity = prior_linkage.get("loaded_model_identity")
                    observed_output_lineage = verified_prior.get("assistant_output_lineage")
                    stored_output_lineage = prior_linkage.get("assistant_output_lineage")
                    observed_runtime_lineage = verified_prior.get("software_generation_attribution")
                    stored_runtime_lineage = prior_linkage.get("software_generation_attribution")
                    output_lineage_matches = (
                        stored_output_lineage is None
                        or (isinstance(observed_output_lineage, Mapping)
                            and isinstance(stored_output_lineage, Mapping)
                            and dict(observed_output_lineage) == dict(stored_output_lineage))
                    )
                    runtime_lineage_matches = (
                        stored_runtime_lineage is None
                        or (isinstance(observed_runtime_lineage, Mapping)
                            and isinstance(stored_runtime_lineage, Mapping)
                            and (dict(observed_runtime_lineage) == dict(stored_runtime_lineage)
                                or compact_runtime_generation_attribution(observed_runtime_lineage)
                                    == dict(stored_runtime_lineage)))
                    )
                    observed_caller_linkage = verified_prior.get("caller_linkage")
                    stored_predecessor_reference = prior_linkage.get(
                        "predecessor_invocation_reference")
                    observed_predecessor_reference = (
                        observed_caller_linkage.get("verified_predecessor_invocation")
                        if isinstance(observed_caller_linkage, Mapping) else None)
                    predecessor_reference_matches = (
                        "predecessor_invocation_reference" not in prior_linkage
                        or stored_predecessor_reference == observed_predecessor_reference)
                    verified_request_id = verified_prior.get("request_id")
                    stored_request_id = prior_linkage.get("request_id")
                    prior_receipt_identity_matches = (
                        verified_prior.get("receipt_id") == prior_linkage.get("invocation_receipt_id")
                        and verified_prior.get("receipt_digest")
                            == prior_linkage.get("invocation_receipt_digest")
                        and isinstance(verified_request_id, str)
                        and (stored_request_id is None or verified_request_id == stored_request_id))
                    if (output_lineage_matches and runtime_lineage_matches
                            and predecessor_reference_matches and prior_receipt_identity_matches
                            and isinstance(observed_prior_identity, Mapping)
                            and isinstance(observed_loaded_identity, Mapping)
                            and isinstance(stored_loaded_identity, Mapping)
                            and dict(observed_prior_identity) == dict(stored_identity)
                            and dict(observed_loaded_identity) == dict(stored_loaded_identity)
                            and predecessor_identity_digest == hashlib.sha256(json.dumps(dict(stored_identity),
                                sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()):
                        predecessor_identity = observed_prior_identity
                        if isinstance(observed_runtime_lineage, Mapping):
                            predecessor_runtime_lineage = dict(observed_runtime_lineage)
                        predecessor_invocation_reference = {
                            "receipt_id": str(verified_prior["receipt_id"]),
                            "receipt_digest": str(verified_prior["receipt_digest"]),
                            "request_id": verified_request_id,
                            "source_user_turn_id": prior_source_user_turn_id,
                        }
                        predecessor_invocation_verified = True
                except Exception:
                    # Prior transcript remains usable as untrusted chat context;
                    # it cannot establish a transition predecessor.
                    pass
        history_budget = self.context_budget_chars
        gaming_development_turn = (
            isinstance(self._inference, DevelopmentLocalChatInference)
            and self._inference.current_workload_mode() == "gaming")
        if gaming_development_turn:
            # Start with a modest history window, then account for the complete
            # trusted gaming instruction and prompt structure before invocation.
            history_budget = min(history_budget, 2000)
        recent_session_recall = _is_recent_session_recall_request(message)
        social_checkin = _is_social_checkin_request(message)
        history_roles = ("user",) if recent_session_recall or social_checkin else None
        history = self.sessions.reconstruct(session["session_id"], budget_chars=history_budget,
            exclude_turn_id=user_turn["turn_id"], include_roles=history_roles)
        # Exact recall and casual check-ins rely on the active transcript.
        # Lexical long-term retrieval can otherwise over-weight topic-matching
        # memories, while old assistant advice can make a greeting sound like
        # another request for help.
        memory_query = "" if recent_session_recall or social_checkin else message
        memory = self.memories.retrieve(memory_query, budget_chars=self.memory_budget_chars)
        runtime_context = self._verified_runtime_context(
            identity=identity_payload, history=history, memory=memory,
            session_id=session["session_id"], screen_observation=screen_observation)
        prompt = assemble_local_chat_context(history=history, memory_snapshot=memory,
            current_message=message,
            runtime_context=runtime_context,
            verified_prior_runtime_lineage=predecessor_runtime_lineage,
            screen_observation=screen_observation,
            compact_history=gaming_development_turn)
        if gaming_development_turn:
            while history_budget > 0:
                effective_prompt = GamingWorkloadPolicy.apply_chat_response_style(
                    prompt, "gaming")
                overflow = (len(effective_prompt)
                    - GamingWorkloadPolicy.GAMING_MAX_INPUT_CHARS)
                if overflow <= 0:
                    break
                next_budget = max(0, history_budget - overflow)
                if next_budget == history_budget:
                    next_budget = 0
                history_budget = next_budget
                history = self.sessions.reconstruct(
                    session["session_id"], budget_chars=history_budget,
                    exclude_turn_id=user_turn["turn_id"], include_roles=history_roles)
                runtime_context = self._verified_runtime_context(
                    identity=identity_payload, history=history, memory=memory,
                    session_id=session["session_id"], screen_observation=screen_observation)
                prompt = assemble_local_chat_context(history=history,
                    memory_snapshot=memory, current_message=message,
                    runtime_context=runtime_context,
                    verified_prior_runtime_lineage=predecessor_runtime_lineage,
                    screen_observation=screen_observation,
                    compact_history=True)
        linkage = {"session_id": session["session_id"], "user_turn_id": user_turn["turn_id"],
                   "conversation_context_snapshot_digest": history.snapshot_digest,
                   "memory_retrieval_snapshot_digest": memory["snapshot_digest"]}
        if predecessor_runtime_lineage is not None:
            linkage["verified_predecessor_runtime_handoff_digest"] = str(
                predecessor_runtime_lineage.get("handoff_digest", ""))
            linkage["verified_predecessor_runtime_software_generation_digest"] = str(
                predecessor_runtime_lineage.get("software_generation_digest", ""))
        if predecessor_invocation_reference is not None:
            linkage["verified_predecessor_invocation"] = dict(
                predecessor_invocation_reference)
        if screen_observation is not None:
            screen_provenance: dict[str, object] = {
                "capture_digest": screen_observation["capture_digest"],
                "text_digest": hashlib.sha256(str(screen_observation["text"]).encode("utf-8")).hexdigest(),
                "capture_scope": "allowlisted_foreground_game_client_area",
                "captured_at": screen_observation["captured_at"],
                "raw_frame_retained": False,
            }
            for key in ("process_name_digest", "consent_id_digest"):
                value = screen_observation.get(key)
                if (isinstance(value, str) and len(value) == 64
                        and all(character in "0123456789abcdef" for character in value)):
                    screen_provenance[key] = value
            bridge_provenance = screen_observation.get("bridge_message_provenance")
            if isinstance(bridge_provenance, Mapping):
                bridge_fields = {
                    "message_id", "source_id", "session_id", "generation_id",
                    "sequence", "created_at", "payload_digest",
                }
                message_id = bridge_provenance.get("message_id")
                payload_digest = bridge_provenance.get("payload_digest")
                source_id = bridge_provenance.get("source_id")
                source_session_id = bridge_provenance.get("session_id")
                generation_id = bridge_provenance.get("generation_id")
                sequence = bridge_provenance.get("sequence")
                created_at = bridge_provenance.get("created_at")
                if (set(bridge_provenance) == bridge_fields
                        and isinstance(message_id, str) and len(message_id) == 64
                        and all(character in "0123456789abcdef" for character in message_id)
                        and isinstance(payload_digest, str) and len(payload_digest) == 64
                        and all(character in "0123456789abcdef" for character in payload_digest)
                        and isinstance(source_id, str) and source_id
                        and isinstance(source_session_id, str) and source_session_id
                        and isinstance(generation_id, str) and generation_id
                        and type(sequence) is int and sequence > 0
                        and isinstance(created_at, str) and len(created_at) <= 64):
                    screen_provenance["bridge_message_provenance"] = dict(bridge_provenance)
            linkage["screen_observation_provenance"] = screen_provenance
        client_request_digest = (user_turn.get("linkage", {}).get("client_request_id_digest")
            if isinstance(user_turn.get("linkage"), Mapping) else None)
        if isinstance(client_request_digest, str):
            linkage["client_request_id_digest"] = client_request_digest
        receipt = self._inference.generate(prompt=prompt, caller="chat_service",
            correlation_id=f"chat:{session['session_id']}:{user_turn['turn_id']}",
            budget=LocalModelInvocationBudget(max_input_chars=8000), caller_linkage=linkage)
        accepted_statuses = {"admitted_completed"}
        if isinstance(self._inference, DevelopmentLocalChatInference):
            accepted_statuses.add("admitted_simulation")
        if receipt.status not in accepted_statuses or not receipt.output_text:
            raise RuntimeError(f"governed_inference_not_completed:{receipt.status}")
        if not isinstance(receipt.output_digest, str):
            raise RuntimeError("invocation_output_digest_missing")
        transcript_output_digest = digest_payload({"text": receipt.output_text})
        if (not receipt.output_truncated
                and digest_payload({"output": receipt.output_text}) != receipt.output_digest):
            raise RuntimeError("invocation_output_transcript_mismatch")
        assistant_output_lineage = {
            "status": ("exact_invocation_output_match" if not receipt.output_truncated
                       else "truncated_transcript_original_output_relation_unknown"),
            "invocation_output_digest": receipt.output_digest,
            "transcript_text_digest": transcript_output_digest,
            "output_truncated": receipt.output_truncated,
        }
        request_linkage = receipt.request.get("linkage", {})
        if isinstance(self._inference, DevelopmentLocalChatInference):
            software_generation_attribution = {
                "status": "development_only",
                "reason_code": "not_a_production_process_observation",
                "generation_identity": None,
                "process_instance_id": None,
            }
        else:
            verifier = getattr(self._inference, "verify_stored_chat_invocation", None)
            if not callable(verifier):
                raise RuntimeError("chat_process_software_generation_verifier_unavailable")
            request_client_digest = (user_turn.get("linkage", {}).get("client_request_id_digest")
                if isinstance(user_turn.get("linkage"), Mapping) else None)
            try:
                verified_current = verifier(receipt_id=receipt.receipt_id,
                    receipt_digest=receipt.receipt_digest,
                    session_id=session["session_id"], user_turn_id=user_turn["turn_id"],
                    assistant_text=receipt.output_text,
                    client_request_id_digest=request_client_digest)
            except Exception as exc:
                raise RuntimeError("chat_process_current_invocation_verification_failed") from exc
            observed_posture = (request_linkage.get("software_generation_attribution")
                if isinstance(request_linkage, Mapping) else None)
            verified_posture = verified_current.get("software_generation_attribution")
            if (not isinstance(observed_posture, Mapping)
                    or not isinstance(verified_posture, Mapping)
                    or dict(observed_posture) != dict(verified_posture)):
                raise RuntimeError("chat_process_software_generation_posture_invalid")
            software_generation_attribution = dict(verified_posture)
        invoked_identity = receipt.request.get("active_model_identity", {})
        upstream = receipt.request.get("upstream_evidence", {})
        serving_lifetime = (upstream.get("current_serving_lifetime")
            if isinstance(upstream, Mapping) else None)
        workload_mode = (serving_lifetime.get("workload_mode")
            if isinstance(serving_lifetime, Mapping) else None)
        if not isinstance(workload_mode, str) or workload_mode not in {"normal", "gaming"}:
            workload_mode = None
        if not isinstance(invoked_identity, Mapping) or not isinstance(identity_payload, Mapping):
            raise RuntimeError("invocation_model_identity_mismatch")
        if "observed_loaded_model_identity" in identity_payload:
            observed_loaded_identity = identity_payload.get("observed_loaded_model_identity")
            if (not isinstance(serving_lifetime, Mapping)
                    or not isinstance(observed_loaded_identity, Mapping)
                    or any(serving_lifetime.get(key) != value
                        for key, value in identity_payload.items())
                    or dict(invoked_identity) != dict(observed_loaded_identity)):
                raise RuntimeError("invocation_model_identity_mismatch")
            caller_context = serving_lifetime.get("caller_context")
            if (not isinstance(caller_context, Mapping)
                    or caller_context.get("session_id") != session["session_id"]
                    or caller_context.get("user_turn_id") != user_turn["turn_id"]):
                raise RuntimeError("invocation_conversation_context_mismatch")
        elif dict(invoked_identity) != dict(identity_payload):
            raise RuntimeError("invocation_model_identity_mismatch")
        serving_identity_digest = hashlib.sha256(json.dumps(dict(identity_payload), sort_keys=True,
            separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        loaded_identity_digest = hashlib.sha256(json.dumps(dict(invoked_identity), sort_keys=True,
            separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        continuity_posture = "model_identity_changed_predecessor_relation_unverified"
        if predecessor_identity_digest == serving_identity_digest:
            continuity_posture = ("same_exact_serving_identity_and_prior_invocation_verified"
                if predecessor_invocation_verified else "same_exact_serving_identity_prior_receipt_unverified")
        elif predecessor_invocation_verified and predecessor_identity is not None:
            prior_generation = predecessor_identity.get("activation_generation")
            current_generation = identity_payload.get("activation_generation")
            if (predecessor_identity.get("installation_identity") == identity_payload.get("installation_identity")
                    and identity_payload.get("activation_predecessor_state_digest")
                        == predecessor_identity.get("activation_state_semantic_digest")
                    and type(prior_generation) is int and type(current_generation) is int
                    and current_generation == prior_generation + 1):
                continuity_posture = "activation_predecessor_bound_to_prior_observed_invocation"
        assistant = self.sessions.append_turn(session["session_id"], role="assistant", text=receipt.output_text,
            linkage={"request_id": receipt.request.get("request_id"),
                     "invocation_receipt_id": receipt.receipt_id,
                     "invocation_receipt_digest": receipt.receipt_digest,
                     "source_user_turn_id": user_turn["turn_id"],
                     "active_model_identity": dict(identity_payload),
                     "active_model_identity_digest": serving_identity_digest,
                     "loaded_model_identity": dict(invoked_identity),
                     "loaded_model_identity_digest": loaded_identity_digest,
                     "software_generation_attribution": compact_runtime_generation_attribution(
                         software_generation_attribution),
                     "assistant_output_lineage": assistant_output_lineage,
                     "predecessor_model_identity_digest": predecessor_identity_digest,
                     "predecessor_invocation_reference": (
                         dict(predecessor_invocation_reference)
                         if predecessor_invocation_reference is not None else None),
                     "model_identity_continuity_posture": continuity_posture,
                     "context_snapshot_digest": history.snapshot_digest,
                     "memory_snapshot_digest": memory["snapshot_digest"],
                     "screen_observation_provenance": (
                         dict(linkage["screen_observation_provenance"])
                         if isinstance(linkage.get("screen_observation_provenance"), Mapping)
                         else None),
                     "memory_retrieval_posture": memory["retrieval_posture"],
                     "legacy_sidecar_posture": memory.get("legacy_sidecar_posture", "unknown_legacy"),
                     "memory_selection_posture": memory.get("selection_posture", "unknown_legacy"),
                     "omitted_memory_count": memory.get("omitted_memory_count")})
        if self._avatar_output is not None:
            try:
                avatar_publication: dict[str, Any] = {
                    "session_id": session["session_id"],
                    "turn_id": str(assistant["turn_id"]),
                    "text": receipt.output_text,
                    "output_digest": transcript_output_digest,
                }
                if workload_mode is not None:
                    avatar_publication["workload_mode"] = workload_mode
                publication = self._avatar_output.publish_response(**avatar_publication)
                if publication.get("status") == "emitted":
                    with self._avatar_workload_sync_lock:
                        self._avatar_workload_modes_observed.pop(session["session_id"], None)
                    self._sync_avatar_workload_mode(session["session_id"])
            except Exception as exc:
                LOGGER.warning("Avatar response publication failed: %s", type(exc).__name__)
        if self._speech_output is not None:
            try:
                self._speech_output.publish_response(
                    session_id=session["session_id"], turn_id=str(assistant["turn_id"]),
                    text=receipt.output_text, output_digest=transcript_output_digest)
            except Exception as exc:
                LOGGER.warning("Local speech publication failed: %s", type(exc).__name__)
        retention_result: dict[str, object] = {"status": "not_requested"}
        if retain:
            operation_id = "retain:" + session["session_id"] + ":" + user_turn["turn_id"]
            request_id = retention_request_id(operation_id)
            candidate = {"candidate_type": CANDIDATE_TYPE, "session_id": session["session_id"],
                         "source_turn_id": user_turn["turn_id"], "source_role": "user",
                         "source_text_digest": user_turn["text_digest"], "explicitly_requested": True,
                         "request_id": request_id, "operation_id": operation_id}
            admission = self.admission_gate.decide(candidate)
            try:
                if admission.decision != "retention_admitted": raise PermissionError(admission.reason or "retention_denied")
                retention_result = self.retention_writer.execute(candidate, admission, user_turn)
                self.sessions.update_turn_retention(session["session_id"], user_turn["turn_id"], state="retained", receipt=retention_result)
            except Exception as exc:
                try:
                    recovery = self.retention_writer.recover_existing_artifact(
                        user_turn, session["session_id"])
                except Exception:
                    recovery = {
                        "artifact_status": "unavailable",
                        "reason_code": "post_error_recovery_unavailable",
                        "admission_status": "not_independently_recoverable",
                        "write_replayed": False,
                    }
                if (recovery.get("artifact_status") == "verified"
                        and isinstance(recovery.get("receipt"), Mapping)):
                    recovered_receipt = dict(recovery.pop("receipt"))
                    self.sessions.update_turn_retention(
                        session["session_id"], user_turn["turn_id"],
                        state="retained", receipt=recovered_receipt)
                    retention_result = {
                        "status": ("retained_artifact_completed_from_verified_stage"
                            if recovery.get("staged_artifact_published") is True
                            else "retained_artifact_reconciled_after_write_error"),
                        "recovery_verification": recovery,
                    }
                else:
                    retention_result = {
                        "status": "retention_failed", "reason": str(exc),
                        "admission_receipt_digest": admission.receipt_digest,
                        "recovery_verification": recovery,
                    }
                    self.sessions.update_turn_retention(
                        session["session_id"], user_turn["turn_id"],
                        state="retention_failed", receipt=retention_result)
        return ChatResponse(response=receipt.output_text, session_id=session["session_id"], turn_id=assistant["turn_id"],
                            context={"conversation_snapshot_digest": history.snapshot_digest,
                                     "memory_snapshot_digest": memory["snapshot_digest"],
                                     "memory_retrieval_posture": memory["retrieval_posture"],
                                     "legacy_sidecar_posture": memory.get("legacy_sidecar_posture", "unknown_legacy"),
                                     "memory_selection_posture": memory.get("selection_posture", "unknown_legacy"),
                                     "omitted_memory_count": memory.get("omitted_memory_count"),
                                     "active_model_identity_digest": serving_identity_digest,
                                     "loaded_model_identity_digest": loaded_identity_digest,
                                     "model_identity_continuity_posture": continuity_posture,
                                     "screen_observation_provenance": (
                                         dict(linkage["screen_observation_provenance"])
                                         if isinstance(linkage.get("screen_observation_provenance"), Mapping)
                                         else None),
                                     "selected_turn_count": len(history.turns), "selected_memory_count": len(memory["memories"])},
                            retention=retention_result)


def _get_conversation_service() -> PersistentConversationService:
    if _CONVERSATION_SERVICE is None:
        raise RuntimeError("chat_not_explicitly_configured")
    return _CONVERSATION_SERVICE


def _storage_roots_overlap(left: Path, right: Path) -> bool:
    """Keep user-retained memory outside transcript and installation custody."""
    first = Path(left).expanduser().resolve()
    second = Path(right).expanduser().resolve()
    try:
        first.relative_to(second)
        return True
    except ValueError:
        try:
            second.relative_to(first)
            return True
        except ValueError:
            return False


def configure_production_chat(*, installation_identity: str, serving_operation_id: str,
                              expected_activation_state_digest: str | None = None,
                              control_plane_kernel: ControlPlaneKernel | None = None,
                              foreground_game_detector: BridgeForegroundGameDetector | None = None,
                              renderer_report_capture_owner: RendererReportCaptureOwner | None = None,
                              resource_context_owner: ProductionChatResourceContextOwner | None = None,
                              resource_provisioning_id: str | None = None,
                              runtime_handoff_id: str | None = None,
                              avatar_state_path: Path | None = None,
                              avatar_output_session: Any | None = None,
                              gaming_companion_runtime: Any | None = None,
                              local_speech_output: bool = False,
                              screen_observer: Callable[[], Mapping[str, object] | None] | None = None) -> None:
    """Establish exactly one explicit hardened production serving lifetime."""
    global _CONVERSATION_SERVICE, _PRODUCTION_COMPOSITION
    avatar_output_owner = None
    core_runtime_owns_foreground_detector = False
    if gaming_companion_runtime is not None:
        from .gaming_companion_core_runtime import WSLCoreGamingCompanionRuntime

        if type(gaming_companion_runtime) is not WSLCoreGamingCompanionRuntime:
            raise TypeError("exact_wsl_core_gaming_companion_runtime_required")
        if foreground_game_detector is not None or avatar_output_session is not None:
            raise ValueError("gaming_companion_runtime_components_are_owned")
        if gaming_companion_runtime.status().get("state") != "running":
            raise ValueError("wsl_core_gaming_companion_runtime_must_be_started")
        foreground_game_detector = gaming_companion_runtime.foreground_game_detector
        avatar_output_session = gaming_companion_runtime.avatar_output_session
        avatar_output_owner = gaming_companion_runtime
        core_runtime_owns_foreground_detector = True
    elif avatar_output_session is not None:
        avatar_output_owner = avatar_output_session
    if (foreground_game_detector is not None
            and type(foreground_game_detector) is not BridgeForegroundGameDetector):
        raise TypeError("exact_bridge_foreground_game_detector_required")
    if (renderer_report_capture_owner is not None
            and type(renderer_report_capture_owner) is not RendererReportCaptureOwner):
        raise TypeError("exact_renderer_report_capture_owner_required")
    if screen_observer is not None and not callable(screen_observer):
        raise TypeError("callable_screen_observer_required")
    if resource_context_owner is not None and type(resource_context_owner) is not ProductionChatResourceContextOwner:
        raise TypeError("exact_production_chat_resource_context_owner_required")
    if resource_context_owner is not None and not resource_context_owner.has_single_process_custody:
        raise ValueError("resource_ledger_single_process_custody_required")
    if resource_context_owner is not None and resource_provisioning_id is not None:
        raise ValueError("resource_owner_and_provisioning_id_mutually_exclusive")
    avatar_output_emitter = None
    if avatar_output_session is not None:
        from .gaming_companion_core_runtime import WSLCoreAvatarOutputSession

        if type(avatar_output_session) is not WSLCoreAvatarOutputSession:
            raise TypeError("exact_wsl_core_avatar_output_session_required")
        if avatar_state_path is not None:
            raise ValueError("avatar_output_session_and_state_path_mutually_exclusive")
        avatar_output_emitter = avatar_output_session.emitter
    identity = InstallationIdentity.parse(installation_identity)
    if runtime_handoff_id is None:
        raise RuntimeError("chat_process_generation_handoff_required")
    try:
        handle, _runtime_handoff = open_chat_process_handoff(
            installation_identity=identity.value, handoff_id=runtime_handoff_id)
        configured_operation = _runtime_handoff.get("configured_serving_operation_id")
        if (configured_operation is not None
                and configured_operation != serving_operation_id):
            raise RuntimeError("chat_process_serving_operation_handoff_mismatch")
    except Exception as exc:
        raise RuntimeError("chat_process_generation_handoff_invalid") from exc
    if resource_provisioning_id is not None:
        from .production_chat_resource_provisioning import load_production_chat_resource_context_owner
        resource_context_owner = load_production_chat_resource_context_owner(handle, resource_provisioning_id)
    serving: ProductionServingController | None = None
    speech_output: ChatSpeechOutput | None = None
    try:
        data_root = sentientos_data_dir()
        memory_root = sentientos_memory_dir(data_root)
        conversation_root = handle.fixed_object("chat/conversations")
        if (_storage_roots_overlap(memory_root, handle.root)
                or _storage_roots_overlap(memory_root, conversation_root.path)):
            raise ValueError("user_memory_root_overlaps_installation_transcript_custody")
        serving = ProductionServingController(handle, control_plane_kernel or ControlPlaneKernel())
        establish_arguments = {"operation_id": serving_operation_id}
        if expected_activation_state_digest is not None:
            establish_arguments["expected_activation_state_digest"] = expected_activation_state_digest
        serving.establish(**establish_arguments)
        inference_bridge = ProductionServingInferenceController(
            serving, runtime_handoff_id=runtime_handoff_id,
            foreground_game_detector=foreground_game_detector)
        inference: ChatInference = (
            inference_bridge if resource_context_owner is None
            else ResourceBackedProductionChatInference(inference_bridge, resource_context_owner)
        )
        avatar_output = None
        if avatar_output_emitter is not None:
            from control_plane import admit_request
            from .chat_avatar_output import ChatAvatarOutputController

            avatar_output = ChatAvatarOutputController(avatar_output_emitter,
                admission_provider=admit_request)
        elif avatar_state_path is not None:
            from control_plane import admit_request
            from avatar_state import AvatarStateEmitter
            from speech_emitter import SpeechEmitter
            from .chat_avatar_output import ChatAvatarOutputController

            avatar_output = ChatAvatarOutputController(
                SpeechEmitter(AvatarStateEmitter(avatar_state_path)),
                admission_provider=admit_request)
        if local_speech_output:
            from control_plane import admit_request
            from .chat_speech_output import ChatSpeechOutputController

            timing_sink = (getattr(avatar_output, "publish_speech_timing", None)
                           if avatar_output is not None else None)
            speech_output = ChatSpeechOutputController(
                admission_provider=admit_request,
                timing_event_sink=timing_sink if callable(timing_sink) else None)
        # The roots were checked before serving was established.  Transcript
        # custody remains installation-scoped; canonical memory remains user-scoped.
        handle.ensure_directory(conversation_root)
        service = PersistentConversationService(inference=inference,
            session_store=ConversationSessionStore(conversation_root.path),
            memory_store=CanonicalMemoryStore(memory_root), avatar_output=avatar_output,
            speech_output=speech_output, screen_observer=screen_observer)
        if renderer_report_capture_owner is not None:
            renderer_report_capture_owner.start()
    except Exception:
        try:
            if serving is not None:
                serving.close()
        finally:
            try:
                if speech_output is not None:
                    speech_output.close()
            finally:
                try:
                    if resource_context_owner is not None:
                        resource_context_owner.close()
                finally:
                    try:
                        if (foreground_game_detector is not None
                                and not core_runtime_owns_foreground_detector):
                            foreground_game_detector.close()
                    finally:
                        try:
                            if renderer_report_capture_owner is not None:
                                renderer_report_capture_owner.close()
                        finally:
                            if avatar_output_owner is not None:
                                avatar_output_owner.close()
        raise
    assert serving is not None
    close_production_chat()
    _CONVERSATION_SERVICE = service
    _PRODUCTION_COMPOSITION = ProductionChatComposition(service, serving, resource_context_owner,
                                                       (None if core_runtime_owns_foreground_detector
                                                        else foreground_game_detector),
                                                       renderer_report_capture_owner,
                                                       avatar_output_owner)


def configure_development_chat(*, invoker: GovernedLocalModelInvoker,
                               data_root: Path | None = None,
                               avatar_output_emitter: Any | None = None,
                               model_profiles: Mapping[str, Any] | None = None,
                               initial_workload_mode: str = "normal",
                               foreground_game_detector: Any | None = None,
                               game_process_names: tuple[str, ...] | list[str] = ()) -> None:
    """Explicitly install governed local development chat inference."""
    global _CONVERSATION_SERVICE, _PRODUCTION_COMPOSITION
    root = data_root or sentientos_data_dir()
    # data_root selects development transcript custody only; user memory stays
    # on the one process-wide root shared with the authorized legacy manager.
    memory_root = sentientos_memory_dir()
    conversation_root = root / "conversations"
    if _storage_roots_overlap(memory_root, conversation_root):
        raise ValueError("user_memory_root_overlaps_transcript_custody")
    avatar_output = None
    if avatar_output_emitter is not None:
        from control_plane import admit_request
        from .chat_avatar_output import ChatAvatarOutputController
        avatar_output = ChatAvatarOutputController(
            avatar_output_emitter, admission_provider=admit_request)
    close_production_chat()
    inference = DevelopmentLocalChatInference(
        invoker, model_profiles, foreground_game_detector=foreground_game_detector)
    if initial_workload_mode != "normal":
        inference.set_workload_mode(initial_workload_mode, game_process_names)
    _CONVERSATION_SERVICE = PersistentConversationService(
        inference=inference,
        session_store=ConversationSessionStore(conversation_root),
        memory_store=CanonicalMemoryStore(memory_root),
        avatar_output=avatar_output)
    _PRODUCTION_COMPOSITION = None


def close_production_chat() -> None:
    global _CONVERSATION_SERVICE, _PRODUCTION_COMPOSITION
    composition = _PRODUCTION_COMPOSITION
    service = _CONVERSATION_SERVICE
    _PRODUCTION_COMPOSITION = None
    _CONVERSATION_SERVICE = None
    if composition is not None:
        composition.close()
    elif service is not None:
        service.close_outputs()


def production_chat_ready() -> bool:
    """Return coarse read-only readiness; never establish or invoke a model."""
    composition = _PRODUCTION_COMPOSITION
    return composition is not None and composition.ready()


class BootEvent(BaseModel):
    timestamp: str
    message: str
    level: str


@APP.on_event("startup")
async def _startup_event() -> None:
    LOGGER.info("Chat interface ready")


@APP.on_event("shutdown")
async def _shutdown_event() -> None:
    close_production_chat()


@APP.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message must not be empty")
    if _CHANGE_NARRATOR is not None:
        summary = _CHANGE_NARRATOR.maybe_respond(message)
        if summary is not None:
            # Narrator responses are not model conversation turns.
            raise HTTPException(status_code=409, detail=summary)
    try:
        return _get_conversation_service().chat(message, session_id=request.session_id,
            retain=request.retain, request_id=request.request_id,
            observe_screen=request.observe_screen)
    except ChatRequestStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LocalModelPostEffectCustodyError as exc:
        LOGGER.error("Post-effect custody is unconfirmed for invocation %s at %s",
            exc.receipt_id, exc.failure_phase)
        raise HTTPException(status_code=503, detail={
            "code": "post_effect_custody_unconfirmed",
            "failure_phase": exc.failure_phase,
            "invocation_receipt_id": exc.receipt_id,
            "invocation_receipt_digest": exc.receipt_digest,
            "invocation_status": exc.invocation_status,
            "receipt_persistence_confirmed": exc.receipt_persistence_confirmed,
            "resource_linkage_persistence_confirmed":
                exc.resource_linkage_persistence_confirmed,
            "replay_posture": "do_not_retry_automatically",
        }) from exc
    except RuntimeError as exc:
        LOGGER.warning("Production chat unavailable: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Local model inference unavailable") from exc


@APP.get("/readyz")
async def readiness_endpoint() -> dict[str, str]:
    """Expose no serving identity: only coarse current/unavailable state."""
    if not production_chat_ready():
        raise HTTPException(status_code=503, detail="unavailable")
    return {"status": "ready"}


@APP.get("/screen-observation")
async def screen_observation_status_endpoint() -> dict[str, bool]:
    """Expose only whether a per-request screen observer was explicitly configured."""
    return {
        "configured": _get_conversation_service().screen_observation_configured(),
        "per_message_opt_in_required": True,
    }


@APP.get("/workload-mode")
async def workload_mode_endpoint() -> dict[str, Any]:
    try:
        return _get_conversation_service().current_workload_state()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Chat workload mode unavailable") from exc


@APP.post("/workload-mode")
async def set_workload_mode_endpoint(request: ChatWorkloadModeRequest) -> dict[str, Any]:
    try:
        mode = _get_conversation_service().set_workload_mode(
            request.mode, request.game_process_names)
        return _get_conversation_service().current_workload_state() | {"mode": mode}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Chat workload mode unavailable") from exc


@APP.get("/avatar-output")
async def avatar_output_state_endpoint(session_id: str | None = None) -> dict[str, Any]:
    try:
        return _get_conversation_service().avatar_output_state(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Chat session not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Avatar output state unavailable") from exc


@APP.post("/avatar-output")
async def set_avatar_output_endpoint(request: ChatAvatarOutputRequest) -> dict[str, Any]:
    try:
        return _get_conversation_service().set_avatar_output_enabled(
            request.session_id, request.enabled)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Chat session not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        LOGGER.warning("Avatar output control unavailable: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Avatar output unavailable") from exc


@APP.get("/speech-output")
async def speech_output_state_endpoint(session_id: str | None = None) -> dict[str, Any]:
    try:
        return _get_conversation_service().speech_output_state(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Chat session not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Speech output status unavailable") from exc


@APP.post("/speech-output")
async def set_speech_output_endpoint(request: ChatSpeechOutputRequest) -> dict[str, Any]:
    try:
        return _get_conversation_service().set_speech_output_enabled(
            request.session_id, request.enabled)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Chat session not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Speech output unavailable") from exc


@APP.post("/sessions")
async def create_session() -> dict[str, str]:
    try:
        return {"session_id": _get_conversation_service().create_session()}
    except RuntimeError as exc:
        LOGGER.warning("Unable to create chat session: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Local model session unavailable") from exc


@APP.get("/sessions")
async def list_sessions() -> list[dict[str, Any]]:
    try:
        return _get_conversation_service().sessions.list_recent()
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503,
            detail="conversation_session_listing_unavailable_or_degraded") from exc


@APP.get("/sessions/{session_id}/turns")
async def inspect_session_turns(session_id: str, request: Request) -> dict[str, Any]:
    """Return the bounded, display-safe transcript for one local chat session."""
    client_host = getattr(getattr(request, "client", None), "host", None)
    try:
        local_client = isinstance(client_host, str) and ipaddress.ip_address(client_host).is_loopback
    except ValueError:
        local_client = False
    if not local_client:
        raise HTTPException(status_code=403,
            detail="conversation_transcript_local_access_required")
    try:
        session = _get_conversation_service().sessions.load(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="conversation_session_not_found") from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503,
            detail="conversation_session_unavailable_or_invalid") from exc
    turns = session["turns"]
    visible_turns = turns[-100:]
    return {
        "session_id": session_id,
        "total_turns": len(turns),
        "truncated": len(visible_turns) < len(turns),
        "turns": [{key: turn[key] for key in ("turn_id", "sequence", "role", "timestamp", "text")}
                  for turn in visible_turns],
    }


@APP.get("/sessions/{session_id}")
async def inspect_session(session_id: str) -> dict[str, Any]:
    try:
        session = _get_conversation_service().sessions.load(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="conversation_session_not_found") from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503,
            detail="conversation_session_unavailable_or_invalid") from exc
    return {**{k: session[k] for k in ("session_id", "created_at", "latest_activity_at",
        "title", "revision", "lifecycle_state", "model_identity_digest")},
        "model_identity_scope": "session_creation_snapshot_only"}


@APP.get("/boot-feed", response_model=List[BootEvent])
async def boot_feed() -> List[BootEvent]:
    return [BootEvent(**event) for event in boot_history()]


@APP.get("/", response_class=HTMLResponse)
async def root_page() -> HTMLResponse:
    return HTMLResponse(
        """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="utf-8" />
            <title>SentientOS Chat</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 0; padding: 2rem; background: #111; color: #f5f5f5; }
                #chat { max-width: 640px; margin: 0 auto; }
                #conversation { max-height: 48vh; overflow-y: auto; margin: 1rem 0; }
                .turn { margin: 0.75rem 0; padding: 0.8rem 1rem; border-radius: 8px; white-space: pre-wrap; overflow-wrap: anywhere; }
                .turn[data-role="user"] { background: #183047; }
                .turn[data-role="assistant"] { background: #1e1e1e; }
                .turn-label { display: block; margin-bottom: 0.35rem; color: #aaa; font-size: 0.85rem; }
                #conversation-status { color: #aaa; }
                #boot-ceremony { margin-bottom: 2rem; padding: 1rem; background: #1b1b1b; border-radius: 8px; }
                #boot-ceremony h2 { margin-top: 0; }
                .boot-entry { margin: 0.5rem 0; padding: 0.5rem; border-left: 4px solid #444; background: #0f0f0f; border-radius: 4px; }
                .boot-entry[data-level="warning"] { border-color: #f0a202; }
                .boot-entry[data-level="error"] { border-color: #f2545b; }
                #workload-controls { margin: 1rem 0; padding: 0.75rem; background: #1b1b1b; border-radius: 8px; }
                #workload-mode, #game-process-names { width: auto; min-height: 0; margin: 0.25rem; padding: 0.4rem; }
                #workload-status { margin-left: 0.5rem; color: #aaa; }
                #avatar-output-controls { margin: 1rem 0; padding: 0.75rem; background: #1b1b1b; border-radius: 8px; }
                #avatar-output-status { margin-left: 0.5rem; color: #aaa; }
                #screen-observation-controls { margin: 0.75rem 0; }
                #screen-observation-status { display: block; color: #aaa; }
                textarea { width: 100%; min-height: 120px; padding: 0.75rem; font-size: 1rem; }
                button { margin-top: 1rem; padding: 0.75rem 1.5rem; font-size: 1rem; cursor: pointer; }
                .response { margin-top: 2rem; padding: 1rem; background: #1e1e1e; border-radius: 8px; }
            </style>
        </head>
        <body>
            <div id="chat">
                <section id="boot-ceremony">
                    <h2>Boot Ceremony</h2>
                    <div id="boot-feed"></div>
                </section>
                <h1>SentientOS Local Chat</h1>
                <p>Start a local conversation with the SentientOS daemon. All interactions remain on your machine.</p>
                <section id="workload-controls" aria-label="Workload mode">
                    <label for="workload-mode">Workload mode</label>
                    <select id="workload-mode">
                        <option value="normal">Normal</option>
                        <option value="gaming">Gaming</option>
                        <option value="automatic">Automatic by foreground game</option>
                    </select>
                    <label for="game-process-names">Watched game executables</label>
                    <input id="game-process-names" type="text" placeholder="ExampleGame.exe, AnotherGame.exe" />
                    <span id="workload-status" role="status"></span>
                </section>
                <section id="avatar-output-controls" aria-label="Avatar response display">
                    <label for="avatar-output-enabled">Show replies in companion</label>
                    <input id="avatar-output-enabled" type="checkbox" disabled />
                    <span id="avatar-output-status" role="status">Visual text and a nod only; no audio.</span>
                    <p>Approval is limited to this conversation and expires after four hours or when the chat service stops.</p>
                    <p>When enabled, gaming mode caps only the companion renderer at 15 FPS; it does not change game scheduling.</p>
                </section>
                <section id="speech-output-controls" aria-label="Local speech output">
                    <label for="speech-output-enabled">Speak replies with local voice</label>
                    <input id="speech-output-enabled" type="checkbox" disabled />
                    <span id="speech-output-status" role="status">Off; local system voice only, no cloud TTS.</span>
                </section>
                <textarea id="message" placeholder="Type your message..."></textarea>
                <section id="conversation" aria-label="Conversation transcript" aria-live="polite">
                    <p id="conversation-status">Your conversation will appear here.</p>
                </section>
                <section id="screen-observation-controls" aria-label="Screen observation">
                    <label for="observe-screen"><input id="observe-screen" type="checkbox" />
                        Include the current consented game screen in this message</label>
                    <span id="screen-observation-status" role="status">OCR stays local and is not saved. Requires a configured consented screen source.</span>
                </section>
                <button id="send">Send</button>
                <div id="response" class="response" hidden>
                    <strong>Response:</strong>
                    <p id="response-text"></p>
                </div>
            </div>
            <script>
                async function refreshBootFeed() {
                    try {
                        const res = await fetch('/boot-feed');
                        if (!res.ok) {
                            return;
                        }
                        const data = await res.json();
                        const container = document.getElementById('boot-feed');
                        container.innerHTML = '';
                        data.forEach((event) => {
                            const entry = document.createElement('div');
                            entry.className = 'boot-entry';
                            entry.dataset.level = event.level;
                            const timestamp = new Date(event.timestamp).toLocaleTimeString();
                            entry.innerHTML = `<strong>[${timestamp}]</strong> ${event.message}`;
                            container.appendChild(entry);
                        });
                    } catch (err) {
                        console.warn('Unable to refresh boot feed', err);
                    }
                }

                let chatSendInFlight = false;
                async function sendMessage() {
                    if (chatSendInFlight) return;
                    const sendButton = document.getElementById('send');
                    chatSendInFlight = true;
                    sendButton.disabled = true;
                    sendButton.textContent = 'Sending...';
                    try {
                        const messageEl = document.getElementById('message');
                        const responseEl = document.getElementById('response');
                        const responseTextEl = document.getElementById('response-text');
                        const message = messageEl.value.trim();
                        const observeScreen = document.getElementById('observe-screen').checked;
                        if (!message) { alert('Please enter a message before sending.'); return; }
                        let sessionId = localStorage.getItem('sentientos_session_id');
                        if (!sessionId) {
                            const created = await fetch('/sessions', { method: 'POST' });
                            if (!created.ok) { alert('Unable to create a conversation session.'); return; }
                            sessionId = (await created.json()).session_id;
                            localStorage.setItem('sentientos_session_id', sessionId);
                        }
                        const messageDigestBytes = await crypto.subtle.digest(
                            'SHA-256', new TextEncoder().encode(message));
                        const messageDigest = Array.from(new Uint8Array(messageDigestBytes))
                            .map(value => value.toString(16).padStart(2, '0')).join('');
                        const pendingKey = 'sentientos_pending_chat:' + sessionId + ':' + messageDigest
                            + ':' + (observeScreen ? 'screen' : 'text');
                        let pending = null;
                        try { pending = JSON.parse(localStorage.getItem(pendingKey) || 'null'); }
                        catch (_) { pending = null; }
                        const requestId = pending && typeof pending.request_id === 'string'
                            ? pending.request_id : crypto.randomUUID();
                        localStorage.setItem(pendingKey, JSON.stringify({ request_id: requestId }));
                        const res = await fetch('/chat', {
                            method: 'POST', headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ message, session_id: sessionId, request_id: requestId,
                                observe_screen: observeScreen }),
                        });
                        if (!res.ok) {
                            const detail = await res.json().catch(() => ({ detail: 'Unknown error' }));
                            alert(detail.detail || 'Unable to reach SentientOS chat. The same request identity will be reused if retried.');
                            return;
                        }
                        const data = await res.json();
                        localStorage.setItem('sentientos_session_id', data.session_id);
                        localStorage.removeItem(pendingKey);
                        responseTextEl.textContent = data.response;
                        responseEl.hidden = false;
                        await refreshConversationTranscript();
                        refreshAvatarOutput();
                    } catch (err) {
                        alert('Unable to send this message. The same request identity will be reused if retried.');
                        console.error('Unable to send SentientOS chat message', err);
                    } finally {
                        chatSendInFlight = false;
                        sendButton.disabled = false;
                        sendButton.textContent = 'Send';
                    }
                }
                async function refreshScreenObservationStatus() {
                    const control = document.getElementById('observe-screen');
                    const status = document.getElementById('screen-observation-status');
                    try {
                        const response = await fetch('/screen-observation');
                        if (!response.ok) throw new Error('unavailable');
                        const data = await response.json();
                        control.disabled = data.configured !== true;
                        status.textContent = data.configured === true
                            ? 'Configured for this server. OCR stays local and is not saved; each message still requires this checkbox.'
                            : 'Not configured. The server needs an explicit local process allowlist and consented screen source.';
                    } catch (_) {
                        control.checked = false;
                        control.disabled = true;
                        status.textContent = 'Screen observation status unavailable';
                    }
                }
                async function ensureConversationSession() {
                    let sessionId = localStorage.getItem('sentientos_session_id');
                    if (sessionId) return sessionId;
                    const created = await fetch('/sessions', { method: 'POST' });
                    if (!created.ok) throw new Error('session_unavailable');
                    sessionId = (await created.json()).session_id;
                    localStorage.setItem('sentientos_session_id', sessionId);
                    return sessionId;
                }
                async function refreshConversationTranscript() {
                    const container = document.getElementById('conversation');
                    const sessionId = localStorage.getItem('sentientos_session_id');
                    if (!sessionId) return;
                    try {
                        const response = await fetch('/sessions/' + encodeURIComponent(sessionId) + '/turns');
                        if (!response.ok) throw new Error('transcript_unavailable');
                        const data = await response.json();
                        container.replaceChildren();
                        if (data.truncated) {
                            const notice = document.createElement('p');
                            notice.id = 'conversation-status';
                            notice.textContent = 'Showing the latest ' + data.turns.length
                                + ' of ' + data.total_turns + ' turns.';
                            container.appendChild(notice);
                        }
                        if (!data.turns.length) {
                            const empty = document.createElement('p');
                            empty.id = 'conversation-status';
                            empty.textContent = 'Start a message to begin this conversation.';
                            container.appendChild(empty);
                        }
                        data.turns.forEach((turn) => {
                            const entry = document.createElement('article');
                            entry.className = 'turn';
                            entry.dataset.role = turn.role;
                            const label = document.createElement('strong');
                            label.className = 'turn-label';
                            label.textContent = turn.role === 'user' ? 'You' : 'SentientOS';
                            const content = document.createElement('div');
                            content.textContent = turn.text;
                            entry.append(label, content);
                            container.appendChild(entry);
                        });
                        container.scrollTop = container.scrollHeight;
                    } catch (_) {
                        container.replaceChildren();
                        const unavailable = document.createElement('p');
                        unavailable.id = 'conversation-status';
                        unavailable.textContent = 'Saved conversation transcript is unavailable.';
                        container.appendChild(unavailable);
                    }
                }
                async function refreshAvatarOutput(preserveStatus = false) {
                    const control = document.getElementById('avatar-output-enabled');
                    const status = document.getElementById('avatar-output-status');
                    const sessionId = localStorage.getItem('sentientos_session_id');
                    try {
                        const query = sessionId ? '?session_id=' + encodeURIComponent(sessionId) : '';
                        const response = await fetch('/avatar-output' + query);
                        if (!response.ok) throw new Error('unavailable');
                        const data = await response.json();
                        control.disabled = data.configured !== true;
                        control.checked = data.enabled === true;
                        if (!preserveStatus) {
                            status.textContent = data.configured
                                ? (data.enabled ? 'Visual-only approval active for this conversation.'
                                    : (data.clear_pending ? 'Off; the previous display could not be cleared.' : 'Off'))
                                : 'Avatar state path is not configured.';
                        }
                    } catch (_) {
                        control.disabled = true;
                        status.textContent = 'Avatar output status unavailable';
                    }
                }
                async function changeAvatarOutput() {
                    const control = document.getElementById('avatar-output-enabled');
                    const status = document.getElementById('avatar-output-status');
                    control.disabled = true;
                    try {
                        const sessionId = await ensureConversationSession();
                        const response = await fetch('/avatar-output', {
                            method: 'POST', headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ session_id: sessionId, enabled: control.checked }),
                        });
                        if (!response.ok) throw new Error('unavailable');
                        const data = await response.json();
                        control.checked = data.enabled === true;
                        status.textContent = data.enabled
                            ? 'Visual-only approval active for this conversation.'
                            : (data.reason ? 'Approval denied: ' + data.reason
                                : (data.state_cleared === false ? 'Off; avatar state could not be cleared.' : 'Off'));
                    } catch (_) {
                        control.checked = false;
                        status.textContent = 'Unable to update avatar output';
                    } finally {
                        await refreshAvatarOutput(true);
                    }
                }
                async function refreshSpeechOutput(preserveStatus = false) {
                    const control = document.getElementById('speech-output-enabled');
                    const status = document.getElementById('speech-output-status');
                    const sessionId = localStorage.getItem('sentientos_session_id');
                    try {
                        const query = sessionId ? '?session_id=' + encodeURIComponent(sessionId) : '';
                        const response = await fetch('/speech-output' + query);
                        if (!response.ok) throw new Error('unavailable');
                        const data = await response.json();
                        control.disabled = data.configured !== true || data.backend_available !== true;
                        control.checked = data.enabled === true;
                        if (!preserveStatus) {
                            status.textContent = data.configured !== true
                                ? 'Local speech is not enabled for this server.'
                                : (data.backend_available !== true
                                    ? 'Local pyttsx3 voice backend is unavailable.'
                                    : (data.enabled
                                        ? 'Approved for this conversation; playback: ' + data.playback_status + '.'
                                        : 'Off; local system voice only, no cloud TTS.'));
                        }
                    } catch (_) {
                        control.disabled = true;
                        status.textContent = 'Local speech status unavailable';
                    }
                }
                async function changeSpeechOutput() {
                    const control = document.getElementById('speech-output-enabled');
                    const status = document.getElementById('speech-output-status');
                    control.disabled = true;
                    try {
                        const sessionId = await ensureConversationSession();
                        const response = await fetch('/speech-output', {
                            method: 'POST', headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ session_id: sessionId, enabled: control.checked }),
                        });
                        if (!response.ok) throw new Error('unavailable');
                        const data = await response.json();
                        control.checked = data.enabled === true;
                        status.textContent = data.enabled
                            ? 'Local speech approved for this conversation.'
                            : (data.reason || 'Local speech off.');
                    } catch (_) {
                        control.checked = false;
                        status.textContent = 'Unable to update local speech output';
                    } finally {
                        await refreshSpeechOutput(true);
                    }
                }
                async function refreshWorkloadMode() {
                    const control = document.getElementById('workload-mode');
                    const names = document.getElementById('game-process-names');
                    const status = document.getElementById('workload-status');
                    control.disabled = true;
                    names.disabled = true;
                    try {
                        const response = await fetch('/workload-mode');
                        if (!response.ok) throw new Error('unavailable');
                        let data = await response.json();
                        const preference = readWorkloadPreference();
                        if (preference) {
                            names.value = preference.game_process_names.join(', ');
                            const restored = await fetch('/workload-mode', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify(preference),
                            });
                            if (restored.ok) data = await restored.json();
                            else status.textContent = 'Saved workload preference could not be restored';
                        }
                        control.value = data.mode;
                        if (!preference || data.mode === preference.mode) {
                            status.textContent = workloadStatusMessage(data);
                        }
                    } catch (_) {
                        control.disabled = true;
                        names.disabled = true;
                        status.textContent = 'Unavailable';
                    } finally {
                        const unavailable = status.textContent === 'Unavailable';
                        control.disabled = unavailable;
                        names.disabled = unavailable;
                    }
                }
                const workloadPreferenceKey = 'sentientos_workload_preference_v1';
                function readWorkloadPreference() {
                    try {
                        const value = JSON.parse(localStorage.getItem(workloadPreferenceKey) || 'null');
                        if (!value || !['normal', 'gaming', 'automatic'].includes(value.mode)
                                || !Array.isArray(value.game_process_names)
                                || value.game_process_names.length > 32
                                || value.game_process_names.some(name => typeof name !== 'string')) return null;
                        return { mode: value.mode, game_process_names: value.game_process_names };
                    } catch (_) { return null; }
                }
                function saveWorkloadPreference(mode, gameProcessNames) {
                    try {
                        localStorage.setItem(workloadPreferenceKey, JSON.stringify({
                            mode, game_process_names: gameProcessNames,
                        }));
                        return true;
                    } catch (_) { return false; }
                }
                function workloadStatusMessage(data) {
                    return data.mode === 'automatic'
                        ? (data.observation_status === 'available'
                            ? (data.effective_mode === 'gaming'
                                ? 'Game detected; low-work mode active'
                                : 'No watched game in foreground')
                            : 'Detection unavailable; low-work mode active')
                        : (data.mode === 'gaming' ? 'Low-work mode active' : 'Normal mode');
                }
                async function refreshWorkloadStatus() {
                    const control = document.getElementById('workload-mode');
                    if (control.disabled) return;
                    const names = document.getElementById('game-process-names');
                    const status = document.getElementById('workload-status');
                    try {
                        const response = await fetch('/workload-mode');
                        if (!response.ok) throw new Error('unavailable');
                        let data = await response.json();
                        if (control.value !== data.mode) {
                            const preference = readWorkloadPreference();
                            if (preference && preference.mode === control.value) {
                                const restored = await fetch('/workload-mode', {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify(preference),
                                });
                                if (restored.ok) data = await restored.json();
                            }
                        }
                        if (control.value !== data.mode) {
                            control.value = data.mode;
                            const preference = readWorkloadPreference();
                            if (preference && preference.mode === data.mode) {
                                names.value = preference.game_process_names.join(', ');
                            }
                        }
                        status.textContent = workloadStatusMessage(data);
                    } catch (_) {
                        status.textContent = 'Workload status unavailable';
                    }
                }
                async function changeWorkloadMode() {
                    const control = document.getElementById('workload-mode');
                    const names = document.getElementById('game-process-names');
                    const status = document.getElementById('workload-status');
                    control.disabled = true;
                    names.disabled = true;
                    try {
                        const processNames = names.value.split(',').map(value => value.trim()).filter(Boolean);
                        const response = await fetch('/workload-mode', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ mode: control.value, game_process_names: processNames }),
                        });
                        if (!response.ok) throw new Error('unavailable');
                        const data = await response.json();
                        const saved = saveWorkloadPreference(
                            data.mode, data.mode === 'automatic' ? processNames : []);
                        status.textContent = workloadStatusMessage(data)
                            + (saved ? '' : '; not saved in this browser');
                    } catch (_) {
                        const message = control.value === 'automatic'
                            ? 'Add one or more executable names ending in .exe' : 'Unable to change mode';
                        await refreshWorkloadMode();
                        status.textContent = message;
                    } finally {
                        control.disabled = status.textContent === 'Unavailable';
                        names.disabled = status.textContent === 'Unavailable';
                    }
                }
                document.getElementById('send').addEventListener('click', sendMessage);
                document.getElementById('avatar-output-enabled').addEventListener('change', changeAvatarOutput);
                document.getElementById('speech-output-enabled').addEventListener('change', changeSpeechOutput);
                document.getElementById('workload-mode').addEventListener('change', changeWorkloadMode);
                document.getElementById('game-process-names').addEventListener('change', () => {
                    if (document.getElementById('workload-mode').value === 'automatic') changeWorkloadMode();
                });
                document.getElementById('message').addEventListener('keydown', (event) => {
                    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
                        event.preventDefault();
                        sendMessage();
                    }
                });
                refreshBootFeed();
                refreshConversationTranscript();
                refreshWorkloadMode();
                refreshAvatarOutput();
                refreshSpeechOutput();
                refreshScreenObservationStatus();
                setInterval(refreshBootFeed, 5000);
                setInterval(refreshWorkloadStatus, 5000);
                setInterval(refreshAvatarOutput, 5000);
                setInterval(refreshSpeechOutput, 5000);
            </script>
        </body>
        </html>
        """
    )


def _build_cli_screen_observer(process_names: list[str], consent_minutes: int, *,
                               platform_name: str | None = None,
                               now: datetime | None = None) -> Callable[[], Mapping[str, object] | None] | None:
    """Build a one-process-lifetime screen owner only after explicit CLI opt-in."""
    if not process_names:
        return None
    if (platform_name or os.name) != "nt":
        raise ValueError("screen_observation_requires_windows_desktop_session")
    if (type(consent_minutes) is not int or not 1 <= consent_minutes <= 240):
        raise ValueError("screen_observation_consent_minutes_out_of_range")
    try:
        allowed_process_names = normalize_game_process_names(process_names)
    except ValueError as exc:
        raise ValueError("screen_observation_process_allowlist_invalid") from exc
    consent_start = now or datetime.now(timezone.utc)
    if consent_start.tzinfo is None or consent_start.utcoffset() is None:
        raise ValueError("screen_observation_consent_clock_invalid")
    expires_at = (consent_start.astimezone(timezone.utc)
        + timedelta(minutes=consent_minutes)).isoformat().replace("+00:00", "Z")
    from .perception.game_screen_capture import (
        GameScreenCaptureConsent, build_windows_game_screen_ocr,
    )
    from .perception.screen_ocr import ScreenConfig

    consent = GameScreenCaptureConsent(
        consent_id="chat-screen-" + uuid.uuid4().hex,
        allowed_process_names=allowed_process_names,
        expires_at=expires_at,
    )
    owner = build_windows_game_screen_ocr(
        config=ScreenConfig(enable=True, interval_s=2.0, ocr_backend="tesseract"),
        consent_provider=lambda: consent,
    )
    return owner.snapshot


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run explicitly composed local production chat.")
    parser.add_argument("--installation-identity", required=True)
    parser.add_argument("--serving-operation-id", required=True)
    parser.add_argument("--expected-activation-state-digest")
    parser.add_argument("--resource-provisioning-id")
    parser.add_argument("--runtime-handoff-id", required=True)
    parser.add_argument("--expected-software-generation-digest", required=True)
    parser.add_argument("--avatar-state-path", type=Path,
                        help="Opt in to a local visual-only avatar output state file")
    parser.add_argument("--local-speech-output", action="store_true",
                        help="Enable opt-in local pyttsx3 speech output for chat replies")
    parser.add_argument("--screen-observation-process", action="append", default=[],
                        metavar="GAME.exe",
                        help="Opt in to per-message local screen OCR for this allowlisted Windows game; repeat for multiple games")
    parser.add_argument("--screen-observation-consent-minutes", type=int, default=60,
                        help="Expire the launch-scoped screen consent after 1 to 240 minutes (default: 60)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args(argv)
    try:
        screen_observer = _build_cli_screen_observer(
            args.screen_observation_process, args.screen_observation_consent_minutes)
    except ValueError as exc:
        parser.error(str(exc))
    if screen_observer is not None and not _is_loopback_host(args.host):
        parser.error("screen_observation_requires_loopback_chat_host")

    # Supervised children share one installation-scoped lifetime lock. This prevents
    # a replacement daemon from treating a second child as a successor while an
    # orphaned predecessor may still be serving.
    try:
        handle, handoff = open_chat_process_handoff(
            installation_identity=args.installation_identity,
            handoff_id=args.runtime_handoff_id)
        if handoff.get("software_generation_digest") != args.expected_software_generation_digest:
            raise RuntimeError("chat_process_generation_expectation_mismatch")
        handoff_directory = handle.fixed_object("local-model/chat/runtime-handoffs")
        handle.ensure_directory(handoff_directory)
        process_lock = handle.fixed_object(
            "local-model/chat/runtime-handoffs/active-chat-process.lock")
        with handle.exclusive_lock(process_lock, blocking=False):
            configure_production_chat(installation_identity=args.installation_identity,
                serving_operation_id=args.serving_operation_id,
                expected_activation_state_digest=args.expected_activation_state_digest,
                resource_provisioning_id=args.resource_provisioning_id,
                runtime_handoff_id=args.runtime_handoff_id,
                avatar_state_path=args.avatar_state_path,
                local_speech_output=args.local_speech_output,
                screen_observer=screen_observer)
            run(host=args.host, port=args.port)
    except Exception as exc:
        raise RuntimeError("supervised_chat_process_lifetime_unavailable") from exc


def run(host: str = "0.0.0.0", port: int = 5000) -> None:
    if _CONVERSATION_SERVICE is None:
        raise RuntimeError("chat_not_explicitly_configured")
    if (_CONVERSATION_SERVICE.avatar_output_state(None).get("configured") is True
            and not _is_loopback_host(host)):
        raise RuntimeError("chat_avatar_output_requires_loopback_host")
    if (_CONVERSATION_SERVICE.speech_output_state(None).get("configured") is True
            and not _is_loopback_host(host)):
        raise RuntimeError("chat_speech_output_requires_loopback_host")
    if (_CONVERSATION_SERVICE.screen_observation_configured()
            and not _is_loopback_host(host)):
        raise RuntimeError("chat_screen_observation_requires_loopback_host")
    import uvicorn

    uvicorn.run(APP, host=host, port=port)


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False



