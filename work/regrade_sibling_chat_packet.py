"""Protocol-correct regrade and extractive ceiling for the cited CPU recall run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from work.run_sibling_chat_recall import score_cited_answer, sha
from work.verify_sibling_chat_recall import verify


SOURCE = Path(__file__).resolve().parents[1] / (
    "artifacts/experiments/ordinary-chat-retention-20261125/cpu-sibling-recall-cited-v2")


def protocol_text(text):
    """Remove only the single JSON fence explicitly allowed by protocol v2."""
    stripped = text.strip()
    if stripped.startswith("```json\n") and stripped.endswith("\n```"):
        return stripped[len("```json\n"):-len("\n```")].strip()
    return text


def packet_copy(exposure):
    """Copy the exact verified source projection into the requested answer shape."""
    evidence = exposure["prompt_score_evidence"]
    if not evidence:
        return {"record_id": None, "rows": []}
    if len(evidence) != 1:
        raise ValueError("packet copy requires exactly one selected record")
    record = evidence[0]
    rows = []
    seen = set()
    for example in record["examples"]:
        probe_input = example["probe_input"]
        answer = example["observed_answer"]
        correct = example["evaluator_correct"]
        abstained = example["abstained"]
        if (type(probe_input) is not int or probe_input in seen
                or (answer is not None and type(answer) is not int)
                or type(abstained) is not bool
                or (correct is not None and type(correct) is not bool)
                or (abstained and (answer is not None or correct is not None))
                or (not abstained and (answer is None or correct is None))):
            raise ValueError("selected history projection has malformed score evidence")
        seen.add(probe_input)
        outcome = "abstained" if abstained else "correct" if correct else "incorrect"
        rows.append([probe_input, answer, outcome])
    return {"record_id": record["record_id"], "rows": rows}


def regrade(source=SOURCE):
    """Authenticate the original run, then score the protocol's permitted fenced output."""
    original_grades = verify(source)
    plan_file, result_file = source / "plan.json", source / "result.json"
    plan = json.loads(plan_file.read_text(encoding="utf-8"))
    result = json.loads(result_file.read_text(encoding="utf-8"))
    if plan["schema"] != "sentientos.sibling_chat_recall_plan:v2":
        raise ValueError("regrade requires the cited v2 protocol")

    trials = []
    exact_model = 0
    packet_copy_exact = 0
    packet_copy_trials = 0
    for saved, original_grade in zip(result["trials"], original_grades, strict=True):
        arm, scope = saved["condition"].rsplit("_", 1)
        key = saved["condition"]
        exposure = plan["exposures"][key]
        expected = saved["expected_profile"]
        citation = ("inline-example" if scope == "inline" else
                    exposure["prompt_score_evidence"][0]["record_id"]
                    if exposure["prompt_score_evidence"] else None)
        model_grade = score_cited_answer(protocol_text(saved["delivered"]), plan["profiles"])
        model_exact = expected in model_grade["exact_profiles"] and model_grade["cited_record"] == citation
        exact_model += int(model_exact)

        if scope == "inline":
            control = {"applicable": False, "reason": "visible inline report, not developmental history"}
        else:
            answer = packet_copy(exposure)
            control_grade = score_cited_answer(json.dumps(answer), plan["profiles"])
            control_exact = (expected in control_grade["exact_profiles"]
                             and control_grade["cited_record"] == citation)
            packet_copy_trials += 1
            packet_copy_exact += int(control_exact)
            if not control_exact:
                raise ValueError(f"verified packet copy did not meet oracle profile for {key}")
            control = {"applicable": True, "answer": answer, "score": control_grade,
                       "exact": control_exact}
        trials.append({
            "condition": key,
            "prompt_sha256": saved["prompt_sha256"],
            "receipt_id": saved["receipt"]["receipt_id"],
            "expected_profile": expected,
            "protocol_compliant_model_score": model_grade,
            "model_exact": model_exact,
            "previous_saved_format": original_grade[1],
            "packet_copy_control": control,
        })

    return {
        "schema": "sentientos.sibling_chat_packet_regrade:v1",
        "source_plan_sha256": sha(plan_file.read_bytes()),
        "source_result_sha256": sha(result_file.read_bytes()),
        "original_verifier_passed": True,
        "model_invoked": False,
        "scoring_change": "accept exactly one ```json fenced object as permitted by cited v2; rows and citation still independently checked",
        "interpretation_limit": "packet-copy controls show that the verified prompt projection contains sufficient score fields for exact transcription; they are deterministic readouts, not model behavior or evidence of learning",
        "summary": {
            "trials": len(trials),
            "model_exact_after_protocol_correct_regrade": exact_model,
            "packet_copy_applicable_trials": packet_copy_trials,
            "packet_copy_exact": packet_copy_exact,
        },
        "trials_detail": trials,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = regrade(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(report["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
