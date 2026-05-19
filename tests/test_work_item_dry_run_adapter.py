from __future__ import annotations

from pathlib import Path

import pytest

from sentientos.work_item_intake import normalize_work_item_intake
from sentientos.work_item_lifecycle_dry_run_adapter import WorkItemLifecycleDryRunAdapterRequest, run_work_item_lifecycle_dry_run_adapter
from sentientos.work_item_lifecycle_handoff import WorkItemLifecycleHandoffRequest, plan_work_item_lifecycle_handoff



def _packet(**overrides: object) -> dict[str, object]:
    payload = {
        "source_kind": "generic_issue",
        "title": "dry run adapter",
        "description": "desc",
        "requested_outcome": "outcome",
        "declared_targets": ["sentientos/work_item_intake.py", "tests/*.py"],
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


class _Result:
    stop_reason = "lifecycle_completed_for_requested_mode"
    admission_status = "workspace_change_set_admission_accepted"
    preflight_status = "workspace_change_set_preflight_passed"
    transaction_plan_status = "workspace_change_set_transaction_plan_ready"
    transaction_plan_ready = True


class _Wing:
    result = _Result()


@pytest.mark.parametrize(
    "candidate_overrides",
    [
        {},
        {"orchestration_not_invoked": False},
        {"lifecycle_mode": "admit_preflight_execute_verify_close"},
        {"execution_permitted": True},
        {"agent_execution_permitted": True},
        {"evidence_source": "real_execution"},
        {"declared_authority_requests": ["network", "provider", "shell", "prompt_export", "subprocess"]},
        {"declared_authority_requests": ["pr_creation", "branch_creation", "issue_mutation"]},
        {"declared_authority_requests": ["scheduler", "live_tracker"]},
    ],
)
def test_unsafe_lifecycle_candidates_never_invoke(monkeypatch, tmp_path: Path, candidate_overrides: dict[str, object]) -> None:
    packet = _packet()
    handoff = _handoff(packet)
    candidate = dict(handoff.get("lifecycle_orchestration_request_candidate_metadata") or {})
    for key, value in candidate_overrides.items():
        if key == "declared_authority_requests":
            packet["declared_authority_requests"] = value
        else:
            candidate[key] = value
    if "orchestration_not_invoked" not in candidate and candidate_overrides == {}:
        candidate.pop("orchestration_not_invoked", None)
    handoff["lifecycle_orchestration_request_candidate_metadata"] = candidate

    monkeypatch.setattr(
        "sentientos.work_item_lifecycle_dry_run_adapter.run_workspace_change_set_lifecycle_orchestration",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("orchestrator should not be called")),
    )
    res = run_work_item_lifecycle_dry_run_adapter(
        WorkItemLifecycleDryRunAdapterRequest(packet=packet, handoff_plan=handoff, workspace_root=str(tmp_path), request_dry_run=True)
    )
    assert res.lifecycle_orchestration_invoked is False
    assert res.adapter_status in {"dry_run_adapter_blocked", "dry_run_adapter_contradicted"}


@pytest.mark.parametrize(
    "packet_overrides,handoff_overrides,expected_status",
    [
        ({"intake_status": "intake_blocked"}, {}, "dry_run_adapter_blocked"),
        ({"intake_status": "intake_contradicted"}, {}, "dry_run_adapter_blocked"),
        ({"intake_status": "intake_insufficient_metadata"}, {}, "dry_run_adapter_blocked"),
        ({}, {"recommended_next_governed_surface": "needs_manual_review"}, "dry_run_adapter_manual_review_required"),
        ({}, {"recommended_next_governed_surface": "needs_operator_clarification"}, "dry_run_adapter_manual_review_required"),
        ({}, {"recommended_next_governed_surface": "blocked_authority_request"}, "dry_run_adapter_manual_review_required"),
        ({}, {"recommended_next_governed_surface": "blocked_external_integration_request"}, "dry_run_adapter_manual_review_required"),
        ({}, {"recommended_next_governed_surface": "blocked_agent_execution_request"}, "dry_run_adapter_manual_review_required"),
        ({"agent_execution_is_requested": True}, {}, "dry_run_adapter_blocked"),
        ({"agent_execution_is_permitted_by_this_packet": True}, {}, "dry_run_adapter_blocked"),
    ],
)
def test_blocked_no_invoke_variants(monkeypatch, tmp_path: Path, packet_overrides: dict[str, object], handoff_overrides: dict[str, object], expected_status: str) -> None:
    packet = _packet(**packet_overrides)
    handoff = _handoff(packet, **handoff_overrides)
    monkeypatch.setattr(
        "sentientos.work_item_lifecycle_dry_run_adapter.run_workspace_change_set_lifecycle_orchestration",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("orchestrator should not be called")),
    )
    res = run_work_item_lifecycle_dry_run_adapter(
        WorkItemLifecycleDryRunAdapterRequest(packet=packet, handoff_plan=handoff, workspace_root=str(tmp_path), request_dry_run=True)
    )
    assert res.adapter_status == expected_status
    assert res.lifecycle_orchestration_invoked is False


