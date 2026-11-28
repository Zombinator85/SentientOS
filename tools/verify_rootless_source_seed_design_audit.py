"""Reconstruct a low-range source-seed design audit without model inference."""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.developmental_model_replacement_experiment import (  # noqa: E402
    rootless_integer_affine_transfer_task_pair,
)
from sentientos.local_model_authority import digest_payload  # noqa: E402
from work.rootless_history_boundary_campaign import (  # noqa: E402
    _LOW_RANGE_SOURCE_ACQUISITION_PROTOCOL,
    _load_plan,
    verify_experiment_implementation,
)


def _read_private_object(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("source_seed_audit_file_invalid")
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise ValueError("source_seed_audit_file_mode_invalid")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("source_seed_audit_json_invalid")
    return value


def reconstruct(plan_path: Path, audit_path: Path) -> dict[str, Any]:
    plan = _load_plan(plan_path)
    implementation = verify_experiment_implementation(plan)
    audit = _read_private_object(audit_path)
    protocol = plan.get("low_range_source_acquisition_protocol")
    if (plan.get("schema_version") !=
            "sentientos.rootless_history_boundary_campaign_plan:v15"
            or protocol != _LOW_RANGE_SOURCE_ACQUISITION_PROTOCOL
            or plan.get("task_family_id") != protocol["task_family_id"]):
        raise ValueError("source_seed_audit_plan_contract_invalid")

    cycle_ids = plan["ordered_cycle_ids"]
    task_seeds = plan["ordered_task_generation_seeds"]
    acquisition_count = plan.get("acquisition_probe_count", 3)
    transfer_count = plan.get("transfer_probe_count", 3)
    designs: list[dict[str, Any]] = []
    acquisition_sets: list[set[int]] = []
    for index, (cycle_id, seed) in enumerate(zip(cycle_ids, task_seeds)):
        acquisition, transfer = rootless_integer_affine_transfer_task_pair(
            seed,
            task_family_id=plan["task_family_id"],
            acquisition_probe_count=acquisition_count,
            transfer_probe_count=transfer_count,
        )
        acquisition_inputs = acquisition.specification()["probe_inputs"]
        transfer_inputs = transfer.specification()["probe_inputs"]
        if set(acquisition_inputs) & set(transfer_inputs):
            raise ValueError("source_seed_audit_within_cycle_probe_overlap")
        acquisition_sets.append(set(acquisition_inputs))
        designs.append({
            "acquisition_transfer_overlap_count": 0,
            "cycle_id": cycle_id,
            "cycle_index": index,
            "planned_acquisition_probe_inputs": acquisition_inputs,
            "planned_heldout_transfer_probe_inputs": transfer_inputs,
            "task_generation_seed": seed,
        })

    planned_inputs = sorted(set().union(*acquisition_sets))
    overlap_counts = {value: sum(value in values for values in acquisition_sets)
        for value in planned_inputs}
    cross_cycle_overlap = sorted(value for value, count in overlap_counts.items()
        if count > 1)
    unique_opportunities = [{
        "cycle_id": cycle_id,
        "planned_acquisition_inputs_unique_to_cycle": sorted(
            acquisition_sets[index].difference(*(
                acquisition_sets[:index] + acquisition_sets[index + 1:]))),
    } for index, cycle_id in enumerate(cycle_ids)]
    semantic = {
        "actual_correctness_observed": False,
        "authority": False,
        "campaign_id": plan["campaign_id"],
        "completed_source_run_count": 0,
        "correct_input_values_included": False,
        "cross_cycle_acquisition_overlap_count": len(cross_cycle_overlap),
        "cross_cycle_acquisition_overlap_inputs": cross_cycle_overlap,
        "cross_cycle_probe_reuse_allowed": protocol[
            "cross_cycle_probe_reuse_allowed"],
        "cycle_designs": designs,
        "cycle_unique_acquisition_opportunities": unique_opportunities,
        "distinct_correct_input_threshold": protocol[
            "minimum_distinct_correct_source_inputs"],
        "distinct_planned_acquisition_input_count": len(planned_inputs),
        "distinct_planned_acquisition_inputs": planned_inputs,
        "inference_performed": False,
        "initial_history_boundary_digest": plan[
            "initial_history_boundary"]["boundary_digest"],
        "initial_history_file_count": plan["initial_history_boundary"][
            "file_count"],
        "learning_established": False,
        "plan_digest": plan["plan_digest"],
        "planned_probe_input_values_included": True,
        "planned_probe_inputs_are_not_observed_correctness": True,
        "potential_input_coverage_meets_correct_input_threshold": (
            len(planned_inputs) >= protocol[
                "minimum_distinct_correct_source_inputs"]),
        "schema_version": "sentientos.low_range_source_seed_design_audit:v1",
        "source_eligibility_status": "not_evaluated_no_completed_runs",
        "source_run_threshold": protocol[
            "minimum_score_bound_correct_source_runs"],
        "within_cycle_acquisition_transfer_disjointness_verified": True,
    }
    digest = digest_payload(semantic)
    if audit.get("audit_digest") != digest:
        raise ValueError("source_seed_audit_digest_mismatch")
    if audit != {**semantic, "audit_digest": digest}:
        raise ValueError("source_seed_audit_reconstruction_mismatch")
    return {
        "actual_correctness_observed": False,
        "audit_digest": digest,
        "authority": False,
        "experiment_implementation_bound": implementation[
            "experiment_implementation_bound"],
        "experiment_implementation_digest": implementation[
            "experiment_implementation_digest"],
        "experiment_implementation_source_count": implementation[
            "experiment_implementation_source_count"],
        "inference_performed": False,
        "learning_established": False,
        "plan_digest": plan["plan_digest"],
        "schema_version": "sentientos.low_range_source_seed_design_audit_verification:v3",
        "status": "verified",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = reconstruct(args.plan, args.audit)
    encoded = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output is None:
        print(encoded, end="")
        return
    if args.output.exists() or args.output.is_symlink():
        raise ValueError("source_seed_audit_output_already_exists")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(encoded)


if __name__ == "__main__":
    main()
