"""Freeze and validate a score-bound negative-guidance comparison.

This protocol is intentionally separate from raw-example ablation. It binds
the owner-composed prompts, selected history, private task commitment, held-out
probes, generation settings, and one-shot owner ticks before model execution.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sentientos.governed_local_model_invocation import validate_receipt

SCHEMA_VERSION = "sentientos.negative_guidance_intervention_protocol:v1"
PREVIEW_SCHEMA = "sentientos.objective_negative_guidance_prompt_pair_preview:v1"
ARMS = ("negative_guidance_present", "negative_guidance_omitted")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


class NegativeGuidanceInterventionError(ValueError):
    """Invalid negative-guidance preview or frozen execution protocol."""


@dataclass(frozen=True)
class NegativeGuidanceArmExecution:
    """One verified owner observation and its receipt-bound history inventory."""

    receipt: Mapping[str, Any]
    observation: Mapping[str, Any]
    runtime_history_inventory: Mapping[str, Any]


@dataclass(frozen=True)
class NegativeGuidancePairJournalResult:
    """Durable score and terminal evidence for one completed paired task."""

    protocol_digest: str
    score: Mapping[str, Any]
    terminal: Mapping[str, Any]


def digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _require_digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise NegativeGuidanceInterventionError(code)
    return value


def _normalize_digest(value: Any, code: str) -> str:
    if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value):
        return "sha256:" + value
    return _require_digest(value, code)


def _verify_pair_preview(preview: Mapping[str, Any], *,
        target_model_identity_digest: str, task_digest: str) -> None:
    if (preview.get("schema_version") != PREVIEW_SCHEMA
            or preview.get("exact_owner_prompts_reconstructed") is not True
            or preview.get("prompt_pair_owner_composition_verified") is not True
            or preview.get("runtime_condition_created") is not False
            or preview.get("inference_performed") is not False
            or preview.get("learning_established") is not False
            or preview.get("authority") is not False
            or preview.get("target_model_identity_digest")
                != target_model_identity_digest
            or preview.get("task_digest") != task_digest
            or preview.get("changed_context_fields") != ["developmental_history"]
            or preview.get("intervention") !=
                "remove_only_prior_incorrect_examples_from_selected_history"):
        raise NegativeGuidanceInterventionError("negative_guidance_preview_invalid")
    preview_digest = _require_digest(preview.get("pair_preview_digest"),
        "negative_guidance_preview_digest_invalid")
    semantic = {key: value for key, value in preview.items()
        if key != "pair_preview_digest"}
    if digest(semantic) != preview_digest:
        raise NegativeGuidanceInterventionError(
            "negative_guidance_preview_digest_mismatch")
    ablation = preview.get("historical_negative_guidance_ablation")
    if (not isinstance(ablation, Mapping)
            or ablation.get("schema_version") !=
                "sentientos.objective_negative_guidance_prompt_ablation:v1"
            or ablation.get("intervention") !=
                "remove_only_prior_incorrect_examples_from_selected_history"
            or ablation.get("changed_context_fields") != ["developmental_history"]
            or ablation.get("no_imitation_instruction_unchanged") is not True
            or ablation.get("per_record_strategies_unchanged") is not True
            or ablation.get("accumulated_strategy_unchanged") is not True
            or ablation.get("inference_performed") is not False
            or ablation.get("learning_established") is not False
            or ablation.get("authority") is not False
            or type(ablation.get("removed_example_count")) is not int
            or ablation.get("removed_example_count", 0) <= 0):
        raise NegativeGuidanceInterventionError(
            "negative_guidance_ablation_invalid")
    ids = preview.get("history_record_ids")
    record_digests = preview.get("history_record_digests")
    probes = preview.get("probe_binding_digests")
    if (not isinstance(ids, list) or not ids or len(ids) != len(set(ids))
            or any(not isinstance(item, str) or not item for item in ids)
            or not isinstance(record_digests, list)
            or len(record_digests) != len(ids)
            or any(not isinstance(item, str) or _DIGEST.fullmatch(item) is None
                for item in record_digests)
            or ablation.get("selected_record_ids") != ids
            or ablation.get("selected_record_digests") != record_digests
            or not isinstance(probes, list) or not probes
            or any(not isinstance(item, str) or _DIGEST.fullmatch(item) is None
                for item in probes)
            or len(probes) != len(set(probes))):
        raise NegativeGuidanceInterventionError(
            "negative_guidance_preview_history_or_probe_binding_invalid")
    for field in ("snapshot_digest", "target_model_identity_digest",
            "generation_budget_digest", "history_set_digest",
            "baseline_prompt_digest", "ablated_prompt_digest"):
        _normalize_digest(preview.get(field),
            "negative_guidance_preview_binding_invalid:" + field)
    prompt_digests = preview.get("invocation_prompt_digests")
    request_digests = preview.get("preview_request_digests")
    owner_protocols = preview.get("owner_protocols")
    if (not isinstance(prompt_digests, Mapping)
            or set(prompt_digests) != set(ARMS)
            or not isinstance(request_digests, Mapping)
            or set(request_digests) != set(ARMS)
            or not isinstance(owner_protocols, Mapping)
            or set(owner_protocols) != set(ARMS)):
        raise NegativeGuidanceInterventionError(
            "negative_guidance_preview_arm_bindings_invalid")
    for arm in ARMS:
        _require_digest(prompt_digests.get(arm),
            "negative_guidance_preview_prompt_digest_invalid")
        _require_digest(request_digests.get(arm),
            "negative_guidance_preview_request_digest_invalid")
        binding = owner_protocols[arm]
        owner_protocol = binding.get("protocol") if isinstance(binding, Mapping) else None
        if not isinstance(owner_protocol, Mapping):
            raise NegativeGuidanceInterventionError(
                "negative_guidance_preview_owner_protocol_missing")
        try:
            from sentientos.developmental_history_intervention_experiment import (
                DevelopmentalHistoryInterventionProtocol, verify_protocol)
            tuple_fields = {"current_fact_ids", "record_ids", "record_digests",
                "condition_order", "planned_comparisons", "non_claims",
                "epistemic_state_digests", "epistemic_evidence_set_digests",
                "self_model_claim_ids", "self_model_claim_digests"}
            owner_value = dict(owner_protocol)
            for field in tuple_fields:
                if isinstance(owner_value.get(field), list):
                    owner_value[field] = tuple(owner_value[field])
            reconstructed_owner_protocol = (
                DevelopmentalHistoryInterventionProtocol(**owner_value))
            verify_protocol(reconstructed_owner_protocol)
        except Exception as exc:
            raise NegativeGuidanceInterventionError(
                "negative_guidance_preview_owner_protocol_digest_mismatch:" + arm) from exc
        if (binding.get("protocol_digest") != owner_protocol.get("protocol_digest")
                or binding.get("execution_tick_id") is None
                or binding.get("objective_task_plan_digest") is None):
            raise NegativeGuidanceInterventionError(
                "negative_guidance_preview_owner_protocol_invalid:" + arm)
        _require_digest(binding.get("protocol_digest"),
            "negative_guidance_preview_owner_protocol_digest_invalid")
        _require_digest(binding.get("objective_task_plan_digest"),
            "negative_guidance_preview_task_plan_digest_invalid")


def prepare_negative_guidance_pair(*, preview: Mapping[str, Any],
        target_model_identity_digest: str, task_digest: str,
        private_task_plan_digest: str, generation_config_digest: str,
        answer_key_digest: str, held_out_probe_overlap_audit: Mapping[str, Any],
        held_out_probe_overlap_audit_digest: str,
        arm_order: Sequence[str] = ARMS) -> dict[str, Any]:
    """Freeze the paired prompts into a pre-inference execution protocol."""
    for value, code in ((target_model_identity_digest,
            "negative_guidance_model_identity_invalid"),
            (task_digest, "negative_guidance_task_digest_invalid"),
            (private_task_plan_digest, "negative_guidance_private_task_plan_digest_invalid"),
            (generation_config_digest, "negative_guidance_generation_digest_invalid"),
            (answer_key_digest, "negative_guidance_answer_key_digest_invalid"),
            (held_out_probe_overlap_audit_digest,
                "negative_guidance_probe_audit_digest_invalid")):
        _require_digest(value, code)
    if not isinstance(preview, Mapping):
        raise NegativeGuidanceInterventionError("negative_guidance_preview_invalid")
    _verify_pair_preview(preview, target_model_identity_digest=
        target_model_identity_digest, task_digest=task_digest)
    if (not isinstance(held_out_probe_overlap_audit, Mapping)
            or held_out_probe_overlap_audit.get("no_exact_overlap_detected") is not True
            or held_out_probe_overlap_audit.get("overlapping_probe_input_count") != 0
            or held_out_probe_overlap_audit.get("authority") is not False
            or held_out_probe_overlap_audit.get("inference_performed") is not False
            or held_out_probe_overlap_audit.get("learning_established") is not False
            or digest(dict(held_out_probe_overlap_audit))
                != held_out_probe_overlap_audit_digest):
        raise NegativeGuidanceInterventionError(
            "negative_guidance_preview_probe_audit_invalid")
    if not isinstance(arm_order, (list, tuple)) or tuple(arm_order) not in (
            ARMS, tuple(reversed(ARMS))):
        raise NegativeGuidanceInterventionError("negative_guidance_arm_order_invalid")
    ablation = preview["historical_negative_guidance_ablation"]
    semantic = {
        "schema_version": SCHEMA_VERSION,
        "conditions": list(arm_order),
        "intervention": "remove_only_prior_incorrect_examples_from_selected_history",
        "changed_context_fields": ["developmental_history"],
        "target_model_identity_digest": target_model_identity_digest,
        "task_digest": task_digest,
        "private_task_plan_digest": private_task_plan_digest,
        "generation_config_digest": generation_config_digest,
        "generation_budget_digest": preview["generation_budget_digest"],
        "held_out_probe_overlap_audit_digest": held_out_probe_overlap_audit_digest,
        "task_family_id": preview["task_family_id"],
        "snapshot_id": preview["snapshot_id"],
        "snapshot_digest": _normalize_digest(preview["snapshot_digest"],
            "negative_guidance_snapshot_digest_invalid"),
        "history_record_ids": list(preview["history_record_ids"]),
        "history_record_digests": list(preview["history_record_digests"]),
        "history_set_digest": preview["history_set_digest"],
        "probe_binding_digests": list(preview["probe_binding_digests"]),
        "answer_key_digest": answer_key_digest,
        "removed_example_count": ablation["removed_example_count"],
        "removed_packet_count": ablation["removed_packet_count"],
        "removed_evidence_digest": ablation["removed_evidence_digest"],
        "negative_guidance_ablation": dict(ablation),
        "no_imitation_instruction_unchanged": True,
        "retained_per_record_strategy_count":
            ablation["retained_per_record_strategy_count"],
        "per_record_strategies_unchanged": True,
        "accumulated_strategy_unchanged": True,
        "invocation_prompt_digests": dict(preview["invocation_prompt_digests"]),
        "preview_request_digests": dict(preview["preview_request_digests"]),
        "owner_execution_tick_ids": {arm: preview["owner_protocols"][arm][
            "execution_tick_id"] for arm in ARMS},
        "owner_protocol_digests": {arm: preview["owner_protocols"][arm][
            "protocol_digest"] for arm in ARMS},
        "owner_task_plan_digests": {arm: preview["owner_protocols"][arm][
            "objective_task_plan_digest"] for arm in ARMS},
        "owner_pair_preview_digest": preview["pair_preview_digest"],
        "owner_pair_preview_schema": PREVIEW_SCHEMA,
        "owner_prompt_pair_composition_verified": True,
        "exact_pair_verified": True,
        "runtime_condition_created": False,
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
    }
    protocol = {**semantic, "protocol_digest": digest(semantic)}
    validate_negative_guidance_protocol(protocol,
        target_model_identity_digest=target_model_identity_digest,
        task_digest=task_digest)
    return protocol


def validate_negative_guidance_protocol(protocol: Mapping[str, Any], *,
        target_model_identity_digest: str | None = None,
        task_digest: str | None = None) -> None:
    """Validate frozen bindings without reading prompt text or answer values."""
    if (not isinstance(protocol, Mapping)
            or protocol.get("schema_version") != SCHEMA_VERSION
            or protocol.get("conditions") not in (list(ARMS), list(reversed(ARMS)))
            or protocol.get("intervention") !=
                "remove_only_prior_incorrect_examples_from_selected_history"
            or protocol.get("changed_context_fields") != ["developmental_history"]
            or protocol.get("owner_pair_preview_schema") != PREVIEW_SCHEMA
            or protocol.get("owner_prompt_pair_composition_verified") is not True
            or protocol.get("exact_pair_verified") is not True
            or protocol.get("runtime_condition_created") is not False
            or protocol.get("inference_performed") is not False
            or protocol.get("learning_established") is not False
            or protocol.get("authority") is not False
            or protocol.get("no_imitation_instruction_unchanged") is not True
            or protocol.get("per_record_strategies_unchanged") is not True
            or protocol.get("accumulated_strategy_unchanged") is not True):
        raise NegativeGuidanceInterventionError("negative_guidance_protocol_invalid")
    semantic = {key: value for key, value in protocol.items()
        if key != "protocol_digest"}
    if protocol.get("protocol_digest") != digest(semantic):
        raise NegativeGuidanceInterventionError(
            "negative_guidance_protocol_digest_mismatch")
    for field in ("target_model_identity_digest", "task_digest",
            "private_task_plan_digest", "generation_config_digest",
            "generation_budget_digest", "held_out_probe_overlap_audit_digest",
            "snapshot_digest", "history_set_digest", "answer_key_digest",
            "owner_pair_preview_digest", "removed_evidence_digest"):
        _require_digest(protocol.get(field),
            "negative_guidance_protocol_binding_invalid")
    ablation = protocol.get("negative_guidance_ablation")
    if (not isinstance(ablation, Mapping)
            or ablation.get("schema_version") !=
                "sentientos.objective_negative_guidance_prompt_ablation:v1"
            or ablation.get("removed_example_count") !=
                protocol.get("removed_example_count")
            or ablation.get("removed_evidence_digest") !=
                protocol.get("removed_evidence_digest")
            or ablation.get("no_imitation_instruction_unchanged") is not True
            or ablation.get("inference_performed") is not False
            or ablation.get("learning_established") is not False
            or ablation.get("authority") is not False):
        raise NegativeGuidanceInterventionError(
            "negative_guidance_protocol_ablation_binding_invalid")
    if ((target_model_identity_digest is not None and protocol.get(
            "target_model_identity_digest") != target_model_identity_digest)
            or (task_digest is not None and protocol.get("task_digest") != task_digest)):
        raise NegativeGuidanceInterventionError(
            "negative_guidance_protocol_expected_binding_mismatch")
    if (type(protocol.get("removed_example_count")) is not int
            or protocol["removed_example_count"] <= 0
            or type(protocol.get("removed_packet_count")) is not int
            or protocol["removed_packet_count"] <= 0
            or type(protocol.get("retained_per_record_strategy_count")) is not int
            or protocol["retained_per_record_strategy_count"] < 0):
        raise NegativeGuidanceInterventionError(
            "negative_guidance_protocol_counts_invalid")
    ids = protocol.get("history_record_ids")
    record_digests = protocol.get("history_record_digests")
    probes = protocol.get("probe_binding_digests")
    if (not isinstance(ids, list) or not ids or len(ids) != len(set(ids))
            or not isinstance(record_digests, list) or len(record_digests) != len(ids)
            or any(not isinstance(item, str) or not item for item in ids)
            or any(not isinstance(item, str) or _DIGEST.fullmatch(item) is None
                for item in record_digests)
            or digest({"record_ids": ids, "record_digests": record_digests})
                != protocol["history_set_digest"]
            or not isinstance(probes, list) or not probes
            or any(not isinstance(item, str) or _DIGEST.fullmatch(item) is None
                for item in probes)
            or len(probes) != len(set(probes))):
        raise NegativeGuidanceInterventionError(
            "negative_guidance_protocol_history_or_probe_binding_invalid")
    for field in ("owner_protocol_digests", "owner_task_plan_digests",
            "invocation_prompt_digests", "preview_request_digests",
            "owner_execution_tick_ids"):
        mapping = protocol.get(field)
        if not isinstance(mapping, Mapping) or set(mapping) != set(ARMS):
            raise NegativeGuidanceInterventionError(
                "negative_guidance_protocol_arm_bindings_invalid")
    for field in ("owner_protocol_digests", "owner_task_plan_digests",
            "invocation_prompt_digests", "preview_request_digests"):
        if any(not isinstance(value, str) or _DIGEST.fullmatch(value) is None
                for value in protocol[field].values()):
            raise NegativeGuidanceInterventionError(
                "negative_guidance_protocol_arm_digest_invalid")
    ticks = protocol["owner_execution_tick_ids"]
    if (any(not isinstance(value, str) or not value or len(value) > 256
            for value in ticks.values()) or len(set(ticks.values())) != len(ARMS)):
        raise NegativeGuidanceInterventionError(
            "negative_guidance_protocol_execution_ticks_invalid")
    if protocol.get("base_preflight_protocol_digest") is not None:
        _require_digest(protocol["base_preflight_protocol_digest"],
            "negative_guidance_base_protocol_digest_invalid")


def bind_negative_guidance_runtime_preview(*, protocol: Mapping[str, Any],
        runtime_preview: Mapping[str, Any]) -> dict[str, Any]:
    """Bind live session envelope IDs while requiring the frozen prompts unchanged."""
    validate_negative_guidance_protocol(protocol)
    _verify_pair_preview(runtime_preview,
        target_model_identity_digest=protocol[
            "target_model_identity_digest"],
        task_digest=protocol["task_digest"])
    invariant_fields = ("task_family_id", "snapshot_id", "snapshot_digest",
        "generation_budget_digest", "history_record_ids",
        "history_record_digests", "history_set_digest",
        "probe_binding_digests", "invocation_prompt_digests",
        "historical_negative_guidance_ablation", "changed_context_fields",
        "intervention")
    changed_invariants = []
    for key in invariant_fields:
        actual = ( _normalize_digest(runtime_preview.get(key),
            "negative_guidance_runtime_snapshot_digest_invalid")
            if key == "snapshot_digest" else runtime_preview.get(key))
        expected = (protocol["negative_guidance_ablation"] if key ==
            "historical_negative_guidance_ablation" else protocol.get(key))
        if actual != expected:
            changed_invariants.append(key)
    if changed_invariants:
        raise NegativeGuidanceInterventionError(
            "negative_guidance_runtime_preview_semantic_mismatch:" +
            ",".join(changed_invariants))
    owner_protocols = runtime_preview.get("owner_protocols")
    request_digests = runtime_preview.get("preview_request_digests")
    if (not isinstance(owner_protocols, Mapping)
            or set(owner_protocols) != set(ARMS)
            or not isinstance(request_digests, Mapping)
            or set(request_digests) != set(ARMS)):
        raise NegativeGuidanceInterventionError(
            "negative_guidance_runtime_preview_arm_bindings_invalid")
    runtime = {key: value for key, value in protocol.items()
        if key not in {"protocol_digest", "base_preflight_protocol_digest"}}
    runtime.update({
        "base_preflight_protocol_digest": protocol["protocol_digest"],
        "preview_request_digests": dict(request_digests),
        "owner_execution_tick_ids": {arm: owner_protocols[arm][
            "execution_tick_id"] for arm in ARMS},
        "owner_protocol_digests": {arm: owner_protocols[arm][
            "protocol_digest"] for arm in ARMS},
        "owner_task_plan_digests": {arm: owner_protocols[arm][
            "objective_task_plan_digest"] for arm in ARMS},
        "owner_pair_preview_digest": runtime_preview["pair_preview_digest"],
        "owner_prompt_pair_composition_verified": True,
        "exact_pair_verified": True,
        "runtime_condition_created": False,
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
    })
    rebound = {**runtime, "protocol_digest": digest(runtime)}
    validate_negative_guidance_protocol(rebound,
        target_model_identity_digest=protocol["target_model_identity_digest"],
        task_digest=protocol["task_digest"])
    return rebound


def derive_negative_guidance_request_bindings(*, protocol: Mapping[str, Any],
        objective_task: Any) -> dict[str, dict[str, str]]:
    """Build per-arm objective staging requests from the frozen task."""
    validate_negative_guidance_protocol(protocol)
    from sentientos.resident_developmental_cognition import objective_request_payload
    descriptor = objective_task.public_descriptor()
    if descriptor.get("task_digest") != protocol.get("task_digest"):
        raise NegativeGuidanceInterventionError(
            "negative_guidance_request_task_mismatch")
    result = {}
    for arm in ARMS:
        request_id = ("negative-guidance:" +
            protocol["protocol_digest"].removeprefix("sha256:") + ":" + arm)
        payload = objective_request_payload(request_id=request_id,
            task=objective_task)
        result[arm] = {"request_id": request_id,
            "request_digest": payload["request_digest"]}
    return result


def validate_negative_guidance_execution_protocol(*,
        protocol: Mapping[str, Any], objective_task: Any, arm: str,
        tick_id: str, accumulated_strategy_inclusion: str | None) -> dict[str, str]:
    """Return exact owner bindings for one authorized arm invocation."""
    validate_negative_guidance_protocol(protocol)
    if (arm not in ARMS or arm not in protocol["conditions"]
            or protocol["owner_execution_tick_ids"].get(arm) != tick_id
            or accumulated_strategy_inclusion != "included"
            or objective_task.public_descriptor().get("task_digest")
                != protocol["task_digest"]
            or objective_task.public_descriptor().get("task_family_id")
                != protocol["task_family_id"]):
        raise NegativeGuidanceInterventionError(
            "negative_guidance_execution_binding_invalid")
    requests = derive_negative_guidance_request_bindings(
        protocol=protocol, objective_task=objective_task)
    return {"protocol_digest": protocol["protocol_digest"],
        "arm": arm,
        "request_digest": requests[arm]["request_digest"],
        "preview_request_digest": protocol["preview_request_digests"][arm],
        "owner_protocol_digest": protocol["owner_protocol_digests"][arm],
        "owner_task_plan_digest": protocol["owner_task_plan_digests"][arm]}


def verify_negative_guidance_arm_receipt(*, protocol: Mapping[str, Any],
        arm: str, receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Bind a completed inference receipt to the frozen omitted/present prompt."""
    validate_negative_guidance_protocol(protocol)
    if arm not in ARMS or arm not in protocol["conditions"]:
        raise NegativeGuidanceInterventionError(
            "negative_guidance_receipt_arm_invalid")
    valid, reasons = validate_receipt(receipt)
    if not valid:
        raise NegativeGuidanceInterventionError(
            "negative_guidance_receipt_invalid:" + ",".join(reasons))
    request = receipt.get("request")
    effects = receipt.get("effects")
    identity = request.get("active_model_identity") if isinstance(request, Mapping) else None
    upstream = request.get("upstream_evidence") if isinstance(request, Mapping) else None
    linkage = request.get("linkage") if isinstance(request, Mapping) else None
    expected_prompt_digest = protocol["invocation_prompt_digests"][arm].removeprefix(
        "sha256:")
    expected_ablation = (protocol["negative_guidance_ablation"]
        if arm == "negative_guidance_omitted" else None)
    if (receipt.get("status") != "admitted_completed"
            or receipt.get("output_truncated") is not False
            or receipt.get("fallback_occurred") is not False
            or not isinstance(effects, Mapping)
            or effects.get("local_model_inference") is not True
            or not isinstance(request, Mapping)
            or request.get("prompt_digest") != expected_prompt_digest
            or not isinstance(request.get("request_digest"), str)
            or _DIGEST.fullmatch("sha256:" + request["request_digest"].removeprefix(
                "sha256:")) is None
            or request.get("expected_output_format") != "json"
            or not isinstance(receipt.get("generation_config"), Mapping)
            or digest(dict(receipt["generation_config"])) !=
                protocol["generation_config_digest"]
            or not isinstance(identity, Mapping)
            or digest(dict(identity)) != protocol["target_model_identity_digest"]
            or not isinstance(upstream, Mapping)
            or upstream.get("objective_task_digest") != protocol["task_digest"]
            or upstream.get("objective_task_plan_digest") !=
                protocol["owner_task_plan_digests"][arm]
            or upstream.get("historical_negative_guidance_ablation")
                != expected_ablation
            or not isinstance(linkage, Mapping)
            or linkage.get("condition_id") != "history_present"
            or linkage.get("history_present") is not True
            or linkage.get("condition_group") !=
                protocol["owner_execution_tick_ids"][arm] + ":retrieval-comparison"
            or not isinstance(request.get("budget"), Mapping)
            or digest(dict(request["budget"])) !=
                protocol["generation_budget_digest"]):
        raise NegativeGuidanceInterventionError(
            "negative_guidance_receipt_binding_mismatch:" + arm)
    if arm == "negative_guidance_omitted":
        projection = upstream.get("task_family_history_prompt_projection")
        if (not isinstance(projection, Mapping)
                or projection.get("historical_negative_guidance_ablation")
                    != expected_ablation
                or projection.get("governed_request_prompt_digest")
                    != expected_prompt_digest):
            raise NegativeGuidanceInterventionError(
                "negative_guidance_receipt_projection_mismatch")
    output = receipt.get("output_text")
    if not isinstance(output, str):
        raise NegativeGuidanceInterventionError(
            "negative_guidance_receipt_output_missing")
    try:
        decoded = json.loads(output)
    except (TypeError, json.JSONDecodeError) as exc:
        raise NegativeGuidanceInterventionError(
            "negative_guidance_receipt_output_invalid") from exc
    if not isinstance(decoded, Mapping):
        raise NegativeGuidanceInterventionError(
            "negative_guidance_receipt_output_invalid")
    return {"arm": arm, "prompt_digest": "sha256:" + expected_prompt_digest,
        "request_digest": request["request_digest"],
        "preview_request_digest": protocol["preview_request_digests"][arm],
        "request_id": request.get("request_id"),
        "output_digest": receipt.get("output_digest"),
        "response_digest": digest({"output": output}),
        "authority": False, "learning_established": False}


