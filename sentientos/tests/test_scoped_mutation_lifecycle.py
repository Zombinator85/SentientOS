from __future__ import annotations

import json
from pathlib import Path

from sentientos.scoped_lifecycle_diagnostic import build_scoped_lifecycle_diagnostic
from sentientos.scoped_mutation_lifecycle import resolve_scoped_mutation_lifecycle


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def test_resolver_reports_canonical_success_for_manifest(tmp_path: Path) -> None:
    correlation_id = "cid-success"
    _write_jsonl(
        tmp_path / "pulse/forge_events.jsonl",
        [
            {
                "event": "constitutional_mutation_router_execution",
                "typed_action_id": "sentientos.manifest.generate",
                "correlation_id": correlation_id,
                "execution_status": "succeeded",
                "final_disposition": "allow",
                "executed": True,
                "canonical_handler": "scripts.generate_immutable_manifest.generate_manifest",
            }
        ],
    )
    _write_jsonl(
        tmp_path / "glow/control_plane/kernel_decisions.jsonl",
        [
            {
                "event_type": "control_plane_decision",
                "correlation_id": correlation_id,
                "admission_decision_ref": f"kernel_decision:{correlation_id}",
                "final_disposition": "allow",
            }
        ],
    )
    (tmp_path / "vow").mkdir(parents=True, exist_ok=True)
    (tmp_path / "vow/immutable_manifest.json").write_text(
        json.dumps({"admission": {"correlation_id": correlation_id, "typed_action_id": "sentientos.manifest.generate"}}),
        encoding="utf-8",
    )

    resolved = resolve_scoped_mutation_lifecycle(
        tmp_path,
        action_id="sentientos.manifest.generate",
        correlation_id=correlation_id,
    )

    assert resolved["outcome_class"] == "success", json.dumps(resolved, indent=2, sort_keys=True)
    assert resolved["kernel_admission_disposition"] == "allow"
    assert resolved["canonical_router_execution_status"] == "succeeded"
    assert resolved["side_effect_state"] == "present"
    assert resolved["proof_linkage_state"] == "present"


def test_resolver_reports_canonical_denial_for_hold(tmp_path: Path) -> None:
    correlation_id = "cid-denied"
    _write_jsonl(
        tmp_path / "pulse/forge_events.jsonl",
        [
            {
                "event": "constitutional_mutation_router_execution",
                "typed_action_id": "sentientos.merge_train.hold",
                "correlation_id": correlation_id,
                "execution_status": "denied",
                "final_disposition": "deny",
                "executed": False,
                "canonical_handler": "sentientos.forge_merge_train.ForgeMergeTrain._apply_hold_transition",
            }
        ],
    )
    _write_jsonl(
        tmp_path / "glow/control_plane/kernel_decisions.jsonl",
        [
            {
                "event_type": "control_plane_decision",
                "correlation_id": correlation_id,
                "admission_decision_ref": f"kernel_decision:{correlation_id}",
                "final_disposition": "deny",
            }
        ],
    )
    _write_jsonl(tmp_path / "pulse/forge_train_events.jsonl", [])

    resolved = resolve_scoped_mutation_lifecycle(
        tmp_path,
        action_id="sentientos.merge_train.hold",
        correlation_id=correlation_id,
    )

    assert resolved["outcome_class"] == "denied", json.dumps(resolved, indent=2, sort_keys=True)
    assert resolved["side_effect_state"] == "absent"


def test_resolver_reports_canonical_failed_after_admission(tmp_path: Path) -> None:
    correlation_id = "cid-failed"
    _write_jsonl(
        tmp_path / "pulse/forge_events.jsonl",
        [
            {
                "event": "constitutional_mutation_router_execution",
                "typed_action_id": "sentientos.manifest.generate",
                "correlation_id": correlation_id,
                "execution_status": "failed",
                "final_disposition": "allow",
                "executed": True,
                "partial_side_effect_state": "unknown_partial_side_effects_possible",
                "failure": {"exception_type": "RuntimeError", "message": "boom"},
                "canonical_handler": "scripts.generate_immutable_manifest.generate_manifest",
            }
        ],
    )
    _write_jsonl(
        tmp_path / "glow/control_plane/kernel_decisions.jsonl",
        [
            {
                "event_type": "control_plane_decision",
                "correlation_id": correlation_id,
                "admission_decision_ref": f"kernel_decision:{correlation_id}",
                "final_disposition": "allow",
            }
        ],
    )

    resolved = resolve_scoped_mutation_lifecycle(
        tmp_path,
        action_id="sentientos.manifest.generate",
        correlation_id=correlation_id,
    )

    assert resolved["outcome_class"] == "failed_after_admission", json.dumps(resolved, indent=2, sort_keys=True)


