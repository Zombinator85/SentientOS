from __future__ import annotations

from sentientos.work_item_intake import normalize_work_item_intake
from sentientos.work_item_lifecycle_handoff import WorkItemLifecycleHandoffRequest, plan_work_item_lifecycle_handoff


def _packet(**overrides: object):
    payload = {
        "source_kind": "generic_issue",
        "source_ref": "GH-1",
        "title": "Docs tidy",
        "description": "Clarify docs",
        "requested_outcome": "Update docs note",
        "acceptance_criteria": ["note updated"],
    } | overrides
    p, _ = normalize_work_item_intake(payload, derive_workspace_proposal=True)
    return p.__dict__


def test_info_packet_no_action() -> None:
    plan = plan_work_item_lifecycle_handoff(WorkItemLifecycleHandoffRequest(packet=_packet()))
    assert plan.recommended_next_governed_surface == "no_action_required"


def test_vague_packet_insufficient_metadata() -> None:
    p, _ = normalize_work_item_intake({"source_kind": "generic_issue", "title": "x"})
    plan = plan_work_item_lifecycle_handoff(WorkItemLifecycleHandoffRequest(packet=p.__dict__))
    assert plan.recommended_next_governed_surface in {"insufficient_metadata", "needs_operator_clarification"}


def test_workspace_proposal_eligible_for_admission() -> None:
    packet = _packet(declared_targets=["docs/architecture/task_work_item_intake_adapter_wing.md"], change_intent="metadata-only")
    plan = plan_work_item_lifecycle_handoff(WorkItemLifecycleHandoffRequest(packet=packet))
    assert plan.recommended_next_governed_surface == "eligible_for_workspace_change_set_admission"


def test_emit_lifecycle_candidate_is_metadata_only() -> None:
    packet = _packet(declared_targets=["sentientos/work_item_intake.py"], change_intent="x")
    plan = plan_work_item_lifecycle_handoff(WorkItemLifecycleHandoffRequest(packet=packet, emit_lifecycle_candidate=True))
    assert plan.lifecycle_orchestration_request_candidate_metadata is not None
    assert plan.lifecycle_orchestration_request_candidate_metadata["orchestration_not_invoked"] is True


def test_blocked_authorities_route_blocked() -> None:
    packet = _packet(declared_authority_requests=["network", "provider", "prompt_export", "shell", "subprocess"])
    plan = plan_work_item_lifecycle_handoff(WorkItemLifecycleHandoffRequest(packet=packet))
    assert plan.recommended_next_governed_surface in {"blocked_authority_request", "blocked_external_integration_request"}
