"""Audit confidence saturation in a completed rootless cognition campaign.

This CPU-only report verifies the campaign plan, terminal cycles, acquisition
runs, and v6 score digests before aggregating confidence and correctness. It
omits answer values and does not establish calibration, learning, or causality.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping


REPORT_SCHEMA = "sentientos.rootless_campaign_confidence_diagnostic:v3"
CONDITION_ORDER = ("history_present", "history_withheld", "history_restored")
MAX_INPUT_BYTES = 16 * 1024 * 1024


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_object(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("confidence_audit_input_file_invalid")
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("confidence_audit_input_over_bound")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("confidence_audit_input_json_invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("confidence_audit_input_object_invalid")
    return value


def _verify_sealed_digest(value: Mapping[str, Any], digest_key: str,
        error_code: str) -> None:
    claimed = value.get(digest_key)
    semantic = {key: item for key, item in value.items() if key != digest_key}
    expected = _digest(semantic)
    if not isinstance(claimed, str) or claimed not in {expected, "sha256:" + expected}:
        raise ValueError(error_code)


def _score_diagnostic(score: Mapping[str, Any]) -> dict[str, Any]:
    if score.get("schema_version") != "sentientos.objective_task_score:v6":
        raise ValueError("confidence_audit_score_schema_unsupported")
    _verify_sealed_digest(score, "score_digest",
        "confidence_audit_score_digest_mismatch")
    results = score.get("probe_results")
    confidence = score.get("confidence_basis_points")
    if (not isinstance(results, list) or not results
            or not isinstance(confidence, list) or len(confidence) != len(results)):
        raise ValueError("confidence_audit_probe_vector_invalid")
    correct_count = answered_count = abstained_count = 0
    brier_sum = brier_count = max_confidence_count = max_confidence_errors = 0
    for result, confidence_value in zip(results, confidence):
        if not isinstance(result, Mapping):
            raise ValueError("confidence_audit_probe_result_invalid")
        correct = result.get("correct")
        if (confidence_value != result.get("confidence_basis_points")
                or (confidence_value is not None and (
                    type(confidence_value) is not int
                    or not 0 <= confidence_value <= 10_000))):
            raise ValueError("confidence_audit_confidence_binding_invalid")
        if type(correct) is bool:
            answered_count += 1
            correct_count += int(correct)
            if type(confidence_value) is not int:
                raise ValueError("confidence_audit_answer_confidence_missing")
            brier_sum += (confidence_value - (10_000 if correct else 0)) ** 2
            brier_count += 1
            if confidence_value == 10_000:
                max_confidence_count += 1
                max_confidence_errors += int(not correct)
        elif correct is None and confidence_value is None:
            abstained_count += 1
        else:
            raise ValueError("confidence_audit_outcome_shape_invalid")
    if (score.get("correct_count") != correct_count
            or score.get("answered_count") != answered_count
            or score.get("abstained_count") != abstained_count
            or score.get("brier_scored_answer_count") != brier_count
            or score.get("brier_squared_error_sum_basis_points_squared") != brier_sum
            or answered_count + abstained_count != len(results)):
        raise ValueError("confidence_audit_aggregate_binding_invalid")
    return {
        "score_digest": score["score_digest"],
        "probe_count": len(results),
        "answered_count": answered_count,
        "abstained_count": abstained_count,
        "correct_count": correct_count,
        "max_confidence_answer_count": max_confidence_count,
        "incorrect_at_max_confidence_count": max_confidence_errors,
        "brier_squared_error_sum_basis_points_squared": brier_sum,
        "brier_scored_answer_count": brier_count,
    }


def _affine_mapping(descriptor: Mapping[str, Any]) -> tuple[int, int] | None:
    observations = descriptor.get("synthetic_training_observations")
    if (not isinstance(observations, list) or len(observations) < 2
            or any(not isinstance(row, Mapping)
                or type(row.get("input")) is not int
                or type(row.get("output")) is not int for row in observations[:2])):
        return None
    left, right = observations[:2]
    delta_input = right["input"] - left["input"]
    delta_output = right["output"] - left["output"]
    if delta_input == 0 or delta_output % delta_input:
        return None
    multiplier = delta_output // delta_input
    return multiplier, left["output"] - multiplier * left["input"]


def _history_mapping_relation(*, cycle_root: Path,
        condition: Mapping[str, Any], current_descriptor: Mapping[str, Any],
        task_family_id: str) -> dict[str, Any]:
    ids = condition.get("retrieved_record_ids")
    digests = condition.get("retrieved_record_digests")
    selection = condition.get("developmental_history_selection")
    selected = selection.get("selected_records") if isinstance(selection, Mapping) else None
    if (not isinstance(ids, list) or not isinstance(digests, list)
            or len(ids) != len(digests) or len(ids) > 4
            or not isinstance(selected, list)
            or [(row.get("record_id"), row.get("record_digest"))
                for row in selected if isinstance(row, Mapping)]
                != list(zip(ids, digests))):
        raise ValueError("confidence_audit_history_selection_binding_invalid")
    record_root = cycle_root / "resident-cognition" / "history" / "records"
    current_mapping = _affine_mapping(current_descriptor)
    matching = conflicting = unknown = 0
    family_fact_count = 0
    record_integrity_verified_count = 0
    for record_id, record_digest in zip(ids, digests):
        if (not isinstance(record_id, str)
                or not isinstance(record_digest, str)):
            raise ValueError("confidence_audit_history_reference_invalid")
        record = _read_object(record_root / (record_id + ".json"))
        semantic_record = {key: value for key, value in record.items()
            if key not in {"record_id", "record_digest"}}
        expected_record_digest = "sha256:" + _digest(semantic_record)
        expected_record_id = "devrec-" + expected_record_digest.removeprefix(
            "sha256:")[:24]
        if (record.get("record_id") != record_id
                or record_id != expected_record_id
                or record.get("record_digest") != record_digest
                or record_digest != expected_record_digest):
            raise ValueError("confidence_audit_history_record_digest_mismatch")
        if any(record.get(flag) is not False for flag in (
                "current_truth", "authority", "policy",
                "canonical_explicit_user_retention")):
            raise ValueError("confidence_audit_history_record_posture_invalid")
        record_integrity_verified_count += 1
        candidate = record.get("candidate")
        facts = candidate.get("selected_facts") if isinstance(candidate, Mapping) else None
        if not isinstance(facts, list):
            continue
        found_family_fact = False
        for fact in facts:
            payload = fact.get("payload") if isinstance(fact, Mapping) else None
            if (not isinstance(payload, Mapping)
                    or payload.get("objective_task_family") != task_family_id):
                continue
            found_family_fact = True
            descriptor = payload.get("objective_task_descriptor")
            prior_mapping = (_affine_mapping(descriptor)
                if isinstance(descriptor, Mapping) else None)
            if current_mapping is None or prior_mapping is None:
                unknown += 1
            elif current_mapping == prior_mapping:
                matching += 1
            else:
                conflicting += 1
        if found_family_fact:
            family_fact_count += 1
    if not ids:
        posture = "no_history_selected"
    elif family_fact_count == 0:
        posture = "no_selected_task_family_mapping_examples"
    elif unknown:
        posture = "selected_task_family_mapping_relation_incomplete"
    elif conflicting:
        posture = "selected_history_contains_mapping_conflict"
    else:
        posture = "all_projectable_selected_mappings_match_current_task"
    return {
        "selected_record_count": len(ids),
        "record_integrity_verified_count": record_integrity_verified_count,
        "record_integrity_posture": "all_selected_record_digests_and_postures_verified",
        "selected_records_with_task_family_examples": family_fact_count,
        "mapping_match_count": matching,
        "mapping_conflict_count": conflicting,
        "mapping_relation_unknown_count": unknown,
        "mapping_relation_posture": posture,
        "mapping_values_included": False,
    }


def _condition_outcomes(score: Mapping[str, Any]) -> tuple[list[int], list[tuple[bool | None, bool]]]:
    results = score.get("probe_results")
    if not isinstance(results, list):
        raise ValueError("confidence_audit_probe_result_invalid")
    inputs: list[int] = []
    outcomes: list[tuple[bool | None, bool]] = []
    for result in results:
        if (not isinstance(result, Mapping)
                or type(result.get("probe_input")) is not int
                or (result.get("correct") is not None
                    and type(result.get("correct")) is not bool)):
            raise ValueError("confidence_audit_probe_result_invalid")
        inputs.append(result["probe_input"])
        outcomes.append((result.get("correct"), result.get("abstained") is True))
    if len(set(inputs)) != len(inputs):
        raise ValueError("confidence_audit_probe_inputs_not_unique")
    return inputs, outcomes


def _compare_conditions(left: Mapping[str, Any], right: Mapping[str, Any], *,
        left_name: str, right_name: str) -> dict[str, Any]:
    left_inputs, left_outcomes = _condition_outcomes(left)
    right_inputs, right_outcomes = _condition_outcomes(right)
    if left_inputs != right_inputs or left.get("task_digest") != right.get("task_digest"):
        raise ValueError("confidence_audit_matched_condition_binding_invalid")
    differences = [(a, b) for a, b in zip(left_outcomes, right_outcomes) if a != b]
    correctness_differences = sum(a[0] != b[0] for a, b in differences)
    left_correct = sum(outcome[0] is True for outcome in left_outcomes)
    right_correct = sum(outcome[0] is True for outcome in right_outcomes)
    return {
        "left_condition": left_name,
        "right_condition": right_name,
        "probe_count": len(left_inputs),
        "left_correct_count": left_correct,
        "right_correct_count": right_correct,
        "correct_count_delta": left_correct - right_correct,
        "outcome_difference_count": len(differences),
        "correctness_difference_count": correctness_differences,
        "outcomes_match_exactly": not differences,
        "task_digest": left.get("task_digest"),
        "probe_input_digest": _digest({"probe_inputs": left_inputs}),
        "raw_probe_inputs_included": False,
    }


def create_report(*, plan_path: Path, campaign_audit_path: Path,
        cycle_roots: list[Path]) -> dict[str, Any]:
    plan = _read_object(plan_path)
    campaign_audit = _read_object(campaign_audit_path)
    _verify_sealed_digest(plan, "plan_digest",
        "confidence_audit_plan_digest_mismatch")
    _verify_sealed_digest(campaign_audit, "audit_digest",
        "confidence_audit_campaign_digest_mismatch")
    if (campaign_audit.get("plan_digest") != plan.get("plan_digest")
            or campaign_audit.get("campaign_id") != plan.get("campaign_id")
            or campaign_audit.get("all_planned_cycles_completed") is not True
            or campaign_audit.get("learning_established") is not False
            or campaign_audit.get("authority") is not False):
        raise ValueError("confidence_audit_campaign_binding_invalid")
    cycle_ids = plan.get("ordered_cycle_ids")
    if (not isinstance(cycle_ids, list) or len(cycle_roots) != len(cycle_ids)
            or len(set(cycle_ids)) != len(cycle_ids)):
        raise ValueError("confidence_audit_cycle_order_invalid")

    condition_rows: list[dict[str, Any]] = []
    cycle_rows: list[dict[str, Any]] = []
    total_answered = total_correct = total_abstained = 0
    total_max_confidence = total_max_confidence_errors = 0
    total_brier_sum = total_brier_count = 0
    for index, (cycle_id, cycle_root) in enumerate(zip(cycle_ids, cycle_roots)):
        if cycle_root.is_symlink() or not cycle_root.is_dir() or cycle_root.name != cycle_id:
            raise ValueError("confidence_audit_cycle_root_invalid")
        terminal = _read_object(cycle_root / "cycle-result.json")
        if (terminal.get("status") != "completed"
                or terminal.get("run_id") != cycle_id
                or terminal.get("external_preregistration_digest")
                    != plan.get("plan_digest")):
            raise ValueError("confidence_audit_terminal_plan_binding_invalid")
        campaign_binding = terminal.get("history_campaign_binding")
        if (not isinstance(campaign_binding, Mapping)
                or campaign_binding.get("campaign_id") != plan.get("campaign_id")
                or campaign_binding.get("campaign_plan_digest") != plan.get("plan_digest")
                or campaign_binding.get("cycle_index") != index):
            raise ValueError("confidence_audit_terminal_campaign_binding_invalid")
        identity = terminal.get("active_model_identity")
        identity_digest = ("sha256:" + _digest({"identity": dict(identity)})
            if isinstance(identity, Mapping) else None)
        expected_identity = plan.get("ordered_model_identity_digests", [])[index]
        if identity_digest != "sha256:" + expected_identity:
            raise ValueError("confidence_audit_model_identity_binding_invalid")

        acquisition = terminal.get("objective_task_family_acquisition")
        if not isinstance(acquisition, Mapping):
            raise ValueError("confidence_audit_acquisition_summary_missing")
        run_id, run_digest = acquisition.get("run_id"), acquisition.get("run_digest")
        if not isinstance(run_id, str) or not isinstance(run_digest, str):
            raise ValueError("confidence_audit_acquisition_run_binding_missing")
        run_path = (cycle_root / "resident-cognition" / "state"
            / "developmental_experiments" / "runs" / (run_id + ".json"))
        run = _read_object(run_path)
        if run.get("run_id") != run_id or run.get("run_digest") != run_digest:
            raise ValueError("confidence_audit_acquisition_run_binding_invalid")
        semantic_run = {key: value for key, value in run.items()
            if key not in {"run_id", "run_digest"}}
        if run_digest != "sha256:" + _digest(semantic_run):
            raise ValueError("confidence_audit_acquisition_run_digest_mismatch")
        score_rows = run.get("objective_scores")
        if (not isinstance(score_rows, list) or len(score_rows) != len(CONDITION_ORDER)
                or tuple(row.get("condition_id") for row in score_rows
                    if isinstance(row, Mapping)) != CONDITION_ORDER):
            raise ValueError("confidence_audit_condition_order_invalid")
        scores_by_condition = {
            row["condition_id"]: row["score"] for row in score_rows
            if isinstance(row, Mapping) and isinstance(row.get("score"), Mapping)}
        raw_conditions = run.get("conditions")
        if not isinstance(raw_conditions, list) or len(raw_conditions) != 3:
            raise ValueError("confidence_audit_condition_context_missing")
        conditions_by_id = {row.get("condition_id"): row for row in raw_conditions
            if isinstance(row, Mapping)}
        protocol = run.get("protocol")
        current_descriptor = (protocol.get("objective_task_descriptor")
            if isinstance(protocol, Mapping) else None)
        if (set(conditions_by_id) != set(CONDITION_ORDER)
                or set(scores_by_condition) != set(CONDITION_ORDER)
                or not isinstance(current_descriptor, Mapping)
                or current_descriptor.get("task_family_id") != plan.get("task_family_id")):
            raise ValueError("confidence_audit_task_family_context_invalid")
        if any(score.get("task_digest") != current_descriptor.get("task_digest")
                for score in scores_by_condition.values()):
            raise ValueError("confidence_audit_current_task_digest_mismatch")
        matched_history_effects = {
            "history_present_vs_history_withheld": _compare_conditions(
                scores_by_condition["history_present"],
                scores_by_condition["history_withheld"],
                left_name="history_present", right_name="history_withheld"),
            "history_restored_vs_history_present": _compare_conditions(
                scores_by_condition["history_restored"],
                scores_by_condition["history_present"],
                left_name="history_restored", right_name="history_present"),
        }
        selected_mapping_relation = _history_mapping_relation(
            cycle_root=cycle_root,
            condition=conditions_by_id["history_present"],
            current_descriptor=current_descriptor,
            task_family_id=str(plan["task_family_id"]))
        run_correct = run_answered = run_abstained = 0
        run_max_confidence = run_max_errors = run_brier_sum = run_brier_count = 0
        for row in score_rows:
            score = row.get("score")
            if not isinstance(score, Mapping):
                raise ValueError("confidence_audit_score_missing")
            diagnostic = _score_diagnostic(score)
            summary = {"cycle_id": cycle_id,
                "condition_id": row["condition_id"], **diagnostic}
            condition_rows.append(summary)
            run_correct += diagnostic["correct_count"]
            run_answered += diagnostic["answered_count"]
            run_abstained += diagnostic["abstained_count"]
            run_max_confidence += diagnostic["max_confidence_answer_count"]
            run_max_errors += diagnostic["incorrect_at_max_confidence_count"]
            run_brier_sum += diagnostic[
                "brier_squared_error_sum_basis_points_squared"]
            run_brier_count += diagnostic["brier_scored_answer_count"]

        binding = acquisition.get("history_score_binding")
        present_score = score_rows[0].get("score")
        if (not isinstance(binding, Mapping)
                or binding.get("verified") is not True
                or binding.get("source_run_id") != run_id
                or binding.get("expected_score_digest")
                    != present_score.get("score_digest")):
            raise ValueError("confidence_audit_history_score_binding_invalid")
        cycle_rows.append({
            "cycle_id": cycle_id,
            "acquisition_run_id": run_id,
            "acquisition_run_digest": run_digest,
            "condition_count": len(score_rows),
            "answered_count": run_answered,
            "correct_count": run_correct,
            "abstained_count": run_abstained,
            "max_confidence_answer_count": run_max_confidence,
            "incorrect_at_max_confidence_count": run_max_errors,
            "brier_squared_error_sum_basis_points_squared": run_brier_sum,
            "brier_scored_answer_count": run_brier_count,
            "history_present_acquisition_status": present_score.get("status"),
            "history_present_score_binding_verified": True,
            "matched_history_condition_effects": matched_history_effects,
            "selected_history_mapping_relation": selected_mapping_relation,
        })
        total_answered += run_answered
        total_correct += run_correct
        total_abstained += run_abstained
        total_max_confidence += run_max_confidence
        total_max_confidence_errors += run_max_errors
        total_brier_sum += run_brier_sum
        total_brier_count += run_brier_count

    all_answers_max_confidence = total_answered > 0 and (
        total_max_confidence == total_answered)
    if all_answers_max_confidence and total_max_confidence_errors:
        saturation_status = "maximum_confidence_errors_observed"
    elif all_answers_max_confidence:
        saturation_status = "maximum_confidence_without_observed_error"
    else:
        saturation_status = "confidence_varied_or_incomplete"
    semantic = {
        "schema_version": REPORT_SCHEMA,
        "campaign_id": plan["campaign_id"],
        "plan_digest": plan["plan_digest"],
        "campaign_audit_digest": campaign_audit["audit_digest"],
        "cycle_count": len(cycle_rows),
        "cycles": cycle_rows,
        "condition_scores": condition_rows,
        "aggregate": {
            "answered_count": total_answered,
            "correct_count": total_correct,
            "incorrect_count": total_answered - total_correct,
            "abstained_count": total_abstained,
            "max_confidence_answer_count": total_max_confidence,
            "incorrect_at_max_confidence_count": total_max_confidence_errors,
            "brier_squared_error_sum_basis_points_squared": total_brier_sum,
            "brier_scored_answer_count": total_brier_count,
            "normalized_mean_brier_score_millionths": (
                (total_brier_sum * 1_000_000 + total_brier_count * 50_000_000)
                    // (total_brier_count * 100_000_000)
                if total_brier_count else None),
            "all_answered_probes_at_maximum_confidence": all_answers_max_confidence,
            "confidence_saturation_status": saturation_status,
        },
        "interpretation_posture": (
            "descriptive_score_bound_confidence_error_and_matched_history_exposure_summary; "
            "condition differences are exposure associations, not causal estimates; "
            "matched conditions and repeated task family are not independent "
            "calibration samples"),
        "raw_answers_included": False,
        "prompt_or_model_output_text_included": False,
        "calibration_established": False,
        "model_attention_established": False,
        "learning_established": False,
        "authority": False,
    }
    return {**semantic, "report_digest": _digest(semantic)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--campaign-audit", type=Path, required=True)
    parser.add_argument("--cycle-root", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = create_report(plan_path=args.plan,
        campaign_audit_path=args.campaign_audit,
        cycle_roots=args.cycle_root)
    output_path = args.output
    if output_path.is_symlink():
        raise ValueError("confidence_audit_output_path_invalid")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(output_path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(report, sort_keys=True, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({
        "operation": "created",
        "report": str(output_path),
        "report_digest": report["report_digest"],
        "aggregate": report["aggregate"],
        "calibration_established": False,
        "learning_established": False,
        "authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
