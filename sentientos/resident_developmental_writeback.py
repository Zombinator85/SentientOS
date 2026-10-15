"""Bounded, separately admitted resident developmental-history writeback.

Records produced here are historical interpretations.  They are never current
World-State truth, policy, authority, goals, or canonical explicit user memory.
"""
from __future__ import annotations

import json
import os
import stat
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

from .codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK,
    RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from .governed_local_model_invocation import (
    LocalModelInvoker,
    LocalModelInvocationBudget,
    LocalModelInvocationReceipt,
    RESIDENT_COGNITION_LESSON_OUTPUT_SCHEMA,
)
from .local_model_authority import digest_payload
from .canonical_memory import sentientos_memory_dir
from .private_file_custody import (
    PrivateFileCustodyError, list_bounded_json_names_at, open_private_directory,
    read_private_file_at, publish_immutable_bytes,
)
from .platform_fcntl import fcntl, require_flock
from .runtime_admission import AdmissionError, AdmissionEvidence, RuntimeAdmissionVerifier
from .world_state_board import WorldStateSnapshot, digest, to_dict, validate_snapshot
from .windows_handle_custody import WindowsHandleCustodyError, read_regular_files

SCHEMA_VERSION = "sentientos.resident_developmental_writeback:v1"
PRINCIPAL = "deterministic_resident_developmental_writeback_controller"
EFFECTS = tuple(sorted(RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION.required_effects))
PURPOSE = "resident_developmental_interpretation"
COGNITION_LESSON_PROVENANCE_KIND = "history_conditioned_cognition_conclusion:v1"
MAX_SELECTED_FACTS = 16
MAX_SELECTED_EVIDENCE_BYTES = 6000
MAX_RESOURCE_LINEAGE_SELECTED_EVIDENCE_BYTES = 8192
# A verified five-condition replacement run has a larger but still tightly
# bounded lineage vector. This allowance is limited to one v2 embodiment fact;
# all general and mixed-source selections retain the 6 KB cap.
MAX_MODEL_REPLACEMENT_SELECTED_EVIDENCE_BYTES = 8192
# A completed three-condition history-intervention run carries a bounded set
# of invocation and score identities. Keep its writeback allowance narrow to
# one explicitly projected experiment fact.
MAX_DEVELOPMENTAL_EXPERIMENT_SELECTED_EVIDENCE_BYTES = 10_240
# A single preregistered strategy-quality vector is larger than a general
# evidence fact but remains bounded to 12 KB and carries no execution claim.
MAX_STRATEGY_QUALITY_SELECTED_EVIDENCE_BYTES = 12_288
MAX_RETRIEVAL_RECORDS = 16
MAX_INTERPRETATION_CHARS = 4000
MAX_DURABLE_RECORDS = 4096
MAX_DURABLE_RECORD_BYTES = 1_048_576
MAX_DURABLE_RECORD_ROOT_BYTES = 134_217_728


class DevelopmentalWritebackError(ValueError):
    """Fail-closed runtime boundary violation."""


def _valid_optional_lower_sha256(value: Any) -> bool:
    return (value is None or (type(value) is str and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)))


def _has_bounded_integrity_controller_observation(selection: SelectedEvidence) -> bool:
    for fact in selection.facts:
        source = fact.get("source")
        subject = fact.get("subject")
        payload = fact.get("payload")
        if (not isinstance(source, Mapping)
                or source.get("kind") != "audit_trust"
                or source.get("source_id") != "integrity-controller:resident-daemon"
                or not isinstance(subject, Mapping)
                or subject.get("subject_kind") != "integrity_controller_observation"
                or fact.get("stage") != "observation"
                or fact.get("evidence_strength") not in {
                    "source_integrity_status", "integrity_controller_observation_unavailable"}
                or not isinstance(payload, Mapping)
                or payload.get("observation_schema") not in {
                    "sentientos.integrity_controller_observation:v1",
                    "sentientos.integrity_controller_observation:v2",
                }
                or payload.get("source_owner")
                    != "sentientos.integrity_controller.evaluate_integrity"
                or payload.get("controller_posture") not in {"ok", "warn", "fail", "unknown"}
                or payload.get("cause_unknown") is not True
                or payload.get("attack_established") is not False
                or payload.get("hostile_activity_established") is not False
                or payload.get("compromise_established") is not False
                or payload.get("effect_proven") is not False
                or payload.get("effect_authority") is not False
                or payload.get("authority") is not False
                or payload.get("current_truth") is not False
                or payload.get("read_only") is not True):
            continue
        gates = payload.get("gate_results")
        if (isinstance(gates, list) and len(gates) <= 32
                and type(payload.get("gate_count")) is int
                and payload["gate_count"] == len(gates)
                and all(isinstance(gate, Mapping)
                    and isinstance(gate.get("name"), str)
                    and 0 < len(gate["name"]) <= 64
                    and gate.get("status") in {"ok", "warn", "fail", "skipped"}
                    and isinstance(gate.get("reason"), str) and len(gate["reason"]) <= 160
                    and isinstance(gate.get("checked_at"), str)
                    and len(gate["checked_at"]) <= 64
                    and _valid_optional_lower_sha256(gate.get("failed_record_sha256"))
                    for gate in gates)):
            return True
    return False


def _valid_store_identity(value: Any, prefix: str) -> bool:
    marker = prefix + "-"
    return (isinstance(value, str) and len(value) == len(marker) + 24
            and value.startswith(marker)
            and all(character in "0123456789abcdef" for character in value[len(marker):]))


def _digest(value: Any) -> str:
    return "sha256:" + digest_payload(value)


def _identity(prefix: str, payload: Any) -> tuple[str, str]:
    digest = _digest(payload)
    return f"{prefix}-{digest.removeprefix('sha256:')[:24]}", digest


def _validate_candidate_source_bindings(candidate: "DevelopmentalCandidate") -> None:
    """Require one exact source row per source referenced by retained facts.

    Older records can omit selected fact payloads, so this check is limited to
    the versioned payload-bearing form. Mapping construction must not silently
    collapse duplicate source IDs: conflicting duplicates would make recovery
    depend on row order.
    """
    if not candidate.selected_facts:
        return
    if (len(candidate.selected_fact_ids) != len(set(candidate.selected_fact_ids))
            or len(candidate.selected_facts) != len(candidate.selected_fact_ids)):
        raise DevelopmentalWritebackError("candidate_source_binding_invalid")
    sources_by_id: dict[str, Mapping[str, Any]] = {}
    for source in candidate.selected_sources:
        source_id = source.get("source_id") if isinstance(source, Mapping) else None
        source_digest = source.get("digest") if isinstance(source, Mapping) else None
        if (not isinstance(source_id, str) or not source_id
                or not isinstance(source_digest, str) or len(source_digest) != 64
                or any(character not in "0123456789abcdef" for character in source_digest)
                or source_id in sources_by_id):
            raise DevelopmentalWritebackError("candidate_source_binding_invalid")
        sources_by_id[source_id] = source
    referenced_sources: dict[str, Mapping[str, Any]] = {}
    for fact in candidate.selected_facts:
        if not isinstance(fact, Mapping) or not isinstance(fact.get("source"), Mapping):
            raise DevelopmentalWritebackError("candidate_source_binding_invalid")
        source = fact["source"]
        source_id = source.get("source_id")
        if (not isinstance(source_id, str) or not source_id
                or source_id in referenced_sources
                and dict(referenced_sources[source_id]) != dict(source)):
            raise DevelopmentalWritebackError("candidate_source_binding_invalid")
        referenced_sources[source_id] = source
        if sources_by_id.get(source_id) != source:
            raise DevelopmentalWritebackError("candidate_source_binding_invalid")
    if set(sources_by_id) != set(referenced_sources):
        raise DevelopmentalWritebackError("candidate_source_binding_invalid")


def _runtime_history_projection(fact: Mapping[str, Any]) -> dict[str, Any] | None:
    """Retain compact process/serving lineage while binding it to the full source row."""
    source = fact.get("source")
    subject = fact.get("subject")
    original = fact.get("payload")
    if (not isinstance(source, Mapping)
            or source.get("kind") not in {"runtime_supervisor", "resource_governor"}
            or not isinstance(subject, Mapping) or not isinstance(original, Mapping)):
        return None
    kind = subject.get("subject_kind")
    summary: dict[str, Any]
    if kind == "chat_process_software_generation_invocation":
        if source.get("kind") != "resource_governor":
            return None
        lineage = original.get("chat_model_serving_lineage")
        if not isinstance(lineage, Mapping):
            return None
        serving_identity = lineage.get("serving_identity")
        serving_identity = serving_identity if isinstance(serving_identity, Mapping) else {}
        consumption = lineage.get("resource_consumption_receipt_digests", ())
        if not isinstance(consumption, (list, tuple)):
            return None
        summary = {
            "event_time": original.get("event_time"),
            "event_time_posture": original.get("event_time_posture"),
            "chat_model_serving_lineage": {
                key: lineage.get(key) for key in (
                    "invocation_receipt_id", "invocation_receipt_digest",
                    "invocation_request_id", "invocation_request_digest",
                    "installation_identity", "provisioning_id", "resource_allocation_digest",
                    "resource_attempt_id", "resource_linkage_digest",
                    "software_handoff_id", "software_handoff_digest",
                    "software_process_instance_id", "software_generation_digest",
                    "software_generation_startup_timestamp", "model_id",
                    "model_artifact_digest", "relation_posture", "currentness",
                    "serving_receipt_lineage_posture",
                    "software_serving_operation_binding_posture",
                    "effect_authority", "event_time", "event_time_posture")},
            "serving_identity": {key: serving_identity.get(key) for key in (
                "serving_session_id", "serving_operation_id", "serving_receipt_id",
                "serving_receipt_semantic_digest", "serving_operation_attempt_id",
                "serving_operation_attempt_semantic_digest", "activation_state_semantic_digest",
                "activation_generation", "activation_receipt_id",
                "activation_receipt_semantic_digest", "model_serving_admission_ref",
                "model_id", "artifact_id", "artifact_sha256", "runtime_id")},
            "resource_consumption_receipt_digests": list(consumption[:8]),
            "resource_consumption_receipt_digests_digest": digest(list(consumption)),
            "resource_consumption_receipt_digests_omitted": max(0, len(consumption) - 8),
            "projection_posture": "complete" if len(consumption) <= 8
                else "bounded_tail_incomplete",
            "active_model_identity_digest": (
                digest(dict(lineage["active_model_identity"]))
                if isinstance(lineage.get("active_model_identity"), Mapping) else None),
            "historical_only": True, "current_truth": False, "authority": False,
            "effect_proven": False,
        }
    elif kind == "chat_process_runtime_generation_observation":
        observation = original.get("chat_process_runtime_observation")
        links = original.get("linked_invocation_receipts", ())
        if not isinstance(observation, Mapping) or not isinstance(links, (list, tuple)):
            return None
        serving_receipt = observation.get("serving_receipt")
        serving = None
        if isinstance(serving_receipt, Mapping):
            serving_binding = serving_receipt.get("binding")
            serving = {key: serving_receipt.get(key) for key in (
                "receipt_id", "receipt_semantic_digest", "session_id")}
            if isinstance(serving_binding, Mapping):
                serving.update({key: serving_binding.get(key) for key in (
                    "serving_operation_id", "activation_state_semantic_digest",
                    "activation_generation", "model_id")})
        process_executable = observation.get("process_executable_observation")
        executable_summary = None
        if isinstance(process_executable, Mapping):
            executable_summary = {key: process_executable.get(key) for key in (
                "schema_version", "observation_status", "process_id",
                "observed_parent_process_id", "parent_process_matches",
                "process_start_time_ticks", "expected_executable_path_sha256",
                "observed_executable_path_sha256", "executable_path_matches_expected",
                "executable_image_sha256", "executable_image_size_bytes", "observed_at",
                "reason_code", "loaded_python_module_identity_posture", "effect_authority",
                "observation_digest")}
        selected_links: list[dict[str, Any]] = []
        for item in links[:4]:
            if not isinstance(item, Mapping):
                return None
            model_identity = item.get("active_model_identity_at_invocation")
            selected_link = {key: item.get(key) for key in (
                "invocation_receipt_id", "invocation_receipt_digest",
                "invocation_request_id", "invocation_request_digest",
                "serving_receipt_id", "serving_receipt_semantic_digest",
                "serving_operation_attempt_id", "serving_operation_attempt_semantic_digest",
                "serving_operation_id", "serving_session_id",
                "software_serving_operation_binding_posture",
                "resource_allocation_digest", "resource_attempt_id",
                "resource_effect_receipt_digest", "model_id", "model_artifact_digest",
                "linkage_posture", "current_model_claimed")}
            consumption_digests = item.get("resource_consumption_receipt_digests", ())
            if isinstance(consumption_digests, (list, tuple)):
                selected_link["resource_consumption_receipt_digests"] = list(consumption_digests[:8])
                selected_link["resource_consumption_receipt_digests_digest"] = digest(
                    list(consumption_digests))
                selected_link["resource_consumption_receipt_digests_omitted"] = max(
                    0, len(consumption_digests) - 8)
            else:
                return None
            selected_links.append(selected_link)
            if isinstance(model_identity, Mapping):
                selected_links[-1]["active_model_identity_digest"] = digest(dict(model_identity))
        summary = {
            "event_time": original.get("event_time"),
            "event_time_posture": original.get("event_time_posture"),
            "runtime_observation": {key: observation.get(key) for key in (
                "observation_semantic_digest", "runtime_supervisor_generation", "observed_at",
                "runtime_status", "handoff_id", "handoff_digest", "process_instance_id",
                "process_id", "parent_process_id", "software_generation_digest",
                "source_generation_scope", "configured_serving_operation_id",
                "configured_serving_receipt_posture", "independent_signature",
                "effect_authority")},
            "process_executable_observation": executable_summary,
            "serving_receipt_at_observation": serving,
            "invocation_linkage_posture": original.get("invocation_linkage_posture"),
            "linked_invocation_receipts": selected_links,
            "linked_invocation_receipts_digest": digest(list(links)),
            "linked_invocation_receipts_total": len(links),
            "linked_invocation_receipts_omitted": max(0, len(links) - len(selected_links)),
            "projection_posture": "complete" if len(links) <= len(selected_links)
                else "bounded_tail_incomplete",
            "historical_only": True, "current_truth": False, "authority": False,
            "effect_proven": False,
        }
    elif kind == "chat_process_recovery_transition":
        transition = original.get("chat_process_recovery_transition")
        times = original.get("phase_event_times")
        if not isinstance(transition, Mapping):
            return None
        def handoff_summary(value: Any) -> dict[str, Any] | None:
            if not isinstance(value, Mapping):
                return None
            return {key: value.get(key) for key in (
                "handoff_id", "handoff_digest", "process_instance_id",
                "software_generation_digest", "configured_serving_operation_id",
                "source_generation_scope")}
        summary = {
            "transition": {key: transition.get(key) for key in (
                "request_id", "request_semantic_digest", "intent_id", "intent_semantic_digest",
                "approval_id", "approval_semantic_digest", "runtime_supervisor_generation",
                "prior_serving_operation_id", "replacement_serving_operation_id",
                "prior_serving_receipt_id", "prior_serving_receipt_semantic_digest",
                "attempt_phase_digest", "readiness_phase_digest", "completion_phase_digest",
                "advanced_snapshot_digest", "decision_posture", "phase_posture",
                "phase_evidence_posture", "runtime_currentness", "terminal_receipt_digest",
                "terminal_status", "successor_serving_receipt_id",
                "successor_serving_receipt_semantic_digest", "successor_serving_session_id",
                "successor_serving_receipt_posture", "predecessor_serving_operation_binding_posture",
                "successor_serving_operation_binding_posture", "successor_configured_serving_operation_id",
                "effect_authority", "inference_performed")},
            "predecessor_handoff": handoff_summary(transition.get("predecessor_chat_process_handoff")),
            "successor_handoff": handoff_summary(transition.get("successor_chat_process_handoff")),
            "phase_event_times": dict(times) if isinstance(times, Mapping) else {},
            "historical_only": True, "current_truth": False, "authority": False,
            "effect_proven": False,
        }
    elif kind == "resident_parent_lifecycle_history":
        if source.get("kind") != "runtime_supervisor":
            return None
        receipts = original.get("lifecycle_receipts", ())
        if (not isinstance(receipts, (list, tuple)) or len(receipts) > 8
                or any(not isinstance(item, Mapping) for item in receipts)):
            return None
        selected_receipts = []
        for item in receipts:
            selected = {key: item.get(key) for key in (
                "sequence", "timestamp", "event", "receipt_digest", "child_pid",
                "generation_digest", "launch_provenance_digest", "readiness_basis",
                "reason", "presence")}
            if (type(selected["sequence"]) is not int
                    or not isinstance(selected["timestamp"], str)
                    or not isinstance(selected["event"], str)
                    or not isinstance(selected["receipt_digest"], str)):
                return None
            selected_receipts.append(selected)
        summary = {
            "schema_version": original.get("schema_version"),
            "commissioning_status": original.get("commissioning_status"),
            "resident_config_digest": original.get("resident_config_digest"),
            "child_spec_digest": original.get("child_spec_digest"),
            "parent_process_instance_id": original.get("parent_process_instance_id"),
            "parent_process_observation_digest": original.get("parent_process_observation_digest"),
            "parent_pid": original.get("parent_pid"), "child_pid": original.get("child_pid"),
            "parent_process_started_at": original.get("parent_process_started_at"),
            "process_relation_posture": original.get("process_relation_posture"),
            "source_observation_time_posture": original.get("source_observation_time_posture"),
            "parent_lifecycle_lineage": (
                dict(original["parent_lifecycle_lineage"])
                if isinstance(original.get("parent_lifecycle_lineage"), Mapping) else None),
            "launch_receipt_digest": original.get("launch_receipt_digest"),
            "journal_sequence": original.get("journal_sequence"),
            "journal_head_digest": original.get("journal_head_digest"),
            "lifecycle_receipts": selected_receipts,
            "lifecycle_receipts_digest": original.get("lifecycle_receipts_digest"),
            "lifecycle_receipts_omitted": original.get("lifecycle_receipts_omitted"),
            "projection_posture": original.get("projection_posture"),
            "latest_event": original.get("latest_event"),
            "event_time": original.get("event_time"),
            "event_time_posture": original.get("event_time_posture"),
            "generation_digest": original.get("generation_digest"),
            "generation_posture": original.get("generation_posture"),
            "launch_provenance_digest": original.get("launch_provenance_digest"),
            "maintenance_status_claim": original.get("maintenance_status_claim"),
            "freshness": "unknown", "current_running_generation_proven": False,
            "historical_only": True, "current_truth": False, "authority": False,
            "effect_authority": False, "effect_proven": False,
        }
    elif kind == "serving_operation_history":
        summary = {
            "serving_history_status": original.get("serving_history_status"),
            "serving_operation_id": original.get("serving_operation_id"),
            "attempt_id": original.get("attempt_id"),
            "attempt_semantic_digest": original.get("attempt_semantic_digest"),
            "receipt_id": original.get("receipt_id"),
            "receipt_semantic_digest": original.get("receipt_semantic_digest"),
            "serving_session_id": original.get("serving_session_id"),
            "activation_state_semantic_digest": original.get("activation_state_semantic_digest"),
            "activation_generation": original.get("activation_generation"),
            "model_id": original.get("model_id"), "artifact_id": original.get("artifact_id"),
            "runtime_id": original.get("runtime_id"),
            "event_time": original.get("event_time"),
            "event_time_posture": original.get("event_time_posture"),
            "observed_loaded_model_identity_digest": (
                digest(dict(original["observed_loaded_model_identity"]))
                if isinstance(original.get("observed_loaded_model_identity"), Mapping) else None),
            "historical_only": True, "current_truth": False, "authority": False,
            "effect_proven": False,
        }
    else:
        return None
    projection_binding = {
        "schema_version": "sentientos.runtime_history_projection:v1",
        "source_fact_id": str(fact.get("fact_id", "")),
        "source_payload_digest": digest(dict(original)),
        "source_record_digest": str(source.get("digest", "")),
        "projected_payload_digest": digest(summary),
    }
    projection_binding["projection_digest"] = digest(projection_binding)
    summary["interpretation_projection"] = projection_binding
    projected = dict(fact)
    projected["payload"] = summary
    return projected


