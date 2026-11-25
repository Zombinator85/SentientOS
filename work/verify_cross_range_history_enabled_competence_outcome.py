"""Verify a completed cross-range history-enabled competence outcome offline.

The verifier reads a cycle result and its persisted developmental-experiment
score run. It does not start an inference runtime. Its verdict covers internal
artifact consistency and digest bindings; it is not a signature or independent
attestation that inference occurred.
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

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.local_model_authority import digest_payload  # noqa: E402
from sentientos.local_model_authority import (  # noqa: E402
    ROOTLESS_EXPERIMENTAL_DEVELOPMENTAL_INVOCATION_PURPOSES,
)
from sentientos.governed_local_model_invocation import (  # noqa: E402
    validate_receipt,
)
from work.rootless_history_boundary_campaign import (  # noqa: E402
    _load_plan,
    verify_experiment_implementation,
    verify_model_identity_recipe,
)
from work.verify_rootless_planned_cycle_owner_preflight import (  # noqa: E402
    verify_report as verify_preflight_report,
)
from sentientos.resident_developmental_cognition import (  # noqa: E402
    _valid_rootless_epistemic_session_binding,
)

MAX_INPUT_BYTES = 128 * 1024 * 1024
CONDITIONS = ("history_present", "history_withheld", "history_restored")
SCORE_SCHEMAS = {
    "sentientos.objective_task_score:v3",
    "sentientos.objective_task_score:v4",
    "sentientos.objective_task_score:v5",
    "sentientos.objective_task_score:v6",
}


def _read_object(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("cross_range_outcome_input_invalid")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("cross_range_outcome_input_invalid")
    return value


def _sha256(value: Any) -> str:
    return "sha256:" + digest_payload(value)


def _raw_file_digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("cross_range_outcome_input_invalid")
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_report_exclusive(path: Path, report: Mapping[str, Any]) -> None:
    if path.is_symlink() or path.exists():
        raise ValueError("cross_range_verification_report_exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(dict(report), sort_keys=True, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _score_summary(score_rows: Any,
        probe_inputs: list[int]) -> tuple[dict[str, Any], dict[str, Mapping[str, Any]]]:
    if (not isinstance(score_rows, list) or len(score_rows) != len(CONDITIONS)
            or any(not isinstance(row, Mapping) for row in score_rows)
            or tuple(row.get("condition_id") for row in score_rows) != CONDITIONS):
        raise ValueError("cross_range_score_rows_invalid")
    by_condition: dict[str, Mapping[str, Any]] = {}
    correctness: dict[str, list[bool | None] | None] = {}
    abstentions: dict[str, list[bool | None] | None] = {}
    unavailable: list[str] = []
    score_digests: dict[str, str] = {}
    task_digest: str | None = None
    ordered_inputs: list[int] | None = None
    for row in score_rows:
        condition = row["condition_id"]
        score = row.get("score")
        if not isinstance(score, Mapping):
            raise ValueError("cross_range_score_row_missing")
        semantic = {key: value for key, value in score.items()
            if key != "score_digest"}
        current_task_digest = score.get("task_digest")
        score_digest = score.get("score_digest")
        if (score.get("schema_version") not in SCORE_SCHEMAS
                or not isinstance(current_task_digest, str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", current_task_digest) is None
                or task_digest not in (None, current_task_digest)
                or not isinstance(score_digest, str)
                or score_digest != _sha256(semantic)):
            raise ValueError("cross_range_score_digest_invalid")
        task_digest = current_task_digest
        score_digests[condition] = score_digest
        by_condition[condition] = row
        status = score.get("status")
        results = score.get("probe_results")
        probe_count = score.get("probe_count")
        correct_count = score.get("correct_count")
        if (type(probe_count) is not int or probe_count != len(probe_inputs)):
            raise ValueError("cross_range_score_probe_count_invalid")
        if status in {"invalid_answer", "output_truncated", "output_unavailable"}:
            if (results != [] or (status == "invalid_answer"
                    and correct_count != 0) or (status != "invalid_answer"
                    and correct_count is not None)):
                raise ValueError("cross_range_unscoreable_score_invalid")
            if (score.get("schema_version") in {
                    "sentientos.objective_task_score:v4",
                    "sentientos.objective_task_score:v5",
                    "sentientos.objective_task_score:v6"}
                    and (score.get("answered_count") is not None
                        or score.get("abstained_count") is not None)):
                raise ValueError("cross_range_unscoreable_score_invalid")
            correctness[condition] = None
            abstentions[condition] = None
            unavailable.append(condition)
            continue
        if (status not in {"correct", "incorrect", "selective"}
                or not isinstance(results, list)
                or len(results) != probe_count or type(correct_count) is not int):
            raise ValueError("cross_range_score_probe_results_invalid")
        inputs: list[int] = []
        correct_values: list[bool | None] = []
        abstained_values: list[bool] = []
        for result in results:
            if not isinstance(result, Mapping):
                raise ValueError("cross_range_probe_result_invalid")
            probe_input = result.get("probe_input")
            correct = result.get("correct")
            abstained = result.get("abstained", False)
            observed_answer = result.get("observed_answer")
            if (type(probe_input) is not int or type(abstained) is not bool
                    or (abstained and (observed_answer is not None or correct is not None))
                    or (not abstained and (type(observed_answer) is not int
                        or type(correct) is not bool))):
                raise ValueError("cross_range_probe_result_invalid")
            inputs.append(probe_input)
            correct_values.append(correct)
            abstained_values.append(abstained)
        if (inputs != probe_inputs
                or sum(value is True for value in correct_values) != correct_count
                or ordered_inputs not in (None, inputs)):
            raise ValueError("cross_range_score_probe_alignment_invalid")
        schema = score["schema_version"]
        abstained_count = sum(abstained_values)
        if schema == "sentientos.objective_task_score:v3":
            if (abstained_count
                    or status != ("correct" if correct_count == probe_count
                        else "incorrect")):
                raise ValueError("cross_range_score_status_invalid")
        elif schema in {
                "sentientos.objective_task_score:v4",
                "sentientos.objective_task_score:v5",
                "sentientos.objective_task_score:v6"}:
            if (type(score.get("answered_count")) is not int
                    or type(score.get("abstained_count")) is not int
                    or score["answered_count"] != probe_count - abstained_count
                    or score["abstained_count"] != abstained_count):
                raise ValueError("cross_range_score_selective_counts_invalid")
            all_correct = correct_count == probe_count
            expected_status = ("selective" if abstained_count else
                "correct" if all_correct else "incorrect")
            if schema == "sentientos.objective_task_score:v4" and abstained_count:
                expected_status = "incorrect"
            if status != expected_status:
                raise ValueError("cross_range_score_status_invalid")
        ordered_inputs = inputs
        correctness[condition] = correct_values
        abstentions[condition] = abstained_values

    if ordered_inputs is None:
        probe_outcomes: list[dict[str, Any]] = []
        posture = "per_probe_outcomes_unavailable_no_scoreable_condition"
    else:
        probe_outcomes = []
        for index, probe_input in enumerate(ordered_inputs):
            correct_by_condition = {
                condition: (correctness[condition][index]
                    if correctness[condition] is not None else None)
                for condition in CONDITIONS}
            abstained_by_condition = {
                condition: (abstentions[condition][index]
                    if abstentions[condition] is not None else None)
                for condition in CONDITIONS}
            present = correct_by_condition["history_present"]
            withheld = correct_by_condition["history_withheld"]
            restored = correct_by_condition["history_restored"]
            history_transition = ("unscoreable" if type(present) is not bool
                or type(withheld) is not bool else
                "no_correctness_change" if present == withheld else
                "history_associated_correctness_gain" if present else
                "history_associated_correctness_cost")
            restoration = ("unscoreable" if type(present) is not bool
                or type(restored) is not bool else
                "matches_history_present" if restored == present else
                "differs_from_history_present")
            answerability = {
                condition: (not abstentions[condition][index]
                    if abstentions[condition] is not None else None)
                for condition in CONDITIONS}
            present_answerable = answerability["history_present"]
            withheld_answerable = answerability["history_withheld"]
            restored_answerable = answerability["history_restored"]
            answerability_transition = (
                "unscoreable" if type(present_answerable) is not bool
                    or type(withheld_answerable) is not bool else
                "no_answerability_change" if present_answerable == withheld_answerable
                    else "history_associated_answerability_gain" if present_answerable
                    else "history_associated_answerability_cost")
            answerability_restoration = (
                "unscoreable" if type(present_answerable) is not bool
                    or type(restored_answerable) is not bool else
                "matches_history_present" if present_answerable == restored_answerable
                    else "differs_from_history_present")
            probe_outcomes.append({
                "probe_index": index,
                "probe_input": probe_input,
                "correctness_by_condition": correct_by_condition,
                "abstention_by_condition": abstained_by_condition,
                "history_present_vs_withheld": history_transition,
                "restoration_vs_present": restoration,
                "answerability_by_condition": answerability,
                "history_present_vs_withheld_answerability": answerability_transition,
                "restoration_answerability_vs_present": answerability_restoration,
            })
        posture = ("partial_per_probe_outcomes_unscoreable_conditions"
            if unavailable else
            "independent_oracle_correctness_only_answer_values_omitted")
    summary = {
        "condition_order": list(CONDITIONS),
        "task_digest": task_digest,
        "condition_score_digests": score_digests,
        "probe_outcomes": probe_outcomes,
        "unscoreable_condition_ids": unavailable,
        "posture": posture,
    }
    return summary, by_condition


def verify_outcome(*, plan_path: Path, preflight_path: Path,
        cycle_result_path: Path, experiment_state_root: Path) -> dict[str, Any]:
    plan = _load_plan(plan_path)
    verify_model_identity_recipe(plan)
    implementation = verify_experiment_implementation(plan)
    protocol = plan.get("cross_range_history_enabled_competence")
    if (not isinstance(protocol, Mapping)
            or protocol.get("schema_version") !=
                "sentientos.cross_range_history_enabled_competence_protocol:v2"
            or protocol.get("per_probe_outcomes_required") is not True
            or protocol.get("answer_values_in_summary") is not False):
        raise ValueError("cross_range_v2_protocol_required")
    preflight = verify_preflight_report(report_path=preflight_path,
        plan_path=plan_path)
    if preflight.get("status") != "verified":
        raise ValueError("cross_range_preflight_verification_failed")
    preflight_raw = _read_object(preflight_path)
    eligibility = preflight_raw.get(
        "cross_range_history_enabled_competence_eligibility")
    if (not isinstance(eligibility, Mapping)
            or eligibility.get("eligible") is not True
            or not isinstance(eligibility.get("source_record_ids"), list)
            or not eligibility.get("source_record_ids")
            or len(set(eligibility["source_record_ids"]))
                != len(eligibility["source_record_ids"])):
        raise ValueError("cross_range_preflight_gate_invalid")
    cycle_result = _read_object(cycle_result_path)
    cycle_ids = plan.get("ordered_cycle_ids")
    if (not isinstance(cycle_ids, list)
            or preflight_raw.get("plan_digest") != plan.get("plan_digest")
            or preflight_raw.get("cycle_id") not in cycle_ids):
        raise ValueError("cross_range_plan_preflight_binding_invalid")
    cycle_index = cycle_ids.index(preflight_raw["cycle_id"])
    cycle_id = cycle_ids[cycle_index]
    history_binding = cycle_result.get("history_campaign_binding")
    if (cycle_result.get("status") != "completed"
            or cycle_result.get("run_id") != cycle_id
            or not isinstance(history_binding, Mapping)
            or history_binding.get("campaign_id") != plan.get("campaign_id")
            or history_binding.get("campaign_plan_digest") != plan.get("plan_digest")
            or history_binding.get("cycle_index") != cycle_index
            or cycle_result.get("source_provenance_stable_for_run") is not True
            or cycle_result.get("source_provenance_fingerprint_complete") is not True):
        raise ValueError("cross_range_cycle_result_plan_binding_invalid")

    outcome = cycle_result.get("objective_cross_range_history_enabled_competence")
    if (not isinstance(outcome, Mapping)
            or outcome.get("schema_version") !=
                "sentientos.cross_range_history_enabled_competence_outcome:v1"
            or outcome.get("status") !=
                "completed_scored_history_enabled_competence_intervention"
            or outcome.get("protocol") != dict(protocol)
            or outcome.get("inference_performed") is not True
            or outcome.get("capability_evaluated") is not True
            or outcome.get("learning_established") is not False
            or outcome.get("causal_claim_made") is not False
            or outcome.get("authority") is not False):
        raise ValueError("cross_range_outcome_claim_scope_invalid")
    if (outcome.get("source_task_family_id")
            != protocol.get("source_task_family_id")
            or outcome.get("task_family_id")
                != protocol.get("target_task_family_id")
            or outcome.get("baseline_competence_required") is not False
            or outcome.get("source_record_ids")
                != eligibility.get("source_record_ids")):
        raise ValueError("cross_range_outcome_source_binding_invalid")

    probes = preflight_raw.get("transfer_probe_inputs")
    if (not isinstance(probes, list) or not probes
            or any(type(value) is not int for value in probes)
            or len(set(probes)) != len(probes)):
        raise ValueError("cross_range_preflight_probes_invalid")
    bound_probe = history_binding.get("transfer_probe_preflight")
    if (not isinstance(bound_probe, Mapping)
            or bound_probe.get("transfer_probe_inputs") != probes):
        raise ValueError("cross_range_cycle_probe_binding_invalid")
    overlap = outcome.get("all_family_probe_overlap")
    expected_probe_digest = _sha256({"probe_inputs": probes})
    if (not isinstance(overlap, Mapping)
            or overlap.get("historical_probe_overlap_measurement_complete") is not True
            or overlap.get("historical_probe_overlap_input_count") != 0
            or overlap.get("task_probe_input_digest") != expected_probe_digest):
        raise ValueError("cross_range_all_family_overlap_invalid")

    run_id = outcome.get("run_id")
    run_digest = outcome.get("run_digest")
    prefix = "devexp-run-"
    if (not isinstance(run_id, str) or not run_id.startswith(prefix)
            or len(run_id) != len(prefix) + 24
            or not isinstance(run_digest, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", run_digest) is None
            or run_id != prefix + run_digest[7:31]
            or outcome.get("measurement_id") != run_id):
        raise ValueError("cross_range_score_run_identity_invalid")
    score_run_path = (experiment_state_root / "developmental_experiments"
        / "runs" / f"{run_id}.json")
    score_run = _read_object(score_run_path)
    semantic_run = {key: value for key, value in score_run.items()
        if key not in {"run_id", "run_digest"}}
    if (score_run.get("run_id") != run_id
            or score_run.get("run_digest") != run_digest
            or run_digest != _sha256(semantic_run)):
        raise ValueError("cross_range_score_run_digest_invalid")
    descriptor = score_run.get("objective_task_descriptor")
    if (not isinstance(descriptor, Mapping)
            or descriptor.get("task_family_id") != protocol.get("target_task_family_id")
            or descriptor.get("probe_inputs") != probes
            or not isinstance(descriptor.get("task_digest"), str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}",
                descriptor["task_digest"]) is None):
        raise ValueError("cross_range_score_run_task_binding_invalid")
    recomputed_probe, score_rows = _score_summary(
        score_run.get("objective_scores"), probes)
    if recomputed_probe.get("task_digest") != descriptor.get("task_digest"):
        raise ValueError("cross_range_score_run_task_digest_mismatch")
    if (outcome.get("condition_score_digests")
            != recomputed_probe["condition_score_digests"]
            or outcome.get("probe_level_outcomes") != recomputed_probe
            or outcome.get("probe_level_outcomes_digest") != _sha256(recomputed_probe)):
        raise ValueError("cross_range_probe_outcome_digest_invalid")
    stored_evaluation = score_run.get("objective_evaluation")
    if (not isinstance(stored_evaluation, Mapping)
            or stored_evaluation.get("probe_level_outcomes") != recomputed_probe):
        raise ValueError("cross_range_score_run_probe_evaluation_mismatch")

    run_conditions = score_run.get("conditions")
    if (not isinstance(run_conditions, list) or len(run_conditions) != len(CONDITIONS)
            or any(not isinstance(row, Mapping) for row in run_conditions)
            or tuple(row.get("condition_id") for row in run_conditions) != CONDITIONS):
        raise ValueError("cross_range_score_run_conditions_invalid")
    condition_summaries = outcome.get("conditions")
    if (not isinstance(condition_summaries, list)
            or len(condition_summaries) != len(CONDITIONS)
            or tuple(row.get("condition_id") for row in condition_summaries
                if isinstance(row, Mapping)) != CONDITIONS):
        raise ValueError("cross_range_outcome_conditions_invalid")
    required_sources = outcome.get("source_record_ids")
    if (not isinstance(required_sources, list) or not required_sources
            or len(set(required_sources)) != len(required_sources)):
        raise ValueError("cross_range_source_records_invalid")
    observations = {row["condition_id"]: row for row in run_conditions}
    reports = {row["condition_id"]: row for row in condition_summaries}
    retrieved_by_condition: dict[str, list[str]] = {}
    verified_receipts: dict[str, dict[str, str]] = {}
    receipt_root = cycle_result_path.parent / "inference-custody" / "receipts"
    for condition in CONDITIONS:
        observation = observations[condition]
        report = reports[condition]
        score_row = score_rows[condition]
        score = score_row.get("score")
        delivery = report.get("task_family_prompt_delivery_evidence")
        retrieved = observation.get("retrieved_record_ids")
        if (not isinstance(retrieved, list)
                or any(not isinstance(record_id, str) or not record_id
                    for record_id in retrieved)
                or len(set(retrieved)) != len(retrieved)):
            raise ValueError("cross_range_retrieved_history_ids_invalid")
        receipt_id = observation.get("inference_receipt_id")
        receipt_digest = observation.get("inference_receipt_digest")
        if (not isinstance(receipt_id, str)
                or re.fullmatch(r"lmrec-[0-9a-f]{24}", receipt_id) is None
                or not isinstance(receipt_digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", receipt_digest) is None):
            raise ValueError("cross_range_invocation_receipt_identity_invalid")
        receipt_path = receipt_root / f"{receipt_id}.json"
        receipt = _read_object(receipt_path)
        receipt_valid, _receipt_reasons = validate_receipt(receipt)
        receipt_request = receipt.get("request")
        linkage = (receipt_request.get("linkage")
            if isinstance(receipt_request, Mapping) else None)
        session_binding = (linkage.get("rootless_experimental_session")
            if isinstance(linkage, Mapping) else None)
        projection = (receipt_request.get("upstream_evidence", {}).get(
            "task_family_history_prompt_projection")
            if isinstance(receipt_request, Mapping)
            and isinstance(receipt_request.get("upstream_evidence"), Mapping)
            else None)
        projection_semantic = (dict(projection)
            if isinstance(projection, Mapping) else {})
        projection_digest = projection_semantic.pop("projection_digest", None)
        projected_records = (projection.get("records")
            if isinstance(projection, Mapping) else None)
        projected_record_ids = ([row.get("record_id") for row in projected_records]
            if isinstance(projected_records, list)
            and all(isinstance(row, Mapping) for row in projected_records) else None)
        expected_treatment = "withheld" if condition == "history_withheld" else "present"
        if (not isinstance(delivery, Mapping)
                or receipt_valid is not True
                or receipt.get("receipt_id") != receipt_id
                or receipt.get("receipt_digest") != receipt_digest
                or receipt.get("status") != "admitted_completed"
                or not isinstance(receipt_request, Mapping)
                or receipt_request.get("request_id") != observation.get("request_id")
                or receipt_request.get("request_digest")
                    != observation.get("request_digest")
                or receipt_request.get("active_model_identity")
                    != cycle_result.get("active_model_identity")
                or receipt_request.get("purpose") not in
                    ROOTLESS_EXPERIMENTAL_DEVELOPMENTAL_INVOCATION_PURPOSES
                or not isinstance(linkage, Mapping)
                or linkage.get("condition_id") != condition
                or linkage.get("history_present") is not
                    (condition != "history_withheld")
                or "resident_cognitive_serving" in linkage
                or not _valid_rootless_epistemic_session_binding(session_binding)
                or session_binding.get("run_id") != cycle_id
                or session_binding.get("model_manifest_digest")
                    != cycle_result.get("model_manifest_digest")
                or session_binding.get("active_model_identity_digest")
                    != _sha256({"identity": cycle_result.get(
                        "active_model_identity")})
                or receipt.get("output_digest") != observation.get("output_digest")
                or not isinstance(projection, Mapping)
                or projection_digest != _sha256(projection_semantic)
                or delivery.get("projection_digest") != projection_digest
                or receipt_request.get("prompt_digest")
                    != delivery.get("inference_prompt_digest")
                or projection.get("governed_request_prompt_digest")
                    != receipt_request.get("prompt_digest")
                or projection.get("task_family_id")
                    != protocol.get("target_task_family_id")
                or projection.get("condition_id") != condition
                or projection.get("treatment") != expected_treatment
                or projection.get("task_probe_input_digest") != expected_probe_digest
                or projection.get("task_probe_input_count") != len(probes)
                or projection.get("historical_probe_overlap_measurement_complete")
                    is not True
                or projection.get("historical_probe_overlap_input_count") != 0
                or projected_record_ids != retrieved
                or projection.get("selected_record_count") != len(retrieved)
                or not isinstance(score, Mapping)
                or report.get("score_status") != score.get("status")
                or report.get("correct_count") != score.get("correct_count")
                or report.get("probe_count") != score.get("probe_count")
                or report.get("inference_receipt_id")
                    != observation.get("inference_receipt_id")
                or report.get("inference_receipt_digest")
                    != observation.get("inference_receipt_digest")
                or report.get("output_digest") != observation.get("output_digest")
                or delivery.get("request_id") != observation.get("request_id")
                or delivery.get("request_digest")
                    != observation.get("request_digest")
                or not isinstance(delivery.get("projection_digest"), str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}",
                    delivery["projection_digest"]) is None
                or not isinstance(retrieved, list)
                or report.get("retrieved_record_ids") != retrieved
                or delivery.get("status") != "verified_projection_bound_to_governed_request"
                or delivery.get("condition_id") != condition
                or delivery.get("treatment") != expected_treatment
                or delivery.get("task_probe_input_digest") != expected_probe_digest
                or delivery.get("task_probe_input_count") != len(probes)
                or delivery.get("historical_probe_overlap_measurement_complete") is not True
                or delivery.get("historical_probe_overlap_input_count") != 0
                or delivery.get("exact_task_family_packets_present_in_prompt") is not True
                or delivery.get("answer_values_included") is not False
                or delivery.get("raw_prompt_included") is not False):
            raise ValueError("cross_range_condition_score_receipt_binding_invalid")
        retrieved_by_condition[condition] = retrieved
        verified_receipts[condition] = {
            "receipt_id": receipt_id,
            "receipt_digest": "sha256:" + receipt_digest,
            "receipt_file_sha256": _raw_file_digest(receipt_path),
            "projection_digest": projection_digest,
            "rootless_session_binding_digest": _sha256(session_binding),
        }
        required_history = report.get("required_history_record_ids")
        if (not isinstance(required_history, list)
                or not set(required_sources).issubset(required_history)
                or report.get("required_history_record_ids_retrieved") is not
                    (condition != "history_withheld")):
            raise ValueError("cross_range_condition_required_history_invalid")
        if condition == "history_withheld":
            if retrieved or delivery.get("selected_record_count") != 0:
                raise ValueError("cross_range_withheld_history_leaked")
        elif not set(required_sources).issubset(retrieved):
            raise ValueError("cross_range_source_receipt_missing")
    if (retrieved_by_condition["history_present"]
            != retrieved_by_condition["history_restored"]):
        raise ValueError("cross_range_present_restored_history_mismatch")
    if outcome.get("exact_source_record_receipts_verified") is not True:
        raise ValueError("cross_range_exact_source_receipt_claim_invalid")

    semantic_report = {
        "schema_version":
            "sentientos.cross_range_history_enabled_competence_outcome_verification:v1",
        "status": "verified_internal_consistency",
        "campaign_id": plan["campaign_id"],
        "plan_digest": plan["plan_digest"],
        "cycle_id": cycle_id,
        "score_run_id": run_id,
        "score_run_digest": run_digest,
        "implementation_digest": implementation[
            "experiment_implementation_digest"],
        "probe_level_outcomes_digest": outcome[
            "probe_level_outcomes_digest"],
        "condition_score_digests": outcome["condition_score_digests"],
        "condition_receipts": verified_receipts,
        "source_record_ids": required_sources,
        "probe_inputs": probes,
        "learning_established": False,
        "authority": False,
        "inference_origin_attested": False,
        "verification_scope": (
            "plan_preflight_score_run_digest_per_probe_outcomes_and_condition_receipt_summary"),
        "input_artifact_digests": {
            "plan": _raw_file_digest(plan_path),
            "preflight": _raw_file_digest(preflight_path),
            "cycle_result": _raw_file_digest(cycle_result_path),
            "score_run": _raw_file_digest(score_run_path),
        },
    }
    return {**semantic_report, "audit_digest": _sha256(semantic_report)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--cycle-result", type=Path, required=True)
    parser.add_argument("--experiment-state-root", type=Path, required=True,
        help="state root containing developmental_experiments/runs")
    parser.add_argument("--output", type=Path,
        help="optional write-once path for the digest-bound verification report")
    args = parser.parse_args()
    result = verify_outcome(plan_path=args.plan,
        preflight_path=args.preflight, cycle_result_path=args.cycle_result,
        experiment_state_root=args.experiment_state_root)
    if args.output is not None:
        _write_report_exclusive(args.output, result)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
