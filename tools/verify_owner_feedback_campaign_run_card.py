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

SCHEMA_V2 = "sentientos.owner_feedback_recall_campaign_run_card:v2"
SCHEMA_V3 = "sentientos.owner_feedback_recall_campaign_run_card:v3"
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
    schema = card.get("schema_version")
    if schema not in {SCHEMA_V2, SCHEMA_V3}:
        raise ValueError("run_card_schema_mismatch")
    is_source_replan = schema == SCHEMA_V3
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
        _experiment_implementation_hashes,
        _history_boundary,
        _load_plan,
        verify_experiment_implementation,
        verify_model_identity_recipe,
    )
    plan_path = Path(str(card.get("campaign_plan_path", ""))).resolve(strict=True)
    plan = _load_plan(plan_path)
    checks["campaign_id_matches"] = (
        card.get("campaign_id") == plan.get("campaign_id"))
    supersedes_path_value = card.get("supersedes_run_card_path")
    supersedes_digest = card.get("supersedes_run_card_sha256")
    if not isinstance(supersedes_path_value, str) or not isinstance(
            supersedes_digest, str):
        raise ValueError("superseded_run_card_binding_missing")
    superseded_path = Path(supersedes_path_value).resolve(strict=True)
    superseded_card = read_object(superseded_path)
    superseded_cycles = superseded_card.get("cycles")
    current_cycles = card.get("cycles")
    cycle_identity = lambda rows: [
        (row.get("cycle_id"), row.get("task_generation_seed"),
            row.get("backend_seed")) for row in rows
        if isinstance(row, dict)]
    supersession_base = (
        hashlib.sha256(superseded_path.read_bytes()).hexdigest()
            == supersedes_digest
        and isinstance(superseded_cycles, list)
        and isinstance(current_cycles, list)
        and len(cycle_identity(superseded_cycles)) == len(superseded_cycles)
        and len(cycle_identity(current_cycles)) == len(current_cycles))
    if is_source_replan:
        old_cycle_ids = {row[0] for row in cycle_identity(superseded_cycles or [])}
        old_task_seeds = {row[1] for row in cycle_identity(superseded_cycles or [])}
        old_backend_seeds = {row[2] for row in cycle_identity(superseded_cycles or [])}
        new_rows = cycle_identity(current_cycles or [])
        checks["supersession_chain_matches"] = (
            supersession_base
            and superseded_card.get("status") == "prepared_not_started"
            and superseded_card.get("inference_performed") is False
            and superseded_card.get("campaign_id") != card.get("campaign_id")
            and superseded_card.get("campaign_plan_digest")
                != card.get("campaign_plan_digest")
            and card.get("supersession_kind") == "source_pin_replan"
            and all(row[0] not in old_cycle_ids
                and row[1] not in old_task_seeds
                and row[2] not in old_backend_seeds for row in new_rows))
    else:
        checks["supersession_chain_matches"] = (
            supersession_base
            and superseded_card.get("campaign_id") == card.get("campaign_id")
            and superseded_card.get("campaign_plan_digest")
                == card.get("campaign_plan_digest")
            and cycle_identity(superseded_cycles) == cycle_identity(current_cycles))
    checks["campaign_plan_path_matches"] = (
        str(plan_path) == str(Path(str(required_common.get(
            "SENTIENTOS_HERMES_CAMPAIGN_PLAN_PATH", ""))).resolve()))
    checks["plan_digest_matches"] = (
        card.get("campaign_plan_digest") == plan.get("plan_digest"))
    checks["plan_schema_matches"] = (
        card.get("campaign_plan_schema_version") == plan.get("schema_version"))
    campaign_design = card.get("campaign_design")
    if plan.get("schema_version") == "sentientos.rootless_history_boundary_campaign_plan:v14":
        if not isinstance(campaign_design, dict):
            raise ValueError("campaign_design_binding_missing")
        boundary = plan.get("initial_history_boundary")
        expected_design = {
            "task_family_id": plan.get("task_family_id"),
            "acquisition_probe_count": plan.get("acquisition_probe_count"),
            "transfer_probe_count": plan.get("transfer_probe_count"),
            "initial_history_boundary_digest": (
                boundary.get("boundary_digest")
                if isinstance(boundary, dict) else None),
        }
        checks["campaign_design_matches"] = campaign_design == expected_design
    else:
        checks["campaign_design_matches"] = (
            campaign_design is None or isinstance(campaign_design, dict))

    recipe = plan.get("model_identity_recipe")
    if not isinstance(recipe, dict):
        raise ValueError("model_identity_recipe_missing")
    identity = verify_model_identity_recipe(plan)
    try:
        implementation = verify_experiment_implementation(plan)
    except ValueError as exc:
        if str(exc) != "history_campaign_experiment_implementation_mismatch":
            raise
        expected_pins = plan.get("experiment_implementation_sha256")
        current_pins = _experiment_implementation_hashes()
        mismatch_paths = sorted(path for path in set(expected_pins) | set(current_pins)
            if expected_pins.get(path) != current_pins.get(path))
        raise ValueError(
            "history_campaign_experiment_implementation_mismatch:"
            + ",".join(mismatch_paths)) from exc
    checks["model_identity_and_source_pins_match"] = (
        identity.get("identity_digests_verified") is True
        and implementation.get("experiment_implementation_matches_current")
            is True)
    checks["identity_recipe_digest_matches"] = (
        card.get("model_identity_recipe_digest")
        == digest_payload(dict(recipe)))
    saved_verification = card.get("plan_verification")
    checks["saved_plan_verification_matches_current"] = (
        isinstance(saved_verification, dict)
        and saved_verification.get("experiment_implementation_digest")
            == implementation.get("experiment_implementation_digest")
        and saved_verification.get("experiment_implementation_source_count")
            == implementation.get("experiment_implementation_source_count")
        and saved_verification.get("source_implementation_matches_current")
            == implementation.get("experiment_implementation_matches_current")
        and saved_verification.get("model_identity_digests_verified")
            == identity.get("identity_digests_verified")
        and saved_verification.get("model_identity_recipe_digest")
            == identity.get("model_identity_recipe_digest")
        and saved_verification.get("inference_performed") is False)

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
    if is_source_replan:
        bundle_path = Path(str(card.get(
            "initial_history_bundle_path", ""))).resolve(strict=True)
        bundle = read_object(bundle_path)
        checks["initial_history_bundle_matches_plan"] = (
            hashlib.sha256(bundle_path.read_bytes()).hexdigest()
                == card.get("initial_history_bundle_sha256")
            and bundle.get("campaign_id") == plan.get("campaign_id")
            and bundle.get("plan_digest") == plan.get("plan_digest")
            and bundle.get("bundle_digest")
                == card.get("initial_history_bundle_digest")
            and bundle.get("source_history_boundary_digest")
                == plan.get("initial_history_boundary", {}).get("boundary_digest")
            and bundle.get("source_history_file_count")
                == plan.get("initial_history_boundary", {}).get("file_count")
            and bundle.get("source_history_total_size_bytes")
                == plan.get("initial_history_boundary", {}).get("total_size_bytes"))
        preflight_binding = card.get("cycle0_preflight_evidence")
        if not isinstance(preflight_binding, dict):
            raise ValueError("cycle0_preflight_binding_missing")
        preflight_path = Path(str(preflight_binding.get("report_path", ""))).resolve(strict=True)
        verification_path = Path(str(
            preflight_binding.get("verification_path", ""))).resolve(strict=True)
        preflight = read_object(preflight_path)
        preflight_verification = read_object(verification_path)
        checks["cycle0_preflight_matches_plan"] = (
            hashlib.sha256(preflight_path.read_bytes()).hexdigest()
                == preflight_binding.get("report_sha256")
            and hashlib.sha256(verification_path.read_bytes()).hexdigest()
                == preflight_binding.get("verification_sha256")
            and preflight.get("campaign_id") == plan.get("campaign_id")
            and preflight.get("plan_digest") == plan.get("plan_digest")
            and preflight.get("cycle_id") == ids[0]
            and preflight.get("inference_performed") is False
            and preflight.get("learning_established") is False
            and preflight_verification.get("status") == "verified"
            and preflight_verification.get("implementation_matches_current") is True
            and preflight_verification.get("source_preflight_reconstructed") is True
            and preflight_verification.get("inference_performed") is False
            and preflight_verification.get("plan_digest") == plan.get("plan_digest"))
        expected_cycles_root = (Path(workspace) / "sentientos-data"
            / "rootless-experimental" / "developmental-cognition-cycles")
        checks["planned_cycle_roots_absent"] = all(
            not (expected_cycles_root / cycle_id).exists()
            and not (expected_cycles_root / cycle_id).is_symlink()
            for cycle_id in ids)
        checks["cycle1_preflight_is_sequential"] = (
            card.get("cycle1_preflight_status")
                == "blocked_until_cycle0_completion_and_chain_verification")
    checks["no_inference_or_authority_claimed"] = (
        card.get("inference_performed") is False
        and card.get("authority") is False
        and card.get("status") == "prepared_not_started"
        and card.get("preregistration_timing_independently_attested") is False)
    if not all(checks.values()):
        raise ValueError("run_card_binding_mismatch:" + ",".join(
            key for key, passed in checks.items() if not passed))
    return {
        "operation": "verified",
        "campaign_id": plan["campaign_id"],
        "plan_digest": plan["plan_digest"],
        "protocol_digest": protocol_digest,
        "supersession_kind": card.get("supersession_kind", "same_plan_card_revision"),
        "plan_implementation_digest": implementation[
            "experiment_implementation_digest"],
        "cycle0_preflight_status": (
            preflight_verification.get("status") if is_source_replan else None),
        "cycle1_preflight_status": (
            card.get("cycle1_preflight_status") if is_source_replan else None),
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