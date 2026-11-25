"""Independently verify matched rootless model-target preflight evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.local_model_authority import digest_payload  # noqa: E402
from sentientos.windows_handle_custody import (  # noqa: E402
    WindowsHandleCustodyError,
    read_explicit_file,
)
from work.rootless_history_boundary_campaign import (  # noqa: E402
    _load_plan,
)
from work.verify_rootless_planned_cycle_owner_preflight import (  # noqa: E402
    verify_report,
)

SCHEMA_PATH = (REPO_ROOT / "docs/development/"
    "rootless_matched_model_target_pair.schema.json")
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = read_explicit_file(path, max_bytes=MAX_ARTIFACT_BYTES)
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError,
            WindowsHandleCustodyError) as exc:
        raise ValueError("matched_model_pair_artifact_invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("matched_model_pair_artifact_invalid")
    return value


def _repo_artifact(relative: Any) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError("matched_model_pair_path_invalid")
    pure = PurePosixPath(relative)
    if (pure.is_absolute() or ".." in pure.parts or "\\" in relative
            or relative != pure.as_posix()):
        raise ValueError("matched_model_pair_path_invalid")
    candidate = REPO_ROOT.joinpath(*pure.parts)
    current = REPO_ROOT
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("matched_model_pair_path_symlink")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(REPO_ROOT.resolve(strict=True))
    except (OSError, ValueError, RuntimeError) as exc:
        raise ValueError("matched_model_pair_path_outside_repository") from exc
    if not resolved.is_file():
        raise ValueError("matched_model_pair_path_not_file")
    return resolved


def _validate_schema(pair: Mapping[str, Any], schema_path: Path) -> None:
    schema = _read_json(schema_path)
    try:
        import jsonschema
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(dict(pair))
    except ImportError as exc:
        raise ValueError("matched_model_pair_jsonschema_unavailable") from exc
    except Exception as exc:
        raise ValueError("matched_model_pair_schema_invalid") from exc


def _bound_member(pair_member: Mapping[str, Any]) -> tuple[
        dict[str, Any], dict[str, Any], dict[str, Any]]:
    plan_ref = pair_member["plan_file"]
    report_ref = pair_member["owner_report_file"]
    plan_path = _repo_artifact(plan_ref["path"])
    report_path = _repo_artifact(report_ref["path"])
    for path, expected in ((plan_path, plan_ref["sha256"]),
            (report_path, report_ref["sha256"])):
        actual = hashlib.sha256(read_explicit_file(path,
            max_bytes=MAX_ARTIFACT_BYTES)).hexdigest()
        if actual != expected:
            raise ValueError("matched_model_pair_file_hash_mismatch")
    plan = _load_plan(plan_path)
    report = _read_json(report_path)
    recipe = plan.get("model_identity_recipe")
    if not isinstance(recipe, Mapping):
        raise ValueError("matched_model_pair_identity_recipe_missing")
    if (plan.get("plan_digest") != pair_member["plan_digest"]
            or report.get("campaign_id") != plan.get("campaign_id")
            or report.get("audit_digest") != pair_member["owner_report_digest"]
            or report.get("cycle_id") != pair_member["cycle_id"]
            or report.get("campaign_id") != pair_member["campaign_id"]
            or report.get("plan_digest") != plan.get("plan_digest")
            or report.get("target_model_identity_digest") != pair_member[
                "target_model_identity_digest"]
            or report.get("owner_selected_record_ids") != pair_member[
                "selected_history_record_ids"]
            or report.get("transfer_probe_inputs") != pair_member[
                "cycle0_transfer_probe_inputs"]
            or pair_member.get("model_artifact_digest") != recipe.get(
                "manifest_sha256")
            or pair_member.get("model_name") != recipe.get("model_name")
            or pair_member["owner_preflight_verifier_status"] != "verified"
            or pair_member["plan_verifier_status"] != "verified"):
        raise ValueError("matched_model_pair_member_binding_mismatch")
    reconstructed = verify_report(report_path=report_path,
        plan_path=plan_path)
    if (reconstructed.get("status") != "verified"
            or reconstructed.get("plan_digest") != plan.get("plan_digest")
            or reconstructed.get("report_digest") != report.get("audit_digest")
            or reconstructed.get("cycle_id") != report.get("cycle_id")):
        raise ValueError("matched_model_pair_preflight_verification_mismatch")
    return plan, report, reconstructed


def verify_pair(*, pair_path: Path, schema_path: Path = SCHEMA_PATH
        ) -> dict[str, Any]:
    pair = _read_json(Path(pair_path))
    _validate_schema(pair, Path(schema_path))
    semantic = {key: value for key, value in pair.items()
        if key != "pair_digest"}
    if pair.get("pair_digest") != "sha256:" + digest_payload(semantic):
        raise ValueError("matched_model_pair_digest_mismatch")
    members = pair.get("members")
    if not isinstance(members, Mapping) or set(members) != {
            "same_model_artifact_target", "different_model_artifact_target"}:
        raise ValueError("matched_model_pair_members_invalid")
    verified: dict[str, tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = {}
    for key, member in members.items():
        if not isinstance(member, Mapping):
            raise ValueError("matched_model_pair_member_invalid")
        plan_path = _repo_artifact(member["plan_file"]["path"])
        report_path = _repo_artifact(member["owner_report_file"]["path"])
        verified[key] = _bound_member(member)
    left_plan, left_report, left_verification = verified[
        "same_model_artifact_target"]
    right_plan, right_report, right_verification = verified[
        "different_model_artifact_target"]
    left_recipe = left_plan.get("model_identity_recipe")
    right_recipe = right_plan.get("model_identity_recipe")
    if not isinstance(left_recipe, Mapping) or not isinstance(right_recipe, Mapping):
        raise ValueError("matched_model_pair_identity_recipe_missing")
    left_artifact = left_recipe.get("manifest_sha256")
    right_artifact = right_recipe.get("manifest_sha256")
    if (left_recipe.get("model_name") not in {
                "hf.co/bartowski/NousResearch_Hermes-4-14B-GGUF:Q4_K_M",
                "sentientos-hermes4:14b-q4km"}
            or right_recipe.get("model_name") != "qwen3:8b"):
        raise ValueError("matched_model_pair_target_model_roles_invalid")
    left_sources = left_report.get("accumulated_strategy_model_identity_audit")
    right_sources = right_report.get("accumulated_strategy_model_identity_audit")
    if not isinstance(left_sources, Mapping) or not isinstance(right_sources, Mapping):
        raise ValueError("matched_model_pair_source_identity_audit_missing")
    left_relations = left_sources.get("artifact_relation_counts")
    right_relations = right_sources.get("artifact_relation_counts")
    if (not isinstance(left_relations, list) or not isinstance(right_relations, list)
            or left_sources.get("all_source_artifacts_differ_from_target") is not False
            or right_sources.get("all_source_artifacts_differ_from_target") is not True
            or left_relations != [{"relation": "same_model_artifact_identity",
                "source_count": left_sources.get("source_count")}]
            or right_relations != [{"relation": "different_model_artifact_identity",
                "source_count": right_sources.get("source_count")}]
            or left_artifact == right_artifact):
        raise ValueError("matched_model_pair_source_artifact_relation_invalid")
    if (left_plan.get("ordered_model_identity_digests", [None])[0] ==
            right_plan.get("ordered_model_identity_digests", [None])[0]):
        raise ValueError("matched_model_pair_target_identity_not_distinct")
    shared = pair["shared"]
    left_boundary = left_plan["initial_history_boundary"]["boundary_digest"]
    right_boundary = right_plan["initial_history_boundary"]["boundary_digest"]
    equivalence = pair["equivalence_checks"]
    expected = {
        "distinct_target_active_identities": True,
        "distinct_target_artifacts": left_artifact != right_artifact,
        "hermes_sources_share_hermes_artifact": True,
        "qwen_sources_from_different_artifact": True,
        "same_backend_seeds": left_plan["ordered_backend_seeds"] ==
            right_plan["ordered_backend_seeds"],
        "same_cycle0_transfer_probes": left_report["transfer_probe_inputs"] ==
            right_report["transfer_probe_inputs"],
        "same_history_boundary": left_boundary == right_boundary,
        "same_implementation_pin": left_plan.get("experiment_implementation_sha256") ==
            right_plan.get("experiment_implementation_sha256"),
        "same_selected_history_records": left_report["owner_selected_record_ids"] ==
            right_report["owner_selected_record_ids"],
        "same_task_family": left_plan.get("task_family_id") ==
            right_plan.get("task_family_id"),
        "same_task_generation_seeds": left_plan.get("ordered_task_generation_seeds") ==
            right_plan.get("ordered_task_generation_seeds"),
    }
    for name, result in expected.items():
        if result is not True or equivalence.get(name) is not True:
            raise ValueError("matched_model_pair_equivalence_failed")
    if (shared.get("heldout_probe_set") != left_report["transfer_probe_inputs"]
            or shared.get("implementation_digest") != left_report.get(
                "experiment_implementation_sha256_digest")
            or shared.get("initial_history_boundary_digest") != left_boundary
            or shared.get("ordered_backend_seeds") != left_plan[
                "ordered_backend_seeds"]
            or shared.get("ordered_task_generation_seeds") != left_plan[
                "ordered_task_generation_seeds"]
            or shared.get("ordered_backend_seeds") != right_plan[
                "ordered_backend_seeds"]
            or shared.get("ordered_task_generation_seeds") != right_plan[
                "ordered_task_generation_seeds"]
            or shared.get("implementation_source_count") !=
                left_verification.get("implementation_source_count")
            or shared.get("implementation_source_count") !=
                right_verification.get("implementation_source_count")
            or shared.get("task_family_id") != left_plan.get("task_family_id")
            or any(pair["limits"].get(field) is not False for field in (
                "authority", "inference_performed", "learning_established",
                "transfer_established"))):
        raise ValueError("matched_model_pair_shared_binding_mismatch")
    return {
        "status": "verified",
        "pair_digest": pair["pair_digest"],
        "same_model_artifact_campaign": left_plan["campaign_id"],
        "different_model_artifact_campaign": right_plan["campaign_id"],
        "shared_history_boundary_digest": left_boundary,
        "matched_cycle0_transfer_probes": left_report["transfer_probe_inputs"],
        "same_implementation_source_count": shared["implementation_source_count"],
        "distinct_target_artifacts": True,
        "distinct_target_active_identities": True,
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", type=Path, required=True)
    parser.add_argument("--schema", type=Path, default=SCHEMA_PATH)
    args = parser.parse_args()
    result = verify_pair(pair_path=args.pair, schema_path=args.schema)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
