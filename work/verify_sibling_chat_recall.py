"""Reopen the saved CPU recall trial without inference and grade the delivered answers again."""
from __future__ import annotations

import argparse
from pathlib import Path

from sentientos.governed_local_model_invocation import validate_receipt
from sentientos.local_model import candidate_configuration_digest_from_payload
from sentientos.local_model_authority import digest_payload
from work.run_sibling_chat_recall import (
    EXPLICIT_ROW_MAPPING, INLINE_REPORT, INLINE_ROWS, MANIFEST, MODEL, SOURCE_REPORT, conditions, read, recall_question,
    score_answer, score_cited_answer, score_cited_answer_v2_legacy, sha,
)


def verify(path):
    plan_file = path / "plan.json"
    plan, result, archive = read(plan_file), read(path / "result.json"), read(SOURCE_REPORT)
    if plan["schema"] not in {"sentientos.sibling_chat_recall_plan:v1", "sentientos.sibling_chat_recall_plan:v2",
                              "sentientos.sibling_chat_recall_plan:v3", "sentientos.sibling_chat_recall_plan:v4"}:
        raise ValueError("unknown recall protocol")
    cited = plan["schema"].endswith((":v2", ":v3"))
    cited = cited or plan["schema"].endswith(":v4")
    legacy_cited_scoring = plan["schema"].endswith(":v2")
    explicit_row_mapping = plan["schema"].endswith(":v4")
    expected_intervention = ({"id": "explicit_developmental_history_field_to_row_mapping:v1",
        "guidance": EXPLICIT_ROW_MAPPING, "guidance_sha256": sha(EXPLICIT_ROW_MAPPING.encode())}
        if explicit_row_mapping else None)
    trials = conditions(cited)
    plan_hash = sha(plan_file.read_bytes())
    configuration_digest = candidate_configuration_digest_from_payload({
        "engine": "ollama", "options": plan["options"], "max_context_tokens": plan["context_tokens"],
        "generation": plan["generation"]})
    if (result["plan_sha256"] != plan_hash or plan["source_report_sha256"] != sha(SOURCE_REPORT.read_bytes())
            or plan["trials"] != [list(t) for t in trials] or len(result["trials"]) != len(trials)
            or plan["model"] != MODEL or plan["model_identity"]["model_content_sha256"] != MANIFEST
            or configuration_digest != plan["model_identity"]["configuration_digest"]
            or plan["options"]["num_gpu"] != 0 or plan["options"]["num_thread"] != 2
            or plan["questions"] != {s: ((INLINE_REPORT + "\n") if s == "inline" else "")
                                     + recall_question(s, cited) for _, s in trials}
            or plan.get("intervention") != expected_intervention):
        raise ValueError("protocol or trial set differs from the bound experiment")
    profiles = {"empty": []}
    for arm, scope in dict.fromkeys(trials):
        exposure = plan["exposures"][arm + "_" + scope]
        if arm == "empty":
            if exposure["history_block_digest"] is not None or exposure["prompt_score_evidence"]:
                raise ValueError("empty control contains history")
            if exposure["prompt_sha256"] != plan["matched_base_sha256"][scope]:
                raise ValueError("empty control differs outside the history block")
            if scope == "inline":
                profiles["inline"] = INLINE_ROWS
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
    for index, ((arm, scope), trial) in enumerate(zip(trials, result["trials"], strict=True)):
        key = arm + "_" + scope
        exposure = plan["exposures"][key]
        if explicit_row_mapping:
            instruction = exposure.get("history_instruction")
            if ((exposure["history_block_digest"] is None and instruction is not None)
                    or (exposure["history_block_digest"] is not None
                        and (not isinstance(instruction, str)
                            or EXPLICIT_ROW_MAPPING.strip() not in instruction))):
                raise ValueError("history mapping intervention differs from the captured prompt")
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
        scorer = (score_cited_answer_v2_legacy if legacy_cited_scoring else score_cited_answer) if cited else score_answer
        grade = scorer(trial["delivered"], profiles)
        expected = ("inline" if scope == "inline" else "empty" if arm == "empty"
                    else "shared_low" if scope == "low" else key)
        exact = expected in grade["exact_profiles"]
        if cited:
            records = exposure["prompt_score_evidence"]
            expected_citation = "inline-example" if scope == "inline" else records[0]["record_id"] if records else None
            exact = exact and grade["cited_record"] == expected_citation
        if (trial["expected_profile"] != expected or grade != trial["score"] or trial["exact"] is not exact):
            raise ValueError("saved score differs from blind regrade")
        scores.append((key, grade["format"], exact))
    return scores


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_directory", type=Path)
    for row in verify(parser.parse_args().evidence_directory):
        print(*row)