def _valid_model_replacement_continuity_assessment(
    value: Any, *, disposition: Any,
) -> bool:
    if not isinstance(value, Mapping) or set(value) != {
            "schema", "history", "history_set_digest", "restart", "input", "model_use",
            "output", "classification", "improvement"}:
        return False
    if (value.get("schema") != "sentientos.model_replacement_continuity_assessment:v1"
            or value.get("history") not in {"bound", "unavailable"}
            or value.get("restart") != "not_established"
            or value.get("input") not in {"request_lineage_verified", "incomplete"}
            or value.get("model_use") != "not_established"
            or value.get("output") not in {"digest_association_only", "not_assessed"}
            or value.get("classification") != disposition
            or value.get("improvement") != "not_assessed"):
        return False
    record_set_digest = value.get("history_set_digest")
    if value.get("history") == "unavailable":
        return record_set_digest is None
    return (isinstance(record_set_digest, str) and len(record_set_digest) == 71
        and record_set_digest.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in record_set_digest[7:]))


def _selected_fact_byte_limit(facts: Sequence[Mapping[str, Any]]) -> int:
    if len(facts) == 1:
        fact = facts[0]
        source, subject, payload = fact.get("source"), fact.get("subject"), fact.get("payload")
        projection = (payload.get("interpretation_projection")
            if isinstance(payload, Mapping) else None)
        if (isinstance(source, Mapping) and source.get("kind") == "embodiment"
                and isinstance(subject, Mapping)
                and subject.get("subject_kind") == "developmental_model_replacement_experiment"
                and isinstance(payload, Mapping)
                and payload.get("current_truth") is False and payload.get("authority") is False
                and isinstance(projection, Mapping)
                and projection.get("schema_version")
                    == "sentientos.model_replacement_interpretation_projection:v2"
                and _valid_model_replacement_continuity_assessment(
                    payload.get("continuity_assessment"), disposition=fact.get("disposition"))):
            return MAX_MODEL_REPLACEMENT_SELECTED_EVIDENCE_BYTES
        if (isinstance(source, Mapping) and source.get("kind") == "embodiment"
                and isinstance(subject, Mapping)
                and subject.get("subject_kind") == "developmental_history_intervention_experiment"
                and isinstance(payload, Mapping)
                and payload.get("current_truth") is False and payload.get("authority") is False
                and payload.get("learning_established") is False
                and isinstance(projection, Mapping)
                and projection.get("schema_version")
                    == "sentientos.developmental_history_interpretation_projection:v1"):
            return MAX_DEVELOPMENTAL_EXPERIMENT_SELECTED_EVIDENCE_BYTES
        quality_result = (payload.get("decision_quality_result")
            if isinstance(payload, Mapping) else None)
        if (isinstance(source, Mapping) and source.get("kind") == "embodiment"
                and isinstance(subject, Mapping)
                and subject.get("subject_kind") == "embodied_strategy_decision_quality_evaluation"
                and isinstance(payload, Mapping)
                and payload.get("schema_version")
                    == "sentientos.embodied_strategy_decision_quality_feedback:v1"
                and payload.get("current_truth") is False
                and payload.get("execution_occurred") is False
                and payload.get("physical_effect_established") is False
                and payload.get("improvement_claimed") is False
                and payload.get("authority") == {
                    "effect_authority": False, "adoption_authority": False,
                    "observation_authority": False, "goal_authority": False,
                    "authoring_authority": False, "execution_authority": False}
                and isinstance(payload.get("event_dependencies"), list)
                and len(payload["event_dependencies"]) <= 8
                and isinstance(quality_result, Mapping)
                and quality_result.get("schema_version")
                    == "sentientos.embodied_strategy_decision_quality_result:v2"
                and quality_result.get("aggregate_score") is None
                and quality_result.get("condition_labels_used") is False
                and quality_result.get("overall_superiority_claimed") is False
                and quality_result.get("authority") == payload.get("authority")
                and fact.get("effect_proven") is False):
            return MAX_STRATEGY_QUALITY_SELECTED_EVIDENCE_BYTES
        projection = (payload.get("interpretation_projection")
            if isinstance(payload, Mapping) else None)
        if (isinstance(source, Mapping) and source.get("kind") == "resource_governor"
                and isinstance(subject, Mapping)
                and subject.get("subject_kind") in {
                    "causal_resource_consumption", "strategy_invocation_resource_lineage",
                    "model_replacement_invocation_resource_lineage",
                    "developmental_history_invocation_resource_lineage"}
                and isinstance(payload, Mapping)
                and payload.get("current_truth") is False and payload.get("authority") is False
                and fact.get("effect_proven") is False
                and isinstance(projection, Mapping)
                and projection.get("schema_version")
                    == "sentientos.resource_interpretation_projection:v1"):
            return MAX_RESOURCE_LINEAGE_SELECTED_EVIDENCE_BYTES
    return MAX_SELECTED_EVIDENCE_BYTES


def _model_replacement_interpretation_projection(
    fact: Mapping[str, Any], original: Mapping[str, Any], source: Mapping[str, Any],
) -> dict[str, Any]:
    """Bound a verified five-condition run for separately admitted history.

    The experiment artifact can be larger than the writeback input budget.
    Keep the complete condition identities and the causal fields needed to
    interpret them; bind every omitted payload byte through the original
    source-payload digest. Long identity arrays retain a digest and omission
    count, so a bounded projection never claims complete lineage after truncation.
    """
    raw_observations = original.get("observations")
    if not isinstance(raw_observations, (list, tuple)) or len(raw_observations) > 5:
        return dict(fact)
    omitted = False

    def bounded_values(value: Any, *, limit: int = 8) -> Any:
        nonlocal omitted
        if value is None:
            return None
        if not isinstance(value, (list, tuple)):
            omitted = True
            return {"lineage_posture": "invalid_source_shape", "value_digest": digest(value)}
        values = list(value)
        if len(values) <= limit:
            return values
        omitted = True
        return {"values": values[:limit], "count": len(values),
            "lineage_posture": "bounded_incomplete", "full_values_digest": digest(values),
            "omitted_count": len(values) - limit}

    def compact_sha256(value: Any) -> Any:
        # The enclosing versioned vectors declare raw lowercase SHA-256 hex;
        # removing the repeated algorithm prefix keeps the five-condition
        # evidence within the existing selected-evidence byte budget.
        return value[7:] if isinstance(value, str) and value.startswith("sha256:") else value

    observation_columns = ("cond", "obs", "obs_hash", "req", "req_hash", "withheld",
        "receipt", "receipt_hash", "output_hash", "event_time")
    observation_keys = ("condition_id", "observation_id", "observation_digest",
        "request_id", "request_digest", "history_withheld", "inference_receipt_id",
        "inference_receipt_digest", "output_digest", "inference_event_time")
    condition_rows: list[list[Any]] = []
    resource_attributions: list[dict[str, Any]] = []
    resource_postures: set[str] = set()
    event_time_postures: set[str] = set()
    serving_receipts: list[dict[str, Any]] = []
    model_artifacts: dict[str, set[str]] = {"model_a": set(), "model_b": set()}
    for raw in raw_observations:
        if not isinstance(raw, Mapping):
            return dict(fact)
        condition = raw.get("condition_id")
        role = ("model_a" if isinstance(condition, str)
            and condition.startswith("model_a") else "model_b")
        artifact_digest = raw.get("model_artifact_digest")
        if isinstance(artifact_digest, str) and artifact_digest:
            model_artifacts[role].add(artifact_digest)
        resource_linkage = {key: raw.get(key) for key in (
            "resource_allocation_digest", "resource_attempt_id", "resource_linkage_digest",
            "resource_attribution_posture") if raw.get(key) is not None}
        posture = raw.get("resource_attribution_posture")
        if isinstance(posture, str):
            resource_postures.add(posture)
        event_posture = raw.get("inference_event_time_posture")
        if isinstance(event_posture, str):
            event_time_postures.add(event_posture)
        if raw.get("resource_consumption_receipt_digests"):
            resource_linkage["consumption_receipt_digests"] = bounded_values(
                raw.get("resource_consumption_receipt_digests"))
        if any(resource_linkage.get(key) for key in (
                "resource_allocation_digest", "resource_attempt_id", "resource_linkage_digest",
                "consumption_receipt_digests")):
            resource_attributions.append({"condition_id": condition, **resource_linkage})
        serving = {key: raw.get(key) for key in (
            "model_serving_receipt_id", "model_serving_receipt_digest",
            "model_serving_lifetime_id", "model_serving_receipt_posture")
            if raw.get(key) is not None}
        if serving:
            serving_receipts.append({"condition_id": condition, **serving})
        row = [raw.get(key) for key in observation_keys]
        for index in (2, 4, 7, 8):
            row[index] = compact_sha256(row[index])
        condition_rows.append(row)
    if any(len(values) != 1 for values in model_artifacts.values()):
        omitted = True

    shared: dict[str, Any] = {}
    if condition_rows:
        first_raw = raw_observations[0]
        assert isinstance(first_raw, Mapping)
        shared["causal"] = [first_raw.get("causal_context_id"),
            first_raw.get("causal_context_digest")]
        shared["current"] = [first_raw.get("current_projection_id"),
            first_raw.get("current_projection_digest")]
        if any(first_raw.get(key) for key in (
                "prior_self_model_projection_id", "prior_self_model_projection_digest",
                "prior_self_model_source_tick")):
            shared["prior_self"] = [first_raw.get("prior_self_model_projection_id"),
                first_raw.get("prior_self_model_projection_digest"),
                first_raw.get("prior_self_model_source_tick")]
        if any(first_raw.get(key) for key in (
                "prior_epistemic_projection_id", "prior_epistemic_projection_digest",
                "prior_epistemic_source_tick", "prior_epistemic_state_ids", "prior_epistemic_state_digests")):
            shared["prior_epistemic"] = [first_raw.get("prior_epistemic_projection_id"),
                first_raw.get("prior_epistemic_projection_digest"),
                first_raw.get("prior_epistemic_source_tick"),
                bounded_values(first_raw.get("prior_epistemic_state_ids")),
                bounded_values(first_raw.get("prior_epistemic_state_digests"))]
        shared["prior_context_posture"] = first_raw.get("prior_cognitive_context_posture")
        # The run verifier already enforces one frozen current projection and
        # equal present/restored history. Retain that history once instead of
        # repeating it in three condition rows.
        present = next((item for item in raw_observations
            if isinstance(item, Mapping) and item.get("history_withheld") is False), None)
        if isinstance(present, Mapping):
            shared["history"] = [bounded_values(present.get("history_record_ids")),
                bounded_values(present.get("history_record_digests"))]

    raw_statuses = original.get("condition_statuses")
    statuses: list[dict[str, Any]] | None = None
    if isinstance(raw_statuses, (list, tuple)):
        if len(raw_statuses) > 5 or any(not isinstance(item, Mapping) for item in raw_statuses):
            omitted = True
        elif original.get("experiment_completion_posture") != "completed":
            statuses = [{key: item.get(key) for key in (
                "condition", "condition_id", "status", "condition_input_digest",
                "condition_start_digest", "condition_result_digest", "failure_posture")}
                for item in raw_statuses]
    elif raw_statuses is not None:
        omitted = True

    model_lineage = [
        [original.get("model_a_id"), original.get("model_a_identity_digest"),
            next(iter(model_artifacts["model_a"])) if len(model_artifacts["model_a"]) == 1 else None,
            original.get("model_a_provenance_digest"), original.get("model_a_provenance_availability")],
        [original.get("model_b_id"), original.get("model_b_identity_digest"),
            next(iter(model_artifacts["model_b"])) if len(model_artifacts["model_b"]) == 1 else None,
            original.get("model_b_provenance_digest"), original.get("model_b_provenance_availability")],
    ]
    model_lineage = [[row[0], *(compact_sha256(value) for value in row[1:4]), row[4]]
        for row in model_lineage]
    source_assessment = original.get("continuity_assessment")
    continuity_assessment = None
    if isinstance(source_assessment, Mapping):
        history_identity = source_assessment.get("history_identity")
        input_delivery = source_assessment.get("input_delivery")
        output_relation = source_assessment.get("output_relation")
        if (isinstance(history_identity, Mapping) and isinstance(input_delivery, Mapping)
                and isinstance(output_relation, Mapping)):
            continuity_assessment = {
                "schema": source_assessment.get("schema_version"),
                "history": ("bound" if history_identity.get("posture")
                    == "frozen_context_record_set_bound" else "unavailable"),
                "history_set_digest": history_identity.get("record_set_digest"),
                "restart": "not_established",
                "input": ("request_lineage_verified" if input_delivery.get("posture")
                    == "condition_request_lineage_verified" else "incomplete"),
                "model_use": "not_established",
                "output": ("digest_association_only" if output_relation.get("posture")
                    == "digest_level_observed_association_only" else "not_assessed"),
                "classification": output_relation.get("classification"),
                "improvement": "not_assessed",
            }
    summary = {
        "run_id": original.get("run_id"), "run_digest": original.get("run_digest"),
        "protocol_id": original.get("protocol_id"), "protocol_digest": original.get("protocol_digest"),
        "repo_generation_posture": original.get("declared_repository_generation_posture"),
        "software_posture": original.get("software_generation_posture"),
        "model_lineage": model_lineage,
        "context": shared,
        "vector_hash_encoding": "sha256_hex",
        "condition_columns": list(observation_columns),
        "conditions": condition_rows,
        "resource_postures": sorted(resource_postures),
        "event_time_postures": sorted(event_time_postures),
        "completion": original.get("experiment_completion_posture"),
        "condition_journal": original.get("condition_lineage_posture"),
        "claims": original.get("claims_posture"), "non_claims": original.get("non_claims"),
        "current_truth": False, "authority": False,
        "projection_posture": "bounded_context_incomplete" if omitted else "complete",
    }
    if continuity_assessment is not None:
        summary["continuity_assessment"] = continuity_assessment
    if resource_attributions:
        summary["resource_attributions"] = resource_attributions
    if serving_receipts:
        summary["serving_receipts"] = serving_receipts
    if statuses:
        summary["condition_statuses"] = statuses
    objective = original.get("objective_evaluation")
    if objective is not None:
        objective_commitment_safe = (original.get(
            "objective_task_commitment_posture")
            == "salted_private_oracle_commitment:v1")
        valid_deltas = {-1, 0, 1}
        suite_assessment = (isinstance(objective, Mapping)
            and objective.get("assessment") == "preregistered_probe_suite_scored")
        probe_count = objective.get("probe_count") if isinstance(objective, Mapping) else None
        score_digests = objective.get("condition_score_digests") if isinstance(objective, Mapping) else None
        digests_valid = (isinstance(score_digests, (list, tuple)) and len(score_digests) <= 5
            and all(isinstance(item, str) and len(item) == 71 and item.startswith("sha256:")
                and all(character in "0123456789abcdef" for character in item[7:])
                for item in score_digests))
        def delta_valid(item: Any) -> bool:
            return item is None or (type(item) is int and item in valid_deltas)

        def probe_delta_valid(item: Any) -> bool:
            return item is None or (type(item) is int and type(probe_count) is int
                and 2 <= probe_count <= 16 and -probe_count <= item <= probe_count)

        suite_fields = {"probe_count", "model_a_history_correct_probe_delta",
            "model_b_history_correct_probe_delta", "restoration_correct_probe_delta"}
        suite_projection_valid = (
            (suite_assessment and type(probe_count) is int and 2 <= probe_count <= 16
                and suite_fields.issubset(objective)
                and all(probe_delta_valid(objective.get(key)) for key in (
                    "model_a_history_correct_probe_delta", "model_b_history_correct_probe_delta",
                    "restoration_correct_probe_delta")))
            or (not suite_assessment and isinstance(objective, Mapping)
                and not suite_fields.intersection(objective)))

        if (objective_commitment_safe and isinstance(objective, Mapping)
                and isinstance(objective.get("plan_digest"), str)
                and len(objective["plan_digest"]) == 71
                and objective["plan_digest"].startswith("sha256:")
                and all(character in "0123456789abcdef" for character in objective["plan_digest"][7:])
                and digests_valid and isinstance(score_digests, (list, tuple))
                and delta_valid(objective.get("model_a_history_accuracy_delta"))
                and delta_valid(objective.get("model_b_history_accuracy_delta"))
                and type(objective.get("restoration_correctness_stable")) in {bool, type(None)}
                and suite_projection_valid
                and objective.get("assessment") in {"single_preregistered_task_scored",
                    "preregistered_probe_suite_scored",
                    "unscoreable_missing_output"}
                and objective.get("scope") == "task_correctness_not_general_learning_or_weight_change"
                and objective.get("model_behavior_posture") ==
                    "endpoint_execution_receipts_not_independent_model_attestation"):
            summary["objective_evaluation"] = {
                "plan_digest": objective["plan_digest"],
                "condition_score_digests": [compact_sha256(item) for item in score_digests],
                "model_a_history_accuracy_delta": objective.get("model_a_history_accuracy_delta"),
                "model_b_history_accuracy_delta": objective.get("model_b_history_accuracy_delta"),
                "restoration_correctness_stable": objective.get("restoration_correctness_stable"),
                "assessment": objective["assessment"], "scope": objective["scope"],
                "model_behavior_posture": objective["model_behavior_posture"],
            }
            summary["objective_task_commitment_posture"] = (
                "salted_private_oracle_commitment:v1")
            if suite_assessment:
                summary["objective_evaluation"].update({key: objective[key] for key in suite_fields})
        else:
            omitted = True
            summary["objective_evaluation_posture"] = (
                "legacy_oracle_commitment_redacted" if not objective_commitment_safe
                else "invalid_bounded_score_source")
    score_contract = original.get("objective_score_contract")
    if score_contract is not None:
        valid_contract = False
        if isinstance(score_contract, Mapping):
            def valid_contract_digest(value: Any) -> bool:
                return (isinstance(value, str) and len(value) == 71
                    and value.startswith("sha256:")
                    and all(character in "0123456789abcdef" for character in value[7:]))

            semantic = {key: score_contract.get(key) for key in (
                "schema_version", "task_plan_digest", "task_digest",
                "score_schema_version", "evaluator", "condition_score_digests")}
            contract_digests = semantic.get("condition_score_digests")
            score_summary = summary.get("objective_evaluation")
            valid_contract = (
                set(score_contract) == (set(semantic) | {"contract_digest"})
                and semantic.get("schema_version") ==
                    "sentientos.model_replacement_objective_score_contract:v1"
                and valid_contract_digest(semantic.get("task_plan_digest"))
                and valid_contract_digest(semantic.get("task_digest"))
                and semantic.get("score_schema_version") ==
                    "sentientos.objective_task_score:v3"
                and semantic.get("evaluator") in {
                    "deterministic_exact_integer_oracle_v1",
                    "deterministic_exact_integer_suite_oracle_v2"}
                and isinstance(contract_digests, list)
                and len(contract_digests) == 5
                and all(valid_contract_digest(value) for value in contract_digests)
                and isinstance(score_summary, Mapping)
                and original.get("objective_task_commitment_posture") ==
                    "salted_private_oracle_commitment:v1"
                and semantic.get("task_plan_digest") == score_summary.get("plan_digest")
                and [compact_sha256(value) for value in contract_digests]
                    == score_summary.get("condition_score_digests")
                and score_contract.get("contract_digest") == "sha256:" + digest(semantic))
        if valid_contract:
            summary["objective_score_contract"] = dict(score_contract)
            summary["objective_task_commitment_posture"] = (
                "salted_private_oracle_commitment:v1")
        else:
            omitted = True
            summary["objective_score_contract_posture"] = "invalid_or_inconsistent"
    projection_binding = {
        "schema_version": "sentientos.model_replacement_interpretation_projection:v2",
        "source_fact_id": str(fact.get("fact_id", "")),
        "source_payload_digest": digest(dict(original)),
        "source_record_digest": str(source.get("digest", "")),
        "projected_payload_digest": digest(summary),
    }
    projection_binding["projection_digest"] = digest(projection_binding)
    projected = dict(fact)
    projected["payload"] = {**summary, "interpretation_projection": projection_binding}
    return projected


