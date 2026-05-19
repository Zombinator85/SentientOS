from __future__ import annotations

from sentientos.work_item_intake import normalize_work_item_intake


def _base_payload() -> dict[str, object]:
    return {
        "source_kind": "generic_issue",
        "source_ref": "ISSUE-1",
        "title": "Add intake adapter",
        "description": "Normalize external task metadata into local packet",
        "requested_outcome": "Produce deterministic packet",
        "acceptance_criteria": ["packet generated"],
    }


def test_generic_issue_normalizes() -> None:
    packet, decision = normalize_work_item_intake(_base_payload())
    assert packet.source_kind == "generic_issue"
    assert packet.source_ref == "ISSUE-1"
    assert decision.intake_status == "intake_accepted"


def test_manual_operator_and_metadata_source_kinds_accepted() -> None:
    for kind in ("manual_operator_task", "github_issue_metadata", "github_pr_metadata", "linear_issue_metadata", "codex_task_metadata"):
        payload = _base_payload() | {"source_kind": kind}
        packet, _ = normalize_work_item_intake(payload)
        assert packet.source_kind == kind
        assert packet.intake_status in {"intake_accepted", "intake_accepted_with_warnings"}


def test_missing_required_fields_is_insufficient() -> None:
    packet, _ = normalize_work_item_intake({"source_kind": "generic_issue", "title": "x"})
    assert packet.intake_status == "intake_insufficient_metadata"
    assert "missing_description" in packet.blocker_codes


def test_vague_task_has_no_workspace_proposal() -> None:
    payload = _base_payload() | {"description": "help", "acceptance_criteria": []}
    packet, _ = normalize_work_item_intake(payload, derive_workspace_proposal=True)
    assert packet.workspace_change_set_proposal_metadata is None


def test_explicit_targets_can_derive_metadata_only_workspace_proposal() -> None:
    payload = _base_payload() | {"declared_targets": ["sentientos/work_item_intake.py"], "change_intent": "add metadata model"}
    packet, _ = normalize_work_item_intake(payload, derive_workspace_proposal=True)
    assert packet.workspace_change_set_proposal_metadata is not None
    assert packet.workspace_change_set_proposal_metadata["admission_not_invoked"] is True
    assert packet.workspace_change_set_admission_may_be_attempted is True


def test_block_requested_external_authorities() -> None:
    payload = _base_payload() | {"declared_authority_requests": ["network", "provider", "prompt_export", "shell", "subprocess"]}
    packet, _ = normalize_work_item_intake(payload)
    assert packet.intake_status == "intake_blocked"
    assert packet.risk_class == "external_integration_requested"


def test_detect_mutation_and_agent_scheduling_requests_without_performing() -> None:
    payload = _base_payload() | {"declared_authority_requests": ["issue_mutation", "pr_creation", "branch_creation", "agent_execution", "scheduling"]}
    packet, _ = normalize_work_item_intake(payload)
    assert packet.agent_execution_is_requested is True
    assert packet.agent_execution_is_permitted_by_this_packet is False
    assert packet.intake_status == "intake_blocked"


def test_packet_summary_omits_sensitive_payload_fields() -> None:
    payload = _base_payload() | {
        "secrets": {"token": "abc"},
        "prompt_text": "hidden prompt",
        "runtime_handle": "pid-1",
    }
    packet, _ = normalize_work_item_intake(payload)
    serialized = packet.__dict__
    assert "secrets" not in serialized
    assert "prompt_text" not in serialized
    assert "runtime_handle" not in serialized
