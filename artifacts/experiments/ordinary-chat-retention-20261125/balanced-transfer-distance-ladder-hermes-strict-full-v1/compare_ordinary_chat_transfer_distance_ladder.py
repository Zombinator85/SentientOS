"""Compare unconstrained and post-retrieval-constrained ladder runs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _support_signature(plan: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for tier in plan["tiers"]:
        capture = plan["prompt_bindings"][tier + "_history"]["prompt_score_evidence"]
        result[tier] = [{key: item.get(key) for key in (
            "record_id", "source_run_id", "source_score_digest", "task_family_id", "examples")}
            for item in capture]
    return result


def compare(unconstrained: Path, constrained: Path, output: Path) -> dict[str, Any]:
    baseline_plan = _read(unconstrained / "plan.json")
    treatment_plan = _read(constrained / "plan.json")
    baseline_score = _read(unconstrained / "independent-score.json")
    treatment_score = _read(constrained / "independent-score.json")
    baseline_result = _read(unconstrained / "result.json")
    treatment_result = _read(constrained / "result.json")
    if (baseline_score.get("plan_sha256") != _sha(unconstrained / "plan.json")
            or treatment_score.get("plan_sha256") != _sha(constrained / "plan.json")
            or baseline_result.get("plan_sha256") != baseline_score.get("plan_sha256")
            or treatment_result.get("plan_sha256") != treatment_score.get("plan_sha256")):
        raise ValueError("each score and result must bind to its own frozen plan")
    same_identity = (baseline_plan.get("model_identity") == treatment_plan.get("model_identity")
        and baseline_plan.get("model_manifest_sha256") == treatment_plan.get("model_manifest_sha256")
        and baseline_plan.get("model") == treatment_plan.get("model"))
    same_generation = (baseline_plan.get("generation") == treatment_plan.get("generation")
        and baseline_plan.get("options") == treatment_plan.get("options")
        and baseline_plan.get("gpu_layers") == treatment_plan.get("gpu_layers"))
    same_questions = (baseline_plan.get("tiers") == treatment_plan.get("tiers")
        and baseline_plan.get("trial_order") == treatment_plan.get("trial_order"))
    same_support = _support_signature(baseline_plan) == _support_signature(treatment_plan)
    if not all((same_identity, same_generation, same_questions, same_support)):
        raise ValueError("comparison changed model, generation, probes/order, or scored history evidence")
    if treatment_plan.get("format_treatment") != "strict_json_post_retrieval:v1":
        raise ValueError("constrained run lacks the preregistered output-format treatment")
    baseline_valid = sum(row["strict_json_valid"] for row in baseline_score["trials"])
    treatment_valid = sum(row["strict_json_valid"] for row in treatment_score["trials"])
    baseline_correct = sum(row["correct_count"] for row in baseline_score["trials"])
    treatment_correct = sum(row["correct_count"] for row in treatment_score["trials"])
    summary = {}
    for tier in baseline_score["tier_summaries"]:
        before, after = baseline_score["tier_summaries"][tier], treatment_score["tier_summaries"][tier]
        summary[tier] = {
            "unconstrained_history_correct": before["history_correct_count"],
            "unconstrained_empty_correct": before["empty_correct_count"],
            "constrained_history_correct": after["history_correct_count"],
            "constrained_empty_correct": after["empty_correct_count"],
            "constrained_history_json_valid": after["history_json_valid"],
            "constrained_empty_json_valid": after["empty_json_valid"],
        }
    report = {
        "schema": "sentientos.ordinary_chat_transfer_distance_ladder_format_comparison:v1",
        "unconstrained_plan_sha256": baseline_score["plan_sha256"],
        "constrained_plan_sha256": treatment_score["plan_sha256"],
        "comparison_source_sha256": _sha(Path(__file__).resolve()),
        "same_model_identity": same_identity,
        "same_generation_and_gpu_settings": same_generation,
        "same_questions_probe_tiers_and_order": same_questions,
        "same_scored_history_evidence": same_support,
        "strict_json_valid_trials": {"unconstrained": [baseline_valid, 6], "constrained": [treatment_valid, 6]},
        "exact_correct_answers": {"unconstrained": [baseline_correct, 18], "constrained": [treatment_correct, 18]},
        "tier_results": summary,
        "interpretation": (
            "The post-retrieval format instruction changed strict-format compliance but did not produce "
            "correct transfer answers in this single-model run. This does not establish durable learning."),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("unconstrained_run", type=Path)
    parser.add_argument("constrained_run", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = compare(args.unconstrained_run, args.constrained_run, args.output)
    print("ladder_format_comparison_saved", report["constrained_plan_sha256"], flush=True)