def _resource_interpretation_projection(fact: Mapping[str, Any]) -> dict[str, Any]:
    """Keep resource interpretation bounded while binding it to the full source fact."""
    source = fact.get("source")
    subject = fact.get("subject")
    original = fact.get("payload")
    runtime_projection = _runtime_history_projection(fact)
    if runtime_projection is not None:
        return runtime_projection
    if (isinstance(source, Mapping) and source.get("kind") == "embodiment"
            and isinstance(subject, Mapping)
            and subject.get("subject_kind") == "developmental_model_replacement_experiment"
            and isinstance(original, Mapping)):
        return _model_replacement_interpretation_projection(fact, original, source)
    if (isinstance(source, Mapping) and source.get("kind") == "embodiment"
            and isinstance(subject, Mapping)
            and subject.get("subject_kind") == "developmental_history_intervention_experiment"
            and isinstance(original, Mapping)):
        return _developmental_history_interpretation_projection(fact, original, source)
    if (not isinstance(source, Mapping) or source.get("kind") != "resource_governor"
            or not isinstance(subject, Mapping) or not isinstance(original, Mapping)):
        return dict(fact)
    if subject.get("subject_kind") in {
            "strategy_invocation_resource_lineage",
            "model_replacement_invocation_resource_lineage",
            "developmental_history_invocation_resource_lineage"}:
        # Joined attribution records can carry a sizeable frozen-history
        # context. The writeback request has a smaller independent byte bound,
        # so retain exact causal identities and a digest of the unabridged
        # source payload while bounding optional context lists here.
        linkage = original.get("resource_linkage")
        if not isinstance(linkage, Mapping):
            return dict(fact)
        request_context = original.get("task_context")
        context = dict(request_context) if isinstance(request_context, Mapping) else {}
        history_ids = context.get("history_record_ids")
        omitted_history_count = 0
        if isinstance(history_ids, (list, tuple)):
            full_history_digest = digest(list(history_ids))
            omitted_history_count = max(0, len(history_ids) - 32)
            context["history_record_ids"] = list(history_ids[:32])
            if omitted_history_count:
                context["history_record_ids_digest"] = full_history_digest
                context["history_record_ids_omitted"] = omitted_history_count
        history_digests = context.get("history_record_digests")
        omitted_history_digest_count = 0
        if isinstance(history_digests, (list, tuple)):
            if isinstance(history_ids, (list, tuple)) and len(history_digests) != len(history_ids):
                context["history_lineage_posture"] = "source_record_identity_pairs_incomplete"
            context["history_record_digests"] = list(history_digests[:32])
            if len(history_digests) > 32:
                omitted_history_digest_count = len(history_digests) - 32
                context["history_record_digests_digest"] = digest(list(history_digests))
                context["history_record_digests_omitted"] = omitted_history_digest_count
        compact_linkage = {key: linkage.get(key) for key in (
            "request_id", "request_digest", "purpose", "model_id", "model_artifact_digest",
            "invocation_authority_map_digest",
            "allocation_digest", "attempt_id", "consumption_receipt_digests",
            "linkage_digest", "effect_receipt_id", "effect_receipt_digest") if key in linkage}
        receipt_digests = compact_linkage.get("consumption_receipt_digests")
        omitted_receipt_count = 0
        if isinstance(receipt_digests, (list, tuple)):
            full_receipt_digest = digest(list(receipt_digests))
            omitted_receipt_count = max(0, len(receipt_digests) - 16)
            compact_linkage["consumption_receipt_digests"] = list(receipt_digests[:16])
            if omitted_receipt_count:
                compact_linkage["consumption_receipt_digests_digest"] = full_receipt_digest
                compact_linkage["consumption_receipt_digests_omitted"] = omitted_receipt_count
        raw_event_times = original.get("event_times", ())
        event_times = raw_event_times if isinstance(raw_event_times, (list, tuple)) else ()
        selected_times = list(event_times[-16:])
        projection_posture = "complete" if not omitted_history_count and not omitted_history_digest_count \
            and not omitted_receipt_count \
            and context.get("history_lineage_posture") != "source_record_identity_pairs_incomplete" \
            and len(event_times) <= 16 else "bounded_context_incomplete"
        summary = {
            "resource_linkage": compact_linkage,
            "resource_record": original.get("resource_record"),
            "allocation_identity": original.get("allocation_identity"),
            "invocation_receipt_id": original.get("invocation_receipt_id"),
            "invocation_receipt_digest": original.get("invocation_receipt_digest"),
            "principal_id": original.get("principal_id"),
            "principal_binding_digest": original.get("principal_binding_digest"),
            "model_attribution": original.get("model_attribution"),
            "software_attribution": original.get("software_attribution"),
            "model_replacement_run_id": original.get("model_replacement_run_id"),
            "model_replacement_run_digest": original.get("model_replacement_run_digest"),
            "model_replacement_source_record_id": original.get("model_replacement_source_record_id"),
            "model_replacement_source_record_digest": original.get(
                "model_replacement_source_record_digest"),
            "model_replacement_condition": original.get("model_replacement_condition"),
            "model_identity_digest": original.get("model_identity_digest"),
            "model_provenance_manifest_digest": original.get("model_provenance_manifest_digest"),
            "causal_context_id": original.get("causal_context_id"),
            "causal_context_digest": original.get("causal_context_digest"),
            "task_context": context,
            "event_times": selected_times,
            "lineage_findings": list(original.get("lineage_findings", ()))[:16],
            "shared_host_cpu_gpu_attribution": original.get("shared_host_cpu_gpu_attribution"),
            "interpretation": original.get("interpretation"),
            "current_truth": False, "authority": False,
            "lineage_projection_posture": projection_posture,
        }
        for key in ("developmental_history_run_id", "developmental_history_run_digest",
                "developmental_history_source_record_id",
                "developmental_history_source_record_digest",
                "developmental_history_condition", "developmental_history_observation_id",
                "developmental_history_observation_digest", "developmental_history_protocol_id",
                "developmental_history_protocol_digest", "task_family_id", "active_model_identity",
                "resource_measurement_posture"):
            if key in original:
                summary[key] = original[key]
        # Retain a bounded, receipt-identified view of measured consumption so
        # later cognition can compare task outcomes with the evidence that
        # accompanied them.  The enclosing source-payload digest continues to
        # bind the complete owner-produced lineage record.
        if "resource_consumption_evidence" in original:
            measurements = original.get("resource_consumption_evidence")
            if not isinstance(measurements, (list, tuple)):
                raise DevelopmentalWritebackError("resource_measurement_projection_invalid")
            source_linkage = original.get("resource_linkage")
            source_receipt_digests = (source_linkage.get("consumption_receipt_digests", ())
                if isinstance(source_linkage, Mapping) else ())
            if not isinstance(source_receipt_digests, (list, tuple)):
                raise DevelopmentalWritebackError("resource_measurement_projection_invalid")
            for measurement in measurements:
                measured_values = (measurement.get("measured_values")
                    if isinstance(measurement, Mapping) else None)
                receipt_digest = (measurement.get("receipt_digest")
                    if isinstance(measurement, Mapping) else None)
                if (not isinstance(measurement, Mapping)
                        or not isinstance(measurement.get("receipt_id"), str)
                        or not measurement.get("receipt_id")
                        or not isinstance(receipt_digest, str)
                        or len(receipt_digest) != 64
                        or any(character not in "0123456789abcdef" for character in receipt_digest)
                        or receipt_digest not in source_receipt_digests
                        or not isinstance(measured_values, Mapping)
                        or not isinstance(measurement.get("measurement_posture"), Mapping)):
                    raise DevelopmentalWritebackError("resource_measurement_projection_invalid")
                for key, value in measured_values.items():
                    if key not in {"generation_attempted", "call_units_consumed",
                            "generated_output_size_bytes", "returned_output_size_bytes",
                            "output_truncated", "latency_ms"}:
                        continue
                    valid_measurement = (
                        type(value) is bool if key in {"generation_attempted", "output_truncated"}
                        else type(value) is int and value >= 0
                            if key in {"call_units_consumed", "generated_output_size_bytes",
                                "returned_output_size_bytes"}
                            else type(value) in {int, float} and value >= 0)
                    if not valid_measurement:
                        raise DevelopmentalWritebackError(
                            "resource_measurement_projection_invalid")
            measurement_fields = {"generation_attempted", "call_units_consumed",
                "generated_output_size_bytes", "returned_output_size_bytes",
                "output_truncated", "latency_ms"}
            posture_fields = {"token_count", "shared_host_cpu_gpu"}
            summary["resource_consumption_evidence"] = [{
                "receipt_id": item["receipt_id"],
                "receipt_digest": item["receipt_digest"],
                "measured_values": {key: value for key, value in
                    item["measured_values"].items() if key in measurement_fields},
                "measurement_posture": {key: value for key, value in
                    item["measurement_posture"].items() if key in posture_fields
                    and (isinstance(value, (bool, int, float))
                        or isinstance(value, str) and len(value) <= 64)},
            } for item in measurements[:8]]
            if len(measurements) > 8:
                summary["resource_consumption_evidence_omitted_count"] = len(measurements) - 8
                summary["resource_consumption_evidence_omitted_digest"] = digest(list(measurements))
        if "task_outcome" in original:
            task_outcome = original.get("task_outcome")
            if not isinstance(task_outcome, Mapping):
                raise DevelopmentalWritebackError("resource_task_outcome_projection_invalid")
            posture = task_outcome.get("posture")
            if posture in {"not_scored_or_legacy", "score_binding_invalid"}:
                if set(task_outcome) != {"posture"}:
                    raise DevelopmentalWritebackError(
                        "resource_task_outcome_projection_invalid")
            elif posture == "run_owner_score_bound_to_condition":
                expected_outcome = {"posture", "condition_id", "inference_receipt_id",
                    "inference_receipt_digest", "output_digest", "score_digest",
                    "score_status", "correct", "correct_count", "probe_count",
                    "oracle_answer_retained", "causal_effect_established"}
                linkage = original.get("resource_linkage")
                condition_id = original.get("developmental_history_condition",
                    original.get("model_replacement_condition"))
                count = task_outcome.get("correct_count")
                probes = task_outcome.get("probe_count")
                score_status = task_outcome.get("score_status")
                correct = task_outcome.get("correct")
                family_id = context.get("task_family_id")
                family_probe_count = context.get("task_family_probe_count")
                family_counts_valid = (
                    (family_id is None and family_probe_count is None)
                    or ((family_id is None or
                        isinstance(family_id, str) and bool(family_id))
                    and type(family_probe_count) is int and 2 <= family_probe_count <= 16
                    and type(count) is int and type(probes) is int
                    and probes == family_probe_count))
                score_semantics_valid = (
                    (score_status == "correct" and correct is True)
                    or (score_status in {"incorrect", "invalid_answer"} and correct is False)
                    or (score_status in {"output_unavailable", "output_truncated"}
                        and correct is None))
                if score_semantics_valid and count is not None:
                    score_semantics_valid = (
                        (score_status == "correct" and count == probes)
                        or (score_status in {"incorrect", "invalid_answer"}
                            and count < probes)
                        or (score_status in {"output_unavailable", "output_truncated"}
                            and count == 0))
                if (set(task_outcome) != expected_outcome
                        or task_outcome.get("condition_id") != condition_id
                        or task_outcome.get("inference_receipt_id") != original.get(
                            "invocation_receipt_id")
                        or task_outcome.get("inference_receipt_digest") != original.get(
                            "invocation_receipt_digest")
                        or not isinstance(task_outcome.get("output_digest"), str)
                        or len(task_outcome["output_digest"]) not in {64, 71}
                        or (len(task_outcome["output_digest"]) == 71
                            and not task_outcome["output_digest"].startswith("sha256:"))
                        or not isinstance(task_outcome.get("score_digest"), str)
                        or len(task_outcome["score_digest"]) != 71
                        or not task_outcome["score_digest"].startswith("sha256:")
                        or not score_semantics_valid
                        or not family_counts_valid
                        or (task_outcome.get("correct") is not None
                            and type(task_outcome.get("correct")) is not bool)
                        or not ((count is None and probes is None) or (
                            type(count) is int and type(probes) is int
                            and 0 <= count <= probes <= 16))
                        or task_outcome.get("oracle_answer_retained") is not False
                        or task_outcome.get("causal_effect_established") is not False
                        or not isinstance(linkage, Mapping)
                        or linkage.get("effect_receipt_id") != task_outcome.get(
                            "inference_receipt_id")
                        or linkage.get("effect_receipt_digest") != task_outcome.get(
                            "inference_receipt_digest")):
                    raise DevelopmentalWritebackError(
                        "resource_task_outcome_projection_binding_invalid")
            else:
                raise DevelopmentalWritebackError("resource_task_outcome_projection_invalid")
            summary["task_outcome"] = dict(task_outcome)
        if "resource_consumption_evidence" in original:
            evidence = original.get("resource_consumption_evidence")
            summary["resource_consumption_evidence"] = (list(evidence[:2])
                if isinstance(evidence, (list, tuple)) else [])
        projection_binding = {"schema_version": "sentientos.resource_interpretation_projection:v1",
            "source_fact_id": str(fact.get("fact_id", "")),
            "source_payload_digest": digest(dict(original)),
            "source_record_digest": str(source.get("digest", "")),
            "projected_payload_digest": digest(summary)}
        projection_binding["projection_digest"] = digest(projection_binding)
        summary["interpretation_projection"] = projection_binding
        projected = dict(fact)
        projected["payload"] = summary
        return projected
    if (subject.get("subject_kind") != "causal_resource_consumption"
            or not isinstance(original.get("ledger_digest"), str)):
        return dict(fact)
    allocations = tuple(item for item in original.get("allocations", ()) if isinstance(item, Mapping))
    attempts = tuple(item for item in original.get("attempts", ()) if isinstance(item, Mapping))
    receipts = tuple(item for item in original.get("consumption_receipts", ()) if isinstance(item, Mapping))
    invocations = tuple(item for item in original.get("invocation_receipts", ()) if isinstance(item, Mapping))
    # Keep a small verified receipt-chain tail. The original source-payload
    # digest and each retained receipt digest bind omitted historical entries.
    selected_receipts = receipts[-2:]
    omitted_receipts = receipts[:-2]
    selected_invocations = invocations[-4:]
    selected_attempts = attempts[-8:]
    compact_allocations = tuple({key: item.get(key) for key in
        ("allocation_id", "allocation_digest", "principal_id", "principal_binding_digest",
         "resource_kind", "resource_specific_bounds", "policy_digest", "epoch") if key in item}
        for item in allocations[:4])
    compact_attempts = tuple({"attempt_id": item.get("attempt_id"),
        "allocation_id": item.get("allocation_id"), "status": item.get("status")}
        for item in selected_attempts)
    allocation_index_by_digest = {str(item.get("allocation_digest")): index
        for index, item in enumerate(compact_allocations)
        if isinstance(item.get("allocation_digest"), str)}
    compact_receipts_list: list[dict[str, Any]] = []
    measured_postures: list[dict[str, Any]] = []
    receipt_allocation_links_complete = True
    for item in selected_receipts:
        selected_receipt = {key: item.get(key) for key in
            ("receipt_id", "receipt_digest", "attempt_id", "state", "observed_at",
             "previous_receipt_digest", "effect_receipt_digest") if key in item}
        allocation_digest = item.get("allocation_digest")
        principal_digest = item.get("principal_binding_digest")
        allocation_index = allocation_index_by_digest.get(str(allocation_digest))
        if (allocation_index is not None and
                compact_allocations[allocation_index].get("principal_binding_digest") == principal_digest):
            # The allocation table carries the exact allocation and principal
            # identities once; this index preserves the receipt-to-allocation
            # binding without repeating two 64-byte digests per receipt.
            selected_receipt["allocation_index"] = allocation_index
        else:
            receipt_allocation_links_complete = False
            selected_receipt["allocation_digest"] = allocation_digest
            selected_receipt["principal_binding_digest"] = principal_digest
        raw_measurement = item.get("resource_specific_measurement")
        if isinstance(raw_measurement, Mapping):
            # Allocation bounds already carry the configured limits. Preserve
            # exact scalar measurements (including explicit null/unknowns) and
            # avoid repeating that bound document in every receipt.
            selected_measurement = {key: raw_measurement.get(key) for key in (
                "generation_attempted", "call_units_consumed", "generated_output_size_bytes",
                "returned_output_size_bytes", "output_truncated", "latency_ms",
                "invocation_outcome", "actual_token_count") if key in raw_measurement}
            selected_receipt["resource_specific_measurement"] = selected_measurement
        posture = item.get("measurement_posture")
        if isinstance(posture, Mapping):
            measured_postures.append({"receipt_id": item.get("receipt_id"),
                "receipt_digest": item.get("receipt_digest"), "posture": dict(posture)})
        compact_receipts_list.append(selected_receipt)
    compact_receipts = tuple(compact_receipts_list)
    retained_attempt_ids = {str(item.get("attempt_id")) for item in compact_attempts}
    receipt_attempt_links_complete = all(
        isinstance(item.get("attempt_id"), str)
        and str(item.get("attempt_id")) in retained_attempt_ids
        for item in selected_receipts)
    posture_fields = sorted({str(key) for item in measured_postures
        for key in item["posture"]})
    measurement_posture_summary = {
        "scope": "retained_consumption_receipt_tail",
        "per_receipt_postures_digest": digest(measured_postures),
        "posture_values": {key: sorted({str(item["posture"][key]) for item in measured_postures
            if key in item["posture"]}) for key in posture_fields
            if key != "shared_host_cpu_gpu"},
    }
    compact_invocations = tuple({key: item.get(key) for key in
        ("receipt_id", "receipt_digest", "request_id", "request_digest", "status", "purpose",
         "model_id", "model_artifact_digest", "observed_at", "resource_allocation_digest",
         "resource_attempt_id", "resource_consumption_receipt_digests") if key in item}
        | {"local_model_inference": (item.get("local_model_inference")
            if type(item.get("local_model_inference")) is bool else
            item.get("effects", {}).get("local_model_inference")
                if isinstance(item.get("effects"), Mapping) else None)}
        for item in selected_invocations)
    invocation_bindings = {str(item.get("receipt_id")): item for item in compact_invocations
        if isinstance(item.get("receipt_id"), str)}
    legacy_generation_unavailable = (
        "verified_chat_process_generation_attributions" not in original
        and "chat_process_generation_posture" not in original)
    raw_generation_attributions = original.get("verified_chat_process_generation_attributions", ())
    source_generation_posture = original.get("chat_process_generation_posture")
    if legacy_generation_unavailable:
        source_generation_posture = "unknown_legacy_or_unavailable"
    generation_rows_bounded = (isinstance(raw_generation_attributions, (list, tuple))
        and len(raw_generation_attributions) <= 256)
    all_generation_attributions = (tuple(raw_generation_attributions)
        if generation_rows_bounded else ())
    selected_generation_receipt_ids = set(invocation_bindings)
    selected_generation_rows: list[Mapping[str, Any]] = []
    omitted_generation_rows: list[Mapping[str, Any]] = []
    generation_attributions_valid = (legacy_generation_unavailable or (
        generation_rows_bounded
        and source_generation_posture in {
            "verified", "partial_legacy_or_unavailable",
            "unknown_legacy_or_unavailable", "unknown_no_completed_invocations"}))
    if generation_attributions_valid:
        for attribution in all_generation_attributions:
            if not isinstance(attribution, Mapping):
                generation_attributions_valid = False
                break
            receipt_id = attribution.get("invocation_receipt_id")
            if not isinstance(receipt_id, str):
                generation_attributions_valid = False
                break
            if receipt_id not in selected_generation_receipt_ids:
                omitted_generation_rows.append(attribution)
            else:
                selected_generation_rows.append(attribution)
    generation_attributions: list[dict[str, Any]] = []
    if generation_attributions_valid:
        seen_generation_receipts: set[str] = set()
        for attribution in selected_generation_rows:
            if not isinstance(attribution, Mapping):
                generation_attributions_valid = False
                break
            receipt_id = attribution.get("invocation_receipt_id")
            invocation = invocation_bindings.get(str(receipt_id))
            handoff = attribution.get("chat_process_handoff")
            if (set(attribution) != {"invocation_receipt_id", "invocation_receipt_digest",
                    "invocation_request_id", "invocation_request_digest", "chat_process_handoff",
                    "attribution_posture", "currentness_posture"}
                    or not isinstance(receipt_id, str) or receipt_id in seen_generation_receipts
                    or not isinstance(invocation, Mapping)
                    or attribution.get("invocation_receipt_digest") != invocation.get("receipt_digest")
                    or attribution.get("invocation_request_id") != invocation.get("request_id")
                    or attribution.get("invocation_request_digest") != invocation.get("request_digest")
                    or attribution.get("attribution_posture")
                        != "invocation_receipt_and_historical_chat_handoff_verified"
                    or attribution.get("currentness_posture")
                        != "historical_process_identity_not_reobserved_during_recovery"
                    or not isinstance(handoff, Mapping)
                    or handoff.get("status") != "runtime_launcher_process_and_source_bound"
                    or any(not isinstance(handoff.get(key), str) or not handoff.get(key)
                        for key in ("software_generation_digest", "process_instance_id",
                            "handoff_id", "handoff_digest", "source_generation_scope"))):
                generation_attributions_valid = False
                break
            compact_handoff = {key: handoff[key] for key in (
                "status", "reason_code", "software_generation_digest", "process_instance_id",
                "handoff_id", "handoff_digest", "startup_timestamp", "source_generation_scope",
                "configured_serving_operation_id", "prior_snapshot_generation") if key in handoff}
            if len(json.dumps(compact_handoff, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False).encode("utf-8")) > 8192:
                generation_attributions_valid = False
                break
            generation_attributions.append({
                "invocation_receipt_id": receipt_id,
                "invocation_receipt_digest": attribution["invocation_receipt_digest"],
                "invocation_request_id": attribution["invocation_request_id"],
                "invocation_request_digest": attribution["invocation_request_digest"],
                "chat_process_handoff": compact_handoff,
                "attribution_posture": attribution["attribution_posture"],
                "currentness_posture": attribution["currentness_posture"],
            })
            seen_generation_receipts.add(receipt_id)
    if not generation_attributions_valid:
        generation_attributions = []
    elif source_generation_posture == "verified":
        selected_completed = {str(item.get("receipt_id")) for item in compact_invocations
            if item.get("status") == "admitted_completed"
            and item.get("local_model_inference") is True}
        selected_attributed = {str(item.get("invocation_receipt_id"))
            for item in generation_attributions}
        if selected_completed - selected_attributed:
            generation_attributions_valid = False
            generation_attributions = []
    generation_posture = (source_generation_posture if generation_attributions_valid
        else "invalid_or_unbound")
    generation_omitted_count = (len(omitted_generation_rows)
        if generation_rows_bounded else (len(raw_generation_attributions)
            if isinstance(raw_generation_attributions, (list, tuple)) else 0))
    generation_omitted_digest = None
    if generation_omitted_count:
        omitted_value = ([dict(item) for item in omitted_generation_rows]
            if generation_rows_bounded else list(raw_generation_attributions))
        generation_omitted_digest = digest(omitted_value)
    summary = {"ledger_schema": original.get("ledger_schema"),
        "ledger_digest": original.get("ledger_digest"),
        "source_identity": original.get("source_identity", {}),
        "allocations": compact_allocations, "allocation_count": len(allocations),
        "attempts": compact_attempts, "attempt_count": len(attempts),
        "consumption_receipts": compact_receipts, "consumption_receipt_count": len(receipts),
        "omitted_consumption_receipt_count": len(omitted_receipts),
        "measurement_posture_summary": measurement_posture_summary,
        "invocation_receipts": compact_invocations, "invocation_receipt_count": len(invocations),
        "chat_process_generation_posture": generation_posture,
        "chat_process_generation_attribution_count": len(all_generation_attributions),
        "chat_process_generation_attributions_omitted_count": generation_omitted_count,
        "chat_process_generation_attributions_omitted_digest": generation_omitted_digest,
        "verified_chat_process_generation_attributions": tuple(generation_attributions),
        "loaded_code_identity_posture": "not_independently_attested",
        "process_identity_scope": "installation_bound_launcher_handoff_process_identity",
        "event_time_posture": "receipt_event_time_retained_as_historical",
        "event_meaning": "governed resource consumption and historically bound chat process generation",
        "current_truth": False,
        "authority": False,
        "effect_proven": False,
        "attribution_posture": original.get("attribution_posture"),
        "shared_host_usage_attribution": original.get("shared_host_usage_attribution"),
        "lineage_posture": original.get("lineage_posture"),
        "lineage_findings": tuple(original.get("lineage_findings", ()))[:16],
        "lineage_finding_count": int(original.get("lineage_finding_count", len(original.get("lineage_findings", ())))),
        "recovery_posture": original.get("recovery_posture"),
        "incomplete_attempt_ids": tuple(original.get("incomplete_attempt_ids", ()))[:16],
        "incomplete_attempt_count": int(original.get("incomplete_attempt_count",
            len(original.get("incomplete_attempt_ids", ())))),
        "retention_posture": original.get("retention_posture"),
    }
    if not summary["lineage_findings"]:
        summary.pop("lineage_findings")
    if not summary["incomplete_attempt_ids"]:
        summary.pop("incomplete_attempt_ids")
    summary["interpretation_projection_posture"] = (
        "complete" if len(allocations) <= 4 and len(attempts) <= 8
            and len(receipts) <= 2 and len(selected_receipts) == len(receipts)
            and receipt_allocation_links_complete and receipt_attempt_links_complete
            and len(invocations) <= 4
            and generation_attributions_valid and not omitted_generation_rows
            and int(original.get("lineage_finding_count", len(original.get("lineage_findings", ())))) <= 16
            and int(original.get("incomplete_attempt_count", len(original.get("incomplete_attempt_ids", ())))) <= 16
        else "bounded_tail_incomplete")
    projection_binding={"schema_version":"sentientos.resource_interpretation_projection:v1",
        "source_fact_id":str(fact.get("fact_id", "")),
        "source_payload_digest":digest(dict(original)),
        "source_record_digest":str(source.get("digest", "")),
        "projected_payload_digest":digest(summary)}
    projection_binding["projection_digest"]=digest(projection_binding)
    summary["interpretation_projection"]=projection_binding
    projected = dict(fact)
    projected["payload"] = summary
    return projected


