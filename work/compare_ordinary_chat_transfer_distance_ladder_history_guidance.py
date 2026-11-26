"""Compare matched source-near runs with different history guidance."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_sha(payload: Any) -> str:
    return _sha(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())


def _evidence_signature(plan: dict[str, Any]) -> dict[str, Any]:
    return {tier: [{key: row.get(key) for key in (
        "record_id", "source_run_id", "source_score_digest", "task_family_id", "examples")}
        for row in plan["prompt_bindings"][tier + "_history"]["prompt_score_evidence"]]
        for tier in plan["tiers"]}


def _presentation(plan: dict[str, Any]) -> str:
    explicit = plan.get("example_presentation")
    if explicit is not None:
        return explicit
    has_renderings = any(
        bool(binding.get("prompt_example_renderings"))
        for key, binding in plan.get("prompt_bindings", {}).items()
        if key.endswith("_history"))
    return "record_linked" if has_renderings else "structured_only"


def compare(control: Path, treatment: Path, control_report: Path,
            treatment_report: Path, output: Path, *, scope_treatment: bool = False
            ) -> dict[str, Any]:
    control_plan = _read(control / "plan.json")
    treatment_plan = _read(treatment / "plan.json")
    control_result = _read(control / "result.json")
    treatment_result = _read(treatment / "result.json")
    control_score = _read(control / "independent-score.json")
    treatment_score = _read(treatment / "independent-score.json")
    for name, run, plan, result, score, report in (
            ("control", control, control_plan, control_result, control_score, control_report),
            ("treatment", treatment, treatment_plan, treatment_result, treatment_score,
             treatment_report)):
        plan_digest = _sha((run / "plan.json").read_bytes())
        if (plan.get("source_report_sha256") != _sha(report.read_bytes())
                or score.get("plan_sha256") != plan_digest
                or score.get("preflight_sha256") != _sha(report.read_bytes())
                or result.get("plan_sha256") != plan_digest
                or score.get("learning_established") is not False):
            raise ValueError(f"{name} result, score, plan, or preflight binding differs")

    same_identity = (control_plan.get("model") == treatment_plan.get("model")
        and control_plan.get("model_manifest_sha256") == treatment_plan.get("model_manifest_sha256")
        and control_plan.get("model_identity") == treatment_plan.get("model_identity"))
    same_generation = (control_plan.get("generation") == treatment_plan.get("generation")
        and control_plan.get("options") == treatment_plan.get("options")
        and control_plan.get("gpu_layers") == treatment_plan.get("gpu_layers"))
    same_seed = control_plan.get("options", {}).get("seed") == treatment_plan.get(
        "options", {}).get("seed")
    same_task = (control_plan.get("task_family_id") == treatment_plan.get("task_family_id")
        and control_plan.get("tiers") == treatment_plan.get("tiers")
        and control_plan.get("trial_order") == treatment_plan.get("trial_order"))
    same_support = _evidence_signature(control_plan) == _evidence_signature(treatment_plan)
    same_empty_prompts = all(
        control_plan["prompt_bindings"][tier + "_empty"].get("prompt_sha256")
        == treatment_plan["prompt_bindings"][tier + "_empty"].get("prompt_sha256")
        for tier in control_plan["tiers"])
    same_nonhistory_prompt = (control_plan.get("matched_base_sha256")
        == treatment_plan.get("matched_base_sha256"))
    same_format = (control_plan.get("format_treatment") == treatment_plan.get("format_treatment")
        and control_plan.get("output_constraint") == treatment_plan.get("output_constraint"))
    control_presentation = _presentation(control_plan)
    treatment_presentation = _presentation(treatment_plan)
    different_presentation = (control_presentation != treatment_presentation)
    scope_treatment_matches = (
        control_plan.get("semantic_treatment") is None
        and treatment_plan.get("semantic_treatment")
            == "clarify_developmental_history_scope:v1"
        and control_presentation == treatment_presentation) if scope_treatment else False
    if not all((same_identity, same_generation, same_seed, same_task, same_support,
                same_empty_prompts, same_nonhistory_prompt, same_format,
                (scope_treatment_matches if scope_treatment else different_presentation))):
        raise ValueError("runs differ in model, settings, task, support, empty prompt, base prompt, or format")

    settings_without_seed = {
        "generation": control_plan.get("generation"),
        "options": {key: value for key, value in control_plan.get("options", {}).items()
                    if key != "seed"},
        "gpu_layers": control_plan.get("gpu_layers"),
        "format_treatment": control_plan.get("format_treatment"),
        "output_constraint": control_plan.get("output_constraint"),
    }
    task_payload = {"task_family_id": control_plan.get("task_family_id"),
        "tiers": control_plan.get("tiers"), "trial_order": control_plan.get("trial_order")}
    support_payload = _evidence_signature(control_plan)
    model_identity = control_plan.get("model_identity", {})

    control_blocks = {tier: control_plan["prompt_bindings"][tier + "_history"][
        "history_block_digest"] for tier in control_plan["tiers"]}
    treatment_blocks = {tier: treatment_plan["prompt_bindings"][tier + "_history"][
        "history_block_digest"] for tier in treatment_plan["tiers"]}
    if (not all(control_blocks.values()) or not all(treatment_blocks.values())
            or control_blocks == treatment_blocks):
        raise ValueError("history prompt block did not change between control and treatment")

    control_rows = {(row["tier"], row["arm"]): row for row in control_score["trials"]}
    treatment_rows = {(row["tier"], row["arm"]): row for row in treatment_score["trials"]}
    if set(control_rows) != set(treatment_rows) or len(control_rows) != 6:
        raise ValueError("runs do not contain the same six tier/arm outcomes")
    by_tier = {}
    for tier in control_plan["tiers"]:
        by_tier[tier] = {}
        for arm in ("history", "empty"):
            before, after = control_rows[(tier, arm)], treatment_rows[(tier, arm)]
            by_tier[tier][arm] = {
                "control_answers": before["answers"],
                "treatment_answers": after["answers"],
                "control_correct": before["correct_count"],
                "treatment_correct": after["correct_count"],
                "denominator": before["denominator"],
                "control_json_valid": before["strict_json_valid"],
                "treatment_json_valid": after["strict_json_valid"],
            }
    answer_payloads_unchanged = all(
        outcomes[arm]["control_answers"] == outcomes[arm]["treatment_answers"]
        for outcomes in by_tier.values() for arm in ("history", "empty"))
    format_validity_unchanged = all(
        outcomes[arm]["control_json_valid"] == outcomes[arm]["treatment_json_valid"]
        for outcomes in by_tier.values() for arm in ("history", "empty"))
    exact_accuracy_unchanged = all(
        outcomes[arm]["control_correct"] == outcomes[arm]["treatment_correct"]
        for outcomes in by_tier.values() for arm in ("history", "empty"))
    response_effect = ("did not change answer payloads" if answer_payloads_unchanged
        else "changed answer payloads")
    format_effect = ("did not change strict-format validity" if format_validity_unchanged
        else "changed strict-format validity")
    accuracy_effect = ("did not change exact accuracy" if exact_accuracy_unchanged
        else "changed exact accuracy")
    history_control_correct = sum(row["correct_count"] for row in control_score["trials"]
                                  if row["arm"] == "history")
    history_treatment_correct = sum(row["correct_count"] for row in treatment_score["trials"]
                                    if row["arm"] == "history")
    empty_control_correct = sum(row["correct_count"] for row in control_score["trials"]
                                if row["arm"] == "empty")
    empty_treatment_correct = sum(row["correct_count"] for row in treatment_score["trials"]
                                  if row["arm"] == "empty")
    intervention_name = ("the developmental-history scope clarification"
                         if scope_treatment else "the history presentation")
    report = {
        "schema": "sentientos.ordinary_chat_transfer_distance_ladder_history_guidance_comparison:v1",
        "control_plan_sha256": control_score["plan_sha256"],
        "treatment_plan_sha256": treatment_score["plan_sha256"],
        "control_preflight_sha256": control_score["preflight_sha256"],
        "treatment_preflight_sha256": treatment_score["preflight_sha256"],
        "comparison_source_sha256": _sha(Path(__file__).read_bytes()),
        "seed": control_plan.get("options", {}).get("seed"),
        "model": control_plan.get("model"),
        "model_manifest_sha256": control_plan.get("model_manifest_sha256"),
        "model_content_sha256": model_identity.get("model_content_sha256"),
        "non_seed_generation_settings_sha256": _canonical_sha(settings_without_seed),
        "task_probes_and_order_sha256": _canonical_sha(task_payload),
        "scored_support_sha256": _canonical_sha(support_payload),
        "same_model_identity": same_identity,
        "same_generation_and_gpu_settings": same_generation,
        "same_seed": same_seed,
        "same_task_probes_and_trial_order": same_task,
        "same_scored_history_evidence": same_support,
        "same_empty_prompts": same_empty_prompts,
        "same_prompt_outside_history_block": same_nonhistory_prompt,
        "same_format_constraint": same_format,
        "history_example_presentation": {"control": control_presentation,
            "treatment": treatment_presentation},
        "history_example_presentation_changed": different_presentation,
        "history_scope_clarification_treatment": scope_treatment,
        "history_scope_clarification_changed": scope_treatment_matches,
        "history_prompt_block_changed": True,
        "answer_payloads_unchanged": answer_payloads_unchanged,
        "strict_json_validity_unchanged": format_validity_unchanged,
        "exact_accuracy_unchanged": exact_accuracy_unchanged,
        "history_block_digests": {"control": control_blocks, "treatment": treatment_blocks},
        "strict_json_valid_trials": {
            "control": [sum(row["strict_json_valid"] for row in control_score["trials"]), 6],
            "treatment": [sum(row["strict_json_valid"] for row in treatment_score["trials"]), 6]},
        "exact_answers": {
            arm: {"control": [sum(row["correct_count"] for row in control_score["trials"]
                                    if row["arm"] == arm), 9],
                  "treatment": [sum(row["correct_count"] for row in treatment_score["trials"]
                                      if row["arm"] == arm), 9]}
            for arm in ("history", "empty")},
        "tier_results": by_tier,
        "interpretation": (
            f"In this matched pair (seed {control_plan.get('options', {}).get('seed')}), "
            f"{intervention_name} {response_effect}, {format_effect}, and "
            f"{accuracy_effect}. History exact answers were {history_control_correct}/9 "
            f"in control and {history_treatment_correct}/9 in treatment; empty-arm totals were "
            f"{empty_control_correct}/9 "
            f"and {empty_treatment_correct}/9. The model, generation settings, seed, probes, "
            "scored support, empty prompts, non-history prompt, and output constraint matched. "
            "This pair does not establish durable learning or general transfer."),
        "learning_established": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("control_run", type=Path)
    parser.add_argument("treatment_run", type=Path)
    parser.add_argument("control_preflight", type=Path)
    parser.add_argument("treatment_preflight", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--scope-treatment", action="store_true",
        help="Compare a bound developmental-history scope clarification against the unchanged history guidance")
    args = parser.parse_args()
    result = compare(args.control_run, args.treatment_run, args.control_preflight,
                     args.treatment_preflight, args.output,
                     scope_treatment=args.scope_treatment)
    print("history_guidance_comparison_saved", result["treatment_plan_sha256"], flush=True)
