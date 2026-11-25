"""Read-only audit of score-bound input-anchor coverage in a history store."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.resident_developmental_cognition import (  # noqa: E402
    MAX_HISTORY,
    audit_task_family_history_projection,
)
from sentientos.resident_developmental_writeback import (  # noqa: E402
    DevelopmentalHistoryStore,
)
from work.rootless_history_boundary_campaign import (  # noqa: E402
    _history_boundary,
    _load_plan,
)


def _canonical_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def create_audit(*, history_root: Path, plan_path: Path,
        reference_cycle_result_path: Path, output_path: Path) -> dict[str, Any]:
    plan = _load_plan(plan_path)
    cycle_result = json.loads(
        reference_cycle_result_path.read_text(encoding="utf-8"))
    if (not isinstance(plan, dict)
            or not isinstance(plan.get("initial_history_boundary"), dict)
            or not isinstance(plan.get("plan_digest"), str)
            or not isinstance(cycle_result, dict)
            or cycle_result.get("status") != "completed"
            or not isinstance(cycle_result.get("active_model_identity"), dict)):
        raise ValueError("anchor_audit_plan_or_reference_cycle_invalid")

    boundary = _history_boundary(history_root)
    planned_boundary = plan["initial_history_boundary"]
    if boundary.get("boundary_digest") != planned_boundary.get("boundary_digest"):
        raise ValueError("anchor_audit_history_boundary_changed")

    store = DevelopmentalHistoryStore(history_root)
    records = store.records()
    receipts = store.receipts()
    records_by_id = {record.record_id: record for record in records}
    receipts_by_record = {receipt.record_id: receipt for receipt in receipts}
    if (len(records_by_id) != len(records)
            or len(receipts_by_record) != len(receipts)
            or set(records_by_id) != set(receipts_by_record)):
        raise ValueError("anchor_audit_record_receipt_inventory_mismatch")
    for record_id, record in records_by_id.items():
        receipt = receipts_by_record[record_id]
        candidate_digest = record.candidate.get("candidate_digest")
        if (receipt.record_digest != record.record_digest
                or receipt.candidate_digest != candidate_digest
                or receipt.admission_id != record.admission_id
                or receipt.admission_binding_digest
                    != record.admission_binding_digest
                or receipt.storage_verified is not True):
            raise ValueError("anchor_audit_record_receipt_binding_mismatch")
    boundary_after = _history_boundary(history_root)
    if boundary_after.get("boundary_digest") != boundary.get("boundary_digest"):
        raise ValueError("anchor_audit_history_boundary_changed_during_read")

    family = plan.get("task_family_id")
    if not isinstance(family, str) or not family:
        raise ValueError("anchor_audit_task_family_invalid")
    family_candidates = []
    for record in records:
        candidate = record.candidate
        facts = candidate.get("selected_facts", ())
        if any(isinstance(fact, dict)
                and isinstance(fact.get("payload"), dict)
                and fact["payload"].get("objective_task_family") == family
                for fact in facts):
            family_candidates.append(candidate)
    if len(family_candidates) > MAX_HISTORY:
        raise ValueError("anchor_audit_family_history_exceeds_projection_bound")

    projection = audit_task_family_history_projection(
        family_candidates, task_family_id=family,
        target_model_identity=cycle_result["active_model_identity"])
    semantic: dict[str, Any] = {
        "schema_version": "sentientos.rootless_history_anchor_coverage_audit:v3",
        "campaign_id": plan.get("campaign_id"),
        "plan_digest": plan["plan_digest"],
        "planned_history_boundary_digest": planned_boundary["boundary_digest"],
        "observed_history_boundary_digest": boundary["boundary_digest"],
        "history_boundary_stable_across_read": True,
        "history_boundary_file_count": boundary["file_count"],
        "history_boundary_atomic_snapshot": boundary["atomic_snapshot"],
        "verified_record_count": len(records),
        "verified_receipt_count": len(receipts),
        "family_candidate_record_count": len(family_candidates),
        "reference_cycle_id": cycle_result.get("run_id"),
        "reference_model_identity_digest": _canonical_digest(
            cycle_result["active_model_identity"]),
        "reference_model_identity_scope": (
            "latest_completed_cycle_reference_not_future_seed_identity"),
        "projection_audit": projection,
        "audit_scope": "all_matching_persisted_history_candidates_not_prompt_selection",
        "prompt_delivery_assessed": False,
        "inference_performed": False,
        "learning_established": False,
        "current_truth": False,
        "authority": False,
    }
    artifact = {**semantic, "audit_digest": _canonical_digest(semantic)}
    output_path = output_path.expanduser()
    if any(path.is_symlink() for path in (output_path, *output_path.parents)):
        raise ValueError("anchor_audit_output_path_symlink")
    try:
        output_resolved = output_path.resolve(strict=False)
        history_resolved = history_root.resolve(strict=True)
        output_resolved.relative_to(history_resolved)
    except ValueError:
        pass
    else:
        raise ValueError("anchor_audit_output_inside_history_store")
    serialized = json.dumps(artifact, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False) + "\n"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        if output_path.read_text(encoding="utf-8") != serialized:
            raise ValueError("anchor_audit_output_immutable_mismatch")
    else:
        output_path.write_text(serialized, encoding="utf-8")
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-root", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--reference-cycle-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    artifact = create_audit(history_root=args.history_root,
        plan_path=args.plan,
        reference_cycle_result_path=args.reference_cycle_result,
        output_path=args.output)
    coverage = artifact["projection_audit"][
        "independent_input_anchor_coverage"]
    print(json.dumps({
        "artifact": str(args.output),
        "audit_digest": artifact["audit_digest"],
        "verified_records": artifact["verified_record_count"],
        "family_candidate_records": artifact["family_candidate_record_count"],
        "anchor_status": coverage["status"],
        "correct_source_runs": coverage["correct_source_run_count"],
        "distinct_correct_inputs": coverage["distinct_correct_input_count"],
        "prompt_delivery_assessed": False,
        "inference_performed": False,
        "learning_established": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
