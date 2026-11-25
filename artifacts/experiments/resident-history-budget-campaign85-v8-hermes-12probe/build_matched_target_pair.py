"""Build a create-only paired preflight artifact from verified CPU reports."""
from __future__ import annotations

import hashlib
import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from sentientos.local_model_authority import digest_payload
from work.rootless_history_boundary_campaign import _load_plan
from work.verify_rootless_planned_cycle_owner_preflight import verify_report


def _member(plan_path: Path, report_path: Path) -> tuple[dict, dict, dict]:
    plan_raw = plan_path.read_bytes()
    report_raw = report_path.read_bytes()
    plan = _load_plan(plan_path)
    report = json.loads(report_raw)
    verification = verify_report(report_path=report_path, plan_path=plan_path)
    if verification.get("status") != "verified":
        raise ValueError("matched_pair_member_preflight_invalid")
    relative_plan = plan_path.relative_to(REPO_ROOT).as_posix()
    relative_report = report_path.relative_to(REPO_ROOT).as_posix()
    model = plan["model_identity_recipe"]
    value = {
        "campaign_id": plan["campaign_id"],
        "cycle_id": report["cycle_id"],
        "cycle0_transfer_probe_inputs": report["transfer_probe_inputs"],
        "model_artifact_digest": model["manifest_sha256"],
        "model_name": model["model_name"],
        "owner_preflight_verifier_status": "verified",
        "owner_report_digest": (report["audit_digest"]
            if report["audit_digest"].startswith("sha256:") else
            "sha256:" + report["audit_digest"]),
        "owner_report_file": {"path": relative_report,
            "sha256": hashlib.sha256(report_raw).hexdigest()},
        "plan_digest": plan["plan_digest"],
        "plan_file": {"path": relative_plan,
            "sha256": hashlib.sha256(plan_raw).hexdigest()},
        "plan_verifier_status": "verified",
        "selected_history_record_ids": report["owner_selected_record_ids"],
        "target_model_identity_digest": report["target_model_identity_digest"],
    }
    return plan, report, value


def build(*, output: Path, hermes_plan_path: Path, hermes_report_path: Path,
        qwen_plan_path: Path, qwen_report_path: Path) -> dict:
    left = _member(hermes_plan_path, hermes_report_path)
    right = _member(qwen_plan_path, qwen_report_path)
    left_plan, left_report, left_member = left
    right_plan, right_report, right_member = right
    probes = left_report["transfer_probe_inputs"]
    if (len(probes) != 12 or right_report["transfer_probe_inputs"] != probes
            or left_plan["ordered_task_generation_seeds"] !=
                right_plan["ordered_task_generation_seeds"]
            or left_plan["ordered_backend_seeds"] !=
                right_plan["ordered_backend_seeds"]
            or left_plan["initial_history_boundary"]["boundary_digest"] !=
                right_plan["initial_history_boundary"]["boundary_digest"]
            or left_report["owner_selected_record_ids"] !=
                right_report["owner_selected_record_ids"]
            or left_plan["experiment_implementation_sha256"] !=
                right_plan["experiment_implementation_sha256"]
            or left_plan["ordered_model_identity_digests"][0] ==
                right_plan["ordered_model_identity_digests"][0]
            or left_member["model_artifact_digest"] ==
                right_member["model_artifact_digest"]):
        raise ValueError("matched_pair_cross_target_binding_mismatch")
    semantic = {
        "schema_version": "sentientos.rootless_matched_model_target_pair:v2",
        "comparison_status": "matched_preflight_verified",
        "equivalence_checks": {
            "distinct_target_active_identities": True,
            "distinct_target_artifacts": True,
            "hermes_sources_share_hermes_artifact": True,
            "qwen_sources_from_different_artifact": True,
            "same_backend_seeds": True,
            "same_cycle0_transfer_probes": True,
            "same_history_boundary": True,
            "same_implementation_pin": True,
            "same_selected_history_records": True,
            "same_task_family": True,
            "same_task_generation_seeds": True,
        },
        "limits": {
            "authority": False,
            "cycle1_preflight_posture": "rebuild_after_cycle0_history_changes",
            "inference_performed": False,
            "learning_established": False,
            "transfer_established": False,
        },
        "members": {
            "same_model_artifact_target": left_member,
            "different_model_artifact_target": right_member,
        },
        "shared": {
            "heldout_probe_set": probes,
            "implementation_digest": left_report[
                "experiment_implementation_sha256_digest"],
            "implementation_source_count": len(
                left_plan["experiment_implementation_sha256"]),
            "initial_history_boundary_digest": left_plan[
                "initial_history_boundary"]["boundary_digest"],
            "ordered_backend_seeds": left_plan["ordered_backend_seeds"],
            "ordered_task_generation_seeds": left_plan[
                "ordered_task_generation_seeds"],
            "task_family_id": left_plan["task_family_id"],
        },
    }
    pair = {**semantic, "pair_digest": "sha256:" + digest_payload(semantic)}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(pair, handle, sort_keys=True, indent=2)
        handle.write("\n")
    return pair


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-plan", type=Path, required=True)
    parser.add_argument("--hermes-report", type=Path, required=True)
    parser.add_argument("--qwen-plan", type=Path, required=True)
    parser.add_argument("--qwen-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    built = build(output=args.output, hermes_plan_path=args.hermes_plan,
        hermes_report_path=args.hermes_report, qwen_plan_path=args.qwen_plan,
        qwen_report_path=args.qwen_report)
    destination = args.output
    print(json.dumps({"pair": str(destination),
        "pair_digest": built["pair_digest"],
        "heldout_probe_count": len(built["shared"]["heldout_probe_set"]),
        "inference_performed": False, "learning_established": False,
        "authority": False}, sort_keys=True))
