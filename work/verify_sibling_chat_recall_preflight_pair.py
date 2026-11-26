"""Verify a matched strict-output sibling-chat preflight pair without inference."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from work.run_sibling_chat_recall import EXPLICIT_ROW_MAPPING, STRICT_CITED_OUTPUT_CONTRACT, read, sha
from work.verify_sibling_chat_recall_preflight import verify


MATCHED_FIELDS = (
    "model", "model_identity", "ollama_version", "options", "context_tokens", "generation",
    "source_report_sha256", "source_code_sha256", "trials", "questions", "profiles",
    "matched_base_sha256", "output_contract",
)


def verify_pair(control_path: Path, mapped_path: Path) -> dict:
    control_status = verify(control_path)
    mapped_status = verify(mapped_path)
    control, mapped = read(control_path / "plan.json"), read(mapped_path / "plan.json")
    if any(control.get(field) != mapped.get(field) for field in MATCHED_FIELDS):
        raise ValueError("strict control and mapped plans differ on a matched field")
    if (control["schema"] != "sentientos.sibling_chat_recall_plan:v6"
            or mapped["schema"] != "sentientos.sibling_chat_recall_plan:v6"
            or control["output_contract"] != STRICT_CITED_OUTPUT_CONTRACT):
        raise ValueError("pair does not use the strict cited-output protocol")
    expected_intervention = {
        "id": "explicit_developmental_history_field_to_row_mapping:v2",
        "guidance": EXPLICIT_ROW_MAPPING,
        "guidance_sha256": sha(EXPLICIT_ROW_MAPPING.encode()),
    }
    if control.get("intervention") is not None or mapped.get("intervention") != expected_intervention:
        raise ValueError("pair does not isolate the explicit row-mapping treatment")

    keys = set(control["exposures"])
    if keys != set(mapped["exposures"]):
        raise ValueError("control and mapped exposure sets differ")
    for key in keys:
        left, right = control["exposures"][key], mapped["exposures"][key]
        if left["prompt_score_evidence"] != right["prompt_score_evidence"]:
            raise ValueError(f"matched source evidence differs for {key}")
        if key.startswith("empty_") and left["prompt_sha256"] != right["prompt_sha256"]:
            raise ValueError(f"empty-history prompts differ for {key}")
    pair_payload = {
        "control_plan_sha256": control_status["plan_sha256"],
        "mapped_plan_sha256": mapped_status["plan_sha256"],
        "matched_fields": list(MATCHED_FIELDS),
        "history_evidence_equal": True,
        "output_contract": STRICT_CITED_OUTPUT_CONTRACT,
        "intervention": expected_intervention["id"],
        "model_invoked": False,
        "inference_performed": False,
        "learning_established": False,
    }
    return {
        "schema": "sentientos.sibling_chat_recall_preflight_pair:v1",
        **pair_payload,
        "pair_sha256": hashlib.sha256(json.dumps(
            pair_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "control": control_status,
        "mapped": mapped_status,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("control_preflight", type=Path)
    parser.add_argument("mapped_preflight", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_pair(args.control_preflight, args.mapped_preflight),
                     indent=2, sort_keys=True))
