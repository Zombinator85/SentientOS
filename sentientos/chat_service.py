# mypy: disable-error-code=untyped-decorator
from __future__ import annotations

import argparse
import asyncio
import hashlib
import ipaddress
import json
import logging
import math
import os
import re
import queue
import threading
from contextlib import contextmanager
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable, List, Mapping, Protocol

from .fastapi_stub import FastAPI, HTMLResponse, HTTPException, Request, StreamingResponse

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
from .developmental_companion_bridge import (
    CognitionEvidenceUnavailable, CognitionWorkloadUnavailable,
    ResidentDevelopmentalCompanionBridge, make_operator_feedback_record,
)
from .conversation_session import (
    ConversationChatLockTimeout, ConversationSessionStore, assemble_local_chat_context,
    compact_runtime_generation_attribution, transcript_recall_terms,
)
from .canonical_memory import (AdmittedRetentionWriter, CanonicalMemoryStore, CANDIDATE_TYPE,
    ExplicitRetentionAdmissionGate, retention_request_id,
    sentientos_data_dir, sentientos_memory_dir)
from .local_model_authority import digest_payload
from .chat_response_grounding import (
    CURRENT_GAME_STATUS_POLICY_ID, SCREEN_CAPABILITY_POLICY_ID, corrected_gaming_output,
    USER_REPORT_EVIDENCE_POLICY_ID,
    corrected_nonverbal_gaming_output, corrected_multiple_social_questions,
    corrected_output_lineage,
    corrected_screen_capability_output, corrected_social_instruction_echo,
    corrected_system_identity_output, corrected_unobserved_game_status,
    corrected_nonresponsive_gaming_next_step,
    corrected_unprovided_source_reference,
    corrected_stale_screen_failure_claim,
    is_direct_screen_activity_question, is_direct_screen_configuration_status_question,
    is_verified_current_game_context_question, screen_observation_has_usable_content,
    visual_observation_unavailable_correction,
)
from .perception.screen_text_delta import validate_ocr_text_line_delta
from .screen_observation_bridge import ScreenObservationBridgeError

LOGGER = logging.getLogger(__name__)


def _is_earliest_session_recall_request(message: str) -> bool:
    """Whether a same-session recall explicitly targets its earliest user turn."""
    normalized = " ".join(message.casefold().split())
    markers = (
        "what did i ask you first", "what did i ask first",
        "the first thing i asked", "my first message", "my first question",
        "my first request", "my opening message", "my opening question",
        "at the beginning of this conversation", "at the beginning of this chat",
        "from the beginning of this conversation", "from the beginning of this chat",
        "earliest message", "earliest question", "earliest request",
        "initial message", "initial question", "initial request",
    )
    return any(marker in normalized for marker in markers)


_TRANSCRIPT_RECALL_CONTENT_TARGETS = (
    "note", "sign", "letter", "message", "label", "inscription",
    "document", "phrase", "quote", "text", "title", "objective",
)


def _direct_quoted_content_recall_target(message: str) -> str | None:
    """Return a content object for an explicit exact-quote recall request."""
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", message.casefold()).split())
    if not re.search(r"\b(?:what|which)\b", normalized): return None
    if not re.search(r"\b(?:exact|exactly|verbatim|word for word)\b", normalized): return None
    for target in _TRANSCRIPT_RECALL_CONTENT_TARGETS:
        if re.search(rf"\b{re.escape(target)}\b", normalized): return target
    return None


def _quoted_content_from_user_turn(text: str, target: str) -> str | None:
    """Find one unambiguous quoted value explicitly attached to a named object."""
    quote_patterns = (
        re.compile(r"(?P<open>[\"'])(?P<value>[^\"'\n]{1,500})(?P=open)"),
        re.compile(r"“(?P<value>[^”\n]{1,500})”"),
        re.compile(r"‘(?P<value>[^’\n]{1,500})’"),
    )
    content_verbs = re.compile(
        r"\b(?:reads?|says?|said|contains?|states?|stated|was written|is written)\b",
        flags=re.IGNORECASE,
    )
    matches: list[str] = []
    for pattern in quote_patterns:
        for quoted in pattern.finditer(text):
            value = quoted.group("value")
            if not value.strip():
                continue
            prefix = text[max(0, quoted.start() - 160):quoted.start()]
            target_position = prefix.casefold().rfind(target)
            if target_position < 0:
                continue
            relation_text = prefix[target_position + len(target):]
            relation = content_verbs.search(relation_text)
            if relation is None:
                continue
            before_verb = relation_text[:relation.start()]
            after_verb = relation_text[relation.end():]
            if re.search(r"[.!?]", before_verb + after_verb) is None:
                matches.append(value)
    unique = list(dict.fromkeys(matches))
    return unique[0] if len(unique) == 1 else None
def _find_verified_quoted_user_turn(history: Any, target: str) -> tuple[Mapping[str, Any], str] | None:
    """Find one exact quoted value in digest-verified user transcript turns."""
    matches: list[tuple[Mapping[str, Any], str]] = []
    for turn in reversed(history.turns):
        text = turn.get("text")
        text_digest = turn.get("text_digest")
        if (turn.get("role") != "user" or not isinstance(text, str) or not isinstance(text_digest, str)
                or text_digest != digest_payload({"text": text})): continue
        quoted_value = _quoted_content_from_user_turn(text, target)
        if quoted_value is not None: matches.append((turn, quoted_value))
    return matches[0] if len(matches) == 1 else None

def _is_recent_user_statement_reminder(message: str) -> bool:
    normalized = " ".join(message.casefold().split())
    return re.search(r"\bremind me what (?:i|you) (?:said|told)\b", normalized) is not None


def _is_recent_session_recall_request(message: str) -> bool:
    """Keep cross-session memories out of explicit recent-turn questions."""
    normalized = " ".join(message.casefold().split())
    markers = (
        "remind me what i said", "remind me what i told you",
        "remind me what you said", "remind me what you told me",
        "in this conversation", "in this chat", "earlier in this chat",
        "earlier in our chat", "earlier in our conversation",
        "in our earlier chat", "in our earlier conversation",
        "earlier in this conversation", "just before", "before you asked",
        "earlier i told you", "i told you earlier",
        "earlier i mentioned", "i mentioned earlier",
        "what did i just say", "what did i say", "what did i ask you", "what did i ask",
        "what did you just say", "what did you just tell me",
        "what did you just answer", "what did you just reply",
        "what exact phrase did i ask you to repeat",
        "what did i tell you", "what did you answer", "what did you say",
        "what was your answer", "what was your response", "what did you reply",
        "what was the thing you said", "what was the thing you told me",
        "what did i say i was", "what was i doing",
        "what was my last message", "what was my previous message",
    )
    prior_question_reference = _is_prior_assistant_question_recall(message)
    return (any(marker in normalized for marker in markers)
            or prior_question_reference
            or _direct_quoted_content_recall_target(message) is not None)


def _is_prior_assistant_question_recall(message: str) -> bool:
    """Recognize natural questions asking for an earlier assistant question."""
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", message.casefold()).split())
    asks_what_question = re.search(
        r"\bwhat (?:exactly )?(?:was|were) (?:your|the) question\b", normalized
    ) is not None or re.search(
        r"\bwhat question did you ask me\b", normalized
    ) is not None or re.search(
        r"\b(?:what|which) (?:topic|subject) did you ask(?: me)? about\b",
        normalized,
    ) is not None
    refers_to_prior = re.search(
        r"\b(?:earlier|before|previous|prior|last|at the beginning|in this chat|in this conversation)\b",
        normalized,
    ) is not None
    return asks_what_question and refers_to_prior

def _is_direct_recent_assistant_reply_request(message: str) -> bool:
    """Whether the user explicitly asks for the immediately prior assistant reply."""
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", message.casefold()).split())
    return any(marker in normalized for marker in (
        "what did you just say", "what did you just tell me",
        "what did you just answer", "what did you just reply",
    ))


def _prior_assistant_question_turn(history: Any, message: str) -> Mapping[str, Any] | None:
    """Select one verified earlier assistant question relevant to a recall request."""
    query_terms = transcript_recall_terms(message)
    ranked: list[tuple[int, Mapping[str, Any]]] = []
    for turn in history.turns:
        text = turn.get("text")
        if (turn.get("role") != "assistant" or not isinstance(text, str)
                or "?" not in text or turn.get("text_digest") != digest_payload({"text": text})):
            continue
        overlap = len(query_terms.intersection(transcript_recall_terms(text)))
        if overlap:
            ranked.append((overlap, turn))
    if not ranked:
        # A generic prior-question recall can have no lexical overlap with the
        # original question (for example, "what topic did you ask about in the
        # previous interface check?"). Use the latest verified assistant question
        # from the bounded same-session history in that case.
        return next((turn for turn in reversed(history.turns)
            if turn.get("role") == "assistant"
            and isinstance(turn.get("text"), str)
            and "?" in turn["text"]
            and turn.get("text_digest") == digest_payload({"text": turn["text"]})), None)
    strongest_score = max(score for score, _ in ranked)
    strongest = [turn for score, turn in ranked if score == strongest_score]
    return strongest[0] if len(strongest) == 1 else None


def _is_direct_recent_user_turn_recall_request(message: str) -> bool:
    """Whether the user asks for their immediately preceding message."""
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", message.casefold()).split())
    return any(marker in normalized for marker in (
        "what did i just ask", "what did i ask just before",
        "what did i ask you to see", "what did i ask to see",
        "what did i ask you to look at", "what did i ask you to read",
        "what was my last question", "what was my previous question",
        "what was the last thing i asked", "what was the previous thing i asked",
    ))


def _is_self_contained_text_echo_request(message: str) -> bool:
    """Avoid cross-session memories when the user supplies the exact text to echo."""
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", message.casefold()).split())
    return any(marker in normalized for marker in (
        "repeat this exact phrase", "repeat this exact test phrase",
        "copy this exact text", "echo this exact text",
    ))

def _is_current_runtime_context_question(message: str) -> bool:
    """Keep lexical memories from competing with verified live app and screen facts."""
    normalized = " ".join(re.sub(
        r"[^a-z0-9]+", " ", message.casefold()).split())
    markers = (
        "can you see my screen", "can you see what i am doing",
        "what can you see", "what am i doing", "what am i looking at",
        "what can you verify about the game that is currently open",
        "what details can you not observe",
        "what you can observe about the current",
        "what do you observe about the current",
        "what can you tell from your live connection",
        "what can you tell from the live connection",
        "what does your live connection confirm",
        "what do you know about my current", "what game am i playing",
        "what game is open", "which game is open", "what is on my screen", "is my screen visible",
        "my current game", "current cronos session",
    )
    return (any(marker in normalized for marker in markers)
            or is_direct_screen_activity_question(message)
            or is_verified_current_game_context_question(message))


def _is_social_checkin_request(message: str) -> bool:
    """Avoid treating casual check-ins as requests for topic-matched advice."""
    normalized = " ".join(message.casefold().split())
    markers = (
        "how are you", "how's it going", "how is it going", "how are things",
        "how do you feel", "just checking in", "just saying hi",
        "just saying hello", "how about you", "ask me one easy question",
        "ask one easy question", "tell me you are here", "tell me you're here",
        "say you are here", "say you're here", "here with me",
        "keep me company", "could use some company",
        "company while i play", "company while i game",
        "you'd like to ask me", "you’d like to ask me",
        "what else are you curious about", "what else would you like to know",
    )
    companion_roles = r"(?:gaming )?(?:co[- ]?pilot|sidekick|companion)"
    companion_shift_checkin = re.search(
        rf"\bhow(?:'s| is) (?:the|your) {companion_roles}(?: shift)? going\b",
        normalized,
    )
    companion_day_checkin = re.search(
        rf"\bhow(?:'s| is) your (?:day|night|evening) going as "
        rf"(?:my )?{companion_roles}\b",
        normalized,
    )
    asks_for_one_question = re.search(
        r"\bask(?: me)? (?:one|a) "
        r"(?:(?:new|different|another|specific|easy|concrete|natural|"
        r"open(?:[- ]ended)?|simple|short|brief|quick|thoughtful|playful|fun),? )*"
        r"question\b",
        normalized,
    )
    return (any(marker in normalized for marker in markers)
            or asks_for_one_question is not None
            or companion_shift_checkin is not None
            or companion_day_checkin is not None)


def _is_social_checkin_continuation(message: str) -> bool:
    """Recognize a check-in that explicitly refers to the immediately prior exchange."""
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", message.casefold()).split())
    markers = (
        "that is the kind of", "that s the kind of",
        "that is what i mean", "that s what i mean",
        "i like that", "i like your answer", "i like your response",
        "you asked me", "you just asked", "you said", "you mentioned",
        "what you said", "your last answer", "your last response",
        "tell me more", "elaborate on that", "go on",
        "ask one specific", "ask me one specific",
        "ask one new", "ask me one new",
        "ask one different", "ask me one different",
        "ask another", "what else are you curious about",
        "what else would you like to know", "not a general invitation",
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
    __slots__ = ("_delegate", "_workload_mode", "_workload_lock", "_inference_lock",
                 "_residency_release", "_model_profiles", "_foreground_game_detector",
                 "_game_process_names", "_effective_workload_mode", "_gaming_keep_alive",
                 "_gaming_resource_status_provider", "_residency_preload")
    def __init__(self, invoker: GovernedLocalModelInvoker,
                 model_profiles: Mapping[str, Any] | None = None,
                 foreground_game_detector: Any | None = None,
                 gaming_keep_alive: str = "0",
                 gaming_resource_status_provider: Callable[[], Mapping[str, Any]] | None = None
                 ) -> None:
        if gaming_keep_alive not in {"0", "5s", "5m", "15m", "-1"}:
            raise ValueError("unsupported_development_gaming_keep_alive")
        self._gaming_keep_alive = gaming_keep_alive
        if (gaming_resource_status_provider is not None
                and not callable(gaming_resource_status_provider)):
            raise TypeError("gaming_resource_status_provider_must_be_callable")
        self._gaming_resource_status_provider = gaming_resource_status_provider
        self._delegate = invoker
        self._workload_mode: WorkloadMode = "normal"
        self._workload_lock = threading.RLock()
        # Keep profile transitions away from active backend invocations.
        self._inference_lock = threading.Lock()
        self._residency_release: Mapping[str, Any] | None = None
        self._residency_preload: Mapping[str, Any] | None = None
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
    def model_residency_status(self) -> dict[str, object]:
        """Report a bounded point-in-time local model residency observation."""
        observed_at = datetime.now(timezone.utc).isoformat()
        if self._inference_lock.locked():
            return {"status": "operation_in_progress", "loaded": None,
                    "observed_at": observed_at}
        with self._workload_lock:
            model = getattr(self._delegate, "model", None)
            identity = getattr(model, "active_identity", None)
        if identity is None:
            return {"status": "unavailable", "loaded": None,
                    "reason_code": "model_identity_unavailable",
                    "observed_at": observed_at}
        if getattr(identity, "engine", None) != "ollama":
            return {"status": "not_applicable", "loaded": None,
                    "observed_at": observed_at}
        observer = getattr(model, "is_resident", None)
        if not callable(observer):
            return {"status": "unavailable", "loaded": None,
                    "reason_code": "model_residency_probe_unavailable",
                    "observed_at": observed_at}
        try:
            loaded = observer()
        except Exception:
            return {"status": "unavailable", "loaded": None,
                    "reason_code": "model_residency_probe_failed",
                    "observed_at": observed_at}
        if type(loaded) is not bool:
            return {"status": "unavailable", "loaded": None,
                    "reason_code": "model_residency_probe_invalid",
                    "observed_at": observed_at}
        return {"status": "resident" if loaded else "unloaded",
                "loaded": loaded, "observed_at": observed_at}
    def current_workload_mode(self) -> WorkloadMode:
        mode = self.current_workload_state().get("effective_mode")
        if mode not in {"normal", "gaming", "automatic"}:
            raise RuntimeError("effective_workload_mode_invalid")
        return mode

    def cognition_available(self) -> bool:
        return self.current_workload_state()["effective_mode"] == "normal"

    @contextmanager
    def cognition_inference_context(self):
        """Serialize cognition against chat/profile changes and admit normal mode only."""
        with self._workload_lock:
            state = self.current_workload_state()
            if state["mode"] == "automatic":
                self._select_profile_locked(state["effective_mode"])
            if state["effective_mode"] != "normal":
                raise CognitionWorkloadUnavailable()
            yield

    def current_workload_state(self) -> dict[str, Any]:
        with self._workload_lock:
            configured = self._workload_mode
            names = self._game_process_names
            detector = self._foreground_game_detector
            release = (dict(self._residency_release)
                if self._residency_release is not None else None)
            preload = (dict(self._residency_preload)
                if self._residency_preload is not None else None)
        if configured == "automatic":
            try:
                observed = detector.observe(names) if detector is not None else None
            except Exception:
                observed = None
            if observed is not None and observed.status == "available":
                foreground = observed.game_foreground
                process_running = observed.game_process_running
                if foreground is True:
                    effective, source = "gaming", "foreground_allowlist_match"
                elif process_running is True:
                    effective, source = "gaming", "allowlisted_game_process_running"
                elif process_running is False:
                    effective, source = "normal", "foreground_allowlist_no_match"
                else:
                    effective, source = "gaming", "game_process_observation_unavailable_conservative_gaming"
                evidence = {
                    "status": observed.status, "source": source,
                    "game_foreground": foreground,
                    "game_process_running": process_running,
                    "running_process_name_digests": (
                        list(observed.running_process_name_digests)
                        if observed.running_process_name_digests is not None else None),
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
                    "game_foreground": None, "game_process_running": None,
                    "running_process_name_digests": None, "process_name_digest": None,
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
            "game_process_running": evidence.get("game_process_running"),
            "foreground_game_detected": evidence["game_foreground"] is True,
            "workload_evidence": evidence,
        }
        if configured == "automatic":
            state["configured_game_process_names"] = list(names)
        if (self._gaming_resource_status_provider is not None
                and effective == "gaming"):
            try:
                resource_state = self._gaming_resource_status_provider()
            except Exception:
                resource_state = {
                    "admission_status": "deferred",
                    "reason_code": "vram_telemetry_unavailable",
                }
            if isinstance(resource_state, Mapping):
                state["gaming_resource_status"] = dict(resource_state)
        if release is not None:
            state["residency_release"] = release
        if preload is not None:
            state["residency_preload"] = preload
        return state
    def reconcile_workload_state(self) -> dict[str, Any]:
        """Apply automatic profile transitions and gated small-model residency."""
        state = self.current_workload_state()
        if state["mode"] != "automatic":
            return state
        if not self._inference_lock.acquire(blocking=False):
            return {**state, "workload_reconciliation": {
                "status": "deferred", "reason_code": "inference_in_progress"}}
        try:
            return self._reconcile_workload_state_during_idle_inference(state)
        finally:
            self._inference_lock.release()

    def _reconcile_workload_state_during_idle_inference(
            self, state: dict[str, Any]) -> dict[str, Any]:
        with self._workload_lock:
            # A concurrent operator mode change wins over this stale observation.
            if self._workload_mode != "automatic":
                return self.current_workload_state()
            self._select_profile_locked(state["effective_mode"])
            if (state["effective_mode"] == "gaming"
                    and state.get("game_foreground") is True
                    and self._gaming_keep_alive == "-1"
                    and getattr(getattr(self._delegate.model, "active_identity", None),
                                "engine", None) == "ollama"):
                resource = state.get("gaming_resource_status")
                if (isinstance(resource, Mapping)
                        and resource.get("preload_admission_status") == "available"):
                    identity = getattr(self._delegate.model, "active_identity", None)
                    identity_digest = (digest_payload(identity.to_dict())
                        if identity is not None else None)
                    prior_is_current = (
                        self._residency_preload is not None
                        and self._residency_preload.get("model_identity_digest") == identity_digest
                        and self._residency_preload.get("status") in {"preloaded", "already_resident"})
                    should_preload = not prior_is_current
                    if prior_is_current:
                        try:
                            should_preload = not self._delegate.model.is_resident()
                        except Exception:
                            # Let the governed preload path record backend failure;
                            # a transient Ollama observation failure must not abort
                            # workload reconciliation or the chat service.
                            should_preload = True
                    if should_preload:
                        receipt = self._delegate.preload_model_residency(
                            keep_alive=self._gaming_keep_alive,
                            workload_state=state,
                            resource_state=resource)
                        self._residency_preload = receipt.to_dict()
            if self._residency_release is not None:
                state["residency_release"] = dict(self._residency_release)
            if self._residency_preload is not None:
                state["residency_preload"] = dict(self._residency_preload)
        return state
    def set_workload_mode(self, mode: str,
                          game_process_names: tuple[str, ...] | list[str] = ()) -> str:
        selected = GamingWorkloadPolicy.validate_mode(mode)
        names = (normalize_game_process_names(game_process_names)
                 if selected == "automatic" else ())
        target_mode = "gaming" if selected == "automatic" else selected
        with self._inference_lock, self._workload_lock:
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
                 caller_linkage: Mapping[str, Any],
                 on_content_chunk: Callable[[str], None] | None = None) -> LocalModelInvocationReceipt:
        with self._inference_lock:
            return self._generate_with_invocation_barrier(
                prompt=prompt, caller=caller, correlation_id=correlation_id,
                budget=budget, caller_linkage=caller_linkage,
                on_content_chunk=on_content_chunk)

    def _generate_with_invocation_barrier(self, *, prompt: str, caller: str,
                 correlation_id: str, budget: LocalModelInvocationBudget,
                 caller_linkage: Mapping[str, Any],
                 on_content_chunk: Callable[[str], None] | None = None) -> LocalModelInvocationReceipt:
        workload_state = self.current_workload_state()
        with self._workload_lock:
            if workload_state["mode"] != self._workload_mode:
                workload_state = self.current_workload_state()
            mode = workload_state["effective_mode"]
            if workload_state["mode"] == "automatic":
                self._select_profile_locked(mode)
            response_style = caller_linkage.get("chat_response_style")
            social_checkin = response_style == "social_checkin"
            screen_observation = response_style == "screen_observation"
            effective_prompt = GamingWorkloadPolicy.apply_chat_response_style(
                prompt, mode, social_checkin=social_checkin,
                screen_observation=screen_observation)
            recent_session_recall = caller_linkage.get("recent_session_recall") is True
            effective_budget = GamingWorkloadPolicy.constrain_budget(
                mode, budget, recent_session_recall=recent_session_recall,
                response_style=str(response_style or "default"))
            linkage = {**dict(caller_linkage), "workload_mode": mode,
                "workload_evidence": workload_state["workload_evidence"]}
            identity = getattr(self._delegate.model, "active_identity", None)
            if mode == "gaming" and getattr(identity, "engine", None) == "ollama":
                linkage["ollama_keep_alive"] = self._gaming_keep_alive
                model_metadata = getattr(self._delegate.model, "metadata", {})
                if isinstance(model_metadata, Mapping):
                    history_format = model_metadata.get("chat_history_format", "serialized")
                    if history_format in {"serialized", "role_separated"}:
                        linkage["chat_history_format"] = history_format
            request = self._delegate.build_request(purpose="local_user_chat",
                prompt=effective_prompt, caller=caller, correlation_id=correlation_id,
                budget=effective_budget, linkage=linkage)
        if on_content_chunk is None:
            return self._delegate.invoke(request)
        if getattr(identity, "engine", None) != "ollama":
            raise RuntimeError("local_streaming_backend_unsupported")
        return self._delegate.invoke(request, on_content_chunk=on_content_chunk)

    def generate_streaming(self, **kwargs: Any) -> LocalModelInvocationReceipt:
        return self.generate(**kwargs)

    def streaming_available(self) -> bool:
        """Advertise streaming only when the active development model supports it."""
        identity = getattr(self._delegate.model, "active_identity", None)
        return getattr(identity, "engine", None) == "ollama"

    def cancel_pending_generation(self) -> bool:
        cancel = getattr(self._delegate, "cancel_pending_generation", None)
        return bool(cancel()) if callable(cancel) else False

    def close(self) -> None:
        """Release this development profile when its supervised chat runtime stops."""
        identity = getattr(self._delegate.model, "active_identity", None)
        if identity is None or getattr(identity, "engine", None) != "ollama":
            return
        try:
            receipt = self._delegate.release_model_residency(
                reason_code="development_chat_shutdown")
        except Exception as exc:
            LOGGER.warning("Development chat model release at shutdown failed: %s",
                type(exc).__name__)
            return
        with self._workload_lock:
            self._residency_release = receipt.to_dict()
        if receipt.status not in {"released", "already_unloaded", "not_applicable"}:
            LOGGER.warning("Development chat model release at shutdown was not confirmed: %s",
                receipt.status)


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

