"""Request-scoped bridge from consented companion evidence to resident cognition.

This adapter does not own memory. Ordinary interactive replies do not write
developmental history. An explicitly operator-confirmed local cycle may convert
one fresh observation into a transient World-State snapshot and delegate to the
existing governed ResidentDevelopmentalCognitionOwner writeback path.
"""
from __future__ import annotations

import hashlib
import json
import re
from contextlib import nullcontext
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from .cognition_retrieval import is_sparse_or_elliptical_cognition_query
from .embodiment_self_observation import EmbodimentEvidenceOwner, EmbodimentObservation
from .local_model_authority import digest_payload
from .longitudinal_self_model import LongitudinalSelfModelRuntimeConfig
from .persistent_epistemic_state import PersistentEpistemicStateOwner
from .resident_developmental_cognition import (
    MAX_RESIDENT_COGNITION_INPUT_CHARS,
    ResidentCompanionHistoryInterventionResult,
    ResidentCompanionInteractionResult,
    ResidentDevelopmentalCognitionOwner,
    ResidentDevelopmentalCycleResult,
    bind_epistemic_cognitive_context,
)
from .world_state_board import WorldStateBoardBuilder, WorldStateSnapshot, record_digest


class DevelopmentalCompanionBridgeError(ValueError):
    """Invalid request evidence or adapter composition."""


class CognitionWorkloadUnavailable(RuntimeError):
    """The active latency-sensitive workload does not admit cognition inference."""

    code = "cognition_unavailable_during_gaming"


