"""Replay a preregistered transfer task against its frozen prior history.

This read-only CPU audit verifies campaign boundaries, derives the exact seeded
transfer probes and target identity for one selected plan cycle, then runs the
resident owner and prompt binder before any cycle inference. It cannot include
model-generated acquisition results from the planned cycle.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_rootless_ollama_embodied_cognition_cycle import (  # noqa: E402
    ROOTLESS_DEVELOPMENTAL_COGNITION_INPUT_CHAR_LIMIT,
)
from sentientos.local_model import (  # noqa: E402
    ActiveModelIdentity,
    GenerationConfig,
    ModelCandidate,
    ModelConfig,
    candidate_artifact_identity,
    candidate_configuration_digest,
)
from sentientos.local_model_authority import digest_payload  # noqa: E402
from sentientos.developmental_model_replacement_experiment import (  # noqa: E402
    ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY,
    rootless_integer_affine_transfer_task_pair,
)
from sentientos.embodiment_self_observation import (  # noqa: E402
    EmbodimentEvidenceOwner,
    make_synthetic_pre_action_proprioception_observation,
)
from sentientos.resident_developmental_cognition import (  # noqa: E402
    EXPERIMENT_CONTEXT_INSTRUCTION,
    TASK_FAMILY_PRIOR_INCORRECT_EXAMPLE_INSTRUCTION,
    ResidentDevelopmentalCognitionOwner,
    ResidentDevelopmentalCognitionError,
    _current_evidence_prompt_payload,
    _experiment_instruction_template,
    _bind_history_and_epistemic_context,
    _digest,
    _task_family_history_prompt_projection,
    _task_family_history_examples,
)
from sentientos.resident_developmental_writeback import (  # noqa: E402
    DevelopmentalHistoryProjection,
    ResidentDevelopmentalWritebackController,
)
from sentientos.rootless_experimental_ollama_epistemic_session import (  # noqa: E402
    _rootless_ollama_model_options,
)
from sentientos.rootless_experimental_local_model import (  # noqa: E402
    EXPERIMENT_ROOT,
    _no_symlink_path,
)
from work.rootless_history_boundary_campaign import (  # noqa: E402
    _cognition_recovery_state_boundary,
    _history_boundary,
    _load_plan,
    _runtime_admission_boundary,
    verify_chain,
)
from sentientos.world_state_board import WorldStateBoardBuilder  # noqa: E402


def _read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("planned_preflight_source_file_invalid")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("planned_preflight_source_json_invalid")
    return value


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _record_probe_overlap(records: tuple[dict[str, Any], ...], *,
        family: str | tuple[str, ...],
        probe_inputs: tuple[int, ...]) -> list[dict[str, Any]]:
    """Expose which current probes occur in each owner-selected record."""
    requested = set(probe_inputs)
    rows: list[dict[str, Any]] = []
    for record in records:
        record_id = record.get("record_id")
        candidate = record.get("candidate")
        if not isinstance(candidate, dict):
            candidate = record
        inputs: set[int] = set()
        families = family if isinstance(family, tuple) else (family,)
        experiences = [example for family_id in families
            for example in _task_family_history_examples(
                candidate, task_family_id=family_id)]
        for experience in experiences:
            for example in experience.get("examples", ()):
                value = example.get("probe_input") if isinstance(example, dict) else None
                if type(value) is int:
                    inputs.add(value)
        overlaps = sorted(inputs & requested)
        rows.append({"record_id": record_id,
            "projected_experience_count": len(experiences),
            "available_probe_inputs": sorted(inputs),
            "current_probe_overlap_inputs": overlaps,
            "current_probe_overlap_count": len(overlaps)})
    return rows


def _strategy_source_family_audit(strategy: object, *,
        declared_history_families: tuple[str, ...]) -> dict[str, Any]:
    """Expose source-family provenance without copying strategy answers."""
    if not isinstance(strategy, dict):
        return {
            "present": False,
            "history_task_family_ids": None,
            "source_family_counts": [],
            "source_count": None,
            "source_refs_digest": None,
            "relation_matches_task": None,
        }
    source_refs = strategy.get("supporting_source_refs")
    strategy_families = strategy.get("history_task_family_ids")
    if (not isinstance(source_refs, list)
            or not isinstance(strategy_families, list)
            or strategy_families != list(declared_history_families)
            or any(not isinstance(row, dict)
                or row.get("source_task_family_id")
                    not in declared_history_families for row in source_refs)):
        raise ValueError("planned_preflight_strategy_source_family_binding_invalid")
    counts = {family_id: sum(row.get("source_task_family_id") == family_id
        for row in source_refs) for family_id in declared_history_families}
    return {
        "present": True,
        "history_task_family_ids": strategy_families,
        "visible_source_family_counts": [{"task_family_id": family_id,
            "source_count": counts[family_id]}
            for family_id in declared_history_families if counts[family_id]],
        "source_count": strategy.get("supporting_source_count"),
        "visible_source_count": len(source_refs),
        "omitted_source_count": strategy.get("omitted_supporting_source_count"),
        "source_refs_digest": strategy.get("supporting_sources_digest"),
        "relation_matches_task": True,
    }


def _strategy_model_identity_audit(strategy: object, *,
        target_active_model_identity: Mapping[str, Any],
        source_records: tuple[dict[str, Any], ...],
        source_task_family_ids: tuple[str, ...]) -> dict[str, Any]:
    """Report source-to-target identity and artifact relations without answers."""
    target_active_digest = _digest(dict(target_active_model_identity))
    target_artifact_digest = target_active_model_identity.get(
        "semantic_artifact_identity")
    if not isinstance(target_artifact_digest, str) or not target_artifact_digest:
        raise ValueError("planned_preflight_target_model_artifact_identity_invalid")
    if not isinstance(strategy, dict):
        return {
            "schema_version": (
                "sentientos.rootless_planned_cycle_model_identity_audit:v1"),
            "present": False,
            "target_active_model_identity_digest": (
                target_active_digest),
            "target_model_artifact_identity": target_artifact_digest,
            "source_count": None,
            "visible_source_count": 0,
            "omitted_source_count": None,
            "relation_counts": [],
            "artifact_relation_counts": [],
            "source_relations_digest": None,
            "all_sources_bound_to_different_active_identity": None,
            "all_source_artifacts_differ_from_target": None,
        }
    source_refs = strategy.get("supporting_source_refs")
    target_digest = strategy.get("target_active_model_identity_digest")
    omitted_count = strategy.get("omitted_supporting_source_count")
    source_count = strategy.get("supporting_source_count")
    if (not isinstance(source_refs, list)
            or target_digest != target_active_digest
            or type(omitted_count) is not int or omitted_count < 0
            or type(source_count) is not int
            or source_count != len(source_refs) + omitted_count):
        raise ValueError("planned_preflight_strategy_model_identity_binding_invalid")
    source_experiences: dict[tuple[str, str], Mapping[str, Any]] = {}
    for record in source_records:
        record_id = record.get("record_id")
        candidate = record.get("candidate")
        if not isinstance(record_id, str) or not isinstance(candidate, Mapping):
            raise ValueError("planned_preflight_source_identity_record_invalid")
        for family_id in source_task_family_ids:
            for experience in _task_family_history_examples(candidate,
                    task_family_id=family_id):
                fact_id = experience.get("source_fact_id")
                if isinstance(fact_id, str):
                    source_experiences[(record_id, fact_id)] = experience
    relations: list[dict[str, Any]] = []
    for source in source_refs:
        if not isinstance(source, dict):
            raise ValueError("planned_preflight_strategy_source_identity_invalid")
        source_digest = source.get("source_active_model_identity_digest")
        record_id = source.get("record_id")
        fact_id = source.get("source_fact_id")
        experience = source_experiences.get((record_id, fact_id))
        if experience is None:
            raise ValueError("planned_preflight_strategy_source_record_unresolved")
        source_identity = experience.get("source_active_model_identity")
        if source_digest is None:
            if (source_identity is not None
                    or experience.get("model_identity_binding_posture")
                        != "source_model_identity_unbound"):
                raise ValueError(
                    "planned_preflight_strategy_source_identity_unverified")
            relation = "model_identity_unbound"
            source_artifact_digest = None
            artifact_relation = "source_model_artifact_identity_unbound"
        elif (not isinstance(source_digest, str) or len(source_digest) != 71
                or not source_digest.startswith("sha256:")
                or any(char not in "0123456789abcdef"
                    for char in source_digest[7:])):
            raise ValueError("planned_preflight_strategy_source_identity_invalid")
        else:
            if (not isinstance(source_identity, Mapping) or not source_identity
                    or experience.get("source_active_model_identity_digest")
                        != source_digest
                    or _digest(dict(source_identity)) != source_digest):
                raise ValueError(
                    "planned_preflight_strategy_source_identity_unverified")
            source_artifact_digest = source_identity.get(
                "semantic_artifact_identity")
            if (not isinstance(source_artifact_digest, str)
                    or not source_artifact_digest):
                raise ValueError(
                    "planned_preflight_strategy_source_artifact_identity_invalid")
            relation = ("same_active_model_identity"
                if source_digest == target_digest
                else "different_active_model_identity")
            artifact_relation = ("same_model_artifact_identity"
                if source_artifact_digest == target_artifact_digest
                else "different_model_artifact_identity")
        # The durable experience has no target-specific relation until the
        # binder applies this exact target identity. Re-derive it here from the
        # already verified source identity map and the target map above.
        relations.append({
            "record_id": record_id,
            "source_task_family_id": source.get("source_task_family_id"),
            "source_active_model_identity_digest": source_digest,
            "model_identity_relation": relation,
            "source_model_artifact_identity": source_artifact_digest,
            "target_model_artifact_identity": target_artifact_digest,
            "model_artifact_relation": artifact_relation,
        })
    counts: dict[str, int] = {}
    artifact_counts: dict[str, int] = {}
    for row in relations:
        relation = row["model_identity_relation"]
        counts[relation] = counts.get(relation, 0) + 1
        artifact_relation = row["model_artifact_relation"]
        artifact_counts[artifact_relation] = (
            artifact_counts.get(artifact_relation, 0) + 1)
    complete = omitted_count == 0 and bool(relations)
    all_different = (complete and all(row["model_identity_relation"] ==
        "different_active_model_identity" for row in relations))
    return {
        "schema_version": (
            "sentientos.rootless_planned_cycle_model_identity_audit:v1"),
        "present": True,
        "target_active_model_identity_digest": target_digest,
        "target_model_artifact_identity": target_artifact_digest,
        "source_count": source_count,
        "visible_source_count": len(relations),
        "omitted_source_count": omitted_count,
        "relation_counts": [{"relation": relation, "source_count": counts[relation]}
            for relation in sorted(counts)],
        "artifact_relation_counts": [{"relation": relation,
            "source_count": artifact_counts[relation]}
            for relation in sorted(artifact_counts)],
        "source_relations_digest": _canonical_digest(relations),
        "all_sources_bound_to_different_active_identity": all_different,
        "all_source_artifacts_differ_from_target": (
            complete and all(row["model_artifact_relation"] ==
                "different_model_artifact_identity" for row in relations)),
    }


def _validate_strategy_inclusion_ablation(value: Mapping[str, Any]) -> None:
    """Enforce the persisted v1 ablation contract before report publication."""
    common = {"schema_version", "status", "inference_performed",
        "learning_established", "authority"}
    if (value.get("schema_version") !=
            "sentientos.rootless_planned_cycle_strategy_inclusion_ablation:v1"
            or any(value.get(field) is not False for field in (
                "inference_performed", "learning_established", "authority"))):
        raise ValueError("planned_preflight_strategy_ablation_contract_invalid")
    status = value.get("status")
    if status == "accumulated_strategy_not_present":
        if set(value) != common:
            raise ValueError("planned_preflight_strategy_ablation_contract_invalid")
        return
    expected = common | {
        "intervention", "changed_context_fields", "accumulated_strategy_digest",
        "accumulated_strategy_serialization_digest", "baseline_prompt_digest",
        "ablated_prompt_digest", "baseline_prompt_chars", "ablated_prompt_chars",
        "prompt_chars_removed", "selected_record_ids", "selected_record_digests",
        "history_packets_unchanged", "history_packets_digest",
        "retained_per_record_candidate_strategy_count",
        "baseline_contains_accumulated_strategy",
        "ablated_prompt_excludes_accumulated_strategy",
        "exact_cycle_prompt_reconstructed", "model_attention_established",
    }
    digest_fields = (
        "accumulated_strategy_digest", "accumulated_strategy_serialization_digest",
        "baseline_prompt_digest", "ablated_prompt_digest", "history_packets_digest")
    if (status != "paired_prompt_reconstruction_verified"
            or set(value) != expected
            or value.get("intervention") !=
                "remove_only_top_level_accumulated_candidate_strategy"
            or value.get("changed_context_fields") != [
                "task_family_accumulated_candidate_strategy"]
            or any(not isinstance(value.get(field), str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", value[field]) is None
                for field in digest_fields)
            or any(type(value.get(field)) is not int or value[field] < 0
                for field in ("baseline_prompt_chars", "ablated_prompt_chars",
                    "retained_per_record_candidate_strategy_count"))
            or type(value.get("prompt_chars_removed")) is not int
            or value["prompt_chars_removed"] != (
                value["baseline_prompt_chars"] - value["ablated_prompt_chars"])
            or value["prompt_chars_removed"] <= 0
            or not isinstance(value.get("selected_record_ids"), list)
            or any(not isinstance(item, str) or not item
                for item in value["selected_record_ids"])
            or len(set(value["selected_record_ids"]))
                != len(value["selected_record_ids"])
            or not isinstance(value.get("selected_record_digests"), list)
            or len(value["selected_record_digests"])
                != len(value["selected_record_ids"])
            or any(not isinstance(item, str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", item) is None
                for item in value["selected_record_digests"])
            or any(value.get(field) is not True for field in (
                "history_packets_unchanged", "baseline_contains_accumulated_strategy",
                "ablated_prompt_excludes_accumulated_strategy"))
            or any(value.get(field) is not False for field in (
                "exact_cycle_prompt_reconstructed", "model_attention_established"))):
        raise ValueError("planned_preflight_strategy_ablation_contract_invalid")


def _strategy_inclusion_ablation(bound_context: Mapping[str, Any], *,
        baseline_prompt: str, selected_record_ids: tuple[str, ...],
        selected_record_digests: tuple[str, ...]) -> dict[str, Any]:
    """Compare the exact bound prompt with only its accumulated strategy removed."""
    schema = "sentientos.rootless_planned_cycle_strategy_inclusion_ablation:v1"
    strategy = bound_context.get("task_family_accumulated_candidate_strategy")
    if not isinstance(strategy, Mapping):
        result = {"schema_version": schema,
            "status": "accumulated_strategy_not_present",
            "inference_performed": False, "learning_established": False,
            "authority": False}
        _validate_strategy_inclusion_ablation(result)
        return result
    serialized_context = json.dumps(dict(bound_context), sort_keys=True,
        separators=(",", ":"))
    if serialized_context != baseline_prompt:
        raise ValueError("planned_preflight_strategy_ablation_baseline_prompt_mismatch")
    history_packets = bound_context.get("developmental_history")
    if not isinstance(history_packets, (list, tuple)):
        raise ValueError("planned_preflight_strategy_ablation_history_invalid")
    history_ids = tuple(packet.get("record_id") for packet in history_packets
        if isinstance(packet, Mapping))
    history_digests = tuple(packet.get("record_digest") for packet in history_packets
        if isinstance(packet, Mapping))
    if (len(history_ids) != len(history_packets)
            or history_ids != selected_record_ids
            or history_digests != selected_record_digests):
        raise ValueError("planned_preflight_strategy_ablation_history_binding_mismatch")
    ablated_context = dict(bound_context)
    ablated_context.pop("task_family_accumulated_candidate_strategy")
    changed_fields = sorted(key for key in set(bound_context) | set(ablated_context)
        if bound_context.get(key) != ablated_context.get(key))
    if changed_fields != ["task_family_accumulated_candidate_strategy"]:
        raise ValueError("planned_preflight_strategy_ablation_changed_other_context")
    ablated_prompt = json.dumps(ablated_context, sort_keys=True,
        separators=(",", ":"))
    strategy_serialization = json.dumps(dict(strategy), sort_keys=True,
        separators=(",", ":"))
    if strategy_serialization not in baseline_prompt:
        raise ValueError("planned_preflight_strategy_ablation_strategy_missing_from_baseline")
    if strategy_serialization in ablated_prompt:
        raise ValueError("planned_preflight_strategy_ablation_strategy_remains")
    per_record_strategy_count = sum(
        isinstance(experience.get("candidate_integer_affine_strategy"), Mapping)
        for packet in history_packets if isinstance(packet, Mapping)
        for experience in packet.get("task_relevant_experience", ())
        if isinstance(experience, Mapping))
    result = {
        "schema_version": schema,
        "status": "paired_prompt_reconstruction_verified",
        "intervention": "remove_only_top_level_accumulated_candidate_strategy",
        "changed_context_fields": changed_fields,
        "accumulated_strategy_digest": strategy.get("strategy_digest"),
        "accumulated_strategy_serialization_digest": _canonical_digest(
            dict(strategy)),
        "baseline_prompt_digest": _digest({"prompt": baseline_prompt}),
        "ablated_prompt_digest": _digest({"prompt": ablated_prompt}),
        "baseline_prompt_chars": len(baseline_prompt),
        "ablated_prompt_chars": len(ablated_prompt),
        "prompt_chars_removed": len(baseline_prompt) - len(ablated_prompt),
        "selected_record_ids": list(selected_record_ids),
        "selected_record_digests": list(selected_record_digests),
        "history_packets_unchanged": (
            bound_context["developmental_history"]
                == ablated_context["developmental_history"]),
        "history_packets_digest": _canonical_digest(list(history_packets)),
        "retained_per_record_candidate_strategy_count": (
            per_record_strategy_count),
        "baseline_contains_accumulated_strategy": True,
        "ablated_prompt_excludes_accumulated_strategy": True,
        "exact_cycle_prompt_reconstructed": False,
        "model_attention_established": False,
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
    }
    _validate_strategy_inclusion_ablation(result)
    return result


def _historical_examples_ablation(bound_context: Mapping[str, Any], *,
        baseline_prompt: str, selected_record_ids: tuple[str, ...],
        selected_record_digests: tuple[str, ...],
        heldout_probe_inputs: tuple[int, ...],
        family_projection: Mapping[str, Any]) -> dict[str, Any]:
    """Reconstruct an offline prompt with raw historical examples omitted.

    This is a study-design artifact only. It does not pass through the regular
    binder, and must never be described as a runtime condition or model input.
    """
    schema = "sentientos.rootless_planned_cycle_historical_examples_ablation:v2"
    if json.dumps(dict(bound_context), sort_keys=True, separators=(",", ":")) != baseline_prompt:
        raise ValueError("planned_preflight_examples_ablation_baseline_mismatch")
    history_packets = bound_context.get("developmental_history")
    if not isinstance(history_packets, (list, tuple)):
        raise ValueError("planned_preflight_examples_ablation_history_invalid")
    history_ids = tuple(packet.get("record_id") for packet in history_packets
        if isinstance(packet, Mapping))
    history_digests = tuple(packet.get("record_digest") for packet in history_packets
        if isinstance(packet, Mapping))
    if (len(history_ids) != len(history_packets)
            or history_ids != selected_record_ids
            or history_digests != selected_record_digests):
        raise ValueError("planned_preflight_examples_ablation_binding_mismatch")

    variant = copy.deepcopy(dict(bound_context))
    omitted: list[dict[str, Any]] = []
    for packet in variant["developmental_history"]:
        experiences = packet.get("task_relevant_experience", ())
        if not isinstance(experiences, list):
            continue
        for index, experience in enumerate(experiences):
            if not isinstance(experience, dict) or "examples" not in experience:
                continue
            examples = experience.pop("examples")
            if not isinstance(examples, list):
                raise ValueError("planned_preflight_examples_ablation_examples_invalid")
            if examples:
                omitted.append({"record_id": packet["record_id"],
                    "experience_index": index, "examples": examples})
    if not omitted:
        return {
            "schema_version": schema,
            "status": "historical_examples_not_present",
            "inference_performed": False,
            "learning_established": False,
            "model_attention_established": False,
            "authority": False,
        }
    overlap_input_count = family_projection.get(
        "historical_probe_overlap_input_count")
    overlap_example_count = family_projection.get(
        "historical_probe_overlap_example_count")
    overlap_digest = family_projection.get(
        "historical_probe_overlap_input_digest")
    overlap_complete = family_projection.get(
        "historical_probe_overlap_measurement_complete")
    if (not heldout_probe_inputs
            or type(overlap_input_count) is not int or overlap_input_count < 0
            or type(overlap_example_count) is not int or overlap_example_count < 0
            or not isinstance(overlap_digest, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", overlap_digest) is None
            or overlap_complete is not True):
        raise ValueError("planned_preflight_examples_ablation_probe_overlap_invalid")
    omitted_digest = _canonical_digest(omitted)
    variant_prompt = json.dumps(variant, sort_keys=True, separators=(",", ":"))

    baseline_strategy = bound_context.get("task_family_accumulated_candidate_strategy")
    if variant.get("task_family_accumulated_candidate_strategy") != baseline_strategy:
        raise ValueError("planned_preflight_examples_ablation_accumulated_strategy_changed")
    def per_record_strategies(context: Mapping[str, Any]) -> list[Any]:
        return [experience.get("candidate_integer_affine_strategy")
            for packet in context["developmental_history"]
            for experience in packet.get("task_relevant_experience", ())
            if isinstance(experience, Mapping)
            and "candidate_integer_affine_strategy" in experience]
    baseline_record_strategies = per_record_strategies(bound_context)
    if per_record_strategies(variant) != baseline_record_strategies:
        raise ValueError("planned_preflight_examples_ablation_record_strategy_changed")
    retained_ids = [packet.get("record_id") for packet in variant["developmental_history"]]
    retained_digests = [packet.get("record_digest") for packet in variant["developmental_history"]]
    if retained_ids != list(selected_record_ids) or retained_digests != list(selected_record_digests):
        raise ValueError("planned_preflight_examples_ablation_source_binding_changed")
    result = {
        "schema_version": schema,
        "status": "paired_prompt_reconstruction_verified",
        "intervention": "remove_raw_examples_arrays_from_selected_history_packets",
        "changed_context_fields": ["developmental_history"],
        "baseline_prompt_digest": _digest({"prompt": baseline_prompt}),
        "ablated_prompt_digest": _digest({"prompt": variant_prompt}),
        "baseline_prompt_chars": len(baseline_prompt),
        "ablated_prompt_chars": len(variant_prompt),
        "selected_record_ids": list(selected_record_ids),
        "selected_record_digests": list(selected_record_digests),
        "history_source_records_unchanged": True,
        "history_source_record_ids_digest": _canonical_digest(list(selected_record_ids)),
        "history_source_record_digests_digest": _canonical_digest(list(selected_record_digests)),
        "withheld_example_count": sum(len(row["examples"]) for row in omitted),
        "withheld_example_digest": omitted_digest,
        "heldout_transfer_probe_count": len(heldout_probe_inputs),
        "heldout_transfer_probe_digest": _digest({
            "probe_inputs": list(heldout_probe_inputs)}),
        "historical_probe_overlap_input_count": overlap_input_count,
        "historical_probe_overlap_example_count": overlap_example_count,
        "historical_probe_overlap_input_digest": overlap_digest,
        "historical_probe_overlap_measurement_complete": overlap_complete,
        "heldout_transfer_probe_set_disjoint": (
            overlap_input_count == 0 and overlap_example_count == 0),
        "retained_per_record_candidate_strategy_count": len(baseline_record_strategies),
        "per_record_candidate_strategies_unchanged": True,
        "accumulated_strategy_unchanged": True,
        "exact_cycle_prompt_reconstructed": False,
        "runtime_condition_created": False,
        "model_attention_established": False,
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
    }
    _validate_historical_examples_ablation(result)
    return result


def _negative_example_ablation(bound_context: Mapping[str, Any], *,
        baseline_prompt: str, selected_record_ids: tuple[str, ...],
        selected_record_digests: tuple[str, ...],
        heldout_probe_inputs: tuple[int, ...],
        projected_negative_example_count: int) -> dict[str, Any]:
    """Build an answer-free paired prompt with retrieved negative examples removed."""
    schema = "sentientos.rootless_planned_cycle_negative_example_ablation:v1"
    if json.dumps(dict(bound_context), sort_keys=True, separators=(",", ":")) != baseline_prompt:
        raise ValueError("planned_preflight_negative_ablation_baseline_mismatch")
    variant = copy.deepcopy(dict(bound_context))
    history = variant.get("developmental_history")
    if not isinstance(history, list):
        raise ValueError("planned_preflight_negative_ablation_history_invalid")
    if ([packet.get("record_id") for packet in history] != list(selected_record_ids)
            or [packet.get("record_digest") for packet in history]
                != list(selected_record_digests)):
        raise ValueError("planned_preflight_negative_ablation_source_binding_mismatch")
    removed: list[dict[str, Any]] = []
    for packet in history:
        experiences = packet.get("task_relevant_experience", ())
        if not isinstance(experiences, list):
            continue
        for index, experience in enumerate(experiences):
            if not isinstance(experience, dict):
                continue
            negative = experience.pop("prior_incorrect_examples", None)
            if negative is not None:
                removed.append({"record_id": packet["record_id"],
                    "experience_index": index, "prior_incorrect_examples": negative})
    if not removed:
        return {"schema_version": schema, "status": "negative_examples_not_present",
            "inference_performed": False, "learning_established": False,
            "model_attention_established": False, "authority": False}
    if (not heldout_probe_inputs or type(projected_negative_example_count) is not int
            or projected_negative_example_count <= 0):
        raise ValueError("planned_preflight_negative_ablation_heldout_probes_missing")
    variant_prompt = json.dumps(variant, sort_keys=True, separators=(",", ":"))
    if (TASK_FAMILY_PRIOR_INCORRECT_EXAMPLE_INSTRUCTION not in baseline_prompt
            or TASK_FAMILY_PRIOR_INCORRECT_EXAMPLE_INSTRUCTION not in variant_prompt):
        raise ValueError("planned_preflight_negative_ablation_guidance_changed")
    return {
        "schema_version": schema, "status": "paired_prompt_reconstruction_verified",
        "intervention": "remove_only_prior_incorrect_examples_from_selected_history",
        "changed_context_fields": ["developmental_history"],
        "baseline_prompt_digest": _digest({"prompt": baseline_prompt}),
        "ablated_prompt_digest": _digest({"prompt": variant_prompt}),
        "baseline_prompt_chars": len(baseline_prompt),
        "ablated_prompt_chars": len(variant_prompt),
        "selected_record_ids": list(selected_record_ids),
        "selected_record_digests": list(selected_record_digests),
        "removed_negative_example_packet_count": len(removed),
        "removed_negative_example_digest": _canonical_digest(removed),
        "negative_example_count": projected_negative_example_count,
        "no_imitation_guidance_unchanged": True,
        "heldout_probe_count": len(heldout_probe_inputs),
        "heldout_probe_digest": _digest({"probe_inputs": list(heldout_probe_inputs)}),
        "source_record_binding_unchanged": True,
        "exact_cycle_prompt_reconstructed": False,
        "runtime_condition_created": False, "inference_performed": False,
        "learning_established": False, "model_attention_established": False,
        "authority": False,
    }


def _validate_negative_example_ablation(value: Mapping[str, Any]) -> None:
    if any(value.get(key) is not False for key in (
            "inference_performed", "learning_established",
            "model_attention_established", "authority")):
        raise ValueError("planned_preflight_negative_ablation_posture_invalid")
    if value.get("schema_version") != "sentientos.rootless_planned_cycle_negative_example_ablation:v1":
        raise ValueError("planned_preflight_negative_ablation_schema_invalid")
    common = {"schema_version", "status", "inference_performed",
        "learning_established", "model_attention_established", "authority"}
    if value.get("status") == "negative_examples_not_present":
        if set(value) != common:
            raise ValueError("planned_preflight_negative_ablation_contract_invalid")
        return
    expected = common | {"intervention", "changed_context_fields",
        "baseline_prompt_digest", "ablated_prompt_digest", "baseline_prompt_chars",
        "ablated_prompt_chars", "selected_record_ids", "selected_record_digests",
        "removed_negative_example_packet_count", "removed_negative_example_digest",
        "negative_example_count", "no_imitation_guidance_unchanged",
        "heldout_probe_count", "heldout_probe_digest", "source_record_binding_unchanged",
        "exact_cycle_prompt_reconstructed", "runtime_condition_created"}
    if (value.get("status") != "paired_prompt_reconstruction_verified"
            or set(value) != expected
            or value.get("intervention") != "remove_only_prior_incorrect_examples_from_selected_history"
            or value.get("changed_context_fields") != ["developmental_history"]
            or any(not isinstance(value.get(k), str) or re.fullmatch(
                r"sha256:[0-9a-f]{64}", value[k]) is None for k in (
                    "baseline_prompt_digest", "ablated_prompt_digest",
                    "removed_negative_example_digest", "heldout_probe_digest"))
            or any(type(value.get(k)) is not int or value[k] < 0 for k in (
                "baseline_prompt_chars", "ablated_prompt_chars",
                "removed_negative_example_packet_count", "negative_example_count",
                "heldout_probe_count"))
            or value["removed_negative_example_packet_count"] < 1
            or value["negative_example_count"] < 1
            or value["heldout_probe_count"] < 1
            or value.get("no_imitation_guidance_unchanged") is not True
            or value.get("source_record_binding_unchanged") is not True
            or value.get("exact_cycle_prompt_reconstructed") is not False
            or value.get("runtime_condition_created") is not False):
        raise ValueError("planned_preflight_negative_ablation_contract_invalid")


def _validate_historical_examples_ablation(value: Mapping[str, Any]) -> None:
    """Validate the answer-free, offline historical-example ablation record."""
    common = {"schema_version", "status", "inference_performed",
        "learning_established", "model_attention_established", "authority"}
    if (value.get("schema_version") !=
            "sentientos.rootless_planned_cycle_historical_examples_ablation:v2"
            or any(value.get(field) is not False for field in (
                "inference_performed", "learning_established",
                "model_attention_established", "authority"))):
        raise ValueError("planned_preflight_examples_ablation_contract_invalid")
    if value.get("status") == "historical_examples_not_present":
        if set(value) != common:
            raise ValueError("planned_preflight_examples_ablation_contract_invalid")
        return
    expected = common | {"intervention", "changed_context_fields",
        "baseline_prompt_digest", "ablated_prompt_digest",
        "baseline_prompt_chars", "ablated_prompt_chars", "selected_record_ids",
        "selected_record_digests", "history_source_records_unchanged",
        "history_source_record_ids_digest", "history_source_record_digests_digest",
        "withheld_example_count", "withheld_example_digest",
        "heldout_transfer_probe_count", "heldout_transfer_probe_digest",
        "historical_probe_overlap_input_count",
        "historical_probe_overlap_example_count",
        "historical_probe_overlap_input_digest",
        "historical_probe_overlap_measurement_complete",
        "heldout_transfer_probe_set_disjoint",
        "retained_per_record_candidate_strategy_count",
        "per_record_candidate_strategies_unchanged", "accumulated_strategy_unchanged",
        "exact_cycle_prompt_reconstructed", "runtime_condition_created"}
    digest_fields = ("baseline_prompt_digest", "ablated_prompt_digest",
        "history_source_record_ids_digest", "history_source_record_digests_digest",
        "withheld_example_digest", "heldout_transfer_probe_digest",
        "historical_probe_overlap_input_digest")
    if (value.get("status") != "paired_prompt_reconstruction_verified"
            or set(value) != expected
            or value.get("intervention") !=
                "remove_raw_examples_arrays_from_selected_history_packets"
            or value.get("changed_context_fields") != ["developmental_history"]
            or any(not isinstance(value.get(field), str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", value[field]) is None
                for field in digest_fields)
            or any(type(value.get(field)) is not int or value[field] < 0
                for field in ("baseline_prompt_chars", "ablated_prompt_chars",
                    "withheld_example_count", "heldout_transfer_probe_count",
                    "historical_probe_overlap_input_count",
                    "historical_probe_overlap_example_count",
                    "retained_per_record_candidate_strategy_count"))
            or value["withheld_example_count"] <= 0
            or value["heldout_transfer_probe_count"] <= 0
            or value.get("historical_probe_overlap_measurement_complete") is not True
            or value.get("heldout_transfer_probe_set_disjoint") is not (
                value["historical_probe_overlap_input_count"] == 0
                and value["historical_probe_overlap_example_count"] == 0)
            or not isinstance(value.get("selected_record_ids"), list)
            or any(not isinstance(item, str) or not item for item in value["selected_record_ids"])
            or len(set(value["selected_record_ids"])) != len(value["selected_record_ids"])
            or not isinstance(value.get("selected_record_digests"), list)
            or len(value["selected_record_digests"]) != len(value["selected_record_ids"])
            or any(not isinstance(item, str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", item) is None
                for item in value["selected_record_digests"])
            or value.get("history_source_record_ids_digest") != _canonical_digest(
                value["selected_record_ids"])
            or value.get("history_source_record_digests_digest") != _canonical_digest(
                value["selected_record_digests"])
            or any(value.get(field) is not True for field in (
                "history_source_records_unchanged", "per_record_candidate_strategies_unchanged",
                "accumulated_strategy_unchanged"))
            or any(value.get(field) is not False for field in (
                "exact_cycle_prompt_reconstructed", "runtime_condition_created"))):
        raise ValueError("planned_preflight_examples_ablation_contract_invalid")


def _verify_owner_ranking_trace(trace: object,
        selected_record_ids: tuple[str, ...]) -> None:
    """Check trace order and selected set against the owner projection."""
    if (not selected_record_ids
            and (trace is None or isinstance(trace, (list, tuple)) and not trace)):
        return
    if not isinstance(trace, (list, tuple)) or not trace:
        raise ValueError("planned_preflight_owner_ranking_trace_missing")
    if any(not isinstance(row, dict)
            or row.get("rank_position") != index
            for index, row in enumerate(trace)):
        raise ValueError("planned_preflight_owner_ranking_trace_order_invalid")
    if "evaluator_scored_distinct_input_count" in trace[0]:
        score_fields = (
            "outcome_priority", "evaluator_scored_distinct_input_count",
            "target_model_identity_match", "current_probe_overlap_count",
            "checkpoint_order", "evaluator_correct_distinct_input_count")
    else:
        score_fields = (
            "outcome_priority", "evaluator_correct_distinct_input_count",
            "target_model_identity_match", "usable_distinct_input_count",
            "current_probe_overlap_count", "checkpoint_order")
    score_rows = [tuple(row.get(field) for field in score_fields)
        for row in trace]
    if any(any(type(value) is not int for value in score)
            for score in score_rows):
        raise ValueError("planned_preflight_owner_ranking_trace_score_invalid")
    if score_rows != sorted(score_rows, reverse=True):
        raise ValueError("planned_preflight_owner_ranking_trace_rank_invalid")
    trace_selected = {row.get("record_id") for row in trace
        if row.get("selected_within_owner_limit") is True}
    if trace_selected != set(selected_record_ids):
        raise ValueError("planned_preflight_owner_ranking_trace_selection_mismatch")


def _model_identity(*, manifest_path: Path, model_name: str,
        backend_seed: int, gpu_layers: int) -> dict[str, Any]:
    try:
        experiment_root = _no_symlink_path(EXPERIMENT_ROOT).resolve(strict=True)
        manifest_path = _no_symlink_path(manifest_path.expanduser()).resolve(strict=True)
        manifest_path.relative_to(experiment_root)
    except (OSError, ValueError, RuntimeError) as exc:
        raise ValueError("planned_preflight_model_manifest_outside_custody") from exc
    if not manifest_path.is_file() or manifest_path.stat().st_size > 1_048_576:
        raise ValueError("planned_preflight_model_manifest_invalid")
    manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if manifest_path.stem != manifest_digest:
        raise ValueError("planned_preflight_model_manifest_digest_invalid")
    if type(gpu_layers) is not int or not 0 <= gpu_layers <= 128:
        raise ValueError("planned_preflight_gpu_layers_invalid")
    options = _rootless_ollama_model_options(model_name=model_name,
        manifest_digest=manifest_digest, gpu_layers=gpu_layers)
    options["seed"] = backend_seed
    candidate = ModelCandidate(manifest_path, "ollama", model_name, options)
    config = ModelConfig([candidate], default_engine="ollama",
        max_context_tokens=8192,
        generation=GenerationConfig(max_new_tokens=512, temperature=0,
            top_p=1))
    resolved, semantic, content_digest, size, sidecar_digest = (
        candidate_artifact_identity(candidate, {}))
    identity = ActiveModelIdentity(engine="ollama",
        resolved_artifact_path=resolved,
        semantic_artifact_identity=semantic,
        model_content_sha256=content_digest,
        artifact_size_bytes=size,
        sidecar_metadata_digest=sidecar_digest,
        configuration_digest=candidate_configuration_digest(candidate,
            config, "ollama"),
        candidate_index=0, posture="development_only", fallback=False)
    if (content_digest != manifest_digest or size != manifest_path.stat().st_size
            or sidecar_digest != manifest_digest):
        raise ValueError("planned_preflight_model_identity_invalid")
    return identity.to_dict()


class _ReadOnlyRecordStore:
    def __init__(self, root: Path, expected_refs: dict[str, str]) -> None:
        self.root = root
        self.expected_refs = expected_refs
        self.cache: dict[str, SimpleNamespace] = {}

    def get(self, record_id: str) -> SimpleNamespace:
        if record_id not in self.cache:
            path = self.root / (record_id + ".json")
            row = _read_json(path)
            if (row.get("record_id") != record_id
                    or row.get("record_digest") != self.expected_refs.get(record_id)
                    or not isinstance(row.get("candidate"), dict)):
                raise ValueError("planned_preflight_record_binding_invalid")
            self.cache[record_id] = SimpleNamespace(record_id=record_id,
                record_digest=row["record_digest"], candidate=row["candidate"])
        return self.cache[record_id]

    def records(self) -> tuple[SimpleNamespace, ...]:
        return tuple(self.get(record_id)
            for record_id in sorted(self.expected_refs))


class _ReadOnlyWriteback:
    def __init__(self, store: _ReadOnlyRecordStore) -> None:
        self.store = store

    def retrieve(self, record_ids: list[str], *, limit: int
            ) -> DevelopmentalHistoryProjection:
        selected = record_ids[:limit]
        records = tuple({"record_id": record_id,
            "record_digest": self.store.get(record_id).record_digest,
            "candidate": self.store.get(record_id).candidate}
            for record_id in selected)
        return DevelopmentalHistoryProjection(records=records,
            requested_record_ids=tuple(selected))

    def select_evidence(self, snapshot: Any, *, fact_ids: tuple[str, ...]) -> Any:
        return ResidentDevelopmentalWritebackController.select_evidence(
            self, snapshot, fact_ids=fact_ids)

    @staticmethod
    def empty_selection(*, snapshot_id: str, snapshot_digest: str) -> Any:
        return ResidentDevelopmentalWritebackController.empty_selection(
            snapshot_id=snapshot_id, snapshot_digest=snapshot_digest)


def create_report(*, plan_path: Path, prior_history_root: Path,
        manifest_path: Path, model_name: str, output_path: Path,
        cycle_index: int = 0,
        alternate_seed_count: int = 16) -> dict[str, Any]:
    if (isinstance(alternate_seed_count, bool)
            or not isinstance(alternate_seed_count, int)
            or not 1 <= alternate_seed_count <= 2048):
        raise ValueError("planned_preflight_alternate_seed_count_invalid")
    plan = _load_plan(plan_path)
    pinned_plan_schemas = {
        f"sentientos.rootless_history_boundary_campaign_plan:v{version}"
        for version in range(8, 16)}
    if (plan.get("task_family_id") ==
            "rootless_integer_affine_transfer_wide_range_v7"
            and plan.get("schema_version") not in pinned_plan_schemas):
        raise ValueError("planned_preflight_experiment_implementation_unbound")
    if plan.get("schema_version") in pinned_plan_schemas:
        from work.rootless_history_boundary_campaign import (
            verify_experiment_implementation, verify_model_identity_recipe)
        verify_model_identity_recipe(plan)
        verify_experiment_implementation(plan)
    cycle_ids = plan.get("ordered_cycle_ids")
    task_seeds = plan.get("ordered_task_generation_seeds")
    backend_seeds = plan.get("ordered_backend_seeds")
    identity_digests = plan.get("ordered_model_identity_digests")
    if (not isinstance(cycle_ids, list) or not cycle_ids
            or not isinstance(task_seeds, list)
            or not isinstance(backend_seeds, list)
            or not isinstance(identity_digests, list)
            or not (len(cycle_ids) == len(task_seeds) == len(backend_seeds)
                == len(identity_digests))
            or type(cycle_index) is not int
            or not 0 <= cycle_index < len(cycle_ids)):
        raise ValueError("planned_preflight_campaign_plan_invalid")
    cycle_id = cycle_ids[cycle_index]
    task_seed = task_seeds[cycle_index]
    backend_seed = backend_seeds[cycle_index]
    family = plan["task_family_id"]
    expected_identity_digest = identity_digests[cycle_index]
    recipe = plan.get("model_identity_recipe")
    if (not isinstance(recipe, Mapping)
            or recipe.get("model_name") != model_name
            or recipe.get("resolved_manifest_path") !=
                str(manifest_path.resolve(strict=True))
            or type(recipe.get("gpu_layers")) is not int):
        raise ValueError("planned_preflight_model_identity_recipe_mismatch")
    identity = _model_identity(manifest_path=manifest_path,
        model_name=model_name, backend_seed=backend_seed,
        gpu_layers=recipe["gpu_layers"])
    identity_digest = digest_payload({"identity": identity})
    if identity_digest != expected_identity_digest:
        raise ValueError("planned_preflight_target_identity_plan_mismatch")

    history_root = prior_history_root.resolve(strict=True)
    state_root = history_root.parent / "state"
    cycle_root = history_root.parent.parent
    before_history = _history_boundary(history_root)
    before_recovery = _cognition_recovery_state_boundary(state_root)
    before_admission = _runtime_admission_boundary(history_root)
    if cycle_index == 0:
        if (before_history != plan.get("initial_history_boundary")
                or before_recovery != plan.get("initial_cognition_recovery_state")
                or before_admission != plan.get("initial_runtime_admission_ledger")):
            raise ValueError("planned_preflight_initial_boundary_mismatch")
        prior_history_boundary_verification = {
            "status": "plan_initial_boundary_match",
            "verified_prefix_cycle_ids": [],
            "prefix_audit_digest": None,
            "boundary_digest": before_history["boundary_digest"],
            "append_only_history_chain_verified": True,
        }
    else:
        expected_prior_cycle_id = cycle_ids[cycle_index - 1]
        if cycle_root.name != expected_prior_cycle_id:
            raise ValueError("planned_preflight_prior_cycle_identity_mismatch")
        prior_cycle_roots = [EXPERIMENT_ROOT / "developmental-cognition-cycles"
            / prior_id for prior_id in cycle_ids[:cycle_index]]
        prefix_audit = verify_chain(plan_path=plan_path,
            cycle_roots=prior_cycle_roots, allow_prefix=True)
        prefix_boundaries = prefix_audit.get("cycle_boundaries", [])
        last_boundary = prefix_boundaries[-1]
        if (prefix_audit.get("append_only_history_chain_verified") is not True
                or prefix_audit.get("runtime_admission_chain_verified") is not True
                or prefix_audit.get("cognition_recovery_state_chain_verified")
                    is not True
                or not all(row.get("campaign_binding_verified") is True
                    and row.get("history_seed_boundary_verified") is True
                    and row.get("runtime_admission_ledger_append_only") is True
                    and row.get("cognition_recovery_state_append_only") is True
                    for row in prefix_boundaries)
                or last_boundary.get("cycle_id") != expected_prior_cycle_id
                or last_boundary.get("history_boundary_digest")
                    != before_history.get("boundary_digest")
                or last_boundary.get("cognition_recovery_state") != before_recovery
                or last_boundary.get("runtime_admission_ledger") != before_admission):
            raise ValueError("planned_preflight_prior_history_chain_invalid")
        prior_history_boundary_verification = {
            "status": "append_only_campaign_prefix_verified",
            "verified_prefix_cycle_ids": list(cycle_ids[:cycle_index]),
            "prefix_audit_digest": prefix_audit.get("audit_digest"),
            "boundary_digest": before_history["boundary_digest"],
            "append_only_history_chain_verified": True,
        }

    state = _read_json(state_root / "composition_state.json")
    state_semantic = {key: value for key, value in state.items()
        if key != "state_digest"}
    if state.get("state_digest") != _digest(state_semantic):
        raise ValueError("planned_preflight_composition_state_digest_invalid")
    record_root = history_root / "records"
    expected_refs: dict[str, str] = {}
    for row in before_history["files"]:
        relative = row["path"]
        if relative.startswith("records/") and relative.endswith(".json"):
            record_id = relative[len("records/"):-len(".json")]
            record = _read_json(record_root / (record_id + ".json"))
            if record.get("record_id") != record_id:
                raise ValueError("planned_preflight_initial_record_invalid")
            expected_refs[record_id] = record.get("record_digest")

    acquisition_task, transfer_task = (
        rootless_integer_affine_transfer_task_pair(task_seed,
            task_family_id=family,
            transfer_probe_count=plan.get("transfer_probe_count", 3)))
    acquisition_inputs = (acquisition_task.probe_input,
        *acquisition_task.additional_probe_inputs)
    transfer_inputs = (transfer_task.probe_input,
        *transfer_task.additional_probe_inputs)
    objective_descriptor = transfer_task.public_descriptor()
    objective_descriptor["task_digest"] = "sha256:" + "0" * 64
    store = _ReadOnlyRecordStore(record_root, expected_refs)
    owner = ResidentDevelopmentalCognitionOwner.__new__(
        ResidentDevelopmentalCognitionOwner)
    owner.config = SimpleNamespace(max_retrieved_records=4,
        allowed_source_kinds=("embodiment",), max_selected_facts=16,
        semantic_history_model_id=None, semantic_history_model_revision=None,
        state_root=None)
    owner.writeback = _ReadOnlyWriteback(store)
    owner.objective_task = transfer_task
    history_families = transfer_task.history_task_family_ids or (family,)
    cross_range_history_eligibility: dict[str, Any] | None = None
    cross_range_protocol = plan.get("cross_range_history_enabled_competence")
    if isinstance(cross_range_protocol, Mapping):
        from scripts.run_rootless_ollama_embodied_cognition_cycle import (
            _cross_range_history_competence_eligibility)
        cross_range_history_eligibility = (
            _cross_range_history_competence_eligibility(
                owner=owner, transfer_task=transfer_task,
                source_task_family_id=cross_range_protocol[
                    "source_task_family_id"],
                target_model_identity=identity))
    owner_ranking_metadata: dict[str, Any] = {}
    projection = owner._prior_projection(state, cycle_id + ":planned-transfer-preflight",
        task_family_id=family, task_probe_inputs=transfer_inputs,
        target_model_identity=identity, require_task_family_history=True,
        use_semantic_retrieval=False,
        retrieval_metadata=owner_ranking_metadata)
    _verify_owner_ranking_trace(owner_ranking_metadata.get(
        "task_family_ranking_trace"), projection.requested_record_ids)
    if tuple(projection.requested_record_ids) != tuple(
            row["record_id"] for row in projection.records):
        raise ValueError("planned_preflight_owner_selection_invalid")

    timestamp_placeholder = "2026-11-22T00:00:00.000000+00:00"
    body_observation = make_synthetic_pre_action_proprioception_observation(
        run_id=cycle_id, pose="idle", observed_at=timestamp_placeholder)
    snapshot_records = EmbodimentEvidenceOwner(
        [body_observation]).world_state_records()
    snapshot = WorldStateBoardBuilder(
        clock=lambda: datetime.fromisoformat(timestamp_placeholder)).build(
            snapshot_records)
    current = owner._current_projection(snapshot)
    current = owner._exclude_retained_task_facts(
        current, projection.records, family)
    current_evidence = _current_evidence_prompt_payload(
        current, target_model_identity=identity)
    instruction_template = _experiment_instruction_template(current)

    def bind_evidence(evidence_payload: dict[str, Any], *,
            history_records: tuple[dict[str, Any], ...] | None = None,
            task_probe_inputs: tuple[int, ...] | None = None,
            task_descriptor: dict[str, Any] | None = None,
            expected_history_record_ids: tuple[str, ...] | None = None
            ) -> dict[str, Any]:
        records = projection.records if history_records is None else history_records
        probe_inputs = transfer_inputs if task_probe_inputs is None else task_probe_inputs
        descriptor = objective_descriptor if task_descriptor is None else task_descriptor
        context = {
            "instruction": instruction_template["instruction"],
            "current_evidence": evidence_payload,
            "developmental_history_task_family_id": family,
            "developmental_history_task_family_history_required": True,
            "developmental_history_target_model_identity": identity,
            "developmental_history_retrieval_policy_id": (
                projection.retrieval_policy_id or
                "task_family_outcome_then_scored_example_coverage_then_model_probe_overlap_recency:v10"),
            "objective_task": descriptor,
        }
        bound, metadata, prompt, selected_ids, selected_digests = (
            _bind_history_and_epistemic_context(context=context,
                records=records, projection=None,
                history_present=True, compact_history_for_input=True,
                expected_history_record_ids=expected_history_record_ids,
                max_input_chars=ROOTLESS_DEVELOPMENTAL_COGNITION_INPUT_CHAR_LIMIT))
        prompt_digest = _digest({"prompt": prompt})
        family_projection = _task_family_history_prompt_projection(bound,
            condition_id="history_present", task_family_id=family,
            task_probe_inputs=probe_inputs,
            governed_request_prompt_digest=prompt_digest[7:], prompt=prompt)
        strategy = bound.get("task_family_accumulated_candidate_strategy")
        strategy_provenance = family_projection.get(
            "accumulated_candidate_integer_affine_strategy")
        return {
            "bound": bound,
            "prompt": prompt,
            "prompt_digest": prompt_digest,
            "selected_ids": selected_ids,
            "selected_digests": selected_digests,
            "history_selection": metadata.get(
                "developmental_history_selection"),
            "strategy": strategy,
            "strategy_provenance": strategy_provenance,
            "family_projection": family_projection,
        }

    acquisition_ranking_metadata: dict[str, Any] = {}
    owner.objective_task = acquisition_task
    acquisition_projection = owner._prior_projection(state,
        cycle_id + ":planned-acquisition-preflight",
        task_family_id=family, task_probe_inputs=acquisition_inputs,
        target_model_identity=identity, require_task_family_history=True,
        use_semantic_retrieval=False,
        retrieval_metadata=acquisition_ranking_metadata)
    owner.objective_task = transfer_task
    _verify_owner_ranking_trace(acquisition_ranking_metadata.get(
        "task_family_ranking_trace"), acquisition_projection.requested_record_ids)
    if tuple(acquisition_projection.requested_record_ids) != tuple(
            row["record_id"] for row in acquisition_projection.records):
        raise ValueError("planned_preflight_acquisition_owner_selection_invalid")
    acquisition_snapshot_projection = owner._current_projection(snapshot)
    acquisition_current = owner._exclude_retained_task_facts(
        acquisition_snapshot_projection, acquisition_projection.records, family)
    acquisition_current_evidence = _current_evidence_prompt_payload(
        acquisition_current, target_model_identity=identity)
    acquisition_descriptor = acquisition_task.public_descriptor()
    acquisition_descriptor["task_digest"] = "sha256:" + "0" * 64
    acquisition_bound_result = bind_evidence(acquisition_current_evidence,
        history_records=acquisition_projection.records,
        task_probe_inputs=acquisition_inputs,
        task_descriptor=acquisition_descriptor)
    acquisition_binder_ids = acquisition_bound_result["selected_ids"]
    acquisition_binder_id_set = set(acquisition_binder_ids)
    acquisition_binder_records = tuple(record for record in
        acquisition_projection.records
        if record.get("record_id") in acquisition_binder_id_set)
    if ({record.get("record_id") for record in acquisition_binder_records}
            != acquisition_binder_id_set):
        raise ValueError("planned_preflight_acquisition_binder_records_invalid")
    acquisition_family_projection = acquisition_bound_result["family_projection"]
    planned_acquisition_probe_reuse = {
        "schema_version": "sentientos.rootless_planned_cycle_acquisition_probe_reuse:v1",
        "acquisition_probe_inputs": list(acquisition_inputs),
        "acquisition_probe_input_digest": _digest({
            "probe_inputs": list(acquisition_inputs)}),
        "owner_selected_record_ids": list(
            acquisition_projection.requested_record_ids),
        "binder_selected_record_ids": list(acquisition_binder_ids),
        "owner_selected_record_overlaps": _record_probe_overlap(
            acquisition_projection.records, family=history_families,
            probe_inputs=acquisition_inputs),
        "binder_selected_prompt_record_overlaps": _record_probe_overlap(
            acquisition_binder_records, family=history_families,
            probe_inputs=acquisition_inputs),
        "prompt_projection_overlap_input_count": acquisition_family_projection.get(
            "historical_probe_overlap_input_count"),
        "prompt_projection_overlap_input_digest": acquisition_family_projection.get(
            "historical_probe_overlap_input_digest"),
        "prompt_projection_overlap_example_count": acquisition_family_projection.get(
            "historical_probe_overlap_example_count"),
        "prompt_projection_overlap_measurement_complete": (
            acquisition_family_projection.get(
                "historical_probe_overlap_measurement_complete")),
        "no_exact_history_probe_overlap": (
            acquisition_family_projection.get(
                "historical_probe_overlap_measurement_complete") is True
            and acquisition_family_projection.get(
                "historical_probe_overlap_input_count") == 0),
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
    }
    if (family == ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY
            and not planned_acquisition_probe_reuse[
                "no_exact_history_probe_overlap"]):
        raise ValueError("planned_preflight_novel_acquisition_history_overlap")

    bound_result = bind_evidence(current_evidence)
    bound = bound_result["bound"]
    prompt = bound_result["prompt"]
    prompt_digest = bound_result["prompt_digest"]
    selected_ids = bound_result["selected_ids"]
    selected_digests = bound_result["selected_digests"]
    strategy = bound_result["strategy"]
    family_projection = bound_result["family_projection"]
    frozen_selection_result = bind_evidence(current_evidence,
        expected_history_record_ids=tuple(selected_ids))
    original_history_selection = bound_result.get("history_selection")
    frozen_history_selection = frozen_selection_result.get("history_selection")
    if (not isinstance(original_history_selection, Mapping)
            or not isinstance(frozen_history_selection, Mapping)
            or frozen_selection_result.get("selected_ids") != selected_ids
            or frozen_selection_result.get("selected_digests") != selected_digests
            or dict(frozen_history_selection) != dict(original_history_selection)):
        raise ValueError("planned_preflight_frozen_history_selection_replay_mismatch")
    frozen_history_selection_replay = {
        "schema_version": (
            "sentientos.rootless_planned_cycle_frozen_history_selection_replay:v1"),
        "expected_record_ids": list(selected_ids),
        "selected_record_ids": list(frozen_selection_result["selected_ids"]),
        "selected_record_digests": list(
            frozen_selection_result["selected_digests"]),
        "available_records_digest": _digest(
            frozen_history_selection.get("available_records")),
        "selection_digest": frozen_history_selection.get("selection_digest"),
        "full_available_inventory_preserved": (
            frozen_history_selection.get("available_records") ==
                original_history_selection.get("available_records")),
        "selection_metadata_unchanged": True,
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
    }
    selected_id_set = set(selected_ids)
    binder_selected_records = tuple(record for record in projection.records
        if record.get("record_id") in selected_id_set)
    if ({record.get("record_id") for record in binder_selected_records}
            != selected_id_set):
        raise ValueError("planned_preflight_binder_overlap_records_invalid")
    planned_seed_probe_reuse = {
        "schema_version": "sentientos.rootless_planned_cycle_probe_reuse:v1",
        "transfer_probe_inputs": list(transfer_inputs),
        "transfer_probe_input_digest": _digest({
            "probe_inputs": list(transfer_inputs)}),
        "owner_selected_record_overlaps": _record_probe_overlap(
            projection.records, family=history_families,
            probe_inputs=transfer_inputs),
        "binder_selected_prompt_record_overlaps": _record_probe_overlap(
            binder_selected_records, family=history_families,
            probe_inputs=transfer_inputs),
        "prompt_projection_overlap_input_count": family_projection.get(
            "historical_probe_overlap_input_count"),
        "prompt_projection_overlap_input_digest": family_projection.get(
            "historical_probe_overlap_input_digest"),
        "prompt_projection_overlap_example_count": family_projection.get(
            "historical_probe_overlap_example_count"),
        "prompt_projection_overlap_measurement_complete": family_projection.get(
            "historical_probe_overlap_measurement_complete"),
        "posture": ("planned_transfer_reuses_historical_probe_inputs"
            if family_projection.get("historical_probe_overlap_input_count", 0) > 0
            else "planned_transfer_probe_set_disjoint_from_selected_history"
            if family_projection.get(
                "historical_probe_overlap_measurement_complete") is True
            else "planned_transfer_probe_overlap_unmeasured"),
        "held_out_transfer_qualified": (
            family_projection.get(
                "historical_probe_overlap_measurement_complete") is True
            and family_projection.get(
                "historical_probe_overlap_input_count") == 0),
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
    }
    seed_sensitivity_rows: list[dict[str, Any]] = []
    for seed in range(task_seed + 1,
            task_seed + alternate_seed_count + 1):
        seeded_acquisition, seeded_transfer = (
            rootless_integer_affine_transfer_task_pair(seed,
                task_family_id=family,
                transfer_probe_count=plan.get("transfer_probe_count", 3)))
        seeded_acquisition_inputs = (seeded_acquisition.probe_input,
            *seeded_acquisition.additional_probe_inputs)
        seeded_transfer_inputs = (seeded_transfer.probe_input,
            *seeded_transfer.additional_probe_inputs)
        seeded_ranking_metadata: dict[str, Any] = {}
        seeded_projection = owner._prior_projection(state,
            cycle_id + ":seed-sensitivity:" + str(seed),
            task_family_id=family, task_probe_inputs=seeded_transfer_inputs,
            target_model_identity=identity, require_task_family_history=True,
            use_semantic_retrieval=False,
            retrieval_metadata=seeded_ranking_metadata)
        if tuple(seeded_projection.requested_record_ids) != tuple(
                row["record_id"] for row in seeded_projection.records):
            raise ValueError("planned_preflight_seed_owner_selection_invalid")
        _verify_owner_ranking_trace(seeded_ranking_metadata.get(
            "task_family_ranking_trace"), seeded_projection.requested_record_ids)
        seeded_descriptor = seeded_transfer.public_descriptor()
        seeded_descriptor["task_digest"] = "sha256:" + "0" * 64
        seeded_result = bind_evidence(current_evidence,
            history_records=seeded_projection.records,
            task_probe_inputs=seeded_transfer_inputs,
            task_descriptor=seeded_descriptor)
        seeded_strategy = seeded_result["strategy"]
        seeded_strategy_source_audit = _strategy_source_family_audit(
            seeded_result["strategy_provenance"],
            declared_history_families=history_families)
        seeded_identity_audit = _strategy_model_identity_audit(
            seeded_result["strategy_provenance"],
            target_active_model_identity=identity,
            source_records=tuple(record for record in seeded_projection.records
                if record.get("record_id") in set(seeded_result["selected_ids"])),
            source_task_family_ids=history_families)
        seeded_ranking_trace = seeded_ranking_metadata.get(
            "task_family_ranking_trace", [])
        binder_matches_owner_top = (
            isinstance(seeded_ranking_trace, list)
            and {row.get("record_id") for row in seeded_ranking_trace[
                :len(seeded_result["selected_ids"])]}
                == set(seeded_result["selected_ids"]))
        seeded_acquisition_ranking: dict[str, Any] = {}
        owner.objective_task = seeded_acquisition
        seeded_acquisition_projection = owner._prior_projection(state,
            cycle_id + ":seed-acquisition-sensitivity:" + str(seed),
            task_family_id=family,
            task_probe_inputs=seeded_acquisition_inputs,
            target_model_identity=identity, require_task_family_history=True,
            use_semantic_retrieval=False,
            retrieval_metadata=seeded_acquisition_ranking)
        owner.objective_task = transfer_task
        if tuple(seeded_acquisition_projection.requested_record_ids) != tuple(
                row["record_id"] for row in seeded_acquisition_projection.records):
            raise ValueError(
                "planned_preflight_seed_acquisition_owner_selection_invalid")
        _verify_owner_ranking_trace(seeded_acquisition_ranking.get(
            "task_family_ranking_trace"),
            seeded_acquisition_projection.requested_record_ids)
        seeded_acquisition_base = owner._current_projection(snapshot)
        seeded_acquisition_current = owner._exclude_retained_task_facts(
            seeded_acquisition_base, seeded_acquisition_projection.records, family)
        seeded_acquisition_evidence = _current_evidence_prompt_payload(
            seeded_acquisition_current, target_model_identity=identity)
        seeded_acquisition_descriptor = seeded_acquisition.public_descriptor()
        seeded_acquisition_descriptor["task_digest"] = "sha256:" + "0" * 64
        seeded_acquisition_result = bind_evidence(
            seeded_acquisition_evidence,
            history_records=seeded_acquisition_projection.records,
            task_probe_inputs=seeded_acquisition_inputs,
            task_descriptor=seeded_acquisition_descriptor)
        seeded_acquisition_ids = seeded_acquisition_result["selected_ids"]
        seeded_acquisition_id_set = set(seeded_acquisition_ids)
        seeded_acquisition_binder_records = tuple(record for record in
            seeded_acquisition_projection.records
            if record.get("record_id") in seeded_acquisition_id_set)
        if ({record.get("record_id") for record in
                seeded_acquisition_binder_records}
                != seeded_acquisition_id_set):
            raise ValueError(
                "planned_preflight_seed_acquisition_binder_records_invalid")
        seeded_acquisition_family_projection = (
            seeded_acquisition_result["family_projection"])
        seeded_acquisition_no_overlap = (
            seeded_acquisition_family_projection.get(
                "historical_probe_overlap_measurement_complete") is True
            and seeded_acquisition_family_projection.get(
                "historical_probe_overlap_input_count") == 0
            and len(seeded_acquisition_result["prompt"]) <=
                ROOTLESS_DEVELOPMENTAL_COGNITION_INPUT_CHAR_LIMIT)
        seed_sensitivity_rows.append({
            "task_generation_seed": seed,
            "acquisition_probe_inputs": list(seeded_acquisition_inputs),
            "acquisition_owner_selected_record_ids": list(
                seeded_acquisition_projection.requested_record_ids),
            "acquisition_binder_selected_record_ids": list(
                seeded_acquisition_ids),
            "acquisition_owner_selected_record_overlaps": _record_probe_overlap(
                seeded_acquisition_projection.records,
                family=history_families,
                probe_inputs=seeded_acquisition_inputs),
            "acquisition_binder_selected_record_overlaps": _record_probe_overlap(
                seeded_acquisition_binder_records,
                family=history_families,
                probe_inputs=seeded_acquisition_inputs),
            "acquisition_prompt_projection_overlap_input_count": (
                seeded_acquisition_family_projection.get(
                    "historical_probe_overlap_input_count")),
            "acquisition_prompt_projection_overlap_measurement_complete": (
                seeded_acquisition_family_projection.get(
                    "historical_probe_overlap_measurement_complete")),
            "acquisition_prompt_within_bound": (
                len(seeded_acquisition_result["prompt"]) <=
                    ROOTLESS_DEVELOPMENTAL_COGNITION_INPUT_CHAR_LIMIT),
            "acquisition_no_exact_history_probe_overlap": (
                seeded_acquisition_no_overlap),
            "transfer_probe_inputs": list(seeded_transfer_inputs),
            "owner_selected_record_ids": list(
                seeded_projection.requested_record_ids),
            "owner_selected_record_probe_overlap": _record_probe_overlap(
                seeded_projection.records, family=history_families,
                probe_inputs=seeded_transfer_inputs),
            "owner_ranking_trace": seeded_ranking_metadata.get(
                "task_family_ranking_trace", []),
            "binder_selection_matches_top_owner_ranked_records": (
                binder_matches_owner_top),
            "binder_selected_record_ids": list(seeded_result["selected_ids"]),
            "accumulated_strategy_present": isinstance(seeded_strategy, dict),
            "accumulated_strategy_digest": (
                _digest(seeded_strategy) if isinstance(seeded_strategy, dict)
                else None),
            "accumulated_strategy_relation": (
                seeded_strategy.get("relation")
                if isinstance(seeded_strategy, dict) else None),
            "accumulated_strategy_core_digest": (
                _canonical_digest({key: seeded_strategy.get(key) for key in (
                    "task_family_id", "target_active_model_identity_digest",
                    "relation", "supporting_distinct_input_count",
                    "supporting_run_count")})
                if isinstance(seeded_strategy, dict) else None),
            "accumulated_strategy_run_count": (
                seeded_strategy.get("supporting_run_count")
                if isinstance(seeded_strategy, dict) else None),
            "accumulated_strategy_distinct_input_count": (
                seeded_strategy.get("supporting_distinct_input_count")
                if isinstance(seeded_strategy, dict) else None),
            "accumulated_strategy_source_family_audit": (
                seeded_strategy_source_audit),
            "accumulated_strategy_model_identity_audit": seeded_identity_audit,
            "prompt_chars": len(seeded_result["prompt"]),
            "prompt_within_bound": (len(seeded_result["prompt"]) <=
                ROOTLESS_DEVELOPMENTAL_COGNITION_INPUT_CHAR_LIMIT),
            "task_family_prompt_projection_verified": True,
            "task_family_prompt_projection_digest": (
                seeded_result["family_projection"]["projection_digest"]),
        })
    seed_strategy_digests = sorted({
        row["accumulated_strategy_digest"] for row in seed_sensitivity_rows
        if row["accumulated_strategy_digest"] is not None})
    seed_strategy_core_digests = sorted({
        row["accumulated_strategy_core_digest"]
        for row in seed_sensitivity_rows
        if row["accumulated_strategy_core_digest"] is not None})
    seed_strategy_relations = sorted({
        row["accumulated_strategy_relation"] for row in seed_sensitivity_rows
        if row["accumulated_strategy_relation"] is not None})
    seed_selection_sets = sorted({tuple(sorted(row[
        "binder_selected_record_ids"])) for row in seed_sensitivity_rows})
    seed_strategy_family_sets = sorted({tuple(
        row["accumulated_strategy_source_family_audit"][
            "history_task_family_ids"] or ()) for row in seed_sensitivity_rows})
    seed_model_identity_relation_sets = sorted({tuple(
        (item["relation"], item["source_count"])
        for item in row["accumulated_strategy_model_identity_audit"][
            "relation_counts"]) for row in seed_sensitivity_rows})
    seed_model_artifact_relation_sets = sorted({tuple(
        (item["relation"], item["source_count"])
        for item in row["accumulated_strategy_model_identity_audit"][
            "artifact_relation_counts"]) for row in seed_sensitivity_rows})
    seed_probe_sets = sorted({tuple(row["transfer_probe_inputs"])
        for row in seed_sensitivity_rows})
    seed_sensitivity_summary = {
        "seed_count": len(seed_sensitivity_rows),
        "acquisition_history_disjoint_seed_candidates": [
            row["task_generation_seed"] for row in seed_sensitivity_rows
            if row["acquisition_no_exact_history_probe_overlap"]],
        "acquisition_disjoint_candidate_count": sum(
            row["acquisition_no_exact_history_probe_overlap"]
            for row in seed_sensitivity_rows),
        "unique_transfer_probe_set_count": len(seed_probe_sets),
        "unique_binder_record_set_count": len(seed_selection_sets),
        "candidate_strategy_digest_count": len(seed_strategy_digests),
        "candidate_strategy_core_digest_count": len(seed_strategy_core_digests),
        "candidate_strategy_relations": seed_strategy_relations,
        "candidate_strategy_history_family_sets": [list(item)
            for item in seed_strategy_family_sets],
        "all_strategy_source_families_match_task": all(
            row["accumulated_strategy_source_family_audit"][
                "relation_matches_task"] is True for row in seed_sensitivity_rows),
        "all_seed_source_identity_relations_match_target_audit": all(
            row["accumulated_strategy_model_identity_audit"]["present"]
            and row["accumulated_strategy_model_identity_audit"][
                "omitted_source_count"] == 0
            for row in seed_sensitivity_rows),
        "unique_source_identity_relation_count_sets": [
            [{"relation": relation, "source_count": count}
                for relation, count in items]
            for items in seed_model_identity_relation_sets],
        "all_seed_source_artifact_relations_audited": all(
            row["accumulated_strategy_model_identity_audit"]["present"]
            and row["accumulated_strategy_model_identity_audit"][
                "omitted_source_count"] == 0
            for row in seed_sensitivity_rows),
        "all_seed_source_active_identities_differ_from_target": all(
            row["accumulated_strategy_model_identity_audit"][
                "all_sources_bound_to_different_active_identity"] is True
            for row in seed_sensitivity_rows),
        "all_seed_source_artifacts_differ_from_target": all(
            row["accumulated_strategy_model_identity_audit"][
                "all_source_artifacts_differ_from_target"] is True
            for row in seed_sensitivity_rows),
        "unique_source_model_artifact_relation_count_sets": [
            [{"relation": relation, "source_count": count}
                for relation, count in items]
            for items in seed_model_artifact_relation_sets],
        "all_binder_selections_match_owner_top_ranked_records": all(
            row["binder_selection_matches_top_owner_ranked_records"]
            for row in seed_sensitivity_rows),
        "unique_top_two_usable_input_count_pairs": sorted({tuple(
            item["usable_distinct_input_count"] for item in
            row["owner_ranking_trace"][:2])
            for row in seed_sensitivity_rows}),
        "unique_owner_probe_overlap_count_vectors": sorted({tuple(
            item["current_probe_overlap_count"] for item in
            row["owner_ranking_trace"])
            for row in seed_sensitivity_rows}),
        "all_seeds_retained_candidate_strategy": all(
            row["accumulated_strategy_present"] for row in seed_sensitivity_rows),
        "supporting_run_counts": sorted({
            row["accumulated_strategy_run_count"] for row in seed_sensitivity_rows
            if row["accumulated_strategy_run_count"] is not None}),
        "supporting_distinct_input_counts": sorted({
            row["accumulated_strategy_distinct_input_count"]
            for row in seed_sensitivity_rows
            if row["accumulated_strategy_distinct_input_count"] is not None}),
        "prompt_chars_min": min((row["prompt_chars"]
            for row in seed_sensitivity_rows), default=None),
        "prompt_chars_max": max((row["prompt_chars"]
            for row in seed_sensitivity_rows), default=None),
        "transfer_probe_sets": [list(item) for item in seed_probe_sets],
        "binder_record_sets": [list(item) for item in seed_selection_sets],
    }
    sensitivity_rows: list[dict[str, Any]] = []
    for extra_chars in (0, 128, 256, 320, 338, 339, 340, 341, 384, 512,
            768, 1024, 1536, *range(1552, 2048, 16), 2048, 3072, 4096,
            6144):
        sensitivity_evidence = dict(current_evidence)
        if extra_chars:
            sensitivity_evidence["preflight_synthetic_padding"] = "x" * extra_chars
        try:
            sensitivity = bind_evidence(sensitivity_evidence)
        except ResidentDevelopmentalCognitionError as exc:
            sensitivity_rows.append({
                "synthetic_padding_string_chars": extra_chars,
                "binding_status": "input_budget_rejected",
                "failure_code": getattr(exc, "code", "unknown"),
                "selected_record_count": 0,
                "strategy_run_count": None,
                "strategy_distinct_input_count": None,
            })
            continue
        sensitivity_strategy = sensitivity["strategy"]
        serialized_evidence_chars = len(json.dumps(sensitivity_evidence,
            sort_keys=True, separators=(",", ":"), ensure_ascii=True))
        baseline_evidence_chars = len(json.dumps(current_evidence,
            sort_keys=True, separators=(",", ":"), ensure_ascii=True))
        sensitivity_rows.append({
            "synthetic_padding_string_chars": extra_chars,
            "additional_serialized_evidence_chars": (
                serialized_evidence_chars - baseline_evidence_chars),
            "binding_status": "bound",
            "prompt_chars": len(sensitivity["prompt"]),
            "prompt_margin_chars": (ROOTLESS_DEVELOPMENTAL_COGNITION_INPUT_CHAR_LIMIT
                - len(sensitivity["prompt"])),
            "selected_record_count": len(sensitivity["selected_ids"]),
            "selected_record_ids": list(sensitivity["selected_ids"]),
            "strategy_run_count": (sensitivity_strategy.get(
                "supporting_run_count") if isinstance(sensitivity_strategy, dict)
                else None),
            "strategy_distinct_input_count": (sensitivity_strategy.get(
                "supporting_distinct_input_count")
                if isinstance(sensitivity_strategy, dict) else None),
            "task_family_prompt_projection_verified": True,
            "task_family_prompt_projection_digest": (
                sensitivity["family_projection"]["projection_digest"]),
        })
    baseline_strategy_row = next((row for row in sensitivity_rows
        if row.get("synthetic_padding_string_chars") == 0), None)
    expected_strategy_run_count = (baseline_strategy_row.get(
        "strategy_run_count") if isinstance(baseline_strategy_row, Mapping)
        else None)
    expected_strategy_distinct_input_count = (baseline_strategy_row.get(
        "strategy_distinct_input_count")
        if isinstance(baseline_strategy_row, Mapping) else None)
    def retains_baseline_strategy(row: Mapping[str, Any]) -> bool:
        return (type(expected_strategy_run_count) is int
            and type(expected_strategy_distinct_input_count) is int
            and row.get("strategy_run_count") == expected_strategy_run_count
            and row.get("strategy_distinct_input_count") ==
                expected_strategy_distinct_input_count)
    retained_rows = [row for row in sensitivity_rows
        if retains_baseline_strategy(row)]
    retained_max = max((row["synthetic_padding_string_chars"]
        for row in retained_rows), default=None)
    first_retained_padding = min((row["synthetic_padding_string_chars"]
        for row in retained_rows), default=None)
    first_lost = next((row for row in sensitivity_rows
        if first_retained_padding is not None
        and row["synthetic_padding_string_chars"] > first_retained_padding
        and not retains_baseline_strategy(row)), None)
    strategy_transition = {
        "observed_padding_resolution_chars": 16,
        "largest_observed_padding_with_strategy": retained_max,
        "largest_observed_serialized_evidence_delta_with_strategy": next((
            row["additional_serialized_evidence_chars"] for row in retained_rows
            if row["synthetic_padding_string_chars"] == retained_max), None),
        "first_observed_padding_without_strategy": (
            first_lost["synthetic_padding_string_chars"] if first_lost else None),
        "first_lost_strategy_prompt_chars": (
            first_lost.get("prompt_chars") if first_lost else None),
        "first_lost_strategy_prompt_margin_chars": (
            first_lost.get("prompt_margin_chars") if first_lost else None),
        "strategy_reappeared_after_first_observed_loss": bool(first_lost and any(
            row["synthetic_padding_string_chars"] > first_lost[
                "synthetic_padding_string_chars"]
            and retains_baseline_strategy(row)
            for row in sensitivity_rows)),
    }
    strategy = bound.get("task_family_accumulated_candidate_strategy")
    strategy_source_audit = _strategy_source_family_audit(
        bound_result["strategy_provenance"],
        declared_history_families=history_families)
    strategy_identity_audit = _strategy_model_identity_audit(
        bound_result["strategy_provenance"],
        target_active_model_identity=identity,
        source_records=binder_selected_records,
        source_task_family_ids=history_families)
    strategy_inclusion_ablation = _strategy_inclusion_ablation(bound,
        baseline_prompt=prompt, selected_record_ids=selected_ids,
        selected_record_digests=selected_digests)
    historical_examples_ablation = _historical_examples_ablation(bound,
        baseline_prompt=prompt, selected_record_ids=selected_ids,
        selected_record_digests=selected_digests,
        heldout_probe_inputs=transfer_inputs,
        family_projection=family_projection)
    negative_example_ablation = _negative_example_ablation(bound,
        baseline_prompt=prompt, selected_record_ids=selected_ids,
        selected_record_digests=selected_digests,
        heldout_probe_inputs=transfer_inputs,
        projected_negative_example_count=family_projection.get(
            "prior_incorrect_example_count", 0))
    after_history = _history_boundary(history_root)
    after_recovery = _cognition_recovery_state_boundary(state_root)
    after_admission = _runtime_admission_boundary(history_root)
    if (after_history != before_history or after_recovery != before_recovery
            or after_admission != before_admission):
        raise ValueError("planned_preflight_source_boundary_changed")

    report: dict[str, Any] = {
        "schema_version": "sentientos.rootless_planned_cycle_owner_preflight:v21",
        "campaign_id": plan["campaign_id"],
        "plan_digest": plan["plan_digest"],
        "experiment_implementation_sha256_digest": digest_payload(
            dict(plan["experiment_implementation_sha256"])),
        "cycle_id": cycle_id,
        "task_family_id": family,
        "cross_range_history_enabled_competence_eligibility": ({
            "protocol": dict(cross_range_protocol),
            **cross_range_history_eligibility,
        } if isinstance(cross_range_protocol, Mapping)
            and isinstance(cross_range_history_eligibility, Mapping) else {
                "status": "not_preregistered",
                "inference_performed": False,
                "learning_established": False,
                "authority": False,
            }),
        "history_task_family_ids": list(history_families),
        "task_generation_seed": task_seed,
        "task_generator": "rootless_integer_affine_transfer_task_pair:v1",
        "acquisition_probe_inputs": list(acquisition_inputs),
        "transfer_probe_inputs": list(transfer_inputs),
        "objective_task_descriptor_digest": _digest(objective_descriptor),
        "objective_task_descriptor_chars": len(json.dumps(objective_descriptor,
            sort_keys=True, separators=(",", ":"), ensure_ascii=True)),
        "objective_task_descriptor_posture": (
            "public_descriptor_shape_with_zeroed_commitment_digest_for_reproducibility"),
        "prior_history_root_cycle_id": cycle_root.name,
        "prior_history_boundary_digest": before_history["boundary_digest"],
        "prior_history_boundary_verification": (
            prior_history_boundary_verification),
        "prior_recovery_state_boundary_digest": before_recovery["boundary_digest"],
        "prior_runtime_admission_ledger_digest": (
            before_admission.get("sha256") if isinstance(before_admission, dict)
            else None),
        "composition_state_digest": state["state_digest"],
        "composition_state_digest_verified": True,
        "target_model_identity_digest": identity_digest,
        "target_model_identity_matches_plan": True,
        "owner_selected_record_ids": list(projection.requested_record_ids),
        "owner_ranking_trace_schema": owner_ranking_metadata.get(
            "task_family_ranking_trace_schema"),
        "owner_ranking_trace": owner_ranking_metadata.get(
            "task_family_ranking_trace", []),
        "binder_selected_record_ids": list(selected_ids),
        "binder_selected_record_digests": list(selected_digests),
        "frozen_history_selection_replay": frozen_history_selection_replay,
        "planned_acquisition_probe_reuse": planned_acquisition_probe_reuse,
        "planned_seed_probe_reuse": planned_seed_probe_reuse,
        "accumulated_strategy_present": isinstance(strategy, dict),
        "accumulated_strategy_schema_version": (
            strategy.get("schema_version") if isinstance(strategy, dict) else None),
        "accumulated_strategy_run_count": (
            strategy.get("supporting_run_count") if isinstance(strategy, dict) else None),
        "accumulated_strategy_distinct_input_count": (
            strategy.get("supporting_distinct_input_count")
            if isinstance(strategy, dict) else None),
        "accumulated_strategy_source_family_audit": strategy_source_audit,
        "accumulated_strategy_model_identity_audit": strategy_identity_audit,
        "strategy_inclusion_ablation": strategy_inclusion_ablation,
        "historical_examples_ablation": historical_examples_ablation,
        "negative_example_ablation": negative_example_ablation,
        "prompt_chars": len(prompt),
        "prompt_digest": prompt_digest,
        "prompt_limit_chars": ROOTLESS_DEVELOPMENTAL_COGNITION_INPUT_CHAR_LIMIT,
        "prompt_within_bound": (len(prompt)
            <= ROOTLESS_DEVELOPMENTAL_COGNITION_INPUT_CHAR_LIMIT),
        "task_family_prompt_projection_verified": True,
        "task_family_prompt_projection_schema": family_projection["schema_version"],
        "task_family_prompt_projection_digest": family_projection["projection_digest"],
        "negative_example_delivery": {
            "transfer": {
                "record_ids": sorted({item.get("record_id") for item in
                    family_projection.get("prior_incorrect_examples", [])
                    if isinstance(item, Mapping) and isinstance(
                        item.get("record_id"), str)}),
                "example_count": family_projection.get(
                    "prior_incorrect_example_count", 0),
                "no_imitation_instruction_present": (
                    not family_projection.get("prior_incorrect_example_count", 0)
                    or TASK_FAMILY_PRIOR_INCORRECT_EXAMPLE_INSTRUCTION in prompt),
            },
            "acquisition": {
                "record_ids": sorted({item.get("record_id") for item in
                    acquisition_family_projection.get(
                        "prior_incorrect_examples", [])
                    if isinstance(item, Mapping) and isinstance(
                        item.get("record_id"), str)}),
                "example_count": acquisition_family_projection.get(
                    "prior_incorrect_example_count", 0),
                "no_imitation_instruction_present": (
                    not acquisition_family_projection.get(
                        "prior_incorrect_example_count", 0)
                    or TASK_FAMILY_PRIOR_INCORRECT_EXAMPLE_INSTRUCTION
                        in acquisition_bound_result["prompt"]),
            },
            "historical_only": family_projection.get("historical_only"),
            "current_truth": family_projection.get("current_truth"),
            "authority": family_projection.get("authority"),
        },
        "current_evidence_posture": (
            "runner_shared_pre_action_body_snapshot_shape_with_fixed_timestamp_placeholder"),
        "current_snapshot_digest": snapshot.digest,
        "current_projection_digest": current.projection_digest,
        "current_evidence_payload_digest": _canonical_digest(current_evidence),
        "current_evidence_payload_chars": len(json.dumps(current_evidence,
            sort_keys=True, separators=(",", ":"), ensure_ascii=True)),
        "budget_sensitivity_padding_field": "preflight_synthetic_padding",
        "current_observation_timestamp_posture": "fixed_length_placeholder_value",
        "instruction_template_matches_static_experiment_instruction": (
            instruction_template["instruction"] == EXPERIMENT_CONTEXT_INSTRUCTION),
        "budget_sensitivity_posture": (
            "synthetic_extra_evidence_field; serialized_json_overhead_counted; acquisition_history_absent"),
        "input_budget_sensitivity": sensitivity_rows,
        "strategy_retention_transition": strategy_transition,
        "alternate_seed_sensitivity_posture": (
            f"{alternate_seed_count}_alternate_deterministic_task_seeds; "
            "posthoc_owner_and_prompt_coverage_only; no_inference"),
        "owner_record_probe_overlap_posture": (
            "planned_seed_owner_and_exact_binder_prompt_record_overlap_recomputed; "
            "descriptive_only; does_not_establish_model_attention_or_learning"),
        "owner_ranking_trace_posture": (
            "score_bound_coverage_then_model_probe_recency_comparator; "
            "diagnostic_metadata_only; labels_remain_unchanged; no_learning_claim"),
        "alternate_seed_sensitivity": seed_sensitivity_rows,
        "alternate_seed_sensitivity_summary": seed_sensitivity_summary,
        "model_generated_acquisition_outputs_available": False,
        "exact_cycle_prompt_reconstructed": False,
        "exact_cycle_prompt_limitation": (
            "model_generated_acquisition_record_absent_and_observation_timestamp_is_placeholder"),
        "inference_performed": False,
        "model_attention_established": False,
        "learning_established": False,
        "authority": False,
    }
    report["audit_digest"] = _canonical_digest(report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--prior-history-root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cycle-index", type=int, default=0,
        help="planned cycle to audit; performs CPU-only owner/binder preparation")
    parser.add_argument("--alternate-seed-count", type=int, default=16,
        help="number of consecutive deterministic seeds to screen (1-2048)")
    args = parser.parse_args()
    report = create_report(plan_path=args.plan,
        prior_history_root=args.prior_history_root,
        manifest_path=args.manifest, model_name=args.model_name,
        output_path=args.output, cycle_index=args.cycle_index,
        alternate_seed_count=args.alternate_seed_count)
    print(json.dumps({key: report[key] for key in (
        "audit_digest", "schema_version", "cycle_id", "transfer_probe_inputs",
        "owner_selected_record_ids", "binder_selected_record_ids",
        "accumulated_strategy_run_count",
        "accumulated_strategy_distinct_input_count",
        "accumulated_strategy_model_identity_audit", "prompt_chars",
        "strategy_inclusion_ablation",
        "historical_examples_ablation",
        "negative_example_ablation",
        "prompt_within_bound", "strategy_retention_transition",
        "alternate_seed_sensitivity_posture",
        "planned_acquisition_probe_reuse",
        "planned_seed_probe_reuse",
        "owner_record_probe_overlap_posture",
        "owner_ranking_trace_posture",
        "alternate_seed_sensitivity_summary", "inference_performed")},
        sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
