"""Read-only verifier for persisted rootless owner/prompt preflight reports."""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.windows_handle_custody import (  # noqa: E402
    WindowsHandleCustodyError,
    read_explicit_file,
)
from sentientos.local_model_authority import digest_payload  # noqa: E402
from work.replay_planned_cycle_owner_preflight import (  # noqa: E402
    _canonical_digest,
    create_report,
    _validate_historical_examples_ablation,
    _validate_negative_example_ablation,
    _validate_strategy_inclusion_ablation,
)
from work.rootless_history_boundary_campaign import (  # noqa: E402
    _load_plan,
    verify_experiment_implementation,
    verify_model_identity_recipe,
)
from sentientos.rootless_experimental_local_model import (  # noqa: E402
    EXPERIMENT_ROOT,
)

REPORT_SCHEMA = "sentientos.rootless_planned_cycle_owner_preflight:v21"
ABLATION_SCHEMA_PATH = (REPO_ROOT / "docs/development/"
    "rootless_planned_cycle_strategy_inclusion_ablation.schema.json")
EXAMPLES_ABLATION_SCHEMA_PATH = (REPO_ROOT / "docs/development/"
    "rootless_planned_cycle_historical_examples_ablation.schema.json")
NEGATIVE_ABLATION_SCHEMA_PATH = (REPO_ROOT / "docs/development/"
    "rootless_planned_cycle_negative_example_ablation.schema.json")