def _valid_history_citation_audit(value: object, *,
        selected_record_ids: object, selected_record_digests: object,
        selection_digest: object, prompt_block_digest: object,
        retrieval_policy_id: object, history_state_digest: object,
        serving_model_identity_digest: object,
        response_digest: object) -> bool:
    if (not isinstance(value, Mapping)
            or not isinstance(selected_record_ids, list)
            or not isinstance(selected_record_digests, list)
            or len(selected_record_ids) != len(selected_record_digests)
            or not isinstance(selection_digest, str)
            or value.get("schema_version") not in {
                "sentientos.ordinary_history_record_id_citation_audit:v3",
                "sentientos.ordinary_history_record_id_citation_audit:v4"}):
        return False
    optional_fields = {key for key in ("prompt_block_digest", "retrieval_policy_id",
        "history_state_digest", "serving_model_identity_digest") if key in value}
    expected = {"schema_version", "scan_policy_id", "response_text_sha256",
        "response_turn_digest",
        "selection_digest", "citation_posture", "selected_record_ids_cited",
        "selected_record_citations", "unselected_record_id_count",
        "explicit_record_id_count", "scan_complete", "influence_posture",
        "learning_established"} | optional_fields
    cited_ids = value.get("selected_record_ids_cited")
    cited_rows = value.get("selected_record_citations")
    if (set(value) != expected
            or value.get("scan_policy_id") !=
                "exact_devrec_id_tokens_in_saved_assistant_text:v1"
            or not isinstance(value.get("response_text_sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}",
                value["response_text_sha256"]) is None
            or not isinstance(value.get("response_turn_digest"), str)
            or re.fullmatch(r"[0-9a-f]{64}",
                value["response_turn_digest"]) is None
            or value.get("response_turn_digest") != response_digest
            or value.get("selection_digest") != selection_digest
            or not isinstance(cited_ids, list)
            or not isinstance(cited_rows, list)
            or len(cited_ids) != len(cited_rows)
            or len(cited_ids) > len(selected_record_ids)
            or any(not isinstance(record_id, str) for record_id in cited_ids)
            or len(set(cited_ids)) != len(cited_ids)
            or any(not isinstance(record_id, str)
                or record_id not in selected_record_ids for record_id in cited_ids)):
        return False
    for key, expected_value in (
            ("prompt_block_digest", prompt_block_digest),
            ("retrieval_policy_id", retrieval_policy_id),
            ("history_state_digest", history_state_digest),
            ("serving_model_identity_digest", serving_model_identity_digest)):
        if (key in value) != isinstance(expected_value, str):
            return False
        if key in value and value[key] != expected_value:
            return False
    serving_bound = (value.get("schema_version") ==
        "sentientos.ordinary_history_record_id_citation_audit:v4")
    if serving_bound != isinstance(serving_model_identity_digest, str):
        return False
    if (value.get("citation_posture") not in {
            "scan_incomplete_response_length_limit", "no_literal_record_id_citation",
            "selected_record_id_cited", "unselected_record_id_cited",
            "selected_and_unselected_record_ids_cited"}
            or type(value.get("unselected_record_id_count")) is not int
            or value["unselected_record_id_count"] < 0
            or type(value.get("explicit_record_id_count")) is not int
            or value["explicit_record_id_count"] != len(cited_ids)
                + value["unselected_record_id_count"]
            or type(value.get("scan_complete")) is not bool
            or value.get("influence_posture") != "not_measured"
            or value.get("learning_established") is not False):
        return False
    expected_posture = (
        "scan_incomplete_response_length_limit"
        if value["scan_complete"] is False else
        "no_literal_record_id_citation"
        if value["explicit_record_id_count"] == 0 else
        "selected_and_unselected_record_ids_cited"
        if value["unselected_record_id_count"] and cited_ids else
        "unselected_record_id_cited"
        if value["unselected_record_id_count"] else
        "selected_record_id_cited")
    if value["citation_posture"] != expected_posture:
        return False
    digest_by_id = dict(zip(selected_record_ids, selected_record_digests))
    return all(isinstance(row, Mapping)
        and set(row) == {"record_id", "record_digest"}
        and row.get("record_id") == record_id
        and row.get("record_digest") == digest_by_id.get(record_id)
        for record_id, row in zip(cited_ids, cited_rows))


MAX_HISTORY_INTERVENTION_CAPTURE_AGE = timedelta(seconds=60)
MAX_HISTORY_INTERVENTION_FUTURE_SKEW = timedelta(seconds=5)
MAX_COMPANION_CONSEQUENCE_RECORDS = 32


class CognitionEvidenceUnavailable(RuntimeError):
    """No current external or proprioceptive evidence is available for grounding."""

    code = "cognition_current_evidence_unavailable"


@dataclass(frozen=True)
class CompanionDevelopmentalCycleResult(ResidentDevelopmentalCycleResult):
    """Cycle result plus optional post-cognition owner reconciliations."""

    self_model_reconciliation_status: str = "not_configured"
    self_model_reconciliation_id: str | None = None
    self_model_reconciliation_digest: str | None = None
    self_model_reconciliation_generation: int | None = None
    self_model_claim_count: int | None = None
    self_model_reconciliation_error_type: str | None = None
    epistemic_development_status: str = "not_configured"
    epistemic_development_evidence_receipt_ids: tuple[str, ...] = ()
    epistemic_development_state_receipt_ids: tuple[str, ...] = ()
    epistemic_development_successor_state_ids: tuple[str, ...] = ()
    epistemic_development_generations: tuple[int, ...] = ()
    epistemic_development_next_tick_only: bool = True
    epistemic_development_error_type: str | None = None


def _request_bound_capture_freshness(observation: Mapping[str, Any]
        ) -> Mapping[str, Any] | None:
    freshness = observation.get("capture_freshness")
    if freshness is None:
        return None
    if not isinstance(freshness, Mapping) or set(freshness) != {
            "schema_version", "basis", "capture_request_id",
            "capture_age_upper_bound_ms", "freshness_window_ms"}:
        raise DevelopmentalCompanionBridgeError("history_intervention_capture_freshness_invalid")
    request_id = observation.get("capture_request_id")
    age_ms = freshness.get("capture_age_upper_bound_ms")
    window_ms = freshness.get("freshness_window_ms")
    provenance = observation.get("bridge_message_provenance")
    if (freshness.get("schema_version")
            != "sentientos.request_bound_capture_freshness:v1"
            or freshness.get("basis") != "request_correlated_monotonic_upper_bound"
            or not isinstance(request_id, str) or len(request_id) != 32
            or any(character not in "0123456789abcdef" for character in request_id)
            or freshness.get("capture_request_id") != request_id
            or type(age_ms) is not int or not 0 <= age_ms <= 30_000
            or type(window_ms) is not int or not 1 <= window_ms <= 30_000
            or age_ms > window_ms + 1000
            or not isinstance(provenance, Mapping)
            or not isinstance(provenance.get("message_id"), str)
            or len(provenance["message_id"]) != 64
            or any(character not in "0123456789abcdef"
                for character in provenance["message_id"])
            or not isinstance(provenance.get("source_id"), str)
            or not 1 <= len(provenance["source_id"]) <= 128
            or not isinstance(provenance.get("session_id"), str)
            or not 1 <= len(provenance["session_id"]) <= 128
            or not isinstance(provenance.get("generation_id"), str)
            or not 1 <= len(provenance["generation_id"]) <= 128
            or type(provenance.get("sequence")) is not int
            or provenance["sequence"] < 1
            or not isinstance(provenance.get("created_at"), str)
            or len(provenance["created_at"]) > 64
            or not isinstance(provenance.get("payload_digest"), str)
            or len(provenance["payload_digest"]) != 64
            or any(character not in "0123456789abcdef"
                for character in provenance["payload_digest"])
            or not isinstance(provenance.get("signed_envelope_digest"), str)
            or len(provenance["signed_envelope_digest"]) != 64
            or any(character not in "0123456789abcdef"
                for character in provenance["signed_envelope_digest"])):
        raise DevelopmentalCompanionBridgeError("history_intervention_capture_freshness_invalid")
    # The screen provider authenticates and digests its exact bridge payload.
    # RequestDrivenScreenObservation adds freshness (and may add a local text
    # delta) after receipt; neither belongs to that signed payload. Recompute
    # the digest over the remaining fields so a caller cannot mutate OCR,
    # capture identity, or consent metadata while retaining the old provenance.
    signed_payload = {key: value for key, value in observation.items()
        if key not in {"capture_freshness", "bridge_message_provenance", "text_delta"}}
    try:
        payload_bytes = json.dumps(signed_payload, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise DevelopmentalCompanionBridgeError(
            "history_intervention_capture_payload_invalid") from exc
    payload_digest = hashlib.sha256(payload_bytes).hexdigest()
    if payload_digest != provenance["payload_digest"]:
        raise DevelopmentalCompanionBridgeError(
            "history_intervention_capture_payload_digest_mismatch")
    return freshness


def _screen_record(observation: Mapping[str, Any], *, staleness: str = "unknown",
        capture_age_seconds: int | None = None) -> dict[str, Any]:
    if staleness not in {"fresh", "aging", "stale", "expired", "unknown"}:
        raise DevelopmentalCompanionBridgeError("consented_screen_observation_staleness_invalid")
    if (capture_age_seconds is not None
            and (type(capture_age_seconds) is not int or capture_age_seconds < 0
                or capture_age_seconds > 60)):
        raise DevelopmentalCompanionBridgeError("consented_screen_observation_age_invalid")
    request_freshness = _request_bound_capture_freshness(observation)
    text = observation.get("text")
    captured_at = observation.get("captured_at")
    capture_digest = observation.get("capture_digest")
    if (observation.get("modality") != "screen"
            or observation.get("raw_frame_retained") is not False
            or observation.get("capture_scope")
                != "allowlisted_foreground_game_client_area"
            or not isinstance(text, str) or not text.strip() or len(text) > 1200
            or not isinstance(captured_at, str) or len(captured_at) > 64
            or not isinstance(capture_digest, str) or len(capture_digest) != 64
            or any(char not in "0123456789abcdef" for char in capture_digest)):
        raise DevelopmentalCompanionBridgeError("consented_screen_observation_invalid")
    try:
        event_time = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DevelopmentalCompanionBridgeError(
            "consented_screen_observation_time_invalid") from exc
    if event_time.tzinfo is None or event_time.utcoffset() is None:
        raise DevelopmentalCompanionBridgeError(
            "consented_screen_observation_time_invalid")
    text_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "source_kind": "embodiment",
        "source_id": f"consented-screen:{capture_digest}",
        "schema_version": "sentientos.consented_screen_ocr_observation:v1",
        "subject_id": f"game-screen:{capture_digest[:24]}",
        "subject_kind": "allowlisted_foreground_game_screen",
        "stage": "observation",
        "disposition": "captured",
        "evidence_strength": "bounded_local_capture_unverified_issuer",
        "observed_at": captured_at,
        "staleness": staleness,
        "effect_claimed": False,
        "effect_proven": False,
        "payload": {
            "ocr_text": text,
            "text_digest": text_digest,
            "capture_digest": capture_digest,
            "capture_scope": "allowlisted_foreground_game_client_area",
            "raw_frame_retained": False,
            "capture_time_posture": (
                "windows_timestamp_request_correlated_monotonic_age_bound"
                if request_freshness is not None
                else "caller_asserted_local_capture_time"),
            **({"capture_age_seconds": capture_age_seconds,
                "freshness_window_seconds": 60}
                if capture_age_seconds is not None else {}),
            **({
                "capture_request_id": observation["capture_request_id"],
                "capture_freshness_basis": request_freshness["basis"],
                "capture_age_upper_bound_ms": request_freshness["capture_age_upper_bound_ms"],
                "capture_freshness_window_ms": request_freshness["freshness_window_ms"],
                "bridge_message_provenance": {
                    key: observation["bridge_message_provenance"][key]
                    for key in ("message_id", "source_id", "session_id",
                        "generation_id", "sequence", "created_at", "payload_digest",
                        "signed_envelope_digest")
                },
                **({key: observation[key] for key in (
                    "process_name_digest", "consent_id_digest", "backend",
                    "text_status", "text_truncated", "visual_change_kind",
                    "visual_change_score", "component_statuses", "component_failure_codes")
                    if key in observation}),
            } if request_freshness is not None else {}),
        },
    }


def make_operator_feedback_record(feedback: str, *, request_id: str,
        assistant_turn_id: str, assistant_response_digest: str,
        source_capture_digest: str | None, followup_capture_digest: str,
        source_capture_posture: str = "screen_capture_bound",
        source_user_turn_id: str | None = None,
        observed_at: str, conversation_citation_ids: Sequence[str] = (),
        conversation_citation_digests: Sequence[str] = (),
        conversation_session_id: str | None = None,
        correction_target_turn_id: str | None = None,
        correction_target_epistemic_state_ids: Sequence[str] = (),
        developmental_history_exposure: Mapping[str, Any] | None = None,
        ) -> dict[str, Any]:
    """Represent explicit local operator feedback as an unverified report.

    Conversation-only feedback binds the source user/assistant turns and session
    but carries no fabricated screen-capture digest.
    """
    citation_pattern = re.compile(r"^turn-[0-9a-f]{24}$")
    history_exposure: dict[str, Any] | None = None
    if developmental_history_exposure is not None:
        if not isinstance(developmental_history_exposure, Mapping):
            raise DevelopmentalCompanionBridgeError(
                "operator_feedback_history_exposure_invalid")
        base_exposure_fields = {"context_posture", "selection_digest",
            "record_ids", "record_digests"}
        optional_exposure_fields = {key for key in (
            "prompt_block_digest", "retrieval_policy_id",
            "target_model_identity_digest", "history_state_digest",
            "serving_model_identity_digest", "citation_audit")
            if key in developmental_history_exposure}
        expected_exposure_fields = base_exposure_fields | optional_exposure_fields
        exposure_postures = {
            "selected", "provider_returned_no_context", "provider_unavailable",
            "provider_failed", "context_validation_failed",
            "prompt_budget_unavailable", "prompt_budget_rejected", "not_considered",
        }
        context_posture = developmental_history_exposure.get("context_posture")
        selection_digest = developmental_history_exposure.get("selection_digest")
        record_ids = developmental_history_exposure.get("record_ids")
        record_digests = developmental_history_exposure.get("record_digests")
        prompt_block_digest = developmental_history_exposure.get(
            "prompt_block_digest")
        retrieval_policy_id = developmental_history_exposure.get(
            "retrieval_policy_id")
        target_model_identity_digest = developmental_history_exposure.get(
            "target_model_identity_digest")
        history_state_digest = developmental_history_exposure.get(
            "history_state_digest")
        serving_model_identity_digest = developmental_history_exposure.get(
            "serving_model_identity_digest")
        citation_audit = developmental_history_exposure.get("citation_audit")
        has_prompt_block_digest = "prompt_block_digest" in developmental_history_exposure
        has_retrieval_policy_id = "retrieval_policy_id" in developmental_history_exposure
        has_target_model_identity_digest = (
            "target_model_identity_digest" in developmental_history_exposure)
        has_history_state_digest = (
            "history_state_digest" in developmental_history_exposure)
        has_serving_model_identity_digest = (
            "serving_model_identity_digest" in developmental_history_exposure)
        has_citation_audit = "citation_audit" in developmental_history_exposure
        if (set(developmental_history_exposure) != expected_exposure_fields
                or not isinstance(context_posture, str)
                or context_posture not in exposure_postures
                or not isinstance(record_ids, list)
                or not isinstance(record_digests, list)
                or len(record_ids) != len(record_digests) or len(record_ids) > 16
                or any(not isinstance(item, str) or not item or len(item) > 256
                    for item in record_ids)
                or len(set(record_ids)) != len(record_ids)
                or any(not isinstance(item, str)
                    or re.fullmatch(r"sha256:[0-9a-f]{64}", item) is None
                    for item in record_digests)
                or (has_prompt_block_digest
                    and (not isinstance(prompt_block_digest, str)
                        or re.fullmatch(r"[0-9a-f]{64}", prompt_block_digest) is None
                        or context_posture != "selected"))
                or (has_retrieval_policy_id
                    and (not isinstance(retrieval_policy_id, str)
                        or re.fullmatch(r"[a-z0-9_.:-]{1,512}",
                            retrieval_policy_id) is None
                        or context_posture != "selected"
                        or not has_prompt_block_digest))
                or (has_target_model_identity_digest
                    and (not isinstance(target_model_identity_digest, str)
                        or re.fullmatch(r"[0-9a-f]{64}",
                            target_model_identity_digest) is None
                        or context_posture != "selected"))
                or (has_history_state_digest
                    and (not isinstance(history_state_digest, str)
                        or re.fullmatch(r"sha256:[0-9a-f]{64}",
                            history_state_digest) is None
                        or context_posture != "selected"))
                or (has_serving_model_identity_digest
                    and (not isinstance(serving_model_identity_digest, str)
                        or re.fullmatch(r"[0-9a-f]{64}",
                            serving_model_identity_digest) is None
                        or context_posture != "selected"))
                or (has_citation_audit
                    and not _valid_history_citation_audit(citation_audit,
                        selected_record_ids=record_ids,
                        selected_record_digests=record_digests,
                        selection_digest=selection_digest,
                        prompt_block_digest=prompt_block_digest,
                        retrieval_policy_id=retrieval_policy_id,
                        history_state_digest=history_state_digest,
                        serving_model_identity_digest=serving_model_identity_digest,
                        response_digest=assistant_response_digest))
                or (context_posture == "selected"
                    and (not record_ids or not isinstance(selection_digest, str)
                        or re.fullmatch(r"[0-9a-f]{64}", selection_digest) is None))
                or (context_posture != "selected"
                    and (selection_digest is not None or record_ids or record_digests))):
            raise DevelopmentalCompanionBridgeError(
                "operator_feedback_history_exposure_invalid")
        history_exposure = {"context_posture": context_posture,
            "selection_digest": selection_digest,
            "record_ids": list(record_ids),
            "record_digests": list(record_digests)}
        if has_prompt_block_digest:
            history_exposure["prompt_block_digest"] = prompt_block_digest
        if has_retrieval_policy_id:
            history_exposure["retrieval_policy_id"] = retrieval_policy_id
        if has_target_model_identity_digest:
            history_exposure["target_model_identity_digest"] = (
                target_model_identity_digest)
        if has_history_state_digest:
            history_exposure["history_state_digest"] = history_state_digest
        if has_serving_model_identity_digest:
            history_exposure["serving_model_identity_digest"] = (
                serving_model_identity_digest)
        if has_citation_audit:
            history_exposure["citation_audit"] = dict(citation_audit)
    if (not isinstance(feedback, str) or not feedback.strip()
            or len(feedback) > 800 or len(feedback.encode("utf-8")) > 2048
            or not isinstance(request_id, str) or not request_id
            or not isinstance(assistant_turn_id, str) or not assistant_turn_id
            or not isinstance(assistant_response_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", assistant_response_digest) is None
            or not isinstance(source_capture_posture, str)
            or source_capture_posture not in {
                "screen_capture_bound", "conversation_turns_only"}
            or (source_capture_posture == "screen_capture_bound"
                and (not isinstance(source_capture_digest, str)
                    or re.fullmatch(r"[0-9a-f]{64}", source_capture_digest) is None))
            or (source_capture_posture == "conversation_turns_only"
                and (source_capture_digest is not None
                    or not isinstance(source_user_turn_id, str)
                    or citation_pattern.fullmatch(source_user_turn_id) is None))
            or not isinstance(followup_capture_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", followup_capture_digest) is None
            or not isinstance(observed_at, str) or not observed_at
            or not isinstance(conversation_citation_ids, (tuple, list))
            or not isinstance(conversation_citation_digests, (tuple, list))
            or len(conversation_citation_ids) != len(conversation_citation_digests)
            or len(conversation_citation_ids) > 16
            or any(not isinstance(turn_id, str) or citation_pattern.fullmatch(turn_id) is None
                for turn_id in conversation_citation_ids)
            or len(set(conversation_citation_ids)) != len(conversation_citation_ids)
            or not isinstance(correction_target_epistemic_state_ids, (tuple, list))
            or len(correction_target_epistemic_state_ids) > 16
            or any(not isinstance(state_id, str)
                or re.fullmatch(r"epistemic-state:[0-9a-f]{24}", state_id) is None
                for state_id in correction_target_epistemic_state_ids)
            or len(set(correction_target_epistemic_state_ids))
                != len(correction_target_epistemic_state_ids)
            or (correction_target_epistemic_state_ids
                and correction_target_turn_id is None)
            or any(not isinstance(digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                for digest in conversation_citation_digests)
            or (conversation_session_id is not None
                and (not isinstance(conversation_session_id, str)
                    or re.fullmatch(r"[a-z0-9][a-z0-9-]{7,63}",
                        conversation_session_id) is None))
            or (developmental_history_exposure is not None
                and conversation_session_id is None)
            or (source_capture_posture == "conversation_turns_only"
                and (conversation_session_id is None
                    or source_user_turn_id == assistant_turn_id
                    or len(conversation_citation_ids) < 2
                    or not any(turn_id == source_user_turn_id
                        for turn_id in conversation_citation_ids)
                    or not any(turn_id == assistant_turn_id
                        and digest == assistant_response_digest
                        for turn_id, digest in zip(conversation_citation_ids,
                            conversation_citation_digests))))
            or (history_exposure is not None
                and "prompt_block_digest" in history_exposure
                and not any(turn_id == assistant_turn_id
                    and digest == assistant_response_digest
                    for turn_id, digest in zip(conversation_citation_ids,
                        conversation_citation_digests)))
            or (correction_target_turn_id is not None
                and (not isinstance(correction_target_turn_id, str)
                    or citation_pattern.fullmatch(correction_target_turn_id) is None
                    or correction_target_turn_id not in conversation_citation_ids
                    or conversation_session_id is None))):
        raise DevelopmentalCompanionBridgeError(
            "operator_feedback_contract_invalid")
    normalized = feedback.strip()
    schema_version = ("sentientos.local_operator_feedback:v12"
        if history_exposure is not None and "citation_audit" in history_exposure else
        "sentientos.local_operator_feedback:v11"
        if history_exposure is not None
            and "serving_model_identity_digest" in history_exposure else
        "sentientos.local_operator_feedback:v10"
        if history_exposure is not None
            and "target_model_identity_digest" in history_exposure else
        "sentientos.local_operator_feedback:v9"
        if source_capture_posture == "conversation_turns_only" else
        "sentientos.local_operator_feedback:v8"
        if history_exposure is not None
            and "retrieval_policy_id" in history_exposure else
        "sentientos.local_operator_feedback:v7"
        if history_exposure is not None
            and "prompt_block_digest" in history_exposure else
        "sentientos.local_operator_feedback:v6"
        if history_exposure is not None else
        "sentientos.local_operator_feedback:v5"
        if correction_target_turn_id is not None
            and correction_target_epistemic_state_ids else
        "sentientos.local_operator_feedback:v4"
        if correction_target_turn_id is not None else
        "sentientos.local_operator_feedback:v3"
        if conversation_session_id is not None else
        "sentientos.local_operator_feedback:v2")
    semantic: dict[str, Any] = {
        "schema_version": schema_version,
        "request_id": request_id,
        "assistant_turn_id": assistant_turn_id,
        "assistant_response_digest": assistant_response_digest,
        "source_capture_digest": source_capture_digest,
        "followup_capture_digest": followup_capture_digest,
        "conversation_citations": [
            {"turn_id": turn_id, "text_digest": digest}
            for turn_id, digest in zip(conversation_citation_ids,
                conversation_citation_digests)],
        "assertion_text": normalized,
        "assertion_digest": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        "evidence_posture": "operator_assertion_unverified",
        "authority": {"decision": False, "admission": False,
            "execution": False, "adoption": False, "truth": False},
    }
    if schema_version == "sentientos.local_operator_feedback:v9":
        semantic["source_capture_posture"] = source_capture_posture
        semantic["source_user_turn_id"] = source_user_turn_id
    elif schema_version in {"sentientos.local_operator_feedback:v10",
            "sentientos.local_operator_feedback:v11",
            "sentientos.local_operator_feedback:v12"}:
        semantic["source_capture_posture"] = source_capture_posture
        if source_capture_posture == "conversation_turns_only":
            semantic["source_user_turn_id"] = source_user_turn_id
    if conversation_session_id is not None:
        semantic["conversation_session_id"] = conversation_session_id
    if correction_target_turn_id is not None:
        target_index = conversation_citation_ids.index(correction_target_turn_id)
        semantic["correction_target"] = {
            "turn_id": correction_target_turn_id,
            "text_digest": conversation_citation_digests[target_index],
        }
        if correction_target_epistemic_state_ids:
            semantic["correction_target"]["epistemic_state_citation_ids"] = list(
                correction_target_epistemic_state_ids)
    if history_exposure is not None:
        semantic["developmental_history_exposure"] = history_exposure
    identity = hashlib.sha256(json.dumps(semantic, sort_keys=True,
        separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
    return {
        "source_kind": "operator_input",
        "source_id": f"local-operator-feedback:{identity}",
        "schema_version": semantic["schema_version"],
        "subject_id": f"assistant-turn:{assistant_turn_id}",
        "subject_kind": "operator_reported_companion_feedback",
        "stage": "observation",
        "disposition": "reported",
        "evidence_strength": "operator_assertion_unverified",
        "observed_at": observed_at,
        "staleness": "fresh",
        "effect_claimed": False,
        "effect_proven": False,
        "payload": semantic,
    }


def build_companion_snapshot(*, screen_observation: Mapping[str, Any] | None = None,
        proprioception: Sequence[EmbodimentObservation] = (),
        operator_feedback: Mapping[str, Any] | None = None,
        historical_consequence_records: Sequence[Mapping[str, Any]] = (),
        current_consequence_records: Sequence[Mapping[str, Any]] = (),
        screen_staleness: str = "unknown",
        screen_capture_age_seconds: int | None = None,
        clock: Any | None = None) -> WorldStateSnapshot:
    """Build one bounded snapshot; source provenance remains explicitly qualified."""
    records: list[Mapping[str, Any]] = []
    if screen_observation is not None:
        if not isinstance(screen_observation, Mapping):
            raise DevelopmentalCompanionBridgeError("consented_screen_observation_invalid")
        records.append(_screen_record(screen_observation, staleness=screen_staleness,
            capture_age_seconds=screen_capture_age_seconds))
    if operator_feedback is not None:
        if not isinstance(operator_feedback, Mapping):
            raise DevelopmentalCompanionBridgeError(
                "operator_feedback_contract_invalid")
        records.append(dict(operator_feedback))
    if proprioception:
        try:
            records.extend(EmbodimentEvidenceOwner(proprioception).world_state_records())
        except (TypeError, ValueError) as exc:
            raise DevelopmentalCompanionBridgeError(
                "proprioception_evidence_invalid") from exc
    if (not isinstance(historical_consequence_records, (tuple, list))
            or len(historical_consequence_records) > MAX_COMPANION_CONSEQUENCE_RECORDS
            or any(not isinstance(item, Mapping)
                or item.get("source_kind") != "embodiment"
                or not isinstance(item.get("digest"), str)
                or item.get("digest") != record_digest(item)
                or type(item.get("effect_claimed", False)) is not bool
                or type(item.get("effect_proven", False)) is not bool
                for item in historical_consequence_records)):
        raise DevelopmentalCompanionBridgeError(
            "historical_consequence_projection_invalid")
    if (not isinstance(current_consequence_records, (tuple, list))
            or len(current_consequence_records) > MAX_COMPANION_CONSEQUENCE_RECORDS
            or any(not isinstance(item, Mapping)
                or item.get("source_kind") != "embodiment"
                or not isinstance(item.get("digest"), str)
                or item.get("digest") != record_digest(item)
                or type(item.get("effect_claimed", False)) is not bool
                or type(item.get("effect_proven", False)) is not bool
                for item in current_consequence_records)):
        raise DevelopmentalCompanionBridgeError(
            "current_consequence_evidence_invalid")
    if len(historical_consequence_records) + len(current_consequence_records) > \
            MAX_COMPANION_CONSEQUENCE_RECORDS:
        raise DevelopmentalCompanionBridgeError(
            "companion_consequence_record_bound_exceeded")
    # Selected, verified historical records retain their timestamps and
    # uncertainty. The bridge never upgrades them into fresh observations.
    records.extend(historical_consequence_records)
    # A just-measured consequence retains its own event time and uncertainty.
    # It is never promoted to a proven effect.
    records.extend(current_consequence_records)
    if len(records) > 64:
        raise DevelopmentalCompanionBridgeError(
            "companion_snapshot_source_bound_exceeded")
    return WorldStateBoardBuilder(clock=clock).build(records)


class ResidentDevelopmentalCompanionBridge:
    """Route one user turn through the existing resident cognition owner."""

    def __init__(self, owner: ResidentDevelopmentalCognitionOwner, *,
                 history_intervention_owner: ResidentDevelopmentalCognitionOwner | None = None,
                 proprioception_provider: Any | None = None,
                 consequence_records_provider: Any | None = None,
                 self_model_owner: Any | None = None,
                 self_model_config: LongitudinalSelfModelRuntimeConfig | None = None,
                 epistemic_state_owner: PersistentEpistemicStateOwner | None = None,
                 epistemic_state_config: Mapping[str, Any] | None = None,
                 epistemic_development_runtime: Any | None = None,
                 cognition_inference_gate: Any | None = None,
                 cognition_available: Any | None = None,
                 clock: Any | None = None) -> None:
        if not isinstance(owner, ResidentDevelopmentalCognitionOwner):
            raise TypeError("resident_developmental_cognition_owner_required")
        if history_intervention_owner is not None:
            if not isinstance(history_intervention_owner,
                    ResidentDevelopmentalCognitionOwner):
                raise TypeError("resident_history_intervention_owner_required")
            if (history_intervention_owner.config.history_root
                    != owner.config.history_root
                    or history_intervention_owner.config.state_root
                    != owner.config.state_root
                    or history_intervention_owner.writeback is not owner.writeback
                    or history_intervention_owner.invoker is not owner.invoker):
                raise ValueError("resident_history_intervention_owner_composition_mismatch")
        if (proprioception_provider is not None
                and not callable(proprioception_provider)):
            raise TypeError("proprioception_provider_must_be_callable")
        if (consequence_records_provider is not None
                and not callable(consequence_records_provider)):
            raise TypeError("consequence_records_provider_must_be_callable")
        if cognition_inference_gate is not None and not callable(cognition_inference_gate):
            raise TypeError("cognition_inference_gate_invalid")
        if cognition_available is not None and not callable(cognition_available):
            raise TypeError("cognition_availability_provider_invalid")
        if (self_model_owner is not None
                and not callable(getattr(self_model_owner, "cognitive_projection", None))):
            raise TypeError("self_model_projection_owner_invalid")
        if (self_model_owner is not None and self_model_config is not None
                and self_model_config.enabled
                and not callable(getattr(self_model_owner, "reconcile", None))):
            raise TypeError("self_model_reconciliation_owner_invalid")
        if (self_model_config is not None and self_model_config.enabled
                and self_model_config.cognitive_consumption_enabled
                and self_model_owner is None):
            raise ValueError("enabled_self_model_projection_owner_required")
        epistemic_config = dict(epistemic_state_config or {})
        if epistemic_state_owner is not None and not epistemic_config:
            raise ValueError("epistemic_state_projection_config_required")
        if (epistemic_config.get("cognitive_consumption_enabled") is True
                and epistemic_state_owner is None):
            raise ValueError("enabled_epistemic_projection_owner_required")
        if epistemic_development_runtime is not None:
            if epistemic_state_owner is None:
                raise ValueError("epistemic_development_state_owner_required")
            if getattr(epistemic_development_runtime, "owner", None) is not epistemic_state_owner:
                raise ValueError("epistemic_development_owner_composition_mismatch")
            if not callable(getattr(epistemic_development_runtime,
                    "process_snapshot", None)):
                raise TypeError("epistemic_development_runtime_invalid")
        self._owner = owner
        # Keep interactive inference in non-comparison mode. The separately
        # configured owner runs only the explicitly confirmed A/B/A experiment.
        self._history_intervention_owner = history_intervention_owner or owner
        self._proprioception_provider = proprioception_provider
        self._consequence_records_provider = consequence_records_provider
        self._self_model_owner = self_model_owner
        self._self_model_config = self_model_config
        self._epistemic_state_owner = epistemic_state_owner
        self._epistemic_state_config = epistemic_config
        self._epistemic_development_runtime = epistemic_development_runtime
        self._cognition_inference_gate = cognition_inference_gate
        self._cognition_available = cognition_available
        self._clock = clock

    def verify_committed_response(self, *, linkage: Mapping[str, Any],
            response_text: str, request_id: str) -> bool:
        """Verify transcript delivery against the durable owner observation and receipt."""
        try:
            observation_id = linkage.get("cognition_observation_id")
            observation_digest = linkage.get("cognition_observation_digest")
            observation = self._owner.verified_cognition_observation(
                str(observation_id), str(observation_digest))
            expected_tick = "companion-interaction-" + hashlib.sha256(
                request_id.encode("utf-8")).hexdigest()[:32]
            text_digest = digest_payload({"text": response_text})
            history_record_ids = linkage.get("cognition_history_record_ids", [])
            retrieved_record_ids = observation.get("retrieved_record_ids", ())
            history_lineage_valid = (
                isinstance(history_record_ids, list)
                and all(isinstance(item, str) for item in history_record_ids)
                and len(set(history_record_ids)) == len(history_record_ids)
                and isinstance(retrieved_record_ids, (list, tuple))
                and all(isinstance(item, str) for item in retrieved_record_ids)
                and set(history_record_ids).issubset(retrieved_record_ids))
            if observation.get("schema_version") == "sentientos.resident_cognition_observation:v8":
                memory_lineage_valid = (
                    "cognition_memory_selection_digest" not in linkage
                    and "cognition_memory_citation_ids" not in linkage)
            else:
                memory_citation_ids = linkage.get("cognition_memory_citation_ids", ())
                memory_lineage_valid = (
                    observation.get("schema_version")
                        in {"sentientos.resident_cognition_observation:v9",
                            "sentientos.resident_cognition_observation:v10",
                            "sentientos.resident_cognition_observation:v11",
                            "sentientos.resident_cognition_observation:v12",
                            "sentientos.resident_cognition_observation:v13",
                            "sentientos.resident_cognition_observation:v14", "sentientos.resident_cognition_observation:v15", "sentientos.resident_cognition_observation:v16"}
                    and linkage.get("cognition_memory_selection_digest")
                        == observation.get("canonical_user_memory_selection_digest")
                    and isinstance(memory_citation_ids, (list, tuple))
                    and list(memory_citation_ids)
                        == list(observation.get("companion_memory_citation_ids", ()))
                    and set(memory_citation_ids) <=
                        set(observation.get("canonical_user_memory_record_ids", ())))
            if observation.get("schema_version") in {
                    "sentientos.resident_cognition_observation:v11",
                    "sentientos.resident_cognition_observation:v12",
                    "sentientos.resident_cognition_observation:v13",
                    "sentientos.resident_cognition_observation:v14", "sentientos.resident_cognition_observation:v15", "sentientos.resident_cognition_observation:v16"}:
                self_model_citation_ids = linkage.get(
                    "cognition_self_model_claim_ids", ())
                selection = observation.get("prior_self_model_prompt_selection")
                selected_ids = (selection.get("selected_claim_ids", ())
                    if isinstance(selection, Mapping) else ())
                self_model_lineage_valid = (
                    isinstance(self_model_citation_ids, (list, tuple))
                    and list(self_model_citation_ids) == list(observation.get(
                        "companion_self_model_citation_ids", ()))
                    and len(set(self_model_citation_ids)) == len(self_model_citation_ids)
                    and set(self_model_citation_ids) <= set(selected_ids))
            else:
                self_model_lineage_valid = "cognition_self_model_claim_ids" not in linkage
            return (
                linkage.get("response_origin") == "resident_developmental_cognition"
                and observation.get("condition_id") == "companion-interaction"
                and observation.get("tick_id") == expected_tick
                and observation.get("correlation_id") ==
                    f"{expected_tick}:resident_developmental_cognition:companion-interaction"
                and linkage.get("cognition_snapshot_id") ==
                    observation.get("current_snapshot_id")
                and linkage.get("cognition_snapshot_digest") ==
                    observation.get("current_snapshot_digest")
                and linkage.get("inference_receipt_id") ==
                    observation.get("inference_receipt_id")
                and linkage.get("inference_receipt_digest") ==
                    observation.get("inference_receipt_digest")
                and linkage.get("invocation_output_digest") ==
                    observation.get("output_digest")
                and linkage.get("response_digest") == text_digest
                and linkage.get("assistant_output_lineage") == {
                    "status": "resident_cognition_interaction",
                    "cognition_observation_id": observation_id,
                    "cognition_observation_digest": observation_digest,
                    "inference_receipt_id": observation.get("inference_receipt_id"),
                    "inference_receipt_digest": observation.get("inference_receipt_digest"),
                    "invocation_output_digest": observation.get("output_digest"),
                    "response_digest": text_digest,
                }
                and linkage.get("cognition_evidence_ids") ==
                    list(linkage.get("cognition_evidence_ids", ()))
                and set(linkage.get("cognition_evidence_ids", ())) <=
                    set(observation.get("current_fact_ids", ()))
                and linkage.get("cognition_prior_record_ids") ==
                    list(observation.get("retrieved_record_ids", ()))
                and observation.get("schema_version") in {
                    "sentientos.resident_cognition_observation:v8",
                    "sentientos.resident_cognition_observation:v9",
                    "sentientos.resident_cognition_observation:v10",
                    "sentientos.resident_cognition_observation:v11",
                    "sentientos.resident_cognition_observation:v12",
                    "sentientos.resident_cognition_observation:v13",
                    "sentientos.resident_cognition_observation:v14", "sentientos.resident_cognition_observation:v15", "sentientos.resident_cognition_observation:v16"}
                and observation.get("companion_history_citation_ids") == list(history_record_ids)
                and memory_lineage_valid
                and self_model_lineage_valid
                and (observation.get("schema_version") not in {
                    "sentientos.resident_cognition_observation:v12",
                    "sentientos.resident_cognition_observation:v13",
                    "sentientos.resident_cognition_observation:v14", "sentientos.resident_cognition_observation:v15", "sentientos.resident_cognition_observation:v16"} or (
                    linkage.get("conversation_context_snapshot_digest") ==
                        observation.get("companion_conversation_context_snapshot_digest")
                    and linkage.get("conversation_context_selection_digest") ==
                        observation.get("companion_conversation_context_selection_digest")
                    and linkage.get("conversation_context_turn_ids", []) == list(
                        observation.get("companion_conversation_context_turn_ids", ()))
                    and linkage.get("conversation_context_turn_text_digests", []) == list(
                        observation.get("companion_conversation_context_turn_digests", ()))
                    and linkage.get("cognition_conversation_turn_citation_ids", []) == list(
                        observation.get("companion_conversation_citation_ids", ()))
                    and linkage.get("cognition_conversation_turn_citation_digests", []) == list(
                        observation.get("companion_conversation_citation_digests", ()))
                    ))
                and (observation.get("schema_version") not in {
                    "sentientos.resident_cognition_observation:v15",
                    "sentientos.resident_cognition_observation:v16"} or (
                    linkage.get("cognition_historical_conversation_citation_ids", []) == list(
                        observation.get("companion_historical_conversation_citation_ids", ()))
                    and linkage.get("cognition_historical_conversation_citation_digests", []) == list(
                        observation.get("companion_historical_conversation_citation_digests", ()))
                    and len(observation.get(
                        "companion_historical_conversation_citation_ids", ())) ==
                        len(observation.get(
                            "companion_historical_conversation_citation_digests", ()))
                    and set(zip(
                        observation.get("companion_historical_conversation_citation_ids", ()),
                        observation.get("companion_historical_conversation_citation_digests", ())))
                        <= set(zip(
                            observation.get("companion_historical_citation_turn_ids", ()),
                            observation.get("companion_historical_citation_turn_digests", ())))
                    ))
                and history_lineage_valid
                and linkage.get("cognition_model_id") == observation.get("model_id")
                and linkage.get("cognition_model_artifact_digest") ==
                    observation.get("model_artifact_digest")
                and linkage.get("self_model_projection_id") ==
                    observation.get("self_model_projection_id")
                and linkage.get("self_model_projection_digest") ==
                    observation.get("self_model_projection_digest")
                and linkage.get("epistemic_projection_id") ==
                    observation.get("epistemic_projection_id")
                and linkage.get("epistemic_projection_digest") ==
                    observation.get("epistemic_projection_digest")
                and linkage.get("cognition_epistemic_state_citation_ids", []) == list(
                    observation.get("companion_epistemic_state_citation_ids", ()))
            )
        except Exception:
            return False

    def _projection_boundary(self) -> tuple[str, int]:
        now = self._clock() if callable(self._clock) else datetime.now(timezone.utc)
        if isinstance(now, str):
            try:
                now = datetime.fromisoformat(now.replace("Z", "+00:00"))
            except ValueError as exc:
                raise DevelopmentalCompanionBridgeError(
                    "cognitive_projection_time_invalid") from exc
        if (not isinstance(now, datetime) or now.tzinfo is None
                or now.utcoffset() is None):
            raise DevelopmentalCompanionBridgeError(
                "cognitive_projection_time_invalid")
        tick_id = now.isoformat()
        if tick_id.endswith("-00:00"):
            raise DevelopmentalCompanionBridgeError(
                "cognitive_projection_time_offset_unknown")
        try:
            projection_tick = int(now.timestamp())
        except (OSError, OverflowError, ValueError) as exc:
            raise DevelopmentalCompanionBridgeError(
                "cognitive_projection_time_unrepresentable") from exc
        return tick_id, projection_tick

    def _prior_cognitive_context(self, *, tick_id: str,
            projection_tick: int,
            relevance_query: str | None = None,
            prioritized_epistemic_state_ids: Sequence[str] = ()
            ) -> tuple[Any | None, Any | None]:
        prior_self_model = None
        config = self._self_model_config
        if (config is not None and config.enabled
                and config.cognitive_consumption_enabled):
            if self._self_model_owner is None:
                raise DevelopmentalCompanionBridgeError(
                    "enabled_self_model_projection_owner_required")
            prior_self_model = self._self_model_owner.cognitive_projection(
                before_tick=tick_id, max_claims=config.max_projection_claims,
                allowed_predicates=config.allowed_predicates,
                relevance_query=relevance_query)
        prior_epistemic_state = None
        if (self._epistemic_state_owner is not None
                and self._epistemic_state_config.get(
                    "cognitive_consumption_enabled") is True):
            maximum = self._epistemic_state_config.get(
                "max_cognitive_projection_count")
            if (not isinstance(maximum, int) or isinstance(maximum, bool)
                    or not 1 <= maximum <= 128):
                raise DevelopmentalCompanionBridgeError(
                    "epistemic_projection_bound_invalid")
            developmental_config = getattr(getattr(getattr(self, "_owner", None),
                "config", None), "semantic_history_model_id", None)
            developmental_revision = getattr(getattr(getattr(self, "_owner", None),
                "config", None), "semantic_history_model_revision", None)
            semantic_config = ({"semantic_model_id": developmental_config,
                "semantic_model_revision": developmental_revision}
                if developmental_config is not None and developmental_revision is not None
                else {})
            prior_epistemic_state = self._epistemic_state_owner.cognitive_projection(
                max_states=maximum, current_tick=projection_tick,
                prioritized_state_ids=prioritized_epistemic_state_ids,
                relevance_query=relevance_query,
                **semantic_config)
        return prior_self_model, prior_epistemic_state

    def can_handle(self) -> bool:
        if self._cognition_available is None:
            return True
        try:
            return self._cognition_available() is True
        except Exception:
            return False

    def semantic_memory_retrieval_config(self) -> tuple[str, str] | None:
        """Expose the already pinned local semantic encoder to memory retrieval."""
        config = getattr(getattr(self, "_owner", None), "config", None)
        model_id = getattr(config, "semantic_history_model_id", None)
        revision = getattr(config, "semantic_history_model_revision", None)
        if (not isinstance(model_id, str) or not model_id
                or not isinstance(revision, str)
                or re.fullmatch(r"[0-9a-f]{40}", revision) is None):
            return None
        return model_id, revision

    def ordinary_chat_epistemic_context(self, *, question: str,
            max_input_chars: int = 8000) -> dict[str, Any] | None:
        """Return bounded, prior-only epistemic context for ordinary fallback chat."""
        owner = self._epistemic_state_owner
        if (owner is None or self._epistemic_state_config.get(
                "cognitive_consumption_enabled") is not True):
            return None
        if (not isinstance(question, str) or not question.strip()
                or len(question) > 1200
                or not isinstance(max_input_chars, int)
                or isinstance(max_input_chars, bool)
                or not 128 <= max_input_chars <= MAX_RESIDENT_COGNITION_INPUT_CHARS):
            raise DevelopmentalCompanionBridgeError(
                "ordinary_chat_epistemic_context_request_invalid")
        maximum = self._epistemic_state_config.get(
            "max_cognitive_projection_count")
        if (not isinstance(maximum, int) or isinstance(maximum, bool)
                or not 1 <= maximum <= 128):
            raise DevelopmentalCompanionBridgeError(
                "epistemic_projection_bound_invalid")
        tick_id, projection_tick = self._projection_boundary()
        projection = owner.cognitive_projection(max_states=maximum,
            current_tick=projection_tick, relevance_query=question)
        if projection is None:
            return None
        evaluation_time = datetime.fromisoformat(tick_id).isoformat()
        instruction = (
            "This prior epistemic position is historical context selected by the "
            "verified epistemic owner. Use its complete source-bound packets as "
            "defeasible knowledge when relevant; preserve recorded uncertainty and "
            "freshness limits. It is not current evidence, truth, policy, authority, "
            "or permission to mutate epistemic state. Omitted propositions are "
            "unknown to this prompt, not absent or resolved.")
        bound, _metadata, _prompt = bind_epistemic_cognitive_context(
            context={"instruction": instruction}, projection=projection,
            evaluation_time=evaluation_time, max_input_chars=max_input_chars)
        prior = bound.get("prior_epistemic_state")
        if not isinstance(prior, Mapping):
            return None
        packets = prior.get("semantic_packets")
        if not isinstance(packets, (list, tuple)) or not packets:
            return None
        semantic = {
            "schema_version": "sentientos.ordinary_chat_epistemic_context:v1",
            "instruction": bound.get("instruction", instruction),
            "prior_epistemic_state": dict(prior),
            "historical_only": True, "current_truth": False,
            "authority": False, "mutation_performed": False,
        }
        return {**semantic, "selection_digest": digest_payload(semantic)}

    def ordinary_chat_developmental_history_context(self, *, question: str,
            max_input_chars: int = 8000) -> dict[str, Any] | None:
        """Expose verified developmental history without enabling writeback."""
        owner = self._owner
        if (owner is None or getattr(getattr(owner, "config", None),
                "enabled", False) is not True):
            return None
        provider = getattr(owner,
            "ordinary_chat_developmental_history_context", None)
        if not callable(provider):
            return None
        return provider(question=question, max_input_chars=max_input_chars)

    def ordinary_chat_developmental_history_context_for_model(self, *,
            question: str, target_model_identity: Mapping[str, Any] | None = None,
            max_input_chars: int = 8000) -> dict[str, Any] | None:
        """Rank ordinary-chat history against the exact serving model identity."""
        if (target_model_identity is not None
                and not isinstance(target_model_identity, Mapping)):
            raise DevelopmentalCompanionBridgeError(
                "ordinary_chat_target_model_identity_invalid")
        owner = self._owner
        if (owner is None or getattr(getattr(owner, "config", None),
                "enabled", False) is not True):
            return None
        provider = getattr(owner,
            "ordinary_chat_developmental_history_context_for_model", None)
        if callable(provider):
            return provider(question=question,
                target_model_identity=target_model_identity,
                max_input_chars=max_input_chars)
        # Older owners expose only the model-independent interface. Preserve
        # compatibility while making the loss of model-aware ranking explicit
        # in the owner capability rather than silently breaking ordinary chat.
        return self.ordinary_chat_developmental_history_context(
            question=question, max_input_chars=max_input_chars)

    def history_intervention_available(self) -> bool:
        """Whether the existing three-condition cognition experiment is enabled."""
        owner = self._history_intervention_owner
        return (self.can_handle()
            and owner.config.enabled is True
            and owner.config.comparison_enabled is True
            and owner.objective_task is None
            and "embodiment" in owner.config.allowed_source_kinds)

    def compare_history_intervention(self, *, tick_id: str, question: str,
            screen_observation: Mapping[str, Any]
            ) -> ResidentCompanionHistoryInterventionResult:
        """Run the existing history-present/withheld/restored experiment on fresh evidence.

        This explicit experiment makes up to four governed local inference calls, grants
        no action authority, and does not treat a screen capture as verified truth.
        """
        if (not isinstance(tick_id, str) or not tick_id.strip() or len(tick_id) > 256
                or not isinstance(question, str) or not question.strip()
                or len(question) > 1200 or not isinstance(screen_observation, Mapping)):
            raise DevelopmentalCompanionBridgeError(
                "history_intervention_request_invalid")
        if not self.history_intervention_available():
            raise CognitionWorkloadUnavailable()
        proprioception: Sequence[EmbodimentObservation] = ()
        if self._proprioception_provider is not None:
            value = self._proprioception_provider()
            if not isinstance(value, (tuple, list)) or any(
                    not isinstance(item, EmbodimentObservation) for item in value):
                raise DevelopmentalCompanionBridgeError(
                    "proprioception_provider_output_invalid")
            proprioception = tuple(value)
        _screen_record(screen_observation)
        now = self._clock() if callable(self._clock) else datetime.now(timezone.utc)
        if isinstance(now, str):
            try:
                now = datetime.fromisoformat(now.replace("Z", "+00:00"))
            except ValueError as exc:
                raise DevelopmentalCompanionBridgeError(
                    "history_intervention_clock_invalid") from exc
        request_freshness = _request_bound_capture_freshness(screen_observation)
        if request_freshness is None:
            captured_at = datetime.fromisoformat(
                str(screen_observation["captured_at"]).replace("Z", "+00:00"))
            if (not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None
                    or captured_at.tzinfo is None or captured_at.utcoffset() is None):
                raise DevelopmentalCompanionBridgeError(
                    "history_intervention_capture_time_invalid")
            capture_age = now.astimezone(timezone.utc) - captured_at.astimezone(timezone.utc)
            if (capture_age < -MAX_HISTORY_INTERVENTION_FUTURE_SKEW
                    or capture_age > MAX_HISTORY_INTERVENTION_CAPTURE_AGE):
                raise DevelopmentalCompanionBridgeError(
                    "history_intervention_capture_not_fresh")
        tick_time, projection_tick = self._projection_boundary()
        prior_self_model, prior_epistemic_state = self._prior_cognitive_context(
            tick_id=tick_time, projection_tick=projection_tick,
            relevance_query=question)
        capture_age_seconds = (None if request_freshness is not None else
            int(max(0.0, capture_age.total_seconds())))
        snapshot = build_companion_snapshot(
            screen_observation=screen_observation,
            proprioception=proprioception,
            screen_staleness="fresh",
            screen_capture_age_seconds=capture_age_seconds,
            clock=self._clock)
        if not snapshot.facts:
            raise CognitionEvidenceUnavailable()
        gate = (self._cognition_inference_gate()
            if self._cognition_inference_gate is not None else nullcontext())
        with gate:
            return self._history_intervention_owner.run_companion_history_intervention(
                snapshot=snapshot, tick_id=tick_id, question=question,
                prior_self_model=prior_self_model,
                prior_epistemic_state=prior_epistemic_state)

    def developmental_cycle_available(self) -> bool:
        """Whether an explicitly confirmed, governed writeback cycle is configured."""
        return (self.can_handle()
            and self._owner.config.enabled is True
            and self._owner.config.comparison_enabled is False
            and self._owner.objective_task is None
            and "embodiment" in self._owner.config.allowed_source_kinds)

    def operator_feedback_available(self) -> bool:
        return (self.developmental_cycle_available()
            and "operator_input" in self._owner.config.allowed_source_kinds)

    def run_developmental_cycle(self, *, tick_id: str,
            screen_observation: Mapping[str, Any] | None = None,
            operator_feedback: Mapping[str, Any] | None = None,
            current_consequence_records: Sequence[Mapping[str, Any]] = ()
            ) -> CompanionDevelopmentalCycleResult:
        """Run one fresh-evidence tick through the existing governed writeback owner.

        Callers must put this behind an explicit operator confirmation. This
        method never invents a second memory store or bypasses owner admission.
        """
        if (not isinstance(tick_id, str) or not tick_id.strip() or len(tick_id) > 256
                or (screen_observation is not None
                    and not isinstance(screen_observation, Mapping))
                or not isinstance(current_consequence_records, (tuple, list))):
            raise DevelopmentalCompanionBridgeError(
                "developmental_cycle_request_invalid")
        if not self.developmental_cycle_available():
            raise CognitionWorkloadUnavailable()
        proprioception: Sequence[EmbodimentObservation] = ()
        if self._proprioception_provider is not None:
            value = self._proprioception_provider()
            if not isinstance(value, (tuple, list)) or any(
                    not isinstance(item, EmbodimentObservation) for item in value):
                raise DevelopmentalCompanionBridgeError(
                    "proprioception_provider_output_invalid")
            proprioception = tuple(value)
        capture_age_seconds = None
        if screen_observation is not None:
            _screen_record(screen_observation)
            now = self._clock() if callable(self._clock) else datetime.now(timezone.utc)
            if isinstance(now, str):
                try:
                    now = datetime.fromisoformat(now.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise DevelopmentalCompanionBridgeError(
                        "developmental_cycle_clock_invalid") from exc
            request_freshness = _request_bound_capture_freshness(screen_observation)
            if request_freshness is None:
                captured_at = datetime.fromisoformat(
                    str(screen_observation["captured_at"]).replace("Z", "+00:00"))
                if (not isinstance(now, datetime) or now.tzinfo is None
                        or now.utcoffset() is None or captured_at.tzinfo is None
                        or captured_at.utcoffset() is None):
                    raise DevelopmentalCompanionBridgeError(
                        "developmental_cycle_capture_time_invalid")
                capture_age = now.astimezone(timezone.utc) - captured_at.astimezone(timezone.utc)
                if (capture_age < -MAX_HISTORY_INTERVENTION_FUTURE_SKEW
                        or capture_age > MAX_HISTORY_INTERVENTION_CAPTURE_AGE):
                    raise DevelopmentalCompanionBridgeError(
                        "developmental_cycle_capture_not_fresh")
                capture_age_seconds = int(max(0.0, capture_age.total_seconds()))
        tick_time, projection_tick = self._projection_boundary()
        consequence_records: Sequence[Mapping[str, Any]] = ()
        if self._consequence_records_provider is not None:
            try:
                value = self._consequence_records_provider()
            except Exception as exc:
                raise DevelopmentalCompanionBridgeError(
                    "historical_consequence_projection_unavailable") from exc
            if (not isinstance(value, (tuple, list))
                    or len(value) > MAX_COMPANION_CONSEQUENCE_RECORDS):
                raise DevelopmentalCompanionBridgeError(
                    "historical_consequence_projection_invalid")
            consequence_records = tuple(value)
        snapshot = build_companion_snapshot(
            screen_observation=screen_observation,
            proprioception=proprioception, operator_feedback=operator_feedback,
            screen_staleness="fresh",
            historical_consequence_records=consequence_records,
            current_consequence_records=current_consequence_records,
            screen_capture_age_seconds=capture_age_seconds, clock=self._clock)
        if not snapshot.facts:
            raise CognitionEvidenceUnavailable()
        if (self._consequence_records_provider is not None
                and len(snapshot.facts) > self._owner.config.max_selected_facts):
            raise DevelopmentalCompanionBridgeError(
                "developmental_cycle_fact_selection_capacity_insufficient")
        current_context = self._owner.selected_current_relevance_context(
            snapshot, maximum_chars=2800)
        prior_self_model, prior_epistemic_state = self._prior_cognitive_context(
            tick_id=tick_time, projection_tick=projection_tick,
            relevance_query=current_context or None)
        gate = (self._cognition_inference_gate()
            if self._cognition_inference_gate is not None else nullcontext())
        with gate:
            cycle = self._owner.run_tick(snapshot=snapshot, tick_id=tick_id,
                prior_self_model=prior_self_model,
                prior_epistemic_state=prior_epistemic_state)
        self_model_result: Any | None = None
        self_model_status = "not_configured"
        self_model_error_type: str | None = None
        config = self._self_model_config
        if (self._self_model_owner is not None and config is not None
                and config.enabled):
            try:
                # Match sentientosd's temporal ordering: cognition first, then
                # same-snapshot reconciliation. Use the timestamp boundary, not
                # the request's opaque tick ID, so later projections can select it.
                self_model_result = self._self_model_owner.reconcile(
                    snapshot, tick_id=tick_time)
                self_model_status = "reconciled"
            except Exception as exc:
                # The governed developmental write may already be committed.
                # Preserve that result and report the optional owner failure
                # separately rather than implying the whole cycle rolled back.
                self_model_status = "degraded"
                self_model_error_type = type(exc).__name__
        epistemic_result: Any | None = None
        epistemic_status = "not_configured"
        epistemic_error_type: str | None = None
        epistemic_runtime = self._epistemic_development_runtime
        if epistemic_runtime is not None:
            config = getattr(epistemic_runtime, "config", None)
            if getattr(config, "enabled", False) is not True:
                epistemic_status = "disabled"
            else:
                try:
                    # Match the daemon's post-cognition, next-tick-only ordering.
                    # The same validated snapshot that informed this cognition is
                    # the sole input to the governed epistemic-development owner.
                    if tick_time.endswith("-00:00"):
                        raise ValueError("epistemic_development_tick_offset_unknown")
                    instant = datetime.fromisoformat(tick_time.replace("Z", "+00:00"))
                    if instant.tzinfo is None or instant.utcoffset() is None:
                        raise ValueError("epistemic_development_tick_timezone_required")
                    epistemic_result = epistemic_runtime.process_snapshot(
                        snapshot, tick=int(instant.timestamp()),
                        recorded_at=instant.isoformat())
                    epistemic_status = str(getattr(
                        epistemic_result, "status", "completed"))
                except Exception as exc:
                    # Cognition and its writeback may already be committed. Keep
                    # that result and report this separately as a degraded owner.
                    epistemic_status = "degraded"
                    epistemic_error_type = type(exc).__name__
        return CompanionDevelopmentalCycleResult(
            **asdict(cycle),
            self_model_reconciliation_status=self_model_status,
            self_model_reconciliation_id=(
                self_model_result.reconciliation_id
                if self_model_result is not None else None),
            self_model_reconciliation_digest=(
                self_model_result.reconciliation_digest
                if self_model_result is not None else None),
            self_model_reconciliation_generation=(
                self_model_result.generation
                if self_model_result is not None else None),
            self_model_claim_count=(
                len(self_model_result.claims)
                if self_model_result is not None else None),
            self_model_reconciliation_error_type=self_model_error_type,
            epistemic_development_status=epistemic_status,
            epistemic_development_evidence_receipt_ids=tuple(getattr(
                epistemic_result, "evidence_receipt_ids", ())),
            epistemic_development_state_receipt_ids=tuple(getattr(
                epistemic_result, "state_receipt_ids", ())),
            epistemic_development_successor_state_ids=tuple(getattr(
                epistemic_result, "successor_state_ids", ())),
            epistemic_development_generations=tuple(getattr(
                epistemic_result, "generations", ())),
            epistemic_development_next_tick_only=bool(getattr(
                epistemic_result, "next_tick_only", True)),
            epistemic_development_error_type=epistemic_error_type)

    def selected_historical_operator_citations(self, *, request_id: str,
            question: str,
            conversation_context: Mapping[str, Any] | None = None
            ) -> tuple[dict[str, Any], ...]:
        """Expose cited-turn references for the exact bounded history window."""
        if not self.can_handle():
            return ()
        return self._owner.selected_historical_operator_citations(
            request_id=request_id, question=question,
            conversation_context=conversation_context)

    def respond(self, *, request_id: str, question: str,
                screen_observation: Mapping[str, Any] | None = None,
                canonical_memory_context: Mapping[str, Any] | None = None,
                conversation_context: Mapping[str, Any] | None = None,
                historical_citation_context: Mapping[str, Any] | None = None,
                withhold_developmental_history: bool = False
                ) -> ResidentCompanionInteractionResult:
        if type(withhold_developmental_history) is not bool:
            raise DevelopmentalCompanionBridgeError(
                "developmental_history_withholding_invalid")
        proprioception: Sequence[EmbodimentObservation] = ()
        if self._proprioception_provider is not None:
            value = self._proprioception_provider()
            if not isinstance(value, (tuple, list)) or any(
                    not isinstance(item, EmbodimentObservation) for item in value):
                raise DevelopmentalCompanionBridgeError(
                    "proprioception_provider_output_invalid")
            proprioception = tuple(value)
        tick_id, projection_tick = self._projection_boundary()
        prioritized_epistemic_state_ids: tuple[str, ...] = ()
        if conversation_context is not None:
            if not isinstance(conversation_context, Mapping):
                raise DevelopmentalCompanionBridgeError(
                    "conversation_epistemic_priority_invalid")
            candidate_ids = conversation_context.get(
                "prior_epistemic_state_ids", ())
            if (not isinstance(candidate_ids, (list, tuple))
                    or len(candidate_ids) > 64
                    or any(not isinstance(item, str) for item in candidate_ids)
                    or len(set(candidate_ids)) != len(candidate_ids)):
                raise DevelopmentalCompanionBridgeError(
                    "conversation_epistemic_priority_invalid")
            prioritized_epistemic_state_ids = tuple(candidate_ids)
            if (self._epistemic_state_owner is not None
                    and self._epistemic_state_config.get(
                        "cognitive_consumption_enabled") is True):
                try:
                    proposition_priorities = (
                        self._epistemic_state_owner.proposition_priorities_for_state_ids(
                            prioritized_epistemic_state_ids))
                except Exception as exc:
                    raise DevelopmentalCompanionBridgeError(
                        "conversation_epistemic_priority_resolution_failed") from exc
                semantic_context = {key: value for key, value in
                    conversation_context.items() if key != "selection_digest"}
                semantic_context["prior_epistemic_proposition_ids"] = list(
                    proposition_priorities)
                conversation_context = {**semantic_context,
                    "selection_digest": digest_payload(semantic_context)}
        snapshot = build_companion_snapshot(
            screen_observation=screen_observation,
            proprioception=proprioception, clock=self._clock)
        if not snapshot.facts:
            raise CognitionEvidenceUnavailable()
        relevance_query = question
        if (isinstance(question, str) and question.strip()
                and len(question) <= 1200
                and is_sparse_or_elliptical_cognition_query(question)):
            relevance_parts = [question]
            turns = (conversation_context.get("turns", ())
                if isinstance(conversation_context, Mapping) else ())
            prior_user_text = None
            if isinstance(turns, (list, tuple)):
                for row in reversed(turns):
                    if not isinstance(row, Mapping) or row.get("role") != "user":
                        continue
                    candidate_text = row.get("text")
                    if isinstance(candidate_text, str) and candidate_text.strip():
                        prior_user_text = candidate_text
                        break
            if isinstance(prior_user_text, str):
                relevance_parts.append(prior_user_text[:1000])
            current_context = self._owner.selected_current_relevance_context(
                snapshot, question=question, maximum_chars=2800)
            if current_context:
                relevance_parts.append(current_context)
            if len(relevance_parts) > 1:
                # Sparse follow-ups may use validated prior user language and
                # selected current observations to rank prior cognitive state.
                # Specific questions retain question-only ranking; neither cue
                # is relabeled as current evidence or authority.
                relevance_query = " ".join(relevance_parts)[:4000]
        prior_self_model, prior_epistemic_state = self._prior_cognitive_context(
            tick_id=tick_id, projection_tick=projection_tick,
            relevance_query=relevance_query,
            prioritized_epistemic_state_ids=prioritized_epistemic_state_ids)
        gate = (self._cognition_inference_gate()
            if self._cognition_inference_gate is not None else nullcontext())
        with gate:
            interaction_arguments = dict(
                snapshot=snapshot, request_id=request_id, question=question,
                prior_self_model=prior_self_model,
                prior_epistemic_state=prior_epistemic_state,
                canonical_memory_context=canonical_memory_context,
                conversation_context=conversation_context,
                historical_citation_context=historical_citation_context)
            if withhold_developmental_history:
                interaction_arguments["withhold_developmental_history"] = True
            return self._owner.run_companion_interaction(**interaction_arguments)