def build_resident_negative_guidance_arm_executor(*, owner: Any,
        snapshot: Any, objective_task: Any):
    """Adapt the resident owner to one frozen negative-guidance arm at a time."""
    if (not callable(getattr(owner, "run_objective_intervention_once", None))
            or not callable(getattr(owner, "verified_cognition_observation", None))
            or not callable(getattr(owner, "verified_cognition_invocation_receipt", None))
            or not callable(getattr(objective_task, "specification", None))
            or not callable(getattr(objective_task, "public_descriptor", None))):
        raise NegativeGuidanceInterventionError(
            "negative_guidance_executor_dependencies_invalid")
    history_store = getattr(getattr(owner, "writeback", None), "store", None)
    read_records = getattr(history_store, "records", None)
    read_receipts = getattr(history_store, "receipts", None)
    lock = getattr(owner, "_composition_lock", None)
    if not callable(read_records) or not callable(read_receipts) or not callable(lock):
        raise NegativeGuidanceInterventionError(
            "negative_guidance_executor_history_inventory_unavailable")
    baseline_inventory: dict[str, str] | None = None

    def inventory(protocol: Mapping[str, Any]) -> dict[str, Any]:
        nonlocal baseline_inventory
        with lock():
            records = read_records()
            receipts = read_receipts()
        rows = []
        record_digests: dict[str, str] = {}
        for record in records:
            record_id = getattr(record, "record_id", None)
            record_digest = getattr(record, "record_digest", None)
            _require_digest(record_digest, "negative_guidance_runtime_record_digest_invalid")
            if not isinstance(record_id, str) or record_id in record_digests:
                raise NegativeGuidanceInterventionError(
                    "negative_guidance_runtime_record_invalid")
            record_digests[record_id] = record_digest
            rows.append({"record_id": record_id, "record_digest": record_digest})
        selected_ids = protocol["history_record_ids"]
        selected_digests = protocol["history_record_digests"]
        if any(record_digests.get(record_id) != record_digest
                for record_id, record_digest in zip(
                    selected_ids, selected_digests, strict=True)):
            raise NegativeGuidanceInterventionError(
                "negative_guidance_runtime_selected_history_mismatch")
        record_set = digest(sorted(rows, key=lambda row: row["record_id"]))
        receipt_rows = []
        receipt_records: set[str] = set()
        for receipt in receipts:
            receipt_id = getattr(receipt, "receipt_id", None)
            receipt_digest = getattr(receipt, "receipt_digest", None)
            record_id = getattr(receipt, "record_id", None)
            record_digest = getattr(receipt, "record_digest", None)
            if (not isinstance(receipt_id, str) or not isinstance(record_id, str)
                    or not isinstance(receipt_digest, str)
                    or record_digests.get(record_id) != record_digest):
                raise NegativeGuidanceInterventionError(
                    "negative_guidance_runtime_receipt_binding_invalid")
            receipt_records.add(record_id)
            receipt_rows.append({"receipt_id": receipt_id,
                "receipt_digest": receipt_digest})
        if not set(selected_ids).issubset(receipt_records):
            raise NegativeGuidanceInterventionError(
                "negative_guidance_runtime_selected_receipt_missing")
        receipt_set = digest(sorted(receipt_rows,
            key=lambda row: row["receipt_id"]))
        current = {"record": record_set, "receipt": receipt_set}
        if baseline_inventory is None:
            baseline_inventory = current
        elif current != baseline_inventory:
            raise NegativeGuidanceInterventionError(
                "negative_guidance_runtime_history_mutated_during_pair")
        return {"record_count": len(rows), "record_set_digest": record_set,
            "receipt_count": len(receipt_rows), "receipt_set_digest": receipt_set}

    def execute(arm: str, protocol: Mapping[str, Any]) -> NegativeGuidanceArmExecution:
        validate_negative_guidance_protocol(protocol)
        if arm not in protocol["conditions"]:
            raise NegativeGuidanceInterventionError(
                "negative_guidance_executor_arm_invalid")
        before = inventory(protocol)
        bindings = derive_negative_guidance_request_bindings(
            protocol=protocol, objective_task=objective_task)
        tick_id = protocol["owner_execution_tick_ids"][arm]
        try:
            result = owner.run_objective_intervention_once(
                snapshot=snapshot, tick_id=tick_id, objective_task=objective_task,
                request_id=bindings[arm]["request_id"],
                request_digest=bindings[arm]["request_digest"],
                accumulated_strategy_inclusion="included",
                negative_guidance_condition=arm,
                negative_guidance_protocol=protocol)
        finally:
            after = inventory(protocol)
            if after != before:
                raise NegativeGuidanceInterventionError(
                    "negative_guidance_runtime_history_mutated_during_arm")
        observations = getattr(result, "cognition_observation_ids", ())
        if (getattr(result, "status", None) != "objective_strategy_arm_completed"
                or getattr(result, "tick_id", None) != tick_id
                or not isinstance(observations, (list, tuple))
                or len(observations) != 1 or not isinstance(observations[0], str)):
            raise NegativeGuidanceInterventionError(
                "negative_guidance_executor_result_invalid")
        observation = owner.verified_cognition_observation(observations[0])
        receipt = owner.verified_cognition_invocation_receipt(
            observations[0], observation["observation_digest"])
        if (observation.get("tick_id") != tick_id
                or observation.get("condition_id") != "history_present"
                or observation.get("request_digest") !=
                    receipt.get("request", {}).get("request_digest")):
            raise NegativeGuidanceInterventionError(
                "negative_guidance_executor_observation_invalid")
        verify_negative_guidance_arm_receipt(
            protocol=protocol, arm=arm, receipt=receipt)
        inventory_semantic = {"schema_version":
                "sentientos.negative_guidance_runtime_history_inventory:v1",
            "protocol_digest": protocol["protocol_digest"],
            "selected_history_set_digest": protocol["history_set_digest"],
            "before": before, "after": after,
            "stable_within_arm": True, "selected_records_verified": True,
            "selected_record_receipts_verified": True, "authority": False}
        runtime_inventory = {**inventory_semantic,
            "history_inventory_digest": digest(inventory_semantic)}
        return NegativeGuidanceArmExecution(receipt=dict(receipt),
            observation=dict(observation),
            runtime_history_inventory=runtime_inventory)
    return execute