def test_resolver_flags_fragmented_when_kernel_or_router_link_missing(tmp_path: Path) -> None:
    correlation_id = "cid-fragmented"
    _write_jsonl(
        tmp_path / "pulse/forge_events.jsonl",
        [
            {
                "event": "constitutional_mutation_router_execution",
                "typed_action_id": "sentientos.manifest.generate",
                "correlation_id": correlation_id,
                "execution_status": "succeeded",
                "final_disposition": "allow",
                "executed": True,
                "canonical_handler": "scripts.generate_immutable_manifest.generate_manifest",
            }
        ],
    )

    resolved = resolve_scoped_mutation_lifecycle(
        tmp_path,
        action_id="sentientos.manifest.generate",
        correlation_id=correlation_id,
    )

    assert resolved["outcome_class"] == "fragmented_unresolved", json.dumps(resolved, indent=2, sort_keys=True)
    assert any(item["kind"] == "kernel_decision_missing" for item in resolved["findings"])


def test_non_canonical_direct_side_effect_cannot_fabricate_clean_lifecycle(tmp_path: Path) -> None:
    correlation_id = "cid-fake"
    _write_jsonl(
        tmp_path / "pulse/forge_events.jsonl",
        [
            {
                "event": "constitutional_mutation_router_execution",
                "typed_action_id": "sentientos.merge_train.hold",
                "correlation_id": correlation_id,
                "execution_status": "denied",
                "final_disposition": "deny",
                "executed": False,
                "canonical_handler": "sentientos.forge_merge_train.ForgeMergeTrain._apply_hold_transition",
            }
        ],
    )
    _write_jsonl(
        tmp_path / "glow/control_plane/kernel_decisions.jsonl",
        [
            {
                "event_type": "control_plane_decision",
                "correlation_id": correlation_id,
                "admission_decision_ref": f"kernel_decision:{correlation_id}",
                "final_disposition": "deny",
            }
        ],
    )
    _write_jsonl(
        tmp_path / "pulse/forge_train_events.jsonl",
        [{"event": "train_held", "correlation_id": correlation_id}],
    )

    resolved = resolve_scoped_mutation_lifecycle(
        tmp_path,
        action_id="sentientos.merge_train.hold",
        correlation_id=correlation_id,
    )

    assert resolved["outcome_class"] == "fragmented_unresolved", json.dumps(resolved, indent=2, sort_keys=True)
    assert any(item["kind"] == "denied_side_effect_leak" for item in resolved["findings"])


def test_diagnostic_consumer_exposes_resolved_lifecycle_rows(tmp_path: Path) -> None:
    correlation_id = "cid-diag"
    _write_jsonl(
        tmp_path / "pulse/forge_events.jsonl",
        [
            {
                "event": "constitutional_mutation_router_execution",
                "typed_action_id": "sentientos.manifest.generate",
                "correlation_id": correlation_id,
                "execution_status": "failed",
                "final_disposition": "allow",
                "executed": True,
                "partial_side_effect_state": "unknown_partial_side_effects_possible",
                "failure": {"exception_type": "RuntimeError", "message": "simulated"},
                "canonical_handler": "scripts.generate_immutable_manifest.generate_manifest",
            }
        ],
    )
    _write_jsonl(
        tmp_path / "glow/control_plane/kernel_decisions.jsonl",
        [
            {
                "event_type": "control_plane_decision",
                "correlation_id": correlation_id,
                "admission_decision_ref": f"kernel_decision:{correlation_id}",
                "final_disposition": "allow",
            }
        ],
    )

    diagnostic = build_scoped_lifecycle_diagnostic(tmp_path)
    row = next(item for item in diagnostic["actions"] if item["typed_action_identity"] == "sentientos.manifest.generate")
    assert row["outcome_class"] == "failed_after_admission", json.dumps(row, indent=2, sort_keys=True)
