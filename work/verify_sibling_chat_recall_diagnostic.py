"""Verify one governed empty-history generation diagnostic."""
from __future__ import annotations

import argparse
from pathlib import Path

from sentientos.governed_local_model_invocation import validate_receipt
from sentientos.local_model import candidate_configuration_digest_from_payload
from sentientos.local_model_authority import digest_payload
from work.run_sibling_chat_recall import (
    INLINE_REPORT, MODEL_MANIFESTS, SOURCE_REPORT, read, recall_question,
    score_cited_answer, sha,
)


def verify(path: Path):
    plan_path, result_path = path / "plan.json", path / "result.json"
    plan, result = read(plan_path), read(result_path)
    condition = plan.get("diagnostic_condition")
    if condition not in {"empty_wide", "empty_inline"}:
        raise ValueError("unsupported diagnostic condition")
    arm, scope = condition.split("_", 1)
    plan_hash = sha(plan_path.read_bytes())
    config_digest = candidate_configuration_digest_from_payload({
        "engine": "ollama", "options": plan["options"], "max_context_tokens": plan["context_tokens"],
        "generation": plan["generation"],
    })
    expected_question = ((INLINE_REPORT + "\n") if scope == "inline" else "") + recall_question(scope, True)
    exposure = plan["exposures"][condition]
    if (plan["schema"] != "sentientos.sibling_chat_recall_diagnostic:v1"
            or arm != "empty" or plan["trials"] != [[arm, scope]]
            or plan["source_report_sha256"] != sha(SOURCE_REPORT.read_bytes())
            or plan["model"] not in MODEL_MANIFESTS
            or plan["model_identity"]["model_content_sha256"] != MODEL_MANIFESTS[plan["model"]]
            or plan["options"]["model"] != plan["model"]
            or plan["options"]["manifest_sha256"] != MODEL_MANIFESTS[plan["model"]]
            or config_digest != plan["model_identity"]["configuration_digest"]
            or type(plan["options"]["num_gpu"]) is not int
            or not 0 <= plan["options"]["num_gpu"] <= 128 or plan["options"]["num_thread"] != 2
            or plan["options"]["timeout_seconds"] != 120
            or plan["questions"].get(scope) != expected_question
            or exposure["history_block_digest"] is not None
            or exposure["prompt_score_evidence"]
            or exposure["prompt_sha256"] != plan["matched_base_sha256"][scope]
            or result["plan_sha256"] != plan_hash or len(result["trials"]) != 1):
        raise ValueError("diagnostic plan or trial differs from the pinned no-history protocol")
    trial = result["trials"][0]
    disk = trial["receipt"]
    persisted = read(path / "inference-custody" / "receipts" / (disk["receipt_id"] + ".json"))
    valid, reason = validate_receipt(disk)
    score = score_cited_answer(trial["delivered"], plan["profiles"])
    expected_profile = "inline" if scope == "inline" else "empty"
    expected_citation = "inline-example" if scope == "inline" else None
    exact = (expected_profile in score["exact_profiles"]
             and score["cited_record"] == expected_citation)
    if (trial["trial"] != 0 or trial["condition"] != condition or trial["plan_sha256"] != plan_hash
            or trial["prompt_sha256"] != exposure["prompt_sha256"]
            or (plan["options"]["num_gpu"] == 0 and trial["resident_vram_bytes"] != 0)
            or (plan["options"]["num_gpu"] > 0 and trial["resident_vram_bytes"] <= 0)
            or not valid or reason
            or persisted != disk
            or disk["status"] != "admitted_completed" or disk["fallback_occurred"]
            or disk["request"]["prompt_digest"] != exposure["invocation_prompt_digest"]
            or disk["request"]["linkage"].get(
                "ordinary_developmental_history_prompt_block_digest") is not None
            or disk["request"]["active_model_identity"] != plan["model_identity"]
            or disk["request"]["purpose"] != "local_user_chat"
            or disk["request"]["budget"]["timeout_seconds"] != plan["options"]["timeout_seconds"]
            or digest_payload({"output": trial["model_output"]}) != disk["output_digest"]
            or trial["delivered"] != trial["model_output"].strip()
            or trial["score"] != score or trial["exact"] is not exact):
        raise ValueError("diagnostic response or governed receipt is invalid")
    return {"plan_sha256": plan_hash, "condition": condition,
            "latency_ms": disk["latency_ms"], "format": score["format"], "exact": exact,
            "resident_vram_bytes": trial["resident_vram_bytes"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    print("diagnostic_verified", verify(parser.parse_args().run_directory))
