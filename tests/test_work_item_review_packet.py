from __future__ import annotations

from pathlib import Path

from sentientos.work_item_review_packet import WorkItemDryRunReviewRequest, build_work_item_dry_run_review_packet


def _payload(**overrides: object) -> dict[str, object]:
    payload = {
        "source_kind": "generic_issue",
        "source_ref": "ISSUE-1",
        "title": "review",
        "description": "desc",
        "requested_outcome": "outcome",
        "declared_targets": ["sentientos/work_item_intake.py"],
        "change_intent": "metadata",
    }
    payload.update(overrides)
    return payload


def test_review_only_skips_dry_run(tmp_path: Path) -> None:
    res = build_work_item_dry_run_review_packet(WorkItemDryRunReviewRequest(work_item_payload=_payload(), workspace_root=str(tmp_path), mode="review_only"))
    assert res.packet.dry_run_adapter_status is None
    assert any(s.stage_name == "dry_run_adapter" and not s.attempted for s in res.stage_summaries)


def test_review_with_dry_run_runs_once_when_eligible(tmp_path: Path) -> None:
    res = build_work_item_dry_run_review_packet(WorkItemDryRunReviewRequest(work_item_payload=_payload(), workspace_root=str(tmp_path), mode="review_with_dry_run"))
    assert res.packet.dry_run_adapter_status is not None


def test_closure_mode_emits_closure_when_dry_run_exists(tmp_path: Path) -> None:
    res = build_work_item_dry_run_review_packet(WorkItemDryRunReviewRequest(work_item_payload=_payload(), workspace_root=str(tmp_path), mode="review_with_dry_run_closure"))
    assert res.packet.dry_run_closure_status is not None


def test_blocked_authority_propagates(tmp_path: Path) -> None:
    res = build_work_item_dry_run_review_packet(WorkItemDryRunReviewRequest(work_item_payload=_payload(declared_authority_requests=["network"]), workspace_root=str(tmp_path), mode="review_with_dry_run_closure"))
    assert res.packet.operator_action == "blocked_authority_request"
    assert res.packet.dry_run_adapter_status is None


def test_missing_metadata_maps_to_clarification_or_insufficient(tmp_path: Path) -> None:
    res = build_work_item_dry_run_review_packet(WorkItemDryRunReviewRequest(work_item_payload=_payload(title=""), workspace_root=str(tmp_path), mode="review_only"))
    assert res.packet.operator_action in {"request_clarification", "insufficient_evidence"}
