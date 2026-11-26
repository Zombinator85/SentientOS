"""Compare history rule derivation with an explicit arithmetic calibration."""
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


def compare(derivation: Path, calibration: Path, output: Path, *,
            derivation_score_path: Path | None = None,
            calibration_score_path: Path | None = None) -> dict[str, Any]:
    derivation_plan = _read(derivation / "plan.json")
    calibration_plan = _read(calibration / "plan.json")
    derivation_score_path = derivation_score_path or (derivation / "independent-score.json")
    calibration_score_path = calibration_score_path or (calibration / "independent-score.json")
    derivation_score, calibration_score = _read(derivation_score_path), _read(calibration_score_path)
    scorer_sha = _sha(Path(__file__).with_name("score_ordinary_chat_transfer_distance_ladder.py"))
    for directory, plan, score in ((derivation, derivation_plan, derivation_score),
                                   (calibration, calibration_plan, calibration_score)):
        if score.get("plan_sha256") != _sha(directory / "plan.json"):
            raise ValueError("independent score does not bind to its frozen plan")
        evidence = score.get("prompt_evidence_validation", {})
        if (score.get("schema") != "sentientos.ordinary_chat_transfer_distance_ladder_independent_score:v2"
                or score.get("scorer_source_sha256") != scorer_sha
                or evidence.get("history_matches_model_free_preflight") is not True
                or evidence.get("empty_arm_exposed_no_history") is not True):
            raise ValueError("both runs require current v2 scores with independent evidence validation")
        result = _read(directory / "result.json")
        if result.get("plan_sha256") != score["plan_sha256"]:
            raise ValueError("run result and independent score bind to different plans")

    same_model = (derivation_plan.get("model_identity") == calibration_plan.get("model_identity")
        and derivation_plan.get("model_manifest_sha256") == calibration_plan.get("model_manifest_sha256")
        and derivation_plan.get("model") == calibration_plan.get("model"))
    same_generation = (derivation_plan.get("generation") == calibration_plan.get("generation")
        and derivation_plan.get("options") == calibration_plan.get("options")
        and derivation_plan.get("gpu_layers") == calibration_plan.get("gpu_layers"))
    same_task = (derivation_plan.get("tiers") == calibration_plan.get("tiers")
        and derivation_plan.get("trial_order") == calibration_plan.get("trial_order"))
    same_support = _support_signature(derivation_plan) == _support_signature(calibration_plan)
    same_format = (derivation_plan.get("format_treatment") == "strict_json_post_retrieval:v1"
        and calibration_plan.get("format_treatment") == "strict_json_post_retrieval:v1"
        and derivation_plan.get("output_constraint_sha256") == calibration_plan.get("output_constraint_sha256"))
    if not all((same_model, same_generation, same_task, same_support, same_format)):
        raise ValueError("comparison changed model, generation, format, task/order, or history evidence")
    if derivation_plan.get("semantic_treatment") != "derive_rule_from_available_history:v3":
        raise ValueError("first run must use the frozen history rule-derivation treatment")
    if calibration_plan.get("semantic_treatment") != "explicit_mapping_calibration:v1":
        raise ValueError("second run must use the separately frozen explicit mapping calibration")

    tiers = {}
    for tier in derivation_score["tier_summaries"]:
        derived = derivation_score["tier_summaries"][tier]
        supplied = calibration_score["tier_summaries"][tier]
        tiers[tier] = {
            "derivation_history_correct": derived["history_correct_count"],
            "derivation_empty_correct": derived["empty_correct_count"],
            "calibration_history_correct": supplied["history_correct_count"],
            "calibration_empty_correct": supplied["empty_correct_count"],
            "derivation_history_json_valid": derived["history_json_valid"],
            "derivation_empty_json_valid": derived["empty_json_valid"],
            "calibration_history_json_valid": supplied["history_json_valid"],
            "calibration_empty_json_valid": supplied["empty_json_valid"],
        }
    report = {
        "schema": "sentientos.ordinary_chat_transfer_distance_ladder_calibration_comparison:v1",
        "derivation_plan_sha256": derivation_score["plan_sha256"],
        "calibration_plan_sha256": calibration_score["plan_sha256"],
        "comparison_source_sha256": _sha(Path(__file__).resolve()),
        "same_model_identity": same_model,
        "same_generation_and_gpu_settings": same_generation,
        "same_questions_probe_tiers_and_order": same_task,
        "same_scored_history_evidence": same_support,
        "same_output_format_constraint": same_format,
        "tier_results": tiers,
        "learning_established": False,
        "interpretation": (
            "The supplied-rule arm is an arithmetic and format calibration, not a history-learning condition. "
            "Success with the supplied rule and failure under derivation would localize the observed limitation "
            "to rule induction or use of retrieved examples under this prompt; neither result establishes learning."),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("derivation_run", type=Path)
    parser.add_argument("calibration_run", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--derivation-score", type=Path)
    parser.add_argument("--calibration-score", type=Path)
    args = parser.parse_args()
    report = compare(args.derivation_run, args.calibration_run, args.output,
        derivation_score_path=args.derivation_score,
        calibration_score_path=args.calibration_score)
    print("ladder_calibration_comparison_saved", report["calibration_plan_sha256"], flush=True)