def _runtime_inventory_is_valid(value: Mapping[str, Any], *,
        protocol: Mapping[str, Any]) -> bool:
    semantic = {key: item for key, item in value.items()
        if key != "history_inventory_digest"}
    return (value.get("schema_version") ==
                "sentientos.negative_guidance_runtime_history_inventory:v1"
            and value.get("protocol_digest") == protocol.get("protocol_digest")
            and value.get("selected_history_set_digest") ==
                protocol.get("history_set_digest")
            and value.get("stable_within_arm") is True
            and value.get("selected_records_verified") is True
            and value.get("selected_record_receipts_verified") is True
            and value.get("authority") is False
            and value.get("history_inventory_digest") == digest(semantic))


def _private_answer_key(*, task: Any, protocol: Mapping[str, Any]
        ) -> dict[str, int]:
    descriptor = task.public_descriptor()
    specification = task.specification()
    probes = descriptor.get("probe_inputs")
    multiplier, offset = (specification.get("multiplier"),
        specification.get("offset"))
    if (descriptor.get("task_digest") != protocol.get("task_digest")
            or not isinstance(probes, (list, tuple)) or not probes
            or type(multiplier) is not int or type(offset) is not int):
        raise NegativeGuidanceInterventionError(
            "negative_guidance_private_task_invalid")
    return {digest({"schema_version": "sentientos.objective_probe_binding:v1",
        "task_digest": descriptor["task_digest"], "probe_index": index,
        "probe_input": probe}): multiplier * probe + offset
        for index, probe in enumerate(probes)}