def _developmental_history_interpretation_projection(
    fact: Mapping[str, Any], original: Mapping[str, Any], source: Mapping[str, Any],
) -> dict[str, Any]:
    """Keep exact trial provenance while bounding a run for later interpretation.

    The full source payload remains bound by its digest. The projection carries
    only the three canonical conditions and their exact receipt, request,
    retrieved-history, event-time, and objective-score identities.
    """
    run_id = original.get("run_id")
    subject = fact.get("subject")
    if (not isinstance(run_id, str) or not run_id
            or source.get("source_id") != "developmental-history-run:" + run_id
            or not isinstance(subject, Mapping)
            or subject.get("subject_kind") != "developmental_history_intervention_experiment"
            or subject.get("subject_id") != run_id):
        raise DevelopmentalWritebackError("developmental_history_source_identity_invalid")
    conditions = original.get("conditions")
    if not isinstance(conditions, (list, tuple)) or len(conditions) != 3:
        raise DevelopmentalWritebackError("developmental_history_conditions_invalid")
    selected_conditions: list[dict[str, Any]] = []
    family_projection = original.get("objective_task_family") is not None
    if family_projection:
        descriptor = original.get("objective_task_descriptor")
        if (not isinstance(descriptor, Mapping)
                or descriptor.get("task_digest_posture")
                    != "salted_private_oracle_commitment:v1"):
            raise DevelopmentalWritebackError(
                "developmental_history_legacy_oracle_commitment_not_admissible")
    condition_fields: tuple[str, ...] = (
        "condition_id", "observation_id", "observation_digest", "output_digest",
        "request_id", "request_digest", "inference_receipt_id",
        "inference_receipt_digest", "serving_session_id", "observed_at",
    )
    if not family_projection:
        condition_fields += ("retrieved_record_ids", "retrieved_record_digests")
    for condition in conditions:
        if not isinstance(condition, Mapping):
            raise DevelopmentalWritebackError("developmental_history_condition_invalid")
        selected = {key: condition.get(key) for key in condition_fields}
        for key in ("retrieved_record_ids", "retrieved_record_digests"):
            if key not in selected:
                continue
            value = selected[key]
            if not isinstance(value, (list, tuple)) or len(value) > 64:
                raise DevelopmentalWritebackError("developmental_history_retrieval_lineage_invalid")
            selected[key] = list(value)
        selected_conditions.append(selected)
    scores = original.get("objective_scores")
    score_summary = None
    if scores is not None:
        if not isinstance(scores, (list, tuple)) or len(scores) != 3:
            raise DevelopmentalWritebackError("developmental_history_scores_invalid")
        score_summary = []
        for item in scores:
            if not isinstance(item, Mapping):
                raise DevelopmentalWritebackError("developmental_history_score_invalid")
            score_summary.append({
                "condition_id": item.get("condition_id"),
                **{key: item[key] for key in (
                    "schema_version", "plan_digest", "task_digest", "output_digest",
                    "evaluator") if key in item},
                "score_digest": item.get("score_digest"),
                "status": item.get("status"),
                "correct": item.get("correct"),
                **({"correct_count": item.get("correct_count"),
                    "probe_count": item.get("probe_count")}
                    if "correct_count" in item else {}),
            })
    summary = {
        "run_id": original.get("run_id"), "run_digest": original.get("run_digest"),
        "protocol_id": original.get("protocol_id"),
        "protocol_digest": original.get("protocol_digest"),
        "protocol_schema_version": original.get("protocol_schema_version"),
        "record_set_digest": original.get("record_set_digest"),
        "history_record_ids": original.get("history_record_ids"),
        "history_record_digests": original.get("history_record_digests"),
        "model_id": original.get("model_id"),
        "model_artifact_digest": original.get("model_artifact_digest"),
        "active_model_identity": original.get("active_model_identity"),
        "authority_map_digest": original.get("authority_map_digest"),
        "conditions": selected_conditions,
        "condition_event_times": original.get("condition_event_times"),
        "event_time_posture": original.get("event_time_posture"),
        "history_intervention_summary": (
            {key: original.get("history_intervention_summary", {}).get(key)
                for key in ("classification", "claims_posture")}
            if family_projection and isinstance(original.get("history_intervention_summary"), Mapping)
            else original.get("history_intervention_summary")),
        "objective_scores": score_summary,
        "objective_evaluation": original.get("objective_evaluation"),
        "claims_posture": original.get("claims_posture"),
        "current_truth": False, "authority": False,
        "learning_established": False, "reconstruction_time_is_event_time": False,
    }
    # Retain the experiment owner's bounded invocation-receipt posture beside
    # the scored examples. This preserves whether an example came from a
    # simulation, a receipt-reported backend entry, or an unresolved receipt;
    # it never upgrades the owner's receipt into an independent backend
    # observation. Historical runs without these fields remain readable with
    # their execution posture explicitly unavailable downstream.
    execution_keys = {
        "execution_evidence_conditions", "execution_evidence_posture",
        "execution_evidence_scope", "independent_backend_observation",
    }
    execution_present = execution_keys.intersection(original)
    if execution_present:
        execution_conditions = original.get("execution_evidence_conditions")
        expected_conditions = ("history_present", "history_withheld", "history_restored")
        allowed_postures = {
            "receipt_reports_simulation_or_no_backend_entry",
            "verified_owner_receipt_reports_backend_entry",
            "receipt_does_not_establish_backend_entry",
            "receipt_unbound_or_identity_mismatch",
        }
        if (execution_present != execution_keys
                or original.get("execution_evidence_scope") != (
                    "authenticated_owner_receipt_not_independent_backend_observation")
                or original.get("independent_backend_observation") is not False
                or not isinstance(execution_conditions, (list, tuple))
                or len(execution_conditions) != len(expected_conditions)):
            raise DevelopmentalWritebackError(
                "developmental_history_execution_evidence_shape_invalid")
        execution_summary: list[dict[str, Any]] = []
        for expected_condition, item in zip(expected_conditions, execution_conditions):
            receipt_condition = next((row for row in selected_conditions
                if row.get("condition_id") == expected_condition), None)
            if (not isinstance(item, Mapping)
                    or item.get("condition_id") != expected_condition
                    or type(item.get("receipt_identity_verified")) is not bool
                    or item.get("posture") not in allowed_postures
                    or not isinstance(receipt_condition, Mapping)
                    or item.get("invocation_receipt_id")
                        != receipt_condition.get("inference_receipt_id")
                    or item.get("invocation_receipt_digest")
                        != receipt_condition.get("inference_receipt_digest")
                    or not isinstance(receipt_condition.get("inference_receipt_id"), str)
                    or not receipt_condition.get("inference_receipt_id")
                    or not isinstance(receipt_condition.get("inference_receipt_digest"), str)
                    or len(receipt_condition["inference_receipt_digest"]) not in {64, 71}
                    or (len(receipt_condition["inference_receipt_digest"]) == 71
                        and not receipt_condition["inference_receipt_digest"].startswith("sha256:"))
                    or any(character not in "0123456789abcdef"
                        for character in (receipt_condition["inference_receipt_digest"][7:]
                            if len(receipt_condition["inference_receipt_digest"]) == 71
                            else receipt_condition["inference_receipt_digest"]))
                    or (item.get("receipt_identity_verified") is True
                        and not isinstance(item.get("receipt_status"), str))
                    or (item.get("receipt_identity_verified") is False
                        and (item.get("posture") != "receipt_unbound_or_identity_mismatch"
                            or item.get("receipt_status") is not None
                            or item.get("local_model_inference_effect") is not None
                            or item.get("fallback_occurred") is not None))
                    or (item.get("receipt_identity_verified") is True
                        and item.get("posture") == "receipt_unbound_or_identity_mismatch")
                    or (item.get("local_model_inference_effect") is not None
                        and type(item.get("local_model_inference_effect")) is not bool)
                    or (item.get("fallback_occurred") is not None
                        and type(item.get("fallback_occurred")) is not bool)
                    or item.get("independent_backend_observation") is not False):
                    raise DevelopmentalWritebackError(
                        "developmental_history_execution_condition_invalid")
            if item["receipt_identity_verified"] is True:
                execution_summary.append({key: item.get(key) for key in (
                    "condition_id", "receipt_identity_verified", "receipt_status",
                    "local_model_inference_effect", "fallback_occurred", "posture",
                    "independent_backend_observation")}
                    | {"invocation_receipt_id": receipt_condition["inference_receipt_id"],
                        "invocation_receipt_digest": receipt_condition[
                            "inference_receipt_digest"]})
            else:
                # Keep the recorded invocation identity and explicit unverified
                # posture, but omit three unavailable null metadata fields.
                execution_summary.append({"condition_id": expected_condition,
                    "receipt_identity_verified": False,
                    "posture": "receipt_unbound_or_identity_mismatch",
                    "invocation_receipt_id": receipt_condition["inference_receipt_id"],
                    "invocation_receipt_digest": receipt_condition[
                        "inference_receipt_digest"]})
        expected_execution_posture = (
            "incomplete_or_unverified_condition_receipts"
            if any(item["receipt_identity_verified"] is not True
                for item in execution_summary)
            else
            "all_owner_receipts_report_backend_entry"
            if all(item["posture"] == "verified_owner_receipt_reports_backend_entry"
                for item in execution_summary)
            else "one_or_more_conditions_simulated_or_no_backend_entry"
            if any(item["posture"] == "receipt_reports_simulation_or_no_backend_entry"
                for item in execution_summary)
            else "one_or_more_receipts_do_not_establish_backend_entry")
        if original.get("execution_evidence_posture") != expected_execution_posture:
            raise DevelopmentalWritebackError(
                "developmental_history_execution_posture_invalid")
        summary.update({
            "execution_evidence_conditions": execution_summary,
            "execution_evidence_posture": expected_execution_posture,
            "execution_evidence_scope": (
                "authenticated_owner_receipt_not_independent_backend_observation"),
            "independent_backend_observation": False,
        })
    if (original.get("objective_task_commitment_posture")
            == "salted_private_oracle_commitment:v1"):
        summary["objective_task_commitment_posture"] = (
            "salted_private_oracle_commitment:v1")
    family_id = original.get("objective_task_family")
    if family_id is not None:
        descriptor = original.get("objective_task_descriptor")
        summary["objective_task_commitment_posture"] = (
            "salted_private_oracle_commitment:v1")
        score_rows = original.get("objective_scores")
        history_score = (next((row for row in score_rows if isinstance(row, Mapping)
            and row.get("condition_id") == "history_present"), None)
            if isinstance(score_rows, (list, tuple)) else None)
        history_condition = next((row for row in conditions if isinstance(row, Mapping)
            and row.get("condition_id") == "history_present"), None)
        probe_results = history_score.get("probe_results") if isinstance(history_score, Mapping) else None
        probes = descriptor.get("probe_inputs") if isinstance(descriptor, Mapping) else None
        if (not isinstance(family_id, str) or not family_id or len(family_id) > 96
                or not isinstance(descriptor, Mapping)
                or descriptor.get("task_family_id") != family_id
                or original.get("task_family_posture") != "operator_declared_protocol_bound"
                or not isinstance(original.get("acquisition_examples"), list)
                or len(original["acquisition_examples"]) > 16
                or not isinstance(probes, (list, tuple)) or len(probes) != len(original["acquisition_examples"])
                or not isinstance(probe_results, (list, tuple)) or len(probe_results) != len(probes)
                or not isinstance(history_score.get("score_digest"), str)):
            raise DevelopmentalWritebackError("developmental_history_task_family_binding_invalid")
        expected_examples: list[dict[str, Any]] = []
        lineage_fields = ("schema_version", "plan_digest", "task_digest", "output_digest",
            "evaluator")
        lineage_present = (isinstance(history_score, Mapping)
            and all(key in history_score for key in lineage_fields))
        if lineage_present:
            if (any(not isinstance(history_score.get(key), str)
                    or not history_score.get(key) or len(history_score[key]) > 128
                    for key in lineage_fields)
                    or history_score.get("schema_version") != "sentientos.objective_task_score:v3"
                    or history_score.get("evaluator") !=
                        "deterministic_exact_integer_suite_oracle_v2"
                    or history_score.get("task_digest") != descriptor.get("task_digest")
                    or history_score.get("output_digest") != history_condition.get("output_digest")
                    or any(not isinstance(history_score.get(key), str)
                        or len(history_score[key]) != 71
                        or not history_score[key].startswith("sha256:")
                        or any(character not in "0123456789abcdef"
                            for character in history_score[key][7:])
                        for key in ("plan_digest", "task_digest", "score_digest"))
                    or not isinstance(history_score.get("output_digest"), str)
                    or len(history_score["output_digest"]) not in {64, 71}
                    or (len(history_score["output_digest"]) == 71
                        and not history_score["output_digest"].startswith("sha256:"))
                    or any(character not in "0123456789abcdef"
                        for character in history_score["output_digest"]
                            .removeprefix("sha256:"))):
                raise DevelopmentalWritebackError(
                    "developmental_history_task_score_lineage_invalid")
        elif any(any(key in example for key in (
                "source_score_schema_version", "source_plan_digest", "source_task_digest",
                "source_output_digest", "source_evaluator"))
                for example in original["acquisition_examples"]):
            raise DevelopmentalWritebackError(
                "developmental_history_task_score_lineage_incomplete")
        for probe, result in zip(probes, probe_results):
            if (type(probe) is not int or not isinstance(result, Mapping)
                    or result.get("probe_input") != probe
                    or type(result.get("observed_answer")) is not int
                    or type(result.get("correct")) is not bool):
                raise DevelopmentalWritebackError("developmental_history_task_example_invalid")
            expected_examples.append({"probe_input": probe,
                "observed_answer": result["observed_answer"],
                "evaluator_correct": result["correct"],
                "source_score_digest": history_score["score_digest"],
                "source_condition": "history_present"})
        examples = original["acquisition_examples"]
        if examples != expected_examples:
            raise DevelopmentalWritebackError("developmental_history_task_example_binding_invalid")
        summary.update({"objective_task_family": family_id,
            "objective_task_descriptor": dict(descriptor),
            "acquisition_examples": [dict(example) for example in examples],
            "task_family_posture": "operator_declared_protocol_bound"})
    if len(json.dumps(summary, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False).encode("utf-8")) > MAX_DEVELOPMENTAL_EXPERIMENT_SELECTED_EVIDENCE_BYTES:
        raise DevelopmentalWritebackError("developmental_history_projection_over_bound")
    binding = {
        "schema_version": "sentientos.developmental_history_interpretation_projection:v1",
        "source_fact_id": str(fact.get("fact_id", "")),
        "source_payload_digest": digest(dict(original)),
        "source_record_digest": str(source.get("digest", "")),
        "projected_payload_digest": digest(summary),
    }
    binding["projection_digest"] = digest(binding)
    projected = dict(fact)
    projected["payload"] = {**summary, "interpretation_projection": binding}
    return projected


