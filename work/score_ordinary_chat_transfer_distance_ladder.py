"""Independently score the frozen history-versus-empty transfer ladder."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sentientos.developmental_model_replacement_experiment import (
    FIXED_OBJECTIVE_TASK_FAMILY_MAPPINGS,
)
from sentientos.governed_local_model_invocation import validate_receipt
from sentientos.local_model_authority import digest_payload
from work.preflight_sibling_chat_histories import read
from work.run_ordinary_chat_transfer_distance_ladder import REPORT, TRIAL_ORDER, sha


def _strict_answers(raw: Any, count: int) -> tuple[bool, list[int | None] | None]:
    if not isinstance(raw, str):
        return False, None
    try:
        payload = json.loads(raw)
    except ValueError:
        return False, None
    if (not isinstance(payload, dict) or set(payload) != {"answers"}
            or not isinstance(payload["answers"], list)
            or len(payload["answers"]) != count
            or any(answer is not None and type(answer) is not int for answer in payload["answers"])):
        return False, None
    return True, payload["answers"]


def _validate_plan_evidence(plan: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    presentation = protocol.get("example_presentation", "record_linked")
    if presentation not in {"structured_only", "record_linked"}:
        raise ValueError("unknown history example presentation")
    if plan.get("example_presentation", "record_linked") != presentation:
        raise ValueError("execution plan example presentation differs from the frozen preflight")
    history_records = {}
    for tier, tier_protocol in protocol["tiers"].items():
        history = plan["prompt_bindings"][tier + "_history"]
        empty = plan["prompt_bindings"][tier + "_empty"]
        expected = tier_protocol["captures"]["history"]["prompt_score_evidence"]
        if not expected or history.get("prompt_score_evidence") != expected:
            raise ValueError(f"{tier} history evidence differs from the frozen model-free preflight")
        expected_renderings = tier_protocol["captures"]["history"].get(
            "prompt_example_renderings", [])
        if (history.get("prompt_example_renderings", []) != expected_renderings
                or (presentation == "record_linked" and not expected_renderings)
                or (presentation == "structured_only" and expected_renderings)):
            raise ValueError(f"{tier} rendered examples differ from the frozen preflight")
        if (not history.get("history_block_digest")
                or empty.get("prompt_score_evidence") != []
                or empty.get("prompt_example_renderings") != []
                or empty.get("history_block_digest") is not None):
            raise ValueError(f"{tier} history/empty evidence separation is invalid")
        history_records[tier] = [item["record_id"] for item in expected]
    return {
        "history_matches_model_free_preflight": True,
        "empty_arm_exposed_no_history": True,
        "history_record_ids_by_tier": history_records,
    }


def score(run_directory: Path, output: Path,
          preflight_report: Path | None = None) -> dict[str, Any]:
    plan_path = run_directory / "plan.json"
    plan, result = read(plan_path), read(run_directory / "result.json")
    selected_report = preflight_report or REPORT
    protocol = read(selected_report)
    plan_digest = sha(plan_path.read_bytes())
    if (plan.get("schema") not in {
                "sentientos.ordinary_chat_transfer_distance_ladder_execution_plan:v1",
                "sentientos.ordinary_chat_transfer_distance_ladder_execution_plan:v2",
                "sentientos.ordinary_chat_transfer_distance_ladder_execution_plan:v3",
                "sentientos.ordinary_chat_transfer_distance_ladder_execution_plan:v4"}
            or plan_digest != result.get("plan_sha256")
            or plan.get("source_report_sha256") != sha(selected_report.read_bytes())
            or set(plan.get("tiers", {})) != set(protocol.get("tiers", {}))):
        raise ValueError("execution plan or results do not match the frozen ladder preflight")
    if plan["schema"].endswith((":v2", ":v3", ":v4")):
        if (plan.get("format_treatment") != "strict_json_post_retrieval:v1"
                or plan.get("output_constraint_sha256") != sha(plan["output_constraint"].encode())):
            raise ValueError("post-retrieval output constraint is not bound to the execution plan")
        if plan["schema"].endswith(":v3"):
            from work.run_ordinary_chat_transfer_distance_ladder import HISTORY_RULE_DERIVATION
            if (plan.get("semantic_treatment") != "derive_rule_from_available_history:v3"
                    or plan.get("semantic_procedure") != HISTORY_RULE_DERIVATION
                    or plan.get("semantic_procedure_sha256") != sha(HISTORY_RULE_DERIVATION.encode())):
                raise ValueError("history rule-derivation procedure is not bound to the execution plan")
        if plan["schema"].endswith(":v4"):
            from work.run_ordinary_chat_transfer_distance_ladder import EXPLICIT_RULE_CALIBRATION
            if (plan.get("semantic_treatment") != "explicit_mapping_calibration:v1"
                    or plan.get("semantic_procedure") != EXPLICIT_RULE_CALIBRATION
                    or plan.get("semantic_procedure_sha256") != sha(EXPLICIT_RULE_CALIBRATION.encode())):
                raise ValueError("explicit mapping calibration is not bound to the execution plan")
    elif plan.get("format_treatment") != "user_message_only:v1" or plan.get("output_constraint") is not None:
        raise ValueError("unconstrained-format execution plan has an unexpected treatment")
    if [(item.get("tier"), item.get("arm")) for item in result.get("trials", ())] != list(TRIAL_ORDER):
        raise ValueError("trial order differs from preregistration")
    evidence_validation = _validate_plan_evidence(plan, protocol)
    task_family = protocol["task_family_id"]
    if plan.get("task_family_id", task_family) != task_family:
        raise ValueError("execution plan task family differs from the frozen preflight")
    mapping = FIXED_OBJECTIVE_TASK_FAMILY_MAPPINGS[task_family]
    summaries: dict[str, dict[str, Any]] = {}
    trial_rows = []
    for tier, tier_protocol in protocol["tiers"].items():
        probes = tier_protocol["probe_inputs"]
        key = [mapping[0] * probe + mapping[1] for probe in probes]
        commitment = "sha256:" + digest_payload({
            "task_family_id": task_family,
            "probe_inputs": probes, "expected_outputs": key,
        })
        if plan["tiers"][tier].get("answer_key_commitment") != commitment:
            raise ValueError(f"answer key commitment mismatch for tier {tier}")
        rows_by_arm = {}
        for trial in (row for row in result["trials"] if row["tier"] == tier):
            arm = trial["arm"]
            if arm in rows_by_arm:
                raise ValueError(f"duplicate {tier}/{arm} trial")
            receipt = trial.get("receipt")
            raw = trial.get("delivered")
            binding = plan["prompt_bindings"][tier + "_" + arm]
            if (not validate_receipt(receipt)[0]
                    or receipt.get("request", {}).get("active_model_identity") != plan.get("model_identity")
                    or receipt.get("request", {}).get("prompt_digest") != binding.get("invocation_prompt_digest")
                    or receipt.get("output_digest") != digest_payload({"output": raw})
                    or trial.get("prompt_sha256") != binding.get("prompt_sha256")
                    or trial.get("model_output") != raw):
                raise ValueError(f"{tier}/{arm} response does not match its governed prompt receipt")
            format_valid, answers = _strict_answers(raw, len(probes))
            correct = ([answer == expected for answer, expected in zip(answers, key, strict=True)]
                       if format_valid else [False] * len(probes))
            row = {"tier": tier, "arm": arm, "strict_json_valid": format_valid,
                "answers": answers, "probe_correct": correct,
                "correct_count": sum(correct), "denominator": len(probes),
                "receipt_id": receipt.get("receipt_id")}
            rows_by_arm[arm] = row
            trial_rows.append(row)
        if set(rows_by_arm) != {"history", "empty"}:
            raise ValueError(f"tier {tier} lacks one history and one empty trial")
        summaries[tier] = {
            "history_correct_count": rows_by_arm["history"]["correct_count"],
            "empty_correct_count": rows_by_arm["empty"]["correct_count"],
            "history_minus_empty_correct_count": (
                rows_by_arm["history"]["correct_count"] - rows_by_arm["empty"]["correct_count"]),
            "history_json_valid": rows_by_arm["history"]["strict_json_valid"],
            "empty_json_valid": rows_by_arm["empty"]["strict_json_valid"],
            "denominator_per_arm": len(probes),
        }
    report = {
        "schema": "sentientos.ordinary_chat_transfer_distance_ladder_independent_score:v2",
        "plan_sha256": plan_digest,
        "preflight_sha256": sha(selected_report.read_bytes()),
        "ladder_design": protocol.get("ladder_design", "balanced_magnitude_v1"),
        "scorer_source_sha256": sha(Path(__file__).read_bytes()),
        "prompt_evidence_validation": evidence_validation,
        "format_treatment": plan.get("format_treatment"),
        "tier_summaries": summaries,
        "trials": trial_rows,
        "learning_established": False,
        "interpretation": (
            "Immediate transfer scores under one model and frozen history; the report does not establish "
            "durable learning or causal attribution to the history's original acquisition."),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--preflight-report", type=Path,
        help="The protocol report bound by the execution plan")
    args = parser.parse_args()
    report = score(args.run_directory, args.output, args.preflight_report)
    print("independent_ladder_score_saved", report["plan_sha256"], flush=True)
