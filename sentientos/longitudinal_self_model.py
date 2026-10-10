"""Deterministic, non-authoritative longitudinal claims derived from World-State."""
from __future__ import annotations

import json
import math
import os
import stat
import tempfile
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .local_model_authority import digest_payload
from .world_state_board import WorldStateFact, WorldStateSnapshot, validate_snapshot
from .windows_handle_custody import WindowsHandleCustodyError, read_explicit_file, read_regular_files

SCHEMA = "sentientos.longitudinal_self_model:v1"
RECONCILIATION_SCHEMA = "sentientos.longitudinal_self_model_reconciliation:v1"
CONFIG_SCHEMA = "sentientos.longitudinal_self_model_runtime_config:v1"
PROJECTION_SCHEMA = "sentientos.cognitive_self_model_projection:v1"
PROJECTION_POLICY = "predicate_then_claim_id:v1"
MAX_PROJECTION_CLAIMS = 32
FALSE_AUTHORITY = {
    "decision_authority": False, "admission_authority": False,
    "execution_authority": False, "adoption_authority": False,
    "policy_authority": False, "goal_authority": False,
    "source_mutation_authority": False, "model_authorship_authority": False,
}
MAX_CLAIMS = 256
MAX_VALUE_BYTES = 4096
MAX_RECONCILIATION_ENTRIES = 4096
MAX_RECONCILIATION_BYTES = 4_194_304
MAX_RECONCILIATION_CUSTODY_BYTES = 268_435_456
MAX_RUNTIME_CONFIG_BYTES = 16_384
FORBIDDEN_PREDICATES = {
    "authority", "permission", "policy", "goal", "adoption", "consciousness",
    "sentience", "identity_continuity", "learning", "improvement",
    "model_authored_claim", "reflection_claim",
}
PAYLOAD_PREDICATES = {
    "software_generation": ("software_generation", "runtime_generation"),
    "chat_process_generation_attribution": ("verified_chat_process_generation_attributions",),
    "chat_model_serving_lineage": ("chat_model_serving_lineage",),
    "cognitive_model_identity": ("cognitive_model_id", "serving_model", "model_id"),
    "declared_repository_generation_identity": ("declared_repository_generation_identity",),
    "declared_repository_generation_posture": ("declared_repository_generation_posture",),
    "predecessor_model_identity": ("predecessor_model_identity",),
    "proposed_successor_model_identity": ("proposed_successor_model_identity",),
    "activated_model_identity": ("activated_model_identity",),
    "running_model_identity_observed": ("running_model_identity_observed",),
    "transition_protocol_digest": ("transition_protocol_digest",),
    "transition_observation_posture": ("transition_observation_posture",),
    "transition_stage_semantic_status": ("stage_semantically_verified",),
    "activation_receipt_id": ("activation_receipt_id",),
    "activation_receipt_digest": ("activation_receipt_digest",),
    "activation_state_digest": ("activation_state_digest",),
    "serving_binding_digest": ("serving_binding_digest",),
    "serving_activation_receipt_id": ("serving_activation_receipt_id",),
    "serving_activation_receipt_digest": ("serving_activation_receipt_digest",),
    "serving_expected_model_identity": ("serving_expected_model_identity",),
    "predecessor_software_generation": ("predecessor_generation_digest",),
    "successor_software_generation": ("successor_generation_digest",),
    "running_software_generation_observed": ("running_software_generation_observed",),
    "software_lineage_id": ("lineage_id",),
    "software_continuity_receipt_digest": ("continuity_receipt_digest",),
    "software_pending_handoff_event_digest": ("pending_handoff_event_digest",),
    "software_successor_repository_commit": ("successor_repository_commit",),
    "software_successor_repository_tree": ("successor_repository_tree",),
    "software_successor_launch_provenance": ("successor_launch_provenance_digest",),
    "software_readiness_receipt": ("readiness_receipt_digest",),
    "resource_consumption_lineage": ("resource_linkage",),
    "running_software_process_instance": ("process_instance_id",),
    "running_software_repository_commit": ("repository_commit",),
    "running_software_repository_tree": ("repository_tree",),
    "running_software_provenance": ("provenance_digest",),
    "model_development_provenance_reference": ("model_development_provenance_reference",),
    "model_development_provenance_reference_posture": ("model_development_provenance_reference_posture",),
    "model_development_provenance_posture": ("model_development_provenance_posture",),
    "proposed_successor_model_development_provenance": ("proposed_successor_model_development_provenance",),
    "predecessor_model_development_provenance": ("predecessor_model_development_provenance",),
    "model_development_provenance": ("model_development_provenance",),
    "developmental_history_boundary": ("developmental_history_boundary",),
    "software_generation_posture": ("software_generation_posture",),
    "configuration_identity": ("configuration_id",),
    "capability_identity": ("capability_id",),
    "embodiment.body_identity": ("installation_body_id",),
    "embodiment.body_generation": ("body_generation",),
    "embodiment.avatar_asset_identity": ("avatar_asset_id",),
    "embodiment.rig_identity": ("rig_id",),
    "embodiment.renderer_identity": ("renderer_identity", "renderer_interface_id"),
    "embodiment.sensor_presence": ("present",),
    "embodiment.sensor_health": ("healthy",),
    "embodiment.actuator_availability": ("available",),
    "embodiment.commanded_pose": ("commanded_pose",),
    "embodiment.commanded_expression": ("commanded_expression",),
    "embodiment.renderer_reported_pose": ("renderer_reported_pose",),
    "embodiment.renderer_reported_expression": ("renderer_reported_expression",),
    "embodiment.observed_pose": ("observed_pose",),
    "embodiment.observed_expression": ("observed_expression",),
}
HISTORICAL_CONSEQUENCE_CLASSES = frozenset({
    "expectation_satisfied", "expectation_partially_satisfied", "expectation_contradicted",
    "observation_missing", "renderer_report_only", "indeterminate", "execution_failed",
    "body_generation_mismatch", "correlation_mismatch",
})
HISTORICAL_COMPARISON_RESULTS = frozenset({"satisfied", "contradicted", "missing", "indeterminate"})
HISTORICAL_REVIEW_SUBJECTS = frozenset({"embodied_strategy_proposal_review"})
HISTORICAL_FULFILLMENT_SUBJECTS = frozenset({"embodied_proposal_fulfillment_receipt"})
HOST_RESOURCE_METRICS = (
    "cpu_utilization_percent", "ram_utilization_percent", "gpu_utilization_percent",
    "vram_utilization_percent", "disk_utilization_percent", "disk_free_bytes",
    "network_rx_bytes_per_second", "network_tx_bytes_per_second", "process_count",
    "battery_percent",
)
_REVIEW_CONTEXT_FIELDS = (
    "condition", "history_record_id", "history_record_digest", "invocation_receipt_id",
    "invocation_receipt_digest", "execution_evidence_digest", "execution_posture",
    "declared_model_id", "declared_model_artifact_digest", "active_model_identity_digest",
    "serving_identity_posture", "serving_identity_digest", "declared_software_generation",
    "software_generation_posture", "software_execution_provenance_digest",
    "resource_linkage", "invocation_request_context_linkage",
)


class LongitudinalSelfModelError(ValueError):
    """A fail-closed projection or custody violation."""


