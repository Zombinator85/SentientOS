"""Verify an interrupted v5 recall trial and its governed timeout receipt."""
from __future__ import annotations

import argparse
from pathlib import Path

from sentientos.governed_local_model_invocation import validate_receipt
from work.run_sibling_chat_recall import (
    EXPLICIT_ROW_MAPPING, MODEL_MANIFESTS, STRICT_CITED_OUTPUT_CONTRACT, read, sha,
)


def verify(path: Path):
    plan_path, failure_path = path / "plan.json", path / "trials" / "0" / "failure.json"
    plan, failure = read(plan_path), read(failure_path)
    plan_hash = sha(plan_path.read_bytes())
    schema = plan["schema"]
    strict = schema == "sentientos.sibling_chat_recall_plan:v6"
    preflight_binding_required = (strict or
                                  (plan["options"]["num_gpu"] > 0 and plan["ollama_version"] == "0.40.16"))
    binding_path = path / "preflight_binding.json"
    binding = read(binding_path) if binding_path.exists() else None
    expected_binding = {
        "schema": "sentientos.sibling_chat_recall_preflight_binding:v1",
        "preflight_plan_sha256": plan_hash,
        "full_run_plan_sha256": plan_hash,
        "matched": True,
    }
    mapped = (schema == "sentientos.sibling_chat_recall_plan:v5"
              or (strict and plan.get("intervention") is not None))
    diagnostic = schema == "sentientos.sibling_chat_recall_diagnostic:v1"
    condition = plan.get("diagnostic_condition", "right_wide")
    if (schema not in {"sentientos.sibling_chat_recall_plan:v3", "sentientos.sibling_chat_recall_plan:v5",
                       "sentientos.sibling_chat_recall_plan:v6",
                       "sentientos.sibling_chat_recall_diagnostic:v1"}
            or plan["model"] not in MODEL_MANIFESTS
            or plan["model_identity"]["model_content_sha256"] != MODEL_MANIFESTS[plan["model"]]
            or plan["options"]["model"] != plan["model"]
            or plan["options"]["manifest_sha256"] != MODEL_MANIFESTS[plan["model"]]
            or type(plan["options"]["num_gpu"]) is not int
            or not 0 <= plan["options"]["num_gpu"] <= 128
            or failure["schema"] != "sentientos.sibling_chat_recall_trial_failure:v1"
            or failure["plan_sha256"] != plan_hash
            or failure["trial"] != 0 or failure["condition"] != condition
            or failure["prompt_sha256"] != plan["exposures"][condition]["invocation_prompt_digest"]
            or plan.get("output_contract") != (STRICT_CITED_OUTPUT_CONTRACT if strict else None)
            or (preflight_binding_required and binding != expected_binding)
            or (binding is not None and binding != expected_binding)
            or (strict and plan["source_code_sha256"] != sha(
                Path(__file__).resolve().with_name("run_sibling_chat_recall.py").read_bytes()))
            or not failure["model_invoked"] or failure["receipt_status"] != "timeout"
            or failure["exception"] != "governed_inference_not_completed:timeout"
            or failure["output_size_bytes"] != 0 or failure["fallback_occurred"] is not False
            or plan.get("intervention") != ({
                "id": "explicit_developmental_history_field_to_row_mapping:v2",
                "guidance": EXPLICIT_ROW_MAPPING,
                "guidance_sha256": sha(EXPLICIT_ROW_MAPPING.encode()),
            } if mapped else None)
            or (diagnostic and (plan["trials"] != [condition.split("_", 1)]
                or condition not in {"empty_wide", "empty_inline"}))
            or (not diagnostic and condition != "right_wide")
            or (path / "result.json").exists()):
        raise ValueError("failed-trial record differs from the v5 timeout")
    receipt_path = path / "inference-custody" / "receipts" / (failure["receipt_id"] + ".json")
    receipt = read(receipt_path)
    valid, reason = validate_receipt(receipt)
    if (not valid or reason or receipt["receipt_digest"] != failure["receipt_digest"]
            or receipt["status"] != "timeout" or receipt["reason_codes"] != ["timeout_worker_terminated", "timeout"]
            or receipt["latency_ms"] != failure["latency_ms"]
            or receipt["output_size_bytes"] != 0 or receipt["fallback_occurred"]
            or receipt["request"]["prompt_digest"] != failure["prompt_sha256"]
            or receipt["request"]["budget"]["timeout_seconds"] != plan["options"]["timeout_seconds"]
            or receipt["request"]["active_model_identity"] != plan["model_identity"]):
        raise ValueError("governed timeout receipt does not match the captured trial")
    return {
        "plan_sha256": plan_hash, "receipt_id": receipt["receipt_id"],
        "latency_ms": receipt["latency_ms"], "output_size_bytes": receipt["output_size_bytes"],
        "fallback_occurred": receipt["fallback_occurred"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    print("timeout_verified", verify(parser.parse_args().run_directory))