MAX_REPORT_BYTES = 4_194_304


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = read_explicit_file(Path(path), max_bytes=MAX_REPORT_BYTES)
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError,
            WindowsHandleCustodyError) as exc:
        raise ValueError("owner_preflight_artifact_invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("owner_preflight_artifact_invalid")
    return value


def verify_report(*, report_path: Path, plan_path: Path,
        schema_path: Path = ABLATION_SCHEMA_PATH,
        examples_schema_path: Path = EXAMPLES_ABLATION_SCHEMA_PATH,
        negative_schema_path: Path = NEGATIVE_ABLATION_SCHEMA_PATH) -> dict[str, Any]:
    """Verify a saved report's digest, plan binding, identity, and ablation schema."""
    report = _read_json(Path(report_path))
    plan = _load_plan(Path(plan_path))
    if report.get("schema_version") != REPORT_SCHEMA:
        raise ValueError("owner_preflight_report_schema_unsupported")
    claimed_digest = report.get("audit_digest")
    semantic = {key: value for key, value in report.items()
        if key != "audit_digest"}
    if (not isinstance(claimed_digest, str)
            or claimed_digest != _canonical_digest(semantic)):
        raise ValueError("owner_preflight_report_digest_mismatch")
    if (report.get("campaign_id") != plan.get("campaign_id")
            or report.get("plan_digest") != plan.get("plan_digest")
            or report.get("task_family_id") != plan.get("task_family_id")):
        raise ValueError("owner_preflight_report_plan_binding_mismatch")
    cycle_ids = plan.get("ordered_cycle_ids")
    if not isinstance(cycle_ids, list) or cycle_ids.count(report.get("cycle_id")) != 1:
        raise ValueError("owner_preflight_report_cycle_binding_mismatch")
    cycle_index = cycle_ids.index(report["cycle_id"])
    expected_identity_digest = plan["ordered_model_identity_digests"][cycle_index]
    expected_task_seed = plan["ordered_task_generation_seeds"][cycle_index]
    expected_prior_boundary_digest = (
        plan["initial_history_boundary"].get("boundary_digest")
        if cycle_index == 0 else None)
    prior_boundary_verification = report.get(
        "prior_history_boundary_verification")
    prior_prefix_valid = (cycle_index == 0 or (
        isinstance(prior_boundary_verification, Mapping)
        and prior_boundary_verification.get("status") ==
            "append_only_campaign_prefix_verified"
        and prior_boundary_verification.get(
            "append_only_history_chain_verified") is True
        and prior_boundary_verification.get("boundary_digest") ==
            report.get("prior_history_boundary_digest")
        and prior_boundary_verification.get("verified_prefix_cycle_ids") ==
            cycle_ids[:cycle_index]
        and report.get("prior_history_root_cycle_id") ==
            cycle_ids[cycle_index - 1]))
    if (report.get("target_model_identity_digest") != expected_identity_digest
            or report.get("target_model_identity_matches_plan") is not True
            or report.get("task_generation_seed") != expected_task_seed
            or not prior_prefix_valid
            or (expected_prior_boundary_digest is not None
                and report.get("prior_history_boundary_digest") !=
                    expected_prior_boundary_digest)):
        raise ValueError("owner_preflight_report_source_binding_mismatch")
    if (report.get("inference_performed") is not False
            or report.get("learning_established") is not False
            or report.get("authority") is not False
            or report.get("prompt_within_bound") is not True
            or report.get("task_family_prompt_projection_verified") is not True):
        raise ValueError("owner_preflight_report_posture_invalid")
    ablation = report.get("strategy_inclusion_ablation")
    if not isinstance(ablation, Mapping):
        raise ValueError("owner_preflight_ablation_missing")
    _validate_strategy_inclusion_ablation(ablation)
    if (ablation.get("status") != "accumulated_strategy_not_present"
            and (ablation.get("baseline_prompt_digest") != report.get("prompt_digest")
                or ablation.get("baseline_prompt_chars") != report.get("prompt_chars")
                or ablation.get("selected_record_ids") != report.get(
                    "binder_selected_record_ids")
                or ablation.get("selected_record_digests") != report.get(
                    "binder_selected_record_digests"))):
        raise ValueError("owner_preflight_ablation_report_binding_mismatch")
    examples_ablation = report.get("historical_examples_ablation")
    if not isinstance(examples_ablation, Mapping):
        raise ValueError("owner_preflight_examples_ablation_missing")
    _validate_historical_examples_ablation(examples_ablation)
    if (examples_ablation.get("status") != "historical_examples_not_present"
            and (examples_ablation.get("baseline_prompt_digest")
                    != report.get("prompt_digest")
                or examples_ablation.get("baseline_prompt_chars")
                    != report.get("prompt_chars")
                or examples_ablation.get("selected_record_ids") != report.get(
                    "binder_selected_record_ids")
                or examples_ablation.get("selected_record_digests") != report.get(
                    "binder_selected_record_digests"))):
        raise ValueError("owner_preflight_examples_ablation_report_binding_mismatch")
    negative_ablation = report.get("negative_example_ablation")
    if not isinstance(negative_ablation, Mapping):
        raise ValueError("owner_preflight_negative_ablation_missing")
    _validate_negative_example_ablation(negative_ablation)
    if (negative_ablation.get("status") != "negative_examples_not_present"
            and (negative_ablation.get("baseline_prompt_digest")
                    != report.get("prompt_digest")
                or negative_ablation.get("baseline_prompt_chars")
                    != report.get("prompt_chars")
                or negative_ablation.get("selected_record_ids") != report.get(
                    "binder_selected_record_ids")
                or negative_ablation.get("selected_record_digests") != report.get(
                    "binder_selected_record_digests")
                or negative_ablation.get("heldout_probe_count") != len(
                    report.get("transfer_probe_inputs", ())))):
        raise ValueError("owner_preflight_negative_ablation_report_binding_mismatch")
    reuse = report.get("planned_seed_probe_reuse")
    acquisition_reuse = report.get("planned_acquisition_probe_reuse")
    if (not isinstance(acquisition_reuse, Mapping)
            or acquisition_reuse.get("schema_version")
                != "sentientos.rootless_planned_cycle_acquisition_probe_reuse:v1"
            or acquisition_reuse.get("acquisition_probe_inputs")
                != report.get("acquisition_probe_inputs")
            or acquisition_reuse.get("acquisition_probe_input_digest")
                != _canonical_digest({"probe_inputs": report.get(
                    "acquisition_probe_inputs")})
            or acquisition_reuse.get("inference_performed") is not False
            or acquisition_reuse.get("learning_established") is not False
            or acquisition_reuse.get("authority") is not False
            or acquisition_reuse.get("no_exact_history_probe_overlap")
                != (acquisition_reuse.get(
                    "prompt_projection_overlap_measurement_complete") is True
                    and acquisition_reuse.get(
                        "prompt_projection_overlap_input_count") == 0)):
        raise ValueError("owner_preflight_acquisition_probe_reuse_invalid")
    if not isinstance(reuse, Mapping):
        raise ValueError("owner_preflight_seed_probe_reuse_missing")
    if (examples_ablation.get("status") != "historical_examples_not_present"
            and (examples_ablation.get("heldout_transfer_probe_count")
                    != len(report.get("transfer_probe_inputs", ()))
                or examples_ablation.get("heldout_transfer_probe_digest")
                    != reuse.get("transfer_probe_input_digest")
                or examples_ablation.get("historical_probe_overlap_input_count")
                    != reuse.get("prompt_projection_overlap_input_count")
                or examples_ablation.get("historical_probe_overlap_example_count")
                    != reuse.get("prompt_projection_overlap_example_count")
                or examples_ablation.get("historical_probe_overlap_input_digest")
                    != reuse.get("prompt_projection_overlap_input_digest")
                or examples_ablation.get("historical_probe_overlap_measurement_complete")
                    != reuse.get("prompt_projection_overlap_measurement_complete"))):
        raise ValueError("owner_preflight_examples_ablation_probe_binding_mismatch")
    schema = _read_json(Path(schema_path))
    try:
        import jsonschema
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(dict(ablation))
    except ImportError as exc:
        raise ValueError("owner_preflight_jsonschema_unavailable") from exc
    except Exception as exc:
        raise ValueError("owner_preflight_ablation_schema_invalid") from exc
    examples_schema = _read_json(Path(examples_schema_path))
    try:
        jsonschema.Draft202012Validator.check_schema(examples_schema)
        jsonschema.Draft202012Validator(examples_schema).validate(
            dict(examples_ablation))
    except Exception as exc:
        raise ValueError("owner_preflight_examples_ablation_schema_invalid") from exc
    negative_schema = _read_json(Path(negative_schema_path))
    try:
        jsonschema.Draft202012Validator.check_schema(negative_schema)
        jsonschema.Draft202012Validator(negative_schema).validate(
            dict(negative_ablation))
    except Exception as exc:
        raise ValueError("owner_preflight_negative_ablation_schema_invalid") from exc
    identity_evidence = verify_model_identity_recipe(plan)
    implementation_evidence = verify_experiment_implementation(plan)
    expected_implementation_digest = digest_payload(dict(
        plan["experiment_implementation_sha256"]))
    if (identity_evidence.get("identity_digests_verified") is not True
            or identity_evidence.get("inference_performed") is not False
            or implementation_evidence.get(
                "experiment_implementation_matches_current") is not True
            or implementation_evidence.get("inference_performed") is not False
            or report.get("experiment_implementation_sha256_digest")
                != expected_implementation_digest):
        raise ValueError("owner_preflight_plan_evidence_verification_failed")
    history_root_cycle_id = report.get("prior_history_root_cycle_id")
    recipe = plan.get("model_identity_recipe")
    if (not isinstance(history_root_cycle_id, str)
            or re.fullmatch(r"rootless-cognition-cycle-[0-9a-f]{20}",
                history_root_cycle_id) is None
            or not isinstance(recipe, Mapping)
            or not isinstance(recipe.get("resolved_manifest_path"), str)
            or not isinstance(recipe.get("model_name"), str)):
        raise ValueError("owner_preflight_source_reconstruction_inputs_invalid")
    prior_history_root = (EXPERIMENT_ROOT / "developmental-cognition-cycles"
        / history_root_cycle_id / "resident-cognition" / "history")
    with tempfile.TemporaryDirectory(prefix="sentientos-owner-preflight-verify-") as temp_dir:
        reconstructed = create_report(plan_path=Path(plan_path),
            prior_history_root=prior_history_root,
            manifest_path=Path(recipe["resolved_manifest_path"]),
            model_name=recipe["model_name"],
            output_path=Path(temp_dir) / "reconstructed_report.json",
            cycle_index=cycle_index,
            alternate_seed_count=report.get(
                "alternate_seed_sensitivity_summary", {}).get(
                    "seed_count", 16))
    reconstruction_fields = (
        "campaign_id", "plan_digest", "cycle_id",
        "prior_history_root_cycle_id", "prior_history_boundary_digest",
        "prior_history_boundary_verification", "owner_selected_record_ids",
        "owner_ranking_trace_schema",
        "owner_ranking_trace", "binder_selected_record_ids",
        "binder_selected_record_digests", "prompt_digest", "prompt_chars",
        "negative_example_delivery", "historical_examples_ablation",
        "negative_example_ablation",
        "planned_acquisition_probe_reuse", "alternate_seed_sensitivity",
        "alternate_seed_sensitivity_summary")
    if any(json.loads(json.dumps(reconstructed.get(field), sort_keys=True))
            != json.loads(json.dumps(report.get(field), sort_keys=True))
            for field in reconstruction_fields):
        raise ValueError("owner_preflight_source_reconstruction_mismatch")
    return {
        "status": "verified",
        "report_schema": report["schema_version"],
        "campaign_id": report["campaign_id"],
        "cycle_id": report["cycle_id"],
        "cycle_index": cycle_index,
        "plan_digest": report["plan_digest"],
        "report_digest": claimed_digest,
        "target_model_identity_digest": expected_identity_digest,
        "model_identity_recipe_digest": identity_evidence[
            "model_identity_recipe_digest"],
        "initial_history_boundary_digest": report[
            "prior_history_boundary_digest"],
        "implementation_digest": implementation_evidence[
            "experiment_implementation_digest"],
        "implementation_source_count": implementation_evidence[
            "experiment_implementation_source_count"],
        "ablation_schema_digest": _canonical_digest(schema),
        "historical_examples_ablation_schema_digest": _canonical_digest(
            examples_schema),
        "negative_example_ablation_schema_digest": _canonical_digest(
            negative_schema),
        "strategy_ablation_status": ablation["status"],
        "historical_examples_ablation_status": examples_ablation["status"],
        "historical_examples_withheld_count": examples_ablation.get(
            "withheld_example_count"),
        "heldout_transfer_probe_count": examples_ablation.get(
            "heldout_transfer_probe_count"),
        "historical_probe_overlap_input_count": examples_ablation.get(
            "historical_probe_overlap_input_count"),
        "historical_probe_overlap_example_count": examples_ablation.get(
            "historical_probe_overlap_example_count"),
        "heldout_transfer_probe_set_disjoint": examples_ablation.get(
            "heldout_transfer_probe_set_disjoint"),
        "prompt_chars_removed": ablation.get("prompt_chars_removed"),
        "model_identity_verified": identity_evidence.get(
            "identity_digests_verified") is True,
        "implementation_matches_current": implementation_evidence.get(
            "experiment_implementation_matches_current") is True,
        "source_preflight_reconstructed": True,
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--schema", type=Path, default=ABLATION_SCHEMA_PATH)
    parser.add_argument("--examples-schema", type=Path,
        default=EXAMPLES_ABLATION_SCHEMA_PATH)
    parser.add_argument("--negative-schema", type=Path,
        default=NEGATIVE_ABLATION_SCHEMA_PATH)
    args = parser.parse_args()
    print(json.dumps(verify_report(report_path=args.report,
        plan_path=args.plan, schema_path=args.schema,
        examples_schema_path=args.examples_schema,
        negative_schema_path=args.negative_schema), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
