"""Verify an interrupted v5 recall trial and its governed timeout receipt."""
from __future__ import annotations

import argparse
from pathlib import Path

from sentientos.governed_local_model_invocation import validate_receipt
from work.run_sibling_chat_recall import read, sha


def verify(path: Path):
    plan_path, failure_path = path / "plan.json", path / "trials" / "0" / "failure.json"
    plan, failure = read(plan_path), read(failure_path)
    plan_hash = sha(plan_path.read_bytes())
    if (plan["schema"] != "sentientos.sibling_chat_recall_plan:v5"
            or failure["schema"] != "sentientos.sibling_chat_recall_trial_failure:v1"
            or failure["plan_sha256"] != plan_hash
            or failure["trial"] != 0 or failure["condition"] != "right_wide"
            or failure["prompt_sha256"] != plan["exposures"]["right_wide"]["invocation_prompt_digest"]
            or not failure["model_invoked"] or failure["receipt_status"] != "timeout"
            or failure["exception"] != "governed_inference_not_completed:timeout"
            or failure["output_size_bytes"] != 0 or failure["fallback_occurred"] is not False
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