class HistoryInterventionRequest(BaseModel):
    session_id: str
    assistant_turn_id: str
    request_id: str
    operator_confirmed: bool = False


class DevelopmentalCycleRequest(BaseModel):
    session_id: str
    assistant_turn_id: str
    request_id: str
    operator_confirmed: bool = False
    operator_feedback: str | None = None


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    retain: bool = False
    request_id: str | None = None
    observe_screen: bool = False


def _publish_grounded_model_stream(
    on_content_chunk: Callable[[str], None],
    chunks: list[str],
    *,
    generated_text: str,
    response_text: str,
    response_origin: str,
) -> None:
    """Publish only text that survived final grounding and response policy."""
    if response_origin == "model_generated" and "".join(chunks) == generated_text:
        for chunk in chunks:
            on_content_chunk(chunk)
        return
    if response_text:
        on_content_chunk(response_text)


class ChatResponse(BaseModel):
    response: str
    session_id: str
    turn_id: str
    context: dict[str, object]
    retention: dict[str, object]
    response_diagnostics: dict[str, object] = {}

    def __init__(self, **data: Any) -> None:
        response_text = data.get("response")
        diagnostics = data.get("response_diagnostics")
        if isinstance(response_text, str):
            diagnostics = dict(diagnostics) if isinstance(diagnostics, Mapping) else {}
            diagnostics.setdefault("delivery_text_sha256",
                hashlib.sha256(response_text.encode("utf-8")).hexdigest())
            data["response_diagnostics"] = diagnostics
        super().__init__(**data)


def _chat_response_diagnostics(response_text: str,
                               lineage: Mapping[str, Any] | None = None
                               ) -> dict[str, object]:
    """Bind API delivery text to stored lineage without exposing model prompts."""
    result = dict(lineage) if isinstance(lineage, Mapping) else {}
    delivery_digest = hashlib.sha256(response_text.encode("utf-8")).hexdigest()
    result["delivery_text_sha256"] = delivery_digest
    result.setdefault("transcript_text_sha256", delivery_digest)
    return result


def _bounded_screen_observation_provenance(
        observation: Mapping[str, Any] | None) -> dict[str, object] | None:
    """Keep bounded screen diagnostics without retaining OCR or caption text."""
    if not isinstance(observation, Mapping):
        return None
    capture_digest = observation.get("capture_digest")
    if not isinstance(capture_digest, str) or re.fullmatch(r"[0-9a-f]{64}", capture_digest) is None:
        return None
    text_digest = observation.get("text_digest")
    if not isinstance(text_digest, str) or re.fullmatch(r"[0-9a-f]{64}", text_digest) is None:
        text = observation.get("text")
        if not isinstance(text, str):
            return None
        text_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    text_status = observation.get("text_status")
    if text_status not in {"available", "no_readable_text"}:
        return None
    captured_at = observation.get("captured_at")
    if not isinstance(captured_at, str) or not 1 <= len(captured_at) <= 64:
        return None
    result: dict[str, object] = {
        "capture_digest": capture_digest,
        "text_digest": text_digest,
        "text_status": text_status,
        "captured_at": captured_at,
        "raw_frame_retained": False,
    }
    backend = observation.get("backend")
    if isinstance(backend, str) and re.fullmatch(r"[A-Za-z0-9_.+-]{1,64}", backend):
        result["backend"] = backend
    allowed_statuses = {"available", "unavailable", "no_readable_text"}
    statuses = observation.get("component_statuses")
    if (isinstance(statuses, Mapping) and statuses
            and not set(statuses) - {"ocr", "vision"}
            and all(isinstance(value, str) and value in allowed_statuses
                    for value in statuses.values())):
        result["component_statuses"] = dict(statuses)
    failures = observation.get("component_failure_codes")
    if (isinstance(failures, Mapping) and failures
            and not set(failures) - {"ocr", "vision"}
            and all(isinstance(code, str)
                    and re.fullmatch(r"(?:screen|game_screen)_[a-z0-9_]{1,80}", code)
                    and isinstance(statuses, Mapping)
                    and statuses.get(component) == "unavailable"
                    for component, code in failures.items())):
        result["component_failure_codes"] = dict(failures)
    if observation.get("capture_scope") == "allowlisted_foreground_game_client_area":
        result["capture_scope"] = "allowlisted_foreground_game_client_area"
    for key in ("process_name_digest", "consent_id_digest"):
        value = observation.get(key)
        if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value):
            result[key] = value
    text_change_kind = observation.get("text_change_kind")
    if text_change_kind in {"initial", "changed", "unchanged"}:
        result["text_change_kind"] = text_change_kind
    visual_change_kind = observation.get("visual_change_kind")
    if visual_change_kind in {"initial", "changed", "stable", "unknown"}:
        result["visual_change_kind"] = visual_change_kind
    return result


_SAVED_RESPONSE_LINEAGE_KEYS = frozenset({
    "status", "invocation_output_digest", "transcript_text_digest",
    "invocation_output_text_sha256", "transcript_text_sha256",
    "delivery_text_sha256", "output_truncated",
})


def _saved_transcript_response_diagnostics(
        turn: Mapping[str, Any]) -> dict[str, object]:
    text = turn.get("text")
    if not isinstance(text, str):
        return {"status": "historical_lineage_unavailable"}
    linkage = turn.get("linkage")
    lineage = (linkage.get("assistant_output_lineage")
        if isinstance(linkage, Mapping) else None)
    result: dict[str, object] = {}
    if isinstance(lineage, Mapping):
        for key in _SAVED_RESPONSE_LINEAGE_KEYS:
            value = lineage.get(key)
            if isinstance(value, (str, bool)):
                result[key] = value
    saved_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    result["saved_transcript_text_sha256"] = saved_digest
    if isinstance(linkage, Mapping):
        result["developmental_history_intervention_available"] = (
            linkage.get("response_origin") == "resident_developmental_cognition"
            and isinstance(linkage.get("cognition_observation_id"), str)
            and isinstance(linkage.get("cognition_observation_digest"), str))
        screen = linkage.get("screen_observation_provenance")
        response_digest = linkage.get("response_digest")
        result["operator_feedback_available"] = (
            result["developmental_history_intervention_available"] is True
            and isinstance(response_digest, str)
            and re.fullmatch(r"[0-9a-f]{64}", response_digest) is not None
            and isinstance(screen, Mapping)
            and isinstance(screen.get("capture_digest"), str)
            and re.fullmatch(r"[0-9a-f]{64}", screen["capture_digest"]) is not None)
        if isinstance(screen, Mapping):
            safe_screen: dict[str, object] = {"raw_frame_retained": False}
            text_status = screen.get("text_status")
            if text_status in {"available", "no_readable_text"}:
                safe_screen["text_status"] = text_status
            backend = screen.get("backend")
            if isinstance(backend, str) and 1 <= len(backend) <= 64:
                safe_screen["backend"] = backend
            component_statuses = screen.get("component_statuses")
            if (isinstance(component_statuses, Mapping)
                    and component_statuses
                    and not set(component_statuses) - {"ocr", "vision"}
                    and all(isinstance(status, str) and status in {
                        "available", "unavailable", "no_readable_text"}
                        for status in component_statuses.values())):
                safe_screen["component_statuses"] = dict(component_statuses)
            component_failures = screen.get("component_failure_codes")
            if (isinstance(component_failures, Mapping) and component_failures
                    and not set(component_failures) - {"ocr", "vision"}
                    and all(isinstance(code, str) and re.fullmatch(
                        r"(?:screen|game_screen)_[a-z0-9_]{1,80}", code) is not None
                        for code in component_failures.values())):
                safe_screen["component_failure_codes"] = dict(component_failures)
            captured_at = screen.get("captured_at")
            if isinstance(captured_at, str) and len(captured_at) <= 64:
                safe_screen["captured_at"] = captured_at
            result["screen_observation"] = safe_screen
    result.setdefault("delivery_text_sha256", saved_digest)
    result["delivery_text_digest_source"] = "computed_from_saved_transcript"
    if isinstance(result.get("transcript_text_sha256"), str):
        result["transcript_text_digest_source"] = "stored_invocation_lineage"
    else:
        result["transcript_text_sha256"] = saved_digest
        result["transcript_text_digest_source"] = "computed_from_saved_transcript"
    result.setdefault("status", "historical_lineage_unavailable")
    return result


def _stored_output_lineage_matches(stored: Any, observed: Any) -> bool:
    """Verify every historical field while allowing added diagnostics on replay."""
    return (stored is None
        or (isinstance(stored, Mapping) and isinstance(observed, Mapping)
            and all(observed.get(key) == value for key, value in stored.items())))


class ChatWorkloadModeRequest(BaseModel):
    mode: str
    game_process_names: tuple[str, ...] = ()


class ChatAvatarOutputRequest(BaseModel):
    session_id: str
    enabled: bool


class ChatSpeechOutputRequest(BaseModel):
    session_id: str
    enabled: bool


def _public_inference_timing(receipt: Any) -> dict[str, object]:
    """Expose bounded local timing counters without prompt or model output data."""
    result: dict[str, object] = {"backend_metrics_status": "unavailable"}
    latency_ms = getattr(receipt, "latency_ms", None)
    if type(latency_ms) is int and 0 <= latency_ms <= 3_600_000:
        result["invocation_latency_ms"] = latency_ms
    completion = getattr(receipt, "backend_completion", None)
    if not isinstance(completion, Mapping):
        return result
    backend = completion.get("backend")
    if backend in {"ollama", "llama_cpp"}:
        result["backend"] = backend
    for source, target, maximum in (
        ("total_duration_ns", "backend_total_duration_ns", 3_600_000_000_000),
        ("load_duration_ns", "load_duration_ns", 3_600_000_000_000),
        ("prompt_eval_duration_ns", "prompt_evaluation_duration_ns", 3_600_000_000_000),
        ("eval_duration_ns", "generation_duration_ns", 3_600_000_000_000),
        ("first_token_duration_ns", "first_content_chunk_duration_ns", 3_600_000_000_000),
        ("prompt_tokens", "prompt_tokens", 131072),
        ("completion_tokens", "completion_tokens", 131072),
    ):
        value = completion.get(source)
        if type(value) is int and 0 <= value <= maximum:
            result[target] = value
    if "backend" in result:
        result["backend_metrics_status"] = "available"
    return result


class ChatRequestStateError(ValueError):
    """A replay conflict or an intentionally unreplayed interrupted request."""


