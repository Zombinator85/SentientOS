"""Audit history support and output-format effects in a frozen transfer run."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from sentientos.developmental_model_replacement_experiment import (
    FIXED_OBJECTIVE_TASK_FAMILY_MAPPINGS,
    ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY,
)
from sentientos.local_model_authority import digest_payload
from work.preflight_sibling_chat_histories import NOVEL_TRANSFER_PROBES, read
from work.run_ordinary_chat_novel_transfer import ARMS, sha


def _strict_answers(raw: str, count: int) -> tuple[bool, list[int | None] | None]:
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return False, None
    if (not isinstance(value, dict) or set(value) != {"answers"}
            or not isinstance(value["answers"], list) or len(value["answers"]) != count
            or any(answer is not None and type(answer) is not int for answer in value["answers"])):
        return False, None
    return True, value["answers"]


def _recover_payload(raw: str, count: int) -> list[int | None] | None:
    """Find one unambiguous JSON answers object, allowing wrapper prose/fences."""
    decoder = json.JSONDecoder()
    found: list[list[int | None]] = []
    for offset, char in enumerate(raw):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(raw[offset:])
        except ValueError:
            continue
        if (isinstance(value, dict) and set(value) == {"answers"}
                and isinstance(value["answers"], list) and len(value["answers"]) == count
                and all(answer is None or type(answer) is int for answer in value["answers"])):
            found.append(value["answers"])
    return found[0] if len(found) == 1 else None


def analyze(run_directory: Path, output: Path) -> dict[str, Any]:
    plan_path, result_path = run_directory / "plan.json", run_directory / "result.json"
    plan, result = read(plan_path), read(result_path)
    key_report = read(run_directory / "independent-score.json")
    plan_digest = sha(plan_path.read_bytes())
    mapping = FIXED_OBJECTIVE_TASK_FAMILY_MAPPINGS[ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY]
    calculated_commitment = "sha256:" + digest_payload({
        "task_family_id": ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY,
        "probe_inputs": list(NOVEL_TRANSFER_PROBES),
        "expected_outputs": [mapping[0] * probe + mapping[1] for probe in NOVEL_TRANSFER_PROBES],
    })
    if (plan.get("answer_key_commitment") != key_report.get("answer_key_commitment")
            or plan.get("answer_key_commitment") != calculated_commitment
            or plan_digest != result.get("plan_sha256")
            or plan_digest != key_report.get("plan_sha256")
            or [trial.get("arm") for trial in result.get("trials", ())] != list(ARMS)):
        raise ValueError("plan, run result, and independent score do not identify one frozen run")

    history_support: dict[str, dict[str, Any]] = {}
    outputs: dict[str, dict[str, Any]] = {}
    expected_by_arm = {entry["arm"]: entry for entry in key_report["arms"]}
    for arm in ARMS:
        exposure = plan["prompt_bindings"][arm]
        source_examples = []
        for evidence in exposure["prompt_score_evidence"]:
            for row in evidence.get("examples", ()):
                input_value, observed = row.get("probe_input"), row.get("observed_answer")
                target_value = mapping[0] * input_value + mapping[1] if type(input_value) is int else None
                abstained = row.get("abstained") is True
                source_examples.append({
                    "task_family_id": evidence.get("task_family_id"),
                    "probe_input": input_value,
                    "observed_answer": observed,
                    "source_evaluator_correct": row.get("evaluator_correct"),
                    "abstained": abstained,
                    "agrees_with_novel_family_mapping": (
                        type(observed) is int and target_value is not None and observed == target_value),
                })
        answered = [row for row in source_examples if not row["abstained"]]
        aligned = sum(row["agrees_with_novel_family_mapping"] for row in answered)
        if not source_examples:
            support_class = "no_scored_history_examples"
        elif not answered:
            support_class = "abstention_only_history"
        elif aligned == len(answered) and len(answered) == len(source_examples):
            support_class = "all_observed_examples_agree_with_fixed_mapping"
        elif aligned:
            support_class = "mixed_history_support"
        else:
            support_class = "no_observed_example_agrees_with_fixed_mapping"
        history_support[arm] = {
            "history_record_ids": [item["record_id"] for item in exposure["prompt_score_evidence"]],
            "history_block_digest": exposure["history_block_digest"],
            "examples": source_examples,
            "answered_example_count": len(answered),
            "mapping_aligned_answer_count": aligned,
            "support_class": support_class,
        }

        trial = next(item for item in result["trials"] if item["arm"] == arm)
        raw = trial.get("delivered")
        strict_valid, strict_values = _strict_answers(raw, len(NOVEL_TRANSFER_PROBES)) if isinstance(raw, str) else (False, None)
        recovered = _recover_payload(raw, len(NOVEL_TRANSFER_PROBES)) if isinstance(raw, str) else None
        score = expected_by_arm[arm]
        if score["format_valid"] != strict_valid:
            raise ValueError(f"strict format analysis differs from independent scorer for {arm}")
        outputs[arm] = {
            "strict_json_only_valid": strict_valid,
            "strict_answers": strict_values,
            "unambiguous_json_payload_recovered": recovered is not None,
            "recovered_answers": recovered,
            "recovered_correct_count": sum(value is not None and value == target
                for value, target in zip(recovered, [mapping[0] * probe + mapping[1]
                    for probe in NOVEL_TRANSFER_PROBES], strict=True)) if recovered is not None else 0,
            "strict_score_correct_count": score["correct_count"],
            "denominator": score["denominator"],
        }

    parent_left = history_support["parent"]["examples"] == history_support["left"]["examples"]
    report = {
        "schema": "sentientos.ordinary_chat_novel_transfer_evidence_diagnostic:v1",
        "plan_sha256": plan_digest,
        "independent_score_sha256": sha((run_directory / "independent-score.json").read_bytes()),
        "analyzer_source_sha256": sha(Path(__file__).read_bytes()),
        "task_family_id": ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY,
        "history_support_by_arm": history_support,
        "outputs_by_arm": outputs,
        "parent_and_left_exposed_identical_scored_examples": parent_left,
        "interpretation": (
            "Diagnostic decomposition only. Mapping agreement is calculated from frozen source rows; "
            "recovering JSON from prose does not change the strict score or establish learning."),
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
    args = parser.parse_args()
    report = analyze(args.run_directory, args.output)
    print("evidence_diagnostic_saved", report["plan_sha256"], flush=True)
