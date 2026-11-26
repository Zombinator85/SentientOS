"""Verify a matched 2x2 strict-output/history-mapping preflight matrix."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from work.run_sibling_chat_recall import EXPLICIT_ROW_MAPPING, read, sha
from work.verify_sibling_chat_recall_preflight import verify as verify_preflight


MATCHED_FIELDS = (
    "model", "model_identity", "ollama_version", "options", "context_tokens", "generation",
    "source_report_sha256", "source_code_sha256", "trials", "questions", "profiles",
)
OUTPUT_FACTOR = "strict fenced JSON instruction injected after retrieval"
MAPPING_FACTOR = "explicit history-field-to-row mapping injected in history guidance"


def verify_matrix(control: Path, mapped: Path, strict_control: Path, strict_mapped: Path) -> dict:
    paths = {
        "control": control,
        "mapped": mapped,
        "strict_control": strict_control,
        "strict_mapped": strict_mapped,
    }
    statuses = {name: verify_preflight(path) for name, path in paths.items()}
    plans = {name: read(path / "plan.json") for name, path in paths.items()}
    reference = plans["control"]
    if any(any(plan.get(field) != reference.get(field) for field in MATCHED_FIELDS)
           for plan in plans.values()):
        raise ValueError("factorial arms differ on a model, runtime, source, or task field")

    expected_intervention = {
        "id": "explicit_developmental_history_field_to_row_mapping:v2",
        "guidance": EXPLICIT_ROW_MAPPING,
        "guidance_sha256": sha(EXPLICIT_ROW_MAPPING.encode()),
    }
    factor_expectations = {
        "control": ("sentientos.sibling_chat_recall_plan:v3", None, None),
        "mapped": ("sentientos.sibling_chat_recall_plan:v5", expected_intervention, None),
        "strict_control": (
            "sentientos.sibling_chat_recall_plan:v6", None, "fenced_json_only:v1"),
        "strict_mapped": (
            "sentientos.sibling_chat_recall_plan:v6", expected_intervention, "fenced_json_only:v1"),
    }
    for name, (schema, intervention, output_contract) in factor_expectations.items():
        plan = plans[name]
        if (plan["schema"] != schema or plan.get("intervention") != intervention
                or plan.get("output_contract") != output_contract):
            raise ValueError(f"factor assignments differ for {name}")

    exposure_keys = set(reference["exposures"])
    for plan in plans.values():
        if set(plan["exposures"]) != exposure_keys:
            raise ValueError("factorial arms do not expose the same conditions")
    for key in exposure_keys:
        evidence = [plans[name]["exposures"][key]["prompt_score_evidence"] for name in paths]
        if any(items != evidence[0] for items in evidence[1:]):
            raise ValueError(f"source history evidence differs across arms for {key}")
        if key.startswith("empty_"):
            if (plans["control"]["exposures"][key]["prompt_sha256"]
                    != plans["mapped"]["exposures"][key]["prompt_sha256"]
                    or plans["strict_control"]["exposures"][key]["prompt_sha256"]
                    != plans["strict_mapped"]["exposures"][key]["prompt_sha256"]):
                raise ValueError(f"mapping changes an empty-history prompt for {key}")

    # Removing history and treatment yields the same task prompt within each
    # output-format level; the strict instruction is the only base-prompt change.
    for name in ("mapped",):
        if plans[name]["matched_base_sha256"] != plans["control"]["matched_base_sha256"]:
            raise ValueError("mapping changes the matched base prompt")
    if plans["strict_control"]["matched_base_sha256"] != plans["strict_mapped"]["matched_base_sha256"]:
        raise ValueError("strict mapped arm differs from strict control outside history")
    if plans["strict_control"]["matched_base_sha256"] == plans["control"]["matched_base_sha256"]:
        raise ValueError("strict-output factor is absent from the captured base prompts")

    plan_hashes = {name: statuses[name]["plan_sha256"] for name in paths}
    matrix_payload = {
        "plan_sha256": plan_hashes,
        "matched_fields": list(MATCHED_FIELDS),
        "history_evidence_equal_across_all_arms": True,
        "output_factor": OUTPUT_FACTOR,
        "mapping_factor": MAPPING_FACTOR,
        "runtime": reference["ollama_version"],
        "model": reference["model"],
        "model_identity": reference["model_identity"],
        "planned_trials_per_arm": len(reference["trials"]),
        "model_invoked": False,
        "inference_performed": False,
        "learning_established": False,
    }
    matrix_sha = hashlib.sha256(json.dumps(
        matrix_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "schema": "sentientos.sibling_chat_recall_factorial_preflight:v1",
        "design_status": "exploratory post-hoc protocol replication; not confirmatory",
        "primary_outcome": "official exact trials under the preregistered full-response scorer",
        "secondary_diagnostics": [
            "official valid-format trials",
            "exact fenced JSON content and citation (diagnostic only)",
            "prose outside the required fence",
        ],
        "inferential_scope": "descriptive arm counts only; repeated conditions are not independent samples",
        "learning_claim": "none; this is read-only retrieval of existing history with no learning update",
        **matrix_payload,
        "matrix_sha256": matrix_sha,
        "arm_status": statuses,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("control", type=Path)
    parser.add_argument("mapped", type=Path)
    parser.add_argument("strict_control", type=Path)
    parser.add_argument("strict_mapped", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_matrix(args.control, args.mapped, args.strict_control, args.strict_mapped),
                     indent=2, sort_keys=True))
