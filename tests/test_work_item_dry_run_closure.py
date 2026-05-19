from __future__ import annotations

from sentientos.work_item_dry_run_closure import WorkItemDryRunClosureRequest, build_work_item_dry_run_closure_manifest


def _packet() -> dict[str, object]:
    return {
        "work_item_id": "wi_123",
        "source_kind": "manual_operator_task",
        "source_ref": "abc",
        "intake_status": "intake_accepted",
        "risk_class": "bounded_workspace_change",
        "declared_authority_requests": ["filesystem_write"],
        "agent_execution_is_requested": False,
        "agent_execution_is_permitted_by_this_packet": False,
    }


def _handoff() -> dict[str, object]:
    return {
        "work_item_id": "wi_123",
        "recommended_next_governed_surface": "eligible_for_workspace_change_set_admission",
        "workspace_change_set_proposal_candidate_id": "wsp_1",
        "workspace_change_set_proposal_candidate_digest": "d",
    }


def _dry(status: str = "dry_run_adapter_completed") -> dict[str, object]:
    return {
        "work_item_id": "wi_123",
        "adapter_status": status,
        "lifecycle_orchestration_invoked": True,
        "lifecycle_mode_used": "dry_run_full_lifecycle",
        "lifecycle_stop_reason": "lifecycle_completed_for_requested_mode",
        "artifact_records": [{"stage": "dry_run_adapter", "digest": "x"}],
    }


def test_closure_statuses():
    assert build_work_item_dry_run_closure_manifest(WorkItemDryRunClosureRequest(_packet(), _handoff(), _dry())).manifest.closure_status == "dry_run_closed_clean"
    warn = _packet(); warn["warning_codes"] = ["w1"]
    assert build_work_item_dry_run_closure_manifest(WorkItemDryRunClosureRequest(warn, _handoff(), _dry())).manifest.closure_status == "dry_run_closed_with_warnings"
    assert build_work_item_dry_run_closure_manifest(WorkItemDryRunClosureRequest(_packet(), _handoff(), _dry("dry_run_adapter_blocked"))).manifest.closure_status == "dry_run_closed_blocked"
    assert build_work_item_dry_run_closure_manifest(WorkItemDryRunClosureRequest(_packet(), _handoff(), _dry("dry_run_adapter_manual_review_required"))).manifest.closure_status == "dry_run_closed_manual_review"
    assert build_work_item_dry_run_closure_manifest(WorkItemDryRunClosureRequest(_packet(), _handoff(), _dry("dry_run_adapter_insufficient_metadata"))).manifest.closure_status == "dry_run_closed_insufficient_metadata"


def test_contradictions_and_evidence():
    bad = _dry(); bad["work_item_id"] = "wi_other"
    assert build_work_item_dry_run_closure_manifest(WorkItemDryRunClosureRequest(_packet(), _handoff(), bad)).manifest.closure_status == "dry_run_closed_contradicted"
    bad2 = _dry(); bad2["lifecycle_mode_used"] = "execute"
    assert build_work_item_dry_run_closure_manifest(WorkItemDryRunClosureRequest(_packet(), _handoff(), bad2)).manifest.closure_status == "dry_run_closed_contradicted"
    assert build_work_item_dry_run_closure_manifest(WorkItemDryRunClosureRequest(None, _handoff(), _dry())).manifest.closure_status == "dry_run_closure_insufficient_evidence"


def test_metadata_only_and_output(tmp_path):
    out = tmp_path / "closure.json"
    result = build_work_item_dry_run_closure_manifest(WorkItemDryRunClosureRequest(_packet(), _handoff(), _dry(), str(out)))
    assert result.manifest.metadata_only
    assert out.exists()
    assert "description" not in out.read_text(encoding="utf-8")
