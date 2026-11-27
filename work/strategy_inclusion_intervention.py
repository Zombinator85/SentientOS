"""Prepare and score a matched accumulated-strategy prompt intervention.

This module is a CPU-only protocol and scoring primitive. It does not invoke a
model, write developmental history, or authorize actions.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from sentientos.governed_local_model_invocation import validate_receipt
from sentientos.local_model_authority import digest_payload


LEGACY_SCHEMA_VERSION = "sentientos.strategy_inclusion_intervention_protocol:v2"
PREVIOUS_SCHEMA_VERSION = "sentientos.strategy_inclusion_intervention_protocol:v3"
PRIVATE_TASK_SCHEMA_VERSION = "sentientos.strategy_inclusion_intervention_protocol:v4"
SESSION_NORMALIZED_SCHEMA_VERSION = "sentientos.strategy_inclusion_intervention_protocol:v5"
SCHEMA_VERSION = "sentientos.strategy_inclusion_intervention_protocol:v6"
SESSION_ONLY_REQUEST_DIGEST_BINDING_POSTURE = (
    "request_semantics_with_rootless_session_custody_elided:v1")
REQUEST_DIGEST_BINDING_POSTURE = (
    "request_semantics_with_rootless_session_custody_and_volatile_authority_map_digest_elided:v2")
SCORE_SCHEMA_VERSION = "sentientos.strategy_inclusion_intervention_score:v2"
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_ARMS = ("strategy_included", "strategy_omitted")
_OWNER_PREVIEW_V2 = "sentientos.objective_strategy_inclusion_prompt_pair_preview:v2"
_OWNER_PREVIEW_V3 = "sentientos.objective_strategy_inclusion_prompt_pair_preview:v3"
MAX_ARM_RECOVERY_CANDIDATES = 256


class StrategyInclusionInterventionError(ValueError):
    """Invalid pair binding or score evidence."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise StrategyInclusionInterventionError(
            "strategy_intervention_value_not_canonical_json") from exc


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _payload_digest(value: Any) -> str:
    return "sha256:" + digest_payload(value)


def canonical_strategy_invocation_request_digest(
        request_semantic_payload: Mapping[str, Any], *,
        binding_posture: str = REQUEST_DIGEST_BINDING_POSTURE) -> str:
    """Return a stable digest under an explicit custody normalization posture.

    V1 elides only per-session custody. V2 also elides the volatile authority
    map snapshot digest, retaining its stable policy digest; receipts separately
    verify the actual authority map and model identity.
    """
    if not isinstance(request_semantic_payload, Mapping):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_request_payload_invalid")
    if binding_posture not in {
            SESSION_ONLY_REQUEST_DIGEST_BINDING_POSTURE,
            REQUEST_DIGEST_BINDING_POSTURE}:
        raise StrategyInclusionInterventionError(
            "strategy_intervention_request_digest_posture_invalid")
    semantic = normalize_strategy_invocation_request_semantics(
        request_semantic_payload, binding_posture=binding_posture)
    return digest_payload(semantic)