def test_missing_metadata_and_dry_run_not_explicit_do_not_invoke(monkeypatch, tmp_path: Path) -> None:
    packet = _packet()
    packet.pop("workspace_change_set_proposal_metadata", None)
    handoff = _handoff(packet)
    monkeypatch.setattr(
        "sentientos.work_item_lifecycle_dry_run_adapter.run_workspace_change_set_lifecycle_orchestration",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("orchestrator should not be called")),
    )
    res_missing = run_work_item_lifecycle_dry_run_adapter(
        WorkItemLifecycleDryRunAdapterRequest(packet=packet, handoff_plan=handoff, workspace_root=str(tmp_path), request_dry_run=True)
    )
    assert res_missing.adapter_status == "dry_run_adapter_insufficient_metadata"
    packet2 = _packet()
    handoff2 = _handoff(packet2)
    res_not_explicit = run_work_item_lifecycle_dry_run_adapter(
        WorkItemLifecycleDryRunAdapterRequest(packet=packet2, handoff_plan=handoff2, workspace_root=str(tmp_path), request_dry_run=False)
    )
    assert res_not_explicit.adapter_status == "dry_run_adapter_manual_review_required"
    assert res_not_explicit.lifecycle_orchestration_invoked is False


def test_orchestrator_called_once_in_dry_run_mode_only(monkeypatch, tmp_path: Path) -> None:
    packet = _packet()
    handoff = _handoff(packet)
    calls: list[tuple[str, str | None]] = []

    def _fake(proposal, *, mode, workspace_root, **kwargs):
        calls.append((mode, workspace_root))
        return _Wing()

    monkeypatch.setattr("sentientos.work_item_lifecycle_dry_run_adapter.run_workspace_change_set_lifecycle_orchestration", _fake)
    res = run_work_item_lifecycle_dry_run_adapter(
        WorkItemLifecycleDryRunAdapterRequest(packet=packet, handoff_plan=handoff, workspace_root=str(tmp_path), request_dry_run=True)
    )
    assert res.adapter_status == "dry_run_adapter_completed"
    assert calls == [("dry_run_full_lifecycle", str(tmp_path))]


def test_adapter_never_calls_stage_helpers_or_workspace_effect_helpers(monkeypatch, tmp_path: Path) -> None:
    packet = _packet()
    handoff = _handoff(packet, recommended_next_governed_surface="needs_manual_review")

    forbidden_paths = [
        "sentientos.workspace_change_set_execution.apply_workspace_change_target_effect",
        "sentientos.workspace_change_set_execution.rollback_workspace_change_target_effect",
        "sentientos.workspace_change_set_admission.run_workspace_change_set_admission_wing",
        "sentientos.workspace_change_set_preflight.run_workspace_change_set_preflight_wing",
        "sentientos.workspace_change_set_execution.run_workspace_change_set_execution_wing",
        "sentientos.workspace_change_set_execution_verification.verify_workspace_change_set_execution",
        "sentientos.workspace_change_set_lifecycle_closure.build_workspace_change_set_lifecycle_closure_manifest",
    ]
    for dotted in forbidden_paths:
        monkeypatch.setattr(dotted, lambda *a, **k: (_ for _ in ()).throw(AssertionError(f"forbidden helper called: {dotted}")))
    monkeypatch.setattr(
        "sentientos.work_item_lifecycle_dry_run_adapter.run_workspace_change_set_lifecycle_orchestration",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("orchestrator should not be called in blocked flow")),
    )

    res = run_work_item_lifecycle_dry_run_adapter(
        WorkItemLifecycleDryRunAdapterRequest(packet=packet, handoff_plan=handoff, workspace_root=str(tmp_path), request_dry_run=True)
    )
    assert res.adapter_status == "dry_run_adapter_manual_review_required"


def test_adapter_does_not_read_targets_and_writes_only_artifact(tmp_path: Path) -> None:
    packet = _packet(declared_targets=["forbidden/secret.txt", "**/*.py"])
    handoff = _handoff(packet, recommended_next_governed_surface="needs_manual_review")
    target = tmp_path / "forbidden" / "secret.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("do-not-read", encoding="utf-8")
    output = tmp_path / "adapter.json"

    res = run_work_item_lifecycle_dry_run_adapter(
        WorkItemLifecycleDryRunAdapterRequest(
            packet=packet,
            handoff_plan=handoff,
            workspace_root=str(tmp_path),
            request_dry_run=True,
            artifact_output_path=str(output),
        )
    )

    assert res.lifecycle_orchestration_invoked is False
    assert output.exists()
    assert output.read_text(encoding="utf-8")
    assert target.read_text(encoding="utf-8") == "do-not-read"
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()) == ["adapter.json", "forbidden/secret.txt"]
