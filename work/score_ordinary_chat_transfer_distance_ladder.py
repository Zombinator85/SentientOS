"""Score receipt-bound answers for the frozen ordinary-chat transfer ladder."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from sentientos.developmental_model_replacement_experiment import (
    FIXED_OBJECTIVE_TASK_FAMILY_MAPPINGS,
)
from sentientos.cognition_retrieval import (
    derive_ordinary_chat_integer_affine_hypothesis,
    derive_ordinary_chat_integer_affine_negative_control,
)
from sentientos.governed_local_model_invocation import validate_receipt
from sentientos.local_model_authority import digest_payload

ARMS = ("history", "empty")
CANDIDATE_ARMS = ("history", "derived_history", "empty")
CANDIDATE_SHAM_ARMS = ("history", "derived_history", "sham_history", "empty")
TIERS = ("near", "middle", "far")
TRIAL_ORDER = (
    ("near", "history"), ("near", "empty"),
    ("middle", "empty"), ("middle", "history"),
    ("far", "history"), ("far", "empty"),
)


def _validate_plan_treatment(plan: dict) -> None:
    schema = plan.get("schema")
    if schema.endswith((":v2", ":v3", ":v4", ":v5", ":v6", ":v7", ":v8", ":v9", ":v10", ":v11", ":v12", ":v13")):
        if (plan.get("format_treatment") != "strict_json_post_retrieval:v1"
                or plan.get("output_constraint") is None
                or hashlib.sha256(plan["output_constraint"].encode()).hexdigest()
                    != plan.get("output_constraint_sha256")):
            raise ValueError("strict JSON treatment is not bound to the execution plan")
    elif (plan.get("format_treatment") != "user_message_only:v1"
            or plan.get("output_constraint") is not None):
        raise ValueError("unconstrained-format execution plan has an unexpected treatment")

    if schema.endswith(":v3"):
        from work.run_ordinary_chat_transfer_distance_ladder import HISTORY_RULE_DERIVATION
        expected = ("derive_rule_from_available_history:v3", HISTORY_RULE_DERIVATION)
    elif schema.endswith(":v4"):
        from work.run_ordinary_chat_transfer_distance_ladder import EXPLICIT_RULE_CALIBRATION
        expected = ("explicit_mapping_calibration:v1", EXPLICIT_RULE_CALIBRATION)
    elif schema.endswith(":v5"):
        from work.run_ordinary_chat_transfer_distance_ladder import HISTORY_SCOPE_CLARIFICATION
        expected = ("clarify_developmental_history_scope:v1", HISTORY_SCOPE_CLARIFICATION)
    else:
        expected = (None, None)
    if (plan.get("semantic_treatment") != expected[0]
            or plan.get("semantic_procedure") != expected[1]
            or plan.get("semantic_procedure_sha256") != (
                hashlib.sha256(expected[1].encode()).hexdigest()
                if expected[1] is not None else None)):
        raise ValueError("semantic treatment is not bound to the execution plan")


def execution_from_run(preflight: dict, preflight_bytes: bytes, run_directory: Path) -> dict:
    """Bind a completed runner directory to its frozen model-free preflight."""
    plan_path = run_directory / "plan.json"
    result_path = run_directory / "result.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    run = json.loads(result_path.read_text(encoding="utf-8"))
    plan_sha = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    preflight_sha = hashlib.sha256(preflight_bytes).hexdigest()
    preflight_is_blinded_v10 = preflight.get("schema", "").endswith(":v10")
    plan_is_blinded_v13 = plan.get("schema", "").endswith(":v13")
    if preflight_is_blinded_v10 != plan_is_blinded_v13:
        raise ValueError("blinded v10 preflight requires the matching v13 execution plan")
    if (plan.get("schema") not in {
                "sentientos.ordinary_chat_transfer_distance_ladder_execution_plan:v1",
                "sentientos.ordinary_chat_transfer_distance_ladder_execution_plan:v2",
                "sentientos.ordinary_chat_transfer_distance_ladder_execution_plan:v3",
                "sentientos.ordinary_chat_transfer_distance_ladder_execution_plan:v4",
                "sentientos.ordinary_chat_transfer_distance_ladder_execution_plan:v5",
                "sentientos.ordinary_chat_transfer_distance_ladder_execution_plan:v6",
                "sentientos.ordinary_chat_transfer_distance_ladder_execution_plan:v7",
                "sentientos.ordinary_chat_transfer_distance_ladder_execution_plan:v8",
                "sentientos.ordinary_chat_transfer_distance_ladder_execution_plan:v9",
                "sentientos.ordinary_chat_transfer_distance_ladder_execution_plan:v10",
                "sentientos.ordinary_chat_transfer_distance_ladder_execution_plan:v11",
                "sentientos.ordinary_chat_transfer_distance_ladder_execution_plan:v12",
                "sentientos.ordinary_chat_transfer_distance_ladder_execution_plan:v13"}
            or plan.get("source_report_sha256") != preflight_sha
            or run.get("plan_sha256") != plan_sha
            or plan.get("task_family_id") != preflight.get("task_family_id")
            or plan.get("learning_established") is not False
            or run.get("learning_established") is not False
            or set(plan.get("tiers", {})) != set(TIERS)
            or not re.fullmatch(r"[0-9a-f]{64}", plan.get("matched_base_sha256", ""))
            or plan.get("arms", list(ARMS))
                != preflight.get("arms", list(ARMS))):
        raise ValueError("completed run does not match the frozen preflight")
    arms = tuple(preflight.get("arms", ARMS))
    has_candidate = preflight.get("derived_rule_hypothesis_treatment") is not None
    has_sham = preflight.get("affine_negative_control_treatment") is not None
    expected_arms = (CANDIDATE_SHAM_ARMS if has_sham else
        CANDIDATE_ARMS if has_candidate else ARMS)
    trial_order = tuple(tuple(item) for item in preflight.get(
        "trial_order", TRIAL_ORDER))
    if (arms != expected_arms
            or tuple((item.get("tier"), item.get("arm"))
                for item in plan.get("trial_order", ())) != trial_order
            or tuple((item.get("tier"), item.get("arm"))
                for item in run.get("trials", ())) != trial_order):
        raise ValueError("execution arms or order differ from the frozen preflight")
    if not isinstance(plan.get("model_identity"), dict):
        raise ValueError("execution plan lacks a bound model identity")
    _validate_plan_treatment(plan)
    captures: dict[str, dict] = {tier: {} for tier in TIERS}
    for index, (tier, arm) in enumerate(trial_order):
        key = tier + "_" + arm
        frozen = preflight["tiers"][tier]
        binding = plan["prompt_bindings"].get(key)
        trial = run["trials"][index]
        frozen_arm = frozen["captures"].get(arm, {})
        arm_binding = plan["prompt_bindings"].get(tier + "_" + arm, {})
        if (not isinstance(binding, dict)
                or plan.get("example_presentation", "record_linked")
                    != preflight.get("example_presentation", "record_linked")
                or plan.get("derived_rule_hypothesis_treatment")
                    != preflight.get("derived_rule_hypothesis_treatment")
                or plan.get("affine_negative_control_treatment")
                    != preflight.get("affine_negative_control_treatment")
                or plan.get("affine_candidate_provenance_visibility")
                    != preflight.get("affine_candidate_provenance_visibility")
                or plan.get("arm_hypothesis_provenance")
                    != preflight.get("arm_hypothesis_provenance")
                or plan["tiers"][tier].get("probe_inputs") != frozen.get("probe_inputs")
                or plan["tiers"][tier].get("answer_key_commitment") != frozen.get("answer_key_commitment")
                or arm_binding.get("prompt_score_evidence")
                    != frozen_arm.get("prompt_score_evidence")
                or arm_binding.get("prompt_example_renderings", [])
                    != frozen_arm.get("prompt_example_renderings", [])
                or arm_binding.get("derived_rule_hypotheses", [])
                    != frozen_arm.get("derived_rule_hypotheses", [])
                or arm_binding.get("history_instruction")
                    != frozen_arm.get("history_instruction")
                or arm_binding.get("ordinary_history_selection")
                    != frozen_arm.get("ordinary_history_selection")
                or ((arm != "empty") != bool(arm_binding.get("history_block_digest")))
                or arm_binding.get("prompt_sha256") != binding.get("prompt_sha256")
                or arm_binding.get("invocation_prompt_digest")
                    != binding.get("invocation_prompt_digest")
                or not re.fullmatch(r"[0-9a-f]{64}", binding.get("prompt_sha256", ""))
                or not re.fullmatch(r"[0-9a-f]{64}", binding.get("invocation_prompt_digest", ""))
                or trial.get("plan_sha256") != plan_sha
                or trial.get("prompt_sha256") != binding.get("prompt_sha256")
                or trial.get("delivered") != trial.get("model_output")):
            raise ValueError(f"run trial differs from its frozen prompt or answer key for {tier}/{arm}")
        receipt = trial.get("receipt")
        linkage = receipt.get("request", {}).get("linkage", {}) if isinstance(receipt, dict) else {}
        receipt_session_id = linkage.get("session_id") if isinstance(linkage, dict) else None
        trial_session_id = trial.get("session_id")
        if (not isinstance(receipt_session_id, str) or not receipt_session_id
                or (trial_session_id is not None and trial_session_id != receipt_session_id)):
            raise ValueError("trial session ID is absent or differs from its invocation receipt")
        captures[tier][arm] = {
            "arm": arm,
            "session_id": receipt_session_id,
            "prompt_sha256": trial.get("prompt_sha256"),
            "invocation_prompt_digest": binding.get("invocation_prompt_digest"),
            "model_identity": plan["model_identity"],
            "model_output": trial.get("model_output"),
            "receipt": trial.get("receipt"),
        }
    return {
        "schema": "sentientos.ordinary_chat_transfer_execution:v1",
        "preflight_sha256": digest_payload(preflight),
        "plan_sha256": plan_sha,
        "arms": list(arms),
        "model_identity": plan["model_identity"],
        "format_treatment": plan.get("format_treatment"),
        "semantic_treatment": plan.get("semantic_treatment"),
        "derived_rule_hypothesis_treatment": plan.get("derived_rule_hypothesis_treatment"),
        "affine_negative_control_treatment": plan.get("affine_negative_control_treatment"),
        "affine_candidate_provenance_visibility": plan.get(
            "affine_candidate_provenance_visibility"),
        "arm_hypothesis_provenance": plan.get("arm_hypothesis_provenance"),
        "example_presentation": plan.get("example_presentation", "record_linked"),
        "ladder_design": plan.get("ladder_design", preflight.get("ladder_design")),
        "captures": captures,
        "inference_performed": True,
        "learning_established": False,
    }


def score(preflight: dict, execution: dict) -> dict:
    if (preflight.get("schema") not in {
                "sentientos.ordinary_chat_transfer_distance_ladder_preflight:v1",
                "sentientos.ordinary_chat_transfer_distance_ladder_preflight:v2",
                "sentientos.ordinary_chat_transfer_distance_ladder_preflight:v3",
                "sentientos.ordinary_chat_transfer_distance_ladder_preflight:v8",
                "sentientos.ordinary_chat_transfer_distance_ladder_preflight:v9",
                "sentientos.ordinary_chat_transfer_distance_ladder_preflight:v10"}
            or execution.get("schema") !=
                "sentientos.ordinary_chat_transfer_execution:v1"
            or execution.get("preflight_sha256") != digest_payload(preflight)
            or preflight.get("learning_established") is not False
            or preflight.get("inference_performed") is not False
            or preflight.get("model_bound_execution_plan_created") is not False
            or execution.get("inference_performed") is not True
            or execution.get("learning_established") is not False
            or preflight.get("arms") != execution.get("arms")
            or preflight.get("derived_rule_hypothesis_treatment")
                != execution.get("derived_rule_hypothesis_treatment")
            or preflight.get("affine_negative_control_treatment")
                != execution.get("affine_negative_control_treatment")
            or preflight.get("affine_candidate_provenance_visibility")
                != execution.get("affine_candidate_provenance_visibility")
            or preflight.get("arm_hypothesis_provenance")
                != execution.get("arm_hypothesis_provenance")):
        raise ValueError("execution does not match the frozen transfer protocol")
    arms = tuple(preflight.get("arms", ARMS))
    has_candidate = preflight.get("derived_rule_hypothesis_treatment") is not None
    has_sham = preflight.get("affine_negative_control_treatment") is not None
    expected_arms = (CANDIDATE_SHAM_ARMS if has_sham else
        CANDIDATE_ARMS if has_candidate else ARMS)
    if arms != expected_arms:
        raise ValueError("preflight arms do not match the treatment")
    task_family = preflight.get("task_family_id")
    protocol = preflight.get("protocol_checks", preflight)
    if (task_family not in FIXED_OBJECTIVE_TASK_FAMILY_MAPPINGS
            or preflight.get("derived_rule_hypothesis_treatment") not in {
                None, "exact_integer_affine_fit_from_scored_rows:v1"}
            or preflight.get("affine_negative_control_treatment") not in {
                None, "same_width_offset_step_protocol_sham:v1"}
            or (preflight.get("schema", "").endswith(":v10")
                and (preflight.get("affine_candidate_provenance_visibility")
                    != "model_blinded_neutral_candidate_label:v1"
                    or preflight.get("arm_hypothesis_provenance") != {
                        "derived_history": "task_derived",
                        "sham_history": "sham_control"}))
            or has_sham and not has_candidate
            or preflight.get("derived_rule_hypothesis_projection_verified",
                False) is not (preflight.get("derived_rule_hypothesis_treatment") is not None)
            or protocol.get("probe_inputs_disjoint_from_history_and_prior_probes") is not True
            or protocol.get("all_tier_prompts_match_outside_probe_values") is not True
            or protocol.get("fixed_mapping_shared_by_source_and_novel_task_families") is not True
            or preflight.get("answer_values_withheld") is not True
            or set(preflight.get("tiers", {})) != set(TIERS)):
        raise ValueError("preflight does not meet the frozen scoring conditions")
    mapping = FIXED_OBJECTIVE_TASK_FAMILY_MAPPINGS[task_family]
    identity = execution.get("model_identity")
    captures = execution.get("captures")
    if not isinstance(identity, dict) or not isinstance(captures, dict):
        raise ValueError("execution identity or captures are missing")
    used_receipts: set[str] = set()
    used_sessions: set[str] = set()
    results = []
    multiplier, offset = mapping
    if preflight.get("schema", "").endswith(":v10"):
        for tier in TIERS:
            frozen_captures = preflight["tiers"][tier]["captures"]
            evidence = frozen_captures["history"]["prompt_score_evidence"]
            if (len(evidence) != 1
                    or frozen_captures["history"].get("derived_rule_hypotheses")
                    or frozen_captures["empty"].get("derived_rule_hypotheses")):
                raise ValueError("blinded candidate controls changed the shared history evidence")
            support = evidence[0]
            support_rows = support["examples"]
            expected_by_arm = {
                "derived_history": derive_ordinary_chat_integer_affine_hypothesis(
                    preflight["support_task_family_id"], support_rows),
                "sham_history": derive_ordinary_chat_integer_affine_negative_control(
                    preflight["support_task_family_id"], support_rows),
            }
            for arm, expected_hypothesis in expected_by_arm.items():
                entries = frozen_captures[arm].get("derived_rule_hypotheses", [])
                if (not expected_hypothesis or len(entries) != 1
                        or entries[0].get("hypothesis_kind") != "candidate"
                        or entries[0].get("hypothesis") != expected_hypothesis
                        or entries[0].get("record_id") != preflight["support_record_id"]
                        or entries[0].get("task_family_id")
                            != preflight["support_task_family_id"]
                        or entries[0].get("source_run_id") != support.get("source_run_id")
                        or entries[0].get("source_score_digest")
                            != support.get("source_score_digest")
                        or entries[0].get("source_fact_id") != support.get("source_fact_id")):
                    raise ValueError(
                        "blinded candidate arm does not match its private provenance mapping")
    for tier in TIERS:
        frozen = preflight["tiers"][tier]
        inputs = frozen["probe_inputs"]
        if not isinstance(inputs, list) or len(inputs) != 3 or any(type(x) is not int for x in inputs):
            raise ValueError("frozen probe set is invalid")
        expected = [multiplier * value + offset for value in inputs]
        commitment = "sha256:" + digest_payload({
            "task_family_id": task_family,
            "probe_inputs": inputs,
            "expected_outputs": expected,
        })
        if frozen.get("answer_key_commitment") != commitment:
            raise ValueError("frozen answer-key commitment does not match the task family")
        tier_captures = captures.get(tier)
        if not isinstance(tier_captures, dict):
            raise ValueError("tier captures are missing")
        arm_results = {}
        for arm in arms:
            capture = tier_captures.get(arm)
            if not isinstance(capture, dict) or capture.get("arm") != arm:
                raise ValueError("paired arm capture is invalid")
            output, receipt = capture.get("model_output"), capture.get("receipt")
            prompt_sha = capture.get("prompt_sha256")
            session_id = capture.get("session_id")
            if (not isinstance(prompt_sha, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", prompt_sha)
                    or not isinstance(session_id, str) or not session_id
                    or session_id in used_sessions
                    or capture.get("model_identity") != identity
                    or not isinstance(output, str) or not isinstance(receipt, dict)
                    or not validate_receipt(receipt)[0]
                    or receipt.get("status") != "admitted_completed"
                    or receipt.get("request", {}).get("active_model_identity") != identity
                    or receipt.get("request", {}).get("linkage", {}).get("session_id") != session_id
                    or receipt.get("request", {}).get("prompt_digest") != capture.get("invocation_prompt_digest")
                    or receipt.get("output_digest") != digest_payload({"output": output})
                    or not isinstance(receipt.get("receipt_id"), str)
                    or not receipt.get("receipt_id")
                    or receipt.get("receipt_id") in used_receipts):
                raise ValueError("prompt, identity, output, or receipt binding failed")
            used_receipts.add(receipt["receipt_id"])
            used_sessions.add(session_id)
            try:
                parsed = json.loads(output)
            except json.JSONDecodeError:
                parsed = None
            answers = parsed.get("answers") if isinstance(parsed, dict) and set(parsed) == {"answers"} else None
            valid = (isinstance(answers, list) and len(answers) == len(expected)
                and all(value is None or type(value) is int for value in answers))
            probe_correct = ([answer == target for answer, target in zip(answers, expected)]
                if valid else [False] * len(expected))
            arm_results[arm] = {
                "answers": answers if valid else None,
                "probe_correct": probe_correct,
                "exact": sum(probe_correct),
                "denominator": len(expected),
                "valid_json": valid,
                "session_id": session_id,
                "receipt_id": receipt["receipt_id"],
            }
        tier_result = {"tier": tier, "inputs": inputs, "expected": expected,
            **arm_results, "history_minus_empty":
                arm_results["history"]["exact"] - arm_results["empty"]["exact"]}
        if "derived_history" in arms:
            tier_result["derived_history_minus_empty"] = (
                arm_results["derived_history"]["exact"]
                - arm_results["empty"]["exact"])
            tier_result["derived_minus_raw_history"] = (
                arm_results["derived_history"]["exact"]
                - arm_results["history"]["exact"])
        if "sham_history" in arms:
            tier_result["sham_history_minus_raw_history"] = (
                arm_results["sham_history"]["exact"]
                - arm_results["history"]["exact"])
            tier_result["sham_history_minus_empty"] = (
                arm_results["sham_history"]["exact"]
                - arm_results["empty"]["exact"])
            tier_result["derived_minus_sham_history"] = (
                arm_results["derived_history"]["exact"]
                - arm_results["sham_history"]["exact"])
        results.append(tier_result)
    return {"schema": "sentientos.ordinary_chat_transfer_score:v2",
        "preflight_sha256": digest_payload(preflight), "model_identity": identity,
        "plan_sha256": execution.get("plan_sha256"),
        "format_treatment": execution.get("format_treatment"),
        "semantic_treatment": execution.get("semantic_treatment"),
        "derived_rule_hypothesis_treatment": execution.get("derived_rule_hypothesis_treatment"),
        "affine_negative_control_treatment": execution.get("affine_negative_control_treatment"),
        "affine_candidate_provenance_visibility": execution.get(
            "affine_candidate_provenance_visibility"),
        "arm_hypothesis_provenance": execution.get("arm_hypothesis_provenance"),
        "example_presentation": execution.get("example_presentation"),
        "ladder_design": execution.get("ladder_design"),
        "primary_outcome": preflight.get("primary_outcome"),
        "arms": list(arms), "tiers": results, "inference_performed": True,
        "learning_established": False, "authority": False,
        "scorer_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("preflight", type=Path)
    parser.add_argument("execution_or_run_directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    preflight_bytes = args.preflight.read_bytes()
    preflight = json.loads(preflight_bytes)
    execution = (execution_from_run(preflight, preflight_bytes, args.execution_or_run_directory)
        if args.execution_or_run_directory.is_dir() else
        json.loads(args.execution_or_run_directory.read_text(encoding="utf-8")))
    result = score(preflight, execution)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")


if __name__ == "__main__":
    main()
