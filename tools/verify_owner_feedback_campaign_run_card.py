from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

SCHEMA = "sentientos.owner_feedback_recall_campaign_run_card:v2"
EXPECTED_CYCLE_MAPPING = {
    "SENTIENTOS_HERMES_CYCLE_ID": "cycle_id",
    "SENTIENTOS_HERMES_EXPERIMENT_SEED": "task_generation_seed",
    "SENTIENTOS_HERMES_BACKEND_SEED": "backend_seed",
    "SENTIENTOS_ROOTLESS_PRIOR_HISTORY_ROOT": "prior_history_root",
    "SENTIENTOS_HERMES_GPU_AVAILABLE_FOR_CYCLE":
        "must equal cycle_id after the operator confirms the GPU is free",
}


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected_json_object")
    return value


def verify(card_path: Path) -> dict[str, Any]:
    card_path = card_path.resolve(strict=True)
    card = read_object(card_path)
    if card.get("schema_version") != SCHEMA:
        raise ValueError("run_card_schema_mismatch")
    checks: dict[str, bool] = {}
    checks["private_mode_0600"] = (
        stat.S_IMODE(card_path.stat().st_mode) == 0o600)

    required_common = card.get("required_common_environment")
    if not isinstance(required_common, dict):
        raise ValueError("required_common_environment_missing")
    workspace = required_common.get("SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE")
    if not isinstance(workspace, str) or not workspace:
        raise ValueError("experiment_workspace_missing")
    os.environ["SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE"] = workspace
    from sentientos.local_model_authority import digest_payload
    from work.rootless_history_boundary_campaign import (
        _history_boundary,
        _load_plan,
        verify_experiment_implementation,
        verify_model_identity_recipe,
    )
    plan_path = Path(str(card.get("campaign_plan_path", ""))).resolve(strict=True)
    plan = _load_plan(plan_path)
    checks["campaign_id_matches"] = (
        card.get("campaign_id") == plan.get("campaign_id"))
    checks["campaign_plan_path_matches"] = (
        str(plan_path) == str(Path(str(required_common.get(
            "SENTIENTOS_HERMES_CAMPAIGN_PLAN_PATH", ""))).resolve()))
    checks["plan_digest_matches"] = (
        card.get("campaign_plan_digest") == plan.get("plan_digest"))
    checks["plan_schema_matches"] = (
        card.get("campaign_plan_schema_version") == plan.get("schema_version"))

    recipe = plan.get("model_identity_recipe")
    if not isinstance(recipe, dict):
        raise ValueError("model_identity_recipe_missing")
    identity = verify_model_identity_recipe(plan)
    implementation = verify_experiment_implementation(plan)
    checks["model_identity_and_source_pins_match"] = (
        identity.get("identity_digests_verified") is True
        and implementation.get("experiment_implementation_matches_current")
            is True)
    checks["identity_recipe_digest_matches"] = (
        card.get("model_identity_recipe_digest")
        == digest_payload(dict(recipe)))

    manifest_path = Path(str(card.get("model_manifest_path", ""))).resolve(strict=True)
    manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    checks["model_manifest_matches"] = (
        manifest_digest == card.get("model_manifest_sha256")
        == recipe.get("manifest_sha256")
        and manifest_path.stem == manifest_digest
        and manifest_path == Path(str(
            recipe.get("resolved_manifest_path", ""))).resolve())
    checks["model_runtime_matches"] = (
        card.get("model_name") == recipe.get("model_name")
        and card.get("gpu_layers") == recipe.get("gpu_layers"))

    protocol_path = Path(str(card.get(
        "owner_feedback_protocol_path", ""))).resolve(strict=True)
    protocol_bytes = protocol_path.read_bytes().replace(b"\r\n", b"\n").replace(
        b"\r", b"\n")
    protocol_digest = hashlib.sha256(protocol_bytes).hexdigest()
    protocol = read_object(protocol_path)
    checks["protocol_identity_and_digest_match"] = (
        card.get("owner_feedback_protocol_id") == protocol.get("protocol_id")
        and card.get("owner_feedback_protocol_digest") == protocol_digest)

    checks["common_environment_matches"] = (
        required_common.get("SENTIENTOS_HERMES_CAMPAIGN_PLAN_PATH")
            == str(plan_path)
        and required_common.get("SENTIENTOS_HERMES_PREREGISTRATION_DIGEST")
            == plan.get("plan_digest")
        and required_common.get("SENTIENTOS_HERMES_OWNER_FEEDBACK_PROTOCOL_DIGEST")
            == protocol_digest
        and required_common.get("SENTIENTOS_HERMES_MODEL")
            == card.get("model_name")
        and required_common.get("SENTIENTOS_HERMES_MODEL_MANIFEST_PATH")
            == str(manifest_path)
        and required_common.get("SENTIENTOS_HERMES_GPU_LAYERS")
            == str(card.get("gpu_layers")))

    cycles = card.get("cycles")
    ids = plan.get("ordered_cycle_ids")
    task_seeds = plan.get("ordered_task_generation_seeds")
    backend_seeds = plan.get("ordered_backend_seeds")
    if not all(isinstance(x, list) for x in (cycles, ids, task_seeds, backend_seeds)):
        raise ValueError("ordered_cycle_bindings_missing")
    checks["cycle_bindings_match"] = (
        len(cycles) == len(ids) == len(task_seeds) == len(backend_seeds)
        and all(
            isinstance(cycle, dict)
            and cycle.get("cycle_index") == i
            and cycle.get("cycle_id") == ids[i]
            and cycle.get("task_generation_seed") == task_seeds[i]
            and cycle.get("backend_seed") == backend_seeds[i]
            and cycle.get("operator_gpu_confirmation_value_must_equal_cycle_id")
                == ids[i]
            and cycle.get("gpu_confirmation_required_at_launch") is True
            and cycle.get("status") == "prepared_not_started"
            for i, cycle in enumerate(cycles)))
    checks["cycle_environment_mapping_matches"] = (
        card.get("required_cycle_environment_mapping")
            == EXPECTED_CYCLE_MAPPING)
    if len(cycles) == 2 and all(
            isinstance(cycle, dict) for cycle in cycles):
        first_history_root = Path(str(
            cycles[0].get("prior_history_root", ""))).resolve(strict=True)
        second_history_root = Path(str(
            cycles[1].get("prior_history_root", ""))).resolve()
        initial_boundary = plan.get("initial_history_boundary")
        checks["initial_history_boundary_matches"] = (
            isinstance(initial_boundary, dict)
            and _history_boundary(first_history_root).get("boundary_digest")
                == initial_boundary.get("boundary_digest"))
        expected_second_root = (
            Path(workspace) / "sentientos-data" / "rootless-experimental"
            / "developmental-cognition-cycles" / ids[0]
            / "resident-cognition" / "history").resolve()
        checks["cycle_history_lineage_matches"] = (
            second_history_root == expected_second_root)
    else:
        checks["initial_history_boundary_matches"] = False
        checks["cycle_history_lineage_matches"] = False
    checks["no_inference_or_authority_claimed"] = (
        card.get("inference_performed") is False
        and card.get("authority") is False)
    if not all(checks.values()):
        raise ValueError("run_card_binding_mismatch:" + ",".join(
            key for key, passed in checks.items() if not passed))
    return {
        "operation": "verified",
        "campaign_id": plan["campaign_id"],
        "plan_digest": plan["plan_digest"],
        "protocol_digest": protocol_digest,
        "run_card_sha256": hashlib.sha256(card_path.read_bytes()).hexdigest(),
        "verifier_sha256": hashlib.sha256(
            Path(__file__).resolve().read_bytes()).hexdigest(),
        "checks": checks,
        "inference_performed": False,
        "authority": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Offline custody verifier for a prepared owner-feedback run card.")
    parser.add_argument("--run-card", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify(args.run_card)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"operation": "rejected", "reason": str(exc),
            "inference_performed": False, "authority": False}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())