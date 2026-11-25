"""Verify a persisted CPU-only v3 preflight reconstruction artifact.

This checks schemas, digests, and plan/artifact bindings. It does not reopen or
recompute the frozen history; use the reconstruction command for that step.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from sentientos.local_model_authority import digest_payload
from work.rootless_history_boundary_campaign import (
    _load_plan,
    verify_experiment_implementation,
    verify_model_identity_recipe,
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("cpu_reconstruction_object_expected")
    return value


def verify(artifact_path: Path, plan_path: Path) -> dict[str, Any]:
    artifact = _read_json(artifact_path)
    plan = _load_plan(plan_path)
    identity = verify_model_identity_recipe(plan)
    implementation = verify_experiment_implementation(plan)
    if (identity.get("identity_digests_verified") is not True
            or implementation.get("experiment_implementation_matches_current")
                is not True):
        raise ValueError("cpu_reconstruction_plan_verification_failed")

    wrapper_semantic = {key: value for key, value in artifact.items()
        if key != "reconstruction_digest"}
    if artifact.get("reconstruction_digest") != digest_payload(wrapper_semantic):
        raise ValueError("cpu_reconstruction_digest_mismatch")
    receipt = artifact.get("preflight_receipt")
    if not isinstance(receipt, dict):
        raise ValueError("cpu_reconstruction_receipt_missing")
    receipt_semantic = {key: value for key, value in receipt.items()
        if key != "preflight_digest"}
    if receipt.get("preflight_digest") != digest_payload(receipt_semantic):
        raise ValueError("cpu_reconstruction_preflight_digest_mismatch")

    if (artifact.get("plan_digest") != plan.get("plan_digest")
            or artifact.get("cycle_id") != plan["ordered_cycle_ids"][0]
            or receipt.get("cycle_id") != artifact.get("cycle_id")
            or receipt.get("seed") != plan["ordered_task_generation_seeds"][0]
            or artifact.get("history_boundary_digest") !=
                plan["initial_history_boundary"].get("boundary_digest")
            or receipt.get("prior_history_boundary_digest") !=
                artifact.get("history_boundary_digest")
            or artifact.get("projected_history_record_count") !=
                len(receipt.get("projected_record_ids", []))
            or len(set(receipt.get("projected_record_ids", []))) !=
                len(receipt.get("projected_record_ids", []))
            or receipt.get("projected_record_set_digest") != digest_payload({
                "record_ids": receipt.get("projected_record_ids")})):
        raise ValueError("cpu_reconstruction_plan_binding_mismatch")
    if (artifact.get("history_boundary_stable_across_read") is not True
            or artifact.get("receipt_schema_validated") is not True
            or artifact.get("verification_scope") !=
                "offline_reconstruction_from_frozen_persisted_history"
            or any(artifact.get(key) is not False for key in (
                "runtime_receipt_emitted", "model_loaded", "inference_performed",
                "learning_established", "authority"))):
        raise ValueError("cpu_reconstruction_scope_claim_invalid")

    schema_dir = REPO_ROOT / "docs/development"
    import jsonschema
    for instance, schema_name in (
        (artifact, "rootless_novel_acquisition_gate_cpu_reconstruction.schema.json"),
        (receipt, "rootless_novel_acquisition_transfer_probe_preflight.schema.json"),
    ):
        schema = _read_json(schema_dir / schema_name)
        jsonschema.Draft202012Validator(schema).validate(instance)

    return {
        "status": "verified_artifact_integrity_and_plan_binding",
        "cycle_id": artifact["cycle_id"],
        "plan_digest": artifact["plan_digest"],
        "history_boundary_digest": artifact["history_boundary_digest"],
        "acquisition_overlap_count": receipt[
            "acquisition_historical_probe_overlap"][
                "historical_probe_overlap_input_count"],
        "transfer_overlap_count": receipt["historical_probe_overlap"][
            "historical_probe_overlap_input_count"],
        "reconstruction_digest": artifact["reconstruction_digest"],
        "history_recomputed_by_verifier": False,
        "runtime_receipt_emitted": False,
        "model_loaded": False,
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.artifact, args.plan), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