@dataclass(frozen=True)
class SelectedEvidence:
    snapshot_id: str
    snapshot_digest: str
    facts: tuple[Mapping[str, Any], ...]
    sources: tuple[Mapping[str, Any], ...]
    conflicts: tuple[Mapping[str, Any], ...]
    selection_id: str = ""
    selection_digest: str = ""

    def semantic_payload(self) -> dict[str, Any]:
        return {"snapshot_id": self.snapshot_id, "snapshot_digest": self.snapshot_digest,
                "facts": [dict(x) for x in self.facts], "sources": [dict(x) for x in self.sources],
                "conflicts": [dict(x) for x in self.conflicts]}


@dataclass(frozen=True)
class DevelopmentalCandidate:
    interpretation: str
    uncertainty: str
    epistemic_status: str
    snapshot_id: str
    snapshot_digest: str
    selection_id: str
    selection_digest: str
    selected_fact_ids: tuple[str, ...]
    selected_sources: tuple[Mapping[str, Any], ...]
    model_id: str
    model_artifact_digest: str | None
    request_id: str
    request_digest: str
    inference_receipt_id: str
    inference_receipt_digest: str
    output_digest: str
    transformation_provenance: Mapping[str, Any]
    selected_facts: tuple[Mapping[str, Any], ...] = ()
    candidate_id: str = ""
    candidate_digest: str = ""

    def semantic_payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("candidate_id"); value.pop("candidate_digest")
        # Historical candidates predate payload retention. Preserve their
        # content identities while new records carry exact selected evidence.
        if not self.selected_facts:
            value.pop("selected_facts", None)
        return value


@dataclass(frozen=True)
class DevelopmentalRecord:
    record_id: str
    record_digest: str
    candidate: Mapping[str, Any]
    admission_id: str
    admission_binding_digest: str
    principal: str
    operation_id: str
    correlation_id: str
    created_at: str
    epistemic_posture: str = "historical_interpretation_not_current_truth"
    current_truth: bool = False
    authority: bool = False
    policy: bool = False
    canonical_explicit_user_retention: bool = False
    schema_version: str = SCHEMA_VERSION

    def semantic_payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("record_id"); value.pop("record_digest")
        return value


@dataclass(frozen=True)
class WritebackReceipt:
    receipt_id: str
    receipt_digest: str
    record_id: str
    record_digest: str
    candidate_id: str
    candidate_digest: str
    admission_id: str
    admission_binding_digest: str
    principal: str
    operation_id: str
    storage_verified: bool
    grants_authority: bool = False
    schema_version: str = SCHEMA_VERSION

    def semantic_payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("receipt_id"); value.pop("receipt_digest")
        return value


@dataclass(frozen=True)
class DevelopmentalHistoryProjection:
    records: tuple[Mapping[str, Any], ...]
    requested_record_ids: tuple[str, ...]
    read_only: bool = True
    epistemic_posture: str = "historical_interpretation_not_current_truth"
    current_truth: bool = False
    authority: bool = False
    policy: bool = False
    canonical_explicit_user_retention: bool = False


@dataclass(frozen=True)
class CognitionObservation:
    condition_id: str
    downstream_cognition_id: str
    downstream_cognition_digest: str
    retrieved_record_ids: tuple[str, ...]


@dataclass(frozen=True)
class ChangedCognitionMeasurement:
    measurement_id: str
    measurement_digest: str
    with_record_condition: Mapping[str, Any]
    without_record_condition: Mapping[str, Any]
    compared_fields: tuple[str, ...]
    observable_difference: bool
    interpretation: str = "difference_only_not_improvement_learning_or_correctness"


def _map_custody_error(exc: PrivateFileCustodyError) -> DevelopmentalWritebackError:
    codes = {
        "directory_root_missing": "durable_store_root_missing",
        "directory_root_invalid": "durable_store_root_invalid",
        "directory_root_unavailable": "durable_store_root_unavailable",
        "directory_permissions_invalid": "durable_store_root_permissions_invalid",
        "directory_path_permissions_invalid": "durable_store_path_permissions_invalid",
        "directory_custody_unsupported": "durable_store_directory_custody_unsupported",
        "file_missing": "stored_payload_missing",
        "file_path_invalid": "stored_payload_path_invalid",
        "file_unbounded_or_not_private": "stored_payload_unbounded_or_not_regular",
        "file_changed_during_read": "stored_payload_changed_during_read",
        "file_unavailable": "stored_payload_unavailable",
        "payload_size_limit_exceeded": "durable_payload_size_limit_exceeded",
        "publication_short_write": "durable_publication_short_write",
        "publication_unavailable": "durable_publication_unavailable",
    }
    return DevelopmentalWritebackError(codes.get(exc.code, exc.code))


def _open_store_directory(path: Path, *, create: bool) -> int:
    try:
        return open_private_directory(path, create=create)
    except PrivateFileCustodyError as exc:
        raise _map_custody_error(exc) from exc


def _read_store_file(directory_fd: int, name: str, *,
                     max_bytes: int = MAX_DURABLE_RECORD_BYTES) -> bytes:
    try:
        return read_private_file_at(directory_fd, name, max_bytes=max_bytes)
    except PrivateFileCustodyError as exc:
        raise _map_custody_error(exc) from exc


