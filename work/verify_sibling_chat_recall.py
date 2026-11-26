"""Reopen the saved CPU recall trial without inference and grade the delivered answers again."""
from __future__ import annotations

import argparse
from pathlib import Path

from sentientos.governed_local_model_invocation import validate_receipt
from sentientos.local_model import candidate_configuration_digest_from_payload
from sentientos.local_model_authority import digest_payload
from work.run_sibling_chat_recall import (
    FORMAT, MANIFEST, MODEL, QUESTIONS, SOURCE_REPORT, TRIALS, read, score_answer, sha,
)


def verify(path):
    plan_file = path / "plan.json"
    plan, result, archive = read(plan_file), read(path / "result.json"), read(SOURCE_REPORT)
    plan_hash = sha(plan_file.read_bytes())
    configuration_digest = candidate_configuration_digest_from_payload({
        "engine": "ollama", "options": plan["options"], "max_context_tokens": plan["context_tokens"],
        "generation": plan["generation"]})
    if (result["plan_sha256"] != plan_hash or plan["source_report_sha256"] != sha(SOURCE_REPORT.read_bytes())
            or plan["trials"] != [list(t) for t in TRIALS] or len(result["trials"]) != len(TRIALS)
            or plan["model"] != MODEL or plan["model_identity"]["model_content_sha256"] != MANIFEST
            or configuration_digest != plan["model_identity"]["configuration_digest"]
            or plan["options"]["num_gpu"] != 0 or plan["options"]["num_thread"] != 2
            or plan["questions"] != {s: QUESTIONS["latest_" + s] + FORMAT for _, s in TRIALS}):
        raise ValueError("protocol or trial set differs from the bound experiment")
    profiles = {"empty": []}
    for arm, scope in dict.fromkeys(TRIALS):
        exposure = plan["exposures"][arm + "_" + scope]
        if arm == "empty":
            if exposure["history_block_digest"] is not None or exposure["prompt_score_evidence"]:
                raise ValueError("empty control contains history")
            if exposure["prompt_sha256"] != plan["matched_base_sha256"][scope]:
                raise ValueError("empty control differs outside the history block")
            continue
        oracle, = archive["questions"]["latest_" + scope]["captures"][arm]["prompt_score_evidence"]
        evidence, = exposure["prompt_score_evidence"]
        if any(evidence[k] != oracle[k] for k in ("record_id", "source_run_id", "source_score_digest",
                                                   "examples", "source_fact_id", "task_family_id")):
            raise ValueError("exposure differs from archived evidence")
        if arm in ("left", "right") and scope == "wide":
            added = archive["arms"][arm]["addition"]
            if any(oracle[k] != added[k] for k in ("record_id", "source_score_digest", "examples")):
                raise ValueError("wide-range oracle differs from acquisition")
        key = "shared_low" if scope == "low" else arm + "_wide"
        rows = [[e["probe_input"], e["observed_answer"], "abstained" if e["abstained"]
                 else "correct" if e["evaluator_correct"] else "incorrect"] for e in oracle["examples"]]
        if profiles.setdefault(key, rows) != rows:
            raise ValueError("sibling control oracles disagree")
    if profiles != plan["profiles"]:
        raise ValueError("scoring profiles differ from archived scores")
    references, scores = set(), []
    for index, ((arm, scope), trial) in enumerate(zip(TRIALS, result["trials"], strict=True)):
        key = arm + "_" + scope
        exposure = plan["exposures"][key]
        disk = trial["receipt"]
        req = disk["request"]
        if (trial["trial"] != index or trial["condition"] != key or trial["plan_sha256"] != plan_hash
                or trial["prompt_sha256"] != exposure["prompt_sha256"] or trial["resident_vram_bytes"] != 0
                or not validate_receipt(disk)[0] or disk["receipt_id"] in references
                or not disk["admission_decision_ref"] or disk["status"] != "admitted_completed" or disk["fallback_occurred"]
                or req["budget"]["timeout_seconds"] != plan["options"]["timeout_seconds"]
                or req["prompt_digest"] != exposure["invocation_prompt_digest"]
                or req["linkage"].get("ordinary_developmental_history_prompt_block_digest") != exposure["history_block_digest"]
                or req["purpose"] != "local_user_chat" or req["active_model_identity"] != plan["model_identity"]
                or digest_payload({"output": trial["model_output"]}) != disk["output_digest"]):
            raise ValueError("trial receipt, output or placement differs from its protocol")
        references.add(disk["receipt_id"])
        if trial["delivered"] != trial["model_output"].strip():
            raise ValueError("delivered text differs from the receipted model response")
        grade = score_answer(trial["delivered"], profiles)
        expected = "empty" if arm == "empty" else "shared_low" if scope == "low" else key
        exact = expected in grade["exact_profiles"]
        if (trial["expected_profile"] != expected or grade != trial["score"] or trial["exact"] is not exact):
            raise ValueError("saved score differs from blind regrade")
        scores.append((key, grade["format"], exact))
    return scores


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_directory", type=Path)
    for row in verify(parser.parse_args().evidence_directory):
        print(*row)