@dataclass(frozen=True)
class LongitudinalSelfModelRuntimeConfig:
    enabled: bool
    custody_root: Path
    cognitive_consumption_enabled: bool
    max_projection_claims: int
    allowed_predicates: tuple[str, ...]
    installation_id: str


@dataclass(frozen=True)
class CognitiveSelfModelProjection:
    schema: str
    projection_id: str
    projection_digest: str
    source_reconciliation_id: str
    source_reconciliation_digest: str
    source_reconciliation_generation: int
    source_tick: str
    selected_claims: tuple[Mapping[str, Any], ...]
    selected_claim_ids: tuple[str, ...]
    selected_claim_digests: tuple[str, ...]
    software_generations: tuple[str, ...]
    cognitive_model_identities: tuple[str, ...]
    developmental_history_boundaries: tuple[str, ...]
    projection_policy: str
    authority: Mapping[str, bool]
    read_only: bool = True
    derived_evidence: bool = True
    current_truth: bool = False
    interpretation: bool = False

    def semantic_payload(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("projection_id")
        value.pop("projection_digest")
        return value


def load_runtime_config(path: str | Path) -> LongitudinalSelfModelRuntimeConfig:
    try:
        config_data = read_explicit_file(Path(path), max_bytes=MAX_RUNTIME_CONFIG_BYTES)
        payload = json.loads(config_data.decode("utf-8"))
    except LongitudinalSelfModelError:
        raise
    except (WindowsHandleCustodyError, OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise LongitudinalSelfModelError("runtime_configuration_unreadable") from exc
    expected = {"schema", "enabled", "custody_root", "cognitive_consumption_enabled",
                "max_projection_claims", "allowed_predicates", "installation_id"}
    if not isinstance(payload, dict) or set(payload) != expected or payload.get("schema") != CONFIG_SCHEMA:
        raise LongitudinalSelfModelError("runtime_configuration_shape_invalid")
    allowed = payload["allowed_predicates"]
    if (not isinstance(payload["enabled"], bool)
            or not isinstance(payload["cognitive_consumption_enabled"], bool)
            or not isinstance(payload["custody_root"], str) or not Path(payload["custody_root"]).is_absolute()
            or not isinstance(payload["installation_id"], str) or not payload["installation_id"]
            or not isinstance(payload["max_projection_claims"], int)
            or isinstance(payload["max_projection_claims"], bool)
            or not 1 <= payload["max_projection_claims"] <= MAX_PROJECTION_CLAIMS
            or not isinstance(allowed, list) or not allowed
            or any(not isinstance(item, str) or not item or item in FORBIDDEN_PREDICATES for item in allowed)
            or len(allowed) != len(set(allowed))):
        raise LongitudinalSelfModelError("runtime_configuration_values_invalid")
    return LongitudinalSelfModelRuntimeConfig(
        payload["enabled"], Path(payload["custody_root"]), payload["cognitive_consumption_enabled"],
        payload["max_projection_claims"], tuple(sorted(allowed)), payload["installation_id"])


def _digest(value: Any) -> str:
    return "sha256:" + str(digest_payload(value))


def _tick_instant(value: Any) -> datetime | None:
    """Decode daemon UTC tick identities; opaque or naive ticks are unordered."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (OverflowError, OSError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _bounded(value: Any) -> Any:
    result: Any
    if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
        result = value
    elif isinstance(value, str):
        result = value
    elif isinstance(value, list):
        result = [_bounded(item) for item in value]
    elif isinstance(value, dict) and all(isinstance(key, str) for key in value):
        result = {key: _bounded(value[key]) for key in sorted(value)}
    else:
        raise LongitudinalSelfModelError("claim_value_not_bounded_json")
    if len(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()) > MAX_VALUE_BYTES:
        raise LongitudinalSelfModelError("claim_value_too_large")
    return result


@dataclass(frozen=True)
class SelfModelClaim:
    claim_id: str
    claim_key: str
    subject_id: str
    subject_kind: str
    predicate: str
    value: Any
    temporal_scope: str
    claim_category: str
    lifecycle_stage: str
    status: str
    freshness: str
    contradiction_state: str
    evidence_strength: str
    source_evidence_ids: tuple[str, ...]
    source_evidence_digests: tuple[str, ...]
    source_fact_ids: tuple[str, ...]
    world_state_snapshot_id: str
    world_state_snapshot_digest: str
    source_observed_at: tuple[str, ...]
    first_supported_generation: int
    last_supported_generation: int
    first_supported_tick: str
    last_supported_tick: str
    supersedes: tuple[str, ...] = ()
    superseded_by: tuple[str, ...] = ()
    software_generation: str | None = None
    cognitive_model_identity: str | None = None
    developmental_history_boundary: str | None = None
    evidence_bound: bool = True
    current_truth: bool = False
    interpretation: bool = False
    authority: Mapping[str, bool] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.authority is None:
            object.__setattr__(self, "authority", dict(FALSE_AUTHORITY))


@dataclass(frozen=True)
class SelfModelReconciliation:
    schema: str
    reconciliation_id: str
    reconciliation_digest: str
    generation: int
    tick_id: str
    snapshot_id: str
    snapshot_digest: str
    previous_reconciliation_id: str | None
    claims: tuple[SelfModelClaim, ...]
    authority: Mapping[str, bool]


def _claim_key(fact: WorldStateFact, predicate: str) -> str:
    return _digest((fact.subject.subject_id, fact.subject.subject_kind, fact.stage, predicate))


def _claim_id(key: str, value: Any, fact_ids: Sequence[str]) -> str:
    return "self-claim-" + _digest((key, value, sorted(fact_ids)))[7:31]


def _fact_predicates(fact: WorldStateFact) -> list[tuple[str, Any, str]]:
    historical_transition_event = (
        (fact.source.kind == "runtime_supervisor"
            and fact.subject.subject_kind in {"resident_model_transition", "software_generation_transition",
                "chat_process_recovery_transition",
                "chat_process_runtime_generation_observation",
                "serving_operation_attempt", "serving_operation_history"})
        or (fact.source.kind == "resource_governor"
            and fact.subject.subject_kind == "chat_process_software_generation_invocation"))
    out = [(f"lifecycle.{fact.stage}.disposition", fact.disposition,
        "historical_interpretation" if historical_transition_event else "current_state")]
    for predicate, keys in PAYLOAD_PREDICATES.items():
        for key in keys:
            if key in fact.payload:
                out.append((predicate, _bounded(fact.payload[key]), "lineage"
                    if any(token in predicate for token in ("generation", "model", "resource", "transition"))
                    else "configuration"))
                break
    if fact.effect_proven and "observed_consequence" in fact.payload:
        out.append(("observed_consequence", _bounded(fact.payload["observed_consequence"]), "observed_consequence"))
    # Preserve the verified model-transition observation/history join as one
    # historical claim. Independent payload predicates above remain selectors;
    # this grouped claim exists only when the exact source row is qualified.
    if (fact.source.kind == "runtime_supervisor"
            and fact.subject.subject_kind == "resident_model_transition"
            and fact.source.finding == "ok"
            and fact.disposition == "completed"
            and fact.payload.get("transition_observation_posture")
                == "owner_verified_durable_cognition_history_handoff"):
        payload = fact.payload
        phase = payload.get("transition_phase")
        common = {"transition_id": payload.get("transition_id"),
            "transition_protocol_digest": payload.get("transition_protocol_digest"),
            "journal_entry_digest": payload.get("journal_entry_digest"),
            "transition_phase": phase,
            "predecessor_model_identity": payload.get("predecessor_model_identity"),
            "proposed_successor_model_identity": payload.get("proposed_successor_model_identity"),
            "source_record_id": fact.source.source_id,
            "source_record_digest": fact.source.digest,
            "transition_stage_event_time": payload.get("event_time"),
            "cognition_observation_event_time": None,
            "event_time_posture": "journal_stage_time_not_inference_receipt_time"}
        if phase == "b_epoch_observed":
            pairs = (
                (payload.get("b_epoch_observation_id"), payload.get("b_epoch_observation_digest")),
                (payload.get("b_epoch_developmental_record_id"), payload.get("b_epoch_developmental_record_digest")),
                (payload.get("b_epoch_writeback_receipt_id"), payload.get("b_epoch_writeback_receipt_digest")),
            )
            tick = payload.get("b_epoch_tick_id")
            if (isinstance(tick, str) and tick
                    and all(isinstance(identity, str) and identity for pair in pairs for identity in pair)):
                lineage = {**common, "tick_id": tick,
                    "cognition_observation_id": pairs[0][0],
                    "cognition_observation_digest": pairs[0][1],
                    "developmental_record_id": pairs[1][0],
                    "developmental_record_digest": pairs[1][1],
                    "writeback_receipt_id": pairs[2][0],
                    "writeback_receipt_digest": pairs[2][1]}
            else:
                lineage = {}
        elif phase == "post_restoration_observed":
            retrieved_ids = payload.get("retrieved_record_ids")
            retrieved_digests = payload.get("retrieved_record_digests")
            pairs = ((payload.get("restored_a_observation_id"),
                      payload.get("restored_a_observation_digest")),
                     (payload.get("restored_a_inference_receipt_id"),
                      payload.get("restored_a_inference_receipt_digest")))
            if (isinstance(payload.get("restored_a_tick_id"), str)
                    and payload.get("restored_a_tick_id")
                    and all(isinstance(identity, str) and identity for pair in pairs for identity in pair)
                    and isinstance(retrieved_ids, (list, tuple))
                    and isinstance(retrieved_digests, (list, tuple))
                    and len(retrieved_ids) == len(retrieved_digests) <= 16
                    and all(isinstance(identity, str) and identity for identity in retrieved_ids)
                    and len(set(retrieved_ids)) == len(retrieved_ids)
                    and all(isinstance(identity, str) and identity for identity in retrieved_digests)):
                lineage = {**common, "tick_id": payload["restored_a_tick_id"],
                    "cognition_observation_id": pairs[0][0],
                    "cognition_observation_digest": pairs[0][1],
                    "inference_receipt_id": pairs[1][0],
                    "inference_receipt_digest": pairs[1][1],
                    "retrieved_record_ids": list(retrieved_ids),
                    "retrieved_record_digests": list(retrieved_digests)}
            else:
                lineage = {}
        else:
            lineage = {}
        if lineage and len(json.dumps(lineage, sort_keys=True, separators=(",", ":")).encode("utf-8")) <= MAX_VALUE_BYTES:
            lineage.update({"source_binding_posture": "world_state_source_digest_verified",
                "historical_only": True, "current_truth": False,
                "effect_proven": False, "authority": False})
            out.append(("resident_model_transition.cognition_history_handoff",
                        _bounded(lineage), "historical_interpretation"))
    if (fact.source.kind == "runtime_supervisor"
            and fact.subject.subject_kind == "chat_process_runtime_generation_observation"
            and fact.source.finding == "ok" and isinstance(fact.payload, Mapping)):
        observation = fact.payload.get("chat_process_runtime_observation")
        linked_invocations = fact.payload.get("linked_invocation_receipts", ())
        if isinstance(observation, Mapping) and isinstance(linked_invocations, (list, tuple)):
            source_links = list(linked_invocations)
            linked_invocation_source_digest = digest_payload(source_links)
            link_posture = "complete"
            if len(source_links) > 16 or any(not isinstance(item, Mapping) for item in source_links):
                selected_linked_invocations = []
                link_posture = "source_link_collection_invalid"
            else:
                selected_linked_invocations = []
                for item in source_links[:2]:
                    selected = {key: item.get(key) for key in (
                        "invocation_receipt_id", "invocation_receipt_digest",
                        "invocation_request_id", "invocation_request_digest",
                        "serving_receipt_id", "serving_receipt_semantic_digest",
                        "serving_operation_attempt_id", "serving_operation_attempt_semantic_digest",
                        "serving_operation_id", "serving_session_id",
                        "serving_receipt_lineage_posture",
                        "resource_allocation_digest", "resource_attempt_id",
                        "resource_effect_receipt_digest", "model_id", "model_artifact_digest",
                        "linkage_posture", "current_model_claimed")}
                    consumption = item.get("resource_consumption_receipt_digests", ())
                    if not isinstance(consumption, (list, tuple)):
                        link_posture = "source_link_collection_invalid"
                        selected["resource_consumption_receipt_digests"] = None
                    else:
                        selected["resource_consumption_receipt_digests"] = list(consumption[:4])
                        selected["resource_consumption_receipt_digests_digest"] = (
                            digest_payload(list(consumption)))
                        selected["resource_consumption_receipt_digests_total"] = len(consumption)
                        selected["resource_consumption_receipt_digests_omitted"] = max(
                            0, len(consumption) - 4)
                        if len(consumption) > 4:
                            link_posture = "bounded_subset_with_source_digest"
                    model_identity = item.get("active_model_identity_at_invocation")
                    selected["active_model_identity_digest"] = (
                        digest_payload(dict(model_identity))
                        if isinstance(model_identity, Mapping) else None)
                    selected_linked_invocations.append(selected)
                if len(source_links) > len(selected_linked_invocations):
                    link_posture = "bounded_subset_with_source_digest"
            lineage = {
                "source_record_id": fact.source.source_id,
                "source_record_digest": fact.source.digest,
                "runtime_observation_digest": observation.get("observation_semantic_digest"),
                "runtime_supervisor_generation": observation.get("runtime_supervisor_generation"),
                "observed_at": observation.get("observed_at"),
                "runtime_status_at_observation": observation.get("runtime_status"),
                "configured_serving_receipt_posture_at_observation": observation.get("configured_serving_receipt_posture"),
                "configured_serving_operation_id_at_observation": observation.get(
                    "configured_serving_operation_id"),
                "serving_receipt_at_observation": (
                    {key: observation["serving_receipt"].get(key) for key in (
                        "receipt_id", "receipt_semantic_digest", "session_id",
                        "serving_operation_id", "model_identity_in_receipt",
                        "selection_posture")}
                    if isinstance(observation.get("serving_receipt"), Mapping) else None),
                "model_identity_in_receipt_is_current_claim": False,
                "process_instance_id": observation.get("process_instance_id"),
                "handoff_id": observation.get("handoff_id"),
                "handoff_digest": observation.get("handoff_digest"),
                "software_generation_digest": observation.get("software_generation_digest"),
                "source_generation_scope": observation.get("source_generation_scope"),
                "invocation_linkage_posture": fact.payload.get("invocation_linkage_posture"),
                "linked_invocation_receipts": selected_linked_invocations,
                "linked_invocation_receipts_source_digest": linked_invocation_source_digest,
                "linked_invocation_receipts_total": len(source_links),
                "linked_invocation_receipts_omitted": max(
                    0, len(source_links) - len(selected_linked_invocations)),
                "linked_invocation_receipts_posture": link_posture,
                "current_model_claimed": False,
                "currentness": "historical_owner_observation_only",
                "independent_signature": False,
                "historical_only": True, "current_truth": False,
                "effect_proven": False, "authority": False,
            }
            if (isinstance(lineage["runtime_observation_digest"], str)
                    and isinstance(lineage["handoff_digest"], str)
                    and len(json.dumps(lineage, sort_keys=True, separators=(",", ":")).encode("utf-8"))
                        <= MAX_VALUE_BYTES):
                out.append(("chat_process_runtime.historical_generation_observation",
                    _bounded(lineage), "historical_interpretation"))
    if (fact.source.kind == "runtime_supervisor"
            and fact.subject.subject_kind == "chat_process_recovery_transition"
            and fact.source.finding == "ok" and isinstance(fact.payload, Mapping)):
        transition = fact.payload.get("chat_process_recovery_transition")
        if isinstance(transition, Mapping):
            def handoff_lineage(value: Any) -> dict[str, Any] | None:
                if not isinstance(value, Mapping):
                    return None
                keys = ("handoff_id", "handoff_digest", "process_instance_id",
                    "software_generation_digest", "startup_timestamp", "source_generation_scope",
                    "configured_serving_operation_id")
                projected = {key: value[key] for key in keys if key in value}
                return projected if {"handoff_id", "handoff_digest"}.issubset(projected) else None
            lineage = {
                "source_record_id": fact.source.source_id,
                "source_record_digest": fact.source.digest,
                "request_id": transition.get("request_id"),
                "request_semantic_digest": transition.get("request_semantic_digest"),
                "intent_id": transition.get("intent_id"),
                "intent_semantic_digest": transition.get("intent_semantic_digest"),
                "approval_id": transition.get("approval_id"),
                "approval_semantic_digest": transition.get("approval_semantic_digest"),
                "runtime_supervisor_generation": transition.get("runtime_supervisor_generation"),
                "prior_serving_receipt_id": transition.get("prior_serving_receipt_id"),
                "prior_serving_receipt_semantic_digest": transition.get("prior_serving_receipt_semantic_digest"),
                "prior_serving_operation_id": transition.get("prior_serving_operation_id"),
                "replacement_serving_operation_id": transition.get("replacement_serving_operation_id"),
                "attempt_phase_digest": transition.get("attempt_phase_digest"),
                "readiness_phase_digest": transition.get("readiness_phase_digest"),
                "completion_phase_digest": transition.get("completion_phase_digest"),
                "attempt_started_at": transition.get("attempt_started_at"),
                "readiness_observed_at": transition.get("readiness_observed_at"),
                "snapshot_advanced_at": transition.get("snapshot_advanced_at"),
                "advanced_snapshot_digest": transition.get("advanced_snapshot_digest"),
                "successor_serving_receipt_id": transition.get("successor_serving_receipt_id"),
                "successor_serving_receipt_semantic_digest": transition.get(
                    "successor_serving_receipt_semantic_digest"),
                "successor_serving_session_id": transition.get("successor_serving_session_id"),
                "successor_serving_receipt_posture": transition.get("successor_serving_receipt_posture"),
                "predecessor_serving_operation_binding_posture": transition.get(
                    "predecessor_serving_operation_binding_posture"),
                "successor_serving_operation_binding_posture": transition.get(
                    "successor_serving_operation_binding_posture"),
                "successor_configured_serving_operation_id": transition.get(
                    "successor_configured_serving_operation_id"),
                "predecessor_chat_process_handoff": handoff_lineage(
                    transition.get("predecessor_chat_process_handoff")),
                "successor_chat_process_handoff": handoff_lineage(
                    transition.get("successor_chat_process_handoff")),
                "handoff_lineage_posture": transition.get("handoff_lineage_posture"),
                "phase_posture": transition.get("phase_posture"),
                "terminal_receipt_digest": transition.get("terminal_receipt_digest"),
                "terminal_status": transition.get("terminal_status"),
                "decision_posture": transition.get("decision_posture"),
                "runtime_currentness": transition.get("runtime_currentness"),
                "historical_only": True, "current_truth": False,
                "effect_proven": False, "authority": False,
            }
            if (isinstance(lineage["request_id"], str)
                    and isinstance(lineage["attempt_phase_digest"], str)
                    and len(json.dumps(lineage, sort_keys=True, separators=(",", ":")).encode("utf-8"))
                        <= MAX_VALUE_BYTES):
                out.append(("chat_process_recovery.historical_phase_lineage",
                    _bounded(lineage), "historical_interpretation"))
    if (fact.source.kind == "runtime_supervisor"
            and fact.subject.subject_kind == "serving_operation_attempt"
            and fact.source.finding == "ok" and isinstance(fact.payload, Mapping)):
        attempt = fact.payload.get("serving_operation_attempt")
        if isinstance(attempt, Mapping):
            lineage = {
                "source_record_id": fact.source.source_id,
                "source_record_digest": fact.source.digest,
                "attempt_id": attempt.get("attempt_id"),
                "attempt_semantic_digest": attempt.get("attempt_semantic_digest"),
                "installation_identity": attempt.get("installation_identity"),
                "serving_operation_id": attempt.get("serving_operation_id"),
                "activation_state_semantic_digest": attempt.get("activation_state_semantic_digest"),
                "activation_generation": attempt.get("activation_generation"),
                "model_id": attempt.get("model_id"),
                "operation_intent_digest": attempt.get("operation_intent_digest"),
                "admission_decision_ref": attempt.get("admission_decision_ref"),
                "reserved_at": attempt.get("reserved_at"),
                "attempt_posture": attempt.get("attempt_posture"),
                "model_load_outcome": fact.payload.get("model_load_outcome", "unknown"),
                "resource_consumption_measurements": "unknown",
                "current_model_claimed": False, "inference_performed": False,
                "effect_proven": False, "authority": False,
                "independent_signature": False,
                "historical_only": True, "current_truth": False,
            }
            if (isinstance(lineage["attempt_id"], str)
                    and isinstance(lineage["attempt_semantic_digest"], str)
                    and len(json.dumps(lineage, sort_keys=True, separators=(",", ":")).encode("utf-8"))
                        <= MAX_VALUE_BYTES):
                out.append(("chat_process.serving_operation_attempt",
                    _bounded(lineage), "historical_interpretation"))
    if (fact.source.kind == "runtime_supervisor"
            and fact.subject.subject_kind == "serving_operation_history"
            and fact.source.finding == "ok" and isinstance(fact.payload, Mapping)):
        lineage = {
            "source_record_id": fact.source.source_id,
            "source_record_digest": fact.source.digest,
            "serving_history_status": fact.payload.get("serving_history_status"),
            "serving_operation_id": fact.payload.get("serving_operation_id"),
            "attempt_id": fact.payload.get("attempt_id"),
            "attempt_semantic_digest": fact.payload.get("attempt_semantic_digest"),
            "receipt_id": fact.payload.get("receipt_id"),
            "receipt_semantic_digest": fact.payload.get("receipt_semantic_digest"),
            "serving_session_id": fact.payload.get("serving_session_id"),
            "activation_state_semantic_digest": fact.payload.get("activation_state_semantic_digest"),
            "activation_generation": fact.payload.get("activation_generation"),
            "model_id": fact.payload.get("model_id"),
            "artifact_id": fact.payload.get("artifact_id"),
            "runtime_id": fact.payload.get("runtime_id"),
            "observed_loaded_model_identity": fact.payload.get("observed_loaded_model_identity"),
            "event_time": fact.payload.get("event_time"),
            "event_time_posture": fact.payload.get("event_time_posture"),
            "resource_consumption_measurements": "unknown",
            "current_model_claimed": False, "inference_performed": False,
            "effect_proven": False, "authority": False,
            "historical_only": True, "current_truth": False,
        }
        if (isinstance(lineage["serving_operation_id"], str)
                and len(json.dumps(lineage, sort_keys=True, separators=(",", ":")).encode("utf-8"))
                    <= MAX_VALUE_BYTES):
            out.append(("chat_process.serving_operation_history",
                _bounded(lineage), "historical_interpretation"))
    # Keep deterministic comparison results available to later cognition as
    # explicitly historical interpretation. They do not prove an effect or
    # become current merely because a projection was reconstructed recently.
    if (fact.source.kind == "embodiment"
            and fact.subject.subject_kind in {"embodied_consequence_attribution",
                                               "embodied_prediction_comparison"}
            and fact.payload.get("classification") in HISTORICAL_CONSEQUENCE_CLASSES):
        out.append(("embodiment.historical_consequence_classification",
                    _bounded(fact.payload["classification"]), "historical_interpretation"))
    # Keep enough of the prediction comparison in durable history for a later
    # cognition to inspect what was compared and which fields were unresolved.
    # Values themselves stay in the source record; this compact claim carries
    # only digest-bound identities, outcome labels and bounded counts.
    if (fact.source.kind == "embodiment" and fact.source.finding == "ok"
            and fact.subject.subject_kind in {"embodied_consequence_attribution",
                                               "embodied_prediction_comparison"}):
        payload = fact.payload
        attribution_record = fact.subject.subject_kind == "embodied_consequence_attribution"
        identity_fields = (("attribution_id", "attribution_digest") if attribution_record
                          else ("comparison_id", "comparison_digest"))
        record_id, record_digest = (payload.get(identity_fields[0]), payload.get(identity_fields[1]))
        comparison_id = payload.get("comparison_id")
        comparison_digest = payload.get("comparison_digest")
        expectation_id = payload.get("expectation_id")
        expectation_digest = payload.get("expectation_digest")
        observation_id = payload.get("observation_id")
        observation_digest = payload.get("observation_digest")
        complete_pairs = (
            (record_id, record_digest), (comparison_id, comparison_digest),
            (expectation_id, expectation_digest),
        )
        optional_observation_pair = (observation_id, observation_digest)
        if (record_id == fact.source.source_id and record_digest == fact.source.digest
                and all(isinstance(identity, str) and identity for pair in complete_pairs for identity in pair)
                and ((observation_id is None and observation_digest is None)
                     or all(isinstance(identity, str) and identity for identity in optional_observation_pair))):
            raw_results = payload.get("observable_results", ())
            compact_results: list[dict[str, str]] = []
            result_posture = "field_results_unavailable"
            if isinstance(raw_results, (list, tuple)) and len(raw_results) <= 32:
                valid_results = all(isinstance(item, Mapping)
                    and isinstance(item.get("field"), str) and 0 < len(item["field"]) <= 64
                    and item.get("result") in HISTORICAL_COMPARISON_RESULTS
                    for item in raw_results)
                if valid_results:
                    compact_results = [{"field": item["field"], "result": item["result"]}
                                       for item in raw_results]
                    result_posture = "digest_bound_field_results"
            raw_counts = payload.get("counts")
            counts: dict[str, int] = {}
            if isinstance(raw_counts, Mapping) and all(
                    key in HISTORICAL_COMPARISON_RESULTS
                    and type(value) is int and 0 <= value <= 32
                    for key, value in raw_counts.items()):
                counts = {str(key): value for key, value in raw_counts.items()}
            outcome = payload.get("classification") if attribution_record else None
            if outcome not in HISTORICAL_CONSEQUENCE_CLASSES:
                outcome = None
            lineage = {
                "record_id": record_id, "record_digest": record_digest,
                "comparison_id": comparison_id, "comparison_digest": comparison_digest,
                "expectation_id": expectation_id, "expectation_digest": expectation_digest,
                "observation_id": observation_id, "observation_digest": observation_digest,
                "outcome_classification": outcome, "outcome_counts": counts,
                "field_results": compact_results, "field_results_posture": result_posture,
                "observation_independence_posture": payload.get(
                    "observation_independence_posture", "not_bound_by_comparison"),
                "causal_attribution_posture": payload.get("causal_attribution_posture", "unknown"),
                "event_time": payload.get("evaluated_at") if attribution_record else None,
                "source_binding_posture": "world_state_source_digest_verified",
                "historical_only": True, "current_truth": False,
                "effect_proven": False, "authority": False,
            }
            if len(json.dumps(lineage, sort_keys=True, separators=(",", ":")).encode("utf-8")) <= MAX_VALUE_BYTES:
                out.append(("embodiment.prediction_outcome_lineage", _bounded(lineage),
                            "historical_interpretation"))
    # Keep source-reported host snapshots available to later cognition through
    # the same configured self-model path. This records no per-invocation
    # attribution and deliberately does not upgrade collector values to
    # independently calibrated measurements.
    if (fact.source.kind == "resource_governor"
            and fact.subject.subject_kind == "host_resource_snapshot"
            and fact.source.source_id == "host_resource_runtime:snapshot"
            and fact.source.finding == "ok"):
        payload = fact.payload
        snapshot_id = payload.get("snapshot_id")
        if isinstance(snapshot_id, str) and snapshot_id:
            metrics: dict[str, int | float] = {}
            unknown_metrics: list[str] = []
            for name in HOST_RESOURCE_METRICS:
                value = payload.get(name)
                if (type(value) in (int, float)
                        and (type(value) is int or math.isfinite(value))):
                    metrics[name] = value
                else:
                    unknown_metrics.append(name)
            event_time = payload.get("observed_at")
            if not isinstance(event_time, str) or not event_time:
                event_time = None
            host_observation = {
                "snapshot_id": snapshot_id,
                "snapshot_digest": fact.source.digest,
                "event_time": event_time,
                "event_time_posture": "source_payload_timestamp" if event_time else "unknown",
                "source_value_posture": "host_reported_quality_unqualified",
                "metrics": metrics,
                "unknown_metrics": unknown_metrics,
                "shared_host_use_attribution": "not_per_invocation",
                "historical_only": True, "current_truth": False,
                "effect_proven": False, "authority": False,
            }
            if len(json.dumps(host_observation, sort_keys=True,
                              separators=(",", ":")).encode("utf-8")) <= MAX_VALUE_BYTES:
                out.append(("resource_governor.historical_host_snapshot",
                            _bounded(host_observation), "historical_interpretation"))
    if (fact.source.kind == "embodiment"
            and fact.subject.subject_kind == "developmental_model_replacement_experiment"):
        raw_observations = fact.payload.get("observations")
        conditions: list[dict[str, Any]] = []
        valid_shape = (isinstance(raw_observations, (list, tuple))
            and 0 < len(raw_observations) <= 5)
        if valid_shape:
            for item in raw_observations:
                if not isinstance(item, Mapping):
                    valid_shape = False
                    break
                if (any(not isinstance(item.get(key), str) or not item.get(key) for key in (
                        "condition_id", "observation_id", "observation_digest",
                        "model_identity_digest", "model_provenance_manifest_digest",
                        "inference_receipt_id", "inference_receipt_digest"))
                        or type(item.get("history_withheld")) is not bool):
                    valid_shape = False
                    break
                conditions.append({key: item.get(key) for key in (
                    "condition_id", "observation_id", "observation_digest",
                    "model_identity_digest", "model_provenance_manifest_digest",
                    "history_withheld", "inference_receipt_id", "inference_receipt_digest",
                    "inference_event_time", "inference_event_time_posture",
                    "resource_allocation_digest", "resource_attempt_id",
                    "resource_linkage_digest", "resource_attribution_posture")})
        value: dict[str, Any] = {
            "run_id": fact.payload.get("run_id"),
            "run_digest": fact.payload.get("run_digest"),
            "protocol_id": fact.payload.get("protocol_id"),
            "protocol_digest": fact.payload.get("protocol_digest"),
            "causal_context_id": fact.payload.get("causal_context_id"),
            "causal_context_digest": fact.payload.get("causal_context_digest"),
            "model_a_identity_digest": fact.payload.get("model_a_identity_digest"),
            "model_b_identity_digest": fact.payload.get("model_b_identity_digest"),
            "model_a_provenance_digest": fact.payload.get("model_a_provenance_digest"),
            "model_b_provenance_digest": fact.payload.get("model_b_provenance_digest"),
            "software_generation_identity": fact.payload.get("software_generation_identity"),
            "software_generation_posture": fact.payload.get("software_generation_posture", "unknown"),
            "experiment_completion_posture": fact.payload.get("experiment_completion_posture"),
            "classification": fact.payload.get("classification"),
            "conditions": conditions if valid_shape else [],
            "condition_lineage_posture": "digest_bound_condition_summary" if valid_shape
                else "source_fact_digest_only",
            "current_truth": False, "effect_proven": False, "authority": False,
        }
        if len(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")) > MAX_VALUE_BYTES:
            value["conditions"] = []
            value["condition_lineage_posture"] = "source_fact_digest_only"
        out.append(("developmental.model_replacement_interpretation", _bounded(value),
                    "historical_interpretation"))
    if (fact.source.kind == "embodiment"
            and fact.subject.subject_kind in HISTORICAL_REVIEW_SUBJECTS):
        contexts = fact.payload.get("source_execution_contexts", ())
        compact_contexts = []
        if isinstance(contexts, (list, tuple)):
            for context in contexts[:3]:
                if isinstance(context, Mapping):
                    compact_contexts.append({key: context[key] for key in _REVIEW_CONTEXT_FIELDS
                                             if key in context})
        value = {
            "review_receipt_id": fact.payload.get("review_receipt_id"),
            "review_material_digest": fact.payload.get("review_material_digest"),
            "review_binding_posture": fact.payload.get("review_binding_posture", "unknown"),
            "proposal_id": fact.payload.get("proposal_id"),
            "proposal_digest": fact.payload.get("proposal_digest"),
            "review_outcome": fact.payload.get("review_outcome"),
            "reviewer_kind": fact.payload.get("reviewer_kind"),
            "reviewer_identity_posture": fact.payload.get("reviewer_identity_posture", "unknown"),
            "source_event_refs": fact.payload.get("source_event_refs", []),
            "source_execution_contexts": compact_contexts,
        }
        # The claim has a stricter bound than the source fact. Keep complete
        # fact identity and digest lineage even when optional context is too
        # large for this compact later-cognition projection.
        if len(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")) > MAX_VALUE_BYTES:
            value["source_execution_contexts"] = []
            value["source_event_refs"] = []
        out.append(("embodiment.historical_proposal_review", _bounded(value),
                    "historical_interpretation"))
    if (fact.source.kind == "embodiment"
            and fact.subject.subject_kind in HISTORICAL_FULFILLMENT_SUBJECTS):
        value = {"fulfillment_receipt_id": fact.payload.get("fulfillment_receipt_id"),
            "fulfillment_receipt_digest": fact.payload.get("fulfillment_receipt_digest"),
            "source_fulfillment_candidate_id": fact.payload.get("source_fulfillment_candidate_id"),
            "source_governance_bridge_candidate_ref": fact.payload.get("source_governance_bridge_candidate_ref"),
            "source_handoff_candidate_ref": fact.payload.get("source_handoff_candidate_ref"),
            "source_proposal_id": fact.payload.get("source_proposal_id"),
            "source_review_receipt_id": fact.payload.get("source_review_receipt_id"),
            "fulfillment_outcome": fact.payload.get("fulfillment_outcome"),
            "fulfiller_kind": fact.payload.get("fulfiller_kind"),
            "event_time_posture": fact.payload.get("event_time_posture"),
            "observer_issuer_posture": fact.payload.get("observer_issuer_posture"),
            "actual_effect_observed": False, "effect_proven": False}
        out.append(("embodiment.historical_fulfillment_claim", _bounded(value),
                    "historical_interpretation"))
    return out


def _semantic(reconciliation: SelfModelReconciliation) -> dict[str, Any]:
    value = asdict(reconciliation)
    value.pop("reconciliation_id", None)
    value.pop("reconciliation_digest", None)
    return value


class LongitudinalSelfModelOwner:
    """Append immutable reconciliations; never mutate source evidence or confer authority."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.entries = self.root / "reconciliations"

    @staticmethod
    def _read_entry(path: Path) -> bytes:
        descriptor: int | None = None
        try:
            metadata = path.lstat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_RECONCILIATION_BYTES:
                raise LongitudinalSelfModelError("reconciliation_file_unbounded_or_not_regular")
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            opened = os.fstat(descriptor)
            if (not stat.S_ISREG(opened.st_mode) or opened.st_ino != metadata.st_ino
                    or opened.st_dev != metadata.st_dev or opened.st_size > MAX_RECONCILIATION_BYTES):
                raise LongitudinalSelfModelError("reconciliation_file_changed_during_open")
            chunks: list[bytes] = []
            remaining = MAX_RECONCILIATION_BYTES + 1
            while remaining:
                chunk = os.read(descriptor, min(65_536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
            after = os.fstat(descriptor)
            if len(data) > MAX_RECONCILIATION_BYTES:
                raise LongitudinalSelfModelError("reconciliation_file_unbounded_or_not_regular")
            if (len(data) != opened.st_size or after.st_size != opened.st_size
                    or after.st_mtime_ns != opened.st_mtime_ns):
                raise LongitudinalSelfModelError("reconciliation_file_changed_during_read")
            return data
        except LongitudinalSelfModelError:
            raise
        except OSError as exc:
            raise LongitudinalSelfModelError("reconciliation_file_unavailable") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def _publish_entry(self, path: Path, result: SelfModelReconciliation) -> None:
        if os.name != "posix":
            raise LongitudinalSelfModelError("reconciliation_publication_unsupported_platform")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.parent.is_symlink() or not path.parent.is_dir():
            raise LongitudinalSelfModelError("reconciliation_custody_root_invalid")
        data = json.dumps(asdict(result), sort_keys=True, indent=2).encode("utf-8") + b"\n"
        if len(data) > MAX_RECONCILIATION_BYTES:
            raise LongitudinalSelfModelError("reconciliation_file_unbounded")
        descriptor, temporary = tempfile.mkstemp(prefix=".reconciliation-", suffix=".tmp",
            dir=str(path.parent))
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, path, follow_symlinks=False)
            except FileExistsError as exc:
                raise LongitudinalSelfModelError("reconciliation_path_collision") from exc
            directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    def _load(self) -> tuple[SelfModelReconciliation, ...]:
        if self.root.is_symlink():
            raise LongitudinalSelfModelError("reconciliation_custody_root_invalid")
        try:
            entries_mode = self.entries.lstat().st_mode
        except FileNotFoundError:
            return ()
        if not stat.S_ISDIR(entries_mode):
            raise LongitudinalSelfModelError("reconciliation_custody_root_invalid")
        if os.name == "nt":
            try:
                windows_entries = read_regular_files(self.entries,
                    max_entries=MAX_RECONCILIATION_ENTRIES,
                    max_file_bytes=MAX_RECONCILIATION_BYTES,
                    max_total_bytes=MAX_RECONCILIATION_CUSTODY_BYTES)
            except WindowsHandleCustodyError as exc:
                raise LongitudinalSelfModelError("reconciliation_windows_recovery_failed") from exc
            entry_rows: list[tuple[str, bytes | None, Path | None]] = [
                (name, data, None) for name, data in windows_entries]
        else:
            paths = sorted(self.entries.glob("*.json"))
            if len(paths) > MAX_RECONCILIATION_ENTRIES:
                raise LongitudinalSelfModelError("reconciliation_entry_limit_exceeded")
            entry_rows = [(path.name, None, path) for path in paths]
        loaded: list[SelfModelReconciliation] = []
        total_bytes = 0
        for name, windows_data, path in entry_rows:
            try:
                entry_bytes = windows_data if windows_data is not None else self._read_entry(path)
                total_bytes += len(entry_bytes)
                if total_bytes > MAX_RECONCILIATION_CUSTODY_BYTES:
                    raise LongitudinalSelfModelError("reconciliation_custody_limit_exceeded")
                raw = json.loads(entry_bytes.decode("utf-8"))
                if (not isinstance(raw, dict)
                        or json.dumps(raw, sort_keys=True, indent=2).encode("utf-8") + b"\n" != entry_bytes):
                    raise LongitudinalSelfModelError("reconciliation_record_noncanonical")
                claims = tuple(SelfModelClaim(**{
                    **claim,
                    "source_evidence_ids": tuple(claim["source_evidence_ids"]),
                    "source_evidence_digests": tuple(claim["source_evidence_digests"]),
                    "source_fact_ids": tuple(claim["source_fact_ids"]),
                    "source_observed_at": tuple(claim["source_observed_at"]),
                    "supersedes": tuple(claim["supersedes"]),
                    "superseded_by": tuple(claim["superseded_by"]),
                }) for claim in raw.pop("claims"))
                reconciliation = SelfModelReconciliation(claims=claims, **raw)
            except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, RecursionError) as exc:
                raise LongitudinalSelfModelError("reconciliation_journal_corrupt") from exc
            if reconciliation.schema != RECONCILIATION_SCHEMA or reconciliation.reconciliation_digest != _digest(_semantic(reconciliation)):
                raise LongitudinalSelfModelError("reconciliation_digest_mismatch")
            expected_id = "self-reconciliation-" + reconciliation.reconciliation_digest[7:31]
            expected_path = f"{reconciliation.generation:020d}-{expected_id}.json"
            if reconciliation.reconciliation_id != expected_id or name != expected_path:
                raise LongitudinalSelfModelError("reconciliation_identity_mismatch")
            loaded.append(reconciliation)
        for index, item in enumerate(loaded):
            expected_previous = loaded[index - 1].reconciliation_id if index else None
            if item.generation != index + 1 or item.previous_reconciliation_id != expected_previous:
                raise LongitudinalSelfModelError("reconciliation_chain_invalid")
        return tuple(loaded)

    def history(self) -> tuple[SelfModelReconciliation, ...]:
        return self._load()

    def reconstruct(self, generation: int | None = None) -> SelfModelReconciliation | None:
        history = self._load()
        if not history:
            return None
        if generation is None:
            return history[-1]
        if generation < 1 or generation > len(history):
            raise LongitudinalSelfModelError("generation_not_found")
        return history[generation - 1]

    def cognitive_projection(self, *, before_tick: str, max_claims: int,
                             allowed_predicates: Sequence[str]) -> CognitiveSelfModelProjection | None:
        """Project only a reconciliation completed before ``before_tick``.

        Tick identity equality is rejected mechanically.  The daemon captures this
        projection before reconciling its current World-State, so the selected
        generation cannot be affected by same-tick cognition or writeback.
        """
        current_instant = _tick_instant(before_tick)
        if current_instant is None or not 1 <= max_claims <= MAX_PROJECTION_CLAIMS:
            raise LongitudinalSelfModelError("invalid_cognitive_projection_boundary")
        history = self._load()
        eligible = [item for item in history
                    if item.tick_id != before_tick
                    and (prior_instant := _tick_instant(item.tick_id)) is not None
                    and prior_instant < current_instant]
        if not eligible:
            return None
        source = eligible[-1]
        allowed = set(allowed_predicates)
        claims = sorted((claim for claim in source.claims if claim.predicate in allowed),
                        key=lambda claim: (claim.predicate, claim.claim_id))[:max_claims]
        selected: list[Mapping[str, Any]] = []
        digests: list[str] = []
        for claim in claims:
            bounded = {
                "claim_id": claim.claim_id, "semantic_digest": _digest(asdict(claim)),
                "predicate": claim.predicate, "value": _bounded(claim.value),
                "status": claim.status, "freshness": claim.freshness,
                "contradiction_state": claim.contradiction_state,
                "evidence_strength": claim.evidence_strength,
                "source_evidence_ids": list(claim.source_evidence_ids),
                "source_evidence_digests": list(claim.source_evidence_digests),
                "software_generation": claim.software_generation,
                "cognitive_model_identity": claim.cognitive_model_identity,
                "developmental_history_boundary": claim.developmental_history_boundary,
            }
            selected.append(bounded); digests.append(str(bounded["semantic_digest"]))
        raw = CognitiveSelfModelProjection(
            PROJECTION_SCHEMA, "", "", source.reconciliation_id, source.reconciliation_digest,
            source.generation, source.tick_id, tuple(selected), tuple(c.claim_id for c in claims),
            tuple(digests), tuple(sorted({c.software_generation for c in claims if c.software_generation})),
            tuple(sorted({c.cognitive_model_identity for c in claims if c.cognitive_model_identity})),
            tuple(sorted({c.developmental_history_boundary for c in claims if c.developmental_history_boundary})),
            PROJECTION_POLICY, dict(FALSE_AUTHORITY))
        digest = _digest(raw.semantic_payload())
        return replace(raw, projection_id="cognitive-self-model-" + digest[7:31], projection_digest=digest)

    def reconcile(self, snapshot: WorldStateSnapshot, *, tick_id: str) -> SelfModelReconciliation:
        validation = validate_snapshot(snapshot)
        if not validation.valid or snapshot.validation_posture != "valid":
            raise LongitudinalSelfModelError("invalid_world_state_snapshot:" + ",".join(validation.findings))
        if not tick_id or any(snapshot.authority.values()):
            raise LongitudinalSelfModelError("invalid_reconciliation_context")
        for fact in snapshot.facts:
            if not fact.source.source_id or not fact.source.digest or fact.source.finding != "ok":
                raise LongitudinalSelfModelError("missing_or_invalid_source_provenance")
            if any(bool(fact.payload.get(key)) for key in FORBIDDEN_PREDICATES):
                raise LongitudinalSelfModelError("authority_or_unsupported_claim_smuggling")

        history = self._load()
        for history_item in history:
            if history_item.snapshot_id == snapshot.snapshot_id:
                if history_item.snapshot_digest != snapshot.digest:
                    raise LongitudinalSelfModelError("snapshot_identity_digest_mismatch")
                return history_item

        generation = len(history) + 1
        if generation > MAX_RECONCILIATION_ENTRIES:
            raise LongitudinalSelfModelError("reconciliation_entry_limit_exceeded")
        previous = history[-1] if history else None
        prior_current = {claim.claim_key: claim for claim in previous.claims if claim.status in {"current", "contradicted", "unresolved"}} if previous else {}
        candidates: dict[str, list[tuple[WorldStateFact, str, Any, str]]] = {}
        for fact in snapshot.facts:
            for predicate, value, category in _fact_predicates(fact):
                if predicate in FORBIDDEN_PREDICATES:
                    raise LongitudinalSelfModelError("unsupported_predicate")
                candidates.setdefault(_claim_key(fact, predicate), []).append((fact, predicate, value, category))
        if sum(len(items) for items in candidates.values()) > MAX_CLAIMS:
            raise LongitudinalSelfModelError("claim_limit_exceeded")

        new_claims: list[SelfModelClaim] = []
        active_ids_by_key: dict[str, tuple[str, ...]] = {}
        conflict_fact_ids = {fid for conflict in snapshot.conflicts for fid in conflict.fact_ids}
        for key, items in sorted(candidates.items()):
            grouped: dict[str, list[tuple[WorldStateFact, str, Any, str]]] = {}
            for item in items:
                grouped.setdefault(json.dumps(item[2], sort_keys=True, separators=(",", ":")), []).append(item)
            contradicted = len(grouped) > 1 or any(item[0].fact_id in conflict_fact_ids for item in items)
            ids: list[str] = []
            for group in grouped.values():
                facts = [item[0] for item in group]
                predicate, value, category = group[0][1], group[0][2], group[0][3]
                cid = _claim_id(key, value, [fact.fact_id for fact in facts]); ids.append(cid)
                prior = prior_current.get(key)
                supersedes = (prior.claim_id,) if prior and prior.value != value else ()
                source_times = tuple(sorted({str(fact.observed_at) for fact in facts if fact.observed_at is not None}))
                payloads = [fact.payload for fact in facts]
                freshnesses = {fact.source.staleness for fact in facts}
                declared_freshnesses = {str(payload.get("declared_source_freshness", "unknown")).lower()
                                        for payload in payloads if "declared_source_freshness" in payload}
                unauthenticated_observation = any(payload.get("observer_issuer_posture")
                    == "unverified_caller_assertion" for payload in payloads)
                all_freshnesses = freshnesses | declared_freshnesses
                historical_interpretation = category == "historical_interpretation"
                freshness = ("unknown" if historical_interpretation or unauthenticated_observation else
                             "stale" if all_freshnesses & {"stale", "expired"} else
                             "unknown" if all_freshnesses & {"unknown", "undated"} else
                             "aging" if "aging" in all_freshnesses else "fresh")
                if "not_applicable" in all_freshnesses and not all_freshnesses & {
                        "fresh", "current", "aging", "stale", "expired", "undated", "unknown"}:
                    freshness = "not_applicable"
                def context(names: Sequence[str]) -> str | None:
                    vals = {str(payload[name]) for payload in payloads for name in names if name in payload}
                    return next(iter(vals)) if len(vals) == 1 else None
                new_claims.append(SelfModelClaim(
                    cid, key, facts[0].subject.subject_id, facts[0].subject.subject_kind,
                    predicate, value, "historical_and_current", category, facts[0].stage,
                    "contradicted" if contradicted else ("historical" if historical_interpretation
                        or freshness in {"stale", "unknown", "not_applicable"} else "current"),
                    freshness, "contradicted" if contradicted else "consistent",
                    ("unverified_caller_assertion" if unauthenticated_observation else
                     min((fact.evidence_strength for fact in facts), default="unknown")),
                    tuple(sorted({fact.source.source_id for fact in facts})),
                    tuple(sorted({fact.source.digest for fact in facts})),
                    tuple(sorted(fact.fact_id for fact in facts)), snapshot.snapshot_id, snapshot.digest,
                    source_times, prior.first_supported_generation if prior and prior.value == value else generation,
                    generation, prior.first_supported_tick if prior and prior.value == value else tick_id, tick_id,
                    supersedes, (), context(("software_generation", "runtime_generation")),
                    context(("cognitive_model_id", "serving_model", "model_id")),
                    context(("developmental_history_boundary",)),
                    current_truth=False, interpretation=historical_interpretation,
                ))
            active_ids_by_key[key] = tuple(sorted(ids))

        if previous:
            for old in previous.claims:
                replacements = active_ids_by_key.get(old.claim_key, ())
                matching = any(claim.claim_id == old.claim_id for claim in new_claims)
                if not matching:
                    new_claims.append(replace(old, status="historical" if replacements else "withdrawn",
                                              freshness="superseded" if replacements else "stale",
                                              superseded_by=replacements, last_supported_generation=generation - 1))

        shell = SelfModelReconciliation(RECONCILIATION_SCHEMA, "", "", generation, tick_id,
                                        snapshot.snapshot_id, snapshot.digest,
                                        previous.reconciliation_id if previous else None,
                                        tuple(sorted(new_claims, key=lambda claim: (claim.claim_key, claim.claim_id, claim.status))),
                                        dict(FALSE_AUTHORITY))
        dg = _digest(_semantic(shell)); result = replace(shell, reconciliation_id="self-reconciliation-" + dg[7:31], reconciliation_digest=dg)
        self.entries.mkdir(parents=True, exist_ok=True)
        target = self.entries / f"{generation:020d}-{result.reconciliation_id}.json"
        self._publish_entry(target, result)
        return result


__all__ = ["CONFIG_SCHEMA", "FALSE_AUTHORITY", "CognitiveSelfModelProjection",
           "LongitudinalSelfModelError", "LongitudinalSelfModelOwner", "LongitudinalSelfModelRuntimeConfig",
           "SelfModelClaim", "SelfModelReconciliation", "load_runtime_config"]