def _publish_store_json(path: Path, payload: Mapping[str, Any], *, collision_error: str,
                        max_bytes: int = MAX_DURABLE_RECORD_BYTES) -> None:
    """Publish canonical immutable JSON through shared descriptor custody."""
    data = json.dumps(payload, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    try:
        publish_immutable_bytes(path, data, max_bytes=max_bytes, collision_code=collision_error)
    except PrivateFileCustodyError as exc:
        if exc.code == collision_error:
            raise DevelopmentalWritebackError(collision_error) from exc
        raise _map_custody_error(exc) from exc


def _read_store_collection(path: Path, *, kind: str) -> tuple[tuple[str, bytes], ...]:
    """Read one bounded immutable collection from a pinned directory handle."""
    try:
        before = path.lstat()
    except FileNotFoundError:
        return ()
    except OSError as exc:
        raise DevelopmentalWritebackError(f"durable_{kind}_root_unavailable") from exc
    if not stat.S_ISDIR(before.st_mode):
        raise DevelopmentalWritebackError(f"durable_{kind}_root_invalid")
    if os.name == "nt":
        try:
            return tuple(read_regular_files(path, max_entries=MAX_DURABLE_RECORDS,
                max_file_bytes=MAX_DURABLE_RECORD_BYTES,
                max_total_bytes=MAX_DURABLE_RECORD_ROOT_BYTES))
        except WindowsHandleCustodyError as exc:
            raise DevelopmentalWritebackError(f"durable_{kind}_windows_recovery_failed") from exc

    directory_fd: int | None = None
    try:
        directory_fd = _open_store_directory(path, create=False)
        opened = os.fstat(directory_fd)
        if (not stat.S_ISDIR(opened.st_mode) or opened.st_dev != before.st_dev
                or opened.st_ino != before.st_ino):
            raise DevelopmentalWritebackError(f"durable_{kind}_collection_changed_during_read")
        try:
            names = list_bounded_json_names_at(
                directory_fd, max_entries=MAX_DURABLE_RECORDS,
                max_directory_entries=MAX_DURABLE_RECORDS + 1024)
        except PrivateFileCustodyError as exc:
            if exc.code in {"directory_entry_limit_exceeded", "directory_file_count_limit_exceeded"}:
                raise DevelopmentalWritebackError(f"durable_{kind}_limit_exceeded") from exc
            raise DevelopmentalWritebackError(f"durable_{kind}_root_unavailable") from exc
        entries: list[tuple[str, bytes]] = []
        total = 0
        for name in names:
            try:
                data = _read_store_file(directory_fd, name)
            except DevelopmentalWritebackError as exc:
                if str(exc) == "stored_payload_missing":
                    raise DevelopmentalWritebackError(
                        f"durable_{kind}_collection_changed_during_read") from exc
                raise
            total += len(data)
            if total > MAX_DURABLE_RECORD_ROOT_BYTES:
                raise DevelopmentalWritebackError(f"durable_{kind}_root_size_limit_exceeded")
            entries.append((name, data))
        after = os.fstat(directory_fd)
        if (after.st_dev != opened.st_dev or after.st_ino != opened.st_ino
                or after.st_mtime_ns != opened.st_mtime_ns
                or after.st_ctime_ns != opened.st_ctime_ns):
            raise DevelopmentalWritebackError(f"durable_{kind}_collection_changed_during_read")
        return tuple(entries)
    except DevelopmentalWritebackError:
        raise
    except (OSError, PrivateFileCustodyError) as exc:
        raise DevelopmentalWritebackError(f"durable_{kind}_root_unavailable") from exc
    finally:
        if directory_fd is not None:
            os.close(directory_fd)


class DevelopmentalHistoryStore:
    """Content-addressed immutable store, physically separate from canonical memory."""
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.records_root = self.root / "records"
        self.receipts_root = self.root / "receipts"
        try:
            memory_root = Path(sentientos_memory_dir()).expanduser().resolve(strict=False)
            storage_roots = (
                self.records_root.expanduser().resolve(strict=False),
                self.receipts_root.expanduser().resolve(strict=False),
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise DevelopmentalWritebackError("canonical_memory_root_identity_invalid") from exc
        if any(path == memory_root or path in memory_root.parents or memory_root in path.parents
               for path in storage_roots):
            raise DevelopmentalWritebackError("durable_store_root_overlaps_canonical_memory")

    def append(self, record: DevelopmentalRecord) -> DevelopmentalRecord:
        self._verify_record(record)
        path = self.records_root / f"{record.record_id}.json"
        payload = asdict(record)
        try:
            existing = self._read_json(path)
        except DevelopmentalWritebackError as exc:
            if str(exc) != "stored_payload_missing":
                raise
            existing = None
        if existing is not None:
            if digest_payload(existing) != digest_payload(payload):
                raise DevelopmentalWritebackError("record_identity_collision")
            return record
        if os.name != "posix":
            raise DevelopmentalWritebackError("durable_record_publication_unsupported_platform")
        _publish_store_json(path, payload, collision_error="record_identity_collision")
        if self.get(record.record_id).record_digest != record.record_digest:
            raise DevelopmentalWritebackError("durable_record_verification_failed")
        return record

    def get(self, record_id: str) -> DevelopmentalRecord:
        if not _valid_store_identity(record_id, "devrec"):
            raise DevelopmentalWritebackError("record_identity_invalid")
        path = self.records_root / f"{record_id}.json"
        try: record = DevelopmentalRecord(**self._read_json(path))
        except (OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise DevelopmentalWritebackError("record_missing_or_corrupt") from exc
        self._verify_record(record)
        return record

    def write_receipt(self, receipt: WritebackReceipt) -> WritebackReceipt:
        self._verify_receipt(receipt)
        if self.get(receipt.record_id).record_digest != receipt.record_digest:
            raise DevelopmentalWritebackError("receipt_record_not_durable")
        path = self.receipts_root / f"{receipt.receipt_id}.json"
        payload = asdict(receipt)
        try:
            existing = self._read_json(path)
        except DevelopmentalWritebackError as exc:
            if str(exc) != "stored_payload_missing":
                raise
            existing = None
        if existing is not None and digest_payload(existing) != digest_payload(payload):
            raise DevelopmentalWritebackError("receipt_identity_collision")
        if existing is None:
            if os.name != "posix":
                raise DevelopmentalWritebackError("durable_receipt_publication_unsupported_platform")
            _publish_store_json(path, payload, collision_error="receipt_identity_collision")
        if self.get_receipt(receipt.receipt_id).receipt_digest != receipt.receipt_digest:
            raise DevelopmentalWritebackError("durable_receipt_verification_failed")
        return receipt

    def get_receipt(self, receipt_id: str) -> WritebackReceipt:
        if not _valid_store_identity(receipt_id, "devreceipt"):
            raise DevelopmentalWritebackError("receipt_identity_invalid")
        try: receipt = WritebackReceipt(**self._read_json(self.receipts_root / f"{receipt_id}.json"))
        except (OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise DevelopmentalWritebackError("receipt_missing_or_corrupt") from exc
        self._verify_receipt(receipt); return receipt

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        if os.name == "nt":
            try:
                entries = read_regular_files(path.parent, max_entries=1,
                    max_file_bytes=MAX_DURABLE_RECORD_BYTES, max_total_bytes=MAX_DURABLE_RECORD_BYTES,
                    selected_names=(path.name,))
            except WindowsHandleCustodyError as exc:
                if str(exc) == "explicit_file_missing":
                    raise DevelopmentalWritebackError("stored_payload_missing") from exc
                raise DevelopmentalWritebackError("stored_payload_windows_recovery_failed") from exc
            if len(entries) != 1 or entries[0][0] != path.name:
                raise DevelopmentalWritebackError("stored_payload_missing")
            data = entries[0][1]
        else:
            try:
                directory_fd = _open_store_directory(path.parent, create=False)
            except DevelopmentalWritebackError as exc:
                if str(exc) == "durable_store_root_missing":
                    raise DevelopmentalWritebackError("stored_payload_missing") from exc
                raise
            try:
                data = _read_store_file(directory_fd, path.name)
            finally:
                os.close(directory_fd)
        value = json.loads(data.decode("utf-8"))
        if not isinstance(value, dict): raise DevelopmentalWritebackError("stored_payload_not_object")
        if json.dumps(value, sort_keys=True, indent=2).encode("utf-8") + b"\n" != data:
            raise DevelopmentalWritebackError("stored_payload_noncanonical")
        return value

    def records(self) -> tuple[DevelopmentalRecord, ...]:
        entries = _read_store_collection(self.records_root, kind="record")
        recovered: list[DevelopmentalRecord] = []
        for name, data in entries:
            try:
                payload = json.loads(data.decode("utf-8"))
                if (not isinstance(payload, dict)
                        or json.dumps(payload, sort_keys=True, indent=2).encode("utf-8") + b"\n" != data):
                    raise DevelopmentalWritebackError("stored_payload_noncanonical")
                record = DevelopmentalRecord(**payload)
            except (UnicodeError, json.JSONDecodeError, TypeError) as exc:
                raise DevelopmentalWritebackError("record_missing_or_corrupt") from exc
            self._verify_record(record)
            if name != record.record_id + ".json":
                raise DevelopmentalWritebackError("durable_record_path_identity_mismatch")
            recovered.append(record)
        return tuple(recovered)

    def receipts(self) -> tuple[WritebackReceipt, ...]:
        """Recover the bounded receipt collection without creating or repairing custody."""
        entries = _read_store_collection(self.receipts_root, kind="receipt")
        recovered: list[WritebackReceipt] = []
        for name, data in entries:
            try:
                payload = json.loads(data.decode("utf-8"))
                if (not isinstance(payload, dict)
                        or json.dumps(payload, sort_keys=True, indent=2).encode("utf-8") + b"\n" != data):
                    raise DevelopmentalWritebackError("stored_payload_noncanonical")
                receipt = WritebackReceipt(**payload)
            except (UnicodeError, json.JSONDecodeError, TypeError) as exc:
                raise DevelopmentalWritebackError("receipt_missing_or_corrupt") from exc
            self._verify_receipt(receipt)
            if name != receipt.receipt_id + ".json":
                raise DevelopmentalWritebackError("durable_receipt_path_identity_mismatch")
            recovered.append(receipt)
        return tuple(recovered)

    @staticmethod
    def _verify_record(record: DevelopmentalRecord) -> None:
        rid, digest = _identity("devrec", record.semantic_payload())
        if (record.record_id, record.record_digest) != (rid, digest):
            raise DevelopmentalWritebackError("record_digest_mismatch")
        if record.current_truth or record.authority or record.policy or record.canonical_explicit_user_retention:
            raise DevelopmentalWritebackError("historical_posture_violation")

    @staticmethod
    def _verify_receipt(receipt: WritebackReceipt) -> None:
        rid, digest = _identity("devreceipt", receipt.semantic_payload())
        if (receipt.receipt_id, receipt.receipt_digest) != (rid, digest) or not receipt.storage_verified or receipt.grants_authority:
            raise DevelopmentalWritebackError("receipt_digest_or_posture_mismatch")


class ResidentDevelopmentalWritebackController:
    def __init__(self, *, history_root: Path, admission_verifier: RuntimeAdmissionVerifier,
                 current_sequence: Callable[[], int]) -> None:
        self.store = DevelopmentalHistoryStore(history_root)
        self.admission_verifier = admission_verifier
        self.current_sequence = current_sequence

    def select_evidence(self, snapshot: WorldStateSnapshot, *, fact_ids: Sequence[str]) -> SelectedEvidence:
        validation = validate_snapshot(snapshot)
        if not validation.valid: raise DevelopmentalWritebackError("invalid_world_state_snapshot:" + ",".join(validation.findings))
        requested = tuple(fact_ids)
        if not requested or len(requested) > MAX_SELECTED_FACTS or len(set(requested)) != len(requested):
            raise DevelopmentalWritebackError("selected_fact_bounds_invalid")
        facts_by_id = {fact.fact_id: fact for fact in snapshot.facts}
        if any(fid not in facts_by_id for fid in requested): raise DevelopmentalWritebackError("selected_fact_not_in_snapshot")
        facts = tuple(_resource_interpretation_projection(to_dict(facts_by_id[fid]))
                      for fid in sorted(requested))
        source_ids = {str(fact["source"]["source_id"]) for fact in facts}
        sources_by_id = {source.source_id: source for source in snapshot.sources}
        if any(sid not in sources_by_id for sid in source_ids): raise DevelopmentalWritebackError("selected_source_not_in_snapshot")
        sources = tuple(to_dict(sources_by_id[sid]) for sid in sorted(source_ids))
        for fact in facts:
            source = sources_by_id[str(fact["source"]["source_id"])]
            if fact["source"] != to_dict(source): raise DevelopmentalWritebackError("selected_source_provenance_mismatch")
        conflicts = tuple(to_dict(c) for c in snapshot.conflicts if set(c.fact_ids) & set(requested))
        raw = SelectedEvidence(snapshot.snapshot_id, snapshot.digest, facts, sources, conflicts)
        encoded_size = len(json.dumps(raw.semantic_payload(), sort_keys=True,
            separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        if encoded_size > _selected_fact_byte_limit(facts):
            raise DevelopmentalWritebackError("selected_evidence_unbounded")
        sid, digest = _identity("devsel", raw.semantic_payload())
        return replace(raw, selection_id=sid, selection_digest=digest)

    @staticmethod
    def empty_selection(*, snapshot_id: str, snapshot_digest: str) -> SelectedEvidence:
        """Bind an empty current-evidence set for a history-only cognition candidate."""
        raw = SelectedEvidence(snapshot_id, snapshot_digest, (), (), ())
        sid, digest = _identity("devsel", raw.semantic_payload())
        return replace(raw, selection_id=sid, selection_digest=digest)

    @staticmethod
    def candidate_from_history_conditioned_cognition(
        selection: SelectedEvidence, receipt: LocalModelInvocationReceipt, *,
        observation: Mapping[str, Any], source_output_text: str,
        lesson_payload: Mapping[str, Any],
    ) -> DevelopmentalCandidate:
        """Bind one exact lesson emitted by the ordinary completed cognition call."""
        sid, sdigest = _identity("devsel", selection.semantic_payload())
        if (selection.selection_id, selection.selection_digest) != (sid, sdigest):
            raise DevelopmentalWritebackError("cognition_selection_identity_invalid")
        if (receipt.status != "admitted_completed" or receipt.output_truncated
                or receipt.fallback_occurred or receipt.output_text != source_output_text
                or not isinstance(receipt.output_digest, str)
                or digest_payload({"output": source_output_text}) != receipt.output_digest
                or receipt.output_size_bytes != len(source_output_text.encode("utf-8"))
                or receipt.effects.get("local_model_inference") is not True):
            raise DevelopmentalWritebackError("cognition_source_output_unverified")
        if (not isinstance(observation, Mapping)
                or observation.get("condition_id") != "with-history"
                or observation.get("developmental_projection_present") is not True
                or observation.get("output_digest") != receipt.output_digest
                or observation.get("inference_receipt_id") != receipt.receipt_id
                or observation.get("inference_receipt_digest") != receipt.receipt_digest
                or observation.get("request_id") != receipt.request.get("request_id")
                or observation.get("request_digest") != receipt.request.get("request_digest")
                or observation.get("current_snapshot_id") != selection.snapshot_id
                or observation.get("current_snapshot_digest") != selection.snapshot_digest
                or tuple(observation.get("current_fact_ids", ()))
                    != tuple(str(fact.get("fact_id", "")) for fact in selection.facts)):
            raise DevelopmentalWritebackError("cognition_observation_binding_invalid")
        try:
            output = json.loads(source_output_text)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise DevelopmentalWritebackError("cognition_source_output_invalid") from exc
        if (not isinstance(output, dict)
                or output != dict(lesson_payload)
                or set(output) != {"conclusion", "lesson_candidate"}
                or not isinstance(output.get("conclusion"), str)
                or not isinstance(output.get("lesson_candidate"), Mapping)):
            raise DevelopmentalWritebackError("cognition_lesson_output_invalid")
        lesson = dict(output["lesson_candidate"])
        expected_lesson_fields = {"statement", "scope", "applicability", "uncertainty",
            "uncertainty_rationale", "evidence_dependencies", "possible_contradiction_ids"}
        if set(lesson) != expected_lesson_fields:
            raise DevelopmentalWritebackError("cognition_lesson_output_invalid")
        dependencies = lesson.get("evidence_dependencies")
        contradictions = lesson.get("possible_contradiction_ids")
        consumed_ids = (set(str(value) for value in observation.get("retrieved_record_ids", ()))
            | set(str(value) for value in observation.get("current_fact_ids", ()))
            | set(str(value) for value in observation.get("self_model_claim_ids", ()))
            | set(str(value) for value in observation.get("epistemic_consumed_packet_ids", ())))
        if (not isinstance(dependencies, list) or not dependencies or len(dependencies) > 8
                or any(not isinstance(value, str) or not value for value in dependencies)
                or len(set(dependencies)) != len(dependencies)
                or not set(dependencies).issubset(consumed_ids)
                or not isinstance(contradictions, list) or len(contradictions) > 8
                or any(not isinstance(value, str) or not value for value in contradictions)
                or len(set(contradictions)) != len(contradictions)
                or not set(contradictions).issubset(consumed_ids)):
            raise DevelopmentalWritebackError("cognition_lesson_evidence_binding_invalid")
        request = receipt.request
        upstream = request.get("upstream_evidence") if isinstance(request, Mapping) else None
        if (not isinstance(request, Mapping)
                or request.get("expected_output_format") != "json"
                or request.get("structured_output_schema") != RESIDENT_COGNITION_LESSON_OUTPUT_SCHEMA):
            raise DevelopmentalWritebackError("cognition_request_output_contract_mismatch")
        exact_bindings = {
            "snapshot_id": observation.get("current_snapshot_id"),
            "snapshot_digest": observation.get("current_snapshot_digest"),
            "current_projection_id": observation.get("current_projection_id"),
            "current_projection_digest": observation.get("current_projection_digest"),
            "current_fact_ids": list(observation.get("current_fact_ids", ())),
            "record_ids": list(observation.get("retrieved_record_ids", ())),
            "record_digests": list(observation.get("retrieved_record_digests", ())),
            "self_model_projection_present": observation.get("self_model_projection_present"),
            "self_model_projection_id": observation.get("self_model_projection_id"),
            "self_model_projection_digest": observation.get("self_model_projection_digest"),
            "self_model_reconciliation_id": observation.get("self_model_reconciliation_id"),
            "self_model_reconciliation_digest": observation.get("self_model_reconciliation_digest"),
            "self_model_reconciliation_generation": observation.get("self_model_reconciliation_generation"),
            "self_model_source_tick": observation.get("self_model_source_tick"),
            "self_model_claim_ids": list(observation.get("self_model_claim_ids", ())),
            "self_model_claim_digests": list(observation.get("self_model_claim_digests", ())),
            "epistemic_projection_id": observation.get("epistemic_projection_id"),
            "epistemic_projection_digest": observation.get("epistemic_projection_digest"),
            "epistemic_proposition_ids": list(observation.get("epistemic_proposition_ids", ())),
            "epistemic_state_ids": list(observation.get("epistemic_state_ids", ())),
            "epistemic_state_digests": list(observation.get("epistemic_state_digests", ())),
            "epistemic_generations": list(observation.get("epistemic_generations", ())),
            "epistemic_evidence_set_digests": list(observation.get("epistemic_evidence_set_digests", ())),
            "epistemic_projection_schema": observation.get("epistemic_projection_schema"),
            "epistemic_semantic_status": observation.get("epistemic_semantic_status"),
            "epistemic_owner_packet_count": observation.get("epistemic_owner_packet_count"),
            "epistemic_consumed_packet_ids": list(observation.get("epistemic_consumed_packet_ids", ())),
            "epistemic_consumed_packet_digests": list(observation.get("epistemic_consumed_packet_digests", ())),
            "epistemic_omitted_packets": list(observation.get("epistemic_omitted_packets", ())),
            "epistemic_omitted_packets_digest": observation.get("epistemic_omitted_packets_digest"),
            "epistemic_consumed_packets_digest": observation.get("epistemic_consumed_packets_digest"),
            "epistemic_projection_context_digest": observation.get("epistemic_projection_context_digest"),
            "epistemic_prompt_digest": observation.get("epistemic_prompt_digest"),
            "epistemic_consumed_content_digest": observation.get("epistemic_consumed_content_digest"),
            "developmental_history_selection": observation.get("developmental_history_selection"),
        }
        if (not isinstance(upstream, Mapping)
                or any(upstream.get(key) != value for key, value in exact_bindings.items())
                or request.get("purpose") != "resident_developmental_retrieval_cognition"):
            raise DevelopmentalWritebackError("cognition_request_lineage_mismatch")
        context_fields = (
            "tick_id", "condition_id", "correlation_id", "current_snapshot_id",
            "current_snapshot_digest", "current_projection_id", "current_projection_digest",
            "current_fact_ids", "retrieved_record_ids", "retrieved_record_digests",
            "self_model_projection_present", "self_model_projection_id",
            "self_model_projection_digest", "self_model_reconciliation_id",
            "self_model_reconciliation_digest", "self_model_reconciliation_generation",
            "self_model_source_tick", "self_model_claim_ids", "self_model_claim_digests",
            "epistemic_projection_present", "epistemic_projection_id",
            "epistemic_projection_digest", "epistemic_proposition_ids",
            "epistemic_state_ids", "epistemic_state_digests", "epistemic_generations",
            "epistemic_evidence_set_digests", "epistemic_projection_schema",
            "epistemic_semantic_status", "epistemic_owner_packet_count",
            "epistemic_consumed_packet_ids", "epistemic_consumed_packet_digests",
            "epistemic_omitted_packets", "epistemic_omitted_packets_digest",
            "epistemic_consumed_packets_digest", "epistemic_projection_context_digest",
            "epistemic_prompt_digest", "epistemic_consumed_content_digest",
            "developmental_history_selection")
        context = {key: (list(observation.get(key, ()))
                         if isinstance(observation.get(key), (list, tuple))
                         else observation.get(key)) for key in context_fields}
        provenance = {
            "kind": COGNITION_LESSON_PROVENANCE_KIND,
            "observation_id": observation.get("observation_id"),
            "observation_digest": observation.get("observation_digest"),
            "source_output_text": source_output_text,
            "source_output_digest": receipt.output_digest,
            "source_request": dict(request),
            "conclusion": output["conclusion"],
            "lesson_candidate": lesson,
            "consumed_context": context,
            "model_id": request.get("model_id"),
            "model_artifact_digest": request.get("model_artifact_digest"),
            "active_model_identity": dict(observation.get("active_model_identity", {})),
            "authority_map_digest": observation.get("authority_map_digest"),
            "candidate_posture": "untrusted_candidate_not_truth_policy_authority_or_adopted_procedure",
            "current_truth": False, "authority": False, "policy": False,
            "canonical_explicit_user_retention": False,
        }
        raw = DevelopmentalCandidate(
            str(lesson["statement"]), str(lesson["uncertainty"]),
            "untrusted_history_conditioned_cognition_candidate",
            selection.snapshot_id, selection.snapshot_digest, selection.selection_id,
            selection.selection_digest, tuple(str(fact["fact_id"]) for fact in selection.facts),
            selection.sources, str(request.get("model_id")),
            request.get("model_artifact_digest"), str(request.get("request_id")),
            str(request.get("request_digest")), receipt.receipt_id, receipt.receipt_digest,
            receipt.output_digest, provenance, tuple(selection.facts))
        cid, digest = _identity("devcand", raw.semantic_payload())
        return replace(raw, candidate_id=cid, candidate_digest=digest)

    @staticmethod
    def infer_candidate(selection: SelectedEvidence, *, invoker: LocalModelInvoker,
                        correlation_id: str, budget: LocalModelInvocationBudget | None = None) -> DevelopmentalCandidate:
        bounded = budget or LocalModelInvocationBudget(max_input_chars=8000, max_output_chars=4000, max_new_tokens=512, timeout_seconds=30, max_calls_per_correlation=1)
        if bounded.max_calls_per_correlation != 1 or bounded.max_input_chars > 8000 or bounded.max_output_chars > 4000 or bounded.max_new_tokens > 512 or bounded.timeout_seconds > 30:
            raise DevelopmentalWritebackError("developmental_inference_budget_unbounded")
        schema = {"type":"object", "required":["interpretation","uncertainty"], "additionalProperties":False,
                  "properties":{"interpretation":{"type":"string","maxLength":MAX_INTERPRETATION_CHARS},
                                "uncertainty":{"type":"string","enum":["low","medium","high","unknown"]}}}
        instruction = ("Interpret selected World-State evidence only as bounded context, without asserting truth, authority, policy, goals, or storage. "
            "Preserve whether each source time is current, historical, or unknown; the World-State observation clock is not an event time unless the owner says so. "
            "Do not infer hostile activity, attack, intent, or cause from a protective-state custody failure; unreadable custody leaves the stored protective state unknown. "
            "A configured attestation snapshot signature-verification failure establishes only that verifier's bounded result, not attack, hostile activity, intent, compromise, or cause. "
            + ("An integrity-controller gate is only its bounded verifier result; a warning or failure does not establish attack, cause, hostile intent, compromise, or a successful defense. Skipped gates are gaps in coverage. Do not derive authority, policy, or a defensive procedure. "
               if _has_bounded_integrity_controller_observation(selection) else "")
            + "Keep provenance and uncertainty attached to each interpretation. For resource evidence, distinguish measured, "
            + "estimated, predicted, and unknown values by their source posture; shared host usage is not invocation attribution. "
            + "Resource expenditure is not inherently good or bad and must not become a reward, penalty, or objective.")
        request = invoker.build_request(purpose=PURPOSE, prompt=json.dumps({"instruction":instruction,
            "selection":selection.semantic_payload()}, sort_keys=True), caller=PRINCIPAL, correlation_id=correlation_id, expected_output_format="json", budget=bounded, upstream_evidence={"selection_id":selection.selection_id,"selection_digest":selection.selection_digest,"snapshot_id":selection.snapshot_id,"snapshot_digest":selection.snapshot_digest}, linkage={"transformation":"selected_world_state_to_historical_interpretation"}, structured_output_schema=schema)
        receipt = invoker.invoke(request, persist=True, include_output_in_receipt=False)
        return ResidentDevelopmentalWritebackController.candidate_from_receipt(selection, receipt)

    @staticmethod
    def candidate_from_receipt(selection: SelectedEvidence, receipt: LocalModelInvocationReceipt) -> DevelopmentalCandidate:
        if receipt.status not in {"admitted_completed", "admitted_simulation"} or receipt.purpose != PURPOSE or receipt.output_text is None or receipt.output_digest is None:
            raise DevelopmentalWritebackError("developmental_inference_not_completed")
        try: output = json.loads(receipt.output_text)
        except json.JSONDecodeError as exc: raise DevelopmentalWritebackError("malformed_developmental_output") from exc
        if not isinstance(output, dict) or set(output) != {"interpretation", "uncertainty"} or not isinstance(output["interpretation"], str) or not output["interpretation"].strip() or len(output["interpretation"]) > MAX_INTERPRETATION_CHARS or output["uncertainty"] not in {"low","medium","high","unknown"}:
            raise DevelopmentalWritebackError("malformed_developmental_output")
        req = dict(receipt.request)
        if req.get("purpose") != PURPOSE or req.get("upstream_evidence") != {"selection_id":selection.selection_id,"selection_digest":selection.selection_digest,"snapshot_id":selection.snapshot_id,"snapshot_digest":selection.snapshot_digest}:
            raise DevelopmentalWritebackError("inference_evidence_binding_mismatch")
        raw = DevelopmentalCandidate(output["interpretation"], output["uncertainty"], "untrusted_historical_interpretation_candidate", selection.snapshot_id, selection.snapshot_digest, selection.selection_id, selection.selection_digest, tuple(str(f["fact_id"]) for f in selection.facts), selection.sources, str(req["model_id"]), req.get("model_artifact_digest"), str(req["request_id"]), str(req["request_digest"]), receipt.receipt_id, receipt.receipt_digest, receipt.output_digest, {"kind":"governed_local_model_transformation", "purpose":PURPOSE, "selected_evidence_digest":selection.selection_digest}, tuple(selection.facts))
        cid, digest = _identity("devcand", raw.semantic_payload())
        return replace(raw, candidate_id=cid, candidate_digest=digest)

    @staticmethod
    def admission_configuration_digest(candidate: DevelopmentalCandidate, *, operation_id: str) -> str:
        return _digest({"candidate_id":candidate.candidate_id,"candidate_digest":candidate.candidate_digest,"operation_id":operation_id,"principal":PRINCIPAL,"effects":list(EFFECTS)})

    @contextmanager
    def _operation_lock(self) -> Iterator[None]:
        """Serialize operation identity lookup and durable publication."""
        if os.name != "posix":
            raise DevelopmentalWritebackError("developmental_writeback_lock_unsupported")
        directory_fd: int | None = None
        descriptor: int | None = None
        try:
            require_flock()
            directory_fd = open_private_directory(self.store.root, create=True)
            descriptor = os.open(
                ".developmental-writeback.lock",
                os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
                0o600,
                dir_fd=directory_fd,
            )
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.geteuid()
                or opened.st_nlink != 1
                or opened.st_mode & 0o077
            ):
                raise DevelopmentalWritebackError("developmental_writeback_lock_invalid")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        except DevelopmentalWritebackError:
            if descriptor is not None:
                os.close(descriptor)
            if directory_fd is not None:
                os.close(directory_fd)
            raise
        except (OSError, PrivateFileCustodyError) as exc:
            if descriptor is not None:
                os.close(descriptor)
            if directory_fd is not None:
                os.close(directory_fd)
            raise DevelopmentalWritebackError("developmental_writeback_lock_unavailable") from exc
        assert directory_fd is not None and descriptor is not None
        try:
            yield
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)
                os.close(directory_fd)

    def append(self, candidate: DevelopmentalCandidate, *, admission: AdmissionEvidence,
               operation_id: str, correlation_id: str, created_at: str | None = None) -> tuple[DevelopmentalRecord, WritebackReceipt]:
        with self._operation_lock():
            with self.admission_verifier.authorized_local_commit():
                return self._append_locked(candidate, admission=admission, operation_id=operation_id,
                    correlation_id=correlation_id, created_at=created_at)

    def _append_locked(self, candidate: DevelopmentalCandidate, *, admission: AdmissionEvidence,
                       operation_id: str, correlation_id: str,
                       created_at: str | None) -> tuple[DevelopmentalRecord, WritebackReceipt]:
        cid, cdigest = _identity("devcand", candidate.semantic_payload())
        if (candidate.candidate_id, candidate.candidate_digest) != (cid, cdigest):
            raise DevelopmentalWritebackError("candidate_digest_mismatch")
        _validate_candidate_source_bindings(candidate)
        _verify_history_conditioned_candidate(candidate)
        config = self.admission_configuration_digest(candidate, operation_id=operation_id)
        if tuple(admission.effects) != EFFECTS:
            raise DevelopmentalWritebackError("admission_effect_surface_not_exact")
        try:
            for effect in EFFECTS:
                self.admission_verifier.verify(
                    admission, current_sequence=self.current_sequence(),
                    capability_id=RESIDENT_DEVELOPMENTAL_WRITEBACK, principal_id=PRINCIPAL,
                    effect=effect, subject_id=candidate.candidate_id,
                    request_configuration_digest=config)
        except AdmissionError as exc:
            raise DevelopmentalWritebackError(f"runtime_admission_rejected:{exc}") from exc

        matches = [record for record in self.store.records() if record.operation_id == operation_id]
        if len(matches) > 1:
            raise DevelopmentalWritebackError("developmental_operation_identity_ambiguous")
        if matches:
            record = matches[0]
            if (
                digest_payload(record.candidate) != digest_payload(asdict(candidate))
                or record.admission_id != admission.admission_id
                or record.admission_binding_digest != admission.binding_digest
                or record.principal != PRINCIPAL
                or record.correlation_id != correlation_id
                or (created_at is not None and record.created_at != created_at)
            ):
                raise DevelopmentalWritebackError("developmental_operation_identity_collision")
        else:
            raw = DevelopmentalRecord(
                "", "", asdict(candidate), admission.admission_id, admission.binding_digest,
                PRINCIPAL, operation_id, correlation_id,
                created_at or datetime.now(timezone.utc).isoformat())
            rid, rdigest = _identity("devrec", raw.semantic_payload())
            record = self.store.append(replace(raw, record_id=rid, record_digest=rdigest))

        receipt_raw = WritebackReceipt(
            "", "", record.record_id, record.record_digest, candidate.candidate_id,
            candidate.candidate_digest, admission.admission_id, admission.binding_digest,
            PRINCIPAL, operation_id, True)
        receipt_id, receipt_digest = _identity("devreceipt", receipt_raw.semantic_payload())
        receipt = self.store.write_receipt(
            replace(receipt_raw, receipt_id=receipt_id, receipt_digest=receipt_digest))
        return record, receipt

    def retrieve(self, record_ids: Sequence[str], *, limit: int = MAX_RETRIEVAL_RECORDS) -> DevelopmentalHistoryProjection:
        ids = tuple(record_ids)
        if limit < 1 or limit > MAX_RETRIEVAL_RECORDS or len(ids) > limit or len(set(ids)) != len(ids): raise DevelopmentalWritebackError("retrieval_bounds_invalid")
        records = tuple(asdict(self.store.get(rid)) for rid in ids)
        return DevelopmentalHistoryProjection(records, ids)

    def recover_completed_records(self) -> tuple[tuple[DevelopmentalRecord, WritebackReceipt], ...]:
        """Verify and repair record/receipt custody under the append serialization lock."""
        if os.name == "posix":
            # Recovery may publish a missing deterministic receipt. Serialize its
            # inventory snapshot and repair with append's operation-id lookup so
            # restart reconciliation cannot race an authorized append.
            with self._operation_lock():
                return self._recover_completed_records_locked(repair_missing_receipts=True)
        # Windows recovery remains read-only; the POSIX writer lock is unavailable.
        return self._recover_completed_records_locked(repair_missing_receipts=False)

    def inspect_completed_records(self) -> tuple[tuple[DevelopmentalRecord, WritebackReceipt], ...]:
        """Revalidate durable history/admission lineage without repair or locking writes.

        This read-only inventory may observe a concurrent publication halfway
        through its record/receipt pair and fail closed. It never creates a
        lockfile, reconstructs a receipt, or changes authority state.
        """
        return self._recover_completed_records_locked(repair_missing_receipts=False)

    def _recover_completed_records_locked(
        self, *, repair_missing_receipts: bool,
    ) -> tuple[tuple[DevelopmentalRecord, WritebackReceipt], ...]:
        """Verify durable records and restore only their deterministic receipt metadata."""
        durable_records = self.store.records()
        records_by_id = {record.record_id: record for record in durable_records}
        if len(records_by_id) != len(durable_records):
            raise DevelopmentalWritebackError("durable_record_identity_collision")

        # Reconcile the whole receipt inventory before repairing any interrupted
        # record-to-receipt publication. A receipt whose record disappeared is
        # contradictory custody, not an empty or safely ignorable history.
        for stored_receipt in self.store.receipts():
            linked_record = records_by_id.get(stored_receipt.record_id)
            if linked_record is None:
                raise DevelopmentalWritebackError("durable_receipt_orphaned")
            candidate_id = linked_record.candidate.get("candidate_id")
            candidate_digest = linked_record.candidate.get("candidate_digest")
            if not isinstance(candidate_id, str) or not isinstance(candidate_digest, str):
                raise DevelopmentalWritebackError("durable_receipt_candidate_identity_invalid")
            receipt_raw = WritebackReceipt("", "", linked_record.record_id,
                linked_record.record_digest, candidate_id, candidate_digest,
                linked_record.admission_id, linked_record.admission_binding_digest,
                linked_record.principal, linked_record.operation_id, True)
            expected_id, expected_digest = _identity("devreceipt", receipt_raw.semantic_payload())
            expected_receipt = replace(receipt_raw, receipt_id=expected_id, receipt_digest=expected_digest)
            if stored_receipt != expected_receipt:
                raise DevelopmentalWritebackError("durable_receipt_record_lineage_mismatch")

        recovered: list[tuple[DevelopmentalRecord, WritebackReceipt]] = []
        for record in durable_records:
            try:
                candidate_payload = dict(record.candidate)
                candidate_payload["selected_fact_ids"] = tuple(candidate_payload["selected_fact_ids"])
                candidate_payload["selected_sources"] = tuple(candidate_payload["selected_sources"])
                candidate_payload["selected_facts"] = tuple(candidate_payload.get("selected_facts", ()))
                candidate = DevelopmentalCandidate(**candidate_payload)
            except (KeyError, TypeError, ValueError) as exc:
                raise DevelopmentalWritebackError("durable_candidate_reconstruction_failed") from exc
            candidate_id, candidate_digest = _identity("devcand", candidate.semantic_payload())
            if (candidate.candidate_id, candidate.candidate_digest) != (candidate_id, candidate_digest):
                raise DevelopmentalWritebackError("durable_candidate_digest_mismatch")
            _validate_candidate_source_bindings(candidate)
            _verify_history_conditioned_candidate(candidate)
            is_cognition_candidate = (
                candidate.transformation_provenance.get("kind")
                == COGNITION_LESSON_PROVENANCE_KIND)
            if ((not candidate.selected_fact_ids and not is_cognition_candidate)
                    or len(candidate.selected_fact_ids) > MAX_SELECTED_FACTS
                    or len(set(candidate.selected_fact_ids)) != len(candidate.selected_fact_ids)
                    or any(not isinstance(item, str) or not item for item in candidate.selected_fact_ids)):
                raise DevelopmentalWritebackError("durable_candidate_fact_bounds_invalid")
            if candidate.selected_facts:
                if (len(candidate.selected_facts) != len(candidate.selected_fact_ids)
                        or any(not isinstance(fact, Mapping) for fact in candidate.selected_facts)
                        or any(not isinstance(source, Mapping) for source in candidate.selected_sources)
                        or tuple(str(fact.get("fact_id", "")) for fact in candidate.selected_facts)
                            != candidate.selected_fact_ids
                        or len(json.dumps([dict(fact) for fact in candidate.selected_facts], sort_keys=True,
                            separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
                            > _selected_fact_byte_limit(candidate.selected_facts)):
                    raise DevelopmentalWritebackError("durable_candidate_fact_payload_invalid")
                selected_sources = {str(source.get("source_id", "")): dict(source)
                                    for source in candidate.selected_sources}
                for fact in candidate.selected_facts:
                    source = fact.get("source")
                    subject = fact.get("subject")
                    if (set(fact) != {"fact_id", "subject", "stage", "disposition", "evidence_strength",
                                      "source", "payload", "effect_claimed", "effect_proven", "observed_at"}
                            or not isinstance(source, Mapping) or not isinstance(subject, Mapping)
                            or set(subject) != {"subject_id", "subject_kind", "labels"}
                            or not isinstance(subject.get("subject_id"), str)
                            or not isinstance(subject.get("subject_kind"), str)
                            or not isinstance(subject.get("labels"), list)
                            or not isinstance(fact.get("stage"), str)
                            or not isinstance(fact.get("disposition"), str)
                            or not isinstance(fact.get("evidence_strength"), str)
                            or type(fact.get("effect_claimed")) is not bool
                            or type(fact.get("effect_proven")) is not bool
                            or selected_sources.get(str(source.get("source_id", ""))) != dict(source)
                            or not isinstance(fact.get("payload"), Mapping)
                            or not isinstance(source.get("source_id"), str)
                            or not isinstance(source.get("digest"), str)
                            or len(source["digest"]) != 64
                            or any(character not in "0123456789abcdef" for character in source["digest"])):
                        raise DevelopmentalWritebackError("durable_candidate_fact_source_mismatch")
                    payload_value = dict(fact["payload"])
                    projection = payload_value.pop("interpretation_projection", None)
                    if projection is None:
                        expected_id = "fact-" + digest((subject.get("subject_id"), subject.get("subject_kind"),
                            fact.get("stage"), fact.get("disposition"), source.get("digest"),
                            dict(fact["payload"]), fact.get("effect_claimed"),
                            fact.get("effect_proven")))[:16]
                        if fact.get("fact_id") != expected_id:
                            raise DevelopmentalWritebackError("durable_candidate_fact_identity_mismatch")
                    else:
                        if (not isinstance(projection, Mapping)
                                or set(projection) != {"schema_version", "source_fact_id", "source_payload_digest",
                                    "source_record_digest", "projected_payload_digest", "projection_digest"}
                                or projection.get("schema_version") not in {
                                    "sentientos.resource_interpretation_projection:v1",
                                    "sentientos.runtime_history_projection:v1",
                                    "sentientos.model_replacement_interpretation_projection:v1",
                                    "sentientos.model_replacement_interpretation_projection:v2",
                                    "sentientos.developmental_history_interpretation_projection:v1"}
                                or (projection.get("schema_version")
                                    == "sentientos.runtime_history_projection:v1"
                                    and not (
                                        (source.get("kind") == "runtime_supervisor"
                                            and subject.get("subject_kind") in {
                                                "chat_process_runtime_generation_observation",
                                                "chat_process_recovery_transition",
                                                "resident_parent_lifecycle_history",
                                                "serving_operation_history"})
                                        or (source.get("kind") == "resource_governor"
                                            and subject.get("subject_kind")
                                                == "chat_process_software_generation_invocation")))
                                or (projection.get("schema_version")
                                    in {"sentientos.model_replacement_interpretation_projection:v1",
                                        "sentientos.model_replacement_interpretation_projection:v2"}
                                    and not (source.get("kind") == "embodiment"
                                        and subject.get("subject_kind")
                                            == "developmental_model_replacement_experiment"
                                        and payload_value.get("run_id") == subject.get("subject_id")
                                        and payload_value.get("current_truth") is False
                                        and payload_value.get("authority") is False))
                                or (projection.get("schema_version")
                                    == "sentientos.model_replacement_interpretation_projection:v2"
                                    and not _valid_model_replacement_continuity_assessment(
                                        payload_value.get("continuity_assessment"),
                                        disposition=fact.get("disposition")))
                                or (projection.get("schema_version")
                                    == "sentientos.developmental_history_interpretation_projection:v1"
                                    and not (source.get("kind") == "embodiment"
                                        and subject.get("subject_kind")
                                            == "developmental_history_intervention_experiment"
                                        and payload_value.get("run_id") == subject.get("subject_id")
                                        and payload_value.get("current_truth") is False
                                        and payload_value.get("authority") is False
                                        and payload_value.get("learning_established") is False
                                        and payload_value.get("reconstruction_time_is_event_time") is False
                                        and isinstance(payload_value.get("conditions"), list)
                                        and len(payload_value["conditions"]) == 3))
                                or projection.get("source_fact_id") != fact.get("fact_id")
                                or projection.get("source_record_digest") != source.get("digest")
                                or projection.get("projected_payload_digest") != digest(payload_value)):
                            raise DevelopmentalWritebackError("durable_resource_projection_binding_invalid")
                        projection_semantic = dict(projection); claimed_projection = projection_semantic.pop("projection_digest")
                        if claimed_projection != digest(projection_semantic):
                            raise DevelopmentalWritebackError("durable_resource_projection_digest_mismatch")
                        source_payload_digest = str(projection.get("source_payload_digest", ""))
                        if (len(source_payload_digest) != 64
                                or any(character not in "0123456789abcdef" for character in source_payload_digest)):
                            raise DevelopmentalWritebackError("durable_resource_source_payload_digest_invalid")
            admission = self.admission_verifier.recorded_admission(record.admission_id)
            # The recorded admission's configuration digest below binds the
            # exact operation_id. Recovery must not infer that identity again
            # from correlation_id: the public append owner accepts explicit,
            # independently admitted operation identities.
            if (admission.binding_digest != record.admission_binding_digest
                    or admission.effects != EFFECTS or record.principal != PRINCIPAL
                    or admission.principal_id != PRINCIPAL
                    or admission.subject_id != candidate.candidate_id):
                raise DevelopmentalWritebackError("durable_admission_binding_mismatch")
            request_digest = self.admission_configuration_digest(candidate, operation_id=record.operation_id)
            try:
                for effect in EFFECTS:
                    self.admission_verifier.verify(admission, current_sequence=admission.issued_sequence,
                        capability_id=RESIDENT_DEVELOPMENTAL_WRITEBACK, principal_id=PRINCIPAL,
                        effect=effect, subject_id=candidate.candidate_id,
                        request_configuration_digest=request_digest)
            except AdmissionError as exc:
                raise DevelopmentalWritebackError("durable_admission_recovery_rejected") from exc
            raw = WritebackReceipt("", "", record.record_id, record.record_digest,
                candidate.candidate_id, candidate.candidate_digest, record.admission_id,
                record.admission_binding_digest, record.principal, record.operation_id, True)
            receipt_id, receipt_digest = _identity("devreceipt", raw.semantic_payload())
            expected_receipt = replace(raw, receipt_id=receipt_id, receipt_digest=receipt_digest)
            if repair_missing_receipts:
                receipt = self.store.write_receipt(expected_receipt)
            else:
                try:
                    receipt = self.store.get_receipt(receipt_id)
                except DevelopmentalWritebackError as exc:
                    if str(exc) == "stored_payload_missing":
                        raise DevelopmentalWritebackError(
                            "durable_writeback_receipt_missing") from exc
                    raise
                if receipt != expected_receipt:
                    raise DevelopmentalWritebackError("durable_receipt_record_lineage_mismatch")
            recovered.append((record, receipt))
        return tuple(recovered)


def _verify_history_conditioned_candidate(candidate: DevelopmentalCandidate) -> None:
    """Revalidate the exact source-output packet carried by a cognition candidate."""
    provenance = candidate.transformation_provenance
    if not isinstance(provenance, Mapping):
        raise DevelopmentalWritebackError("candidate_transformation_provenance_invalid")
    if provenance.get("kind") != COGNITION_LESSON_PROVENANCE_KIND:
        return
    source_text = provenance.get("source_output_text")
    source_request = provenance.get("source_request")
    if (not isinstance(source_request, Mapping)
            or set(source_request) != {"purpose", "prompt_digest", "prompt_size", "model_id",
                "authority_map_digest", "model_artifact_digest", "active_model_identity",
                "caller", "lifecycle_phase", "correlation_id", "expected_output_format",
                "structured_output_schema", "budget", "upstream_evidence", "linkage",
                "allowed_effects", "forbidden_effects", "request_id", "request_digest",
                "raw_prompt_stored", "ephemeral_prompt_handling"}
            or source_request.get("purpose") != "resident_developmental_retrieval_cognition"
            or source_request.get("expected_output_format") != "json"
            or source_request.get("structured_output_schema") != RESIDENT_COGNITION_LESSON_OUTPUT_SCHEMA
            or source_request.get("request_id") != candidate.request_id
            or source_request.get("request_digest") != candidate.request_digest
            or source_request.get("model_id") != candidate.model_id
            or source_request.get("model_artifact_digest") != candidate.model_artifact_digest
            or source_request.get("allowed_effects") != {"local_model_inference": True}
            or source_request.get("forbidden_effects") != {
                "provider_network": False, "tool": False, "memory": False,
                "action": False, "adoption": False, "repository_mutation": False}
            or source_request.get("raw_prompt_stored") is not False):
        raise DevelopmentalWritebackError("cognition_candidate_request_invalid")
    request_semantic = {key: value for key, value in source_request.items()
        if key not in {"request_id", "request_digest", "raw_prompt_stored", "ephemeral_prompt_handling"}}
    request_budget = source_request.get("budget")
    if (not isinstance(request_budget, Mapping)
            or set(request_budget) != {"max_input_chars", "max_output_chars", "max_new_tokens",
                                      "timeout_seconds", "max_calls_per_correlation"}
            or not isinstance(request_budget.get("max_input_chars"), int)
            or request_budget["max_input_chars"] > 16_000
            or not isinstance(request_budget.get("max_output_chars"), int)
            or request_budget["max_output_chars"] > 4000
            or not isinstance(request_budget.get("max_new_tokens"), int)
            or request_budget["max_new_tokens"] > 512
            or not isinstance(request_budget.get("timeout_seconds"), (int, float))
            or request_budget["timeout_seconds"] > 30
            or request_budget.get("max_calls_per_correlation") != 1):
        raise DevelopmentalWritebackError("cognition_candidate_budget_invalid")
    if (digest_payload(request_semantic) != candidate.request_digest
            or candidate.request_id != "lmreq-" + candidate.request_digest[:24]):
        raise DevelopmentalWritebackError("cognition_candidate_request_digest_invalid")
    context = provenance.get("consumed_context")
    upstream = source_request.get("upstream_evidence")
    upstream_context_keys = {
        "snapshot_id": "current_snapshot_id", "snapshot_digest": "current_snapshot_digest",
        "current_projection_id": "current_projection_id",
        "current_projection_digest": "current_projection_digest",
        "current_fact_ids": "current_fact_ids", "record_ids": "retrieved_record_ids",
        "record_digests": "retrieved_record_digests",
        "self_model_projection_present": "self_model_projection_present",
        "self_model_projection_id": "self_model_projection_id",
        "self_model_projection_digest": "self_model_projection_digest",
        "self_model_reconciliation_id": "self_model_reconciliation_id",
        "self_model_reconciliation_digest": "self_model_reconciliation_digest",
        "self_model_reconciliation_generation": "self_model_reconciliation_generation",
        "self_model_source_tick": "self_model_source_tick",
        "self_model_claim_ids": "self_model_claim_ids",
        "self_model_claim_digests": "self_model_claim_digests",
        "epistemic_projection_id": "epistemic_projection_id",
        "epistemic_projection_digest": "epistemic_projection_digest",
        "epistemic_proposition_ids": "epistemic_proposition_ids",
        "epistemic_state_ids": "epistemic_state_ids",
        "epistemic_state_digests": "epistemic_state_digests",
        "epistemic_generations": "epistemic_generations",
        "epistemic_evidence_set_digests": "epistemic_evidence_set_digests",
        "epistemic_projection_schema": "epistemic_projection_schema",
        "epistemic_semantic_status": "epistemic_semantic_status",
        "epistemic_owner_packet_count": "epistemic_owner_packet_count",
        "epistemic_consumed_packet_ids": "epistemic_consumed_packet_ids",
        "epistemic_consumed_packet_digests": "epistemic_consumed_packet_digests",
        "epistemic_omitted_packets": "epistemic_omitted_packets",
        "epistemic_omitted_packets_digest": "epistemic_omitted_packets_digest",
        "epistemic_consumed_packets_digest": "epistemic_consumed_packets_digest",
        "epistemic_projection_context_digest": "epistemic_projection_context_digest",
        "epistemic_prompt_digest": "epistemic_prompt_digest",
        "epistemic_consumed_content_digest": "epistemic_consumed_content_digest",
        "developmental_history_selection": "developmental_history_selection",
    }
    expected_upstream = ({key: context.get(value) for key, value in upstream_context_keys.items()}
        if isinstance(context, Mapping) else {})
    if (not isinstance(upstream, Mapping)
            or any(upstream.get(key) != value for key, value in expected_upstream.items())
            or source_request.get("model_id") != provenance.get("model_id")
            or source_request.get("model_artifact_digest") != provenance.get("model_artifact_digest")):
        raise DevelopmentalWritebackError("cognition_candidate_request_lineage_invalid")
    if (candidate.epistemic_status != "untrusted_history_conditioned_cognition_candidate"
            or provenance.get("candidate_posture")
                != "untrusted_candidate_not_truth_policy_authority_or_adopted_procedure"
            or provenance.get("current_truth") is not False
            or provenance.get("authority") is not False
            or provenance.get("policy") is not False
            or provenance.get("canonical_explicit_user_retention") is not False):
        raise DevelopmentalWritebackError("cognition_candidate_posture_invalid")
    if (not isinstance(source_text, str) or len(source_text.encode("utf-8")) > 4000
            or digest_payload({"output": source_text}) != candidate.output_digest
            or provenance.get("source_output_digest") != candidate.output_digest
            or not isinstance(provenance.get("observation_id"), str)
            or not isinstance(provenance.get("observation_digest"), str)):
        raise DevelopmentalWritebackError("cognition_candidate_source_output_invalid")
    try:
        output = json.loads(source_text)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise DevelopmentalWritebackError("cognition_candidate_source_output_invalid") from exc
    lesson = provenance.get("lesson_candidate")
    context = provenance.get("consumed_context")
    dependencies = lesson.get("evidence_dependencies") if isinstance(lesson, Mapping) else None
    contradictions = lesson.get("possible_contradiction_ids") if isinstance(lesson, Mapping) else None
    consumed_ids: set[str] = set()
    if isinstance(context, Mapping):
        for key in ("retrieved_record_ids", "current_fact_ids", "self_model_claim_ids",
                    "epistemic_consumed_packet_ids"):
            values = context.get(key, ())
            if isinstance(values, (list, tuple)) and all(isinstance(value, str) for value in values):
                consumed_ids.update(values)
    if (not isinstance(output, dict) or set(output) != {"conclusion", "lesson_candidate"}
            or output.get("conclusion") != provenance.get("conclusion")
            or output.get("lesson_candidate") != lesson
            or not isinstance(lesson, Mapping)
            or set(lesson) != {"statement", "scope", "applicability", "uncertainty",
                "uncertainty_rationale", "evidence_dependencies", "possible_contradiction_ids"}
            or candidate.interpretation != lesson.get("statement")
            or candidate.uncertainty != lesson.get("uncertainty")
            or not isinstance(dependencies, list) or not dependencies
            or len(dependencies) > 8 or any(not isinstance(value, str) for value in dependencies)
            or len(set(dependencies)) != len(dependencies)
            or not set(dependencies).issubset(consumed_ids)
            or not isinstance(contradictions, list) or len(contradictions) > 8
            or any(not isinstance(value, str) for value in contradictions)
            or len(set(contradictions)) != len(contradictions)
            or not set(contradictions).issubset(consumed_ids)
            or not isinstance(context, Mapping)
            or context.get("condition_id") != "with-history"
            or not context.get("retrieved_record_ids")):
        raise DevelopmentalWritebackError("cognition_candidate_lineage_invalid")


def measure_changed_cognition(*, with_record: CognitionObservation, without_record: CognitionObservation,
                              expected_record_ids: Sequence[str]) -> ChangedCognitionMeasurement:
    expected = tuple(expected_record_ids)
    if not expected or with_record.retrieved_record_ids != expected or without_record.retrieved_record_ids or with_record.condition_id == without_record.condition_id:
        raise DevelopmentalWritebackError("controlled_measurement_conditions_invalid")
    payload = {"with_record":asdict(with_record),"without_record":asdict(without_record),"compared_fields":["downstream_cognition_id","downstream_cognition_digest"],"observable_difference":with_record.downstream_cognition_digest != without_record.downstream_cognition_digest}
    mid, digest = _identity("devmeasure", payload)
    return ChangedCognitionMeasurement(mid, digest, asdict(with_record), asdict(without_record), ("downstream_cognition_id","downstream_cognition_digest"), bool(payload["observable_difference"]))
