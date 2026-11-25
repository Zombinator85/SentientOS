"""Reconstruct the planned v8 runtime overlap receipt from frozen history.

This is an offline CPU reconstruction. It does not create a cycle root, load a
model, or assert that the runtime receipt was emitted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from sentientos.developmental_model_replacement_experiment import (
    ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY,
    rootless_integer_affine_transfer_task_pair,
)
from sentientos.local_model_authority import digest_payload
from sentientos.resident_developmental_cognition import (
    _task_family_history_examples,
    _task_family_history_probe_overlap,
)
from sentientos.resident_developmental_writeback import DevelopmentalHistoryStore
from work.rootless_history_boundary_campaign import (
    _history_boundary,
    _load_plan,
    verify_experiment_implementation,
    verify_model_identity_recipe,
)


def reconstruct(plan_path: Path, history_root: Path, output: Path) -> dict[str, Any]:
    plan = _load_plan(plan_path)
    if (plan.get("task_family_id") != ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY
            or plan.get("schema_version") !=
                "sentientos.rootless_history_boundary_campaign_plan:v11"):
        raise ValueError("cpu_gate_preview_plan_family_invalid")
    identity = verify_model_identity_recipe(plan)
    implementation = verify_experiment_implementation(plan)
    if (identity.get("identity_digests_verified") is not True
            or implementation.get("experiment_implementation_matches_current") is not True):
        raise ValueError("cpu_gate_preview_plan_verification_failed")
    cycle_index = 0
    cycle_id = plan["ordered_cycle_ids"][cycle_index]
    seed = plan["ordered_task_generation_seeds"][cycle_index]
    boundary_before = _history_boundary(history_root)
    if boundary_before != plan["initial_history_boundary"]:
        raise ValueError("cpu_gate_preview_initial_boundary_mismatch")

    acquisition, transfer = rootless_integer_affine_transfer_task_pair(
        seed, task_family_id=ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY,
        transfer_probe_count=plan.get("transfer_probe_count", 3))
    acquisition_inputs = [acquisition.probe_input,
        *acquisition.additional_probe_inputs]
    transfer_inputs = [transfer.probe_input, *transfer.additional_probe_inputs]
    history_families = list(transfer.history_task_family_ids)
    manifest_record_digests = {
        row["path"].removeprefix("records/").removesuffix(".json"): row["sha256"]
        for row in boundary_before["files"] if row["path"].startswith("records/")}
    records = DevelopmentalHistoryStore(history_root).records()
    if (len({record.record_id for record in records}) != len(records)
            or sorted(manifest_record_digests) != sorted(
                record.record_id for record in records)):
        raise ValueError("cpu_gate_preview_history_inventory_mismatch")

    packets: list[dict[str, Any]] = []
    projected_record_ids: list[str] = []
    for record in records:
        envelope = asdict(record)
        encoded = (json.dumps(envelope, sort_keys=True, indent=2) + "\n").encode("utf-8")
        if hashlib.sha256(encoded).hexdigest() != manifest_record_digests[record.record_id]:
            raise ValueError("cpu_gate_preview_history_record_digest_mismatch")
        candidate = envelope.get("candidate")
        if not isinstance(candidate, dict):
            continue
        projected = []
        for family_id in history_families:
            projected.extend(_task_family_history_examples(candidate,
                task_family_id=family_id))
        if projected:
            packets.append({"task_relevant_experience": projected})
            projected_record_ids.append(record.record_id)

    transfer_overlap = _task_family_history_probe_overlap(packets,
        task_probe_inputs=transfer_inputs)
    acquisition_overlap = _task_family_history_probe_overlap(packets,
        task_probe_inputs=acquisition_inputs)
    qualified = (acquisition_overlap.get(
        "historical_probe_overlap_measurement_complete") is True
        and acquisition_overlap.get("historical_probe_overlap_input_count") == 0)
    boundary_after = _history_boundary(history_root)
    if boundary_after != boundary_before:
        raise ValueError("cpu_gate_preview_history_changed_during_read")

    receipt_semantic = {
        "schema_version": "sentientos.rootless_campaign_transfer_probe_preflight:v3",
        "cycle_id": cycle_id,
        "seed": seed,
        "task_family_id": plan["task_family_id"],
        "history_task_family_ids": history_families,
        "prior_history_boundary_digest": boundary_before["boundary_digest"],
        "projected_record_ids": projected_record_ids,
        "projected_record_set_digest": digest_payload({
            "record_ids": projected_record_ids}),
        "acquisition_probe_inputs": acquisition_inputs,
        "transfer_probe_inputs": transfer_inputs,
        "historical_probe_overlap": transfer_overlap,
        "held_out_transfer_qualified": (
            transfer_overlap.get("historical_probe_overlap_measurement_complete") is True
            and transfer_overlap.get("historical_probe_overlap_input_count") == 0),
        "inference_performed": False,
        "learning_claimed": False,
        "authority_granted": False,
        "acquisition_historical_probe_overlap": acquisition_overlap,
        "novel_acquisition_qualified": qualified,
    }
    schema_path = REPO_ROOT / "docs/development/"
    schema_path /= "rootless_novel_acquisition_transfer_probe_preflight.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    receipt_semantic["preflight_digest"] = digest_payload(receipt_semantic)
    try:
        import jsonschema
        jsonschema.Draft202012Validator(schema).validate(receipt_semantic)
    except ImportError as exc:
        raise ValueError("cpu_gate_preview_jsonschema_unavailable") from exc
    except Exception as exc:
        raise ValueError("cpu_gate_preview_receipt_schema_invalid") from exc

    receipt = receipt_semantic
    wrapper_semantic = {
        "schema_version": "sentientos.rootless_novel_acquisition_gate_cpu_reconstruction:v1",
        "plan_digest": plan["plan_digest"],
        "cycle_id": cycle_id,
        "history_boundary_digest": boundary_before["boundary_digest"],
        "history_boundary_stable_across_read": True,
        "projected_history_record_count": len(projected_record_ids),
        "receipt_schema_validated": True,
        "preflight_receipt": receipt,
        "verification_scope": "offline_reconstruction_from_frozen_persisted_history",
        "runtime_receipt_emitted": False,
        "model_loaded": False,
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
    }
    artifact = {**wrapper_semantic,
        "reconstruction_digest": digest_payload(wrapper_semantic)}
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or output.is_symlink():
        raise ValueError("cpu_gate_preview_output_exists")
    output.write_text(json.dumps(artifact, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--history-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = reconstruct(args.plan, args.history_root, args.output)
    receipt = report["preflight_receipt"]
    print(json.dumps({
        "artifact": str(args.output),
        "reconstruction_digest": report["reconstruction_digest"],
        "acquisition_probe_inputs": receipt["acquisition_probe_inputs"],
        "acquisition_overlap_count": receipt[
            "acquisition_historical_probe_overlap"][
                "historical_probe_overlap_input_count"],
        "novel_acquisition_qualified": receipt[
            "novel_acquisition_qualified"],
        "transfer_probe_inputs": receipt["transfer_probe_inputs"],
        "transfer_overlap_count": receipt["historical_probe_overlap"][
            "historical_probe_overlap_input_count"],
        "runtime_receipt_emitted": False,
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
