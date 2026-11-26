"""Separate strict-format failures from recoverable ladder answer payloads."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sentientos.developmental_model_replacement_experiment import (
    FIXED_OBJECTIVE_TASK_FAMILY_MAPPINGS,
    ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY,
)
from sentientos.local_model_authority import digest_payload
from work.preflight_sibling_chat_histories import read
from work.run_ordinary_chat_transfer_distance_ladder import REPORT, TRIAL_ORDER, sha


def _recover(raw: Any, expected_count: int) -> list[int | None] | None:
    if not isinstance(raw, str):
        return None
    decoder = json.JSONDecoder()
    candidates = []
    for offset, char in enumerate(raw):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(raw[offset:])
        except ValueError:
            continue
        if (isinstance(value, dict) and set(value) == {"answers"}
                and isinstance(value["answers"], list)
                and len(value["answers"]) == expected_count
                and all(item is None or type(item) is int for item in value["answers"])):
            candidates.append(value["answers"])
    return candidates[0] if len(candidates) == 1 else None


def analyze(run_directory: Path, output: Path) -> dict[str, Any]:
    plan_path = run_directory / "plan.json"
    plan, result = read(plan_path), read(run_directory / "result.json")
    score_path = run_directory / "independent-score.json"
    scores = read(score_path)
    plan_hash = sha(plan_path.read_bytes())
    if (plan_hash != result.get("plan_sha256") or plan_hash != scores.get("plan_sha256")
            or scores.get("preflight_sha256") != sha(REPORT.read_bytes())
            or [(r.get("tier"), r.get("arm")) for r in result.get("trials", ())] != list(TRIAL_ORDER)):
        raise ValueError("run, plan, independent score, or preflight do not match")
    mapping = FIXED_OBJECTIVE_TASK_FAMILY_MAPPINGS[ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY]
    tier_reports = {}
    score_index = {(row["tier"], row["arm"]): row for row in scores["trials"]}
    payload_index = {}
    for trial in result["trials"]:
        tier, arm = trial["tier"], trial["arm"]
        probes = plan["tiers"][tier]["probe_inputs"]
        recovered = _recover(trial.get("delivered"), len(probes))
        expected = [mapping[0] * value + mapping[1] for value in probes]
        correct = [value == target for value, target in zip(recovered, expected, strict=True)] \
            if recovered is not None else [False] * len(probes)
        official = score_index[(tier, arm)]
        if official["strict_json_valid"] and official["answers"] != recovered:
            raise ValueError(f"strict answers differ from recovered payload for {tier}/{arm}")
        payload_index[(tier, arm)] = {"recoverable": recovered is not None,
            "recovered_answers": recovered, "payload_correct_count": sum(correct),
            "denominator": len(probes), "strict_json_valid": official["strict_json_valid"],
            "official_correct_count": official["correct_count"],
            "receipt_id": official["receipt_id"]}
    for tier in plan["tiers"]:
        history_examples = [example for evidence in plan["prompt_bindings"][tier + "_history"][
            "prompt_score_evidence"] for example in evidence.get("examples", ())]
        support_aligned = sum(
            type(row.get("probe_input")) is int
            and row.get("observed_answer") == mapping[0] * row["probe_input"] + mapping[1]
            and row.get("evaluator_correct") is True
            and row.get("abstained") is False for row in history_examples)
        history = payload_index[(tier, "history")]
        empty = payload_index[(tier, "empty")]
        tier_reports[tier] = {
            "support_examples": len(history_examples),
            "support_examples_aligned_with_fixed_mapping": support_aligned,
            "history_payload": history,
            "empty_payload": empty,
            "payload_correct_count_difference": history["payload_correct_count"] - empty["payload_correct_count"],
        }
    report = {
        "schema": "sentientos.ordinary_chat_transfer_distance_ladder_payload_diagnostic:v1",
        "plan_sha256": plan_hash,
        "independent_score_sha256": sha(score_path.read_bytes()),
        "analyzer_source_sha256": sha(Path(__file__).read_bytes()),
        "tiers": tier_reports,
        "interpretation": (
            "Payload extraction is descriptive and does not alter strict scores. All outputs remain "
            "behavioral evidence only; this one-run ladder does not establish durable learning."),
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
    print("ladder_payload_diagnostic_saved", report["plan_sha256"], flush=True)
