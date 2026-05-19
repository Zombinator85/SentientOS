from __future__ import annotations

from pathlib import Path

from sentientos.work_item_lifecycle_dry_run_adapter import WorkItemLifecycleDryRunAdapterRequest, run_work_item_lifecycle_dry_run_adapter
from sentientos.work_item_intake import normalize_work_item_intake
from sentientos.work_item_lifecycle_handoff import WorkItemLifecycleHandoffRequest, plan_work_item_lifecycle_handoff


def _packet(**overrides: object) -> dict[str, object]:
    payload = {
        "source_kind": "generic_issue",
        "title": "dry run adapter",
        "description": "desc",
        "requested_outcome": "outcome",
        "declared_targets": ["sentientos/work_item_intake.py"],
        "change_intent": "metadata",
    }
    payload.update(overrides)
    packet, _ = normalize_work_item_intake(payload, derive_workspace_proposal=True)
    return packet.__dict__


def _handoff(packet: dict[str, object], **overrides: object) -> dict[str, object]:
    plan = plan_work_item_lifecycle_handoff(WorkItemLifecycleHandoffRequest(packet=packet, emit_lifecycle_candidate=True))
    out = plan.__dict__.copy()
    out.update(overrides)
    return out


def test_eligible_invokes_dry_run_mode(monkeypatch, tmp_path: Path) -> None:
    packet = _packet()
    handoff = _handoff(packet)
    called: dict[str, object] = {}

    class _Result:
        stop_reason = "lifecycle_completed_for_requested_mode"
        admission_status = "workspace_change_set_admission_accepted"
        preflight_status = "workspace_change_set_preflight_passed"
        transaction_plan_status = "workspace_change_set_transaction_plan_ready"
        transaction_plan_ready = True

    class _Wing:
        result = _Result()

    def _fake(proposal, *, mode, workspace_root, **kwargs):
        called["mode"] = mode
        called["workspace_root"] = workspace_root
        return _Wing()

    monkeypatch.setattr("sentientos.work_item_lifecycle_dry_run_adapter.run_workspace_change_set_lifecycle_orchestration", _fake)
    res = run_work_item_lifecycle_dry_run_adapter(WorkItemLifecycleDryRunAdapterRequest(packet=packet, handoff_plan=handoff, workspace_root=str(tmp_path), request_dry_run=True))
    assert res.adapter_status == "dry_run_adapter_completed"
    assert res.lifecycle_orchestration_invoked is True
    assert called["mode"] == "dry_run_full_lifecycle"
    assert res.transaction_plan_ready is True


def test_blocked_authority_does_not_invoke(monkeypatch, tmp_path: Path) -> None:
    packet = _packet(declared_authority_requests=["network"])
    handoff = _handoff(packet)
    monkeypatch.setattr("sentientos.work_item_lifecycle_dry_run_adapter.run_workspace_change_set_lifecycle_orchestration", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not invoke")))
    res = run_work_item_lifecycle_dry_run_adapter(WorkItemLifecycleDryRunAdapterRequest(packet=packet, handoff_plan=handoff, workspace_root=str(tmp_path), request_dry_run=True))
    assert res.lifecycle_orchestration_invoked is False
    assert res.adapter_status == "dry_run_adapter_blocked"


def test_manual_review_surface_does_not_invoke(tmp_path: Path) -> None:
    packet = _packet()
    handoff = _handoff(packet, recommended_next_governed_surface="needs_manual_review")
    res = run_work_item_lifecycle_dry_run_adapter(WorkItemLifecycleDryRunAdapterRequest(packet=packet, handoff_plan=handoff, workspace_root=str(tmp_path), request_dry_run=True))
    assert res.adapter_status == "dry_run_adapter_manual_review_required"
    assert res.lifecycle_orchestration_invoked is False


def test_missing_proposal_metadata_insufficient(tmp_path: Path) -> None:
    packet = _packet()
    packet.pop("workspace_change_set_proposal_metadata", None)
    handoff = _handoff(packet)
    res = run_work_item_lifecycle_dry_run_adapter(WorkItemLifecycleDryRunAdapterRequest(packet=packet, handoff_plan=handoff, workspace_root=str(tmp_path), request_dry_run=True))
    assert res.adapter_status == "dry_run_adapter_insufficient_metadata"


def test_cli_artifact_only_write(tmp_path: Path) -> None:
    packet = _packet()
    handoff = _handoff(packet)
    out = tmp_path / "out.json"
    res = run_work_item_lifecycle_dry_run_adapter(WorkItemLifecycleDryRunAdapterRequest(packet=packet, handoff_plan=handoff, workspace_root=str(tmp_path), request_dry_run=False, artifact_output_path=str(out)))
    assert out.exists()
    assert res.adapter_status != "dry_run_adapter_completed"