class ChatInputBudgetError(ChatRequestStateError):
    """Current chat content cannot fit the active workload input ceiling."""


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
                 screen_observer: Callable[[], Mapping[str, object] | None] | None = None,
                 screen_capture_policy: str = "request_driven",
                 resident_cognition_bridge: Any | None = None,
                 live_consequence_cycle_provider: Callable[
                     [str, str], Mapping[str, Any] | None
                 ] | None = None) -> None:
        self._inference = inference; self.sessions = session_store; self.memories = memory_store
        self._avatar_output = avatar_output
        self._avatar_workload_sync_lock = threading.Lock()
        self._avatar_workload_mode_apply_lock = threading.Lock()
        self._avatar_workload_sync: dict[str, tuple[threading.Event, threading.Thread]] = {}
        self._avatar_workload_modes_observed: dict[str, str] = {}
        self._speech_output = speech_output
        if screen_capture_policy not in {"request_driven", "allowlisted_session_polling"}:
            raise ValueError("screen_capture_policy_invalid")
        self._screen_observer = screen_observer
        self._screen_capture_policy = screen_capture_policy
        if (resident_cognition_bridge is not None
                and not callable(getattr(resident_cognition_bridge, "respond", None))):
            raise TypeError("resident_cognition_bridge_invalid")
        self._resident_cognition_bridge = resident_cognition_bridge
        if (live_consequence_cycle_provider is not None
                and not callable(live_consequence_cycle_provider)):
            raise TypeError("live_consequence_cycle_provider_must_be_callable")
        self._live_consequence_cycle_provider = live_consequence_cycle_provider
        self.admission_gate = admission_gate or ExplicitRetentionAdmissionGate()
        self.retention_writer = AdmittedRetentionWriter(
            memory_store, admission_gate=self.admission_gate)
        self.context_budget_chars = context_budget_chars; self.memory_budget_chars = memory_budget_chars

    def history_intervention_available(self) -> bool:
        bridge = self._resident_cognition_bridge
        available = getattr(bridge, "history_intervention_available", None)
        return (self._screen_observer is not None and callable(available)
            and available() is True)

    def run_history_intervention(self, *, session_id: str,
            assistant_turn_id: str, request_id: str) -> dict[str, Any]:
        """Run an explicitly requested present/withheld/restored cognition comparison."""
        if (not isinstance(session_id, str) or not session_id
                or not isinstance(assistant_turn_id, str)
                or not re.fullmatch(r"turn-[0-9a-f]{24}", assistant_turn_id)
                or not isinstance(request_id, str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", request_id)):
            raise ChatRequestStateError("history_intervention_request_invalid")
        bridge = self._resident_cognition_bridge
        observer = self._screen_observer
        if bridge is None or observer is None:
            raise ChatRequestStateError("history_intervention_path_unavailable")
        if not self.history_intervention_available():
            raise CognitionWorkloadUnavailable()
        with self.sessions.serialize_chat_requests(session_id):
            session = self.sessions.load(session_id)
            assistant = next((turn for turn in session["turns"]
                if turn.get("turn_id") == assistant_turn_id
                and turn.get("role") == "assistant"), None)
            linkage = assistant.get("linkage") if isinstance(assistant, Mapping) else None
            if (not isinstance(assistant, Mapping) or not isinstance(linkage, Mapping)
                    or linkage.get("response_origin")
                        != "resident_developmental_cognition"):
                raise ChatRequestStateError(
                    "history_intervention_requires_resident_cognition_reply")
            source_turn_id = linkage.get("source_user_turn_id")
            source_turn = next((turn for turn in session["turns"]
                if turn.get("turn_id") == source_turn_id
                and turn.get("role") == "user"), None)
            question = source_turn.get("text") if isinstance(source_turn, Mapping) else None
            if not isinstance(question, str) or not question.strip() or len(question) > 1200:
                raise ChatRequestStateError(
                    "history_intervention_source_question_unavailable")
            cognition_request_id = f"{session_id}:{source_turn_id}"
            verifier = getattr(bridge, "verify_committed_response", None)
            if (not callable(verifier) or verifier(linkage=linkage,
                    response_text=str(assistant.get("text", "")),
                    request_id=cognition_request_id) is not True):
                raise ChatRequestStateError(
                    "history_intervention_prior_response_unverified")
            question_observer = getattr(type(observer), "observe_question", None)
            observation = (question_observer(observer, question)
                if callable(question_observer) else observer())
            if not isinstance(observation, Mapping):
                raise RuntimeError("screen_observation_unavailable")
            tick_id = "companion-history-intervention-" + hashlib.sha256(
                f"{session_id}\0{request_id}".encode("utf-8")).hexdigest()[:32]
            result = bridge.compare_history_intervention(
                tick_id=tick_id, question=question,
                screen_observation=observation)
        return {
            "status": result.status,
            "tick_id": result.tick_id,
            "measurement_id": result.changed_cognition_measurement_id,
            "response_text_classification": result.response_text_classification,
            "restored_prompt_matches": result.restored_prompt_matches,
            "conditions": [str(item.get("condition_id", "unknown"))
                for item in result.conditions],
            "condition_responses": [{
                "condition_id": str(item.get("condition_id", "unknown")),
                "response_text": str(item.get("response", ""))[:4000],
                "disposition": str(item.get("disposition", "unknown")),
            } for item in result.conditions],
            "authority": result.authority,
            "action_authority": result.action_authority,
            "performance_improvement_established": False,
            "raw_frame_retained": False,
        }

    def developmental_cycle_available(self) -> bool:
        bridge = self._resident_cognition_bridge
        available = getattr(bridge, "developmental_cycle_available", None)
        return (self._screen_observer is not None and callable(available)
            and available() is True)

    def operator_feedback_available(self) -> bool:
        bridge = self._resident_cognition_bridge
        available = getattr(bridge, "operator_feedback_available", None)
        return callable(available) and available() is True

    def run_developmental_cycle(self, *, session_id: str,
            assistant_turn_id: str, request_id: str,
            operator_feedback: str | None = None) -> dict[str, Any]:
        """Capture fresh local evidence and invoke the existing governed writeback owner."""
        if (not isinstance(session_id, str) or not session_id
                or not isinstance(assistant_turn_id, str)
                or not re.fullmatch(r"turn-[0-9a-f]{24}", assistant_turn_id)
                or not isinstance(request_id, str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", request_id)):
            raise ChatRequestStateError("developmental_cycle_request_invalid")
        bridge = self._resident_cognition_bridge
        observer = self._screen_observer
        if bridge is None or observer is None:
            raise ChatRequestStateError("developmental_cycle_path_unavailable")
        if not self.developmental_cycle_available():
            raise CognitionWorkloadUnavailable()
        if operator_feedback is not None and not self.operator_feedback_available():
            raise ChatRequestStateError(
                "developmental_cycle_operator_feedback_not_enabled")
        with self.sessions.serialize_chat_requests(session_id):
            session = self.sessions.load(session_id)
            assistant = next((turn for turn in session["turns"]
                if turn.get("turn_id") == assistant_turn_id
                and turn.get("role") == "assistant"), None)
            linkage = assistant.get("linkage") if isinstance(assistant, Mapping) else None
            if (not isinstance(assistant, Mapping) or not isinstance(linkage, Mapping)
                    or linkage.get("response_origin")
                        != "resident_developmental_cognition"):
                raise ChatRequestStateError(
                    "developmental_cycle_requires_resident_cognition_reply")
            source_turn_id = linkage.get("source_user_turn_id")
            source_turn = next((turn for turn in session["turns"]
                if turn.get("turn_id") == source_turn_id
                and turn.get("role") == "user"), None)
            if not isinstance(source_turn, Mapping):
                raise ChatRequestStateError(
                    "developmental_cycle_source_turn_unavailable")
            cognition_request_id = f"{session_id}:{source_turn_id}"
            verifier = getattr(bridge, "verify_committed_response", None)
            if (not callable(verifier) or verifier(linkage=linkage,
                    response_text=str(assistant.get("text", "")),
                    request_id=cognition_request_id) is not True):
                raise ChatRequestStateError(
                    "developmental_cycle_prior_response_unverified")
            feedback_record = None
            source_capture_digest: str | None = None
            feedback_observed_at = datetime.now(timezone.utc).isoformat().replace(
                "+00:00", "Z")
            if operator_feedback is not None:
                if (not isinstance(operator_feedback, str)
                        or not operator_feedback.strip()
                        or len(operator_feedback) > 800
                        or len(operator_feedback.encode("utf-8")) > 2048):
                    raise ChatRequestStateError(
                        "developmental_cycle_operator_feedback_invalid")
                source_provenance = linkage.get("screen_observation_provenance")
                source_capture_digest = (
                    source_provenance.get("capture_digest")
                    if isinstance(source_provenance, Mapping) else None)
                if (not isinstance(source_capture_digest, str)
                        or re.fullmatch(r"[0-9a-f]{64}", source_capture_digest) is None):
                    raise ChatRequestStateError(
                        "developmental_cycle_operator_feedback_requires_screen_evidence")
            question = "Capture the current allowlisted foreground game for one operator-requested developmental cognition cycle."
            question_observer = getattr(type(observer), "observe_question", None)
            observation = (question_observer(observer, question)
                if callable(question_observer) else observer())
            if not isinstance(observation, Mapping):
                raise RuntimeError("screen_observation_unavailable")
            consequence_measurement: Mapping[str, Any] | None = None
            current_consequence_records: tuple[Mapping[str, Any], ...] = ()
            if self._live_consequence_cycle_provider is not None:
                try:
                    consequence_measurement = (
                        self._live_consequence_cycle_provider(session_id, assistant_turn_id))
                except Exception as exc:  # noqa: BLE001 - optional capture must fail open for screen writeback
                    # The optional second measurement must not suppress the
                    # ordinary operator-confirmed screen-evidence writeback.
                    consequence_measurement = {
                        "status": "unavailable",
                        "error_type": type(exc).__name__,
                        "effect_proven": False,
                    }
                if consequence_measurement is not None:
                    measurement_status = consequence_measurement.get("status")
                    if measurement_status == "completed":
                        records = consequence_measurement.get("world_state_records")
                        if (not isinstance(records, (tuple, list))
                                or not records or len(records) > 32
                                or any(not isinstance(item, Mapping) for item in records)):
                            raise RuntimeError(
                                "developmental_consequence_measurement_invalid")
                        current_consequence_records = tuple(records)
                    elif measurement_status != "unavailable":
                        raise RuntimeError(
                            "developmental_consequence_measurement_invalid")
            tick_id = "companion-developmental-cycle-" + hashlib.sha256(
                f"{session_id}\0{assistant_turn_id}\0{request_id}".encode("utf-8")).hexdigest()[:32]
            if operator_feedback is not None:
                response_digest = linkage.get("response_digest")
                followup_capture_digest = observation.get("capture_digest")
                if (not isinstance(response_digest, str)
                        or re.fullmatch(r"[0-9a-f]{64}", response_digest) is None
                        or not isinstance(followup_capture_digest, str)
                        or re.fullmatch(r"[0-9a-f]{64}", followup_capture_digest) is None):
                    raise ChatRequestStateError(
                        "developmental_cycle_operator_feedback_lineage_invalid")
                if source_capture_digest is None:
                    raise ChatRequestStateError(
                        "developmental_cycle_operator_feedback_requires_screen_evidence")
                feedback_record = make_operator_feedback_record(
                    operator_feedback, request_id=request_id,
                    assistant_turn_id=assistant_turn_id,
                    assistant_response_digest=response_digest,
                    source_capture_digest=source_capture_digest,
                    followup_capture_digest=followup_capture_digest,
                    observed_at=feedback_observed_at)
            cycle_kwargs: dict[str, Any] = {
                "tick_id": tick_id, "screen_observation": observation,
                "operator_feedback": feedback_record,
            }
            if current_consequence_records:
                cycle_kwargs["current_consequence_records"] = current_consequence_records
            result = bridge.run_developmental_cycle(**cycle_kwargs)
        if result.status != "completed":
            raise ChatRequestStateError("developmental_cycle_not_completed")
        return {
            "status": ("completed_writeback" if result.written_record_id is not None
                else "completed_without_writeback"),
            "tick_id": result.tick_id,
            "assistant_turn_id": assistant_turn_id,
            "snapshot_id": result.snapshot_id,
            "selected_fact_ids": list(result.selected_fact_ids),
            "prior_record_ids": list(result.prior_record_ids),
            "written_record_id": result.written_record_id,
            "writeback_receipt_id": result.writeback_receipt_id,
            "cognition_observation_ids": list(result.cognition_observation_ids),
            "operator_feedback_included": feedback_record is not None,
            "operator_feedback_posture": ("operator_assertion_unverified"
                if feedback_record is not None else None),
            "self_model_reconciliation_status": getattr(
                result, "self_model_reconciliation_status", "not_configured"),
            "self_model_reconciliation_id": getattr(
                result, "self_model_reconciliation_id", None),
            "self_model_reconciliation_digest": getattr(
                result, "self_model_reconciliation_digest", None),
            "self_model_reconciliation_generation": getattr(
                result, "self_model_reconciliation_generation", None),
            "self_model_claim_count": getattr(result, "self_model_claim_count", None),
            "self_model_reconciliation_error_type": getattr(
                result, "self_model_reconciliation_error_type", None),
            "raw_frame_retained": False,
            "consequence_measurement": ({
                "status": consequence_measurement.get("status"),
                "error_type": consequence_measurement.get("error_type"),
                "chain_id": consequence_measurement.get("chain_id"),
                "classification": consequence_measurement.get("classification"),
                "confidence": consequence_measurement.get("confidence"),
                "quality": consequence_measurement.get("quality"),
                "effect_proven": False,
                "renderer_effect_proven": False,
                "observer_transport_authenticated": consequence_measurement.get("observer_transport_authenticated") is True,
                "observation_accuracy_established": False,
            } if consequence_measurement is not None else None),
        }

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

    def reconcile_workload_state(self) -> dict[str, Any]:
        reconciler = getattr(self._inference, "reconcile_workload_state", None)
        if callable(reconciler):
            return dict(reconciler())
        return self.current_workload_state()

    def screen_observation_configured(self) -> bool:
        return self._screen_observer is not None

    def screen_observation_status(self) -> dict[str, Any]:
        configured = self.screen_observation_configured()
        status = {
            "configured": configured,
            "capture_policy": (self._screen_capture_policy if configured else "disabled"),
            "per_message_opt_in_required": True,
        }
        consent_status = getattr(self._screen_observer, "consent_status", None)
        if configured and callable(consent_status):
            try:
                metadata = consent_status()
            except Exception:
                metadata = {"consent_status": "unknown"}
            if isinstance(metadata, Mapping):
                status.update({key: value for key, value in metadata.items()
                               if key in {"consent_status", "consent_expires_at",
                                          "consent_seconds_remaining",
                                          "foreground_wait_seconds"}})
        return status

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
                if type(workload.get("game_process_running")) is bool:
                    workload_context["game_process_running"] = workload["game_process_running"]
                names = workload.get("configured_game_process_names")
                if ((workload["game_foreground"] is True
                     or workload.get("game_process_running") is True)
                        and isinstance(names, (tuple, list))
                        and all(isinstance(name, str) for name in names)):
                    workload_context["configured_game_process_names"] = list(names)
            elif workload.get("mode_source") == "local_development_operator_selection":
                workload_context["foreground_game_observation"] = "not_observed"
            resource_status = workload.get("gaming_resource_status")
            if isinstance(resource_status, Mapping):
                workload_context["gaming_resource_status"] = {
                    key: resource_status[key] for key in (
                        "admission_status", "reason_code",
                        "vram_utilization_percent", "observed_at",
                        "release_threshold_percent", "recovery_threshold_percent")
                    if key in resource_status and isinstance(
                        resource_status[key], (str, int, float, type(None)))
                }
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

    def streaming_available(self) -> bool:
        capability = getattr(self._inference, "streaming_available", None)
        if callable(capability):
            try:
                return bool(capability())
            except Exception:
                return False
        return callable(getattr(self._inference, "generate_streaming", None))

    def cancel_active_generation(self) -> bool:
        cancel = getattr(self._inference, "cancel_pending_generation", None)
        return bool(cancel()) if callable(cancel) else False

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
                LOGGER.warning(
                    "Avatar workload synchronization failed: code=%s phase=%s "
                    "failure_type=%s errno=%s",
                    getattr(exc, "code", type(exc).__name__),
                    getattr(exc, "failure_phase", None),
                    getattr(exc, "failure_type", type(exc).__name__),
                    getattr(exc, "failure_errno", None),
                )

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
                    LOGGER.warning(
                    "Avatar workload synchronization failed: code=%s phase=%s "
                    "failure_type=%s errno=%s",
                    getattr(exc, "code", type(exc).__name__),
                    getattr(exc, "failure_phase", None),
                    getattr(exc, "failure_type", type(exc).__name__),
                    getattr(exc, "failure_errno", None),
                )
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

    def close(self) -> None:
        try:
            self.close_outputs()
        finally:
            close_inference = getattr(self._inference, "close", None)
            if callable(close_inference):
                close_inference()

    def _complete_transcript_recall_response(
            self, *, session_id: str, user_turn: Mapping[str, Any],
            source_assistant_turn: Mapping[str, Any], history: Any,
            memory: Mapping[str, Any], on_content_chunk: Callable[[str], None] | None,
            transcript_recall_kind: str | None = None,
            ) -> ChatResponse:
        """Return a verified assistant turn verbatim from the same-session transcript."""
        response_text = str(source_assistant_turn["text"])
        source_turn_id = str(source_assistant_turn["turn_id"])
        source_text_digest = str(source_assistant_turn["text_digest"])
        output_digest = digest_payload({"text": response_text})
        decision_payload = {
            "schema": "sentientos.transcript_recall_decision:v1",
            "session_id": session_id,
            "source_user_turn_id": str(user_turn["turn_id"]),
            "source_user_text_digest": str(user_turn["text_digest"]),
            "source_assistant_turn_id": source_turn_id,
            "source_assistant_text_digest": source_text_digest,
            "output_digest": output_digest,
        }
        if transcript_recall_kind is not None:
            decision_payload["transcript_recall_kind"] = transcript_recall_kind
        decision_digest = digest_payload(decision_payload)
        recall_linkage: dict[str, Any] = {
                "source_user_turn_id": str(user_turn["turn_id"]),
                "response_origin": "transcript_recall",
                "source_assistant_turn_id": source_turn_id,
                "source_assistant_text_digest": source_text_digest,
                "policy_decision": {"payload": decision_payload, "digest": decision_digest},
                "assistant_output_lineage": {
                    "status": "transcript_recall_output",
                    "policy_decision_digest": decision_digest,
                    "transcript_text_digest": output_digest,
                },
                "context_snapshot_digest": history.snapshot_digest,
                "memory_snapshot_digest": str(memory["snapshot_digest"]),
                "memory_retrieval_posture": memory.get("retrieval_posture", "unknown"),
                "legacy_sidecar_posture": memory.get("legacy_sidecar_posture", "unknown_legacy"),
                "memory_selection_posture": memory.get("selection_posture", "unknown_legacy"),
                "omitted_memory_count": memory.get("omitted_memory_count"),
                "selected_turn_count": len(history.turns),
                "selected_memory_count": len(memory.get("memories", [])),
            }
        if transcript_recall_kind is not None:
            recall_linkage["transcript_recall_kind"] = transcript_recall_kind
        assistant = self.sessions.append_turn(session_id, role="assistant",
            text=response_text, linkage=recall_linkage)
        if self._avatar_output is not None:
            try:
                self._avatar_output.publish_response(session_id=session_id,
                    turn_id=str(assistant["turn_id"]), text=response_text,
                    output_digest=output_digest)
            except Exception as exc:
                LOGGER.warning("Avatar transcript recall publication failed: %s",
                    getattr(exc, "code", type(exc).__name__))
        if self._speech_output is not None:
            try:
                self._speech_output.publish_response(session_id=session_id,
                    turn_id=str(assistant["turn_id"]), text=response_text,
                    output_digest=output_digest)
            except Exception as exc:
                LOGGER.warning("Local transcript recall speech failed: %s", type(exc).__name__)
        if on_content_chunk is not None:
            on_content_chunk(response_text)
        response_context: dict[str, Any] = {
                "conversation_snapshot_digest": history.snapshot_digest,
                "memory_snapshot_digest": str(memory["snapshot_digest"]),
                "memory_retrieval_posture": memory.get("retrieval_posture", "unknown"),
                "legacy_sidecar_posture": memory.get("legacy_sidecar_posture", "unknown_legacy"),
                "memory_selection_posture": memory.get("selection_posture", "unknown_legacy"),
                "omitted_memory_count": memory.get("omitted_memory_count"),
                "selected_turn_count": len(history.turns),
                "selected_memory_count": len(memory.get("memories", [])),
                "response_origin": "transcript_recall",
                "policy_decision_digest": decision_digest,
                "inference_timing": {
                    "backend_metrics_status": "not_applicable",
                    "reason_code": "transcript_recall_response",
                },
            }
        if transcript_recall_kind is not None:
            response_context["transcript_recall_kind"] = transcript_recall_kind
        return ChatResponse(response=response_text, session_id=session_id,
            turn_id=str(assistant["turn_id"]), context=response_context,
            retention={"status": "not_requested"},
            response_diagnostics=_chat_response_diagnostics(response_text, {
                "status": "transcript_recall_output",
            }))

    def _complete_quoted_content_recall_response(
            self, *, session_id: str, user_turn: Mapping[str, Any],
            source_user_turn: Mapping[str, Any], quoted_value: str, history: Any,
            memory: Mapping[str, Any], on_content_chunk: Callable[[str], None] | None
            ) -> ChatResponse:
        """Return an exact quoted value from a verified user transcript turn."""
        source_turn_id = str(source_user_turn["turn_id"])
        source_text_digest = str(source_user_turn["text_digest"])
        quoted_text_digest = digest_payload({"text": quoted_value})
        output_digest = quoted_text_digest
        decision_payload = {
            "schema": "sentientos.transcript_quote_recall_decision:v1",
            "session_id": session_id,
            "source_user_turn_id": str(user_turn["turn_id"]),
            "source_user_text_digest": str(user_turn["text_digest"]),
            "recalled_user_turn_id": source_turn_id,
            "recalled_user_text_digest": source_text_digest,
            "quoted_text_digest": quoted_text_digest,
            "output_digest": output_digest,
        }
        decision_digest = digest_payload(decision_payload)
        assistant = self.sessions.append_turn(session_id, role="assistant",
            text=quoted_value, linkage={
                "source_user_turn_id": str(user_turn["turn_id"]),
                "response_origin": "transcript_recall",
                "transcript_recall_kind": "quoted_content",
                "recalled_user_turn_id": source_turn_id,
                "recalled_user_text_digest": source_text_digest,
                "recalled_quote_digest": quoted_text_digest,
                "policy_decision": {"payload": decision_payload, "digest": decision_digest},
                "assistant_output_lineage": {
                    "status": "transcript_quote_recall_output",
                    "policy_decision_digest": decision_digest,
                    "transcript_text_digest": output_digest,
                },
                "context_snapshot_digest": history.snapshot_digest,
                "memory_snapshot_digest": str(memory["snapshot_digest"]),
                "memory_retrieval_posture": memory.get("retrieval_posture", "unknown"),
                "legacy_sidecar_posture": memory.get("legacy_sidecar_posture", "unknown_legacy"),
                "memory_selection_posture": memory.get("selection_posture", "unknown_legacy"),
                "omitted_memory_count": memory.get("omitted_memory_count"),
                "selected_turn_count": len(history.turns),
                "selected_memory_count": len(memory.get("memories", [])),
            })
        if self._avatar_output is not None:
            try:
                self._avatar_output.publish_response(session_id=session_id,
                    turn_id=str(assistant["turn_id"]), text=quoted_value,
                    output_digest=output_digest)
            except Exception as exc:
                LOGGER.warning("Avatar transcript quote recall publication failed: %s",
                    getattr(exc, "code", type(exc).__name__))
        if self._speech_output is not None:
            try:
                self._speech_output.publish_response(session_id=session_id,
                    turn_id=str(assistant["turn_id"]), text=quoted_value,
                    output_digest=output_digest)
            except Exception as exc:
                LOGGER.warning("Local transcript quote recall speech failed: %s", type(exc).__name__)
        if on_content_chunk is not None:
            on_content_chunk(quoted_value)
        return ChatResponse(response=quoted_value, session_id=session_id,
            turn_id=str(assistant["turn_id"]), context={
                "conversation_snapshot_digest": history.snapshot_digest,
                "memory_snapshot_digest": str(memory["snapshot_digest"]),
                "memory_retrieval_posture": memory.get("retrieval_posture", "unknown"),
                "legacy_sidecar_posture": memory.get("legacy_sidecar_posture", "unknown_legacy"),
                "memory_selection_posture": memory.get("selection_posture", "unknown_legacy"),
                "omitted_memory_count": memory.get("omitted_memory_count"),
                "selected_turn_count": len(history.turns),
                "selected_memory_count": len(memory.get("memories", [])),
                "response_origin": "transcript_recall",
                "transcript_recall_kind": "quoted_content",
                "policy_decision_digest": decision_digest,
                "inference_timing": {
                    "backend_metrics_status": "not_applicable",
                    "reason_code": "transcript_quote_recall_response",
                },
            }, retention={"status": "not_requested"},
            response_diagnostics=_chat_response_diagnostics(quoted_value, {
                "status": "transcript_quote_recall_output",
            }))

    def _complete_prior_user_turn_recall_response(
            self, *, session_id: str, user_turn: Mapping[str, Any],
            source_user_turn: Mapping[str, Any], history: Any,
            memory: Mapping[str, Any], on_content_chunk: Callable[[str], None] | None
            ) -> ChatResponse:
        """Answer a direct last-question query from its verified transcript turn."""
        source_turn_id = str(source_user_turn["turn_id"])
        source_text = str(source_user_turn["text"])
        source_text_digest = str(source_user_turn["text_digest"])
        response_text = f"You asked: {chr(0x201c)}{source_text}{chr(0x201d)}"
        output_digest = digest_payload({"text": response_text})
        decision_payload = {
            "schema": "sentientos.prior_user_turn_recall_decision:v1",
            "session_id": session_id,
            "source_user_turn_id": str(user_turn["turn_id"]),
            "source_user_text_digest": str(user_turn["text_digest"]),
            "recalled_user_turn_id": source_turn_id,
            "recalled_user_text_digest": source_text_digest,
            "output_digest": output_digest,
        }
        decision_digest = digest_payload(decision_payload)
        assistant = self.sessions.append_turn(session_id, role="assistant",
            text=response_text, linkage={
                "source_user_turn_id": str(user_turn["turn_id"]),
                "response_origin": "transcript_recall",
                "transcript_recall_kind": "prior_user_turn",
                "recalled_user_turn_id": source_turn_id,
                "recalled_user_text_digest": source_text_digest,
                "policy_decision": {"payload": decision_payload, "digest": decision_digest},
                "assistant_output_lineage": {
                    "status": "prior_user_transcript_recall_output",
                    "policy_decision_digest": decision_digest,
                    "transcript_text_digest": output_digest,
                },
                "context_snapshot_digest": history.snapshot_digest,
                "memory_snapshot_digest": str(memory["snapshot_digest"]),
                "memory_retrieval_posture": memory.get("retrieval_posture", "unknown"),
                "legacy_sidecar_posture": memory.get("legacy_sidecar_posture", "unknown_legacy"),
                "memory_selection_posture": memory.get("selection_posture", "unknown_legacy"),
                "omitted_memory_count": memory.get("omitted_memory_count"),
                "selected_turn_count": len(history.turns),
                "selected_memory_count": len(memory.get("memories", [])),
            })
        if self._avatar_output is not None:
            try:
                self._avatar_output.publish_response(session_id=session_id,
                    turn_id=str(assistant["turn_id"]), text=response_text,
                    output_digest=output_digest)
            except Exception as exc:
                LOGGER.warning("Avatar prior-user recall publication failed: %s",
                    getattr(exc, "code", type(exc).__name__))
        if self._speech_output is not None:
            try:
                self._speech_output.publish_response(session_id=session_id,
                    turn_id=str(assistant["turn_id"]), text=response_text,
                    output_digest=output_digest)
            except Exception as exc:
                LOGGER.warning("Local prior-user recall speech failed: %s", type(exc).__name__)
        if on_content_chunk is not None:
            on_content_chunk(response_text)
        return ChatResponse(response=response_text, session_id=session_id,
            turn_id=str(assistant["turn_id"]), context={
                "conversation_snapshot_digest": history.snapshot_digest,
                "memory_snapshot_digest": str(memory["snapshot_digest"]),
                "memory_retrieval_posture": memory.get("retrieval_posture", "unknown"),
                "legacy_sidecar_posture": memory.get("legacy_sidecar_posture", "unknown_legacy"),
                "memory_selection_posture": memory.get("selection_posture", "unknown_legacy"),
                "omitted_memory_count": memory.get("omitted_memory_count"),
                "selected_turn_count": len(history.turns),
                "selected_memory_count": len(memory.get("memories", [])),
                "response_origin": "transcript_recall",
                "recalled_user_turn_id": source_turn_id,
                "policy_decision_digest": decision_digest,
                "inference_timing": {
                    "backend_metrics_status": "not_applicable",
                    "reason_code": "prior_user_turn_recall_response",
                },
            }, retention={"status": "not_requested"},
            response_diagnostics=_chat_response_diagnostics(response_text, {
                "status": "prior_user_transcript_recall_output",
            }))

    def _complete_deterministic_grounding_response(
            self, *, session_id: str, user_turn: Mapping[str, Any],
            response_text: str, correction: Mapping[str, str],
            runtime_context: Mapping[str, Any], history: Any,
            memory: Mapping[str, Any], on_content_chunk: Callable[[str], None] | None,
            screen_observation_provenance: Mapping[str, Any] | None = None
            ) -> ChatResponse:
        """Persist a verified policy answer without invoking the language model."""
        workload = runtime_context.get("workload")
        names = workload.get("configured_game_process_names") if isinstance(
            workload, Mapping) else None
        evidence = {
            "observation_status": workload.get("observation_status")
                if isinstance(workload, Mapping) else None,
            "game_foreground": workload.get("game_foreground")
                if isinstance(workload, Mapping) else None,
            "game_process_running": workload.get("game_process_running")
                if isinstance(workload, Mapping) else None,
            "configured_game_process_names": list(names)
                if isinstance(names, (list, tuple)) else [],
            "gaming_resource_status": (
                dict(workload["gaming_resource_status"])
                if isinstance(workload, Mapping)
                and isinstance(workload.get("gaming_resource_status"), Mapping)
                else None),
            "screen_observation_configured": (
                isinstance(runtime_context.get("capabilities"), Mapping)
                and isinstance(runtime_context["capabilities"].get("screen_observation"), Mapping)
                and runtime_context["capabilities"]["screen_observation"].get("configured") is True
            ),
        }
        bounded_screen_provenance = _bounded_screen_observation_provenance(
            screen_observation_provenance)
        if bounded_screen_provenance is not None:
            evidence["screen_observation_provenance"] = bounded_screen_provenance
        decision_payload = {
            "schema": "sentientos.deterministic_grounding_policy_decision:v1",
            "session_id": session_id,
            "source_user_turn_id": str(user_turn["turn_id"]),
            "source_user_text_digest": str(user_turn["text_digest"]),
            "policy_id": correction["policy_id"],
            "reason_code": correction["reason_code"],
            "evidence": evidence,
            "output_digest": digest_payload({"text": response_text}),
        }
        decision_digest = digest_payload(decision_payload)
        memory_digest = str(memory["snapshot_digest"])
        policy_decision = {"payload": decision_payload, "digest": decision_digest}
        assistant_output_lineage = {
            "status": "deterministic_policy_output",
            "policy_decision_digest": decision_digest,
            "transcript_text_digest": digest_payload({"text": response_text}),
        }
        assistant_linkage: dict[str, Any] = {
            "source_user_turn_id": str(user_turn["turn_id"]),
            "response_origin": "deterministic_grounding_policy",
            "policy_decision": policy_decision,
            "assistant_output_lineage": assistant_output_lineage,
            "context_snapshot_digest": history.snapshot_digest,
            "memory_snapshot_digest": memory_digest,
            "memory_retrieval_posture": memory.get("retrieval_posture", "unknown"),
            "legacy_sidecar_posture": memory.get("legacy_sidecar_posture", "unknown_legacy"),
            "memory_selection_posture": memory.get("selection_posture", "unknown_legacy"),
            "omitted_memory_count": memory.get("omitted_memory_count"),
            "selected_turn_count": len(history.turns),
            "selected_memory_count": len(memory.get("memories", [])),
        }
        if bounded_screen_provenance is not None:
            assistant_linkage["screen_observation_provenance"] = (
                bounded_screen_provenance)
        assistant = self.sessions.append_turn(session_id, role="assistant",
            text=response_text, linkage=assistant_linkage)
        if self._avatar_output is not None:
            try:
                publication: dict[str, Any] = {
                    "session_id": session_id,
                    "turn_id": str(assistant["turn_id"]),
                    "text": response_text,
                    "output_digest": digest_payload({"text": response_text}),
                }
                mode = workload.get("effective_mode") if isinstance(workload, Mapping) else None
                if isinstance(mode, str) and mode in {"normal", "gaming"}:
                    publication["workload_mode"] = mode
                self._avatar_output.publish_response(**publication)
            except Exception as exc:
                LOGGER.warning("Avatar policy response publication failed: %s",
                    getattr(exc, "code", type(exc).__name__))
        if self._speech_output is not None:
            try:
                self._speech_output.publish_response(
                    session_id=session_id, turn_id=str(assistant["turn_id"]),
                    text=response_text, output_digest=digest_payload({"text": response_text}))
            except Exception as exc:
                LOGGER.warning("Local policy response speech failed: %s", type(exc).__name__)
        if on_content_chunk is not None:
            on_content_chunk(response_text)
        return ChatResponse(response=response_text, session_id=session_id,
            turn_id=str(assistant["turn_id"]),
            context={
                "conversation_snapshot_digest": history.snapshot_digest,
                "memory_snapshot_digest": memory_digest,
                "memory_retrieval_posture": memory.get("retrieval_posture", "unknown"),
                "legacy_sidecar_posture": memory.get("legacy_sidecar_posture", "unknown_legacy"),
                "memory_selection_posture": memory.get("selection_posture", "unknown_legacy"),
                "omitted_memory_count": memory.get("omitted_memory_count"),
                "selected_turn_count": len(history.turns),
                "selected_memory_count": len(memory.get("memories", [])),
                "response_origin": "deterministic_grounding_policy",
                "policy_decision_digest": decision_digest,
                "inference_timing": {
                    "backend_metrics_status": "not_applicable",
                    "reason_code": "deterministic_policy_response",
                },
            },
            retention={"status": "not_requested"})

    def _complete_resident_cognition_response(self, *, session_id: str,
            user_turn: Mapping[str, Any], question: str,
            screen_observation: Mapping[str, object] | None,
            on_content_chunk: Callable[[str], None] | None) -> ChatResponse:
        """Deliver a resident cognition decision as a distinct, receipt-linked response."""
        bridge = self._resident_cognition_bridge
        if bridge is None:
            raise RuntimeError("resident_cognition_bridge_unavailable")
        request_id = f"{session_id}:{user_turn['turn_id']}"
        result = bridge.respond(request_id=request_id, question=question,
            screen_observation=screen_observation)
        response_text = getattr(result, "response", None)
        if (getattr(result, "status", None) != "admitted_completed"
                or not isinstance(response_text, str) or not response_text.strip()
                or len(response_text.encode("utf-8")) > 4000
                or getattr(result, "developmental_history_writeback_performed", True) is not False
                or getattr(result, "authority", True) is not False
                or getattr(result, "current_truth", True) is not False
                or getattr(result, "canonical_explicit_user_retention_mutated", True) is not False):
            raise RuntimeError("resident_cognition_response_contract_invalid")
        response_digest = digest_payload({"text": response_text})
        observation_id = getattr(result, "cognition_observation_id", None)
        observation_digest = getattr(result, "cognition_observation_digest", None)
        receipt_id = getattr(result, "inference_receipt_id", None)
        receipt_digest = getattr(result, "inference_receipt_digest", None)
        invocation_output_digest = getattr(result, "invocation_output_digest", None)
        model_id = getattr(result, "model_id", None)
        evidence_ids = getattr(result, "evidence_ids", ())
        prior_record_ids = getattr(result, "prior_record_ids", ())
        history_record_ids = getattr(result, "history_record_ids", ())
        if (not isinstance(observation_id, str) or not observation_id.startswith("devcog-")
                or not isinstance(observation_digest, str) or not observation_digest.startswith("sha256:")
                or not isinstance(receipt_id, str) or not receipt_id.startswith("lmrec-")
                or not isinstance(receipt_digest, str) or len(receipt_digest) != 64
                or not isinstance(invocation_output_digest, str)
                or not isinstance(model_id, str) or not model_id
                or not isinstance(evidence_ids, (tuple, list))
                or any(not isinstance(item, str) for item in evidence_ids)
                or not isinstance(prior_record_ids, (tuple, list))
                or any(not isinstance(item, str) for item in prior_record_ids)):
            raise RuntimeError("resident_cognition_response_lineage_invalid")
        if (not isinstance(history_record_ids, (tuple, list))
                or any(not isinstance(item, str) for item in history_record_ids)
                or len(set(history_record_ids)) != len(history_record_ids)
                or not set(history_record_ids).issubset(prior_record_ids)):
            raise RuntimeError("resident_cognition_history_lineage_invalid")
        lineage = {
            "status": "resident_cognition_interaction",
            "cognition_observation_id": observation_id,
            "cognition_observation_digest": observation_digest,
            "inference_receipt_id": receipt_id,
            "inference_receipt_digest": receipt_digest,
            "invocation_output_digest": invocation_output_digest,
            "response_digest": response_digest,
        }
        assistant = self.sessions.append_turn(session_id, role="assistant",
            text=response_text, linkage={
                "source_user_turn_id": str(user_turn["turn_id"]),
                "response_origin": "resident_developmental_cognition",
                "cognition_snapshot_id": str(getattr(result, "snapshot_id", "")),
                "cognition_snapshot_digest": str(getattr(result, "snapshot_digest", "")),
                "cognition_observation_id": observation_id,
                "cognition_observation_digest": observation_digest,
                "inference_receipt_id": receipt_id,
                "inference_receipt_digest": receipt_digest,
                "invocation_output_digest": invocation_output_digest,
                "response_digest": response_digest,
                "cognition_disposition": str(getattr(result, "disposition", "")),
                "cognition_evidence_ids": list(evidence_ids),
                "cognition_prior_record_ids": list(prior_record_ids),
                "cognition_history_record_ids": list(history_record_ids),
                "cognition_model_id": model_id,
                "cognition_model_artifact_digest": getattr(result, "model_artifact_digest", None),
                "self_model_projection_id": getattr(result, "self_model_projection_id", None),
                "self_model_projection_digest": getattr(result, "self_model_projection_digest", None),
                "epistemic_projection_id": getattr(result, "epistemic_projection_id", None),
                "epistemic_projection_digest": getattr(result, "epistemic_projection_digest", None),
                "assistant_output_lineage": lineage,
            })
        if self._avatar_output is not None:
            try:
                self._avatar_output.publish_response(
                    session_id=session_id, turn_id=str(assistant["turn_id"]),
                    text=response_text, output_digest=response_digest)
            except Exception as exc:
                LOGGER.warning("Avatar cognition response publication failed: %s",
                    getattr(exc, "code", type(exc).__name__))
        if self._speech_output is not None:
            try:
                self._speech_output.publish_response(session_id=session_id,
                    turn_id=str(assistant["turn_id"]), text=response_text,
                    output_digest=response_digest)
            except Exception as exc:
                LOGGER.warning("Local cognition response speech failed: %s",
                    type(exc).__name__)
        if on_content_chunk is not None:
            on_content_chunk(response_text)
        return ChatResponse(response=response_text, session_id=session_id,
            turn_id=str(assistant["turn_id"]),
            context={
                "response_origin": "resident_developmental_cognition",
                "cognition_disposition": str(getattr(result, "disposition", "")),
                "cognition_snapshot_id": getattr(result, "snapshot_id", None),
                "cognition_snapshot_digest": getattr(result, "snapshot_digest", None),
                "cognition_observation_id": observation_id,
                "cognition_observation_digest": observation_digest,
                "inference_receipt_id": receipt_id,
                "inference_receipt_digest": receipt_digest,
                "cognition_evidence_ids": list(evidence_ids),
                "cognition_prior_record_ids": list(prior_record_ids),
                "cognition_history_record_ids": list(history_record_ids),
                "cognition_model_id": model_id,
                "self_model_projection_id": getattr(result, "self_model_projection_id", None),
                "self_model_projection_digest": getattr(result, "self_model_projection_digest", None),
                "epistemic_projection_id": getattr(result, "epistemic_projection_id", None),
                "epistemic_projection_digest": getattr(result, "epistemic_projection_digest", None),
                "developmental_history_writeback_performed": False,
                "inference_timing": {"backend_metrics_status": "unavailable"},
            }, retention={"status": "not_requested"})

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
        if linkage.get("response_origin") == "transcript_recall":
            decision = linkage.get("policy_decision")
            payload = decision.get("payload") if isinstance(decision, Mapping) else None
            decision_digest = decision.get("digest") if isinstance(decision, Mapping) else None
            lineage = linkage.get("assistant_output_lineage")
            turns = session.get("turns", [])
            user_index = next((index for index, turn in enumerate(turns)
                if turn.get("turn_id") == user_turn_id and turn.get("role") == "user"), None)
            if (isinstance(payload, Mapping)
                    and payload.get("schema") == "sentientos.prior_user_turn_recall_decision:v1"):
                prior_turns = turns[:user_index] if isinstance(user_index, int) else []
                prior_users = [turn for turn in prior_turns if turn.get("role") == "user"]
                source_turn_id = linkage.get("recalled_user_turn_id")
                source = (prior_users[-1] if prior_users
                    and prior_users[-1].get("turn_id") == source_turn_id else None)
                source_text = str(source.get("text", "")) if isinstance(source, Mapping) else ""
                output_text = str(assistant.get("text", ""))
                output_digest = digest_payload({"text": output_text})
                valid_prior_user_record = (
                    isinstance(user_turn, Mapping)
                    and _is_direct_recent_user_turn_recall_request(str(user_turn.get("text", "")))
                    and user_turn.get("retention_state", "not_requested") == "not_requested"
                    and isinstance(source, Mapping)
                    and isinstance(source.get("text"), str)
                    and source.get("text_digest") == digest_payload({"text": source_text})
                    and payload.get("session_id") == session_id
                    and payload.get("source_user_turn_id") == user_turn_id
                    and payload.get("source_user_text_digest") == user_turn.get("text_digest")
                    and payload.get("recalled_user_turn_id") == source_turn_id
                    and payload.get("recalled_user_text_digest") == source.get("text_digest")
                    and payload.get("output_digest") == output_digest
                    and output_text == f"You asked: {chr(0x201c)}{source_text}{chr(0x201d)}"
                    and isinstance(decision_digest, str)
                    and decision_digest == digest_payload(dict(payload))
                    and linkage.get("transcript_recall_kind") == "prior_user_turn"
                    and linkage.get("recalled_user_text_digest") == source.get("text_digest")
                    and isinstance(lineage, Mapping)
                    and lineage.get("status") == "prior_user_transcript_recall_output"
                    and lineage.get("policy_decision_digest") == decision_digest
                    and lineage.get("transcript_text_digest") == output_digest
                )
                if not valid_prior_user_record:
                    raise ChatRequestStateError(
                        "chat_request_prior_user_recall_lineage_invalid")
                return ChatResponse(response=output_text, session_id=session_id,
                    turn_id=str(assistant["turn_id"]), context={
                        "conversation_snapshot_digest": linkage.get("context_snapshot_digest"),
                        "memory_snapshot_digest": linkage.get("memory_snapshot_digest"),
                        "memory_retrieval_posture": linkage.get("memory_retrieval_posture", "unknown"),
                        "legacy_sidecar_posture": linkage.get("legacy_sidecar_posture", "unknown_legacy"),
                        "memory_selection_posture": linkage.get("memory_selection_posture", "unknown_legacy"),
                        "omitted_memory_count": linkage.get("omitted_memory_count"),
                        "selected_turn_count": linkage.get("selected_turn_count", 0),
                        "selected_memory_count": linkage.get("selected_memory_count", 0),
                        "response_origin": "transcript_recall",
                        "recalled_user_turn_id": source_turn_id,
                        "policy_decision_digest": decision_digest,
                        "inference_timing": {
                            "backend_metrics_status": "not_applicable",
                            "reason_code": "prior_user_turn_recall_response",
                        },
                        "recovered_without_inference": True,
                    }, retention={"status": "not_requested"})
            if (isinstance(payload, Mapping)
                    and payload.get("schema") == "sentientos.transcript_quote_recall_decision:v1"):
                prior_turns = turns[:user_index] if isinstance(user_index, int) else []
                prior_users = [turn for turn in prior_turns if turn.get("role") == "user"]
                source_turn_id = linkage.get("recalled_user_turn_id")
                source_matches = [turn for turn in prior_users
                    if turn.get("turn_id") == source_turn_id]
                source = source_matches[0] if len(source_matches) == 1 else None
                output_text = str(assistant.get("text", ""))
                output_digest = digest_payload({"text": output_text})
                target = _direct_quoted_content_recall_target(
                    str(user_turn.get("text", ""))) if isinstance(user_turn, Mapping) else None
                quote_source_text = source.get("text") if isinstance(source, Mapping) else None
                quoted_value = (_quoted_content_from_user_turn(quote_source_text, target)
                    if isinstance(quote_source_text, str) and target is not None else None)
                valid_quote_record = (
                    isinstance(user_turn, Mapping)
                    and target is not None
                    and user_turn.get("retention_state", "not_requested") == "not_requested"
                    and isinstance(source, Mapping)
                    and isinstance(quote_source_text, str)
                    and source.get("text_digest") == digest_payload({"text": quote_source_text})
                    and payload.get("session_id") == session_id
                    and payload.get("source_user_turn_id") == user_turn_id
                    and payload.get("source_user_text_digest") == user_turn.get("text_digest")
                    and payload.get("recalled_user_turn_id") == source_turn_id
                    and payload.get("recalled_user_text_digest") == source.get("text_digest")
                    and isinstance(quoted_value, str)
                    and quoted_value == output_text
                    and payload.get("quoted_text_digest") == digest_payload({"text": output_text})
                    and payload.get("output_digest") == output_digest
                    and isinstance(decision_digest, str)
                    and decision_digest == digest_payload(dict(payload))
                    and linkage.get("transcript_recall_kind") == "quoted_content"
                    and linkage.get("recalled_quote_digest") == digest_payload({"text": output_text})
                    and isinstance(lineage, Mapping)
                    and lineage.get("status") == "transcript_quote_recall_output"
                    and lineage.get("policy_decision_digest") == decision_digest
                    and lineage.get("transcript_text_digest") == output_digest
                )
                if not valid_quote_record:
                    raise ChatRequestStateError(
                        "chat_request_transcript_quote_recall_lineage_invalid")
                return ChatResponse(response=output_text, session_id=session_id,
                    turn_id=str(assistant["turn_id"]), context={
                        "conversation_snapshot_digest": linkage.get("context_snapshot_digest"),
                        "memory_snapshot_digest": linkage.get("memory_snapshot_digest"),
                        "memory_retrieval_posture": linkage.get("memory_retrieval_posture", "unknown"),
                        "legacy_sidecar_posture": linkage.get("legacy_sidecar_posture", "unknown_legacy"),
                        "memory_selection_posture": linkage.get("memory_selection_posture", "unknown_legacy"),
                        "omitted_memory_count": linkage.get("omitted_memory_count"),
                        "selected_turn_count": linkage.get("selected_turn_count", 0),
                        "selected_memory_count": linkage.get("selected_memory_count", 0),
                        "response_origin": "transcript_recall",
                        "transcript_recall_kind": "quoted_content",
                        "recalled_user_turn_id": source_turn_id,
                        "policy_decision_digest": decision_digest,
                        "inference_timing": {
                            "backend_metrics_status": "not_applicable",
                            "reason_code": "transcript_quote_recall_response",
                        },
                        "recovered_without_inference": True,
                    }, retention={"status": "not_requested"})
            source_turn_id = linkage.get("source_assistant_turn_id")
            prior_turns = turns[:user_index] if isinstance(user_index, int) else []
            prior_assistants = [turn for turn in prior_turns
                if turn.get("role") == "assistant"]
            source_matches = [turn for turn in prior_assistants
                if turn.get("turn_id") == source_turn_id]
            recall_kind = linkage.get("transcript_recall_kind")
            prior_question_recall = recall_kind == "prior_assistant_question"
            source = (source_matches[0] if len(source_matches) == 1
                and (prior_question_recall or (prior_assistants
                    and prior_assistants[-1].get("turn_id") == source_turn_id))
                else None)
            output_text = str(assistant.get("text", ""))
            output_digest = digest_payload({"text": output_text})
            recall_request_text = str(user_turn.get("text", ""))
            recall_request_valid = (
                _is_prior_assistant_question_recall(recall_request_text)
                if prior_question_recall else
                _is_direct_recent_assistant_reply_request(recall_request_text))
            valid_record = (
                isinstance(payload, Mapping)
                and payload.get("schema") == "sentientos.transcript_recall_decision:v1"
                and payload.get("session_id") == session_id
                and payload.get("source_user_turn_id") == user_turn_id
                and payload.get("source_user_text_digest") == user_turn.get("text_digest")
                and isinstance(user_turn, Mapping)
                and recall_request_valid
                and (not prior_question_recall or
                    payload.get("transcript_recall_kind") == "prior_assistant_question")
                and user_turn.get("retention_state", "not_requested") == "not_requested"
                and isinstance(source, Mapping)
                and source.get("text_digest") == payload.get("source_assistant_text_digest")
                and source.get("text_digest") == linkage.get("source_assistant_text_digest")
                and source.get("text") == output_text
                and payload.get("source_assistant_turn_id") == source_turn_id
                and payload.get("output_digest") == output_digest
                and isinstance(decision_digest, str)
                and decision_digest == digest_payload(dict(payload))
                and isinstance(lineage, Mapping)
                and lineage.get("status") == "transcript_recall_output"
                and lineage.get("policy_decision_digest") == decision_digest
                and lineage.get("transcript_text_digest") == output_digest
            )
            if not valid_record:
                raise ChatRequestStateError("chat_request_transcript_recall_lineage_invalid")
            return ChatResponse(response=output_text, session_id=session_id,
                turn_id=str(assistant["turn_id"]), context={
                    "conversation_snapshot_digest": linkage.get("context_snapshot_digest"),
                    "memory_snapshot_digest": linkage.get("memory_snapshot_digest"),
                    "memory_retrieval_posture": linkage.get("memory_retrieval_posture", "unknown"),
                    "legacy_sidecar_posture": linkage.get("legacy_sidecar_posture", "unknown_legacy"),
                    "memory_selection_posture": linkage.get("memory_selection_posture", "unknown_legacy"),
                    "omitted_memory_count": linkage.get("omitted_memory_count"),
                    "selected_turn_count": linkage.get("selected_turn_count", 0),
                    "selected_memory_count": linkage.get("selected_memory_count", 0),
                    "response_origin": "transcript_recall",
                    "policy_decision_digest": decision_digest,
                    "inference_timing": {
                        "backend_metrics_status": "not_applicable",
                        "reason_code": "transcript_recall_response",
                    },
                    "recovered_without_inference": True,
                }, retention={"status": "not_requested"})
        if linkage.get("response_origin") == "deterministic_grounding_policy":
            decision = linkage.get("policy_decision")
            payload = decision.get("payload") if isinstance(decision, Mapping) else None
            decision_digest = decision.get("digest") if isinstance(decision, Mapping) else None
            lineage = linkage.get("assistant_output_lineage")
            source_digest = (user_turn.get("text_digest")
                if isinstance(user_turn, Mapping) else None)
            evidence = payload.get("evidence") if isinstance(payload, Mapping) else None
            names = evidence.get("configured_game_process_names") if isinstance(
                evidence, Mapping) else None
            recomputed_text = ""
            recomputed_correction = None
            if (isinstance(evidence, Mapping) and isinstance(names, list)
                    and isinstance(user_turn, Mapping)):
                recomputed_text, recomputed_correction = corrected_unobserved_game_status(
                    "", user_message=str(user_turn.get("text", "")),
                    verified_runtime_context={
                        "workload": {
                            "game_foreground": evidence.get("game_foreground"),
                            "configured_game_process_names": names,
                        },
                        "capabilities": {"screen_observation": {
                            "configured": evidence.get("screen_observation_configured"),
                        }},
                    },
                    screen_observation_provenance=None)
            valid_policy_record = (
                isinstance(payload, Mapping)
                and payload.get("schema") == "sentientos.deterministic_grounding_policy_decision:v1"
                and payload.get("session_id") == session_id
                and payload.get("source_user_turn_id") == user_turn_id
                and payload.get("source_user_text_digest") == source_digest
                and isinstance(user_turn, Mapping)
                and is_direct_screen_activity_question(str(user_turn.get("text", "")))
                and payload.get("policy_id") == CURRENT_GAME_STATUS_POLICY_ID
                and payload.get("reason_code") in {
                    "foreground_only_screen_observation_unconfigured",
                    "foreground_only_no_screen_observation",
                }
                and isinstance(evidence, Mapping)
                and evidence.get("observation_status") == "available"
                and evidence.get("game_foreground") is True
                and type(evidence.get("screen_observation_configured")) is bool
                and isinstance(names, list) and bool(names)
                and all(isinstance(name, str) and name for name in names)
                and isinstance(decision_digest, str)
                and decision_digest == digest_payload(dict(payload))
                and payload.get("output_digest")
                    == digest_payload({"text": str(assistant.get("text", ""))})
                and isinstance(recomputed_correction, Mapping)
                and recomputed_correction.get("policy_id") == payload.get("policy_id")
                and recomputed_correction.get("reason_code") == payload.get("reason_code")
                and str(assistant.get("text", "")) == recomputed_text
                and isinstance(lineage, Mapping)
                and lineage.get("status") == "deterministic_policy_output"
                and lineage.get("policy_decision_digest") == decision_digest
                and lineage.get("transcript_text_digest")
                    == digest_payload({"text": str(assistant.get("text", ""))})
            )
            if not valid_policy_record:
                raise ChatRequestStateError("chat_request_policy_response_lineage_invalid")
            return ChatResponse(
                response=str(assistant["text"]), session_id=session_id,
                turn_id=str(assistant["turn_id"]),
                context={
                    "conversation_snapshot_digest": linkage.get("context_snapshot_digest"),
                    "memory_snapshot_digest": linkage.get("memory_snapshot_digest"),
                    "memory_retrieval_posture": linkage.get("memory_retrieval_posture", "unknown"),
                    "legacy_sidecar_posture": linkage.get("legacy_sidecar_posture", "unknown_legacy"),
                    "memory_selection_posture": linkage.get("memory_selection_posture", "unknown_legacy"),
                    "omitted_memory_count": linkage.get("omitted_memory_count"),
                    "selected_turn_count": linkage.get("selected_turn_count", 0),
                    "selected_memory_count": linkage.get("selected_memory_count", 0),
                    "response_origin": "deterministic_grounding_policy",
                    "policy_decision_digest": decision_digest,
                    "inference_timing": {
                        "backend_metrics_status": "not_applicable",
                        "reason_code": "deterministic_policy_response",
                    },
                    "recovered_without_inference": True,
                },
                retention={"status": "not_requested"},
            )
        if linkage.get("response_origin") == "resident_developmental_cognition":
            bridge_verifier = getattr(self._resident_cognition_bridge,
                "verify_committed_response", None)
            request_id = f"{session_id}:{user_turn_id}"
            if (not callable(bridge_verifier)
                    or not bridge_verifier(linkage=linkage,
                        response_text=str(assistant.get("text", "")),
                        request_id=request_id)):
                raise ChatRequestStateError(
                    "chat_request_cognition_response_lineage_invalid")
            return ChatResponse(response=str(assistant["text"]),
                session_id=session_id, turn_id=str(assistant["turn_id"]),
                context={
                    "response_origin": "resident_developmental_cognition",
                    "cognition_disposition": linkage.get("cognition_disposition"),
                    "cognition_snapshot_id": linkage.get("cognition_snapshot_id"),
                    "cognition_snapshot_digest": linkage.get("cognition_snapshot_digest"),
                    "cognition_observation_id": linkage.get("cognition_observation_id"),
                    "cognition_observation_digest": linkage.get("cognition_observation_digest"),
                    "inference_receipt_id": linkage.get("inference_receipt_id"),
                    "inference_receipt_digest": linkage.get("inference_receipt_digest"),
                    "cognition_evidence_ids": linkage.get("cognition_evidence_ids", []),
                    "cognition_prior_record_ids": linkage.get("cognition_prior_record_ids", []),
                    "cognition_history_record_ids": linkage.get("cognition_history_record_ids", []),
                    "cognition_model_id": linkage.get("cognition_model_id"),
                    "self_model_projection_id": linkage.get("self_model_projection_id"),
                    "self_model_projection_digest": linkage.get("self_model_projection_digest"),
                    "epistemic_projection_id": linkage.get("epistemic_projection_id"),
                    "epistemic_projection_digest": linkage.get("epistemic_projection_digest"),
                    "developmental_history_writeback_performed": False,
                    "recovered_without_inference": True,
                }, retention={"status": "not_requested"})
        verifier = getattr(self._inference, "verify_stored_chat_invocation", None)
        verified_output_lineage: Mapping[str, Any] | None = None
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
            observed_output_lineage = verified.get("assistant_output_lineage")
            if isinstance(observed_output_lineage, Mapping):
                verified_output_lineage = observed_output_lineage
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
                    or not _stored_output_lineage_matches(
                        linkage.get("assistant_output_lineage"),
                        verified.get("assistant_output_lineage"))):
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
        response_text = str(assistant["text"])
        stored_output_lineage = linkage.get("assistant_output_lineage")
        diagnostic_lineage = (verified_output_lineage
            if verified_output_lineage is not None else
            stored_output_lineage if isinstance(stored_output_lineage, Mapping) else None)
        return ChatResponse(
            response=response_text, session_id=session_id,
            turn_id=str(assistant["turn_id"]),
            response_diagnostics=_chat_response_diagnostics(
                response_text, diagnostic_lineage),
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
                "response_origin": linkage.get("response_origin", "model_generated"),
            },
            retention=retention,
        )

    def chat(self, message: str, *, session_id: str | None = None, retain: bool = False,
             request_id: str | None = None, observe_screen: bool = False,
             on_content_chunk: Callable[[str], None] | None = None) -> ChatResponse:
        if session_id is None:
            return self._chat_unlocked(message, session_id=None, retain=retain,
                request_id=request_id, observe_screen=observe_screen,
                on_content_chunk=on_content_chunk)
        try:
            with self.sessions.serialize_chat_requests(session_id):
                return self._chat_unlocked(message, session_id=session_id,
                    retain=retain, request_id=request_id, observe_screen=observe_screen,
                    on_content_chunk=on_content_chunk)
        except ConversationChatLockTimeout as exc:
            raise ChatRequestStateError("chat_session_request_lock_timeout") from exc

    def _chat_unlocked(self, message: str, *, session_id: str | None = None,
                       retain: bool = False, request_id: str | None = None,
                       observe_screen: bool = False,
                       on_content_chunk: Callable[[str], None] | None = None) -> ChatResponse:
        turn_started_ns = time.monotonic_ns()
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
            observer = self._screen_observer
            question_observer = getattr(type(observer), "observe_question", None)
            screen_observation = (
                question_observer(observer, message)
                if callable(question_observer) else observer())
            if not isinstance(screen_observation, Mapping):
                raise RuntimeError("screen_observation_unavailable")
            screen_text = screen_observation.get("text")
            screen_text_status = screen_observation.get("text_status", "available")
            capture_digest = screen_observation.get("capture_digest")
            captured_at = screen_observation.get("captured_at")
            text_change_kind = screen_observation.get("text_change_kind")
            previous_text_digest = screen_observation.get("previous_text_digest")
            current_text_digest = (
                hashlib.sha256(screen_text.encode("utf-8")).hexdigest()
                if isinstance(screen_text, str) and len(screen_text) <= 1200 else None)
            change_lineage_valid = (
                (text_change_kind == "initial" and previous_text_digest is None)
                or (text_change_kind == "unchanged"
                    and isinstance(previous_text_digest, str)
                    and re.fullmatch(r"[0-9a-f]{64}", previous_text_digest) is not None
                    and previous_text_digest == current_text_digest)
                or (text_change_kind == "changed"
                    and isinstance(previous_text_digest, str)
                    and re.fullmatch(r"[0-9a-f]{64}", previous_text_digest) is not None
                    and previous_text_digest != current_text_digest))
            component_statuses = screen_observation.get("component_statuses")
            if component_statuses is not None and (
                    not isinstance(component_statuses, Mapping)
                    or not component_statuses
                    or set(component_statuses) - {"ocr", "vision"}
                    or any(not isinstance(status, str)
                           or status not in {"available", "unavailable", "no_readable_text"}
                           for status in component_statuses.values())
                    or (screen_observation.get("backend") == "tesseract+local_vision"
                        and set(component_statuses) != {"ocr", "vision"})):
                raise RuntimeError("screen_observation_component_status_invalid")
            component_failures = screen_observation.get("component_failure_codes")
            if component_failures is not None and (
                    not isinstance(component_failures, Mapping)
                    or not component_failures
                    or not isinstance(component_statuses, Mapping)
                    or set(component_failures) - {"ocr", "vision"}
                    or any(not isinstance(code, str)
                           or re.fullmatch(r"(?:screen|game_screen)_[a-z0-9_]{1,80}", code) is None
                           or component_statuses.get(component) != "unavailable"
                           for component, code in component_failures.items())):
                raise RuntimeError("screen_observation_component_failure_invalid")
            visual_kind = screen_observation.get("visual_change_kind", "unknown")
            visual_score = screen_observation.get("visual_change_score")
            visual_valid = (
                visual_kind in ("initial", "changed", "stable", "unknown")
                and (visual_score is None or (
                    isinstance(visual_score, (int, float))
                    and not isinstance(visual_score, bool)
                    and math.isfinite(float(visual_score))
                    and 0.0 <= float(visual_score) <= 1.0)))
            if (screen_observation.get("modality") != "screen"
                    or not visual_valid
                    or not change_lineage_valid
                    or screen_observation.get("raw_frame_retained") is not False
                    or not isinstance(screen_text, str) or len(screen_text) > 1200
                    or screen_text_status not in {"available", "no_readable_text"}
                    or (screen_text_status == "available" and not screen_text.strip())
                    or (screen_text_status == "no_readable_text" and screen_text != "")
                    or not isinstance(captured_at, str) or len(captured_at) > 64
                    or screen_observation.get("capture_scope")
                        != "allowlisted_foreground_game_client_area"
                    or not isinstance(capture_digest, str) or len(capture_digest) != 64
                    or any(character not in "0123456789abcdef" for character in capture_digest)):
                raise RuntimeError("screen_observation_contract_invalid")
            text_delta = screen_observation.get("text_delta")
            if text_delta is not None:
                try:
                    text_delta = validate_ocr_text_line_delta(
                        text_delta, current_text=screen_text)
                except ValueError as exc:
                    raise RuntimeError("screen_observation_delta_contract_invalid") from exc
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
        bridge = self._resident_cognition_bridge
        should_route_to_cognition = (bridge is not None and not retain)
        can_handle = getattr(bridge, "can_handle", None)
        if should_route_to_cognition and callable(can_handle):
            try:
                should_route_to_cognition = can_handle() is True
            except Exception:
                should_route_to_cognition = False
        if should_route_to_cognition:
            try:
                return self._complete_resident_cognition_response(
                    session_id=session["session_id"], user_turn=user_turn,
                    question=message, screen_observation=screen_observation,
                    on_content_chunk=on_content_chunk)
            except (CognitionEvidenceUnavailable, CognitionWorkloadUnavailable):
                # Keep ordinary chat available without current evidence, or if
                # a game becomes active after the readiness check.
                pass

        prior_assistant = next((turn for turn in reversed(session.get("turns", ()))
            if turn.get("role") == "assistant"
            and isinstance(turn.get("linkage"), Mapping)
            and isinstance(turn["linkage"].get("invocation_receipt_id"), str)), None)
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
                    output_lineage_matches = _stored_output_lineage_matches(
                        stored_output_lineage, observed_output_lineage)
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
            # Start with room for recent conversation, then trim only as needed
            # to fit the complete trusted prompt under the gaming input ceiling.
            history_budget = min(history_budget, 3000)
        recent_session_recall = _is_recent_session_recall_request(message)
        earliest_session_recall = (
            recent_session_recall and _is_earliest_session_recall_request(message)
        )
        social_checkin = _is_social_checkin_request(message)
        social_checkin_continuation = (
            social_checkin and _is_social_checkin_continuation(message))
        current_runtime_question = _is_current_runtime_context_question(message)
        self_contained_echo = _is_self_contained_text_echo_request(message)
        history_roles: tuple[str, ...] | None
        history_turn_limit: int | None = None
        history_relevance_query: str | None = None
        if recent_session_recall:
            asks_for_assistant_reply = any(marker in " ".join(
                re.sub(r"[^a-z0-9]+", " ", message.casefold()).split())
                for marker in ("what did you answer", "what did you say",
                    "what did you just answer", "what did you just say",
                    "what did you just reply", "what did you just tell me",
                    "what did you tell me", "what was your answer",
                    "what was your response", "what did you reply",
                    "what was the thing you said", "what was the thing you told me"))
            asks_for_prior_assistant_question = (
                _is_prior_assistant_question_recall(message))
            history_roles = ("user", "assistant") if (
                asks_for_assistant_reply or asks_for_prior_assistant_question
            ) else ("user",)
            if asks_for_assistant_reply:
                history_turn_limit = 2
            elif asks_for_prior_assistant_question:
                # Keep a small recent window so generic prior-question recalls
                # without lexical anchors can resolve to the latest verified
                # assistant question. Specific references are ranked below.
                history_turn_limit = 8
            else:
                recall_terms = transcript_recall_terms(message)
                if not earliest_session_recall and recall_terms:
                    # Select relevant user turns, then allow explicit reminders to
                    # choose the latest matching statement from that small set.
                    history_relevance_query = message
                    history_turn_limit = (
                        1 if _is_recent_user_statement_reminder(message) else 3)
                else:
                    history_turn_limit = 1
        elif social_checkin_continuation:
            # Keep just the immediately preceding exchange when a casual follow-up
            # explicitly refers to it; do not pull unrelated earlier conversation.
            history_roles = ("user", "assistant")
            history_turn_limit = 2
        elif social_checkin or self_contained_echo or current_runtime_question:
            # Initial check-ins and self-contained requests should not inherit
            # unrelated transcript context and mistake it for current evidence.
            history_roles = ()
        else:
            history_roles = None
        prefer_recent_relevant = (
            recent_session_recall and _is_recent_user_statement_reminder(message)
            and history_roles == ("user",) and history_relevance_query is not None)
        history = self.sessions.reconstruct(session["session_id"], budget_chars=history_budget,
            exclude_turn_id=user_turn["turn_id"], include_roles=history_roles,
            max_turns=history_turn_limit, oldest_first=earliest_session_recall,
            relevance_query=history_relevance_query,
            prefer_recent_relevant=prefer_recent_relevant)
        # Exact recall, casual check-ins, and live runtime questions rely on the
        # relevant transcript or verified runtime facts. Lexical retrieval can
        # over-weight old prompts (for example, prior screen-visibility questions).
        memory_query = ("" if recent_session_recall or social_checkin
                        or current_runtime_question or self_contained_echo else message)
        memory_budget = self.memory_budget_chars
        memory = self.memories.retrieve(memory_query, budget_chars=memory_budget)
        # Keep check-ins independent of unrelated transcript and retrieved
        # memories while grounding them in verified runtime state. Explicit
        # follow-ups may include only the immediately preceding exchange.
        runtime_context = self._verified_runtime_context(
            identity=identity_payload, history=history, memory=memory,
            session_id=session["session_id"],
            screen_observation=None if social_checkin else screen_observation)
        if not retain and _is_prior_assistant_question_recall(message):
            prior_question = _prior_assistant_question_turn(history, message)
            if prior_question is not None:
                return self._complete_transcript_recall_response(
                    session_id=session["session_id"], user_turn=user_turn,
                    source_assistant_turn=prior_question, history=history,
                    memory=memory, on_content_chunk=on_content_chunk,
                    transcript_recall_kind="prior_assistant_question")
        if not retain and _is_direct_recent_assistant_reply_request(message):
            prior_assistant_turn = next((turn for turn in reversed(history.turns)
                if turn.get("role") == "assistant"
                and isinstance(turn.get("text"), str)
                and isinstance(turn.get("text_digest"), str)
                and turn.get("text_digest") == digest_payload({"text": turn["text"]})), None)
            if prior_assistant_turn is not None:
                return self._complete_transcript_recall_response(
                    session_id=session["session_id"], user_turn=user_turn,
                    source_assistant_turn=prior_assistant_turn, history=history,
                    memory=memory, on_content_chunk=on_content_chunk)
        quoted_content_target = _direct_quoted_content_recall_target(message)
        if not retain and quoted_content_target is not None:
            quoted_source = _find_verified_quoted_user_turn(history, quoted_content_target)
            if quoted_source is not None:
                source_user_turn, quoted_value = quoted_source
                return self._complete_quoted_content_recall_response(
                    session_id=session["session_id"], user_turn=user_turn,
                    source_user_turn=source_user_turn, quoted_value=quoted_value,
                    history=history, memory=memory, on_content_chunk=on_content_chunk)
        if not retain and _is_direct_recent_user_turn_recall_request(message):
            prior_user_turn = next((turn for turn in reversed(history.turns)
                if turn.get("role") == "user"
                and isinstance(turn.get("text"), str)
                and isinstance(turn.get("text_digest"), str)
                and turn.get("text_digest") == digest_payload({"text": turn["text"]})), None)
            if prior_user_turn is not None:
                return self._complete_prior_user_turn_recall_response(
                    session_id=session["session_id"], user_turn=user_turn,
                    source_user_turn=prior_user_turn, history=history,
                    memory=memory, on_content_chunk=on_content_chunk)
        if (isinstance(self._inference, DevelopmentLocalChatInference) and not retain
                and is_direct_screen_configuration_status_question(message)):
            capability_text, capability_correction = corrected_screen_capability_output(
                "", user_message=message,
                screen_observation_configured=self.screen_observation_configured(),
                screen_observation_provenance=screen_observation)
            if (capability_correction is not None
                    and capability_correction.get("policy_id") == SCREEN_CAPABILITY_POLICY_ID):
                provenance = _bounded_screen_observation_provenance(
                    screen_observation)
                return self._complete_deterministic_grounding_response(
                    session_id=session["session_id"], user_turn=user_turn,
                    response_text=capability_text, correction=capability_correction,
                    runtime_context=runtime_context, history=history, memory=memory,
                    on_content_chunk=on_content_chunk,
                    screen_observation_provenance=provenance)
        direct_screen_activity_question = is_direct_screen_activity_question(message)
        visual_fallback, visual_correction = visual_observation_unavailable_correction(
            message, screen_observation)
        if (isinstance(self._inference, DevelopmentLocalChatInference)
                and not retain and visual_correction is not None):
            return self._complete_deterministic_grounding_response(
                session_id=session["session_id"], user_turn=user_turn,
                response_text=visual_fallback, correction=visual_correction,
                runtime_context=runtime_context, history=history, memory=memory,
                on_content_chunk=on_content_chunk,
                screen_observation_provenance=(
                    _bounded_screen_observation_provenance(screen_observation)))
        screen_observation_unusable = not screen_observation_has_usable_content(
            screen_observation)
        if (isinstance(self._inference, DevelopmentLocalChatInference)
                and direct_screen_activity_question
                and not retain and screen_observation_unusable):
            policy_text, policy_correction = corrected_unobserved_game_status(
                "", user_message=message, verified_runtime_context=runtime_context,
                screen_observation_provenance=(
                    _bounded_screen_observation_provenance(screen_observation)))
            allowed_deterministic_grounding = {
                CURRENT_GAME_STATUS_POLICY_ID: {
                    "foreground_only_screen_observation_unconfigured",
                    "foreground_only_no_screen_observation",
                    "verified_workload_context_screen_unavailable",
                    "screen_capture_no_readable_text",
                    "screen_capture_perception_unavailable",
                },
                USER_REPORT_EVIDENCE_POLICY_ID: {
                    "user_report_distinguished_from_current_observation",
                },
            }
            policy_id = (policy_correction.get("policy_id")
                         if policy_correction is not None else None)
            reason_code = (policy_correction.get("reason_code")
                           if policy_correction is not None else None)
            allowed_reasons = (allowed_deterministic_grounding.get(policy_id)
                               if policy_id is not None else None)
            if (policy_correction is not None and reason_code is not None
                    and allowed_reasons is not None
                    and reason_code in allowed_reasons):
                return self._complete_deterministic_grounding_response(
                    session_id=session["session_id"], user_turn=user_turn,
                    response_text=policy_text, correction=policy_correction,
                    runtime_context=runtime_context, history=history, memory=memory,
                    on_content_chunk=on_content_chunk,
                    screen_observation_provenance=(
                        _bounded_screen_observation_provenance(screen_observation)))
        workload_context = runtime_context.get("workload")
        gaming_resource_status = (workload_context.get("gaming_resource_status")
            if isinstance(workload_context, Mapping) else None)
        if (isinstance(self._inference, DevelopmentLocalChatInference)
                and isinstance(workload_context, Mapping)
                and workload_context.get("effective_mode") == "gaming"
                and isinstance(gaming_resource_status, Mapping)
                and gaming_resource_status.get("admission_status") == "deferred"):
            reason = gaming_resource_status.get("reason_code")
            if reason == "vram_pressure":
                response_text = (
                    "I’m pausing model inference while the game is active because GPU memory "
                    "pressure is high. Your message is saved, but I haven’t queued a model reply. "
                    "SentientOS is still monitoring the system; ask again when memory headroom "
                    "recovers."
                )
            elif reason == "vram_telemetry_stale":
                response_text = (
                    "I’m pausing model inference while the game is active because the GPU "
                    "memory reading is stale. Your message is saved, but I haven’t queued a model "
                    "reply. SentientOS is still monitoring the system; ask again after a fresh "
                    "resource reading arrives."
                )
            else:
                response_text = (
                    "I’m pausing model inference while the game is active because GPU memory "
                    "telemetry is unavailable. Your message is saved, but I haven’t queued a model "
                    "reply. SentientOS is still monitoring the system; ask again when a safe "
                    "resource reading is available."
                )
            correction = {
                "policy_id": "gaming_resource_pressure_policy:v1",
                "reason_code": (reason if reason in {
                    "vram_pressure", "vram_telemetry_unavailable",
                    "vram_telemetry_not_observed", "vram_telemetry_stale"}
                    else "vram_telemetry_unavailable"),
            }
            return self._complete_deterministic_grounding_response(
                session_id=session["session_id"], user_turn=user_turn,
                response_text=response_text, correction=correction,
                runtime_context=runtime_context, history=history, memory=memory,
                on_content_chunk=on_content_chunk)
        prompt = assemble_local_chat_context(history=history, memory_snapshot=memory,
            current_message=message,
            runtime_context=runtime_context,
            verified_prior_runtime_lineage=predecessor_runtime_lineage,
            screen_observation=screen_observation,
            compact_history=gaming_development_turn,
            compact_screen_context=gaming_development_turn and screen_observation is not None,
            recent_session_recall=recent_session_recall,
            earliest_session_recall=earliest_session_recall)
        if gaming_development_turn:
            effective_prompt = GamingWorkloadPolicy.apply_chat_response_style(
                prompt, "gaming", social_checkin=social_checkin,
                screen_observation=screen_observation is not None)
            gaming_input_limit = (
                GamingWorkloadPolicy.GAMING_MAX_RECALL_INPUT_CHARS
                if recent_session_recall
                else GamingWorkloadPolicy.GAMING_MAX_INPUT_CHARS)
            while len(effective_prompt) > gaming_input_limit:
                overflow = len(effective_prompt) - gaming_input_limit
                # Retrieved memory is supplemental to the active transcript. Drop
                # it first so a long-running conversation keeps its recent turns.
                if memory_budget > 0:
                    memory_budget = max(0, memory_budget - overflow)
                    memory = self.memories.retrieve(
                        memory_query, budget_chars=memory_budget)
                elif history_budget > 0:
                    next_budget = max(0, history_budget - overflow)
                    if next_budget == history_budget:
                        next_budget = 0
                    history_budget = next_budget
                    history = self.sessions.reconstruct(
                        session["session_id"], budget_chars=history_budget,
                        exclude_turn_id=user_turn["turn_id"], include_roles=history_roles,
                        max_turns=history_turn_limit, oldest_first=earliest_session_recall,
                        relevance_query=history_relevance_query,
                        prefer_recent_relevant=prefer_recent_relevant)
                else:
                    raise ChatInputBudgetError("chat_input_exceeds_gaming_budget")
                runtime_context = self._verified_runtime_context(
                    identity=identity_payload, history=history, memory=memory,
                    session_id=session["session_id"],
                    screen_observation=None if social_checkin else screen_observation)
                prompt = assemble_local_chat_context(history=history,
                    memory_snapshot=memory, current_message=message,
                    runtime_context=runtime_context,
                    verified_prior_runtime_lineage=predecessor_runtime_lineage,
                    screen_observation=screen_observation,
                    compact_history=True,
                    compact_screen_context=screen_observation is not None,
                    recent_session_recall=recent_session_recall,
                    earliest_session_recall=earliest_session_recall)
                effective_prompt = GamingWorkloadPolicy.apply_chat_response_style(
                    prompt, "gaming", social_checkin=social_checkin,
                    screen_observation=screen_observation is not None)
        linkage = {"session_id": session["session_id"], "user_turn_id": user_turn["turn_id"],
                   "chat_response_style": (
                       "screen_observation" if screen_observation is not None else
                       "social_checkin" if social_checkin else "default"),
                   "recent_session_recall": recent_session_recall,
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
                "text_status": screen_observation.get("text_status", "available"),
                "capture_scope": "allowlisted_foreground_game_client_area",
                "captured_at": screen_observation["captured_at"],
                "text_change_kind": screen_observation["text_change_kind"],
                "raw_frame_retained": False,
            }
            observation_backend = screen_observation.get("backend")
            if isinstance(observation_backend, str) and 1 <= len(observation_backend) <= 64:
                screen_provenance["backend"] = observation_backend
            component_statuses = screen_observation.get("component_statuses")
            if isinstance(component_statuses, Mapping):
                screen_provenance["component_statuses"] = dict(component_statuses)
            component_failures = screen_observation.get("component_failure_codes")
            if isinstance(component_failures, Mapping) and component_failures:
                screen_provenance["component_failure_codes"] = dict(component_failures)
            if visual_kind in ("initial", "changed", "stable", "unknown"):
                screen_provenance["visual_change_kind"] = visual_kind
                screen_provenance["visual_change_score"] = visual_score
            previous_text_digest = screen_observation.get("previous_text_digest")
            if (isinstance(previous_text_digest, str)
                    and re.fullmatch(r"[0-9a-f]{64}", previous_text_digest) is not None):
                screen_provenance["previous_text_digest"] = previous_text_digest
            if isinstance(text_delta, Mapping):
                screen_provenance["text_delta"] = {
                    "previous_text_digest": text_delta["previous_text_digest"],
                    "current_text_digest": text_delta["current_text_digest"],
                    "added_line_digests": [hashlib.sha256(line.encode("utf-8")).hexdigest()
                        for line in text_delta["added_lines"]],
                    "removed_line_digests": [hashlib.sha256(line.encode("utf-8")).hexdigest()
                        for line in text_delta["removed_lines"]],
                    "truncated": text_delta["truncated"],
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
                    "sequence", "created_at", "payload_digest", "signed_envelope_digest",
                }
                message_id = bridge_provenance.get("message_id")
                payload_digest = bridge_provenance.get("payload_digest")
                signed_envelope_digest = bridge_provenance.get("signed_envelope_digest")
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
                        and isinstance(signed_envelope_digest, str)
                        and len(signed_envelope_digest) == 64
                        and all(character in "0123456789abcdef"
                                for character in signed_envelope_digest)
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
        invocation_correlation_id = f"chat:{session['session_id']}:{user_turn['turn_id']}"
        invocation_budget = LocalModelInvocationBudget(max_input_chars=8000)
        streamed_model_chunks: list[str] = []
        inference_started_ns = time.monotonic_ns()
        if on_content_chunk is None:
            receipt = self._inference.generate(
                prompt=prompt,
                caller="chat_service",
                correlation_id=invocation_correlation_id,
                budget=invocation_budget,
                caller_linkage=linkage,
            )
        else:
            stream_generator = getattr(self._inference, "generate_streaming", None)
            if not callable(stream_generator):
                raise RuntimeError("chat_streaming_not_supported")
            receipt = stream_generator(
                prompt=prompt,
                caller="chat_service",
                correlation_id=invocation_correlation_id,
                budget=invocation_budget,
                caller_linkage=linkage,
                on_content_chunk=streamed_model_chunks.append,
            )
        inference_completed_ns = time.monotonic_ns()
        accepted_statuses = {"admitted_completed"}
        if isinstance(self._inference, DevelopmentLocalChatInference):
            accepted_statuses.add("admitted_simulation")
        if receipt.status not in accepted_statuses or not receipt.output_text:
            raise RuntimeError(f"governed_inference_not_completed:{receipt.status}")
        if not isinstance(receipt.output_digest, str):
            raise RuntimeError("invocation_output_digest_missing")
        if (not receipt.output_truncated
                and digest_payload({"output": receipt.output_text}) != receipt.output_digest):
            raise RuntimeError("invocation_output_transcript_mismatch")
        request_linkage = receipt.request.get("linkage", {})
        upstream_evidence = receipt.request.get("upstream_evidence", {})
        current_lifetime = (upstream_evidence.get("current_serving_lifetime")
            if isinstance(upstream_evidence, Mapping) else None)
        observed_workload_mode = (current_lifetime.get("workload_mode")
            if isinstance(current_lifetime, Mapping) else None)
        if observed_workload_mode not in {"normal", "gaming"}:
            mode_getter = getattr(self._inference, "current_workload_mode", None)
            observed_workload_mode = mode_getter() if callable(mode_getter) else "normal"
        response_text = receipt.output_text
        grounding_started_ns = time.monotonic_ns()
        grounding_correction: Mapping[str, str] | None = None
        if not receipt.output_truncated:
            invocation_screen_provenance = (request_linkage.get("screen_observation_provenance")
                if isinstance(request_linkage, Mapping) else None)
            if is_verified_current_game_context_question(message):
                response_text, grounding_correction = corrected_unobserved_game_status(
                    receipt.output_text, user_message=message,
                    verified_runtime_context=runtime_context,
                    screen_observation_provenance=invocation_screen_provenance)
            if grounding_correction is None:
                response_text, grounding_correction = corrected_screen_capability_output(
                    receipt.output_text, user_message=message,
                    screen_observation_configured=self.screen_observation_configured(),
                    screen_observation_provenance=invocation_screen_provenance)
            if grounding_correction is None:
                response_text, grounding_correction = corrected_system_identity_output(
                    receipt.output_text, user_message=message,
                    verified_runtime_context=runtime_context)
            if grounding_correction is None:
                source_context_parts = [
                    turn.get("text", "") for turn in history.turns
                    if isinstance(turn.get("text"), str)
                ]
                source_context_parts.extend(
                    record.get("text", "") for record in memory.get("memories", [])
                    if isinstance(record, Mapping)
                    and isinstance(record.get("text"), str)
                )
                response_text, grounding_correction = corrected_unprovided_source_reference(
                    receipt.output_text, user_message=message,
                    available_context="\n".join(source_context_parts))
            if grounding_correction is None:
                response_text, grounding_correction = corrected_unobserved_game_status(
                    receipt.output_text, user_message=message,
                    verified_runtime_context=runtime_context,
                    screen_observation_provenance=invocation_screen_provenance)
            if grounding_correction is None:
                response_text, grounding_correction = corrected_stale_screen_failure_claim(
                    response_text,
                    screen_observation_provenance=invocation_screen_provenance)
            if grounding_correction is None:
                response_text, grounding_correction = corrected_nonresponsive_gaming_next_step(
                    receipt.output_text, user_message=message,
                    workload_mode=str(observed_workload_mode or "normal"),
                    screen_observation_provenance=invocation_screen_provenance)
            if grounding_correction is None:
                response_text, grounding_correction = corrected_social_instruction_echo(
                    receipt.output_text, user_message=message)
            if grounding_correction is None:
                response_text, grounding_correction = corrected_multiple_social_questions(
                    receipt.output_text, user_message=message,
                    workload_mode=str(observed_workload_mode or "normal"),
                    social_checkin=social_checkin)
            if grounding_correction is None:
                response_text, grounding_correction = corrected_nonverbal_gaming_output(
                    receipt.output_text, user_message=message,
                    workload_mode=str(observed_workload_mode or "normal"),
                    social_checkin=social_checkin,
                    screen_observation=screen_observation)
            if grounding_correction is None:
                response_text, grounding_correction = corrected_gaming_output(
                    receipt.output_text, workload_mode=str(observed_workload_mode or "normal"),
                    screen_observation_provenance=invocation_screen_provenance,
                    social_checkin=social_checkin)
        grounding_completed_ns = time.monotonic_ns()
        transcript_output_digest = digest_payload({"text": response_text})
        if grounding_correction is None:
            assistant_output_lineage = {
                "status": ("exact_invocation_output_match" if not receipt.output_truncated
                           else "truncated_transcript_original_output_relation_unknown"),
                "invocation_output_digest": receipt.output_digest,
                "transcript_text_digest": transcript_output_digest,
                "output_truncated": receipt.output_truncated,
            }
            response_origin = "model_generated"
        else:
            assistant_output_lineage = corrected_output_lineage(
                invocation_output_digest=receipt.output_digest, text=response_text,
                output_truncated=receipt.output_truncated,
                policy_id=grounding_correction["policy_id"],
                reason_code=grounding_correction["reason_code"])
            response_origin = "grounding_policy_fallback"
        assistant_output_lineage.update({
            "invocation_output_text_sha256": hashlib.sha256(
                receipt.output_text.encode("utf-8")).hexdigest(),
            "transcript_text_sha256": hashlib.sha256(
                response_text.encode("utf-8")).hexdigest(),
        })
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
                    assistant_text=response_text,
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
        if on_content_chunk is not None:
            _publish_grounded_model_stream(
                on_content_chunk, streamed_model_chunks,
                generated_text=receipt.output_text,
                response_text=response_text,
                response_origin=response_origin,
            )
        assistant = self.sessions.append_turn(session["session_id"], role="assistant", text=response_text,
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
                     "response_origin": response_origin,
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
                    "text": response_text,
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
                LOGGER.warning(
                    "Avatar response publication failed: code=%s phase=%s "
                    "failure_type=%s errno=%s",
                    getattr(exc, "code", type(exc).__name__),
                    getattr(exc, "failure_phase", None),
                    getattr(exc, "failure_type", type(exc).__name__),
                    getattr(exc, "failure_errno", None),
                )
        if self._speech_output is not None:
            try:
                self._speech_output.publish_response(
                    session_id=session["session_id"], turn_id=str(assistant["turn_id"]),
                    text=response_text, output_digest=transcript_output_digest)
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
        return ChatResponse(response=response_text, session_id=session["session_id"], turn_id=assistant["turn_id"],
                            response_diagnostics=_chat_response_diagnostics(
                                response_text, assistant_output_lineage),
                            context={"conversation_snapshot_digest": history.snapshot_digest,
                                     "memory_snapshot_digest": memory["snapshot_digest"],
                                     "memory_retrieval_posture": memory["retrieval_posture"],
                                     "legacy_sidecar_posture": memory.get("legacy_sidecar_posture", "unknown_legacy"),
                                     "memory_selection_posture": memory.get("selection_posture", "unknown_legacy"),
                                     "omitted_memory_count": memory.get("omitted_memory_count"),
                                     "active_model_identity_digest": serving_identity_digest,
                                     "loaded_model_identity_digest": loaded_identity_digest,
                                     "model_identity_continuity_posture": continuity_posture,
                                     "chat_timing": {
                                         "pre_inference_setup_duration_ns": max(
                                             0, inference_started_ns - turn_started_ns),
                                         "model_call_wall_duration_ns": max(
                                             0, inference_completed_ns - inference_started_ns),
                                         "post_generation_grounding_duration_ns": max(
                                             0, grounding_completed_ns - grounding_started_ns),
                                         "model_completion_to_grounding_complete_duration_ns": max(
                                             0, grounding_completed_ns - inference_completed_ns),
                                     },
                                     "inference_timing": _public_inference_timing(receipt),
                                     "response_origin": response_origin,
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
                               game_process_names: tuple[str, ...] | list[str] = (),
                               gaming_keep_alive: str = "0",
                               gaming_resource_status_provider: Callable[
                                   [], Mapping[str, Any]
                               ] | None = None,
                               screen_observer: Callable[
                                   [], Mapping[str, object] | None
                               ] | None = None,
                               screen_capture_policy: str = "request_driven",
                               local_speech_output: bool = False,
                               live_consequence_cycle_provider: Callable[
                                   [str, str], Mapping[str, Any] | None
                               ] | None = None,
                               resident_cognition_bridge: Any | None = None,
                               resident_cognition_owner: Any | None = None,
                               resident_history_intervention_owner: Any | None = None,
                               proprioception_provider: Any | None = None,
                               consequence_records_provider: Any | None = None,
                               self_model_owner: Any | None = None,
                               self_model_config: Any | None = None,
                               epistemic_state_owner: Any | None = None,
                               epistemic_state_config: Mapping[str, Any] | None = None) -> DevelopmentLocalChatInference:
    """Explicitly install governed local development chat inference."""
    global _CONVERSATION_SERVICE, _PRODUCTION_COMPOSITION
    root = data_root or sentientos_data_dir()
    # data_root selects development transcript custody only; user memory stays
    # on the one process-wide root shared with the authorized legacy manager.
    memory_root = sentientos_memory_dir()
    if screen_observer is not None and not callable(screen_observer):
        raise TypeError("callable_screen_observer_required")
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
        invoker, model_profiles, foreground_game_detector=foreground_game_detector,
        gaming_keep_alive=gaming_keep_alive,
        gaming_resource_status_provider=gaming_resource_status_provider)
    if resident_cognition_owner is not None:
        if resident_cognition_bridge is not None:
            raise ValueError("provide_bridge_or_owner_not_both")
        resident_cognition_bridge = ResidentDevelopmentalCompanionBridge(
            resident_cognition_owner,
            history_intervention_owner=resident_history_intervention_owner,
            proprioception_provider=proprioception_provider,
            consequence_records_provider=consequence_records_provider,
            self_model_owner=self_model_owner, self_model_config=self_model_config,
            epistemic_state_owner=epistemic_state_owner,
            epistemic_state_config=epistemic_state_config,
            cognition_inference_gate=inference.cognition_inference_context,
            cognition_available=inference.cognition_available)
    if initial_workload_mode != "normal":
        inference.set_workload_mode(initial_workload_mode, game_process_names)
    speech_output = None
    if local_speech_output:
        from control_plane import admit_request
        from .chat_speech_output import ChatSpeechOutputController

        timing_sink = (getattr(avatar_output, "publish_speech_timing", None)
                       if avatar_output is not None else None)
        speech_output = ChatSpeechOutputController(
            admission_provider=admit_request,
            timing_event_sink=timing_sink if callable(timing_sink) else None)
    _CONVERSATION_SERVICE = PersistentConversationService(
        inference=inference,
        session_store=ConversationSessionStore(conversation_root),
        memory_store=CanonicalMemoryStore(memory_root),
        avatar_output=avatar_output, speech_output=speech_output,
        screen_observer=screen_observer,
        screen_capture_policy=screen_capture_policy,
        resident_cognition_bridge=resident_cognition_bridge,
        live_consequence_cycle_provider=live_consequence_cycle_provider)
    _PRODUCTION_COMPOSITION = None
    return inference


def close_production_chat() -> None:
    global _CONVERSATION_SERVICE, _PRODUCTION_COMPOSITION
    composition = _PRODUCTION_COMPOSITION
    service = _CONVERSATION_SERVICE
    _PRODUCTION_COMPOSITION = None
    _CONVERSATION_SERVICE = None
    if composition is not None:
        composition.close()
    elif service is not None:
        service.close()


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


def _chat_stream_event(event: Mapping[str, object]) -> str:
    event_type = str(event.get("type", "message"))
    data = json.dumps(dict(event), ensure_ascii=True, separators=(",", ":"))
    return f"event: {event_type}\ndata: {data}\n\n"


@APP.post("/sessions/{session_id}/developmental-cycle")
async def developmental_cycle_endpoint(session_id: str,
        request: DevelopmentalCycleRequest, http_request: Request) -> dict[str, Any]:
    """Run one locally confirmed fresh-observation cycle through governed writeback."""
    client_host = getattr(getattr(http_request, "client", None), "host", None)
    try:
        local_client = isinstance(client_host, str) and ipaddress.ip_address(client_host).is_loopback
    except ValueError:
        local_client = False
    if not local_client:
        raise HTTPException(status_code=403,
            detail="developmental_cycle_local_access_required")
    if request.session_id != session_id or request.operator_confirmed is not True:
        raise HTTPException(status_code=400,
            detail="developmental_cycle_operator_confirmation_required")
    try:
        service = _get_conversation_service()
        return await asyncio.to_thread(service.run_developmental_cycle,
            session_id=session_id, assistant_turn_id=request.assistant_turn_id,
            request_id=request.request_id,
            operator_feedback=request.operator_feedback)
    except CognitionWorkloadUnavailable as exc:
        raise HTTPException(status_code=409,
            detail="developmental_cycle_deferred_during_gaming_workload") from exc
    except ChatRequestStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404,
            detail="conversation_session_not_found") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503,
            detail="developmental_cycle_not_completed") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@APP.post("/sessions/{session_id}/history-intervention")
async def history_intervention_endpoint(session_id: str,
        request: HistoryInterventionRequest, http_request: Request) -> dict[str, Any]:
    """Run a local history comparison only after explicit confirmation."""
    client_host = getattr(getattr(http_request, "client", None), "host", None)
    try:
        local_client = isinstance(client_host, str) and ipaddress.ip_address(client_host).is_loopback
    except ValueError:
        local_client = False
    if not local_client:
        raise HTTPException(status_code=403,
            detail="history_intervention_local_access_required")
    if request.session_id != session_id or request.operator_confirmed is not True:
        raise HTTPException(status_code=400,
            detail="history_intervention_operator_confirmation_required")
    try:
        service = _get_conversation_service()
        return await asyncio.to_thread(service.run_history_intervention,
            session_id=session_id, assistant_turn_id=request.assistant_turn_id,
            request_id=request.request_id)
    except CognitionWorkloadUnavailable as exc:
        raise HTTPException(status_code=409,
            detail="history_intervention_deferred_during_gaming_workload") from exc
    except ChatRequestStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404,
            detail="conversation_session_not_found") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503,
            detail="history_intervention_not_completed") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@APP.post("/chat/stream")
