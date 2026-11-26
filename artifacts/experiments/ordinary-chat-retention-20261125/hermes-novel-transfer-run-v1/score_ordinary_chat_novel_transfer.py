"""Independently score frozen ordinary-chat novel-transfer outputs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from sentientos.developmental_model_replacement_experiment import (
    FIXED_OBJECTIVE_TASK_FAMILY_MAPPINGS,
    ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY,
)
from sentientos.governed_local_model_invocation import validate_receipt
from sentientos.local_model_authority import digest_payload
from work.preflight_sibling_chat_histories import NOVEL_TRANSFER_PROBES, ROOT, read
from work.run_ordinary_chat_novel_transfer import ANSWER_KEY_COMMITMENT, ARMS, sha


def score(run_root: Path, output: Path) -> dict:
    plan = read(run_root / "plan.json")
    results = read(run_root / "result.json")
    mapping = FIXED_OBJECTIVE_TASK_FAMILY_MAPPINGS[ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY]
    key = [mapping[0] * probe + mapping[1] for probe in NOVEL_TRANSFER_PROBES]
    commitment = "sha256:" + digest_payload({
        "task_family_id": ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY,
        "probe_inputs": list(NOVEL_TRANSFER_PROBES), "expected_outputs": key,
    })
    if (plan.get("schema") != "sentientos.ordinary_chat_novel_range_transfer_execution_plan:v1"
            or plan.get("answer_key_commitment") != commitment
            or commitment != ANSWER_KEY_COMMITMENT
            or results.get("plan_sha256") != sha((run_root / "plan.json").read_bytes())
            or [trial.get("arm") for trial in results.get("trials", [])] != list(ARMS)):
        raise ValueError("execution plan, answer key commitment, or result order is invalid")
    scored = []
    for trial in results["trials"]:
        receipt = trial["receipt"]
        raw = trial.get("delivered")
        if (not validate_receipt(receipt)[0]
                or receipt.get("request", {}).get("active_model_identity") != plan.get("model_identity")
                or receipt.get("output_digest") != digest_payload({"output": raw})
                or trial.get("model_output") != raw
                or trial.get("prompt_sha256") != plan["prompt_bindings"][trial["arm"]]["prompt_sha256"]):
            raise ValueError("trial output is not bound to a valid governed receipt and frozen prompt")
        try:
            value = json.loads(raw)
            answers = value["answers"] if isinstance(value, dict) and set(value) == {"answers"} else None
        except (TypeError, ValueError):
            answers = None
        valid = (isinstance(answers, list) and len(answers) == len(key)
                 and all(answer is None or type(answer) is int for answer in answers))
        correct = ([answer == expected for answer, expected in zip(answers, key, strict=True)]
                   if valid else [False] * len(key))
        scored.append({"arm": trial["arm"], "format_valid": valid,
            "answers": answers if valid else None, "probe_correct": correct,
            "correct_count": sum(correct), "denominator": len(key),
            "receipt_id": receipt.get("receipt_id"),
            "raw_output_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest() if isinstance(raw, str) else None})
    report = {"schema": "sentientos.ordinary_chat_novel_range_transfer_independent_score:v1",
        "plan_sha256": results["plan_sha256"], "answer_key_commitment": commitment,
        "scorer_source_sha256": sha(Path(__file__).read_bytes()),
        "arms": scored, "interpretation": "Behavioral scores only; this does not establish durable learning or causal attribution."}
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
    report = score(args.run_directory, args.output)
    print("independent_score_saved", report["plan_sha256"], flush=True)
