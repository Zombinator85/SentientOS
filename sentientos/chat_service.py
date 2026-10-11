# mypy: disable-error-code=untyped-decorator
from __future__ import annotations

import argparse
import logging
import hashlib
import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Mapping, Protocol, cast

from .fastapi_stub import FastAPI, HTMLResponse, HTTPException

if TYPE_CHECKING:
    class BaseModel:
        def __init__(self, **data: object) -> None: ...
else:
    from pydantic import BaseModel

from .change_narrator import ChangeNarrator, build_default_change_narrator
from .event_stream import history as boot_history
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
from .conversation_session import (
    ConversationChatLockTimeout, ConversationSessionStore, assemble_local_chat_context,
    compact_runtime_generation_attribution,
)
from .canonical_memory import (AdmittedRetentionWriter, CanonicalMemoryStore, CANDIDATE_TYPE,
    ExplicitRetentionAdmissionGate, retention_request_id,
    sentientos_data_dir, sentientos_memory_dir)
from .local_model_authority import digest_payload

LOGGER = logging.getLogger(__name__)
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


class DevelopmentSimulationInference:
    """Affirmative test/development-only adapter; never selected by production."""
    __slots__ = ("_delegate",)
    def __init__(self, invoker: GovernedLocalModelInvoker) -> None:
        self._delegate = invoker
    def current_conversation_model_identity(self) -> Mapping[str, Any]:
        identity = getattr(self._delegate.model, "active_identity", None)
        return identity.to_dict() if identity is not None else {}
    def generate(self, *, prompt: str, caller: str, correlation_id: str,
                 budget: LocalModelInvocationBudget,
                 caller_linkage: Mapping[str, Any]) -> LocalModelInvocationReceipt:
        request = self._delegate.build_request(purpose="local_user_chat", prompt=prompt, caller=caller,
            correlation_id=correlation_id, budget=budget, linkage=caller_linkage)
        return self._delegate.invoke(request)


class ProductionChatComposition:
    __slots__ = ("service", "_serving", "_resource_owner")
    def __init__(self, service: "PersistentConversationService", serving: ProductionServingController,
                 resource_owner: ProductionChatResourceContextOwner | None = None) -> None:
        self.service, self._serving = service, serving
        self._resource_owner = resource_owner
    def close(self) -> None:
        try:
            self._serving.close()
        finally:
            if self._resource_owner is not None:
                self._resource_owner.close()
    def ready(self) -> bool:
        return cast(bool, self._serving.serving_is_current())

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    retain: bool = False
    request_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    session_id: str
    turn_id: str
    context: dict[str, object]
    retention: dict[str, object]


class ChatRequestStateError(ValueError):
    """A replay conflict or an intentionally unreplayed interrupted request."""


