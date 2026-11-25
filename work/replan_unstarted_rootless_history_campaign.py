"""Replan a v7 campaign after a verified pre-inference GPU headroom failure.

This preserves the frozen task/backend seeds and model identity while assigning
fresh cycle IDs. It does not resume a partially executed cycle or grant
inference authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.governed_local_model_invocation import validate_receipt
from sentientos.local_model_authority import digest_payload
from work.export_rootless_cycle_evidence_manifest import persist_manifest
from work.rootless_history_boundary_campaign import (
    _CAMPAIGN_ID, _CYCLE_ID, _WIDE_TASK_FAMILY, _history_boundary,
    _cognition_recovery_state_boundary, _load_plan, _plan_model_identity_digests,
    _require_output_outside, _runtime_admission_boundary,
    create_plan, verify_model_identity_recipe,
)

RETRY_SCHEMA = "sentientos.rootless_history_preinference_gpu_retry:v1"
_FAILURE_SCHEMA = "sentientos.rootless_ollama_embodied_cognition_failure:v9"
_HEX = re.compile(r"^[0-9a-f]{64}$")
_REVISION = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_MAX_FAILURE_BYTES = 16 * 1024 * 1024


def _read_failure(path: Path) -> tuple[dict[str, Any], str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("gpu_retry_failure_artifact_invalid")
    if path.name != "cycle-failure.json" or path.stat().st_size > _MAX_FAILURE_BYTES:
        raise ValueError("gpu_retry_failure_artifact_invalid")
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("gpu_retry_failure_artifact_invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("gpu_retry_failure_artifact_invalid")
    return value, hashlib.sha256(raw).hexdigest()


def _verify_stage_journal(*, plan: Mapping[str, Any],
        failure: Mapping[str, Any], run_root: Path) -> None:
    summary = failure.get("stage_journal")
    if (not isinstance(summary, Mapping)
            or summary.get("schema_version") !=
                "sentientos.rootless_cycle_stage_journal_summary:v1"
            or summary.get("run_id") != failure.get("run_id")
            or summary.get("last_entered_stage") != failure.get("stage")
            or summary.get("integrity_status") != "valid_digest_bound"):
        raise ValueError("gpu_retry_stage_journal_not_verified")
    rows = summary.get("checkpoints")
    if (not isinstance(rows, list) or not rows
            or summary.get("checkpoint_count") != len(rows)):
        raise ValueError("gpu_retry_stage_journal_inventory_invalid")
    by_sequence = {row.get("stage_sequence"): row for row in rows
        if isinstance(row, Mapping)}
    if len(by_sequence) != len(rows):
        raise ValueError("gpu_retry_stage_journal_inventory_invalid")
    paths = sorted(run_root.glob("stage-checkpoint-*.json"), key=lambda p: p.name)
    if len(paths) != len(rows):
        raise ValueError("gpu_retry_stage_checkpoint_inventory_mismatch")
    checkpoint_fields = {
        "schema_version", "run_id", "stage_sequence", "stage",
        "checkpoint_kind", "recorded_at_utc",
        "external_preregistration_digest", "run_preregistration_digest",
        "source_provenance", "raw_prompts_and_model_output_excluded",
        "checkpoint_digest",
    }
    for path in paths:
        match = re.fullmatch(
            r"stage-checkpoint-(\d{4})-([a-z0-9_]{1,64})\.json", path.name)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 65_536 or match is None:
            raise ValueError("gpu_retry_stage_checkpoint_invalid")
        try:
            checkpoint = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("gpu_retry_stage_checkpoint_invalid") from exc
        if not isinstance(checkpoint, Mapping):
            raise ValueError("gpu_retry_stage_checkpoint_invalid")
        semantic = {key: value for key, value in checkpoint.items()
            if key != "checkpoint_digest"}
        sequence = int(match.group(1))
        stage = match.group(2)
        row = by_sequence.get(sequence)
        if (set(checkpoint) != checkpoint_fields
                or checkpoint.get("schema_version") !=
                    "sentientos.rootless_cycle_stage_checkpoint:v2"
                or checkpoint.get("run_id") != failure.get("run_id")
                or checkpoint.get("stage_sequence") != sequence
                or checkpoint.get("stage") != stage
                or checkpoint.get("checkpoint_kind") != "stage_entered"
                or not isinstance(checkpoint.get("recorded_at_utc"), str)
                or checkpoint.get("external_preregistration_digest") !=
                    plan.get("plan_digest")
                or checkpoint.get("source_provenance") !=
                    failure.get("source_provenance")
                or checkpoint.get("raw_prompts_and_model_output_excluded") is not True
                or checkpoint.get("checkpoint_digest") != digest_payload(semantic)
                or not isinstance(row, Mapping)
                or row.get("stage") != stage
                or row.get("checkpoint_digest") != checkpoint.get("checkpoint_digest")
                or row.get("digest_verified") is not True):
            raise ValueError("gpu_retry_stage_checkpoint_binding_mismatch")

def _verified_unstarted_gpu_failure(*, plan: Mapping[str, Any],
        failure: Mapping[str, Any], failure_path: Path) -> dict[str, Any]:
    run_id = failure.get("run_id")
    if (failure.get("schema_version") != _FAILURE_SCHEMA
            or failure.get("status") != "incomplete"
            or failure.get("failure_code") != "gpu_memory_headroom_insufficient"
            or failure.get("stage") != "model_and_runtime_preflight"
            or not isinstance(run_id, str)
            or not plan.get("ordered_cycle_ids")
            or run_id != plan["ordered_cycle_ids"][0]
            or failure_path.parent.name != run_id
            or (failure_path.parent / "cycle-result.json").exists()):
        raise ValueError("gpu_retry_failure_not_unstarted_headroom_block")
    binding = failure.get("history_campaign_binding")
    boundary = plan.get("initial_history_boundary")
    preflight = (binding.get("transfer_probe_preflight")
        if isinstance(binding, Mapping) else None)
    if (not isinstance(binding, Mapping)
            or not isinstance(boundary, Mapping)
            or not isinstance(preflight, Mapping)
            or binding.get("campaign_id") != plan.get("campaign_id")
            or binding.get("campaign_plan_digest") != plan.get("plan_digest")
            or binding.get("cycle_index") != 0
            or preflight.get("cycle_id") != run_id
            or preflight.get("prior_history_boundary_digest") !=
                boundary.get("boundary_digest")
            or preflight.get("inference_performed") is not False):
        raise ValueError("gpu_retry_failure_campaign_binding_mismatch")
    provenance = failure.get("source_provenance")
    if (not isinstance(provenance, Mapping)
            or provenance.get("observation_status") != "observed"
            or provenance.get("worktree_content_status") != "complete"
            or not isinstance(provenance.get("repository_revision"), str)
            or _REVISION.fullmatch(provenance["repository_revision"]) is None
            or not isinstance(provenance.get("worktree_content_digest"), str)
            or _HEX.fullmatch(provenance["worktree_content_digest"]) is None):
        raise ValueError("gpu_retry_source_provenance_incomplete")
    history_seed = failure.get("prior_developmental_history_seed")
    if (not isinstance(history_seed, Mapping)
            or history_seed.get("status") != "copied_and_reloaded_verified"
            or not isinstance(history_seed.get("source_boundary_digest"), str)
            or _HEX.fullmatch(history_seed["source_boundary_digest"]) is None):
        raise ValueError("gpu_retry_history_seed_not_verified")
    _verify_stage_journal(plan=plan, failure=failure, run_root=failure_path.parent)
    gpu = failure.get("gpu_after")
    if (not isinstance(gpu, Mapping)
            or type(gpu.get("memory_total_mib")) is not int
            or type(gpu.get("memory_free_mib")) is not int
            or type(gpu.get("gpu_utilization_percent")) is not int
            or gpu.get("memory_total_mib") <= 0
            or not 0 <= gpu.get("memory_free_mib") <= gpu.get("memory_total_mib")
            or not 0 <= gpu.get("gpu_utilization_percent") <= 100):
        raise ValueError("gpu_retry_resource_observation_invalid")
    receipts = failure.get("inference_receipts")
    if not isinstance(receipts, list):
        raise ValueError("gpu_retry_receipt_inventory_unavailable")
    for receipt in receipts:
        if (not isinstance(receipt, Mapping)
                or not isinstance(receipt.get("correlation_id"), str)):
            raise ValueError("gpu_retry_receipt_inventory_invalid")
        if run_id in receipt["correlation_id"]:
            raise ValueError("gpu_retry_run_has_inference_receipt")
    unload = failure.get("governed_unload")
    if (not isinstance(unload, Mapping)
            or unload.get("status") != "target_model_not_resident"):
        raise ValueError("gpu_retry_model_residency_not_proven_absent")
    return {
        "failed_cycle_id": run_id,
        "failure_code": failure["failure_code"],
        "failure_stage": failure["stage"],
        "source_provenance_digest": digest_payload(dict(provenance)),
        "history_boundary_digest": boundary["boundary_digest"],
        "inference_receipts_bound_to_failed_cycle": 0,
        "gpu_memory_total_mib": gpu["memory_total_mib"],
        "gpu_memory_free_mib": gpu["memory_free_mib"],
        "gpu_utilization_percent": gpu["gpu_utilization_percent"],
    }


def _verify_failed_cycle_copy(*, source_plan: Mapping[str, Any],
        failure: Mapping[str, Any], run_root: Path) -> None:
    history_root = run_root / "resident-cognition" / "history"
    if _history_boundary(history_root) != source_plan.get("initial_history_boundary"):
        raise ValueError("gpu_retry_copied_history_boundary_mismatch")
    state_root = run_root / "resident-cognition" / "state"
    copied_admission = _runtime_admission_boundary(
        history_root, source_plan.get("initial_history_boundary"))
    copied_recovery = _cognition_recovery_state_boundary(state_root)
    if (copied_admission != source_plan.get("initial_runtime_admission_ledger")
            or copied_recovery != source_plan.get("initial_cognition_recovery_state")):
        raise ValueError("gpu_retry_copied_governance_state_mismatch")
    receipt_root = run_root / "inference-custody" / "receipts"
    if receipt_root.is_symlink() or not receipt_root.is_dir():
        raise ValueError("gpu_retry_local_receipt_inventory_unavailable")
    expected_rows = failure.get("inference_receipts")
    if not isinstance(expected_rows, list):
        raise ValueError("gpu_retry_receipt_inventory_unavailable")
    expected_by_id: dict[str, Mapping[str, Any]] = {}
    for row in expected_rows:
        if (not isinstance(row, Mapping)
                or not isinstance(row.get("receipt_id"), str)
                or not isinstance(row.get("receipt_digest"), str)
                or _HEX.fullmatch(row["receipt_digest"]) is None
                or not isinstance(row.get("correlation_id"), str)):
            raise ValueError("gpu_retry_receipt_inventory_invalid")
        if row["receipt_id"] in expected_by_id:
            raise ValueError("gpu_retry_duplicate_receipt_identity")
        expected_by_id[row["receipt_id"]] = row
    actual_ids: set[str] = set()
    for path in sorted(receipt_root.iterdir(), key=lambda item: item.name):
        if (path.is_symlink() or not path.is_file()
                or re.fullmatch(r"lmrec-[0-9a-f]{24}\.json", path.name) is None):
            raise ValueError("gpu_retry_local_receipt_file_invalid")
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("gpu_retry_local_receipt_file_invalid") from exc
        if not isinstance(document, Mapping):
            raise ValueError("gpu_retry_local_receipt_file_invalid")
        receipt_id = document.get("receipt_id")
        request = document.get("request")
        correlation_id = (request.get("correlation_id")
            if isinstance(request, Mapping) else document.get("correlation_id"))
        expected_row = expected_by_id.get(receipt_id) if isinstance(receipt_id, str) else None
        if (not isinstance(receipt_id, str) or receipt_id in actual_ids
                or path.stem != receipt_id or not isinstance(correlation_id, str)
                or not isinstance(expected_row, Mapping)
                or document.get("receipt_digest") != expected_row.get("receipt_digest")
                or correlation_id != expected_row.get("correlation_id")
                or failure["run_id"] in correlation_id):
            raise ValueError("gpu_retry_current_cycle_receipt_found")
        actual_ids.add(receipt_id)
    if actual_ids != set(expected_by_id):
        raise ValueError("gpu_retry_receipt_inventory_binding_mismatch")

def _verify_existing_artifact(value: Mapping[str, Any], path: Path) -> None:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("gpu_retry_existing_artifact_invalid")
    parent = path.parent.resolve(strict=True)
    if path.parent.absolute() != parent or path.stat().st_nlink != 1:
        raise ValueError("gpu_retry_existing_artifact_invalid")
    raw = path.read_bytes()
    expected = (json.dumps(dict(value), sort_keys=True, separators=(",", ":"))
        + "\n").encode("utf-8")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("gpu_retry_existing_artifact_invalid") from exc
    if parsed != dict(value) or raw != expected:
        raise ValueError("gpu_retry_existing_artifact_mismatch")

def replan(*, source_plan_path: Path, failure_path: Path,
        history_root: Path, campaign_id: str, cycle_ids: list[str],
        output_plan: Path, output_record: Path, verify_existing: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    source_plan = _load_plan(source_plan_path)
    if source_plan.get("schema_version") != (
            "sentientos.rootless_history_boundary_campaign_plan:v7"):
        raise ValueError("gpu_retry_requires_schema_v7_plan")
    if source_plan.get("task_family_id") != _WIDE_TASK_FAMILY:
        raise ValueError("gpu_retry_task_family_unsupported")
    verify_model_identity_recipe(source_plan)
    failure, failure_digest = _read_failure(failure_path)
    failure_evidence = _verified_unstarted_gpu_failure(
        plan=source_plan, failure=failure, failure_path=failure_path)
    _verify_failed_cycle_copy(source_plan=source_plan, failure=failure,
        run_root=failure_path.parent)
    if (not isinstance(campaign_id, str) or _CAMPAIGN_ID.fullmatch(campaign_id) is None
            or campaign_id == source_plan.get("campaign_id")):
        raise ValueError("gpu_retry_campaign_id_invalid")
    prior_ids = source_plan.get("ordered_cycle_ids")
    if (not isinstance(cycle_ids, list) or not isinstance(prior_ids, list)
            or len(cycle_ids) != len(prior_ids)
            or any(not isinstance(value, str) or _CYCLE_ID.fullmatch(value) is None
                for value in cycle_ids)
            or len(set(cycle_ids)) != len(cycle_ids)
            or set(cycle_ids) & set(prior_ids)):
        raise ValueError("gpu_retry_cycle_ids_invalid")
    _require_output_outside(output_plan, [history_root, failure_path.parent])
    _require_output_outside(output_record, [history_root, failure_path.parent])
    if output_plan.resolve(strict=False) == output_record.resolve(strict=False):
        raise ValueError("gpu_retry_output_paths_collide")
    if (not verify_existing and (output_plan.exists() or output_plan.is_symlink()
            or output_record.exists() or output_record.is_symlink())):
        raise ValueError("gpu_retry_output_already_exists")
    expected_boundary = source_plan.get("initial_history_boundary")
    if _history_boundary(history_root) != expected_boundary:
        raise ValueError("gpu_retry_initial_history_boundary_changed")
    recipe = source_plan.get("model_identity_recipe")
    if not isinstance(recipe, Mapping):
        raise ValueError("gpu_retry_identity_recipe_missing")
    replacement = create_plan(
        history_root=history_root,
        campaign_id=campaign_id,
        task_family_id=source_plan["task_family_id"],
        model_identity_digests=_plan_model_identity_digests(source_plan),
        ordered_cycle_ids=cycle_ids,
        task_generation_seeds=list(source_plan["ordered_task_generation_seeds"]),
        backend_seeds=list(source_plan["ordered_backend_seeds"]),
        model_identity_recipe=recipe)
    preserved = (
        replacement.get("initial_history_boundary") == expected_boundary
        and replacement.get("ordered_task_generation_seeds") ==
            source_plan.get("ordered_task_generation_seeds")
        and replacement.get("ordered_backend_seeds") ==
            source_plan.get("ordered_backend_seeds")
        and replacement.get("model_identity_recipe") == recipe
        and replacement.get("initial_runtime_admission_ledger") ==
            source_plan.get("initial_runtime_admission_ledger")
        and replacement.get("initial_cognition_recovery_state") ==
            source_plan.get("initial_cognition_recovery_state"))
    if not preserved:
        raise ValueError("gpu_retry_plan_preservation_check_failed")
    semantic = {
        "schema_version": RETRY_SCHEMA,
        "source_campaign_id": source_plan["campaign_id"],
        "source_plan_digest": source_plan["plan_digest"],
        "source_failure_artifact_sha256": failure_digest,
        "source_failure_cycle_id": failure_evidence["failed_cycle_id"],
        "source_failure_code": failure_evidence["failure_code"],
        "source_failure_stage": failure_evidence["failure_stage"],
        "gpu_memory_total_mib": failure_evidence["gpu_memory_total_mib"],
        "gpu_memory_free_mib": failure_evidence["gpu_memory_free_mib"],
        "gpu_utilization_percent": failure_evidence["gpu_utilization_percent"],
        "source_provenance_digest": failure_evidence["source_provenance_digest"],
        "retry_campaign_id": replacement["campaign_id"],
        "retry_plan_digest": replacement["plan_digest"],
        "retry_cycle_ids": list(replacement["ordered_cycle_ids"]),
        "task_seeds_preserved": list(replacement["ordered_task_generation_seeds"]),
        "backend_seeds_preserved": list(replacement["ordered_backend_seeds"]),
        "initial_history_boundary_digest": failure_evidence["history_boundary_digest"],
        "model_identity_recipe_digest": digest_payload(dict(recipe)),
        "inference_performed_for_source_failure": False,
        "learning_established": False,
        "authority": False,
    }
    record = {**semantic, "retry_record_digest": digest_payload(semantic)}
    if verify_existing:
        _verify_existing_artifact(replacement, output_plan)
        _verify_existing_artifact(record, output_record)
    else:
        persist_manifest(replacement, output_plan)
        persist_manifest(record, output_record)
    return replacement, record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-plan", type=Path, required=True)
    parser.add_argument("--failure", type=Path, required=True)
    parser.add_argument("--history-root", type=Path, required=True)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--cycle-id", action="append", required=True)
    parser.add_argument("--output-plan", type=Path, required=True)
    parser.add_argument("--output-record", type=Path, required=True)
    parser.add_argument("--verify-existing", action="store_true")
    args = parser.parse_args()
    plan, record = replan(source_plan_path=args.source_plan,
        failure_path=args.failure, history_root=args.history_root,
        campaign_id=args.campaign_id, cycle_ids=args.cycle_id,
        output_plan=args.output_plan, output_record=args.output_record,
        verify_existing=args.verify_existing)
    print(json.dumps({"status": "verified_existing" if args.verify_existing else "created",
        "campaign_id": plan["campaign_id"],
        "plan_digest": plan["plan_digest"],
        "retry_record_digest": record["retry_record_digest"],
        "task_seeds_preserved": record["task_seeds_preserved"],
        "backend_seeds_preserved": record["backend_seeds_preserved"],
        "inference_performed": False, "learning_established": False,
        "authority": False}, sort_keys=True))


if __name__ == "__main__":
    main()