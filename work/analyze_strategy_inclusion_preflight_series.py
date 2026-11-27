#!/usr/bin/env python3
"""Reduce a frozen strategy-inclusion task series from persisted score records.

This CPU-only analyzer verifies series, preflight, runner, protocol, score, and
arm-result bindings before reporting task-level outcomes. It never loads a
model or reads raw model answer values from score records.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sentientos.developmental_history_intervention_experiment import (
    _strategy_intervention_digest,
)
from sentientos.local_model_authority import digest_payload
from work.strategy_inclusion_intervention import (
    _digest,
    validate_strategy_inclusion_protocol,
)

_HEX_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_RAW_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_RECEIPT_ID = re.compile(r"lmrec-[0-9a-f]{24}\Z")
_REQUEST_ID = re.compile(r"lmreq-[0-9a-f]{24}\Z")
_ARMS = ("strategy_included", "strategy_omitted")
_OUTCOMES = {"correct", "incorrect", "abstained"}
_MAX_JSON_BYTES = 16 * 1024 * 1024


class SeriesAnalysisError(ValueError):
    """A runtime record does not match the frozen analysis bindings."""


def _read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise SeriesAnalysisError("runtime_artifact_missing_or_not_regular")
    raw = path.read_bytes()
    if len(raw) > _MAX_JSON_BYTES:
        raise SeriesAnalysisError("runtime_artifact_too_large")
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SeriesAnalysisError("runtime_artifact_invalid_json") from exc
    if not isinstance(value, dict):
        raise SeriesAnalysisError("runtime_artifact_not_object")
    return value, raw


def _file_digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _require_digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_DIGEST.fullmatch(value) is None:
        raise SeriesAnalysisError(code)
    return value


def _valid_raw_digest(value: Any) -> bool:
    return isinstance(value, str) and _RAW_DIGEST.fullmatch(value) is not None


def _load_and_verify_task(*, task: Mapping[str, Any], analysis: Mapping[str, Any],
        series: Mapping[str, Any], series_root: Path,
        runtime_entry: Mapping[str, Any]) -> dict[str, Any]:
    seed = task.get("task_seed")
    if (type(seed) is not int or runtime_entry.get("task_seed") != seed
            or runtime_entry.get("cycle_id") not in
                analysis.get("expected_cycle_ids", ())):
        raise SeriesAnalysisError("runtime_manifest_task_binding_invalid")
    cycle_id = runtime_entry.get("cycle_id")
    cycle_root_value = runtime_entry.get("cycle_root")
    journal_root_value = runtime_entry.get("journal_root")
    if (not isinstance(cycle_id, str) or not isinstance(cycle_root_value, str)
            or not isinstance(journal_root_value, str)):
        raise SeriesAnalysisError("runtime_manifest_paths_invalid")
    attempt_status = runtime_entry.get("attempt_status")
    if attempt_status not in {"not_started", "failed", "completed", "unknown"}:
        raise SeriesAnalysisError("runtime_manifest_attempt_status_invalid")
    if attempt_status != "completed":
        raise SeriesAnalysisError("strategy_pair_attempt_not_completed")
    reported_failure_code = runtime_entry.get("failure_code")
    if (reported_failure_code is not None
            and (not isinstance(reported_failure_code, str)
                or len(reported_failure_code) > 160)):
        raise SeriesAnalysisError("runtime_manifest_failure_code_invalid")
    cycle_root = Path(cycle_root_value).expanduser()
    journal_root = Path(journal_root_value).expanduser()
    if (not cycle_root.is_absolute() or not journal_root.is_absolute()
            or cycle_root.is_symlink() or not cycle_root.is_dir()
            or cycle_root.name != cycle_id or journal_root.is_symlink()
            or not journal_root.is_dir()):
        raise SeriesAnalysisError("runtime_roots_invalid")

    preflight_version = task.get("preflight_version")
    verification_version = task.get("verification_version")
    if (type(preflight_version) is not int or type(verification_version) is not int):
        raise SeriesAnalysisError("series_task_artifact_version_invalid")
    preflight_name = f"strategy_inclusion_cpu_preflight_v{preflight_version}.json"
    verification_name = (
        f"strategy_inclusion_cpu_verification_v{verification_version}.json")
    preflight_path = series_root / preflight_name
    verification_path = series_root / verification_name
    preflight, preflight_raw = _read_json(preflight_path)
    verification, verification_raw = _read_json(verification_path)
    input_digests = series.get("input_digests")
    preflight_protocol = preflight.get("strategy_pair_protocol")
    owner_protocols = preflight.get("owner_arm_protocols")
    included_owner = (owner_protocols.get("strategy_included")
        if isinstance(owner_protocols, Mapping) else None)
    omitted_owner = (owner_protocols.get("strategy_omitted")
        if isinstance(owner_protocols, Mapping) else None)
    task_descriptor = (included_owner.get("objective_task_descriptor")
        if isinstance(included_owner, Mapping) else None)
    probe_inputs = (task_descriptor.get("probe_inputs")
        if isinstance(task_descriptor, Mapping) else None)
    probe_set_digest = ("sha256:" + hashlib.sha256(json.dumps(
        sorted(probe_inputs), separators=(",", ":")).encode("ascii")).hexdigest()
        if isinstance(probe_inputs, list)
            and all(type(value) is int for value in probe_inputs) else None)
    if (not isinstance(input_digests, Mapping)
            or not isinstance(preflight_protocol, Mapping)
            or not isinstance(omitted_owner, Mapping)
            or not isinstance(task_descriptor, Mapping)
            or omitted_owner.get("objective_task_descriptor") != task_descriptor
            or task_descriptor.get("task_family_id") != series.get("task_family_id")
            or not isinstance(probe_inputs, list)
            or len(probe_inputs) != task.get("probe_count")
            or len(set(probe_inputs)) != len(probe_inputs)
            or probe_set_digest != task.get("probe_set_digest")
            or input_digests.get(f"v{preflight_version}_preflight")
                != _file_digest(preflight_raw)
            or input_digests.get(f"v{verification_version}_verification")
                != _file_digest(verification_raw)
            or verification.get("preflight_report_digest")
                != _file_digest(preflight_raw)
            or verification.get("task_digest") != preflight.get("task_digest")
            or verification.get("protocol_digest") != preflight.get("protocol_digest")
            or verification.get("answer_key_digest") != preflight.get("answer_key_digest")
            or verification.get("source_receipt_digest")
                != preflight.get("source_receipt_digest")
            or verification.get("source_model_identity_digest")
                != preflight.get("source_model_identity_digest")
            or preflight.get("task_digest") != task.get("task_digest")
            or preflight.get("protocol_digest") != task.get("protocol_digest")
            or preflight.get("answer_key_digest") != task.get("answer_key_digest")
            or preflight.get("task_family_id") != series.get("task_family_id")
            or preflight.get("generation_config_digest")
                != series.get("shared_generation_config_digest")
            or len(preflight_protocol.get("probe_binding_digests", ()))
                != task.get("probe_count")
            or verification.get("selected_history_set_digest") !=
                series.get("shared_selected_history_set_digest")
            or verification.get("strategy_digest") != series.get("shared_strategy_digest")
            or any(verification.get(key) is not True for key in (
                "private_task_plan_reloaded", "strategy_protocol_reloaded",
                "answer_key_commitment_verified", "source_receipt_verified",
                "selected_history_records_verified"))):
        raise SeriesAnalysisError("frozen_preflight_verification_mismatch")

    protocol_digest = _require_digest(preflight.get("protocol_digest"),
        "preflight_protocol_digest_invalid")
    slot_result, _ = _read_json(cycle_root /
        "strategy_inclusion_pair_slot_result.json")
    runner_binding, _ = _read_json(cycle_root /
        "strategy_inclusion_runner_binding.json")
    if (slot_result.get("schema_version") !=
            "sentientos.strategy_inclusion_pair_slot_result:v1"
            or slot_result.get("status") != "completed"
            or slot_result.get("run_id") != cycle_id
            or slot_result.get("inference_performed") is not True
            or slot_result.get("learning_established") is not False
            or slot_result.get("improvement_established") is not False
            or slot_result.get("authority") is not False
            or slot_result.get("governed_unload") != "governed_release_completed"
            or runner_binding.get("schema_version") !=
                "sentientos.strategy_inclusion_runner_binding:v1"
            or runner_binding.get("run_id") != cycle_id
            or runner_binding.get("preflight_protocol_digest") != protocol_digest
            or runner_binding.get("runtime_protocol_digest")
                != slot_result.get("protocol_digest")
            or runner_binding.get("target_model_identity_digest")
                != series.get("shared_target_model_identity_digest")
            or runner_binding.get("source_receipt_digest")
                != series.get("shared_source_receipt_digest")
            or _HEX_DIGEST.fullmatch(str(runner_binding.get(
                "runtime_bundle_digest", ""))) is None
            or _HEX_DIGEST.fullmatch(str(runner_binding.get(
                "history_seed_evidence_digest", ""))) is None
            or _HEX_DIGEST.fullmatch(str(runner_binding.get(
                "resource_guard_evidence_digest", ""))) is None
            or runner_binding.get("history_seed_verified") is not True
            or runner_binding.get("resource_gate_passed") is not True
            or runner_binding.get("authority") is not False):
        raise SeriesAnalysisError("runner_slot_binding_invalid")
    binding_semantic = {key: value for key, value in runner_binding.items()
        if key != "runner_binding_digest"}
    binding_digest = "sha256:" + digest_payload(binding_semantic)
    if (runner_binding.get("runner_binding_digest") != binding_digest
            or slot_result.get("runner_binding_digest") != binding_digest):
        raise SeriesAnalysisError("runner_binding_digest_mismatch")

    runtime_protocol_digest = _require_digest(slot_result.get("protocol_digest"),
        "runtime_protocol_digest_invalid")
    store_root = journal_root / "developmental_experiments"
    protocol_name = ("strategy-inclusion-protocol-"
        + runtime_protocol_digest[7:31] + ".json")
    runtime_protocol, _ = _read_json(store_root / "protocols" / protocol_name)
    try:
        validate_strategy_inclusion_protocol(protocol=runtime_protocol)
    except (TypeError, ValueError) as exc:
        raise SeriesAnalysisError("runtime_protocol_invalid") from exc
    if (not isinstance(preflight_protocol, Mapping)
            or runtime_protocol.get("protocol_digest") != runtime_protocol_digest
            or _strategy_intervention_digest({key: value for key, value
                in runtime_protocol.items() if key != "protocol_digest"})
                != runtime_protocol_digest
            or runtime_protocol.get("task_digest") != preflight.get("task_digest")
            or runtime_protocol.get("answer_key_digest")
                != preflight.get("answer_key_digest")
            or runtime_protocol.get("target_model_identity_digest")
                != series.get("shared_target_model_identity_digest")
            or runtime_protocol.get("generation_config_digest")
                != series.get("shared_generation_config_digest")
            or runtime_protocol.get("strategy_digest") != series.get("shared_strategy_digest")
            or runtime_protocol.get("history_set_digest")
                != series.get("shared_selected_history_set_digest")
            or runtime_protocol.get("probe_binding_digests")
                != preflight_protocol.get("probe_binding_digests")):
        raise SeriesAnalysisError("runtime_protocol_preflight_binding_mismatch")

    score_digest = _require_digest(slot_result.get("score_digest"),
        "slot_score_digest_invalid")
    score_name = ("strategy-inclusion-score-" + runtime_protocol_digest[7:19]
        + "-" + score_digest[7:19] + ".json")
    score, _ = _read_json(store_root / "runs" / score_name)
    score_semantic = {key: value for key, value in score.items()
        if key != "score_digest"}
    if (score.get("schema_version") not in {
            "sentientos.strategy_inclusion_intervention_score:v1",
            "sentientos.strategy_inclusion_intervention_score:v2"}
            or score.get("protocol_digest") != runtime_protocol_digest
            or score.get("score_digest") != score_digest
            or _digest(score_semantic) != score_digest
            or score.get("answer_key_digest") != preflight.get("answer_key_digest")
            or score.get("paired_delivery_verified") is not True
            or score.get("inference_performed") is not True
            or score.get("learning_established") is not False
            or score.get("authority") is not False
            or score.get("probe_count") != len(
                preflight_protocol.get("probe_binding_digests", ()))):
        raise SeriesAnalysisError("persisted_score_binding_invalid")

    receipt_bindings = score.get("invocation_receipt_bindings")
    if not isinstance(receipt_bindings, Mapping) or set(receipt_bindings) != set(_ARMS):
        raise SeriesAnalysisError("score_receipt_bindings_invalid")
    seen_receipt_ids: set[str] = set()
    seen_request_ids: set[str] = set()
    for arm in _ARMS:
        arm_name = ("strategy-inclusion-arm-result-"
            + runtime_protocol_digest[7:31] + "-" + arm + ".json")
        arm_result, _ = _read_json(store_root / "runs" / arm_name)
        receipt_binding = arm_result.get("receipt_binding")
        arm_semantic = {"schema_version":
                "sentientos.strategy_inclusion_arm_execution_result:v1",
            "protocol_digest": runtime_protocol_digest, "arm": arm,
            "receipt_binding": receipt_binding,
            "authority": False}
        if (not isinstance(receipt_binding, Mapping)
                or set(receipt_binding) != {"receipt_id", "receipt_digest",
                    "request_id", "request_digest", "preview_request_digest",
                    "output_digest", "prompt_digest"}
                or not isinstance(receipt_binding.get("receipt_id"), str)
                or _RECEIPT_ID.fullmatch(receipt_binding["receipt_id"]) is None
                or not isinstance(receipt_binding.get("request_id"), str)
                or _REQUEST_ID.fullmatch(receipt_binding["request_id"]) is None
                or receipt_binding.get("receipt_id") in seen_receipt_ids
                or receipt_binding.get("request_id") in seen_request_ids
                or any(not _valid_raw_digest(receipt_binding.get(key))
                    for key in ("receipt_digest", "request_digest",
                        "output_digest", "prompt_digest"))
                or receipt_binding.get("preview_request_digest") !=
                    runtime_protocol.get("preview_request_digests", {}).get(arm)
                or receipt_binding.get("prompt_digest") !=
                    str(runtime_protocol.get("invocation_prompt_digests", {}).get(
                        arm, "")).removeprefix("sha256:")
                or arm_result.get("result_digest")
                != _strategy_intervention_digest(arm_semantic)
                or receipt_binding != receipt_bindings.get(arm)):
            raise SeriesAnalysisError("persisted_arm_result_binding_invalid")
        seen_receipt_ids.add(receipt_binding["receipt_id"])
        seen_request_ids.add(receipt_binding["request_id"])

    expected_probes = preflight_protocol.get("probe_binding_digests")
    outcomes = score.get("outcomes_by_arm")
    if not isinstance(expected_probes, list) or not isinstance(outcomes, Mapping):
        raise SeriesAnalysisError("score_outcomes_invalid")
    by_arm: dict[str, dict[str, str]] = {}
    counts: dict[str, dict[str, int]] = {}
    for arm in _ARMS:
        rows = outcomes.get(arm)
        if (not isinstance(rows, list) or len(rows) != len(expected_probes)
                or any(not isinstance(row, Mapping)
                    or row.get("outcome") not in _OUTCOMES
                    for row in rows)):
            raise SeriesAnalysisError("score_outcome_rows_invalid")
        if [row.get("probe_binding_digest") for row in rows] != expected_probes:
            raise SeriesAnalysisError("score_probe_binding_mismatch")
        if any("brier_squared_error_basis_points_squared" in row
                and (row.get("outcome") == "abstained"
                    or type(row.get(
                        "brier_squared_error_basis_points_squared")) is not int
                    or not 0 <= row[
                        "brier_squared_error_basis_points_squared"]
                        <= 10000 ** 2)
                for row in rows):
            raise SeriesAnalysisError("score_probe_confidence_brier_invalid")
        by_arm[arm] = {row["probe_binding_digest"]: row["outcome"]
            for row in rows}
        counts[arm] = {outcome: sum(row["outcome"] == outcome for row in rows)
            for outcome in sorted(_OUTCOMES)}
    paired_rows = score.get("paired_probe_outcomes")
    if (not isinstance(paired_rows, list) or len(paired_rows) != len(expected_probes)
            or any(not isinstance(row, Mapping)
                or row.get("probe_binding_digest") != probe
                or row.get("strategy_included")
                    != by_arm["strategy_included"][probe]
                or row.get("strategy_omitted")
                    != by_arm["strategy_omitted"][probe]
                for row, probe in zip(paired_rows, expected_probes, strict=True))):
        raise SeriesAnalysisError("score_paired_probe_rows_mismatch")
    score_counts = score.get("correct_counts")
    answered_counts = score.get("answered_counts")
    coverage = score.get("coverage_basis_points")
    if (not isinstance(score_counts, Mapping)
            or not isinstance(answered_counts, Mapping)
            or not isinstance(coverage, Mapping)
            or any(score_counts.get(arm) != counts[arm]["correct"]
                or answered_counts.get(arm) != counts[arm]["correct"]
                    + counts[arm]["incorrect"]
                or coverage.get(arm) != ((counts[arm]["correct"]
                    + counts[arm]["incorrect"]) * 10000)
                    // len(expected_probes) for arm in _ARMS)):
        raise SeriesAnalysisError("score_summary_count_mismatch")
    selective_accuracy = {arm: (counts[arm]["correct"] * 10000 //
        (counts[arm]["correct"] + counts[arm]["incorrect"])
        if counts[arm]["correct"] + counts[arm]["incorrect"] else None)
        for arm in _ARMS}
    abstained_counts = {arm: counts[arm]["abstained"] for arm in _ARMS}
    confidence_brier_sums = {arm: sum(
        row.get("brier_squared_error_basis_points_squared", 0)
        for row in outcomes[arm]) for arm in _ARMS}
    confidence_scored_counts = {arm: sum(
        "brier_squared_error_basis_points_squared" in row
        for row in outcomes[arm]) for arm in _ARMS}
    confidence_brier_scores = {arm: (
        confidence_brier_sums[arm] /
            (confidence_scored_counts[arm] * 10000 ** 2)
        if confidence_scored_counts[arm] else None) for arm in _ARMS}
    paired_confidence_brier_differences = [
        outcomes["strategy_included"][index][
            "brier_squared_error_basis_points_squared"]
        - outcomes["strategy_omitted"][index][
            "brier_squared_error_basis_points_squared"]
        for index in range(len(expected_probes))
        if ("brier_squared_error_basis_points_squared" in
                outcomes["strategy_included"][index]
            and "brier_squared_error_basis_points_squared" in
                outcomes["strategy_omitted"][index])]
    paired_confidence_brier_difference_sum = sum(
        paired_confidence_brier_differences)
    paired_confidence_brier_pair_count = len(
        paired_confidence_brier_differences)
    paired_confidence_brier_delta = (
        paired_confidence_brier_difference_sum /
            (paired_confidence_brier_pair_count * 10000 ** 2)
        if paired_confidence_brier_pair_count else None)
    if (score.get("confidence_brier_squared_error_sums")
            != confidence_brier_sums
            or score.get("confidence_scored_counts")
                != confidence_scored_counts):
        raise SeriesAnalysisError("score_confidence_summary_mismatch")
    # V2 binds these summaries in the score digest. V1 outcomes remain
    # sufficient to derive the supplemental descriptive values below.
    if score.get("schema_version") == (
            "sentientos.strategy_inclusion_intervention_score:v2") and (
            score.get("selective_accuracy_basis_points") != selective_accuracy
            or score.get("abstained_counts") != abstained_counts):
        raise SeriesAnalysisError("score_selective_summary_mismatch")

    transitions = {f"{left}_to_{right}": 0
        for left in sorted(_OUTCOMES) for right in sorted(_OUTCOMES)}
    for probe in expected_probes:
        key = by_arm["strategy_included"][probe] + "_to_" + \
            by_arm["strategy_omitted"][probe]
        transitions[key] += 1
    included_correct = counts["strategy_included"]["correct"]
    omitted_correct = counts["strategy_omitted"]["correct"]
    return {
        "task_seed": seed,
        "cycle_id": cycle_id,
        "attempt_status": "completed",
        "failure_code": None,
        "status": "completed_and_verified",
        "preflight_protocol_digest": protocol_digest,
        "runtime_protocol_digest": runtime_protocol_digest,
        "score_digest": score_digest,
        "probe_count": len(expected_probes),
        "_probe_inputs": sorted(probe_inputs),
        "outcomes_by_arm": counts,
        "coverage_basis_points_by_arm": {
            arm: ((counts[arm]["correct"] + counts[arm]["incorrect"])
                * 10000) // len(expected_probes) for arm in _ARMS},
        "supplemental_selective_accuracy_basis_points_by_arm":
            selective_accuracy,
        "supplemental_abstained_counts_by_arm": abstained_counts,
        "supplemental_confidence_brier_score_by_arm":
            confidence_brier_scores,
        "supplemental_confidence_brier_squared_error_sums_by_arm":
            confidence_brier_sums,
        "supplemental_confidence_scored_counts_by_arm":
            confidence_scored_counts,
        "supplemental_paired_confidence_brier_delta_included_minus_omitted":
            paired_confidence_brier_delta,
        "supplemental_paired_confidence_brier_difference_sum_basis_points_squared":
            paired_confidence_brier_difference_sum,
        "supplemental_paired_confidence_brier_scored_probe_count":
            paired_confidence_brier_pair_count,
        "included_minus_omitted_correct_count": (
            included_correct - omitted_correct),
        "paired_probe_transitions_included_to_omitted": transitions,
    }


def analyze_series(*, series_path: Path, analysis_path: Path,
        runtime_inputs_path: Path) -> dict[str, Any]:
    series, series_raw = _read_json(series_path)
    analysis, analysis_raw = _read_json(analysis_path)
    runtime_inputs, runtime_inputs_raw = _read_json(runtime_inputs_path)
    if (series.get("schema_version") !=
            "sentientos.strategy_inclusion_matched_task_cpu_preflight_series:v1"
            or series.get("status") != "three_receipt_bound_preflights_verified"
            or analysis.get("schema_version") !=
                "sentientos.strategy_inclusion_matched_task_analysis_protocol:v1"
            or series.get("analysis_protocol") != analysis_path.name
            or series.get("analysis_protocol_digest") != _file_digest(analysis_raw)
            or runtime_inputs.get("schema_version") !=
                "sentientos.strategy_inclusion_runtime_inputs:v1"):
        raise SeriesAnalysisError("series_analysis_protocol_binding_invalid")
    tasks = series.get("task_instances")
    entries = runtime_inputs.get("task_instances")
    if (not isinstance(tasks, list) or len(tasks) != 3
            or not isinstance(entries, list) or len(entries) != len(tasks)
            or any(not isinstance(item, Mapping) for item in tasks + entries)
            or [item.get("task_seed") for item in tasks]
                != analysis.get("expected_task_seeds")
            or analysis.get("preflight_series") != series_path.name
            or [item for item in analysis.get("expected_cycle_ids", ())]
                != [item.get("cycle_id") for item in entries]
            or len(set(item.get("cycle_id") for item in entries)) != len(entries)
            or len(set(item.get("cycle_root") for item in entries)) != len(entries)
            or len(set(item.get("journal_root") for item in entries)) != len(entries)):
        raise SeriesAnalysisError("series_runtime_input_set_invalid")
    series_root = series_path.parent
    outcomes: list[dict[str, Any]] = []
    for task, runtime_entry in zip(tasks, entries, strict=True):
        try:
            outcomes.append(_load_and_verify_task(task=task, analysis=analysis,
                series=series, series_root=series_root,
                runtime_entry=runtime_entry))
        except (OSError, TypeError, ValueError) as exc:
            failure_code = (str(exc) if isinstance(exc, SeriesAnalysisError)
                else "runtime_artifact_read_failed")
            reported_failure_code = runtime_entry.get("failure_code")
            outcomes.append({
                "task_seed": task.get("task_seed"),
                "cycle_id": runtime_entry.get("cycle_id"),
                "attempt_status": runtime_entry.get("attempt_status"),
                "failure_code": reported_failure_code,
                "status": "incomplete_or_unverified",
                "analysis_failure_code": failure_code[:160],
                "reported_inference_performed": (
                    runtime_entry.get("inference_performed")
                    if type(runtime_entry.get("inference_performed")) is bool
                    else None),
                "learning_established": False,
                "authority": False,
            })
    completed = [item for item in outcomes
        if item.get("status") == "completed_and_verified"]
    probe_sets = [set(item.pop("_probe_inputs")) for item in completed]
    pairwise_overlap_count = sum(len(left.intersection(right))
        for index, left in enumerate(probe_sets)
        for right in probe_sets[index + 1:])
    complete_series = (len(completed) == len(tasks)
        and pairwise_overlap_count == 0)
    aggregate = None
    supplemental_aggregate = None
    if complete_series:
        included_correct = sum(item["outcomes_by_arm"][
            "strategy_included"]["correct"] for item in completed)
        omitted_correct = sum(item["outcomes_by_arm"][
            "strategy_omitted"]["correct"] for item in completed)
        deltas = [item["included_minus_omitted_correct_count"]
            for item in completed]
        aggregate = {
            "probe_count_per_arm": sum(item["probe_count"]
                for item in completed),
            "correct_counts": {
                "strategy_included": included_correct,
                "strategy_omitted": omitted_correct,
            },
            "included_minus_omitted_correct_count": (
                included_correct - omitted_correct),
            "task_pairs_with_positive_difference": sum(value > 0
                for value in deltas),
            "task_pairs_with_zero_difference": sum(value == 0
                for value in deltas),
            "task_pairs_with_negative_difference": sum(value < 0
                for value in deltas),
        }
        supplemental_aggregate = {
            "status": "descriptive_not_preregistered_primary_endpoints",
            "abstained_counts": {
                arm: sum(item["supplemental_abstained_counts_by_arm"][arm]
                    for item in completed) for arm in _ARMS},
            "selective_accuracy_basis_points": {
                arm: (sum(item["outcomes_by_arm"][arm]["correct"]
                        for item in completed) * 10000 //
                    sum(item["outcomes_by_arm"][arm]["correct"]
                        + item["outcomes_by_arm"][arm]["incorrect"]
                        for item in completed)
                    if sum(item["outcomes_by_arm"][arm]["correct"]
                        + item["outcomes_by_arm"][arm]["incorrect"]
                        for item in completed) else None)
                for arm in _ARMS},
            "confidence_metric_status":
                "proper_score_on_confidence_scored_answers_not_a_calibration_diagnostic",
            "confidence_scored_counts": {
                arm: sum(item[
                    "supplemental_confidence_scored_counts_by_arm"][arm]
                    for item in completed) for arm in _ARMS},
            "confidence_brier_scores": {
                arm: (sum(item[
                        "supplemental_confidence_brier_squared_error_sums_by_arm"][arm]
                        for item in completed)
                    / (sum(item[
                        "supplemental_confidence_scored_counts_by_arm"][arm]
                        for item in completed) * 10000 ** 2)
                    if sum(item[
                        "supplemental_confidence_scored_counts_by_arm"][arm]
                        for item in completed) else None)
                for arm in _ARMS},
            "paired_confidence_brier_metric_status":
                "included_minus_omitted_on_identical_confidence_scored_probes",
            "paired_confidence_brier_scored_probe_count": sum(item[
                "supplemental_paired_confidence_brier_scored_probe_count"]
                for item in completed),
            "paired_confidence_brier_delta_included_minus_omitted": (
                sum(item[
                    "supplemental_paired_confidence_brier_difference_sum_basis_points_squared"]
                    for item in completed)
                / (sum(item[
                    "supplemental_paired_confidence_brier_scored_probe_count"]
                    for item in completed) * 10000 ** 2)
                if sum(item[
                    "supplemental_paired_confidence_brier_scored_probe_count"]
                    for item in completed)
                else None),
        }
    semantic = {
        "schema_version":
            "sentientos.strategy_inclusion_matched_task_series_analysis:v2",
        "series_digest": _file_digest(series_raw),
        "analysis_protocol_digest": _file_digest(analysis_raw),
        "runtime_inputs_digest": _file_digest(runtime_inputs_raw),
        "task_instance_count": len(tasks),
        "completed_and_verified_task_count": len(completed),
        "status": "complete_descriptive_series" if complete_series
            else "incomplete_series_no_primary_aggregate"
            if len(completed) != len(tasks)
            else "invalid_series_probe_overlap_no_primary_aggregate",
        "pairwise_probe_overlap_count": pairwise_overlap_count,
        "probe_sets_pairwise_disjoint": (pairwise_overlap_count == 0
            if len(completed) == len(tasks) else None),
        "task_outcomes": outcomes,
        "primary_aggregate": aggregate,
        "supplemental_aggregate": supplemental_aggregate,
        "primary_aggregate_available": complete_series,
        "inference_performed": (True if completed or any(
            item.get("reported_inference_performed") is True for item in outcomes)
            else False if all(item.get("attempt_status") == "not_started"
                for item in outcomes) else None),
        "learning_established": False,
        "model_independent_continuity_established": False,
        "self_improvement_established": False,
        "authority": False,
        "p_values_reported": False,
        "statistical_significance_claim": False,
    }
    return {**semantic, "analysis_digest": _digest(semantic)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--series", type=Path, required=True)
    parser.add_argument("--analysis-protocol", type=Path, required=True)
    parser.add_argument("--runtime-inputs", type=Path, required=True,
        help="JSON manifest listing each task seed, cycle root, and journal root")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise ValueError("series_analysis_output_already_exists")
    report = analyze_series(series_path=args.series,
        analysis_path=args.analysis_protocol,
        runtime_inputs_path=args.runtime_inputs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode("utf-8")
    descriptor = os.open(args.output,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600)
    try:
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short strategy series report write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        print(f"strategy series analysis failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