async def chat_stream_endpoint(request: ChatRequest, http_request: Request) -> StreamingResponse:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message must not be empty")
    service = _get_conversation_service()
    if not service.streaming_available():
        raise HTTPException(status_code=503, detail="Streaming is unavailable for this model backend")
    if _CHANGE_NARRATOR is not None:
        summary = _CHANGE_NARRATOR.maybe_respond(message)
        if summary is not None:
            raise HTTPException(status_code=409, detail=summary)

    stream_request_started_ns = time.monotonic_ns()
    events: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=128)
    disconnected = threading.Event()
    worker_finished = threading.Event()

    def publish(event: dict[str, Any]) -> bool:
        while not disconnected.is_set():
            try:
                events.put(event, timeout=0.1)
                return True
            except queue.Full:
                continue
        return False

    def on_content_chunk(text: str) -> None:
        if not publish({"type": "delta", "text": text}):
            raise RuntimeError("chat_stream_client_disconnected")

    def run_chat() -> None:
        try:
            response = service.chat(message, session_id=request.session_id,
                retain=request.retain, request_id=request.request_id,
                observe_screen=request.observe_screen,
                on_content_chunk=on_content_chunk)
            payload = {
                "response": response.response,
                "session_id": response.session_id,
                "turn_id": response.turn_id,
                "context": response.context,
                "retention": response.retention,
                "response_diagnostics": response.response_diagnostics,
            }
            publish({"type": "complete", "response": payload})
        except ChatInputBudgetError:
            publish({"type": "error", "code": "chat_input_too_large"})
        except ChatRequestStateError:
            publish({"type": "error", "code": "chat_request_conflict"})
        except FileNotFoundError:
            publish({"type": "error", "code": "chat_session_not_found"})
        except Exception as exc:
            if not disconnected.is_set():
                failure_code = None
                if (type(exc).__name__ == "ScreenObservationBridgeError"
                        and exc.args and isinstance(exc.args[0], str)
                        and re.fullmatch(r"(?:screen|game_screen)_[a-z0-9_]{1,80}",
                                         exc.args[0])):
                    failure_code = exc.args[0]
                if failure_code is None:
                    LOGGER.warning("Streaming chat failed: %s", type(exc).__name__)
                else:
                    LOGGER.warning("Streaming chat failed: %s failure_code=%s",
                                   type(exc).__name__, failure_code)
                if failure_code is not None:
                    publish({"type": "error", "code": "screen_observation_failed",
                             "failure_code": failure_code})
                else:
                    publish({"type": "error", "code": "chat_generation_failed"})
        finally:
            worker_finished.set()

    async def stream_events() -> AsyncIterator[str]:
        worker = threading.Thread(target=run_chat, name="chat-stream-inference", daemon=True)
        worker.start()
        terminal_event = False
        try:
            while True:
                try:
                    event = await asyncio.to_thread(events.get, True, 0.15)
                except queue.Empty:
                    if await http_request.is_disconnected():
                        disconnected.set()
                        service.cancel_active_generation()
                        return
                    if worker_finished.is_set():
                        return
                    continue
                if event.get("type") in {"delta", "complete"}:
                    event["server_elapsed_ns"] = max(
                        0, time.monotonic_ns() - stream_request_started_ns)
                yield _chat_stream_event(event)
                if event.get("type") in {"complete", "error"}:
                    terminal_event = True
                    return
        finally:
            if not terminal_event:
                disconnected.set()
                service.cancel_active_generation()

    return StreamingResponse(stream_events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


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
        service = _get_conversation_service()
        return await asyncio.to_thread(service.chat, message,
            session_id=request.session_id, retain=request.retain,
            request_id=request.request_id, observe_screen=request.observe_screen)
    except ScreenObservationBridgeError as exc:
        failure_code = (exc.args[0] if exc.args and isinstance(exc.args[0], str)
                        and re.fullmatch(r"(?:screen|game_screen)_[a-z0-9_]{1,80}",
                                         exc.args[0]) else "screen_observation_unavailable")
        raise HTTPException(status_code=502, detail={
            "code": "screen_observation_failed",
            "failure_code": failure_code,
        }) from exc
    except ChatInputBudgetError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
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


@APP.get("/runtime-status")
async def runtime_status_endpoint() -> dict[str, Any]:
    """Report local composition posture without conflating dev with production readiness."""
    try:
        service = _get_conversation_service()
        inference = service._inference
        if isinstance(inference, DevelopmentLocalChatInference):
            workload = service.current_workload_state()
            speech = service.speech_output_state(None)
            model_residency = await asyncio.to_thread(
                inference.model_residency_status)
            return {
                "status": "running",
                "posture": "development_only",
                "production_serving": False,
                "effective_workload_mode": workload.get("effective_mode"),
                "model_residency": model_residency,
                "screen_observation_configured": service.screen_observation_configured(),
                "local_speech_configured": speech.get("configured") is True,
                "local_speech_backend_available": speech.get("backend_available") is True,
            }
        ready = production_chat_ready()
        return {
            "status": "ready" if ready else "unavailable",
            "posture": "production",
            "production_serving": ready,
        }
    except Exception as exc:
        LOGGER.warning("Local runtime status unavailable: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Local runtime status unavailable") from exc


@APP.get("/screen-observation")
async def screen_observation_status_endpoint() -> dict[str, Any]:
    """Distinguish capture policy from the per-message choice to include OCR."""
    return _get_conversation_service().screen_observation_status()


@APP.get("/workload-mode")
async def workload_mode_endpoint() -> dict[str, Any]:
    try:
        return _get_conversation_service().current_workload_state()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Chat workload mode unavailable") from exc


@APP.post("/workload-mode/reconcile")
async def reconcile_workload_mode_endpoint() -> dict[str, Any]:
    """Reconcile an automatic game transition and release the prior profile if needed."""
    try:
        return _get_conversation_service().reconcile_workload_state()
    except RuntimeError as exc:
        detail = (
            "Automatic game transition blocked because model residency release was not confirmed."
            if str(exc) == "local_model_profile_release_unconfirmed"
            else "Chat workload mode unavailable"
        )
        raise HTTPException(status_code=503, detail=detail) from exc


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
    service = _get_conversation_service()
    intervention_available = service.history_intervention_available()
    developmental_cycle_available = service.developmental_cycle_available()
    turns = session["turns"]
    visible_turns = turns[-100:]
    display_turns: list[dict[str, Any]] = []
    for turn in visible_turns:
        displayed = {key: turn[key] for key in (
            "turn_id", "sequence", "role", "timestamp", "text")}
        if turn.get("role") == "assistant":
            diagnostics = _saved_transcript_response_diagnostics(turn)
            diagnostics["developmental_history_intervention_available"] = (
                intervention_available is True
                and diagnostics.get("developmental_history_intervention_available") is True)
            diagnostics["developmental_cycle_available"] = (
                developmental_cycle_available is True
                and diagnostics.get("developmental_history_intervention_available") is True)
            diagnostics["operator_feedback_available"] = (
                service.operator_feedback_available() is True
                and diagnostics.get("operator_feedback_available") is True)
            displayed["response_diagnostics"] = diagnostics
        display_turns.append(displayed)
    return {
        "session_id": session_id,
        "total_turns": len(turns),
        "truncated": len(visible_turns) < len(turns),
        "turns": display_turns,
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
                #runtime-diagnostics { margin: 1rem 0; padding: 0.75rem; background: #1b1b1b; border-radius: 8px; }
                #local-runtime-status { margin-left: 0.5rem; color: #aaa; }
                #response-integrity { color: #aaa; font-size: 0.9rem; }
                #response-diagnostics { margin-top: 0.75rem; color: #ccc; }
                #response-diagnostics dl { display: grid; grid-template-columns: minmax(180px, auto) 1fr; gap: 0.35rem 0.75rem; overflow-wrap: anywhere; }
                #response-diagnostics dt { color: #aaa; }
                #response-diagnostics dd { margin: 0; }
                .turn-lineage { margin-top: 0.5rem; color: #aaa; font-size: 0.85rem; }
                .turn-lineage dl { display: grid; grid-template-columns: minmax(170px, auto) 1fr; gap: 0.25rem 0.6rem; overflow-wrap: anywhere; }
                .turn-lineage dt { color: #888; }
                .turn-lineage dd { margin: 0; }
                #workload-controls { margin: 1rem 0; padding: 0.75rem; background: #1b1b1b; border-radius: 8px; }
                #workload-mode, #game-process-names { width: auto; min-height: 0; margin: 0.25rem; padding: 0.4rem; }
                #workload-status { margin-left: 0.5rem; color: #aaa; }
                #conversation-controls { margin: 1rem 0; padding: 0.75rem; background: #1b1b1b; border-radius: 8px; }
                #conversation-session { max-width: 100%; min-height: 0; margin: 0.25rem; padding: 0.4rem; }
                #conversation-session-status { margin-left: 0.5rem; color: #aaa; }
                #avatar-output-controls { margin: 1rem 0; padding: 0.75rem; background: #1b1b1b; border-radius: 8px; }
                #avatar-output-status { margin-left: 0.5rem; color: #aaa; }
                #screen-observation-controls { margin: 0.75rem 0; }
                #screen-observation-status { display: block; color: #aaa; }
                textarea { width: 100%; min-height: 120px; padding: 0.75rem; font-size: 1rem; }
                button { margin-top: 1rem; padding: 0.75rem 1.5rem; font-size: 1rem; cursor: pointer; }
                .response { margin-top: 2rem; padding: 1rem; background: #1e1e1e; border-radius: 8px; }
                #response-timing { margin: 0.5rem 0 0; color: #aaa; font-size: 0.85rem; }
                #response-timing p { margin-bottom: 0; }
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
                <section id="runtime-diagnostics" aria-label="Local runtime status">
                    <strong>Local runtime:</strong>
                    <span id="local-runtime-status" role="status" aria-live="polite">Checking local service...</span>
                </section>
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
                <section id="conversation-controls" aria-label="Conversation">
                    <label for="conversation-session">Saved conversation</label>
                    <select id="conversation-session" aria-label="Saved conversations" disabled></select>
                    <button id="new-conversation" type="button" disabled>New conversation</button>
                    <span id="conversation-session-status" role="status">Loading saved conversations...</span>
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
                    <span id="screen-observation-status" role="status">One consented foreground-game frame is processed locally as OCR and optional visual summary, then discarded.</span>
                </section>
                <button id="send">Send</button>
                <div id="response" class="response" hidden>
                    <strong>Response:</strong>
                    <p id="response-text"></p>
                    <p id="response-integrity" role="status" aria-live="polite"></p>
                    <details id="response-diagnostics">
                        <summary>Answer lineage details</summary>
                        <dl>
                            <dt>Inference output digest</dt><dd><code id="inference-output-digest"></code></dd>
                            <dt>Raw inference text SHA-256</dt><dd><code id="inference-output-text-sha256"></code></dd>
                            <dt>Transcript text SHA-256</dt><dd><code id="transcript-text-sha256"></code></dd>
                            <dt>API response text SHA-256</dt><dd><code id="api-delivery-text-sha256"></code></dd>
                            <dt>Displayed text SHA-256</dt><dd><code id="displayed-text-sha256"></code></dd>
                            <dt>Output truncated</dt><dd id="answer-output-truncated"></dd>
                            <dt>Lineage status</dt><dd id="answer-lineage-status"></dd>
                        </dl>
                    </details>
                    <details id="response-timing" hidden>
                        <summary>Response timing</summary>
                        <p id="response-timing-details" role="status"></p>
                    </details>
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
                let pendingExternalSessionId = null;
                function terminalScreenObservationFailureCode(detail) {
                    if (!detail || typeof detail !== 'object'
                            || detail.code !== 'screen_observation_failed') return null;
                    const code = detail.failure_code;
                    return typeof code === 'string'
                        && /^(screen|game_screen)_[a-z0-9_]{1,80}$/.test(code) ? code : null;
                }
                function clearTerminalChatRequestIdentity(storage, key, failure) {
                    if (!key || typeof failure !== 'string'
                            || (!failure.startsWith('screen_observation_failed:')
                                && failure !== 'chat_request_conflict')) return false;
                    try {
                        storage.removeItem(key);
                        return true;
                    } catch (_) {
                        return false;
                    }
                }
                async function consumeChatStream(response, onDelta) {
                    if (!response.body || typeof response.body.getReader !== 'function') {
                        throw new Error('chat_stream_body_unavailable');
                    }
                    const reader = response.body.getReader();
                    const decoder = new TextDecoder();
                    let buffer = '';
                    let completed = null;
                    let terminalError = null;
                    while (true) {
                        const { value, done } = await reader.read();
                        buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
                            .replace(/\\r\\n/g, '\\n');
                        if (done) buffer += '\\n\\n';
                        let boundary = buffer.indexOf('\\n\\n');
                        while (boundary >= 0) {
                            const frame = buffer.slice(0, boundary);
                            buffer = buffer.slice(boundary + 2);
                            const data = frame.split('\\n')
                                .filter(line => line.startsWith('data:'))
                                .map(line => line.slice(5).trimStart()).join('\\n');
                            if (data) {
                                const event = JSON.parse(data);
                                if (event.type === 'delta' && typeof event.text === 'string') {
                                    onDelta(event.text, event);
                                } else if (event.type === 'complete'
                                        && event.response && typeof event.response === 'object') {
                                    completed = event.response;
                                } else if (event.type === 'error'
                                        && typeof event.code === 'string') {
                                    terminalError = event.code
                                        + (typeof event.failure_code === 'string'
                                            ? ':' + event.failure_code : '');
                                }
                            }
                            boundary = buffer.indexOf('\\n\\n');
                        }
                        if (done) break;
                    }
                    if (terminalError) throw new Error(terminalError);
                    if (!completed) throw new Error('chat_stream_completion_missing');
                    return completed;
                }
                async function recoverChatStreamCompletion(error, payload, fetchChat) {
                    if (!(error instanceof Error)
                            || error.message !== 'chat_stream_completion_missing') {
                        throw error;
                    }
                    const response = await fetchChat('/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload),
                    });
                    if (!response.ok) {
                        const failure = await response.json().catch(() => ({}));
                        const screenCode =
                            terminalScreenObservationFailureCode(failure.detail);
                        if (screenCode !== null) {
                            throw new Error('screen_observation_failed:' + screenCode);
                        }
                        throw new Error('chat_stream_recovery_failed');
                    }
                    let data;
                    try {
                        data = await response.json();
                    } catch (_) {
                        throw new Error('chat_stream_recovery_response_invalid');
                    }
                    if (!data || data.session_id !== payload.session_id
                            || typeof data.turn_id !== 'string'
                            || typeof data.response !== 'string') {
                        throw new Error('chat_stream_recovery_response_invalid');
                    }
                    return data;
                }
                async function refreshRuntimeStatus() {
                    const status = document.getElementById('local-runtime-status');
                    try {
                        const response = await fetch('/runtime-status');
                        if (!response.ok) throw new Error('unavailable');
                        const data = await response.json();
                        if (data.posture === 'development_only' && data.status === 'running') {
                            const speech = data.local_speech_configured
                                ? (data.local_speech_backend_available
                                    ? 'local voice available' : 'local voice backend unavailable')
                                : 'local voice not configured';
                            const screen = data.screen_observation_configured
                                ? 'screen observation configured' : 'screen observation not configured';
                            const residency = data.model_residency || {};
                            const model = residency.status === 'resident'
                                ? 'local model loaded'
                                : residency.status === 'unloaded'
                                    ? 'local model unloaded'
                                    : residency.status === 'operation_in_progress'
                                        ? 'model transition or inference in progress; residency not sampled'
                                        : residency.status === 'not_applicable'
                                            ? 'model residency not applicable'
                                            : 'local model residency unavailable';
                            status.textContent = 'Development runtime running; production serving off; '
                                + model + '; ' + speech + '; ' + screen + '.';
                        } else {
                            status.textContent = data.status === 'ready'
                                ? 'Production chat ready.'
                                : 'Local chat runtime unavailable.';
                        }
                    } catch (_) {
                        status.textContent = 'Local runtime status unavailable.';
                    }
                }

                async function sha256Text(value) {
                    const bytes = await crypto.subtle.digest(
                        'SHA-256', new TextEncoder().encode(value));
                    return Array.from(new Uint8Array(bytes))
                        .map(item => item.toString(16).padStart(2, '0')).join('');
                }

                async function renderResponseDiagnostics(data, responseTextEl) {
                    const lineage = data.response_diagnostics || {};
                    const displayedDigest = await sha256Text(responseTextEl.textContent || '');
                    const rawDigest = lineage.invocation_output_text_sha256;
                    const transcriptDigest = lineage.transcript_text_sha256;
                    const apiDigest = lineage.delivery_text_sha256;
                    const transcriptMatches = typeof transcriptDigest === 'string'
                        && displayedDigest === transcriptDigest;
                    const apiMatches = typeof apiDigest === 'string'
                        && displayedDigest === apiDigest;
                    const rawMatches = typeof rawDigest === 'string'
                        && displayedDigest === rawDigest;
                    const status = document.getElementById('response-integrity');
                    const lineageStatus = lineage.status || 'historical_lineage_unavailable';
                    if (transcriptMatches && apiMatches && rawMatches
                            && lineageStatus === 'exact_invocation_output_match') {
                        status.textContent =
                            'Displayed answer matches the exact inference output, transcript, and API response.';
                    } else if (transcriptMatches && apiMatches
                            && lineageStatus === 'grounding_policy_fallback') {
                        status.textContent =
                            'Displayed answer matches the transcript and API response; grounding policy changed the raw inference output.';
                    } else if (transcriptMatches && apiMatches) {
                        status.textContent =
                            'Displayed answer matches the persisted transcript and API response; raw-output relation: '
                            + lineageStatus + '.';
                    } else {
                        status.textContent =
                            'Answer text integrity could not be fully verified; inspect the available digests and lineage status.';
                    }
                    document.getElementById('inference-output-digest').textContent =
                        lineage.invocation_output_digest || 'unavailable';
                    document.getElementById('inference-output-text-sha256').textContent =
                        rawDigest || 'unavailable';
                    document.getElementById('transcript-text-sha256').textContent =
                        transcriptDigest || 'unavailable';
                    document.getElementById('api-delivery-text-sha256').textContent =
                        apiDigest || 'unavailable';
                    document.getElementById('displayed-text-sha256').textContent = displayedDigest;
                    document.getElementById('answer-output-truncated').textContent =
                        lineage.output_truncated === true ? 'yes'
                            : (lineage.output_truncated === false ? 'no' : 'unknown');
                    document.getElementById('answer-lineage-status').textContent = lineageStatus;
                }

                async function appendSavedTurnDiagnostics(entry, content, lineage) {
                    if (!lineage || typeof lineage !== 'object') return;
                    const displayedDigest = await sha256Text(content.textContent || '');
                    const savedDigest = lineage.saved_transcript_text_sha256;
                    const transcriptDigest = lineage.transcript_text_sha256;
                    const deliveryDigest = lineage.delivery_text_sha256;
                    const rawDigest = lineage.invocation_output_text_sha256;
                    const savedMatches = typeof savedDigest === 'string'
                        && displayedDigest === savedDigest;
                    const transcriptMatches = typeof transcriptDigest === 'string'
                        && displayedDigest === transcriptDigest;
                    const deliveryMatches = typeof deliveryDigest === 'string'
                        && displayedDigest === deliveryDigest;
                    const rawMatches = typeof rawDigest === 'string'
                        && displayedDigest === rawDigest;
                    const lineageStatus = lineage.status || 'historical_lineage_unavailable';
                    const details = document.createElement('details');
                    details.className = 'turn-lineage';
                    const summary = document.createElement('summary');
                    summary.textContent = 'Saved answer integrity';
                    const status = document.createElement('p');
                    const checks = [
                        savedMatches ? 'saved transcript matches' : 'saved transcript mismatch or unavailable',
                        typeof deliveryDigest !== 'string' ? 'API-delivery digest unavailable'
                            : (deliveryMatches ? 'API-delivered transcript text matches'
                                : 'API-delivered transcript text differs'),
                        transcriptMatches ? 'transcript lineage matches' : 'transcript lineage mismatch or unavailable',
                        typeof rawDigest !== 'string' ? 'raw inference digest unavailable'
                            : (rawMatches ? 'raw inference text matches' : 'raw inference text differs'),
                    ];
                    const screen = lineage.screen_observation;
                    const components = screen && screen.component_statuses
                        && typeof screen.component_statuses === 'object'
                        ? screen.component_statuses : {};
                    const failures = screen && screen.component_failure_codes
                        && typeof screen.component_failure_codes === 'object'
                        ? screen.component_failure_codes : {};
                    if (screen && typeof screen === 'object') {
                        checks.push('screen observation captured; local vision '
                            + (components.vision || 'status unavailable') + '; local OCR '
                            + (components.ocr || 'status unavailable')
                            + (failures.vision ? '; vision failure: ' + failures.vision : '')
                            + (failures.ocr ? '; OCR failure: ' + failures.ocr : '')
                            + '; raw frame retained: no');
                    }
                    status.textContent = checks.join('; ') + ' (lineage: ' + lineageStatus + ').';
                    const list = document.createElement('dl');
                    const fields = [
                        ['Raw inference text SHA-256', rawDigest || 'unavailable'],
                        ['Transcript text SHA-256', transcriptDigest || 'unavailable'],
                        ['Transcript digest source', lineage.transcript_text_digest_source
                            || 'unknown'],
                        ['API-delivered text SHA-256', deliveryDigest || 'unavailable'],
                        ['API-delivery digest source', lineage.delivery_text_digest_source
                            || 'unknown'],
                        ['Saved transcript text SHA-256', savedDigest || 'unavailable'],
                        ['Displayed text SHA-256', displayedDigest],
                        ['Lineage status', lineageStatus],
                        ['Output truncated', lineage.output_truncated === true ? 'yes'
                            : (lineage.output_truncated === false ? 'no' : 'unknown')],
                    ];
                    if (screen && typeof screen === 'object') {
                        fields.push(
                            ['Screen observation captured at', screen.captured_at || 'unknown'],
                            ['Screen text status', screen.text_status || 'unknown'],
                            ['Screen backend', screen.backend || 'unknown'],
                            ['Local visual description', components.vision || 'status unavailable'],
                            ['Local visual-description failure', failures.vision || 'none'],
                            ['Local OCR', components.ocr || 'status unavailable'],
                            ['Local OCR failure', failures.ocr || 'none'],
                            ['Raw frame retained', 'no']
                        );
                    }
                    fields.forEach(([labelText, valueText]) => {
                        const label = document.createElement('dt');
                        label.textContent = labelText;
                        const value = document.createElement('dd');
                        const code = document.createElement('code');
                        code.textContent = valueText;
                        value.appendChild(code);
                        list.append(label, value);
                    });
                    details.append(summary, status, list);
                    entry.appendChild(details);
                }

                async function sendMessage() {
                    if (chatSendInFlight) return;
                    const sendButton = document.getElementById('send');
                    const conversationSelect = document.getElementById('conversation-session');
                    const newConversationButton = document.getElementById('new-conversation');
                    const browserRequestStartedAt = performance.now();
                    let firstDeltaReceivedMs = null;
                    let firstServerDeltaMs = null;
                    let firstBrowserPaintMs = null;
                    let firstPaintReason = null;
                    let firstPaintScheduled = null;
                    let pendingKey = null;
                    function scheduleFirstBrowserPaint() {
                        if (firstBrowserPaintMs !== null || firstPaintScheduled !== null) return;
                        if (document.visibilityState !== 'visible') {
                            firstPaintReason = 'the chat page was hidden';
                            return;
                        }
                        firstPaintScheduled = new Promise((resolve) => {
                            requestAnimationFrame(() => requestAnimationFrame(() => {
                                firstBrowserPaintMs = performance.now() - browserRequestStartedAt;
                                resolve();
                            }));
                        });
                    }
                    function formatTimingMs(value) {
                        return Math.max(0, value).toFixed(0) + ' ms';
                    }
                    chatSendInFlight = true;
                    sendButton.disabled = true;
                    conversationSelect.disabled = true;
                    newConversationButton.disabled = true;
                    sendButton.textContent = 'Sending...';
                    try {
                        const messageEl = document.getElementById('message');
                        const responseEl = document.getElementById('response');
                        const responseTextEl = document.getElementById('response-text');
                        const responseTimingEl = document.getElementById('response-timing');
                        const responseTimingDetailsEl = document.getElementById(
                            'response-timing-details');
                        responseTimingEl.hidden = true;
                        responseTimingDetailsEl.textContent = '';
                        const message = messageEl.value.trim();
                        const observeScreenControl = document.getElementById('observe-screen');
                        let observeScreen = observeScreenControl.checked;
                        if (!message) { alert('Please enter a message before sending.'); return; }
                        if (observeScreen) {
                            await refreshScreenObservationStatus();
                            observeScreen = observeScreenControl.checked
                                && !observeScreenControl.disabled;
                            if (!observeScreen) {
                                alert('Screen consent is no longer active. Refresh or restart the local companion before requesting another observation.');
                                return;
                            }
                        }
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
                        pendingKey = 'sentientos_pending_chat:' + sessionId + ':' + messageDigest
                            + ':' + (observeScreen ? 'screen' : 'text');
                        let pending = null;
                        try { pending = JSON.parse(localStorage.getItem(pendingKey) || 'null'); }
                        catch (_) { pending = null; }
                        const requestId = pending && typeof pending.request_id === 'string'
                            ? pending.request_id : crypto.randomUUID();
                        localStorage.setItem(pendingKey, JSON.stringify({ request_id: requestId }));
                        const chatPayload = { message, session_id: sessionId,
                            request_id: requestId, observe_screen: observeScreen };
                        let streamRecoveryStatus = null;
                        let res = await fetch('/chat/stream', {
                            method: 'POST', headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(chatPayload),
                        });
                        if (res.status === 503) {
                            const failure = await res.clone().json().catch(() => ({}));
                            if (failure.detail ===
                                    'Streaming is unavailable for this model backend') {
                                res = await fetch('/chat', {
                                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({ message, session_id: sessionId,
                                        request_id: requestId, observe_screen: observeScreen }),
                                });
                            }
                        }
                        if (!res.ok) {
                            const detail = await res.json().catch(() => ({ detail: 'Unknown error' }));
                            const failure = detail.detail;
                            const failureCode = terminalScreenObservationFailureCode(failure);
                            if (failureCode !== null) {
                                clearTerminalChatRequestIdentity(
                                    localStorage, pendingKey,
                                    'screen_observation_failed:' + failureCode);
                                alert('Screen observation failed (' + failureCode
                                    + '). Send with the screen option, then return focus to the approved game within the configured foreground wait. Uncheck the screen option for text only.');
                                return;
                            }
                            if (failure === 'chat_request_conflict') {
                                const identityCleared = clearTerminalChatRequestIdentity(
                                    localStorage, pendingKey, failure);
                                alert(identityCleared
                                    ? 'This request ID conflicts with an earlier request. I cleared the stale ID; send again only if you want a new request.'
                                    : 'This request ID conflicts with an earlier request, and its local retry ID could not be cleared. Refresh the page before retrying.');
                                return;
                            }
                            alert(typeof failure === 'string' ? failure
                                : 'Unable to reach SentientOS chat. The same request identity will be reused if retried.');
                            return;
                        }
                        let data;
                        if (res.headers.get('content-type')?.startsWith('text/event-stream')) {
                            responseEl.hidden = false;
                            responseTextEl.textContent = '';
                            try {
                                data = await consumeChatStream(res, (chunk, event) => {
                                    if (firstDeltaReceivedMs === null) {
                                        firstDeltaReceivedMs = performance.now()
                                            - browserRequestStartedAt;
                                    }
                                    if (firstServerDeltaMs === null
                                            && Number.isSafeInteger(event.server_elapsed_ns)) {
                                        firstServerDeltaMs = event.server_elapsed_ns / 1e6;
                                    }
                                    responseTextEl.textContent += chunk;
                                    scheduleFirstBrowserPaint();
                                });
                            } catch (streamError) {
                                data = await recoverChatStreamCompletion(
                                    streamError, chatPayload,
                                    (url, options) => fetch(url, options));
                                streamRecoveryStatus =
                                    'Recovered reply through the idempotent non-stream endpoint';
                                responseTextEl.textContent = data.response;
                            }
                        } else {
                            data = await res.json();
                        }
                        const responseCompletedMs = performance.now() - browserRequestStartedAt;
                        localStorage.setItem('sentientos_session_id', data.session_id);
                        localStorage.removeItem(pendingKey);
                        messageEl.value = '';
                        responseTextEl.textContent = data.response;
                        responseEl.hidden = false;
                        await renderResponseDiagnostics(data, responseTextEl);
                        scheduleFirstBrowserPaint();
                        if (firstPaintScheduled && document.visibilityState === 'visible') {
                            await Promise.race([
                                firstPaintScheduled,
                                new Promise(resolve => setTimeout(resolve, 100)),
                            ]);
                        }
                        const timingParts = [];
                        if (streamRecoveryStatus !== null) {
                            timingParts.push(streamRecoveryStatus);
                        }
                        if (data.context && data.context.recovered_without_inference === true) {
                            timingParts.push('saved reply reused without new inference or screen capture');
                        }
                        if (firstBrowserPaintMs !== null) {
                            timingParts.push('First browser paint opportunity (double-rAF estimate) '
                                + formatTimingMs(firstBrowserPaintMs));
                        } else if (firstDeltaReceivedMs !== null) {
                            timingParts.push('First grounded text received '
                                + formatTimingMs(firstDeltaReceivedMs)
                                + '; browser paint not measured'
                                + (firstPaintReason ? ' (' + firstPaintReason + ')' : ''));
                        } else {
                            timingParts.push('Response received '
                                + formatTimingMs(responseCompletedMs) + ' after send');
                        }
                        if (firstServerDeltaMs !== null) {
                            timingParts.push('server released grounded text '
                                + formatTimingMs(firstServerDeltaMs) + ' after request');
                        }
                        const chatTiming = data.context && data.context.chat_timing
                            ? data.context.chat_timing : {};
                        const inferenceTiming = data.context && data.context.inference_timing
                            ? data.context.inference_timing : {};
                        if (Number.isSafeInteger(inferenceTiming.load_duration_ns)) {
                            timingParts.push('backend model load '
                                + formatTimingMs(inferenceTiming.load_duration_ns / 1e6));
                        }
                        if (Number.isSafeInteger(
                                inferenceTiming.prompt_evaluation_duration_ns)) {
                            timingParts.push('backend prompt evaluation '
                                + formatTimingMs(
                                    inferenceTiming.prompt_evaluation_duration_ns / 1e6)
                                + (Number.isSafeInteger(inferenceTiming.prompt_tokens)
                                    ? ' (' + inferenceTiming.prompt_tokens + ' prompt tokens)' : ''));
                        }
                        if (Number.isSafeInteger(inferenceTiming.first_content_chunk_duration_ns)) {
                            timingParts.push('model first content chunk '
                                + formatTimingMs(inferenceTiming.first_content_chunk_duration_ns / 1e6)
                                + ' after invocation start');
                        }
                        if (Number.isSafeInteger(inferenceTiming.generation_duration_ns)) {
                            timingParts.push('backend token generation '
                                + formatTimingMs(inferenceTiming.generation_duration_ns / 1e6)
                                + (Number.isSafeInteger(inferenceTiming.completion_tokens)
                                    ? ' (' + inferenceTiming.completion_tokens + ' output tokens)' : ''));
                        }
                        if (Number.isSafeInteger(chatTiming.model_call_wall_duration_ns)) {
                            timingParts.push('model call '
                                + formatTimingMs(chatTiming.model_call_wall_duration_ns / 1e6));
                        }
                        if (Number.isSafeInteger(
                                chatTiming.model_completion_to_grounding_complete_duration_ns)) {
                            timingParts.push('generation complete to grounded answer '
                                + formatTimingMs(
                                    chatTiming.model_completion_to_grounding_complete_duration_ns
                                        / 1e6));
                        }
                        if (Number.isSafeInteger(chatTiming.post_generation_grounding_duration_ns)) {
                            timingParts.push('grounding policy checks '
                                + formatTimingMs(chatTiming.post_generation_grounding_duration_ns / 1e6));
                        }
                        responseTimingDetailsEl.textContent = timingParts.join(' · ');
                        responseTimingEl.hidden = timingParts.length === 0;
                        await refreshConversationSessions(data.session_id);
                        await refreshConversationTranscript();
                        refreshAvatarOutput();
                    } catch (err) {
                        const failure = err instanceof Error && typeof err.message === 'string'
                            ? err.message.split(String.fromCharCode(13)).join(' ').split(String.fromCharCode(10)).join(' ').split(String.fromCharCode(9)).join(' ').slice(0, 180)
                            : 'unknown_client_error';
                        // Terminal capture failures and request conflicts cannot reuse their old id.
                        const requestIdentityCleared = clearTerminalChatRequestIdentity(
                            localStorage, pendingKey, failure);
                        if (failure === 'screen_observation_failed:screen_observation_request_timeout') {
                            alert('Screen observation timed out. Send with the screen option, then return focus to the approved game within the configured foreground wait. Uncheck the screen option for a text-only message.');
                        } else if (failure.startsWith('screen_observation_failed:')) {
                            alert('Screen observation failed (' + failure.slice(26)
                                + '). Send with the screen option, then return focus to the approved game within the configured foreground wait. Uncheck the screen option for text only.');
                        } else if (failure === 'chat_request_conflict') {
                            alert(requestIdentityCleared
                                ? 'This request ID conflicts with an earlier request. I cleared the stale ID; send again only if you want a new request.'
                                : 'This request ID conflicts with an earlier request, and its local retry ID could not be cleared. Refresh the page before retrying.');
                        } else {
                            alert('Unable to send this message (' + failure
                                + '). The same request identity will be reused if retried.');
                        }
                        console.error('Unable to send SentientOS chat message', err);
                    } finally {
                        chatSendInFlight = false;
                        sendButton.disabled = false;
                        document.getElementById('conversation-session').disabled =
                            !document.getElementById('conversation-session').options.length;
                        document.getElementById('new-conversation').disabled = false;
                        sendButton.textContent = 'Send';
                        if (pendingExternalSessionId !== null) {
                            const externalSessionId = pendingExternalSessionId;
                            pendingExternalSessionId = null;
                            await restoreConversationSession(externalSessionId);
                        }
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
                        if (data.configured !== true) {
                            status.textContent = 'Not configured. The server needs an explicit local process allowlist and consented screen source.';
                        } else if (data.consent_status === 'expired') {
                            control.checked = false;
                            control.disabled = true;
                            status.textContent = 'Screen consent expired. Restart the local companion with a new consent window before requesting another observation.';
                        } else if (data.capture_policy === 'allowlisted_session_polling') {
                            status.textContent = 'Capture policy: allowlisted session polling; raw frames are discarded. This checkbox controls whether the latest OCR observation is included in a message.';
                        } else {
                            const handoffSeconds = Number.isInteger(data.foreground_wait_seconds)
                                ? data.foreground_wait_seconds : 0;
                            const handoff = handoffSeconds > 0
                                ? ' Send, then return focus to the approved game within '
                                    + handoffSeconds + ' seconds.'
                                : ' The approved game must already be foreground when you send.';
                            status.textContent = 'Capture policy: request-driven and local. This checkbox requests one foreground-game observation with local OCR and optional visual summary; the frame is discarded.'
                                + handoff;
                        }
                    } catch (_) {
                        control.checked = false;
                        control.disabled = true;
                        status.textContent = 'Screen observation status unavailable';
                    }
                }
                function conversationSessionLabel(session) {
                    const timestamp = new Date(
                        session.latest_activity_at || session.created_at);
                    const when = Number.isNaN(timestamp.getTime())
                        ? 'Saved conversation' : timestamp.toLocaleString();
                    const turns = Number.isInteger(session.revision) ? session.revision : 0;
                    const suffix = typeof session.session_id === 'string'
                        ? session.session_id.slice(-8) : 'unknown';
                    return `${when} · ${turns} turns · ${suffix}`;
                }
                async function refreshConversationSessions(preferredSessionId = null) {
                    const select = document.getElementById('conversation-session');
                    const status = document.getElementById('conversation-session-status');
                    const currentSessionId = preferredSessionId
                        || localStorage.getItem('sentientos_session_id');
                    try {
                        const response = await fetch('/sessions');
                        if (!response.ok) throw new Error('session_list_unavailable');
                        const sessions = await response.json();
                        if (!Array.isArray(sessions)) throw new Error('session_list_invalid');
                        select.replaceChildren();
                        sessions.forEach((session) => {
                            if (typeof session.session_id !== 'string') return;
                            const option = document.createElement('option');
                            option.value = session.session_id;
                            option.textContent = conversationSessionLabel(session);
                            select.appendChild(option);
                        });
                        if (currentSessionId && !sessions.some(
                                (session) => session.session_id === currentSessionId)) {
                            const option = document.createElement('option');
                            option.value = currentSessionId;
                            option.textContent = 'Current saved conversation · '
                                + currentSessionId.slice(-8);
                            select.appendChild(option);
                        }
                        if (currentSessionId) select.value = currentSessionId;
                        const selected = sessions.find(
                            (session) => session.session_id === currentSessionId);
                        status.textContent = selected
                            ? `Showing saved conversation · ${conversationSessionLabel(selected)}`
                            : (currentSessionId ? 'Showing the selected saved conversation.'
                                : 'No conversation selected.');
                        select.disabled = !select.options.length;
                    } catch (_) {
                        select.disabled = true;
                        status.textContent = 'Saved conversation list unavailable';
                    }
                }
                async function restoreConversationSession(sessionId) {
                    if (!sessionId) return;
                    localStorage.setItem('sentientos_session_id', sessionId);
                    document.getElementById('response').hidden = true;
                    document.getElementById('response-text').textContent = '';
                    document.getElementById('observe-screen').checked = false;
                    await refreshConversationSessions(sessionId);
                    await refreshConversationTranscript();
                    await refreshAvatarOutput();
                    await refreshSpeechOutput();
                }
                async function changeConversationSession() {
                    if (chatSendInFlight) return;
                    const sessionId = document.getElementById('conversation-session').value;
                    await restoreConversationSession(sessionId);
                }
                window.addEventListener('storage', (event) => {
                    if (event.key !== 'sentientos_session_id' || !event.newValue) return;
                    if (chatSendInFlight) {
                        pendingExternalSessionId = event.newValue;
                        return;
                    }
                    restoreConversationSession(event.newValue);
                });
                async function startNewConversation() {
                    if (chatSendInFlight) return;
                    const button = document.getElementById('new-conversation');
                    const select = document.getElementById('conversation-session');
                    const status = document.getElementById('conversation-session-status');
                    button.disabled = true;
                    select.disabled = true;
                    status.textContent = 'Starting a new conversation...';
                    try {
                        const response = await fetch('/sessions', { method: 'POST' });
                        if (!response.ok) throw new Error('session_creation_failed');
                        const payload = await response.json();
                        if (typeof payload.session_id !== 'string') {
                            throw new Error('session_id_missing');
                        }
                        localStorage.setItem('sentientos_session_id', payload.session_id);
                        document.getElementById('response').hidden = true;
                        document.getElementById('response-text').textContent = '';
                        document.getElementById('observe-screen').checked = false;
                        await refreshConversationSessions(payload.session_id);
                        await refreshConversationTranscript();
                        await refreshAvatarOutput();
                        await refreshSpeechOutput();
                        status.textContent = 'New conversation started.';
                        document.getElementById('message').focus();
                    } catch (_) {
                        status.textContent = 'Unable to start a new conversation.';
                    } finally {
                        button.disabled = false;
                        select.disabled = !select.options.length;
                    }
                }
                async function initializeConversationView() {
                    try {
                        await ensureConversationSession();
                        await refreshConversationSessions();
                        await refreshConversationTranscript();
                        await refreshAvatarOutput();
                        await refreshSpeechOutput();
                    } catch (_) {
                        document.getElementById('conversation-session-status').textContent =
                            'Unable to restore a saved conversation.';
                    } finally {
                        document.getElementById('new-conversation').disabled = false;
                        const select = document.getElementById('conversation-session');
                        select.disabled = !select.options.length;
                    }
                }

                async function ensureConversationSession() {
                    const requestedSessionId = new URLSearchParams(window.location.search)
                        .get('session_id');
                    const requestedSessionIdIsValid = typeof requestedSessionId === 'string'
                        && /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(requestedSessionId);
                    let sessionId = requestedSessionIdIsValid
                        ? requestedSessionId
                        : localStorage.getItem('sentientos_session_id');
                    if (requestedSessionIdIsValid) {
                        localStorage.setItem('sentientos_session_id', sessionId);
                    }
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
                        for (const turn of data.turns) {
                            const entry = document.createElement('article');
                            entry.className = 'turn';
                            entry.dataset.role = turn.role;
                            const label = document.createElement('strong');
                            label.className = 'turn-label';
                            label.textContent = turn.role === 'user' ? 'You' : 'SentientOS';
                            const content = document.createElement('div');
                            content.textContent = turn.text;
                            entry.append(label, content);
                            if (turn.role === 'assistant') {
                                await appendSavedTurnDiagnostics(
                                    entry, content, turn.response_diagnostics);
                                if (turn.response_diagnostics
                                        && turn.response_diagnostics
                                            .developmental_history_intervention_available
                                            === true) {
                                    const experimentButton = document.createElement('button');
                                    experimentButton.type = 'button';
                                    experimentButton.textContent =
                                        'Compare history impact (4 inference calls)';
                                    experimentButton.addEventListener('click', () =>
                                        runHistoryIntervention(turn.turn_id, experimentButton, entry));
                                    entry.appendChild(experimentButton);
                                }
                                if (turn.response_diagnostics
                                        && turn.response_diagnostics.developmental_cycle_available
                                            === true) {
                                    const cycleButton = document.createElement('button');
                                    cycleButton.type = 'button';
                                    cycleButton.textContent =
                                        'Learn from current scene (governed writeback)';
                                    cycleButton.addEventListener('click', () =>
                                        runDevelopmentalCycle(turn.turn_id, cycleButton, entry,
                                            turn.response_diagnostics.operator_feedback_available
                                                === true));
                                    entry.appendChild(cycleButton);
                                }
                            }
                            container.appendChild(entry);
                        }
                        container.scrollTop = container.scrollHeight;
                    } catch (_) {
                        container.replaceChildren();
                        const unavailable = document.createElement('p');
                        unavailable.id = 'conversation-status';
                        unavailable.textContent = 'Saved conversation transcript is unavailable.';
                        container.appendChild(unavailable);
                    }
                }
                async function runHistoryIntervention(assistantTurnId, button, entry) {
                    if (!window.confirm('Run a matched history-present / withheld / restored comparison? This uses up to four local model inference calls and one fresh consented screen observation. It runs only when the workload gate allows it. This measures response differences; it does not prove improved performance.')) return;
                    button.disabled = true;
                    const status = document.createElement('p');
                    status.textContent = 'Running the three-condition comparison...';
                    entry.appendChild(status);
                    try {
                        const sessionId = await ensureConversationSession();
                        const response = await fetch('/sessions/' + encodeURIComponent(sessionId)
                            + '/history-intervention', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    session_id: sessionId,
                                    assistant_turn_id: assistantTurnId,
                                    request_id: crypto.randomUUID(),
                                    operator_confirmed: true,
                                }),
                            });
                        const data = await response.json().catch(() => ({}));
                        if (!response.ok) {
                            status.textContent = typeof data.detail === 'string'
                                ? data.detail : 'History comparison did not complete.';
                            return;
                        }
                        status.textContent = 'History comparison: '
                            + data.response_text_classification
                            + '; restored prompt matches: '
                            + (data.restored_prompt_matches ? 'yes' : 'no')
                            + '; performance improvement: not established.';
                        const comparedResponses = Array.isArray(data.condition_responses)
                            ? data.condition_responses : [];
                        if (comparedResponses.length === 3) {
                            const details = document.createElement('details');
                            const summary = document.createElement('summary');
                            summary.textContent = 'Inspect the three responses (temporary)';
                            details.appendChild(summary);
                            const list = document.createElement('ol');
                            comparedResponses.forEach((condition) => {
                                const item = document.createElement('li');
                                const label = document.createElement('strong');
                                label.textContent = String(condition.condition_id || 'condition');
                                const responseText = document.createElement('p');
                                responseText.textContent = String(condition.response_text || '');
                                item.appendChild(label);
                                item.appendChild(responseText);
                                list.appendChild(item);
                            });
                            details.appendChild(list);
                            entry.appendChild(details);
                        }
                    } catch (_) {
                        status.textContent = 'History comparison did not complete.';
                    } finally {
                        button.disabled = false;
                    }
                }


                async function runDevelopmentalCycle(assistantTurnId, button, entry,
                        feedbackAvailable) {
                    let feedback = null;
                    if (feedbackAvailable) {
                        feedback = window.prompt(
                            'Optional: enter your correction or independently noticed detail. It will be stored as an unverified operator report, separate from the screen capture, and may be retained if the governed owner selects it. Leave blank to run without a correction.',
                            '');
                        if (feedback === null) return;
                        if (feedback.length > 800) {
                            window.alert('Keep the operator report under 800 characters.');
                            return;
                        }
                    }
                    if (!window.confirm('Capture one fresh, consented foreground-game observation and run the existing resident cognition tick? The screen evidence and your optional unverified report may be retained through governed developmental writeback. If a reply predicted an avatar nod, this may also request a separate local avatar-motion observation. The measurement can be indeterminate and does not prove an effect. This can make local model inference calls. Raw screen frames are discarded; no gameplay action is authorized.')) return;

                    button.disabled = true;
                    const status = document.createElement('p');
                    status.textContent = 'Capturing fresh evidence for the governed developmental cycle...';
                    entry.appendChild(status);
                    try {
                        const sessionId = await ensureConversationSession();
                        const response = await fetch('/sessions/' + encodeURIComponent(sessionId)
                            + '/developmental-cycle', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    session_id: sessionId,
                                    assistant_turn_id: assistantTurnId,
                                    request_id: crypto.randomUUID(),
                                    operator_confirmed: true,
                                    operator_feedback: (typeof feedback === 'string'
                                        ? feedback.trim() || null : null),
                                }),
                            });
                        const data = await response.json().catch(() => ({}));
                        if (!response.ok) {
                            status.textContent = typeof data.detail === 'string'
                                ? data.detail : 'Developmental cycle did not complete.';
                            return;
                        }
                        const selfModelStatus = data.self_model_reconciliation_status;
                        const selfModelSummary = selfModelStatus === 'reconciled'
                            ? ' Longitudinal self-model generation '
                                + String(data.self_model_reconciliation_generation || 'unavailable')
                                + ' was reconciled after cognition for later ticks; claims remain evidence-bound and non-authoritative.'
                            : selfModelStatus === 'degraded'
                                ? ' Longitudinal self-model reconciliation degraded ('
                                    + String(data.self_model_reconciliation_error_type || 'unknown')
                                    + '); the developmental writeback result is reported separately.'
                                : ' Longitudinal self-model reconciliation is not configured.';
                        const consequence = data.consequence_measurement;
                        const consequenceSummary = consequence
                            ? consequence.status === 'completed'
                                ? ' Avatar consequence measurement: '
                                    + String(consequence.classification || 'unavailable')
                                    + ' (confidence ' + String(consequence.confidence || 'unknown')
                                    + ', quality ' + String(consequence.quality || 'unknown')
                                    + '). Measurement transport was authenticated; observation accuracy and effect are not proven.'
                                : ' Avatar consequence measurement was unavailable; no effect is proven.'
                            : '';
                        status.textContent = data.status === 'completed_writeback'
                            ? 'Governed developmental writeback completed. Record: '
                                + String(data.written_record_id || 'unavailable')
                                + '; receipt: ' + String(data.writeback_receipt_id || 'unavailable')
                                + (data.operator_feedback_included === true
                                    ? '; your report was included as unverified operator evidence'
                                    : '')
                                + '. History influence and performance improvement are not yet established.'
                                + consequenceSummary + selfModelSummary
                            : 'The developmental tick completed, but no eligible lesson was written to history.'
                                + consequenceSummary + selfModelSummary;
                    } catch (_) {
                        status.textContent = 'Developmental cycle did not complete.';
                    } finally {
                        button.disabled = false;
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
                            const playbackFailureCode = typeof data.playback_failure_code
                                === 'string' && /^[a-z0-9_]{1,80}$/.test(
                                    data.playback_failure_code)
                                ? ' (' + data.playback_failure_code + ')' : '';
                            status.textContent = data.configured !== true
                                ? 'Local speech is not enabled for this server.'
                                : (data.backend_available !== true
                                    ? 'Local system voice backend is unavailable.'
                                    : (data.enabled
                                        ? 'Approved for this conversation; playback: '
                                            + data.playback_status + playbackFailureCode + '.'
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
                    if (data.mode !== 'automatic') {
                        return data.mode === 'gaming' ? 'Low-work mode active' : 'Normal mode';
                    }
                    if (data.observation_status !== 'available') {
                        return 'Game detection unavailable; low-work mode active';
                    }
                    if (data.game_foreground === true) {
                        return 'Watched game is foreground; low-work mode active';
                    }
                    if (data.game_process_running === true) {
                        return 'Watched game is running in background; focus it and verify the screen-capture executable allowlist';
                    }
                    return 'No watched game process found; check the executable names';
                }
                async function refreshWorkloadStatus() {
                    const control = document.getElementById('workload-mode');
                    if (control.disabled) return;
                    const names = document.getElementById('game-process-names');
                    const status = document.getElementById('workload-status');
                    try {
                        const response = await fetch('/workload-mode/reconcile', { method: 'POST' });
                        if (!response.ok) {
                            const failure = await response.json().catch(() => ({}));
                            if (failure.detail ===
                                    'Automatic game transition blocked because model residency release was not confirmed.') {
                                status.textContent = 'Game detected; model release unconfirmed, gaming profile not switched';
                                return;
                            }
                            throw new Error('unavailable');
                        }
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
                document.getElementById('conversation-session').addEventListener('change', changeConversationSession);
                document.getElementById('new-conversation').addEventListener('click', startNewConversation);
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
                refreshRuntimeStatus();
                initializeConversationView();
                refreshWorkloadMode();
                refreshScreenObservationStatus();
                setInterval(refreshBootFeed, 5000);
                setInterval(refreshRuntimeStatus, 5000);
                setInterval(refreshWorkloadStatus, 5000);
                setInterval(() => {
                    if (document.visibilityState === 'visible' && !chatSendInFlight) {
                        refreshConversationSessions();
                    }
                }, 15000);
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



