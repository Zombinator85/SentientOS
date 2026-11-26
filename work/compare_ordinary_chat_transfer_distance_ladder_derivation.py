"""Compare strict-format ladder runs with and without history rule scaffolding."""
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
    return {
        tier: [{key: item.get(key) for key in (
            "record_id", "source_run_id", "source_score_digest", "task_family_id", "examples")}
            for item in plan["prompt_bindings"][tier + "_history"]["prompt_score_evidence"]]
        for tier in plan["tiers"]
    }


def compare(control: Path, derivation: Path, output: Path, *,
            control_score_path: Path | None = None,
            derivation_score_path: Path | None = None) -> dict[str, Any]:
    control_plan, derivation_plan = _read(control / "plan.json"), _read(derivation / "plan.json")
    control_score_path = control_score_path or (control / "independent-score.json")
    derivation_score_path = derivation_score_path or (derivation / "independent-score.json")
    control_score, derivation_score = _read(control_score_path), _read(derivation_score_path)
    expected_scorer_sha256 = _sha(Path(__file__).with_name("score_ordinary_chat_transfer_distance_ladder.py"))
    for directory, plan, score in ((control, control_plan, control_score),
                                   (derivation, derivation_plan, derivation_score)):
        if score.get("plan_sha256") != _sha(directory / "plan.json"):
            raise ValueError("independent score does not bind to its frozen plan")
        evidence_validation = score.get("prompt_evidence_validation", {})
        if (score.get("schema") != "sentientos.ordinary_chat_transfer_distance_ladder_independent_score:v2"
                or score.get("scorer_source_sha256") != expected_scorer_sha256
                or evidence_validation.get("history_matches_model_free_preflight") is not True
                or evidence_validation.get("empty_arm_exposed_no_history") is not True):
            raise ValueError("both runs must be rescored with the independent prompt-evidence validator")
        result = _read(directory / "result.json")
        if result.get("plan_sha256") != score["plan_sha256"]:
            raise ValueError("run result and score bind to different plans")

    same_model = (control_plan.get("model_identity") == derivation_plan.get("model_identity")
        and control_plan.get("model_manifest_sha256") == derivation_plan.get("model_manifest_sha256")
        and control_plan.get("model") == derivation_plan.get("model"))
    same_generation = (control_plan.get("generation") == derivation_plan.get("generation")
        and control_plan.get("options") == derivation_plan.get("options")
        and control_plan.get("gpu_layers") == derivation_plan.get("gpu_layers"))
    same_task = (control_plan.get("tiers") == derivation_plan.get("tiers")
        and control_plan.get("trial_order") == derivation_plan.get("trial_order"))
    same_support = _support_signature(control_plan) == _support_signature(derivation_plan)
    same_format = (control_plan.get("format_treatment") == "strict_json_post_retrieval:v1"
        and derivation_plan.get("format_treatment") == "strict_json_post_retrieval:v1"
        and control_plan.get("output_constraint_sha256") == derivation_plan.get("output_constraint_sha256"))
    if not all((same_model, same_generation, same_task, same_support, same_format)):
        raise ValueError("comparison changed model, generation, format, task/order, or history evidence")
    if control_plan.get("semantic_treatment") is not None:
        raise ValueError("control run must not contain the semantic derivation treatment")
    if derivation_plan.get("semantic_treatment") != "derive_rule_from_available_history:v2":
        raise ValueError("treatment run lacks the frozen history rule-derivation procedure")

    tier_results = {}
    for tier in control_score["tier_summaries"]:
        base, treated = control_score["tier_summaries"][tier], derivation_score["tier_summaries"][tier]
        tier_results[tier] = {
            "control_history_correct": base["history_correct_count"],
            "control_empty_correct": base["empty_correct_count"],
            "derivation_history_correct": treated["history_correct_count"],
            "derivation_empty_correct": treated["empty_correct_count"],
            "control_history_json_valid": base["history_json_valid"],
            "control_empty_json_valid": base["empty_json_valid"],
            "derivation_history_json_valid": treated["history_json_valid"],
            "derivation_empty_json_valid": treated["empty_json_valid"],
        }
    report = {
        "schema": "sentientos.ordinary_chat_transfer_distance_ladder_derivation_comparison:v1",
        "control_plan_sha256": control_score["plan_sha256"],
        "derivation_plan_sha256": derivation_score["plan_sha256"],
        "comparison_source_sha256": _sha(Path(__file__).resolve()),
        "same_model_identity": same_model,
        "same_generation_and_gpu_settings": same_generation,
        "same_questions_probe_tiers_and_order": same_task,
        "same_scored_history_evidence": same_support,
        "same_output_format_constraint": same_format,
        "tier_results": tier_results,
        "learning_established": False,
        "interpretation": (
            "This contrast estimates the effect of an equal rule-derivation procedure under history and empty controls. "
            "It does not by itself establish durable learning or attribute the original acquisition of history."),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("strict_format_control_run", type=Path)
    parser.add_argument("derivation_run", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--control-score", type=Path,
        help="v2 score report for the strict-format control (defaults to run/independent-score.json)")
    parser.add_argument("--derivation-score", type=Path,
        help="v2 score report for the rule-derivation run (defaults to run/independent-score.json)")
    args = parser.parse_args()
    report = compare(args.strict_format_control_run, args.derivation_run, args.output,
        control_score_path=args.control_score, derivation_score_path=args.derivation_score)
    print("ladder_derivation_comparison_saved", report["derivation_plan_sha256"], flush=True)