class PersistentConversationService:
    """One transaction boundary for durable turns and governed inference.

    A denied/failed invocation intentionally preserves the user turn as an
    unanswered turn and never manufactures an assistant turn.
    """
    def __init__(self, *, inference: ChatInference, session_store: ConversationSessionStore,
                 memory_store: CanonicalMemoryStore, context_budget_chars: int = 4000,
                 memory_budget_chars: int = 1600, admission_gate: ExplicitRetentionAdmissionGate | None = None) -> None:
        self._inference = inference; self.sessions = session_store; self.memories = memory_store
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
        elif not isinstance(self._inference, DevelopmentSimulationInference):
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
             request_id: str | None = None) -> ChatResponse:
        if session_id is None:
            return self._chat_unlocked(message, session_id=None, retain=retain,
                request_id=request_id)
        try:
            with self.sessions.serialize_chat_requests(session_id):
                return self._chat_unlocked(message, session_id=session_id,
                    retain=retain, request_id=request_id)
        except ConversationChatLockTimeout as exc:
            raise ChatRequestStateError("chat_session_request_lock_timeout") from exc

    def _chat_unlocked(self, message: str, *, session_id: str | None = None,
                       retain: bool = False, request_id: str | None = None) -> ChatResponse:
        if request_id is not None:
            if session_id is None:
                raise ChatRequestStateError("idempotent_request_requires_existing_session")
            try:
                existing = self.sessions.find_user_request(session_id,
                    request_id=request_id, text=message, retain=retain)
            except FileNotFoundError:
                raise
            except ValueError as exc:
                raise ChatRequestStateError(str(exc)) from exc
            if existing is not None:
                return self._recover_idempotent_response(session_id, existing)
        identity_payload = self._inference.current_conversation_model_identity()
        session = self.sessions.create(model_identity=identity_payload) if session_id is None else self.sessions.load(session_id)
        if request_id is None:
            user_turn = self.sessions.append_turn(session["session_id"], role="user", text=message,
                retention_state="requested" if retain else "not_requested")
        else:
            try:
                user_turn, created = self.sessions.append_user_request(session["session_id"],
                    request_id=request_id, text=message, retain=retain)
            except ValueError as exc:
                raise ChatRequestStateError(str(exc)) from exc
            if not created:
                return self._recover_idempotent_response(session["session_id"], user_turn)
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
        history = self.sessions.reconstruct(session["session_id"], budget_chars=self.context_budget_chars,
                                            exclude_turn_id=user_turn["turn_id"])
        memory = self.memories.retrieve(message, budget_chars=self.memory_budget_chars)
        prompt = assemble_local_chat_context(history=history, memory_snapshot=memory,
            current_message=message,
            verified_prior_runtime_lineage=predecessor_runtime_lineage)
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
        client_request_digest = (user_turn.get("linkage", {}).get("client_request_id_digest")
            if isinstance(user_turn.get("linkage"), Mapping) else None)
        if isinstance(client_request_digest, str):
            linkage["client_request_id_digest"] = client_request_digest
        receipt = self._inference.generate(prompt=prompt, caller="chat_service",
            correlation_id=f"chat:{session['session_id']}:{user_turn['turn_id']}",
            budget=LocalModelInvocationBudget(max_input_chars=8000), caller_linkage=linkage)
        accepted_statuses = {"admitted_completed"}
        if isinstance(self._inference, DevelopmentSimulationInference):
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
        if isinstance(self._inference, DevelopmentSimulationInference):
            software_generation_attribution = {
                "status": "development_simulation",
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
                     "memory_retrieval_posture": memory["retrieval_posture"],
                     "legacy_sidecar_posture": memory.get("legacy_sidecar_posture", "unknown_legacy"),
                     "memory_selection_posture": memory.get("selection_posture", "unknown_legacy"),
                     "omitted_memory_count": memory.get("omitted_memory_count")})
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
                retention_result = {"status": "retention_failed", "reason": str(exc),
                                    "admission_receipt_digest": admission.receipt_digest}
                self.sessions.update_turn_retention(session["session_id"], user_turn["turn_id"], state="retention_failed", receipt=retention_result)
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
                              resource_context_owner: ProductionChatResourceContextOwner | None = None,
                              resource_provisioning_id: str | None = None,
                              runtime_handoff_id: str | None = None) -> None:
    """Establish exactly one explicit hardened production serving lifetime."""
    global _CONVERSATION_SERVICE, _PRODUCTION_COMPOSITION
    if resource_context_owner is not None and type(resource_context_owner) is not ProductionChatResourceContextOwner:
        raise TypeError("exact_production_chat_resource_context_owner_required")
    if resource_context_owner is not None and not resource_context_owner.has_single_process_custody:
        raise ValueError("resource_ledger_single_process_custody_required")
    if resource_context_owner is not None and resource_provisioning_id is not None:
        raise ValueError("resource_owner_and_provisioning_id_mutually_exclusive")
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
            serving, runtime_handoff_id=runtime_handoff_id)
        inference: ChatInference = (
            inference_bridge if resource_context_owner is None
            else ResourceBackedProductionChatInference(inference_bridge, resource_context_owner)
        )
        # The roots were checked before serving was established.  Transcript
        # custody remains installation-scoped; canonical memory remains user-scoped.
        handle.ensure_directory(conversation_root)
        service = PersistentConversationService(inference=inference,
            session_store=ConversationSessionStore(conversation_root.path),
            memory_store=CanonicalMemoryStore(memory_root))
    except Exception:
        if serving is not None:
            serving.close()
        if resource_context_owner is not None:
            resource_context_owner.close()
        raise
    assert serving is not None
    close_production_chat()
    _CONVERSATION_SERVICE = service
    _PRODUCTION_COMPOSITION = ProductionChatComposition(service, serving, resource_context_owner)