def score_negative_guidance_pair(*, protocol: Mapping[str, Any], task: Any,
        answer_key: Mapping[str, int],
        receipts_by_arm: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Score both receipts against the private key without claiming learning."""
    validate_negative_guidance_protocol(protocol)
    if (set(answer_key) != set(protocol["probe_binding_digests"])
            or any(type(value) is not int for value in answer_key.values())
            or digest(dict(answer_key)) != protocol["answer_key_digest"]
            or set(receipts_by_arm) != set(ARMS)):
        raise NegativeGuidanceInterventionError(
            "negative_guidance_score_inputs_invalid")
    expected_fields = {"answers"}
    specification = task.specification()
    if specification.get("schema_version") in {
            "sentientos.affine_prediction_task_family_suite:v5",
            "sentientos.affine_prediction_task_family_suite:v6"}:
        expected_fields.add("confidence_basis_points")
    outcomes: dict[str, list[dict[str, Any]]] = {}
    correct_counts = {arm: 0 for arm in ARMS}
    answered_counts = {arm: 0 for arm in ARMS}
    confidence_sums = {arm: 0 for arm in ARMS}
    confidence_counts = {arm: 0 for arm in ARMS}
    receipt_bindings: dict[str, dict[str, Any]] = {}
    for arm in ARMS:
        receipt = receipts_by_arm[arm]
        binding = verify_negative_guidance_arm_receipt(
            protocol=protocol, arm=arm, receipt=receipt)
        output = receipt.get("output_text")
        try:
            decoded = json.loads(output, parse_constant=lambda value:
                (_ for _ in ()).throw(ValueError(value)))
        except (TypeError, json.JSONDecodeError, ValueError) as exc:
            raise NegativeGuidanceInterventionError(
                "negative_guidance_score_output_invalid:" + arm) from exc
        if not isinstance(decoded, Mapping) or set(decoded) != expected_fields:
            raise NegativeGuidanceInterventionError(
                "negative_guidance_score_output_shape_invalid:" + arm)
        answers = decoded.get("answers")
        probes = protocol["probe_binding_digests"]
        if (not isinstance(answers, list) or len(answers) != len(probes)
                or any(value is not None and type(value) is not int
                    for value in answers)):
            raise NegativeGuidanceInterventionError(
                "negative_guidance_score_answers_invalid:" + arm)
        confidence = decoded.get("confidence_basis_points")
        if "confidence_basis_points" in expected_fields:
            if (not isinstance(confidence, list) or len(confidence) != len(probes)
                    or any(value is not None and (type(value) is not int
                        or not 0 <= value <= 10_000) for value in confidence)
                    or any((answer is None) != (value is None)
                        for answer, value in zip(answers, confidence, strict=True))):
                raise NegativeGuidanceInterventionError(
                    "negative_guidance_score_confidence_invalid:" + arm)
        rows = []
        for index, (probe, answer) in enumerate(zip(probes, answers, strict=True)):
            outcome = ("abstained" if answer is None else
                "correct" if answer == answer_key[probe] else "incorrect")
            correct_counts[arm] += outcome == "correct"
            answered_counts[arm] += outcome != "abstained"
            row = {"probe_binding_digest": probe, "outcome": outcome}
            rows.append(row)
            if confidence is not None and answer is not None:
                observed = confidence[index]
                error = observed - (10_000 if outcome == "correct" else 0)
                confidence_sums[arm] += error * error
                confidence_counts[arm] += 1
        outcomes[arm] = rows
        request = receipt["request"]
        receipt_bindings[arm] = {
            "receipt_id": receipt.get("receipt_id"),
            "receipt_digest": receipt.get("receipt_digest"),
            "request_id": request.get("request_id"),
            "request_digest": request.get("request_digest"),
            "preview_request_digest": binding["request_digest"],
            "prompt_digest": request.get("prompt_digest"),
            "output_digest": receipt.get("output_digest"),
        }
    paired = [{"probe_binding_digest": probe,
        ARMS[0]: outcomes[ARMS[0]][index]["outcome"],
        ARMS[1]: outcomes[ARMS[1]][index]["outcome"]}
        for index, probe in enumerate(protocol["probe_binding_digests"])]
    transitions = {"both_correct": 0, "present_only_correct": 0,
        "omitted_only_correct": 0, "neither_correct": 0}
    for row in paired:
        present_correct = row[ARMS[0]] == "correct"
        omitted_correct = row[ARMS[1]] == "correct"
        category = ("both_correct" if present_correct and omitted_correct else
            "present_only_correct" if present_correct else
            "omitted_only_correct" if omitted_correct else "neither_correct")
        transitions[category] += 1
    present_only = transitions["present_only_correct"]
    omitted_only = transitions["omitted_only_correct"]
    discordant = present_only + omitted_only
    if discordant:
        tail = sum(math.comb(discordant, index)
            for index in range(min(present_only, omitted_only) + 1))
        probability_numerator = min(2 * tail, 2 ** discordant)
        probability_denominator = 2 ** discordant
        divisor = math.gcd(probability_numerator, probability_denominator)
        probability = {"numerator": probability_numerator // divisor,
            "denominator": probability_denominator // divisor}
    else:
        probability = {"numerator": 1, "denominator": 1}
    semantic = {
        "schema_version": "sentientos.negative_guidance_intervention_score:v1",
        "protocol_digest": protocol["protocol_digest"],
        "answer_key_digest": protocol["answer_key_digest"],
        "probe_count": len(protocol["probe_binding_digests"]),
        "outcomes_by_arm": outcomes,
        "paired_probe_outcomes": paired,
        "paired_correctness_transition_counts": transitions,
        "discordant_probe_count": discordant,
        "omitted_minus_present_correct_count": omitted_only - present_only,
        "exact_two_sided_mcnemar_p_value_fraction": probability,
        "paired_test_interpretation": (
            "exact_two_sided_binomial_on_discordant_correctness_pairs;"
            "abstentions_count_as_not_correct; coverage_reported_separately"),
        "statistical_inference_claimed": False,
        "correct_counts": correct_counts,
        "answered_counts": answered_counts,
        "coverage_basis_points": {arm: answered_counts[arm] * 10_000 //
            len(protocol["probe_binding_digests"]) for arm in ARMS},
        "confidence_brier_squared_error_sums": confidence_sums,
        "confidence_scored_counts": confidence_counts,
        "invocation_receipt_bindings": receipt_bindings,
        "owner_pair_preview_digest": protocol["owner_pair_preview_digest"],
        "paired_delivery_verified": True,
        "inference_performed": True,
        "scoring_posture": "same_process_private_answer_key_and_arm_labeled_receipts",
        "independent_scorer_attested": False,
        "learning_established": False,
        "authority": False,
    }
    return {**semantic, "score_digest": digest(semantic)}


class NegativeGuidancePairJournal:
    """Append-only arm claim, receipt, score, and terminal journal."""

    def __init__(self, *, store: Any) -> None:
        if (not isinstance(getattr(store, "protocols", None), Path)
                or not isinstance(getattr(store, "runs", None), Path)
                or not callable(getattr(store, "_write_immutable", None))
                or not callable(getattr(store, "_read_json", None))):
            raise NegativeGuidanceInterventionError(
                "negative_guidance_journal_store_invalid")
        self._store = store

    @staticmethod
    def _record(value: Mapping[str, Any], code: str) -> dict[str, Any]:
        semantic = {key: item for key, item in value.items()
            if key != "journal_record_digest"}
        if value.get("journal_record_digest") != digest(semantic):
            raise NegativeGuidanceInterventionError(code)
        return semantic

    def _protocol_path(self, protocol_digest: str) -> Path:
        token = digest({"domain": "negative_guidance_pair_protocol:v1",
            "protocol_digest": protocol_digest})[7:31]
        return self._store.protocols / f"devexp-protocol-{token}.json"

    def _base_binding_path(self, base_protocol_digest: str) -> Path:
        token = digest({"domain": "negative_guidance_runtime_binding:v1",
            "base_protocol_digest": base_protocol_digest})[7:31]
        return self._store.protocols / f"devexp-protocol-binding-{token}.json"

    def _event_path(self, protocol_digest: str, arm: str,
            event: str) -> Path:
        protocol = self.load_protocol(protocol_digest)
        journal_digest = protocol.get("base_preflight_protocol_digest",
            protocol_digest)
        token = digest({"domain": "negative_guidance_pair_event:v1",
            "protocol_digest": journal_digest, "arm": arm,
            "event": event})[7:31]
        return (self._store.protocols if event == "terminal" else self._store.runs
            ) / f"devexp-run-{token}.json"

    def _publish(self, path: Path, semantic: Mapping[str, Any]) -> dict[str, Any]:
        value = {**dict(semantic), "journal_record_digest": digest(dict(semantic))}
        try:
            self._store._write_immutable(path, value)
            stored = self._store._read_json(path)
        except Exception as exc:
            raise NegativeGuidanceInterventionError(
                "negative_guidance_journal_publication_failed") from exc
        if stored != value:
            raise NegativeGuidanceInterventionError(
                "negative_guidance_journal_readback_mismatch")
        return stored

    def persist_protocol(self, protocol: Mapping[str, Any]) -> dict[str, Any]:
        validate_negative_guidance_protocol(protocol)
        base_digest = protocol.get("base_preflight_protocol_digest")
        if isinstance(base_digest, str):
            binding_semantic = {"schema_version":
                    "sentientos.negative_guidance_runtime_protocol_binding:v1",
                "base_preflight_protocol_digest": base_digest,
                "runtime_protocol_digest": protocol["protocol_digest"],
                "runtime_owner_pair_preview_digest": protocol[
                    "owner_pair_preview_digest"],
                "authority": False}
            binding_path = self._base_binding_path(base_digest)
            try:
                existing_value = self._store._read_json(binding_path)
            except FileNotFoundError:
                existing_value = None
            except Exception as exc:
                raise NegativeGuidanceInterventionError(
                    "negative_guidance_runtime_binding_read_failed") from exc
            if existing_value is not None:
                existing = self._record(existing_value,
                    "negative_guidance_runtime_binding_digest_mismatch")
                if existing != binding_semantic:
                    raise NegativeGuidanceInterventionError(
                        "negative_guidance_runtime_binding_already_frozen")
            else:
                self._publish(binding_path, binding_semantic)
        self._publish(self._protocol_path(protocol["protocol_digest"]), protocol)
        return self.load_protocol(protocol["protocol_digest"])

    def load_protocol(self, protocol_digest: str) -> dict[str, Any]:
        _require_digest(protocol_digest, "negative_guidance_protocol_digest_invalid")
        try:
            value = self._store._read_json(self._protocol_path(protocol_digest))
        except Exception as exc:
            raise NegativeGuidanceInterventionError(
                "negative_guidance_journal_protocol_missing") from exc
        semantic = self._record(value,
            "negative_guidance_journal_protocol_record_digest_mismatch")
        validate_negative_guidance_protocol(semantic)
        if semantic.get("protocol_digest") != protocol_digest:
            raise NegativeGuidanceInterventionError(
                "negative_guidance_journal_protocol_binding_mismatch")
        return semantic

    def arm_state(self, *, protocol_digest: str, arm: str) -> dict[str, Any]:
        protocol = self.load_protocol(protocol_digest)
        if arm not in protocol["conditions"]:
            raise NegativeGuidanceInterventionError(
                "negative_guidance_journal_arm_invalid")
        claim_path = self._event_path(protocol_digest, arm, "claim")
        result_path = self._event_path(protocol_digest, arm, "result")
        try:
            claim_value = self._store._read_json(claim_path)
        except FileNotFoundError:
            claim_value = None
        except Exception as exc:
            raise NegativeGuidanceInterventionError(
                "negative_guidance_journal_claim_read_failed") from exc
        if claim_value is None:
            return {"status": "not_started", "claim": None,
                "receipt": None, "runtime_history_inventory": None}
        claim = self._record(claim_value,
            "negative_guidance_journal_claim_digest_mismatch")
        if (claim.get("schema_version") !=
                "sentientos.negative_guidance_pair_arm_claim:v1"
                or claim.get("protocol_digest") != protocol_digest
                or claim.get("arm") != arm or claim.get("invoke_once") is not True
                or claim.get("authority") is not False):
            raise NegativeGuidanceInterventionError(
                "negative_guidance_journal_claim_invalid")
        try:
            result_value = self._store._read_json(result_path)
        except FileNotFoundError:
            result_value = None
        except Exception as exc:
            raise NegativeGuidanceInterventionError(
                "negative_guidance_journal_result_read_failed") from exc
        if result_value is None:
            return {"status": "claimed_without_receipt", "claim": claim,
                "receipt": None, "runtime_history_inventory": None}
        result = self._record(result_value,
            "negative_guidance_journal_result_digest_mismatch")
        receipt = result.get("receipt")
        observation = result.get("observation")
        inventory = result.get("runtime_history_inventory")
        binding = verify_negative_guidance_arm_receipt(protocol=protocol,
            arm=arm, receipt=receipt) if isinstance(receipt, Mapping) else None
        observation_semantic = ({key: value for key, value in observation.items()
            if key not in {"observation_id", "observation_digest"}}
            if isinstance(observation, Mapping) else None)
        observation_digest = (observation.get("observation_digest")
            if isinstance(observation, Mapping) else None)
        expected_tick = protocol["owner_execution_tick_ids"][arm]
        receipt_request = receipt.get("request")
        if (result.get("schema_version") !=
                "sentientos.negative_guidance_pair_arm_result:v1"
                or result.get("protocol_digest") != protocol_digest
                or result.get("arm") != arm
                or result.get("claim_digest") != claim_value.get(
                    "journal_record_digest")
                or result.get("receipt_binding") != binding
                or not isinstance(observation_semantic, Mapping)
                or observation.get("tick_id") != expected_tick
                or observation.get("condition_id") != "history_present"
                or not isinstance(receipt_request, Mapping)
                or observation.get("request_digest") !=
                    receipt_request.get("request_digest")
                or observation.get("inference_receipt_id") !=
                    receipt.get("receipt_id")
                or observation.get("inference_receipt_digest") !=
                    receipt.get("receipt_digest")
                or observation.get("output_digest") != receipt.get("output_digest")
                or not isinstance(observation_digest, str)
                or observation_digest != digest(observation_semantic)
                or observation.get("observation_id") !=
                    "devcog-" + observation_digest[7:31]
                or not isinstance(inventory, Mapping)
                or not _runtime_inventory_is_valid(inventory, protocol=protocol)
                or result.get("authority") is not False):
            raise NegativeGuidanceInterventionError(
                "negative_guidance_journal_result_invalid")
        return {"status": "completed", "claim": claim,
            "receipt": dict(receipt),
            "receipt_binding": dict(binding),
            "observation": dict(observation),
            "runtime_history_inventory": dict(inventory)}

    def claim_arm(self, *, protocol_digest: str, arm: str) -> dict[str, Any]:
        protocol = self.load_protocol(protocol_digest)
        state = self.arm_state(protocol_digest=protocol_digest, arm=arm)
        if state["status"] != "not_started":
            raise NegativeGuidanceInterventionError(
                "negative_guidance_arm_already_claimed")
        semantic = {"schema_version":
                "sentientos.negative_guidance_pair_arm_claim:v1",
            "protocol_digest": protocol_digest, "arm": arm,
            "invoke_once": True, "authority": False}
        path = self._event_path(protocol_digest, arm, "claim")
        try:
            created = self._store._write_immutable(path,
                {**semantic, "journal_record_digest": digest(semantic)})
        except Exception as exc:
            raise NegativeGuidanceInterventionError(
                "negative_guidance_arm_claim_publication_failed") from exc
        if not created:
            raise NegativeGuidanceInterventionError(
                "negative_guidance_arm_already_claimed")
        return self.arm_state(protocol_digest=protocol_digest, arm=arm)["claim"]

    def complete_arm(self, *, protocol_digest: str, arm: str,
            receipt: Mapping[str, Any], observation: Mapping[str, Any],
            runtime_history_inventory: Mapping[str, Any]
            ) -> dict[str, Any]:
        protocol = self.load_protocol(protocol_digest)
        state = self.arm_state(protocol_digest=protocol_digest, arm=arm)
        if state["status"] == "completed":
            binding = verify_negative_guidance_arm_receipt(
                protocol=protocol, arm=arm, receipt=receipt)
            if (state["receipt_binding"] != binding
                    or state["receipt"] != dict(receipt)
                    or state["observation"] != dict(observation)
                    or state["runtime_history_inventory"]
                        != dict(runtime_history_inventory)):
                raise NegativeGuidanceInterventionError(
                    "negative_guidance_journal_receipt_collision")
            return binding
        if state["status"] != "claimed_without_receipt":
            raise NegativeGuidanceInterventionError(
                "negative_guidance_arm_claim_required")
        binding = verify_negative_guidance_arm_receipt(
            protocol=protocol, arm=arm, receipt=receipt)
        observation_semantic = ({key: value for key, value in observation.items()
            if key not in {"observation_id", "observation_digest"}}
            if isinstance(observation, Mapping) else None)
        observation_digest = (observation.get("observation_digest")
            if isinstance(observation, Mapping) else None)
        receipt_request = receipt.get("request")
        if (not isinstance(observation_semantic, Mapping)
                or not isinstance(receipt_request, Mapping)
                or observation.get("tick_id") !=
                    protocol["owner_execution_tick_ids"][arm]
                or observation.get("condition_id") != "history_present"
                or observation.get("request_digest") !=
                    receipt_request.get("request_digest")
                or observation.get("inference_receipt_id") !=
                    receipt.get("receipt_id")
                or observation.get("inference_receipt_digest") !=
                    receipt.get("receipt_digest")
                or observation.get("output_digest") != receipt.get("output_digest")
                or not isinstance(observation_digest, str)
                or observation_digest != digest(observation_semantic)
                or observation.get("observation_id") !=
                    "devcog-" + observation_digest[7:31]):
            raise NegativeGuidanceInterventionError(
                "negative_guidance_owner_observation_invalid")
        if not _runtime_inventory_is_valid(runtime_history_inventory,
                protocol=protocol):
            raise NegativeGuidanceInterventionError(
                "negative_guidance_runtime_history_inventory_invalid")
        claim_path = self._event_path(protocol_digest, arm, "claim")
        claim_value = self._store._read_json(claim_path)
        semantic = {"schema_version":
                "sentientos.negative_guidance_pair_arm_result:v1",
            "protocol_digest": protocol_digest, "arm": arm,
            "claim_digest": claim_value.get("journal_record_digest"),
            "receipt_binding": binding, "receipt": dict(receipt),
            "observation": dict(observation),
            "runtime_history_inventory": dict(runtime_history_inventory),
            "authority": False}
        self._publish(self._event_path(protocol_digest, arm, "result"), semantic)
        return binding

    def _private_task_and_key(self, protocol: Mapping[str, Any]
            ) -> tuple[Any, dict[str, int]]:
        from work.historical_examples_intervention import (
            HistoricalExamplesPairJournal)
        journal = HistoricalExamplesPairJournal(store=self._store)
        task = journal.load_private_task_plan(
            task_digest=protocol["task_digest"],
            task_plan_digest=protocol["private_task_plan_digest"])
        answer_key = _private_answer_key(task=task, protocol=protocol)
        if digest(answer_key) != protocol["answer_key_digest"]:
            raise NegativeGuidanceInterventionError(
                "negative_guidance_private_answer_key_mismatch")
        return task, answer_key

    def _completed_arms(self, protocol: Mapping[str, Any]
            ) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]],
                dict[str, Mapping[str, Any]]]:
        receipts: dict[str, Mapping[str, Any]] = {}
        bindings: dict[str, Mapping[str, Any]] = {}
        inventories: dict[str, Mapping[str, Any]] = {}
        for arm in protocol["conditions"]:
            state = self.arm_state(protocol_digest=protocol["protocol_digest"],
                arm=arm)
            if state["status"] != "completed":
                raise NegativeGuidanceInterventionError(
                    "negative_guidance_pair_incomplete")
            receipts[arm] = state["receipt"]
            bindings[arm] = state["receipt_binding"]
            inventories[arm] = state["runtime_history_inventory"]
        baselines = {(value["before"]["record_set_digest"],
            value["before"]["receipt_set_digest"],
            value["after"]["record_set_digest"],
            value["after"]["receipt_set_digest"])
            for value in inventories.values()}
        if len(baselines) != 1:
            raise NegativeGuidanceInterventionError(
                "negative_guidance_pair_history_inventory_mismatch")
        return receipts, bindings, inventories

    def persist_score(self, *, protocol_digest: str,
            score: Mapping[str, Any]) -> dict[str, Any]:
        protocol = self.load_protocol(protocol_digest)
        receipts, bindings, _ = self._completed_arms(protocol)
        observations = {arm: self.arm_state(protocol_digest=protocol_digest,
            arm=arm)["observation"] for arm in protocol["conditions"]}
        task, answer_key = self._private_task_and_key(protocol)
        expected = score_negative_guidance_pair(protocol=protocol, task=task,
            answer_key=answer_key, receipts_by_arm=receipts)
        if dict(score) != expected:
            raise NegativeGuidanceInterventionError(
                "negative_guidance_pair_score_mismatch")
        semantic = {"schema_version":
                "sentientos.negative_guidance_pair_score_record:v1",
            "protocol_digest": protocol_digest,
            "receipt_bindings": bindings, "score": expected,
            "observation_digests": {arm: observations[arm]["observation_digest"]
                for arm in protocol["conditions"]},
            "authority": False}
        self._publish(self._event_path(protocol_digest, ARMS[0], "score"),
            semantic)
        return self.load_score(protocol_digest=protocol_digest)

    def load_score(self, *, protocol_digest: str) -> dict[str, Any]:
        protocol = self.load_protocol(protocol_digest)
        try:
            value = self._store._read_json(self._event_path(
                protocol_digest, ARMS[0], "score"))
        except Exception as exc:
            raise NegativeGuidanceInterventionError(
                "negative_guidance_pair_score_missing") from exc
        semantic = self._record(value,
            "negative_guidance_pair_score_record_digest_mismatch")
        receipts, bindings, _ = self._completed_arms(protocol)
        observations = {arm: self.arm_state(protocol_digest=protocol_digest,
            arm=arm)["observation"] for arm in protocol["conditions"]}
        task, answer_key = self._private_task_and_key(protocol)
        reconstructed = score_negative_guidance_pair(protocol=protocol,
            task=task, answer_key=answer_key, receipts_by_arm=receipts)
        if (semantic.get("schema_version") !=
                "sentientos.negative_guidance_pair_score_record:v1"
                or semantic.get("protocol_digest") != protocol_digest
                or semantic.get("receipt_bindings") != bindings
                or semantic.get("observation_digests") != {arm:
                    observations[arm]["observation_digest"]
                    for arm in protocol["conditions"]}
                or semantic.get("score") != reconstructed
                or semantic.get("authority") is not False):
            raise NegativeGuidanceInterventionError(
                "negative_guidance_pair_score_record_invalid")
        return reconstructed

    def persist_terminal(self, *, protocol_digest: str,
            score: Mapping[str, Any]) -> dict[str, Any]:
        protocol = self.load_protocol(protocol_digest)
        persisted_score = self.load_score(protocol_digest=protocol_digest)
        receipts, bindings, inventories = self._completed_arms(protocol)
        if dict(score) != persisted_score:
            raise NegativeGuidanceInterventionError(
                "negative_guidance_terminal_score_mismatch")
        semantic = {"schema_version":
                "sentientos.negative_guidance_pair_execution_terminal:v1",
            "protocol_digest": protocol_digest,
            "score_digest": score["score_digest"],
            "conditions": list(protocol["conditions"]),
            "receipt_binding_digests": {arm: digest(bindings[arm])
                for arm in protocol["conditions"]},
            "owner_observation_digests": {arm: self.arm_state(
                protocol_digest=protocol_digest, arm=arm)["observation"][
                    "observation_digest"] for arm in protocol["conditions"]},
            "runtime_history_inventory_digests": {arm: inventories[arm][
                "history_inventory_digest"] for arm in protocol["conditions"]},
            "outcome": "completed_scored_pair",
            "paired_delivery_verified": True,
            "inference_performed": True,
            "model_invoked": True,
            "learning_established": False,
            "improvement_established": False,
            "authority": False}
        path = self._event_path(protocol_digest, "terminal", "terminal")
        self._publish(path, semantic)
        return self.load_terminal(protocol_digest=protocol_digest)

    def load_terminal(self, *, protocol_digest: str) -> dict[str, Any]:
        protocol = self.load_protocol(protocol_digest)
        try:
            value = self._store._read_json(self._event_path(
                protocol_digest, "terminal", "terminal"))
        except Exception as exc:
            raise NegativeGuidanceInterventionError(
                "negative_guidance_pair_terminal_missing") from exc
        terminal = self._record(value,
            "negative_guidance_pair_terminal_digest_mismatch")
        score = self.load_score(protocol_digest=protocol_digest)
        receipts, bindings, inventories = self._completed_arms(protocol)
        expected = {"schema_version":
                "sentientos.negative_guidance_pair_execution_terminal:v1",
            "protocol_digest": protocol_digest,
            "score_digest": score["score_digest"],
            "conditions": list(protocol["conditions"]),
            "receipt_binding_digests": {arm: digest(bindings[arm])
                for arm in protocol["conditions"]},
            "owner_observation_digests": {arm: self.arm_state(
                protocol_digest=protocol_digest, arm=arm)["observation"][
                    "observation_digest"] for arm in protocol["conditions"]},
            "runtime_history_inventory_digests": {arm: inventories[arm][
                "history_inventory_digest"] for arm in protocol["conditions"]},
            "outcome": "completed_scored_pair",
            "paired_delivery_verified": True,
            "inference_performed": True, "model_invoked": True,
            "learning_established": False, "improvement_established": False,
            "authority": False}
        if terminal != expected:
            raise NegativeGuidanceInterventionError(
                "negative_guidance_pair_terminal_invalid")
        return terminal


def execute_negative_guidance_pair_once(*, protocol: Mapping[str, Any],
        execute_arm: Callable[[str, Mapping[str, Any]], NegativeGuidanceArmExecution],
        journal: NegativeGuidancePairJournal) -> NegativeGuidancePairJournalResult:
    """Claim, execute, receipt-verify, score, and terminalize a frozen pair."""
    validate_negative_guidance_protocol(protocol)
    if not callable(execute_arm) or not isinstance(journal,
            NegativeGuidancePairJournal):
        raise NegativeGuidanceInterventionError(
            "negative_guidance_pair_coordinator_invalid")
    persisted_protocol = journal.persist_protocol(protocol)
    for arm in persisted_protocol["conditions"]:
        state = journal.arm_state(protocol_digest=
            persisted_protocol["protocol_digest"], arm=arm)
        if state["status"] == "not_started":
            journal.claim_arm(protocol_digest=persisted_protocol[
                "protocol_digest"], arm=arm)
            execution = execute_arm(arm, persisted_protocol)
            if not isinstance(execution, NegativeGuidanceArmExecution):
                raise NegativeGuidanceInterventionError(
                    "negative_guidance_pair_arm_execution_evidence_missing")
            journal.complete_arm(protocol_digest=persisted_protocol[
                    "protocol_digest"], arm=arm,
                receipt=execution.receipt,
                observation=execution.observation,
                runtime_history_inventory=execution.runtime_history_inventory)
        elif state["status"] != "completed":
            raise NegativeGuidanceInterventionError(
                "negative_guidance_pair_claimed_without_receipt")
    receipts, _, _ = journal._completed_arms(persisted_protocol)
    task, answer_key = journal._private_task_and_key(persisted_protocol)
    score = score_negative_guidance_pair(protocol=persisted_protocol,
        task=task, answer_key=answer_key, receipts_by_arm=receipts)
    persisted_score = journal.persist_score(protocol_digest=
        persisted_protocol["protocol_digest"], score=score)
    terminal = journal.persist_terminal(protocol_digest=
        persisted_protocol["protocol_digest"], score=persisted_score)
    return NegativeGuidancePairJournalResult(
        protocol_digest=persisted_protocol["protocol_digest"],
        score=persisted_score, terminal=terminal)