def normalize_strategy_invocation_request_semantics(
        request_semantic_payload: Mapping[str, Any], *,
        binding_posture: str = REQUEST_DIGEST_BINDING_POSTURE) -> dict[str, Any]:
    """Return the exact request semantics covered by a declared binding posture."""
    if not isinstance(request_semantic_payload, Mapping):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_request_payload_invalid")
    if binding_posture not in {
            SESSION_ONLY_REQUEST_DIGEST_BINDING_POSTURE,
            REQUEST_DIGEST_BINDING_POSTURE}:
        raise StrategyInclusionInterventionError(
            "strategy_intervention_request_digest_posture_invalid")
    semantic = dict(request_semantic_payload)
    linkage = semantic.get("linkage")
    if isinstance(linkage, Mapping) and "rootless_experimental_session" in linkage:
        normalized_linkage = dict(linkage)
        session_binding = normalized_linkage.pop(
            "rootless_experimental_session")
        if not isinstance(session_binding, Mapping):
            raise StrategyInclusionInterventionError(
                "strategy_intervention_rootless_session_binding_invalid")
        semantic["linkage"] = normalized_linkage
    if binding_posture == REQUEST_DIGEST_BINDING_POSTURE:
        authority_digest = semantic.get("authority_map_digest")
        policy_digest = semantic.get("authority_map_policy_digest")
        if (not isinstance(authority_digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", authority_digest) is None
                or not isinstance(policy_digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", policy_digest) is None):
            raise StrategyInclusionInterventionError(
                "strategy_intervention_authority_digest_binding_invalid")
        semantic.pop("authority_map_digest")
    return semantic


def _receipt_request_semantics(request: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in request.items()
        if key not in {"request_id", "request_digest", "raw_prompt_stored",
            "ephemeral_prompt_handling"}}


def _receipt_request_matches_preview(*, request: Mapping[str, Any],
        expected_preview_digest: Any,
        request_digest_binding_posture: Any = None) -> bool:
    actual_digest = request.get("request_digest")
    request_id = request.get("request_id")
    if (not isinstance(actual_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", actual_digest) is None
            or request_id != "lmreq-" + actual_digest[:24]
            or not isinstance(expected_preview_digest, str)
            or _DIGEST.fullmatch(expected_preview_digest) is None):
        return False
    expected_raw_digest = expected_preview_digest.removeprefix("sha256:")
    if request_digest_binding_posture is None:
        return actual_digest == expected_raw_digest
    if request_digest_binding_posture not in {
            SESSION_ONLY_REQUEST_DIGEST_BINDING_POSTURE,
            REQUEST_DIGEST_BINDING_POSTURE}:
        return False
    try:
        canonical_digest = canonical_strategy_invocation_request_digest(
            _receipt_request_semantics(request),
            binding_posture=request_digest_binding_posture)
    except StrategyInclusionInterventionError:
        return False
    return canonical_digest == expected_raw_digest


def _validate_strategy_evidence_summary(value: Any, *,
        strategy_digest: str) -> None:
    fields = {
        "schema_version", "task_family_id", "history_task_family_ids",
        "supporting_distinct_input_count", "supporting_run_count",
        "independent_input_anchor_run_count", "cross_run_probe_overlap_count",
        "supporting_model_identity_count",
        "source_run_model_identity_relation_counts", "supporting_source_count",
        "comparison_unavailable_source_count", "posture",
        "performance_transfer_established", "learning_established",
        "historical_only", "current_truth", "authority", "strategy_digest",
        "relation_withheld", "supporting_answer_values_withheld"}
    if (not isinstance(value, Mapping) or set(value) != fields
            or value.get("schema_version") !=
                "sentientos.accumulated_strategy_evidence_summary:v2"
            or value.get("strategy_digest") != strategy_digest
            or not isinstance(value.get("task_family_id"), str)
            or not value["task_family_id"]
            or not isinstance(value.get("history_task_family_ids"), list)
            or not value["history_task_family_ids"]
            or any(not isinstance(item, str) or not item
                for item in value["history_task_family_ids"])
            or len(set(value["history_task_family_ids"])) !=
                len(value["history_task_family_ids"])
            or type(value.get("supporting_distinct_input_count")) is not int
            or value["supporting_distinct_input_count"] < 3
            or type(value.get("supporting_run_count")) is not int
            or value["supporting_run_count"] < 2
            or type(value.get("independent_input_anchor_run_count")) is not int
            or value["independent_input_anchor_run_count"] != 2
            or not isinstance(value.get(
                "source_run_model_identity_relation_counts"), Mapping)
            or set(value["source_run_model_identity_relation_counts"]) != {
                "same_active_model_identity", "different_active_model_identity",
                "model_identity_unbound"}
            or any(type(item) is not int or item < 0
                for item in value["source_run_model_identity_relation_counts"].values())
            or sum(value["source_run_model_identity_relation_counts"].values()) !=
                value["supporting_run_count"]
            or any(type(value.get(field)) is not int or value[field] < 0
                for field in ("cross_run_probe_overlap_count",
                    "supporting_model_identity_count", "supporting_source_count",
                    "comparison_unavailable_source_count"))
            or value["supporting_source_count"] < 2
            or value["comparison_unavailable_source_count"] >
                value["supporting_source_count"]
            or value.get("posture") !=
                "provisional_relation_fit_to_score_bound_examples_accumulated_across_runs"
            or value.get("performance_transfer_established") is not False
            or value.get("learning_established") is not False
            or value.get("historical_only") is not True
            or value.get("current_truth") is not False
            or value.get("authority") is not False
            or value.get("relation_withheld") is not True
            or value.get("supporting_answer_values_withheld") is not True):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_evidence_summary_invalid")


def _protocol_preview_binding_valid(protocol: Mapping[str, Any]) -> bool:
    schema = protocol.get("schema_version")
    preview_schema = protocol.get("owner_prompt_pair_preview_schema")
    if schema == LEGACY_SCHEMA_VERSION:
        return (preview_schema == _OWNER_PREVIEW_V2
            and "strategy_evidence_summary" not in protocol
            and "private_task_plan_digest" not in protocol
            and "answer_key_digest" not in protocol
            and "request_digest_binding_posture" not in protocol)
    if schema not in {PREVIOUS_SCHEMA_VERSION,
            PRIVATE_TASK_SCHEMA_VERSION, SESSION_NORMALIZED_SCHEMA_VERSION,
            SCHEMA_VERSION} \
            or preview_schema != _OWNER_PREVIEW_V3:
        return False
    try:
        _validate_strategy_evidence_summary(
            protocol.get("strategy_evidence_summary"),
            strategy_digest=str(protocol.get("strategy_digest")))
        if schema == PREVIOUS_SCHEMA_VERSION:
            if ("private_task_plan_digest" in protocol
                    or "answer_key_digest" in protocol
                    or "request_digest_binding_posture" in protocol):
                return False
        else:
            _require_digest(protocol.get("private_task_plan_digest"),
                "strategy_intervention_private_task_plan_digest_invalid")
            _require_digest(protocol.get("answer_key_digest"),
                "strategy_intervention_answer_key_digest_invalid")
            if schema == PRIVATE_TASK_SCHEMA_VERSION:
                if "request_digest_binding_posture" in protocol:
                    return False
            elif schema == SESSION_NORMALIZED_SCHEMA_VERSION:
                if protocol.get("request_digest_binding_posture") != \
                        SESSION_ONLY_REQUEST_DIGEST_BINDING_POSTURE:
                    return False
            elif protocol.get("request_digest_binding_posture") != \
                    REQUEST_DIGEST_BINDING_POSTURE:
                return False
    except StrategyInclusionInterventionError:
        return False
    return True


def _require_digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise StrategyInclusionInterventionError(code)
    return value


def _verify_owner_prompt_pair_preview(preview: Mapping[str, Any], *,
        target_model_identity_digest: str, task_digest: str
        ) -> tuple[str, dict[str, str], dict[str, str], list[str]]:
    """Verify an exact, pre-inference prompt pair returned by the resident owner."""
    preview_schema = preview.get("schema_version")
    if (preview_schema not in {_OWNER_PREVIEW_V2, _OWNER_PREVIEW_V3}
            or preview.get("exact_cycle_prompt_reconstructed") is not True
            or preview.get("prompt_pair_owner_composition_verified") is not True
            or preview.get("inference_performed") is not False
            or preview.get("learning_established") is not False
            or preview.get("authority") is not False
            or preview.get("task_digest") != task_digest
            or preview.get("target_model_identity_digest")
                != target_model_identity_digest
            or preview.get("changed_context_fields") != [
                "task_family_accumulated_candidate_strategy"]):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_owner_prompt_pair_invalid")
    claimed = _require_digest(preview.get("pair_preview_digest"),
        "strategy_intervention_owner_prompt_pair_digest_invalid")
    semantic = {key: value for key, value in preview.items()
        if key != "pair_preview_digest"}
    if claimed != _digest(semantic):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_owner_prompt_pair_digest_mismatch")
    request_semantics = preview.get("request_semantics_by_arm")
    if request_semantics is not None:
        request_digests = preview.get("preview_request_digests")
        if (not isinstance(request_semantics, Mapping)
                or set(request_semantics) != set(_ARMS)
                or not isinstance(request_digests, Mapping)
                or set(request_digests) != set(_ARMS)):
            raise StrategyInclusionInterventionError(
                "strategy_intervention_owner_request_semantics_invalid")
        for arm in _ARMS:
            value = request_semantics[arm]
            digest = request_digests[arm]
            if (not isinstance(value, Mapping)
                    or not isinstance(digest, str)
                    or _DIGEST.fullmatch(digest) is None
                    or canonical_strategy_invocation_request_digest(
                        value, binding_posture=REQUEST_DIGEST_BINDING_POSTURE)
                        != digest.removeprefix("sha256:")):
                raise StrategyInclusionInterventionError(
                    "strategy_intervention_owner_request_semantics_digest_mismatch")
    if preview_schema == _OWNER_PREVIEW_V3:
        _validate_strategy_evidence_summary(
            preview.get("strategy_evidence_summary"),
            strategy_digest=str(preview.get("strategy_digest")))
    elif "strategy_evidence_summary" in preview:
        raise StrategyInclusionInterventionError(
            "strategy_intervention_legacy_preview_has_unversioned_evidence")
    if (not isinstance(preview.get("task_family_id"), str)
            or not preview["task_family_id"]
            or not isinstance(preview.get("snapshot_id"), str)
            or not preview["snapshot_id"]):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_owner_prompt_pair_context_mismatch")
    for field in ("snapshot_digest", "generation_budget_digest",
            "strategy_digest", "history_set_digest", "included_context_digest",
            "omitted_context_digest"):
        _require_digest(preview.get(field),
            "strategy_intervention_owner_prompt_pair_binding_invalid")
    if preview["included_context_digest"] == preview["omitted_context_digest"]:
        raise StrategyInclusionInterventionError(
            "strategy_intervention_owner_prompt_pair_contexts_not_distinct")
    history_ids = preview.get("history_record_ids")
    history_digests = preview.get("history_record_digests")
    if (not isinstance(history_ids, list) or not history_ids
            or not isinstance(history_digests, list)
            or len(history_ids) != len(history_digests)
            or any(not isinstance(value, str) or not value or len(value) > 256
                for value in history_ids)
            or len(set(history_ids)) != len(history_ids)):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_owner_prompt_pair_history_invalid")
    for value in history_digests:
        _require_digest(value,
            "strategy_intervention_owner_prompt_pair_history_digest_invalid")
    if preview["history_set_digest"] != _digest({
            "record_ids": history_ids, "record_digests": history_digests}):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_owner_prompt_pair_history_mismatch")
    prompt_bindings = preview.get("invocation_prompt_digests")
    request_bindings = preview.get("preview_request_digests")
    if (not isinstance(prompt_bindings, Mapping)
            or set(prompt_bindings) != set(_ARMS)
            or not isinstance(request_bindings, Mapping)
            or set(request_bindings) != set(_ARMS)):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_owner_prompt_pair_request_bindings_invalid")
    normalized_prompts = {arm: _require_digest(prompt_bindings[arm],
        "strategy_intervention_owner_prompt_pair_prompt_digest_invalid")
        for arm in _ARMS}
    normalized_requests = {arm: _require_digest(request_bindings[arm],
        "strategy_intervention_owner_prompt_pair_request_digest_invalid")
        for arm in _ARMS}
    if (len(set(normalized_prompts.values())) != len(_ARMS)
            or len(set(normalized_requests.values())) != len(_ARMS)):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_owner_prompt_pair_requests_not_distinct")
    probes = preview.get("probe_binding_digests")
    if (not isinstance(probes, list) or not probes
            or len(probes) > 128 or len(set(probes)) != len(probes)):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_owner_prompt_pair_probe_bindings_invalid")
    owner_protocols = preview.get("owner_protocols")
    if (not isinstance(owner_protocols, Mapping)
            or set(owner_protocols) != set(_ARMS)
            or any(not isinstance(owner_protocols[arm], Mapping)
                or not isinstance(owner_protocols[arm].get(
                    "execution_tick_id"), str)
                or not owner_protocols[arm]["execution_tick_id"]
                or len(owner_protocols[arm]["execution_tick_id"]) > 256
                for arm in _ARMS)):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_owner_execution_ticks_invalid")
    execution_ticks: set[str] = set()
    for arm in _ARMS:
        owner = owner_protocols[arm]
        tick_id = owner["execution_tick_id"]
        protocol = owner.get("protocol")
        expected_comparison = ("strategy_arm:included" if arm ==
            "strategy_included" else "strategy_arm:omitted")
        if (not isinstance(protocol, Mapping)
                or protocol.get("schema_version") not in {
                    "sentientos.developmental_history_intervention_protocol:v14",
                    "sentientos.developmental_history_intervention_protocol:v15"}
                or protocol.get("condition_order") not in
                    (["history_present"], ("history_present",))
                or protocol.get("planned_comparisons") not in
                    ([expected_comparison], (expected_comparison,))
                or protocol.get("objective_task_digest") != task_digest
                or owner.get("protocol_id") != protocol.get("protocol_id")
                or owner.get("protocol_digest") !=
                    protocol.get("protocol_digest")
                or protocol.get("condition_order_trial_index") is not None
                or not isinstance(protocol.get("protocol_digest"), str)
                or _DIGEST.fullmatch(protocol["protocol_digest"]) is None
                or not isinstance(protocol.get("protocol_id"), str)
                or protocol["protocol_id"] != "devexp-protocol-" +
                    protocol["protocol_digest"][7:31]
                or not isinstance(owner.get("objective_task_plan_digest"), str)
                or _DIGEST.fullmatch(owner["objective_task_plan_digest"]) is None
                or tick_id in execution_ticks):
            raise StrategyInclusionInterventionError(
                "strategy_intervention_owner_protocol_binding_invalid:" + arm)
        protocol_semantic = {key: value for key, value in protocol.items()
            if key not in {"protocol_id", "protocol_digest",
                "condition_order_trial_index"}}
        # Match DevelopmentalHistoryInterventionProtocol.semantic_payload()
        # for the authority-policy versioning boundary.
        if protocol["schema_version"] == (
                "sentientos.developmental_history_intervention_protocol:v14"):
            protocol_semantic.pop("authority_map_policy_digest", None)
        else:
            protocol_semantic.pop("authority_map_digest", None)
        if protocol["protocol_digest"] != _digest(protocol_semantic):
            raise StrategyInclusionInterventionError(
                "strategy_intervention_owner_protocol_digest_mismatch:" + arm)
        execution_ticks.add(tick_id)
    for value in probes:
        _require_digest(value,
            "strategy_intervention_owner_prompt_pair_probe_digest_invalid")
    return claimed, normalized_prompts, normalized_requests, list(probes)


def prepare_strategy_inclusion_pair(*, target_model_identity_digest: str,
        task_digest: str, generation_config_digest: str,
        owner_prompt_pair_preview: Mapping[str, Any],
        private_task_plan_digest: str | None = None,
        answer_key_digest: str | None = None,
        arm_order: Sequence[str] = _ARMS) -> dict[str, Any]:
    """Freeze a receipt-checkable protocol directly from the resident preview.

    Probe identities, history references, context digests, and request digests
    come from the exact owner-built pair; callers do not reconstruct prompts.
    """
    target_model_identity_digest = _require_digest(
        target_model_identity_digest, "strategy_intervention_model_identity_invalid")
    task_digest = _require_digest(task_digest, "strategy_intervention_task_digest_invalid")
    generation_config_digest = _require_digest(
        generation_config_digest, "strategy_intervention_generation_digest_invalid")
    if ((private_task_plan_digest is None) != (answer_key_digest is None)):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_task_plan_answer_key_binding_incomplete")
    if private_task_plan_digest is not None:
        private_task_plan_digest = _require_digest(private_task_plan_digest,
            "strategy_intervention_private_task_plan_digest_invalid")
        answer_key_digest = _require_digest(answer_key_digest,
            "strategy_intervention_answer_key_digest_invalid")
    if not isinstance(owner_prompt_pair_preview, Mapping):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_owner_prompt_pair_invalid")
    (owner_prompt_pair_digest, invocation_prompt_digests,
        preview_request_digests, probe_binding_digests) = (
        _verify_owner_prompt_pair_preview(owner_prompt_pair_preview,
            target_model_identity_digest=target_model_identity_digest,
            task_digest=task_digest))
    if (not isinstance(arm_order, (list, tuple)) or tuple(arm_order) not in
            (_ARMS, tuple(reversed(_ARMS)))):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_arm_order_invalid")
    history_ids = list(owner_prompt_pair_preview["history_record_ids"])
    history_digests = list(owner_prompt_pair_preview["history_record_digests"])
    changed = ["task_family_accumulated_candidate_strategy"]
    semantic = {
        "schema_version": (
            SCHEMA_VERSION if private_task_plan_digest is not None else
            PREVIOUS_SCHEMA_VERSION if owner_prompt_pair_preview[
                "schema_version"] == _OWNER_PREVIEW_V3 else
            LEGACY_SCHEMA_VERSION),
        "conditions": list(arm_order),
        "intervention": "remove_only_top_level_accumulated_candidate_strategy",
        "changed_context_fields": changed,
        "baseline_context_digest": owner_prompt_pair_preview[
            "included_context_digest"],
        "strategy_omitted_context_digest": owner_prompt_pair_preview[
            "omitted_context_digest"],
        "baseline_context_serialization_digest": owner_prompt_pair_preview[
            "included_context_digest"],
        "strategy_omitted_context_serialization_digest": owner_prompt_pair_preview[
            "omitted_context_digest"],
        "invocation_prompt_digests": invocation_prompt_digests,
        "preview_request_digests": preview_request_digests,
        "owner_execution_tick_ids": {
            arm: owner_prompt_pair_preview["owner_protocols"][arm][
                "execution_tick_id"] for arm in _ARMS},
        "owner_prompt_pair_preview_digest": owner_prompt_pair_digest,
        "owner_prompt_pair_preview_schema": owner_prompt_pair_preview[
            "schema_version"],
        "owner_prompt_pair_composition_verified": True,
        "target_model_identity_digest": target_model_identity_digest,
        "task_digest": task_digest,
        "task_family_id": owner_prompt_pair_preview["task_family_id"],
        "snapshot_id": owner_prompt_pair_preview["snapshot_id"],
        "snapshot_digest": owner_prompt_pair_preview["snapshot_digest"],
        "generation_budget_digest": owner_prompt_pair_preview[
            "generation_budget_digest"],
        "generation_config_digest": generation_config_digest,
        "strategy_digest": owner_prompt_pair_preview["strategy_digest"],
        "history_record_ids": history_ids,
        "history_record_digests": history_digests,
        "history_set_digest": owner_prompt_pair_preview["history_set_digest"],
        "probe_binding_digests": probe_binding_digests,
        "exact_pair_verified": True,
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
    }
    if owner_prompt_pair_preview["schema_version"] == _OWNER_PREVIEW_V3:
        evidence_summary = dict(owner_prompt_pair_preview[
            "strategy_evidence_summary"])
        _validate_strategy_evidence_summary(evidence_summary,
            strategy_digest=owner_prompt_pair_preview["strategy_digest"])
        semantic["strategy_evidence_summary"] = evidence_summary
    if private_task_plan_digest is not None:
        semantic["private_task_plan_digest"] = private_task_plan_digest
        semantic["answer_key_digest"] = answer_key_digest
        semantic["request_digest_binding_posture"] = (
            REQUEST_DIGEST_BINDING_POSTURE)
    protocol_digest = _digest(semantic)
    protocol = {**semantic, "protocol_digest": protocol_digest}
    return {"protocol": protocol}

def validate_strategy_inclusion_protocol(*, protocol: Mapping[str, Any],
        target_model_identity_digest: str | None = None,
        task_digest: str | None = None) -> None:
    """Validate the frozen pair bindings without requiring answers or scoring."""
    if (not isinstance(protocol, Mapping)
            or protocol.get("schema_version") not in {
                LEGACY_SCHEMA_VERSION, PREVIOUS_SCHEMA_VERSION,
                PRIVATE_TASK_SCHEMA_VERSION, SESSION_NORMALIZED_SCHEMA_VERSION,
                SCHEMA_VERSION}
            or protocol.get("conditions") not in (list(_ARMS), list(reversed(_ARMS)))
            or protocol.get("intervention") !=
                "remove_only_top_level_accumulated_candidate_strategy"
            or protocol.get("changed_context_fields") !=
                ["task_family_accumulated_candidate_strategy"]
            or protocol.get("exact_pair_verified") is not True
            or protocol.get("inference_performed") is not False
            or protocol.get("learning_established") is not False
            or protocol.get("authority") is not False
            or not _protocol_preview_binding_valid(protocol)
            or protocol.get("owner_prompt_pair_composition_verified") is not True):
        raise StrategyInclusionInterventionError("strategy_intervention_protocol_invalid")
    semantic = {key: value for key, value in protocol.items()
        if key != "protocol_digest"}
    protocol_digest = _require_digest(protocol.get("protocol_digest"),
        "strategy_intervention_protocol_digest_invalid")
    if protocol_digest != _digest(semantic):
        raise StrategyInclusionInterventionError("strategy_intervention_protocol_digest_mismatch")
    probes = protocol.get("probe_binding_digests")
    for field in ("baseline_context_digest", "strategy_omitted_context_digest",
            "baseline_context_serialization_digest",
            "strategy_omitted_context_serialization_digest",
            "target_model_identity_digest", "task_digest",
            "generation_config_digest", "generation_budget_digest",
            "strategy_digest", "history_set_digest", "snapshot_digest",
            "owner_prompt_pair_preview_digest"):
        _require_digest(protocol.get(field),
            "strategy_intervention_protocol_binding_invalid")
    if ((target_model_identity_digest is not None
            and protocol.get("target_model_identity_digest")
                != target_model_identity_digest)
            or (task_digest is not None
                and protocol.get("task_digest") != task_digest)):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_protocol_expected_binding_mismatch")
    if (not isinstance(protocol.get("task_family_id"), str)
            or not protocol["task_family_id"]
            or not isinstance(protocol.get("snapshot_id"), str)
            or not protocol["snapshot_id"]):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_protocol_context_invalid")
    if (protocol.get("baseline_context_digest") !=
            protocol.get("baseline_context_serialization_digest")
            or protocol.get("strategy_omitted_context_digest") !=
                protocol.get("strategy_omitted_context_serialization_digest")):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_context_digest_binding_invalid")
    invocation_prompt_digests = protocol.get("invocation_prompt_digests")
    preview_request_digests = protocol.get("preview_request_digests")
    if (not isinstance(invocation_prompt_digests, Mapping)
            or set(invocation_prompt_digests) != set(_ARMS)
            or any(not isinstance(value, str) or _DIGEST.fullmatch(value) is None
                for value in invocation_prompt_digests.values())
            or len(set(invocation_prompt_digests.values())) != len(_ARMS)
            or not isinstance(preview_request_digests, Mapping)
            or set(preview_request_digests) != set(_ARMS)
            or any(not isinstance(value, str) or _DIGEST.fullmatch(value) is None
                for value in preview_request_digests.values())
            or len(set(preview_request_digests.values())) != len(_ARMS)):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_invocation_requests_invalid")
    if (not isinstance(probes, list) or not probes
            or any(not isinstance(value, str) or _DIGEST.fullmatch(value) is None
                for value in probes)
            or len(set(probes)) != len(probes)
            or not isinstance(protocol.get("history_record_ids"), list)
            or not isinstance(protocol.get("history_record_digests"), list)
            or len(protocol["history_record_ids"]) != len(
                protocol["history_record_digests"])
            or any(not isinstance(value, str) or not value or len(value) > 256
                for value in protocol["history_record_ids"])
            or len(set(protocol["history_record_ids"])) != len(
                protocol["history_record_ids"])
            or any(not isinstance(value, str) or _DIGEST.fullmatch(value) is None
                for value in protocol["history_record_digests"])
            or protocol["history_set_digest"] != _digest({
                "record_ids": protocol["history_record_ids"],
                "record_digests": protocol["history_record_digests"]})):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_protocol_binding_invalid")
    if (not isinstance(protocol.get("owner_execution_tick_ids"), Mapping)
            or set(protocol["owner_execution_tick_ids"]) != set(_ARMS)
            or len(set(protocol["owner_execution_tick_ids"].values())) != len(_ARMS)
            or any(not isinstance(value, str) or not value or len(value) > 256
                for value in protocol["owner_execution_tick_ids"].values())):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_owner_execution_ticks_invalid")


def score_strategy_inclusion_pair(*, protocol: Mapping[str, Any],
        answer_key: Mapping[str, int],
        predictions: Mapping[str, Mapping[str, int | None]],
        confidence_basis_points: Mapping[str, Mapping[str, int]] | None = None
        ) -> dict[str, Any]:
    """Score both arms against one hidden deterministic answer key.

    Raw answer-key values and model predictions are not returned. Confidence is
    optional; when supplied it uses integer basis points in [0, 10000].
    """
    validate_strategy_inclusion_protocol(protocol=protocol)
    protocol_digest = protocol["protocol_digest"]
    probes = protocol["probe_binding_digests"]
    if (not isinstance(answer_key, Mapping)
            or set(answer_key) != set(probes or ())
            or any(type(value) is not int for value in answer_key.values())):
        raise StrategyInclusionInterventionError("strategy_intervention_answer_key_invalid")
    if (protocol.get("schema_version") in {
            PRIVATE_TASK_SCHEMA_VERSION, SESSION_NORMALIZED_SCHEMA_VERSION,
            SCHEMA_VERSION}
            and _digest(dict(answer_key)) != protocol.get("answer_key_digest")):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_answer_key_digest_mismatch")
    if not isinstance(predictions, Mapping) or set(predictions) != set(_ARMS):
        raise StrategyInclusionInterventionError("strategy_intervention_predictions_invalid")
    if confidence_basis_points is not None and (
            not isinstance(confidence_basis_points, Mapping)
            or set(confidence_basis_points) - set(_ARMS)):
        raise StrategyInclusionInterventionError("strategy_intervention_confidence_invalid")

    outcome_rows: dict[str, list[dict[str, Any]]] = {}
    correct_counts: dict[str, int] = {}
    confidence_sums: dict[str, int] = {}
    confidence_counts: dict[str, int] = {}
    for arm in _ARMS:
        arm_predictions = predictions[arm]
        if (not isinstance(arm_predictions, Mapping)
                or set(arm_predictions) != set(probes)
                or any(value is not None and type(value) is not int
                    for value in arm_predictions.values())):
            raise StrategyInclusionInterventionError("strategy_intervention_arm_answers_invalid")
        arm_confidence = ((confidence_basis_points or {}).get(arm, {}))
        if (not isinstance(arm_confidence, Mapping)
                or set(arm_confidence) - set(probes)
                or any(type(value) is not int or not 0 <= value <= 10000
                    for value in arm_confidence.values())):
            raise StrategyInclusionInterventionError("strategy_intervention_confidence_invalid")
        rows: list[dict[str, Any]] = []
        confidence_sum = 0
        for probe in probes:
            prediction = arm_predictions[probe]
            correct = prediction is not None and prediction == answer_key[probe]
            row: dict[str, Any] = {"probe_binding_digest": probe,
                "outcome": ("abstained" if prediction is None else
                    "correct" if correct else "incorrect")}
            if probe in arm_confidence:
                if prediction is None:
                    raise StrategyInclusionInterventionError(
                        "strategy_intervention_abstention_confidence_invalid")
                confidence = arm_confidence[probe]
                target = 10000 if correct else 0
                confidence_sum += (confidence - target) ** 2
                row["brier_squared_error_basis_points_squared"] = (
                    confidence - target) ** 2
            rows.append(row)
        outcome_rows[arm] = rows
        correct_counts[arm] = sum(row["outcome"] == "correct" for row in rows)
        confidence_sums[arm] = confidence_sum
        confidence_counts[arm] = len(arm_confidence)

    paired = [{"probe_binding_digest": probe,
        "strategy_included": outcome_rows["strategy_included"][index]["outcome"],
        "strategy_omitted": outcome_rows["strategy_omitted"][index]["outcome"]}
        for index, probe in enumerate(probes)]
    score_semantic = {
        "schema_version": SCORE_SCHEMA_VERSION,
        "protocol_digest": protocol_digest,
        "answer_key_digest": _digest(dict(answer_key)),
        "probe_count": len(probes),
        "outcomes_by_arm": outcome_rows,
        "paired_probe_outcomes": paired,
        "correct_counts": correct_counts,
        "answered_counts": {arm: sum(row["outcome"] != "abstained"
            for row in rows) for arm, rows in outcome_rows.items()},
        "abstained_counts": {arm: sum(row["outcome"] == "abstained"
            for row in rows) for arm, rows in outcome_rows.items()},
        "selective_accuracy_basis_points": {arm: (
            correct_counts[arm] * 10000 // sum(row["outcome"] != "abstained"
                for row in rows) if any(row["outcome"] != "abstained"
                    for row in rows) else None)
            for arm, rows in outcome_rows.items()},
        "coverage_basis_points": {arm: (sum(row["outcome"] != "abstained"
            for row in rows) * 10000) // len(probes) for arm, rows in outcome_rows.items()},
        "confidence_brier_squared_error_sums": confidence_sums,
        "confidence_scored_counts": confidence_counts,
        "inference_performed": True,
        "learning_established": False,
        "authority": False,
    }
    return {**score_semantic, "score_digest": _digest(score_semantic)}


def _normalize_output_values(value: Any, probes: Sequence[str], *,
        field: str, allow_null: bool, require_all: bool = True
        ) -> dict[str, int | None]:
    if isinstance(value, Mapping):
        if ((set(value) != set(probes) if require_all else
                    bool(set(value) - set(probes)))
                or any(item is not None and type(item) is not int
                    for item in value.values())
                or (not allow_null and any(item is None for item in value.values()))):
            raise StrategyInclusionInterventionError(
                "strategy_intervention_output_" + field + "_invalid")
        return dict(value)
    if isinstance(value, list) and len(value) == len(probes):
        if (any(item is not None and type(item) is not int for item in value)
                or (not allow_null and any(item is None for item in value))):
            raise StrategyInclusionInterventionError(
                "strategy_intervention_output_" + field + "_invalid")
        return dict(zip(probes, value))
    raise StrategyInclusionInterventionError(
        "strategy_intervention_output_" + field + "_invalid")


def _objective_output_contract(schema: Any, probe_count: int
        ) -> tuple[bool, bool]:
    """Read the receipt-bound ordered answer schema, including abstention rules."""
    if (not isinstance(schema, Mapping) or schema.get("type") != "object"
            or schema.get("additionalProperties") is not False
            or not isinstance(schema.get("properties"), Mapping)
            or not isinstance(schema.get("required"), list)):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_receipt_output_schema_invalid")
    properties = schema["properties"]
    required = schema["required"]
    if ("answers" not in required or set(properties) not in ({"answers"},
            {"answers", "confidence_basis_points"})
            or set(required) != set(properties)
            or len(required) != len(set(required))):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_receipt_output_schema_invalid")
    answers = properties.get("answers")
    if (not isinstance(answers, Mapping) or answers.get("type") != "array"
            or answers.get("minItems") != probe_count
            or answers.get("maxItems") != probe_count):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_receipt_answer_schema_invalid")
    answer_items = answers.get("items")
    answer_types = ({item.get("type") for item in answer_items.get("anyOf", ())
        if isinstance(item, Mapping)} if isinstance(answer_items, Mapping)
        and isinstance(answer_items.get("anyOf"), list) else
        {answer_items.get("type")} if isinstance(answer_items, Mapping) else set())
    if "integer" not in answer_types or answer_types - {"integer", "null"}:
        raise StrategyInclusionInterventionError(
            "strategy_intervention_receipt_answer_schema_invalid")
    allow_abstention = "null" in answer_types
    include_confidence = "confidence_basis_points" in properties
    if include_confidence:
        confidence = properties["confidence_basis_points"]
        if ("confidence_basis_points" not in required
                or not isinstance(confidence, Mapping)
                or confidence.get("type") != "array"
                or confidence.get("minItems") != probe_count
                or confidence.get("maxItems") != probe_count):
            raise StrategyInclusionInterventionError(
                "strategy_intervention_receipt_confidence_schema_invalid")
        confidence_items = confidence.get("items")
        confidence_types = ({item.get("type") for item in
            confidence_items.get("anyOf", ()) if isinstance(item, Mapping)}
            if isinstance(confidence_items, Mapping)
            and isinstance(confidence_items.get("anyOf"), list) else
            {confidence_items.get("type")} if isinstance(confidence_items, Mapping)
            else set())
        integer_confidence_schemas = [item for item in
            confidence_items.get("anyOf", ()) if isinstance(item, Mapping)
            and item.get("type") == "integer"] if isinstance(
                confidence_items, Mapping) else []
        if ("integer" not in confidence_types
                or confidence_types - {"integer", "null"}
                or len(integer_confidence_schemas) != 1
                or integer_confidence_schemas[0].get("minimum") != 0
                or integer_confidence_schemas[0].get("maximum") != 10000):
            raise StrategyInclusionInterventionError(
                "strategy_intervention_receipt_confidence_schema_invalid")
    return allow_abstention, include_confidence


def score_verified_strategy_inclusion_pair(*, protocol: Mapping[str, Any],
        answer_key: Mapping[str, int],
        invocation_receipts_by_arm: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Verify delivered paired calls, parse their bound outputs, and score them.

    Receipts must include output text in the documented JSON answer format.
    This establishes receipt-bound behavior for this task, not durable learning.
    """
    if (not isinstance(invocation_receipts_by_arm, Mapping)
            or set(invocation_receipts_by_arm) != set(_ARMS)):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_receipts_invalid")
    # Validate the protocol before using any of its arm bindings.
    if not isinstance(protocol, Mapping):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_protocol_invalid")
    prompt_bindings = protocol.get("invocation_prompt_digests")
    request_bindings = protocol.get("preview_request_digests")
    probes = protocol.get("probe_binding_digests")
    if (protocol.get("schema_version") not in {
                LEGACY_SCHEMA_VERSION, PREVIOUS_SCHEMA_VERSION,
                PRIVATE_TASK_SCHEMA_VERSION, SESSION_NORMALIZED_SCHEMA_VERSION,
                SCHEMA_VERSION}
            or protocol.get("conditions") not in (list(_ARMS),
                list(reversed(_ARMS)))
            or protocol.get("exact_pair_verified") is not True
            or protocol.get("inference_performed") is not False
            or protocol.get("learning_established") is not False
            or protocol.get("authority") is not False
            or not _protocol_preview_binding_valid(protocol)
            or protocol.get("owner_prompt_pair_composition_verified") is not True
            or not isinstance(prompt_bindings, Mapping)
            or set(prompt_bindings) != set(_ARMS)
            or len(set(prompt_bindings.values())) != len(_ARMS)
            or any(not isinstance(value, str) or _DIGEST.fullmatch(value) is None
                for value in prompt_bindings.values())
            or not isinstance(request_bindings, Mapping)
            or set(request_bindings) != set(_ARMS)
            or len(set(request_bindings.values())) != len(_ARMS)
            or not isinstance(protocol.get("owner_execution_tick_ids"), Mapping)
            or set(protocol["owner_execution_tick_ids"]) != set(_ARMS)
            or any(not isinstance(value, str) or not value or len(value) > 256
                for value in protocol["owner_execution_tick_ids"].values())
            or len(set(protocol["owner_execution_tick_ids"].values())) != len(_ARMS)
            or any(not isinstance(value, str) or _DIGEST.fullmatch(value) is None
                for value in request_bindings.values())
            or not isinstance(probes, list) or not probes
            or any(not isinstance(value, str) or _DIGEST.fullmatch(value) is None
                for value in probes)
            or len(set(probes)) != len(probes)):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_protocol_invalid")
    for field in ("target_model_identity_digest", "task_digest",
            "generation_config_digest", "generation_budget_digest",
            "snapshot_digest", "strategy_digest",
            "owner_prompt_pair_preview_digest"):
        _require_digest(protocol.get(field),
            "strategy_intervention_protocol_binding_invalid")
    protocol_digest = _require_digest(protocol.get("protocol_digest"),
        "strategy_intervention_protocol_digest_invalid")
    semantic_protocol = {key: value for key, value in protocol.items()
        if key != "protocol_digest"}
    if protocol_digest != _digest(semantic_protocol):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_protocol_digest_mismatch")

    predictions: dict[str, dict[str, int | None]] = {}
    confidence: dict[str, dict[str, int]] = {}
    receipt_bindings: dict[str, dict[str, Any]] = {}
    for arm in _ARMS:
        receipt = invocation_receipts_by_arm[arm]
        if not isinstance(receipt, Mapping):
            raise StrategyInclusionInterventionError(
                "strategy_intervention_receipt_invalid")
        valid, reasons = validate_receipt(receipt)
        if not valid:
            raise StrategyInclusionInterventionError(
                "strategy_intervention_receipt_invalid:" + ",".join(reasons))
        request = receipt.get("request")
        effects = receipt.get("effects")
        identity = request.get("active_model_identity") if isinstance(
            request, Mapping) else None
        upstream = request.get("upstream_evidence") if isinstance(
            request, Mapping) else None
        if (receipt.get("status") != "admitted_completed"
                or receipt.get("output_truncated") is not False
                or receipt.get("fallback_occurred") is not False
                or not isinstance(effects, Mapping)
                or effects.get("local_model_inference") is not True
                or not isinstance(request, Mapping)
                or request.get("prompt_digest") != prompt_bindings[
                    arm].removeprefix("sha256:")
                or not _receipt_request_matches_preview(request=request,
                    expected_preview_digest=request_bindings[arm],
                    request_digest_binding_posture=protocol.get(
                        "request_digest_binding_posture"))
                or not isinstance(identity, Mapping)
                or _payload_digest(dict(identity)) != protocol[
                    "target_model_identity_digest"]
                or not isinstance(upstream, Mapping)
                or upstream.get("objective_task_digest") != protocol["task_digest"]
                or not isinstance(receipt.get("generation_config"), Mapping)
                or _payload_digest(dict(receipt["generation_config"]))
                    != protocol["generation_config_digest"]
                or not isinstance(receipt.get("output_text"), str)
                or receipt.get("output_digest") is None):
            raise StrategyInclusionInterventionError(
                "strategy_intervention_receipt_binding_mismatch:" + arm)
        try:
            decoded = json.loads(receipt["output_text"])
        except (json.JSONDecodeError, TypeError) as exc:
            raise StrategyInclusionInterventionError(
                "strategy_intervention_output_format_invalid:" + arm) from exc
        if not isinstance(decoded, Mapping):
            raise StrategyInclusionInterventionError(
                "strategy_intervention_output_answers_invalid:" + arm)
        allow_abstention, include_confidence = _objective_output_contract(
            request.get("structured_output_schema"), len(probes))
        expected_fields = ({"answers", "confidence_basis_points"}
            if include_confidence else {"answers"})
        if set(decoded) != expected_fields:
            raise StrategyInclusionInterventionError(
                "strategy_intervention_output_schema_mismatch:" + arm)
        predictions[arm] = _normalize_output_values(decoded["answers"], probes,
            field="answers", allow_null=allow_abstention)
        if include_confidence:
            confidence_values = _normalize_output_values(
                decoded["confidence_basis_points"], probes,
                field="confidence", allow_null=True)
            if (any(value is not None and not 0 <= value <= 10000
                    for value in confidence_values.values())
                    or any((predictions[arm][probe] is None)
                        != (confidence_values[probe] is None)
                        for probe in probes)):
                raise StrategyInclusionInterventionError(
                    "strategy_intervention_output_confidence_invalid:" + arm)
            confidence[arm] = {probe: value for probe, value
                in confidence_values.items() if value is not None}
        receipt_bindings[arm] = {
            "receipt_id": receipt.get("receipt_id"),
            "receipt_digest": receipt.get("receipt_digest"),
            "request_id": request.get("request_id"),
            "request_digest": request.get("request_digest"),
            "preview_request_digest": request_bindings[arm],
            "output_digest": receipt.get("output_digest"),
            "prompt_digest": request.get("prompt_digest"),
        }

    score = score_strategy_inclusion_pair(protocol=protocol,
        answer_key=answer_key, predictions=predictions,
        confidence_basis_points=confidence or None)
    semantic_score = {key: value for key, value in score.items()
        if key != "score_digest"}
    semantic_score["invocation_receipt_bindings"] = receipt_bindings
    semantic_score["owner_prompt_pair_preview_digest"] = protocol[
        "owner_prompt_pair_preview_digest"]
    semantic_score["owner_prompt_pair_composition_verified"] = protocol[
        "owner_prompt_pair_composition_verified"]
    semantic_score["exact_cycle_prompt_reconstructed"] = True
    semantic_score["paired_delivery_verified"] = True
    semantic_score["learning_established"] = False
    return {**semantic_score, "score_digest": _digest(semantic_score)}


def verify_strategy_inclusion_arm_receipt(*, protocol: Mapping[str, Any],
        arm: str, receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one completed arm against its preregistered prompt and task."""
    if (not isinstance(protocol, Mapping) or arm not in _ARMS
            or arm not in protocol.get("conditions", ())
            or not isinstance(receipt, Mapping)):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_arm_receipt_binding_invalid")
    valid, reasons = validate_receipt(receipt)
    if not valid:
        raise StrategyInclusionInterventionError(
            "strategy_intervention_receipt_invalid:" + ",".join(reasons))
    request = receipt.get("request")
    effects = receipt.get("effects")
    identity = request.get("active_model_identity") if isinstance(
        request, Mapping) else None
    upstream = request.get("upstream_evidence") if isinstance(
        request, Mapping) else None
    prompt_bindings = protocol.get("invocation_prompt_digests")
    preview_bindings = protocol.get("preview_request_digests")
    probes = protocol.get("probe_binding_digests")
    expected_request_digest = _require_digest(
        preview_bindings.get(arm) if isinstance(preview_bindings, Mapping)
            else None,
        "strategy_intervention_preview_request_digest_invalid:" + arm)
    if (receipt.get("status") != "admitted_completed"
            or receipt.get("output_truncated") is not False
            or receipt.get("fallback_occurred") is not False
            or not isinstance(effects, Mapping)
            or effects.get("local_model_inference") is not True
            or not isinstance(request, Mapping)
            or not isinstance(prompt_bindings, Mapping)
            or request.get("prompt_digest") != prompt_bindings.get(arm, "").removeprefix("sha256:")
            or not _receipt_request_matches_preview(request=request,
                expected_preview_digest=expected_request_digest,
                request_digest_binding_posture=protocol.get(
                    "request_digest_binding_posture"))
            or not isinstance(identity, Mapping)
            or _payload_digest(dict(identity)) !=
                protocol.get("target_model_identity_digest")
            or not isinstance(upstream, Mapping)
            or upstream.get("objective_task_digest") != protocol.get("task_digest")
            or not isinstance(receipt.get("generation_config"), Mapping)
            or _payload_digest(dict(receipt["generation_config"])) !=
                protocol.get("generation_config_digest")
            or not isinstance(receipt.get("output_text"), str)
            or not isinstance(receipt.get("output_digest"), str)
            or not isinstance(preview_bindings, Mapping)
            or not isinstance(probes, list) or not probes):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_receipt_binding_mismatch:" + arm)
    try:
        decoded = json.loads(receipt["output_text"])
    except (json.JSONDecodeError, TypeError) as exc:
        raise StrategyInclusionInterventionError(
            "strategy_intervention_output_format_invalid:" + arm) from exc
    if not isinstance(decoded, Mapping):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_output_answers_invalid:" + arm)
    allow_abstention, include_confidence = _objective_output_contract(
        request.get("structured_output_schema"), len(probes))
    expected_fields = ({"answers", "confidence_basis_points"}
        if include_confidence else {"answers"})
    if set(decoded) != expected_fields:
        raise StrategyInclusionInterventionError(
            "strategy_intervention_output_schema_mismatch:" + arm)
    answers = _normalize_output_values(decoded["answers"], probes,
        field="answers", allow_null=allow_abstention)
    if include_confidence:
        confidence = _normalize_output_values(decoded[
            "confidence_basis_points"], probes, field="confidence",
            allow_null=True)
        if (any(value is not None and not 0 <= value <= 10000
                    for value in confidence.values())
                or any((answers[probe] is None) !=
                    (confidence[probe] is None) for probe in probes)):
            raise StrategyInclusionInterventionError(
                "strategy_intervention_output_confidence_invalid:" + arm)
    return {
        "receipt_id": receipt.get("receipt_id"),
        "receipt_digest": receipt.get("receipt_digest"),
        "request_id": request.get("request_id"),
        "request_digest": request.get("request_digest"),
        "preview_request_digest": preview_bindings.get(arm),
        "output_digest": receipt.get("output_digest"),
        "prompt_digest": request.get("prompt_digest"),
    }


def build_strategy_inclusion_receipt_recovery_callback(
        receipt_reader: Any) -> Callable[[str, Mapping[str, Any]],
            Sequence[Mapping[str, Any]]]:
    """Adapt the resident read-only receipt reader for interrupted-arm recovery."""
    discover = getattr(receipt_reader,
        "find_persisted_invocation_receipt_candidates", None)
    if not callable(discover):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_receipt_discovery_unavailable")

    def recover(arm: str, protocol: Mapping[str, Any]
            ) -> Sequence[Mapping[str, Any]]:
        def matches(receipt: Mapping[str, Any]) -> bool:
            try:
                verify_strategy_inclusion_arm_receipt(
                    protocol=protocol, arm=arm, receipt=receipt)
            except StrategyInclusionInterventionError:
                return False
            return True
        return discover(matches, max_entries=MAX_ARM_RECOVERY_CANDIDATES)

    return recover


def build_resident_strategy_inclusion_arm_executor(*, owner: Any,
        snapshot: Any, objective_task: Any,
        request_ids_by_arm: Mapping[str, str],
        request_digests_by_arm: Mapping[str, str],
        request_semantics_by_arm: Mapping[str, Mapping[str, Any]]
        ) -> Callable[[str, Mapping[str, Any]], Mapping[str, Any]]:
    """Adapt a resident owner to the paired coordinator's one-call arm API.

    The callback uses the tick ID frozen by the CPU prompt preview, then
    reopens the resulting observation and its governed invocation receipt
    through the owner's verification path. It does not write model output to
    developmental history or expose an unverified in-memory receipt.
    """
    if (not callable(getattr(owner, "run_objective_intervention_once", None))
            or not callable(getattr(owner, "verified_cognition_observation", None))
            or not callable(getattr(owner,
                "verified_cognition_invocation_receipt", None))
            or not callable(getattr(objective_task, "specification", None))
            or not callable(getattr(objective_task, "public_descriptor", None))
            or not isinstance(request_ids_by_arm, Mapping)
            or set(request_ids_by_arm) != set(_ARMS)
            or any(not isinstance(value, str) or not value
                for value in request_ids_by_arm.values())
            or not isinstance(request_digests_by_arm, Mapping)
            or set(request_digests_by_arm) != set(_ARMS)
            or any(not isinstance(value, str) or not value
                for value in request_digests_by_arm.values())
            or not isinstance(request_semantics_by_arm, Mapping)
            or set(request_semantics_by_arm) != set(_ARMS)
            or any(not isinstance(value, Mapping)
                for value in request_semantics_by_arm.values())):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_resident_executor_dependencies_invalid")

    def execute(arm: str, protocol: Mapping[str, Any]
            ) -> Mapping[str, Any]:
        if arm not in _ARMS or not isinstance(protocol, Mapping):
            raise StrategyInclusionInterventionError(
                "strategy_intervention_resident_executor_arm_invalid")
        tick_ids = protocol.get("owner_execution_tick_ids")
        if not isinstance(tick_ids, Mapping) or set(tick_ids) != set(_ARMS):
            raise StrategyInclusionInterventionError(
                "strategy_intervention_resident_executor_tick_binding_invalid")
        result = owner.run_objective_intervention_once(
            snapshot=snapshot, tick_id=str(tick_ids[arm]),
            objective_task=objective_task,
            request_id=request_ids_by_arm[arm],
            request_digest=request_digests_by_arm[arm],
            expected_strategy_request_semantic_payload=(
                request_semantics_by_arm[arm]),
            accumulated_strategy_inclusion=(
                "included" if arm == "strategy_included" else "omitted"),
            strategy_pair_protocol=protocol)
        observation_ids = getattr(result, "cognition_observation_ids", ())
        if (getattr(result, "status", None)
                != "objective_strategy_arm_completed"
                or getattr(result, "tick_id", None) != tick_ids[arm]
                or not isinstance(observation_ids, (list, tuple))
                or len(observation_ids) != 1
                or not isinstance(observation_ids[0], str)):
            raise StrategyInclusionInterventionError(
                "strategy_intervention_resident_executor_result_invalid")
        observation = owner.verified_cognition_observation(observation_ids[0])
        if (observation.get("tick_id") != tick_ids[arm]
                or observation.get("condition_id") != "history_present"
                or observation.get("observation_id") != observation_ids[0]
                or not isinstance(observation.get("observation_digest"), str)):
            raise StrategyInclusionInterventionError(
                "strategy_intervention_resident_executor_observation_invalid")
        receipt = owner.verified_cognition_invocation_receipt(
            observation_ids[0], observation["observation_digest"])
        if not isinstance(receipt, Mapping):
            raise StrategyInclusionInterventionError(
                "strategy_intervention_resident_executor_receipt_invalid")
        return dict(receipt)

    return execute


def execute_and_persist_strategy_inclusion_pair(*, store: Any,
        protocol: Mapping[str, Any], answer_key: Mapping[str, int],
        execute_arm: Callable[[str, Mapping[str, Any]], Mapping[str, Any]],
        load_receipt: Callable[[str, str], Mapping[str, Any]] | None = None,
        recover_claimed_arm: Callable[[str, Mapping[str, Any]], Sequence[
            Mapping[str, Any]]] | None = None
        ) -> dict[str, Any]:
    """Run the frozen arms through a caller-owned owner path and persist score.

    The pair protocol is durably stored before the first callback. Calls are
    sequential in the preregistered arm order, and each callback receives only
    its arm and the frozen protocol. A failed callback stops the pair; this
    helper never retries or writes an arm response into developmental history.
    Invocation receipts remain in the governed invoker's receipt store.
    """
    if (not callable(getattr(store, "persist_strategy_inclusion_protocol", None))
            or not callable(getattr(store, "persist_strategy_inclusion_score", None))
            or not callable(getattr(store, "claim_strategy_inclusion_arm", None))
            or not callable(getattr(store, "complete_strategy_inclusion_arm", None))
            or not callable(getattr(store, "strategy_inclusion_arm_execution_state", None))
            or not callable(execute_arm)):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_runner_dependencies_invalid")
    if not isinstance(protocol, Mapping):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_protocol_invalid")
    probes = protocol.get("probe_binding_digests")
    if not isinstance(probes, list) or not probes:
        raise StrategyInclusionInterventionError(
            "strategy_intervention_protocol_probe_bindings_invalid")
    # Validate frozen bindings before invocation; answer-key binding is checked
    # against the supplied private key, never a synthetic scoring fixture.
    validate_strategy_inclusion_protocol(protocol=protocol)
    if (protocol.get("schema_version") in {
            PRIVATE_TASK_SCHEMA_VERSION, SESSION_NORMALIZED_SCHEMA_VERSION,
            SCHEMA_VERSION}
            and _digest(dict(answer_key)) != protocol.get("answer_key_digest")):
        raise StrategyInclusionInterventionError(
            "strategy_intervention_answer_key_digest_mismatch")
    persisted_protocol = store.persist_strategy_inclusion_protocol(protocol)
    receipts: dict[str, Mapping[str, Any]] = {}
    for arm in persisted_protocol.get("conditions", ()):
        arm = str(arm)
        state = store.strategy_inclusion_arm_execution_state(
            protocol_digest=str(persisted_protocol["protocol_digest"]),
            arm=arm)
        if state.get("status") == "claimed_without_receipt":
            candidates = (recover_claimed_arm(arm, persisted_protocol)
                if callable(recover_claimed_arm) else ())
            if (not isinstance(candidates, Sequence)
                    or isinstance(candidates, (str, bytes))):
                raise StrategyInclusionInterventionError(
                    "strategy_intervention_recovery_candidates_invalid:" + arm)
            if len(candidates) > MAX_ARM_RECOVERY_CANDIDATES:
                raise StrategyInclusionInterventionError(
                    "strategy_intervention_recovery_candidate_limit_exceeded:" + arm)
            verified: list[tuple[Mapping[str, Any], dict[str, Any]]] = []
            for candidate in candidates:
                if not isinstance(candidate, Mapping):
                    raise StrategyInclusionInterventionError(
                        "strategy_intervention_recovery_candidate_invalid:" + arm)
                try:
                    binding = verify_strategy_inclusion_arm_receipt(
                        protocol=persisted_protocol, arm=arm, receipt=candidate)
                except StrategyInclusionInterventionError:
                    continue
                verified.append((candidate, binding))
            if len(verified) != 1:
                raise StrategyInclusionInterventionError(
                    "strategy_intervention_arm_claim_requires_manual_reconciliation:" + arm)
            receipt, binding = verified[0]
            store.complete_strategy_inclusion_arm(
                protocol_digest=str(persisted_protocol["protocol_digest"]),
                arm=arm, receipt_binding=binding)
            receipts[arm] = dict(receipt)
            continue
        if state.get("status") == "completed":
            if not callable(load_receipt):
                raise StrategyInclusionInterventionError(
                    "strategy_intervention_receipt_loader_required:" + arm)
            stored_binding = state["result"]["receipt_binding"]
            receipt = load_receipt(stored_binding["receipt_id"],
                stored_binding["receipt_digest"])
            binding = verify_strategy_inclusion_arm_receipt(
                protocol=persisted_protocol, arm=arm, receipt=receipt)
            if binding != stored_binding:
                raise StrategyInclusionInterventionError(
                    "strategy_intervention_reloaded_receipt_binding_mismatch:" + arm)
            receipts[arm] = dict(receipt)
            continue
        if state.get("status") != "not_started":
            raise StrategyInclusionInterventionError(
                "strategy_intervention_arm_state_invalid:" + arm)
        store.claim_strategy_inclusion_arm(
            protocol_digest=str(persisted_protocol["protocol_digest"]), arm=arm)
        receipt = execute_arm(arm, persisted_protocol)
        if not isinstance(receipt, Mapping):
            raise StrategyInclusionInterventionError(
                "strategy_intervention_runner_receipt_missing:" + arm)
        binding = verify_strategy_inclusion_arm_receipt(
            protocol=persisted_protocol, arm=arm, receipt=receipt)
        store.complete_strategy_inclusion_arm(
            protocol_digest=str(persisted_protocol["protocol_digest"]),
            arm=arm, receipt_binding=binding)
        receipts[arm] = dict(receipt)

    score = score_verified_strategy_inclusion_pair(protocol=persisted_protocol,
        answer_key=answer_key, invocation_receipts_by_arm=receipts)
    persisted_score = store.persist_strategy_inclusion_score(
        protocol_digest=str(persisted_protocol["protocol_digest"]),
        score=score, answer_key=answer_key,
        invocation_receipts_by_arm=receipts)
    return {"protocol_digest": persisted_protocol["protocol_digest"],
        "score_digest": persisted_score["score_digest"],
        "score": persisted_score,
        "inference_performed": True,
        "paired_delivery_verified": True,
        "learning_established": False,
        "authority": False}
