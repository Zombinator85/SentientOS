"""Verify a v5 history-recall prompt plan without model inference."""
from __future__ import annotations

import argparse
from pathlib import Path

from sentientos.local_model import candidate_configuration_digest_from_payload
from work.run_sibling_chat_recall import (
    EXPLICIT_ROW_MAPPING, INLINE_REPORT, MANIFEST, MODEL, SOURCE_REPORT, conditions, read,
    recall_question, sha,
)


def verify(path: Path):
    plan_path, status_path = path / "plan.json", path / "preflight.json"
    plan, status, archive = read(plan_path), read(status_path), read(SOURCE_REPORT)
    plan_hash = sha(plan_path.read_bytes())
    config_digest = candidate_configuration_digest_from_payload({
        "engine": "ollama", "options": plan["options"], "max_context_tokens": plan["context_tokens"],
        "generation": plan["generation"],
    })
    if (plan["schema"] != "sentientos.sibling_chat_recall_plan:v5"
            or status != {
                "schema": "sentientos.sibling_chat_recall_preflight:v1",
                "plan_sha256": plan_hash, "model_invoked": False,
                "inference_performed": False, "runtime_condition_created": False,
                "learning_established": False, "authority": False,
                "resident_vram_bytes": 0,
            }
            or (path / "result.json").exists()
            or plan["source_report_sha256"] != sha(SOURCE_REPORT.read_bytes())
            or plan["model"] != MODEL
            or plan["model_identity"]["model_content_sha256"] != MANIFEST
            or config_digest != plan["model_identity"]["configuration_digest"]
            or plan["options"]["num_gpu"] != 0 or plan["options"]["num_thread"] != 2
            or plan["options"]["timeout_seconds"] != 120
            or plan["trials"] != [list(trial) for trial in conditions(True)]
            or plan["questions"] != {
                scope: ((INLINE_REPORT + "\n") if scope == "inline" else "") + recall_question(scope, True)
                for _, scope in conditions(True)
            }
            or plan["intervention"] != {
                "id": "explicit_developmental_history_field_to_row_mapping:v2",
                "guidance": EXPLICIT_ROW_MAPPING,
                "guidance_sha256": sha(EXPLICIT_ROW_MAPPING.encode()),
            }):
        raise ValueError("preflight plan or no-inference status differs from protocol v5")

    for arm, scope in dict.fromkeys(conditions(True)):
        exposure = plan["exposures"][arm + "_" + scope]
        if exposure["prompt_chars"] > 8000 or len(exposure["prompt_sha256"]) != 64:
            raise ValueError("captured prompt exceeds the ordinary-chat budget or lacks a digest")
        if arm == "empty":
            if exposure["history_block_digest"] is not None or exposure["prompt_score_evidence"]:
                raise ValueError("empty-history control contains history")
            if exposure["history_instruction"] is not None:
                raise ValueError("empty-history control contains treatment guidance")
            if exposure["prompt_sha256"] != plan["matched_base_sha256"][scope]:
                raise ValueError("empty-history prompt differs from its matched base")
            continue
        instruction = exposure.get("history_instruction")
        if (not isinstance(instruction, str)
                or instruction.count(EXPLICIT_ROW_MAPPING.strip()) != 1
                or exposure["history_block_digest"] is None
                or len(exposure["prompt_score_evidence"]) != 1):
            raise ValueError("history treatment is missing, duplicated, or unbound")
        oracle, = archive["questions"]["latest_" + scope]["captures"][arm]["prompt_score_evidence"]
        actual, = exposure["prompt_score_evidence"]
        if any(actual.get(key) != oracle.get(key) for key in (
                "record_id", "source_run_id", "source_score_digest", "examples", "source_fact_id", "task_family_id")):
            raise ValueError("preflight history differs from its archived source evidence")
    return {
        "plan_sha256": plan_hash,
        "preflight_conditions": len(plan["trials"]),
        "history_exposures": sum(
            bool(plan["exposures"][arm + "_" + scope]["prompt_score_evidence"])
            for arm, scope in dict.fromkeys(conditions(True))),
        "maximum_prompt_chars": max(row["prompt_chars"] for row in plan["exposures"].values()),
        "inference_performed": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("preflight_directory", type=Path)
    report = verify(parser.parse_args().preflight_directory)
    print("preflight_verified", report)