def configure_development_chat(*, invoker: GovernedLocalModelInvoker,
                               data_root: Path | None = None) -> None:
    """Explicitly install isolated echo/null/test inference."""
    global _CONVERSATION_SERVICE, _PRODUCTION_COMPOSITION
    root = data_root or sentientos_data_dir()
    # data_root selects development transcript custody only; user memory stays
    # on the one process-wide root shared with the authorized legacy manager.
    memory_root = sentientos_memory_dir()
    conversation_root = root / "conversations"
    if _storage_roots_overlap(memory_root, conversation_root):
        raise ValueError("user_memory_root_overlaps_transcript_custody")
    close_production_chat()
    _CONVERSATION_SERVICE = PersistentConversationService(
        inference=DevelopmentSimulationInference(invoker),
        session_store=ConversationSessionStore(conversation_root),
        memory_store=CanonicalMemoryStore(memory_root))
    _PRODUCTION_COMPOSITION = None


def close_production_chat() -> None:
    global _CONVERSATION_SERVICE, _PRODUCTION_COMPOSITION
    composition = _PRODUCTION_COMPOSITION
    _PRODUCTION_COMPOSITION = None
    _CONVERSATION_SERVICE = None
    if composition is not None:
        composition.close()


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
            retain=request.retain, request_id=request.request_id)
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
        return cast(list[dict[str, Any]], _get_conversation_service().sessions.list_recent())
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503,
            detail="conversation_session_listing_unavailable_or_degraded") from exc


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
                #boot-ceremony { margin-bottom: 2rem; padding: 1rem; background: #1b1b1b; border-radius: 8px; }
                #boot-ceremony h2 { margin-top: 0; }
                .boot-entry { margin: 0.5rem 0; padding: 0.5rem; border-left: 4px solid #444; background: #0f0f0f; border-radius: 4px; }
                .boot-entry[data-level="warning"] { border-color: #f0a202; }
                .boot-entry[data-level="error"] { border-color: #f2545b; }
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
                <textarea id="message" placeholder="Type your message..."></textarea>
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

                async function sendMessage() {
                    const messageEl = document.getElementById('message');
                    const responseEl = document.getElementById('response');
                    const responseTextEl = document.getElementById('response-text');
                    const message = messageEl.value.trim();
                    if (!message) {
                        alert('Please enter a message before sending.');
                        return;
                    }
                    let sessionId = localStorage.getItem('sentientos_session_id');
                    if (!sessionId) {
                        const created = await fetch('/sessions', { method: 'POST' });
                        if (!created.ok) {
                            alert('Unable to create a conversation session.');
                            return;
                        }
                        sessionId = (await created.json()).session_id;
                        localStorage.setItem('sentientos_session_id', sessionId);
                    }
                    const messageDigestBytes = await crypto.subtle.digest(
                        'SHA-256', new TextEncoder().encode(message));
                    const messageDigest = Array.from(new Uint8Array(messageDigestBytes))
                        .map(value => value.toString(16).padStart(2, '0')).join('');
                    const pendingKey = 'sentientos_pending_chat:' + sessionId + ':' + messageDigest;
                    let pending = null;
                    try { pending = JSON.parse(localStorage.getItem(pendingKey) || 'null'); }
                    catch (_) { pending = null; }
                    const requestId = pending && typeof pending.request_id === 'string'
                        ? pending.request_id : crypto.randomUUID();
                    localStorage.setItem(pendingKey, JSON.stringify({ request_id: requestId }));
                    const res = await fetch('/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message, session_id: sessionId, request_id: requestId }),
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
                }
                document.getElementById('send').addEventListener('click', sendMessage);
                document.getElementById('message').addEventListener('keydown', (event) => {
                    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
                        event.preventDefault();
                        sendMessage();
                    }
                });
                refreshBootFeed();
                setInterval(refreshBootFeed, 5000);
            </script>
        </body>
        </html>
        """
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run explicitly composed local production chat.")
    parser.add_argument("--installation-identity", required=True)
    parser.add_argument("--serving-operation-id", required=True)
    parser.add_argument("--expected-activation-state-digest")
    parser.add_argument("--resource-provisioning-id")
    parser.add_argument("--runtime-handoff-id", required=True)
    parser.add_argument("--expected-software-generation-digest", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args(argv)

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
                runtime_handoff_id=args.runtime_handoff_id)
            run(host=args.host, port=args.port)
    except Exception as exc:
        raise RuntimeError("supervised_chat_process_lifetime_unavailable") from exc


def run(host: str = "0.0.0.0", port: int = 5000) -> None:
    if _CONVERSATION_SERVICE is None:
        raise RuntimeError("chat_not_explicitly_configured")
    import uvicorn

    uvicorn.run(APP, host=host, port=port)


