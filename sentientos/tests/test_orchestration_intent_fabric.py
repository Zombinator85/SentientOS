from __future__ import annotations

import hashlib
from importlib import reload
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from copy import deepcopy

import control_plane
import pytest
import task_admission
import task_executor
from sentientos.delegated_judgment_fabric import synthesize_delegated_judgment
from sentientos import orchestration_internal_adapters
from sentientos.orchestration_intent_fabric import (
    admit_orchestration_intent,
    append_handoff_packet_ledger,
    append_next_move_proposal_ledger,
    append_operator_action_brief_ledger,
    append_orchestration_intent_ledger,
    build_split_closure_map,
    ingest_external_fulfillment_receipt,
    ingest_operator_resolution_receipt,
    build_handoff_execution_gap_map,
    derive_orchestration_attention_recommendation,
    derive_proposal_packet_continuity_review,
    derive_external_feedback_gap_map,
    derive_operator_adjusted_next_move_proposal_visibility,
    derive_operator_adjusted_next_venue_recommendation,
    derive_repacketization_gap_map,
    derive_operator_resolution_feedback_gap_map,
    derive_operator_resolution_influence,
    derive_packetization_gate,
    derive_next_venue_recommendation,
    derive_next_move_proposal_review,
    derive_orchestration_outcome_review,
    derive_delegated_operation_readiness_verdict,
    derive_orchestration_trust_confidence_posture,
    derive_unified_result_quality_review,
    derive_orchestration_venue_mix_review,
    executable_handoff_map,
    synthesize_operator_action_brief,
    resolve_orchestration_result,
    resolve_unified_orchestration_result,
    resolve_unified_orchestration_result_surface,
    resolve_handoff_packet_fulfillment_lifecycle,
    resolve_handoff_packet_history_for_proposal,
    resolve_latest_operator_resolution_for_proposal,
    resolve_active_handoff_packet_candidate,
    resolve_current_orchestration_state,
    resolve_current_resumed_operation_readiness_verdict,
    resolve_current_orchestration_pressure_signal,
    resolve_current_orchestration_wake_readiness_detector,
    resolve_current_orchestration_handoff_packet_brief,
    resolve_current_orchestration_resolution_path_brief,
    resolve_current_orchestration_closure_brief,
    resolve_current_orchestration_coherence_brief,
    resolve_current_orchestration_digest,
    resolve_current_orchestration_export_packet,
    resolve_current_orchestration_transition_brief,
    resolve_current_operator_facing_orchestration_brief,
    resolve_current_orchestration_resumption_candidate,
    resolve_current_orchestration_watchpoint_brief,
    resolve_current_orchestration_watchpoint,
    resolve_re_evaluation_trigger_recommendation,
    resolve_watchpoint_satisfaction,
    resolve_operator_action_brief_lifecycle,
    synthesize_handoff_packet,
    synthesize_operator_refreshed_handoff_packet,
    synthesize_next_move_proposal,
    synthesize_orchestration_intent,
)
from sentientos.scoped_lifecycle_diagnostic import build_scoped_lifecycle_diagnostic


def _base_evidence() -> dict[str, object]:
    return {
        "contract_status_present": True,
        "contract_drifted_domains": 0,
        "contract_baseline_missing_domains": 0,
        "governance_ambiguity_signal": False,
        "slice_health_status": "healthy",
        "slice_stability_classification": "stable",
        "slice_review_classification": "clean_recent_history",
        "records_considered": 6,
        "admission_denied_ratio": 0.0,
        "admission_sample_count": 8,
        "executor_failure_ratio": 0.0,
        "executor_sample_count": 6,
        "adapter_count": 1,
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _proposal_row(
    *,
    relation_posture: str,
    venue: str,
    executability: str,
    requires_operator: bool = False,
) -> dict[str, object]:
    return {
        "schema_version": "orchestration_next_move_proposal.v1",
        "proposal_id": f"proposal-{relation_posture}-{venue}-{executability}",
        "relation_posture": relation_posture,
        "proposed_next_action": {"proposed_venue": venue, "proposed_posture": "hold"},
        "executability_classification": executability,
        "operator_escalation_requirement_state": {"requires_operator_or_escalation": requires_operator},
        "proposal_only": True,
        "diagnostic_only": True,
        "non_authoritative": True,
        "decision_power": "none",
    }


def _packet_row(
    *,
    proposal_id: str,
    packet_id: str,
    status: str = "ready_for_external_trigger",
    venue: str = "codex_implementation",
    gate_outcome: str = "packetization_allowed",
    supersedes: str | None = None,
    refresh_reason: str | None = None,
    current_candidate: bool = True,
    repacketized: bool = False,
) -> dict[str, object]:
    return {
        "schema_version": "orchestration_handoff_packet.v1",
        "handoff_packet_id": packet_id,
        "recorded_at": "2026-04-12T00:00:00Z",
        "packet_status": status,
        "target_venue": venue,
        "source_next_move_proposal_ref": {"proposal_id": proposal_id},
        "source_packetization_gate_ref": {"packetization_outcome": gate_outcome},
        "packet_lineage": {
            "supersedes_handoff_packet_id": supersedes,
            "refresh_reason": refresh_reason,
            "source_operator_resolution_receipt_id": None,
            "current_packet_candidate": current_candidate,
        },
        "repacketized_from_operator_feedback": repacketized,
        "non_authoritative": True,
        "decision_power": "none",
        "diagnostic_only": True,
    }


def _external_handoff_packet(
    delegated: dict[str, object],
    *,
    venue_recommendation: str,
    outcome_classification: str,
    venue_mix_classification: str,
    attention_signal: str,
) -> dict[str, object]:
    next_venue = derive_next_venue_recommendation(
        delegated,
        {"review_classification": outcome_classification, "records_considered": 4, "condition_flags": {}},
        {"review_classification": venue_mix_classification, "records_considered": 4},
        {"operator_attention_recommendation": attention_signal},
    )
    next_venue["next_venue_recommendation"] = venue_recommendation
    if venue_recommendation in {"prefer_codex_implementation", "prefer_deep_research_audit"}:
        next_venue["relation_to_delegated_judgment"] = "affirming"
    proposal = synthesize_next_move_proposal(
        delegated,
        next_venue,
        {"review_classification": outcome_classification, "records_considered": 4},
        {"review_classification": venue_mix_classification, "records_considered": 4},
        {"operator_attention_recommendation": attention_signal},
        created_at="2026-04-12T00:00:00Z",
    )
    return synthesize_handoff_packet(proposal, delegated, created_at="2026-04-12T00:00:00Z")


def _operator_brief_for_receipt_flow() -> dict[str, object]:
    proposal = {
        "proposal_id": "proposal-operator-receipt-flow",
        "relation_posture": "escalating",
        "proposed_next_action": {"proposed_venue": "codex_implementation", "proposed_posture": "escalate"},
        "executability_classification": "stageable_external_work_order",
        "operator_escalation_requirement_state": {
            "requires_operator_or_escalation": True,
            "attention_signal": "inspect_handoff_blocks",
            "escalation_classification": "escalate_for_operator_priority",
        },
        "source_delegated_judgment": {"source_judgment_linkage_id": "jdg-link-receipt-flow"},
    }
    gate = derive_packetization_gate(
        proposal,
        {"review_classification": "proposal_escalation_heavy", "records_considered": 5},
        {"trust_confidence_posture": "stressed_but_usable", "pressure_summary": {"primary_pressure": "mixed_stress"}},
        {"operator_attention_recommendation": "inspect_handoff_blocks"},
    )
    brief = synthesize_operator_action_brief(
        proposal,
        gate,
        {"trust_confidence_posture": "stressed_but_usable", "pressure_summary": {"primary_pressure": "mixed_stress"}},
        {"operator_attention_recommendation": "inspect_handoff_blocks"},
        next_move_proposal_review={"review_classification": "proposal_escalation_heavy"},
        created_at="2026-04-12T00:00:00Z",
    )
    assert brief is not None
    return brief


def _mock_unified_surface(
    monkeypatch,
    *,
    counts: dict[str, int],
    path_counts: dict[str, int] | None = None,
    records_considered: int | None = None,
    fragmented_linkage_count: int = 0,
) -> None:
    base_counts = {
        "completed_successfully": 0,
        "completed_with_issues": 0,
        "declined_or_abandoned": 0,
        "failed_after_execution": 0,
        "blocked_before_execution": 0,
        "pending_or_unresolved": 0,
        "fragmented_result_history": 0,
    }
    base_counts.update(counts)
    base_paths = {"internal_execution": 0, "external_fulfillment": 0}
    if path_counts:
        base_paths.update(path_counts)
    total = sum(base_counts.values()) if records_considered is None else records_considered
    monkeypatch.setattr(
        "sentientos.orchestration_intent_fabric.resolve_unified_orchestration_result_surface",
        lambda *_args, **_kwargs: {
            "records_considered": total,
            "result_classification_counts": base_counts,
            "resolution_path_counts": base_paths,
            "fragmented_linkage_count": fragmented_linkage_count,
        },
    )


def test_deep_research_judgment_translates_to_stageable_external_work_order() -> None:
    evidence = _base_evidence()
    evidence["governance_ambiguity_signal"] = True
    judgment = synthesize_delegated_judgment(evidence)

    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")

    assert judgment["recommended_venue"] == "deep_research_audit"
    assert intent["intent_kind"] == "deep_research_work_order", json.dumps(intent, indent=2, sort_keys=True)
    assert intent["executability_classification"] == "stageable_external_work_order"
    assert intent["execution_target"] == "no_execution_target_yet"
    assert intent["required_authority_posture"] == "operator_approval_required"
    assert intent["work_order"]["intended_venue"] == "deep_research_audit"
    assert intent["does_not_invoke_external_tools"] is True


def test_internal_execution_judgment_translates_to_executable_now_via_task_admission() -> None:
    evidence = _base_evidence()
    evidence.update(
        {
            "admission_denied_ratio": 0.75,
            "admission_sample_count": 8,
            "executor_failure_ratio": 0.4,
            "executor_sample_count": 8,
        }
    )
    judgment = synthesize_delegated_judgment(evidence)

    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")

    assert judgment["recommended_venue"] == "internal_direct_execution"
    assert intent["intent_kind"] == "internal_maintenance_execution"
    assert intent["executability_classification"] == "executable_now"
    assert intent["execution_target"] == "task_admission_executor"
    assert intent["requires_admission"] is True
    assert intent["handoff_admission_state"] == "admitted_for_internal_staging"
    assert intent["does_not_override_existing_admission"] is True


def test_codex_work_order_is_stageable_not_falsely_executable() -> None:
    judgment = synthesize_delegated_judgment(_base_evidence())

    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")

    assert judgment["recommended_venue"] == "codex_implementation"
    assert intent["intent_kind"] == "codex_work_order"
    assert intent["executability_classification"] == "stageable_external_work_order"
    assert intent["staged_handoff_only"] is True
    assert intent["execution_target"] == "no_execution_target_yet"


def test_operator_and_insufficient_context_cases_remain_blocked() -> None:
    insufficient_context_judgment = synthesize_delegated_judgment(
        {
            **_base_evidence(),
            "records_considered": 0,
            "admission_sample_count": 0,
            "executor_sample_count": 0,
        }
    )
    insufficient_intent = synthesize_orchestration_intent(
        insufficient_context_judgment,
        created_at="2026-04-12T00:00:00Z",
    )

    assert insufficient_context_judgment["recommended_venue"] == "operator_decision_required"
    assert insufficient_intent["required_authority_posture"] == "insufficient_context_blocked"
    assert insufficient_intent["executability_classification"] == "blocked_insufficient_context"

    operator_judgment = {
        **insufficient_context_judgment,
        "recommended_venue": "operator_decision_required",
        "escalation_classification": "escalate_for_operator_priority",
    }
    operator_intent = synthesize_orchestration_intent(operator_judgment, created_at="2026-04-12T00:00:00Z")

    assert operator_intent["intent_kind"] == "operator_review_request"
    assert operator_intent["required_authority_posture"] == "operator_priority_required"
    assert operator_intent["executability_classification"] == "blocked_operator_required"


def test_orchestration_intent_ledger_is_append_only(tmp_path: Path) -> None:
    judgment = synthesize_delegated_judgment(_base_evidence())
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")

    ledger_path = append_orchestration_intent_ledger(tmp_path, intent)
    append_orchestration_intent_ledger(tmp_path, {**intent, "intent_id": "orh-second"})

    lines = ledger_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["intent_id"] == intent["intent_id"]
    assert second["intent_id"] == "orh-second"


def test_internal_executable_intent_is_admitted_to_task_admission_surface(tmp_path: Path) -> None:
    evidence = _base_evidence()
    evidence.update(
        {
            "admission_denied_ratio": 0.75,
            "admission_sample_count": 8,
            "executor_failure_ratio": 0.4,
            "executor_sample_count": 8,
        }
    )
    judgment = synthesize_delegated_judgment(evidence)
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    append_orchestration_intent_ledger(tmp_path, intent)

    handoff = admit_orchestration_intent(tmp_path, intent)

    assert handoff["handoff_outcome"] == "admitted_to_execution_substrate"
    assert handoff["details"]["task_admission"]["allowed"] is True
    assert handoff["details"]["task_admission"]["reason"] == "OK"
    assert handoff["ledger_path"] == "glow/orchestration/orchestration_handoffs.jsonl"

    handoff_rows = (tmp_path / handoff["ledger_path"]).read_text(encoding="utf-8").splitlines()
    assert len(handoff_rows) == 1
    handoff_row = json.loads(handoff_rows[-1])
    assert handoff_row["intent_ref"]["intent_id"] == intent["intent_id"]
    assert handoff_row["does_not_invoke_external_tools"] is True


def test_admitted_handoff_resolves_success_from_real_downstream_task_result(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path / "logs"))
    reload(task_executor)
    reload(task_admission)
    evidence = _base_evidence()
    evidence.update(
        {
            "admission_denied_ratio": 0.75,
            "admission_sample_count": 8,
            "executor_failure_ratio": 0.4,
            "executor_sample_count": 8,
        }
    )
    judgment = synthesize_delegated_judgment(evidence)
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    handoff = admit_orchestration_intent(tmp_path, intent)
    assert handoff["handoff_outcome"] == "admitted_to_execution_substrate"

    task = task_executor.Task(
        task_id=handoff["details"]["task_admission"]["task_id"],
        objective="orchestration_intent_internal_maintenance_handoff",
        steps=(task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload(note="ok")),),
        required_privileges=("orchestration_intent_handoff",),
    )
    auth = control_plane.AuthorizationRecord.create(
        request_type=control_plane.RequestType.TASK_EXECUTION,
        requester_id="orchestration-test",
        intent_hash="orh-success",
        context_hash="ctx-success",
        policy_version="v1-static",
        decision=control_plane.Decision.ALLOW,
        reason=control_plane.ReasonCode.OK,
        metadata={"approved_privileges": ["orchestration_intent_handoff"]},
    )
    decision, result = task_admission.run_task_with_admission(
        task=task,
        ctx=task_admission.AdmissionContext(
            actor="orchestration_intent_fabric",
            mode="operator",
            node_id="sentientos_orchestration_handoff",
            vow_digest=None,
            doctrine_digest=None,
            now_utc_iso="2026-04-12T00:00:01Z",
        ),
        policy=task_admission.AdmissionPolicy(policy_version="orh-test.v1"),
        authorization=auth,
    )
    assert decision.allowed is True
    assert result is not None
    assert result.status == "completed"
    with Path(task_executor.LOG_PATH).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"task_id": result.task_id, "event": "task_result", "status": result.status}) + "\n")

    resolution = resolve_orchestration_result(tmp_path, handoff, executor_log_path=Path(task_executor.LOG_PATH))
    assert resolution["orchestration_result_state"] == "execution_succeeded"
    assert resolution["loop_closed"] is True


def test_admitted_handoff_resolves_failed_from_downstream_task_result(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path / "logs"))
    reload(task_executor)
    reload(task_admission)
    evidence = _base_evidence()
    evidence.update(
        {
            "admission_denied_ratio": 0.75,
            "admission_sample_count": 8,
            "executor_failure_ratio": 0.4,
            "executor_sample_count": 8,
        }
    )
    judgment = synthesize_delegated_judgment(evidence)
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    handoff = admit_orchestration_intent(tmp_path, intent)
    task_id = handoff["details"]["task_admission"]["task_id"]
    executor_log = Path(task_executor.LOG_PATH)
    executor_log.parent.mkdir(parents=True, exist_ok=True)
    executor_log.write_text(json.dumps({"task_id": task_id, "event": "task_result", "status": "failed"}) + "\n", encoding="utf-8")

    resolution = resolve_orchestration_result(tmp_path, handoff, executor_log_path=Path(task_executor.LOG_PATH))
    assert resolution["orchestration_result_state"] == "execution_failed"
    assert resolution["loop_closed"] is True


def test_admitted_handoff_without_downstream_result_stays_pending(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path / "logs"))
    reload(task_executor)
    reload(task_admission)
    evidence = _base_evidence()
    evidence.update(
        {
            "admission_denied_ratio": 0.75,
            "admission_sample_count": 8,
            "executor_failure_ratio": 0.4,
            "executor_sample_count": 8,
        }
    )
    judgment = synthesize_delegated_judgment(evidence)
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    handoff = admit_orchestration_intent(tmp_path, intent)

    resolution = resolve_orchestration_result(tmp_path, handoff, executor_log_path=Path(task_executor.LOG_PATH))
    assert resolution["orchestration_result_state"] == "handoff_admitted_pending_result"
    assert resolution["loop_closed"] is False


def test_missing_required_metadata_blocks_handoff_machine_readably(tmp_path: Path) -> None:
    handoff = admit_orchestration_intent(
        tmp_path,
        {
            "intent_kind": "internal_maintenance_execution",
            "execution_target": "task_admission_executor",
            "executability_classification": "executable_now",
        },
    )
    assert handoff["handoff_outcome"] == "blocked_by_insufficient_context"
    assert "intent_id" in handoff["details"]["missing_required_fields"]


def test_internal_handoff_honors_admission_denial(tmp_path: Path) -> None:
    evidence = _base_evidence()
    evidence.update(
        {
            "admission_denied_ratio": 0.75,
            "admission_sample_count": 8,
            "executor_failure_ratio": 0.4,
            "executor_sample_count": 8,
        }
    )
    judgment = synthesize_delegated_judgment(evidence)
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")

    denied_handoff = admit_orchestration_intent(
        tmp_path,
        intent,
        admission_policy=task_admission.AdmissionPolicy(
            policy_version="orchestration_intent_handoff.denied.v1",
            max_steps=0,
        ),
    )

    assert denied_handoff["handoff_outcome"] == "blocked_by_admission"
    assert denied_handoff["details"]["task_admission"]["allowed"] is False
    assert denied_handoff["details"]["task_admission"]["reason"] == "TOO_MANY_STEPS"


def test_external_venues_remain_staged_only_without_internal_admission(tmp_path: Path) -> None:
    codex_judgment = synthesize_delegated_judgment(_base_evidence())
    codex_intent = synthesize_orchestration_intent(codex_judgment, created_at="2026-04-12T00:00:00Z")
    codex_handoff = admit_orchestration_intent(tmp_path, codex_intent)

    assert codex_judgment["recommended_venue"] == "codex_implementation"
    assert codex_handoff["handoff_outcome"] == "blocked_by_operator_requirement"
    assert "task_admission" not in codex_handoff["details"]
    assert codex_handoff["details"]["codex_work_order_ref"]["staged_only"] is True
    codex_resolution = resolve_orchestration_result(tmp_path, codex_handoff)
    assert codex_resolution["orchestration_result_state"] == "handoff_not_admitted"
    assert codex_resolution["execution_task_ref"]["task_id"] is None
    assert codex_resolution["codex_staged_lifecycle"]["lifecycle_state"] == "blocked_operator_required"

    deep_research_judgment = synthesize_delegated_judgment({**_base_evidence(), "governance_ambiguity_signal": True})
    deep_research_intent = synthesize_orchestration_intent(deep_research_judgment, created_at="2026-04-12T00:01:00Z")
    deep_research_handoff = admit_orchestration_intent(tmp_path, deep_research_intent)

    assert deep_research_judgment["recommended_venue"] == "deep_research_audit"
    assert deep_research_handoff["handoff_outcome"] == "blocked_by_operator_requirement"
    assert "task_admission" not in deep_research_handoff["details"]
    assert deep_research_handoff["details"]["deep_research_work_order_ref"]["staged_only"] is True
    deep_research_resolution = resolve_orchestration_result(tmp_path, deep_research_handoff)
    assert deep_research_resolution["orchestration_result_state"] == "handoff_not_admitted"
    assert deep_research_resolution["execution_task_ref"]["task_id"] is None
    assert deep_research_resolution["deep_research_staged_lifecycle"]["lifecycle_state"] == "blocked_operator_required"


def test_blocked_handoff_does_not_fabricate_execution_attempt(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path / "logs"))
    reload(task_executor)
    reload(task_admission)
    evidence = _base_evidence()
    evidence.update(
        {
            "admission_denied_ratio": 0.75,
            "admission_sample_count": 8,
            "executor_failure_ratio": 0.4,
            "executor_sample_count": 8,
        }
    )
    judgment = synthesize_delegated_judgment(evidence)
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    denied_handoff = admit_orchestration_intent(
        tmp_path,
        intent,
        admission_policy=task_admission.AdmissionPolicy(policy_version="deny.v1", max_steps=0),
    )
    assert denied_handoff["handoff_outcome"] == "blocked_by_admission"
    resolution = resolve_orchestration_result(tmp_path, denied_handoff, executor_log_path=Path(task_executor.LOG_PATH))
    assert resolution["orchestration_result_state"] == "handoff_not_admitted"
    assert resolution["execution_task_ref"]["task_id"] == denied_handoff["details"]["task_admission"]["task_id"]
    assert resolution["result_evidence"]["task_result_rows_seen"] == 0


def test_scoped_lifecycle_diagnostic_surfaces_orchestration_handoff_and_ledger(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("sentientos.scoped_lifecycle_diagnostic.SCOPED_ACTION_IDS", ("sentientos.manifest.generate",))

    def _fake_resolver(_repo_root: Path, *, action_id: str, correlation_id: str) -> dict[str, object]:
        return {
            "typed_action_identity": action_id,
            "correlation_id": correlation_id,
            "outcome_class": "success",
        }

    monkeypatch.setattr("sentientos.scoped_lifecycle_diagnostic.resolve_scoped_mutation_lifecycle", _fake_resolver)

    _write_json(tmp_path / "glow/contracts/contract_status.json", {"contracts": []})
    _write_jsonl(
        tmp_path / "pulse/forge_events.jsonl",
        [
            {
                "event": "constitutional_mutation_router_execution",
                "typed_action_id": "sentientos.manifest.generate",
                "correlation_id": "cid-1",
            }
        ],
    )

    diagnostic = build_scoped_lifecycle_diagnostic(tmp_path)

    handoff = diagnostic["orchestration_handoff"]
    assert handoff["intent_ledger_path"] == "glow/orchestration/orchestration_intents.jsonl"
    assert handoff["handoff_result"]["ledger_path"] == "glow/orchestration/orchestration_handoffs.jsonl"
    assert handoff["handoff_result"]["handoff_outcome"] in {"blocked_by_operator_requirement", "blocked_by_insufficient_context", "staged_only"}
    assert handoff["execution_result"]["orchestration_result_state"] == "handoff_not_admitted"
    assert handoff["gap_map"]["stable_linkage_keys"]["execution_task_to_result"] == "task_id"
    assert handoff["intent"]["schema_version"] == "orchestration_intent.v1"
    assert handoff["executable_handoff_map"]["intent_kind_to_handoff"]["internal_maintenance_execution"]["handoff_path_status"] == "operational"
    ledger = tmp_path / handoff["intent_ledger_path"]
    row = json.loads(ledger.read_text(encoding="utf-8").splitlines()[-1])
    assert row["intent_id"] == handoff["intent"]["intent_id"]
    assert row["does_not_invoke_external_tools"] is True


def test_end_to_end_judgment_to_internal_handoff_and_staged_external_only(tmp_path: Path) -> None:
    internal_evidence = _base_evidence()
    internal_evidence.update(
        {
            "admission_denied_ratio": 0.75,
            "admission_sample_count": 8,
            "executor_failure_ratio": 0.4,
            "executor_sample_count": 8,
        }
    )
    internal_judgment = synthesize_delegated_judgment(internal_evidence)
    internal_intent = synthesize_orchestration_intent(internal_judgment, created_at="2026-04-12T00:00:00Z")
    append_orchestration_intent_ledger(tmp_path, internal_intent)
    internal_handoff = admit_orchestration_intent(tmp_path, internal_intent)

    assert internal_judgment["recommended_venue"] == "internal_direct_execution"
    assert internal_intent["executability_classification"] == "executable_now"
    assert internal_handoff["handoff_outcome"] == "admitted_to_execution_substrate"

    external_judgment = synthesize_delegated_judgment(_base_evidence())
    external_intent = synthesize_orchestration_intent(external_judgment, created_at="2026-04-12T00:00:00Z")
    append_orchestration_intent_ledger(tmp_path, external_intent)
    external_handoff = admit_orchestration_intent(tmp_path, external_intent)

    assert external_judgment["recommended_venue"] == "codex_implementation"
    assert external_handoff["handoff_outcome"] == "blocked_by_operator_requirement"
    assert "task_admission" not in external_handoff["details"]
    assert executable_handoff_map()["known_named_targets_without_handoff_path"] == [
        "mutation_router",
        "federation_canonical_execution",
        "external_tool_placeholder",
    ]


def test_end_to_end_closed_loop_judgment_to_handoff_to_execution_result(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path / "logs"))
    reload(task_executor)
    reload(task_admission)

    internal_evidence = _base_evidence()
    internal_evidence.update(
        {
            "admission_denied_ratio": 0.75,
            "admission_sample_count": 8,
            "executor_failure_ratio": 0.4,
            "executor_sample_count": 8,
        }
    )
    judgment = synthesize_delegated_judgment(internal_evidence)
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    append_orchestration_intent_ledger(tmp_path, intent)
    handoff = admit_orchestration_intent(tmp_path, intent)
    assert handoff["handoff_outcome"] == "admitted_to_execution_substrate"

    task_id = handoff["details"]["task_admission"]["task_id"]
    executor_log = Path(task_executor.LOG_PATH)
    executor_log.parent.mkdir(parents=True, exist_ok=True)
    executor_log.write_text(json.dumps({"task_id": task_id, "event": "task_result", "status": "completed"}) + "\n", encoding="utf-8")

    resolution = resolve_orchestration_result(tmp_path, handoff, executor_log_path=Path(task_executor.LOG_PATH))
    assert resolution["orchestration_result_state"] == "execution_succeeded"
    assert resolution["loop_closed"] is True
    gap_map = build_handoff_execution_gap_map(tmp_path)
    assert gap_map["minimal_missing_linkage"].startswith("resolve admitted handoff task_id")


def _seed_orchestration_history(
    tmp_path: Path,
    *,
    outcomes: list[str],
    executor_statuses: list[str | None],
) -> Path:
    intent_rows: list[dict[str, object]] = []
    handoff_rows: list[dict[str, object]] = []
    executor_rows: list[dict[str, object]] = []
    for idx, handoff_outcome in enumerate(outcomes):
        intent_id = f"orh-seed-{idx}"
        intent_rows.append(
            {
                "schema_version": "orchestration_intent.v1",
                "intent_id": intent_id,
            }
        )
        details: dict[str, object] = {}
        status = executor_statuses[idx]
        if handoff_outcome == "admitted_to_execution_substrate":
            task_id = f"task-{idx}"
            details["task_admission"] = {"task_id": task_id}
            if status is not None:
                executor_rows.append({"task_id": task_id, "event": "task_result", "status": status})
        handoff_rows.append(
            {
                "schema_version": "orchestration_handoff.v1",
                "handoff_outcome": handoff_outcome,
                "intent_ref": {"intent_id": intent_id, "intent_kind": "internal_maintenance_execution"},
                "details": details,
            }
        )

    intent_path = tmp_path / "glow/orchestration/orchestration_intents.jsonl"
    handoff_path = tmp_path / "glow/orchestration/orchestration_handoffs.jsonl"
    executor_path = tmp_path / "logs/task_executor.jsonl"
    _write_jsonl(intent_path, intent_rows)
    _write_jsonl(handoff_path, handoff_rows)
    _write_jsonl(executor_path, executor_rows)
    return executor_path


def _seed_venue_mix_history(
    tmp_path: Path,
    *,
    records: list[dict[str, object]],
) -> None:
    intent_rows: list[dict[str, object]] = []
    handoff_rows: list[dict[str, object]] = []
    codex_rows: list[dict[str, object]] = []
    deep_rows: list[dict[str, object]] = []

    for idx, record in enumerate(records):
        intent_id = f"orh-venue-{idx}"
        intent_kind = str(record.get("intent_kind") or "internal_maintenance_execution")
        authority = str(record.get("required_authority_posture") or "no_additional_operator_approval_required")
        requires_operator = bool(record.get("requires_operator_approval", authority != "no_additional_operator_approval_required"))
        escalation = str(record.get("escalation_classification") or "")
        handoff_outcome = str(record.get("handoff_outcome") or "staged_only")
        intent_rows.append(
            {
                "schema_version": "orchestration_intent.v1",
                "intent_id": intent_id,
                "intent_kind": intent_kind,
                "required_authority_posture": authority,
                "requires_operator_approval": requires_operator,
                "source_delegated_judgment": {"escalation_classification": escalation},
            }
        )
        handoff_rows.append(
            {
                "schema_version": "orchestration_handoff.v1",
                "handoff_outcome": handoff_outcome,
                "intent_ref": {"intent_id": intent_id, "intent_kind": intent_kind},
                "details": {
                    "required_authority_posture": authority,
                    "requires_operator_approval": requires_operator,
                },
            }
        )
        if intent_kind == "codex_work_order":
            codex_rows.append(
                {
                    "schema_version": "codex_staged_work_order.v1",
                    "source_intent_id": intent_id,
                    "venue": "codex_implementation",
                }
            )
        if intent_kind == "deep_research_work_order":
            deep_rows.append(
                {
                    "schema_version": "deep_research_staged_work_order.v1",
                    "source_intent_id": intent_id,
                    "venue": "deep_research_audit",
                }
            )

    _write_jsonl(tmp_path / "glow/orchestration/orchestration_intents.jsonl", intent_rows)
    _write_jsonl(tmp_path / "glow/orchestration/orchestration_handoffs.jsonl", handoff_rows)
    _write_jsonl(tmp_path / "glow/orchestration/codex_work_orders.jsonl", codex_rows)
    _write_jsonl(tmp_path / "glow/orchestration/deep_research_work_orders.jsonl", deep_rows)


def _seed_external_feedback_history(
    tmp_path: Path,
    *,
    external_venues: list[str],
    fulfillment_kinds: list[str | None],
) -> Path:
    intent_rows: list[dict[str, object]] = []
    handoff_rows: list[dict[str, object]] = []
    packet_rows: list[dict[str, object]] = []
    receipt_rows: list[dict[str, object]] = []
    for idx, venue in enumerate(external_venues):
        intent_id = f"orh-ext-{idx}"
        delegated = {
            "work_class": "external_tool_orchestration",
            "recommended_venue": venue,
            "next_move_posture": "hold",
            "consolidation_expansion_posture": "consolidate",
            "escalation_classification": "none",
        }
        linkage = {
            "work_class": str(delegated["work_class"]),
            "recommended_venue": str(delegated["recommended_venue"]),
            "next_move_posture": str(delegated["next_move_posture"]),
            "consolidation_expansion_posture": str(delegated["consolidation_expansion_posture"]),
            "escalation_classification": str(delegated["escalation_classification"]),
            "readiness_basis": {"orchestration_substitution_readiness": {}, "basis": {}},
        }
        linkage_id = f"jdg-link-{hashlib.sha256(json.dumps(linkage, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()[:16]}"
        intent_kind = "codex_work_order" if venue == "codex_implementation" else "deep_research_work_order"
        intent_rows.append(
            {
                "schema_version": "orchestration_intent.v1",
                "intent_id": intent_id,
                "intent_kind": intent_kind,
                "source_delegated_judgment": linkage,
                "required_authority_posture": "operator_approval_required",
                "requires_operator_approval": True,
            }
        )
        handoff_rows.append(
            {
                "schema_version": "orchestration_handoff.v1",
                "handoff_outcome": "staged_only",
                "intent_ref": {"intent_id": intent_id, "intent_kind": intent_kind},
                "details": {"required_authority_posture": "operator_approval_required", "requires_operator_approval": True},
            }
        )
        proposal_id = f"proposal-ext-{idx}"
        packet_id = f"hpk-ext-{idx}"
        packet_rows.append(
            {
                "schema_version": "orchestration_handoff_packet.v1",
                "handoff_packet_id": packet_id,
                "target_venue": venue,
                "source_next_move_proposal_ref": {"proposal_id": proposal_id},
                "source_delegated_judgment_ref": {
                    "source_judgment_linkage_id": linkage_id
                },
                "packet_status": "ready_for_external_trigger",
                "readiness": {"ready_for_external_trigger": True, "staged_only": True, "blocked": False},
            }
        )
        kind = fulfillment_kinds[idx]
        if kind:
            receipt_rows.append(
                {
                    "schema_version": "orchestration_fulfillment_receipt.v1",
                    "fulfillment_receipt_id": f"fr-ext-{idx}",
                    "source_handoff_packet_ref": {"handoff_packet_id": packet_id},
                    "source_venue": venue,
                    "fulfillment_kind": kind,
                }
            )

    _write_jsonl(tmp_path / "glow/orchestration/orchestration_intents.jsonl", intent_rows)
    _write_jsonl(tmp_path / "glow/orchestration/orchestration_handoffs.jsonl", handoff_rows)
    _write_jsonl(tmp_path / "glow/orchestration/orchestration_handoff_packets.jsonl", packet_rows)
    _write_jsonl(tmp_path / "glow/orchestration/orchestration_fulfillment_receipts.jsonl", receipt_rows)
    _write_jsonl(tmp_path / "logs/task_executor.jsonl", [])
    return tmp_path / "logs/task_executor.jsonl"


def test_outcome_review_success_dominant_classifies_clean(tmp_path: Path) -> None:
    executor_log = _seed_orchestration_history(
        tmp_path,
        outcomes=[
            "admitted_to_execution_substrate",
            "admitted_to_execution_substrate",
            "admitted_to_execution_substrate",
            "blocked_by_admission",
            "admitted_to_execution_substrate",
        ],
        executor_statuses=["completed", "completed", "completed", None, "failed"],
    )

    review = derive_orchestration_outcome_review(tmp_path, executor_log_path=executor_log)
    assert review["review_classification"] == "clean_recent_orchestration"
    assert review["summary"]["recent_pattern"] == "healthy_bounded_orchestration"
    attention = derive_orchestration_attention_recommendation(review)
    assert attention["operator_attention_recommendation"] == "none"


def test_outcome_review_block_heavy_classifies_blocked_pattern(tmp_path: Path) -> None:
    executor_log = _seed_orchestration_history(
        tmp_path,
        outcomes=[
            "blocked_by_admission",
            "blocked_by_admission",
            "blocked_by_operator_requirement",
            "admitted_to_execution_substrate",
            "staged_only",
        ],
        executor_statuses=[None, None, None, "completed", None],
    )

    review = derive_orchestration_outcome_review(tmp_path, executor_log_path=executor_log)
    assert review["review_classification"] == "handoff_block_heavy"
    assert review["condition_flags"]["blocked_heavy"] is True
    attention = derive_orchestration_attention_recommendation(review)
    assert attention["operator_attention_recommendation"] == "inspect_handoff_blocks"


def test_outcome_review_failure_heavy_classifies_execution_failure_pattern(tmp_path: Path) -> None:
    executor_log = _seed_orchestration_history(
        tmp_path,
        outcomes=[
            "admitted_to_execution_substrate",
            "admitted_to_execution_substrate",
            "admitted_to_execution_substrate",
            "admitted_to_execution_substrate",
        ],
        executor_statuses=["failed", "failed", "completed", "failed"],
    )

    review = derive_orchestration_outcome_review(tmp_path, executor_log_path=executor_log)
    assert review["review_classification"] == "execution_failure_heavy"
    assert review["condition_flags"]["failure_heavy"] is True
    attention = derive_orchestration_attention_recommendation(review)
    assert attention["operator_attention_recommendation"] == "inspect_execution_failures"


def test_outcome_review_pending_heavy_classifies_stall_pattern(tmp_path: Path) -> None:
    executor_log = _seed_orchestration_history(
        tmp_path,
        outcomes=[
            "admitted_to_execution_substrate",
            "admitted_to_execution_substrate",
            "admitted_to_execution_substrate",
            "admitted_to_execution_substrate",
        ],
        executor_statuses=[None, None, "completed", None],
    )

    review = derive_orchestration_outcome_review(tmp_path, executor_log_path=executor_log)
    assert review["review_classification"] == "pending_stall_pattern"
    assert review["condition_flags"]["stall_heavy"] is True
    attention = derive_orchestration_attention_recommendation(review)
    assert attention["operator_attention_recommendation"] == "inspect_pending_stall"


def test_outcome_review_mixed_classifies_stress_pattern(tmp_path: Path) -> None:
    executor_log = _seed_orchestration_history(
        tmp_path,
        outcomes=[
            "admitted_to_execution_substrate",
            "admitted_to_execution_substrate",
            "blocked_by_admission",
            "staged_only",
            "admitted_to_execution_substrate",
        ],
        executor_statuses=["completed", "failed", None, None, None],
    )

    review = derive_orchestration_outcome_review(tmp_path, executor_log_path=executor_log)
    assert review["review_classification"] == "mixed_orchestration_stress"
    assert review["summary"]["recent_pattern"] == "orchestration_stress_or_uncertainty"
    attention = derive_orchestration_attention_recommendation(review)
    assert attention["operator_attention_recommendation"] in {
        "review_mixed_orchestration_stress",
        "observe",
    }


def test_outcome_review_insufficient_history_when_too_few_records(tmp_path: Path) -> None:
    executor_log = _seed_orchestration_history(
        tmp_path,
        outcomes=["admitted_to_execution_substrate", "blocked_by_admission"],
        executor_statuses=["completed", None],
    )

    review = derive_orchestration_outcome_review(tmp_path, executor_log_path=executor_log)
    assert review["review_classification"] == "insufficient_history"
    assert review["records_considered"] == 2
    attention = derive_orchestration_attention_recommendation(review)
    assert attention["operator_attention_recommendation"] == "insufficient_context"


def test_outcome_review_uses_fulfilled_codex_receipts_as_external_healthy_support(tmp_path: Path) -> None:
    executor_log = _seed_external_feedback_history(
        tmp_path,
        external_venues=["codex_implementation", "codex_implementation", "codex_implementation"],
        fulfillment_kinds=["externally_completed", "externally_completed", "externally_completed"],
    )

    review = derive_orchestration_outcome_review(tmp_path, executor_log_path=executor_log)
    assert review["review_classification"] == "clean_recent_orchestration"
    assert review["condition_flags"]["external_feedback_signal_present"] is True
    assert review["condition_flags"]["external_healthy_support"] is True
    assert review["external_fulfillment_outcome_counts"]["fulfilled_externally"] == 3
    assert review["summary"]["external_fulfillment_influence"]["influence_mode"] == "healthy_support"


def test_outcome_review_marks_external_stress_for_unusable_or_declined_without_internal_failure_claim(tmp_path: Path) -> None:
    executor_log = _seed_external_feedback_history(
        tmp_path,
        external_venues=["codex_implementation", "codex_implementation", "codex_implementation"],
        fulfillment_kinds=["externally_result_unusable", "externally_declined", "externally_abandoned"],
    )

    review = derive_orchestration_outcome_review(tmp_path, executor_log_path=executor_log)
    assert review["review_classification"] == "mixed_orchestration_stress"
    assert review["condition_flags"]["external_feedback_signal_present"] is True
    assert review["condition_flags"]["external_stress_heavy"] is True
    assert review["recent_outcome_counts"]["execution_failed"] == 0
    assert review["external_fulfillment_outcome_counts"]["externally_result_unusable"] == 1


def test_attention_recommendation_light_block_pattern_prefers_observe(tmp_path: Path) -> None:
    executor_log = _seed_orchestration_history(
        tmp_path,
        outcomes=[
            "admitted_to_execution_substrate",
            "admitted_to_execution_substrate",
            "blocked_by_admission",
            "admitted_to_execution_substrate",
            "staged_only",
        ],
        executor_statuses=["completed", "completed", None, "completed", None],
    )

    review = derive_orchestration_outcome_review(tmp_path, executor_log_path=executor_log)
    attention = derive_orchestration_attention_recommendation(review)
    assert review["review_classification"] in {"clean_recent_orchestration", "mixed_orchestration_stress"}
    assert attention["operator_attention_recommendation"] in {"none", "observe"}


def test_venue_mix_review_balanced_recent_use_classifies_balanced(tmp_path: Path) -> None:
    _seed_venue_mix_history(
        tmp_path,
        records=[
            {"intent_kind": "internal_maintenance_execution", "handoff_outcome": "admitted_to_execution_substrate"},
            {"intent_kind": "codex_work_order", "handoff_outcome": "staged_only", "required_authority_posture": "operator_approval_required"},
            {"intent_kind": "deep_research_work_order", "handoff_outcome": "staged_only", "required_authority_posture": "operator_approval_required"},
            {"intent_kind": "internal_maintenance_execution", "handoff_outcome": "admitted_to_execution_substrate"},
        ],
    )

    review = derive_orchestration_venue_mix_review(tmp_path)
    assert review["review_classification"] == "balanced_recent_venue_mix"
    assert review["recent_venue_counts"]["task_admission_executor"] == 2
    assert review["recent_venue_counts"]["codex_implementation"] == 1
    assert review["recent_venue_counts"]["deep_research_audit"] == 1


def test_venue_mix_review_internal_heavy_classification(tmp_path: Path) -> None:
    _seed_venue_mix_history(
        tmp_path,
        records=[
            {"intent_kind": "internal_maintenance_execution", "handoff_outcome": "admitted_to_execution_substrate"},
            {"intent_kind": "internal_maintenance_execution", "handoff_outcome": "admitted_to_execution_substrate"},
            {"intent_kind": "internal_maintenance_execution", "handoff_outcome": "admitted_to_execution_substrate"},
            {"intent_kind": "codex_work_order", "handoff_outcome": "staged_only"},
        ],
    )

    review = derive_orchestration_venue_mix_review(tmp_path)
    assert review["review_classification"] == "internal_execution_heavy"


def test_venue_mix_review_codex_heavy_classification(tmp_path: Path) -> None:
    _seed_venue_mix_history(
        tmp_path,
        records=[
            {"intent_kind": "codex_work_order", "handoff_outcome": "staged_only"},
            {"intent_kind": "codex_work_order", "handoff_outcome": "staged_only"},
            {"intent_kind": "codex_work_order", "handoff_outcome": "staged_only"},
            {"intent_kind": "internal_maintenance_execution", "handoff_outcome": "admitted_to_execution_substrate"},
        ],
    )

    review = derive_orchestration_venue_mix_review(tmp_path)
    assert review["review_classification"] == "codex_heavy"
    assert review["evidence_counts"]["recent_codex_work_orders"] == 3


def test_venue_mix_review_deep_research_heavy_classification(tmp_path: Path) -> None:
    _seed_venue_mix_history(
        tmp_path,
        records=[
            {"intent_kind": "deep_research_work_order", "handoff_outcome": "staged_only"},
            {"intent_kind": "deep_research_work_order", "handoff_outcome": "staged_only"},
            {"intent_kind": "deep_research_work_order", "handoff_outcome": "staged_only"},
            {"intent_kind": "internal_maintenance_execution", "handoff_outcome": "admitted_to_execution_substrate"},
        ],
    )

    review = derive_orchestration_venue_mix_review(tmp_path)
    assert review["review_classification"] == "deep_research_heavy"
    assert review["evidence_counts"]["recent_deep_research_work_orders"] == 3


def test_venue_mix_review_operator_escalation_heavy_classification(tmp_path: Path) -> None:
    _seed_venue_mix_history(
        tmp_path,
        records=[
            {
                "intent_kind": "internal_maintenance_execution",
                "handoff_outcome": "blocked_by_operator_requirement",
                "required_authority_posture": "operator_approval_required",
            },
            {
                "intent_kind": "operator_review_request",
                "handoff_outcome": "blocked_by_operator_requirement",
                "required_authority_posture": "operator_priority_required",
                "escalation_classification": "escalate_for_operator_priority",
            },
            {
                "intent_kind": "codex_work_order",
                "handoff_outcome": "blocked_by_operator_requirement",
                "required_authority_posture": "operator_approval_required",
            },
            {"intent_kind": "deep_research_work_order", "handoff_outcome": "staged_only"},
        ],
    )

    review = derive_orchestration_venue_mix_review(tmp_path)
    assert review["review_classification"] == "operator_escalation_heavy"
    assert review["recent_operator_and_blocked_counts"]["operator_required_or_escalated"] >= 3


def test_venue_mix_review_conflicting_stress_classifies_mixed_stress(tmp_path: Path) -> None:
    _seed_venue_mix_history(
        tmp_path,
        records=[
            {
                "intent_kind": "internal_maintenance_execution",
                "handoff_outcome": "blocked_by_operator_requirement",
                "required_authority_posture": "operator_approval_required",
            },
            {
                "intent_kind": "internal_maintenance_execution",
                "handoff_outcome": "blocked_by_operator_requirement",
                "required_authority_posture": "operator_approval_required",
            },
            {"intent_kind": "internal_maintenance_execution", "handoff_outcome": "admitted_to_execution_substrate"},
            {
                "intent_kind": "operator_review_request",
                "handoff_outcome": "blocked_by_operator_requirement",
                "required_authority_posture": "operator_priority_required",
                "escalation_classification": "escalate_for_operator_priority",
            },
            {
                "intent_kind": "operator_review_request",
                "handoff_outcome": "blocked_by_operator_requirement",
                "required_authority_posture": "operator_priority_required",
                "escalation_classification": "escalate_for_operator_priority",
            },
        ],
    )

    review = derive_orchestration_venue_mix_review(tmp_path)
    assert review["review_classification"] == "mixed_venue_stress"
    assert review["summary"]["classification_basis"]["heavy_flags"]["conflicting_heavy_patterns"] is True


def test_venue_mix_review_insufficient_history(tmp_path: Path) -> None:
    _seed_venue_mix_history(
        tmp_path,
        records=[
            {"intent_kind": "internal_maintenance_execution", "handoff_outcome": "admitted_to_execution_substrate"},
            {"intent_kind": "codex_work_order", "handoff_outcome": "staged_only"},
        ],
    )

    review = derive_orchestration_venue_mix_review(tmp_path)
    assert review["review_classification"] == "insufficient_history"
    assert review["records_considered"] == 2


def test_venue_mix_review_includes_external_fulfillment_quality_contribution(tmp_path: Path) -> None:
    _seed_external_feedback_history(
        tmp_path,
        external_venues=["deep_research_audit", "deep_research_audit", "deep_research_audit"],
        fulfillment_kinds=["externally_completed", "externally_completed", "externally_completed_with_issues"],
    )

    review = derive_orchestration_venue_mix_review(tmp_path)
    external = review["external_fulfillment_contribution"]
    assert external["signal_present"] is True
    assert external["by_venue"]["deep_research_audit"]["healthy"] == 2
    assert external["by_venue"]["deep_research_audit"]["stressed"] == 1
    assert review["summary"]["external_fulfillment_influence"]["influenced_venue_mix_review"] is True


def test_diagnostic_consumer_surfaces_outcome_review_and_remains_non_authoritative(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("sentientos.scoped_lifecycle_diagnostic.SCOPED_ACTION_IDS", ("sentientos.manifest.generate",))

    def _fake_resolver(_repo_root: Path, *, action_id: str, correlation_id: str) -> dict[str, object]:
        return {
            "typed_action_identity": action_id,
            "correlation_id": correlation_id,
            "outcome_class": "success",
        }

    monkeypatch.setattr("sentientos.scoped_lifecycle_diagnostic.resolve_scoped_mutation_lifecycle", _fake_resolver)
    monkeypatch.setattr(
        "sentientos.scoped_lifecycle_diagnostic.synthesize_delegated_judgment",
        lambda _evidence: synthesize_delegated_judgment(_base_evidence()),
    )
    _write_json(tmp_path / "glow/contracts/contract_status.json", {"contracts": []})
    _write_jsonl(
        tmp_path / "pulse/forge_events.jsonl",
        [
            {
                "event": "constitutional_mutation_router_execution",
                "typed_action_id": "sentientos.manifest.generate",
                "correlation_id": "cid-orh-review",
            }
        ],
    )

    diagnostic = build_scoped_lifecycle_diagnostic(tmp_path)
    review = diagnostic["orchestration_handoff"]["outcome_review"]
    venue_mix_review = diagnostic["orchestration_handoff"]["venue_mix_review"]
    attention = diagnostic["orchestration_handoff"]["attention_recommendation"]

    assert "review_classification" in review
    assert "recent_outcome_counts" in review
    assert review["diagnostic_only"] is True
    assert review["non_authoritative"] is True
    assert review["decision_power"] == "none"
    assert review["does_not_change_admission_or_execution_authority"] is True
    assert "review_classification" in venue_mix_review
    assert "recent_venue_counts" in venue_mix_review
    assert "recent_operator_and_blocked_counts" in venue_mix_review
    assert venue_mix_review["diagnostic_only"] is True
    assert venue_mix_review["non_authoritative"] is True
    assert venue_mix_review["decision_power"] == "none"
    assert venue_mix_review["review_only"] is True
    assert venue_mix_review["does_not_change_admission_or_execution"] is True
    assert attention["operator_attention_recommendation"] in {
        "none",
        "observe",
        "inspect_handoff_blocks",
        "inspect_execution_failures",
        "inspect_pending_stall",
        "review_mixed_orchestration_stress",
        "insufficient_context",
    }
    assert attention["diagnostic_only"] is True
    assert attention["non_authoritative"] is True
    assert attention["decision_power"] == "none"
    assert attention["recommendation_only"] is True
    assert attention["does_not_change_admission_or_execution"] is True


def test_recent_history_review_to_attention_to_consumer_stays_non_authoritative(tmp_path: Path) -> None:
    executor_log = _seed_orchestration_history(
        tmp_path,
        outcomes=[
            "admitted_to_execution_substrate",
            "admitted_to_execution_substrate",
            "admitted_to_execution_substrate",
            "admitted_to_execution_substrate",
        ],
        executor_statuses=["failed", "failed", "completed", "failed"],
    )
    review = derive_orchestration_outcome_review(tmp_path, executor_log_path=executor_log)
    attention = derive_orchestration_attention_recommendation(review)

    assert review["review_classification"] == "execution_failure_heavy"
    assert attention["operator_attention_recommendation"] == "inspect_execution_failures"
    assert attention["review_ref"]["review_classification"] == review["review_classification"]
    assert attention["non_authoritative"] is True
    assert attention["decision_power"] == "none"
    assert attention["does_not_change_admission_or_execution"] is True


def test_next_venue_recommendation_prefers_internal_for_healthy_internal_pattern() -> None:
    delegated = {"recommended_venue": "internal_direct_execution", "escalation_classification": "none"}
    outcome_review = {
        "review_classification": "clean_recent_orchestration",
        "records_considered": 6,
        "condition_flags": {"blocked_heavy": False, "failure_heavy": False, "stall_heavy": False},
    }
    venue_mix_review = {"review_classification": "internal_execution_heavy", "records_considered": 6}
    attention = {"operator_attention_recommendation": "none"}

    recommendation = derive_next_venue_recommendation(delegated, outcome_review, venue_mix_review, attention)

    assert recommendation["next_venue_recommendation"] == "prefer_internal_execution"
    assert recommendation["relation_to_delegated_judgment"] == "affirming"


def test_next_venue_recommendation_prefers_codex_for_healthy_codex_pattern() -> None:
    delegated = {"recommended_venue": "codex_implementation", "escalation_classification": "none"}
    outcome_review = {
        "review_classification": "clean_recent_orchestration",
        "records_considered": 5,
        "condition_flags": {"blocked_heavy": False, "failure_heavy": False, "stall_heavy": False},
    }
    venue_mix_review = {"review_classification": "balanced_recent_venue_mix", "records_considered": 5}
    attention = {"operator_attention_recommendation": "none"}

    recommendation = derive_next_venue_recommendation(delegated, outcome_review, venue_mix_review, attention)

    assert recommendation["next_venue_recommendation"] == "prefer_codex_implementation"
    assert recommendation["relation_to_delegated_judgment"] == "affirming"


def test_next_venue_recommendation_prefers_deep_research_for_architecture_stress() -> None:
    delegated = {"recommended_venue": "codex_implementation", "escalation_classification": "none"}
    outcome_review = {
        "review_classification": "mixed_orchestration_stress",
        "records_considered": 7,
        "condition_flags": {"blocked_heavy": False, "failure_heavy": True, "stall_heavy": False},
    }
    venue_mix_review = {"review_classification": "deep_research_heavy", "records_considered": 7}
    attention = {"operator_attention_recommendation": "review_mixed_orchestration_stress"}

    recommendation = derive_next_venue_recommendation(delegated, outcome_review, venue_mix_review, attention)

    assert recommendation["next_venue_recommendation"] == "prefer_deep_research_audit"
    assert recommendation["relation_to_delegated_judgment"] == "nudging"


def test_next_venue_recommendation_prefers_operator_decision_for_escalation_dominant_pattern() -> None:
    delegated = {"recommended_venue": "codex_implementation", "escalation_classification": "escalate_for_operator_priority"}
    outcome_review = {
        "review_classification": "handoff_block_heavy",
        "records_considered": 6,
        "condition_flags": {"blocked_heavy": True, "failure_heavy": False, "stall_heavy": False},
    }
    venue_mix_review = {"review_classification": "operator_escalation_heavy", "records_considered": 6}
    attention = {"operator_attention_recommendation": "inspect_handoff_blocks"}

    recommendation = derive_next_venue_recommendation(delegated, outcome_review, venue_mix_review, attention)

    assert recommendation["next_venue_recommendation"] == "prefer_operator_decision"
    assert recommendation["relation_to_delegated_judgment"] == "escalating"


def test_next_venue_recommendation_holds_for_stressed_mix_without_clear_correction_target() -> None:
    delegated = {"recommended_venue": "deep_research_audit", "escalation_classification": "none"}
    outcome_review = {
        "review_classification": "mixed_orchestration_stress",
        "records_considered": 5,
        "condition_flags": {"blocked_heavy": False, "failure_heavy": False, "stall_heavy": False},
    }
    venue_mix_review = {"review_classification": "mixed_venue_stress", "records_considered": 5}
    attention = {"operator_attention_recommendation": "observe"}

    recommendation = derive_next_venue_recommendation(delegated, outcome_review, venue_mix_review, attention)

    assert recommendation["next_venue_recommendation"] == "hold_current_venue_mix"
    assert recommendation["relation_to_delegated_judgment"] == "holding"


def test_next_venue_recommendation_returns_insufficient_context_when_history_is_thin() -> None:
    delegated = {"recommended_venue": "codex_implementation", "escalation_classification": "none"}
    outcome_review = {
        "review_classification": "insufficient_history",
        "records_considered": 2,
        "condition_flags": {"blocked_heavy": False, "failure_heavy": False, "stall_heavy": False},
    }
    venue_mix_review = {"review_classification": "insufficient_history", "records_considered": 2}
    attention = {"operator_attention_recommendation": "insufficient_context"}

    recommendation = derive_next_venue_recommendation(delegated, outcome_review, venue_mix_review, attention)

    assert recommendation["next_venue_recommendation"] == "insufficient_context"
    assert recommendation["relation_to_delegated_judgment"] == "insufficient_context"


def test_next_venue_recommendation_affirms_codex_when_external_fulfillment_is_healthy() -> None:
    delegated = {"recommended_venue": "codex_implementation", "escalation_classification": "none"}
    outcome_review = {
        "review_classification": "clean_recent_orchestration",
        "records_considered": 5,
        "condition_flags": {"blocked_heavy": False, "failure_heavy": False, "stall_heavy": False},
    }
    venue_mix_review = {
        "review_classification": "codex_heavy",
        "records_considered": 5,
        "external_fulfillment_contribution": {
            "signal_present": True,
            "by_venue": {
                "codex_implementation": {
                    "healthy": 2,
                    "stressed": 0,
                    "blocked_or_unusable": 0,
                    "fulfilled_externally": 2,
                    "fulfilled_externally_with_issues": 0,
                    "externally_declined": 0,
                    "externally_abandoned": 0,
                    "externally_result_unusable": 0,
                },
                "deep_research_audit": {
                    "healthy": 0,
                    "stressed": 0,
                    "blocked_or_unusable": 0,
                    "fulfilled_externally": 0,
                    "fulfilled_externally_with_issues": 0,
                    "externally_declined": 0,
                    "externally_abandoned": 0,
                    "externally_result_unusable": 0,
                },
            },
        },
    }
    attention = {"operator_attention_recommendation": "none"}

    recommendation = derive_next_venue_recommendation(delegated, outcome_review, venue_mix_review, attention)

    assert recommendation["next_venue_recommendation"] == "prefer_codex_implementation"
    assert recommendation["relation_to_delegated_judgment"] == "affirming"
    assert recommendation["basis"]["orchestration_venue_mix_review"]["external_fulfillment_contribution"]["external_feedback_affirming"] is True


def test_next_venue_recommendation_nudges_from_codex_when_external_fulfillment_is_stressed_and_deep_is_healthy() -> None:
    delegated = {"recommended_venue": "codex_implementation", "escalation_classification": "none"}
    outcome_review = {
        "review_classification": "mixed_orchestration_stress",
        "records_considered": 6,
        "condition_flags": {"blocked_heavy": False, "failure_heavy": False, "stall_heavy": False},
    }
    venue_mix_review = {
        "review_classification": "mixed_venue_stress",
        "records_considered": 6,
        "external_fulfillment_contribution": {
            "signal_present": True,
            "by_venue": {
                "codex_implementation": {
                    "healthy": 0,
                    "stressed": 1,
                    "blocked_or_unusable": 1,
                    "fulfilled_externally": 0,
                    "fulfilled_externally_with_issues": 1,
                    "externally_declined": 1,
                    "externally_abandoned": 0,
                    "externally_result_unusable": 0,
                },
                "deep_research_audit": {
                    "healthy": 2,
                    "stressed": 0,
                    "blocked_or_unusable": 0,
                    "fulfilled_externally": 2,
                    "fulfilled_externally_with_issues": 0,
                    "externally_declined": 0,
                    "externally_abandoned": 0,
                    "externally_result_unusable": 0,
                },
            },
        },
    }
    attention = {"operator_attention_recommendation": "review_mixed_orchestration_stress"}

    recommendation = derive_next_venue_recommendation(delegated, outcome_review, venue_mix_review, attention)

    assert recommendation["next_venue_recommendation"] == "prefer_deep_research_audit"
    assert recommendation["relation_to_delegated_judgment"] == "nudging"
    assert recommendation["does_not_override_delegated_judgment"] is True


def test_next_move_proposal_affirming_for_healthy_internal_pattern() -> None:
    delegated = {
        "recommended_venue": "internal_direct_execution",
        "escalation_classification": "none",
        "work_class": "internal_runtime_maintenance",
        "next_move_posture": "hold",
    }
    outcome_review = {
        "review_classification": "clean_recent_orchestration",
        "records_considered": 6,
        "condition_flags": {"blocked_heavy": False, "failure_heavy": False, "stall_heavy": False},
    }
    venue_mix_review = {"review_classification": "internal_execution_heavy", "records_considered": 6}
    attention = {"operator_attention_recommendation": "none"}
    next_venue = derive_next_venue_recommendation(delegated, outcome_review, venue_mix_review, attention)

    proposal = synthesize_next_move_proposal(delegated, next_venue, outcome_review, venue_mix_review, attention)

    assert proposal["relation_posture"] == "affirming"
    assert proposal["proposed_next_action"]["proposed_venue"] == "internal_direct_execution"
    assert proposal["executability_classification"] == "executable_now"
    assert proposal["proposal_state"] == "ready_for_internal_executable_handoff"


def test_next_move_proposal_nudging_or_holding_on_stressed_pattern() -> None:
    delegated = {
        "recommended_venue": "codex_implementation",
        "escalation_classification": "none",
        "work_class": "cross_slice_consolidation",
        "next_move_posture": "consolidate",
    }
    outcome_review = {
        "review_classification": "mixed_orchestration_stress",
        "records_considered": 7,
        "condition_flags": {"blocked_heavy": False, "failure_heavy": True, "stall_heavy": False},
    }
    venue_mix_review = {"review_classification": "deep_research_heavy", "records_considered": 7}
    attention = {"operator_attention_recommendation": "review_mixed_orchestration_stress"}
    next_venue = derive_next_venue_recommendation(delegated, outcome_review, venue_mix_review, attention)

    proposal = synthesize_next_move_proposal(delegated, next_venue, outcome_review, venue_mix_review, attention)

    assert proposal["relation_posture"] in {"nudging", "holding"}
    assert proposal["executability_classification"] in {"stageable_external_work_order", "no_action_recommended"}


def test_next_move_proposal_escalates_for_operator_heavy_patterns() -> None:
    delegated = {
        "recommended_venue": "codex_implementation",
        "escalation_classification": "escalate_for_operator_priority",
        "work_class": "operator_required",
        "next_move_posture": "escalate",
    }
    outcome_review = {
        "review_classification": "handoff_block_heavy",
        "records_considered": 6,
        "condition_flags": {"blocked_heavy": True, "failure_heavy": False, "stall_heavy": False},
    }
    venue_mix_review = {"review_classification": "operator_escalation_heavy", "records_considered": 6}
    attention = {"operator_attention_recommendation": "inspect_handoff_blocks"}
    next_venue = derive_next_venue_recommendation(delegated, outcome_review, venue_mix_review, attention)

    proposal = synthesize_next_move_proposal(delegated, next_venue, outcome_review, venue_mix_review, attention)

    assert proposal["relation_posture"] == "escalating"
    assert proposal["proposed_next_action"]["proposed_posture"] == "escalate"
    assert proposal["executability_classification"] == "blocked_operator_required"
    assert proposal["operator_escalation_requirement_state"]["requires_operator_or_escalation"] is True


def test_next_move_proposal_insufficient_context_when_signal_basis_is_thin() -> None:
    delegated = {
        "recommended_venue": "codex_implementation",
        "escalation_classification": "none",
        "work_class": "cross_slice_consolidation",
        "next_move_posture": "consolidate",
    }
    outcome_review = {
        "review_classification": "insufficient_history",
        "records_considered": 2,
        "condition_flags": {"blocked_heavy": False, "failure_heavy": False, "stall_heavy": False},
    }
    venue_mix_review = {"review_classification": "insufficient_history", "records_considered": 2}
    attention = {"operator_attention_recommendation": "insufficient_context"}
    next_venue = derive_next_venue_recommendation(delegated, outcome_review, venue_mix_review, attention)

    proposal = synthesize_next_move_proposal(delegated, next_venue, outcome_review, venue_mix_review, attention)

    assert proposal["relation_posture"] == "insufficient_context"
    assert proposal["executability_classification"] == "blocked_insufficient_context"
    assert proposal["proposal_only"] is True
    assert proposal["does_not_execute_or_route_work"] is True
    assert proposal["does_not_override_delegated_judgment"] is True


def test_next_move_proposal_artifact_is_append_only_and_proof_visible(tmp_path: Path) -> None:
    delegated = synthesize_delegated_judgment(_base_evidence())
    outcome_review = {
        "review_classification": "clean_recent_orchestration",
        "records_considered": 6,
        "condition_flags": {"blocked_heavy": False, "failure_heavy": False, "stall_heavy": False},
    }
    venue_mix_review = {"review_classification": "balanced_recent_venue_mix", "records_considered": 6}
    attention = {"operator_attention_recommendation": "none"}
    next_venue = derive_next_venue_recommendation(delegated, outcome_review, venue_mix_review, attention)
    proposal = synthesize_next_move_proposal(
        delegated,
        next_venue,
        outcome_review,
        venue_mix_review,
        attention,
        created_at="2026-04-12T00:00:00Z",
    )
    ledger_path = append_next_move_proposal_ledger(tmp_path, proposal)
    append_next_move_proposal_ledger(tmp_path, {**proposal, "proposal_id": "nmp-second"})

    rows = ledger_path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2
    first = json.loads(rows[0])
    second = json.loads(rows[1])
    assert first["proposal_id"] == proposal["proposal_id"]
    assert second["proposal_id"] == "nmp-second"


def test_next_move_proposal_review_classifies_coherent_recent_proposals(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "glow/orchestration/orchestration_next_move_proposals.jsonl",
        [
            _proposal_row(
                relation_posture="affirming",
                venue="internal_direct_execution",
                executability="executable_now",
            ),
            _proposal_row(
                relation_posture="affirming",
                venue="internal_direct_execution",
                executability="executable_now",
            ),
            _proposal_row(
                relation_posture="nudging",
                venue="codex_implementation",
                executability="stageable_external_work_order",
            ),
            _proposal_row(
                relation_posture="affirming",
                venue="codex_implementation",
                executability="stageable_external_work_order",
            ),
        ],
    )

    review = derive_next_move_proposal_review(tmp_path)

    assert review["review_classification"] == "coherent_recent_proposals"
    assert review["summary"]["proposal_behavior_posture"] == "coherent"
    assert review["review_only"] is True
    assert review["non_authoritative"] is True


def test_next_move_proposal_review_classifies_escalation_heavy(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "glow/orchestration/orchestration_next_move_proposals.jsonl",
        [
            _proposal_row(
                relation_posture="escalating",
                venue="operator_decision_required",
                executability="blocked_operator_required",
                requires_operator=True,
            ),
            _proposal_row(
                relation_posture="escalating",
                venue="operator_decision_required",
                executability="blocked_operator_required",
                requires_operator=True,
            ),
            _proposal_row(
                relation_posture="escalating",
                venue="operator_decision_required",
                executability="blocked_operator_required",
                requires_operator=True,
            ),
            _proposal_row(
                relation_posture="holding",
                venue="codex_implementation",
                executability="stageable_external_work_order",
            ),
        ],
    )

    review = derive_next_move_proposal_review(tmp_path)
    assert review["review_classification"] == "proposal_escalation_heavy"


def test_next_move_proposal_review_classifies_hold_heavy(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "glow/orchestration/orchestration_next_move_proposals.jsonl",
        [
            _proposal_row(relation_posture="holding", venue="internal_direct_execution", executability="no_action_recommended"),
            _proposal_row(relation_posture="holding", venue="internal_direct_execution", executability="no_action_recommended"),
            _proposal_row(relation_posture="holding", venue="codex_implementation", executability="no_action_recommended"),
            _proposal_row(relation_posture="affirming", venue="codex_implementation", executability="stageable_external_work_order"),
        ],
    )

    review = derive_next_move_proposal_review(tmp_path)
    assert review["review_classification"] == "proposal_hold_heavy"


def test_next_move_proposal_review_classifies_insufficient_context_heavy(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "glow/orchestration/orchestration_next_move_proposals.jsonl",
        [
            _proposal_row(
                relation_posture="insufficient_context",
                venue="insufficient_context",
                executability="blocked_insufficient_context",
            ),
            _proposal_row(
                relation_posture="insufficient_context",
                venue="insufficient_context",
                executability="blocked_insufficient_context",
            ),
            _proposal_row(
                relation_posture="insufficient_context",
                venue="insufficient_context",
                executability="blocked_insufficient_context",
            ),
            _proposal_row(
                relation_posture="holding",
                venue="operator_decision_required",
                executability="blocked_operator_required",
                requires_operator=True,
            ),
        ],
    )

    review = derive_next_move_proposal_review(tmp_path)
    assert review["review_classification"] == "proposal_insufficient_context_heavy"


def test_next_move_proposal_review_classifies_venue_thrash(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "glow/orchestration/orchestration_next_move_proposals.jsonl",
        [
            _proposal_row(relation_posture="affirming", venue="internal_direct_execution", executability="executable_now"),
            _proposal_row(relation_posture="affirming", venue="codex_implementation", executability="stageable_external_work_order"),
            _proposal_row(relation_posture="affirming", venue="internal_direct_execution", executability="executable_now"),
            _proposal_row(relation_posture="affirming", venue="codex_implementation", executability="stageable_external_work_order"),
            _proposal_row(relation_posture="affirming", venue="internal_direct_execution", executability="executable_now"),
        ],
    )

    review = derive_next_move_proposal_review(tmp_path)
    assert review["review_classification"] == "proposal_venue_thrash"


def test_next_move_proposal_review_classifies_mixed_stress(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "glow/orchestration/orchestration_next_move_proposals.jsonl",
        [
            _proposal_row(
                relation_posture="escalating",
                venue="operator_decision_required",
                executability="blocked_operator_required",
                requires_operator=True,
            ),
            _proposal_row(
                relation_posture="escalating",
                venue="operator_decision_required",
                executability="blocked_operator_required",
                requires_operator=True,
            ),
            _proposal_row(
                relation_posture="holding",
                venue="internal_direct_execution",
                executability="no_action_recommended",
            ),
            _proposal_row(
                relation_posture="holding",
                venue="internal_direct_execution",
                executability="no_action_recommended",
            ),
        ],
    )

    review = derive_next_move_proposal_review(tmp_path)
    assert review["review_classification"] == "mixed_proposal_stress"


def test_next_move_proposal_review_classifies_insufficient_history(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "glow/orchestration/orchestration_next_move_proposals.jsonl",
        [
            _proposal_row(relation_posture="affirming", venue="internal_direct_execution", executability="executable_now"),
            _proposal_row(relation_posture="holding", venue="codex_implementation", executability="no_action_recommended"),
        ],
    )

    review = derive_next_move_proposal_review(tmp_path)
    assert review["review_classification"] == "insufficient_history"


def test_proposal_packet_continuity_classifies_coherent(tmp_path: Path) -> None:
    proposals = [
        _proposal_row(relation_posture="affirming", venue="codex_implementation", executability="stageable_external_work_order"),
        _proposal_row(relation_posture="nudging", venue="deep_research_audit", executability="stageable_external_work_order"),
        _proposal_row(relation_posture="affirming", venue="internal_direct_execution", executability="executable_now"),
    ]
    packets = [
        _packet_row(proposal_id=str(proposals[0]["proposal_id"]), packet_id="packet-coherent-1"),
        _packet_row(proposal_id=str(proposals[1]["proposal_id"]), packet_id="packet-coherent-2", venue="deep_research_audit"),
        _packet_row(proposal_id=str(proposals[2]["proposal_id"]), packet_id="packet-coherent-3", venue="internal_direct_execution"),
    ]
    _write_jsonl(tmp_path / "glow/orchestration/orchestration_next_move_proposals.jsonl", proposals)
    _write_jsonl(tmp_path / "glow/orchestration/orchestration_handoff_packets.jsonl", packets)

    review = derive_proposal_packet_continuity_review(tmp_path)
    assert review["review_classification"] == "coherent_proposal_packet_continuity"
    assert review["summary"]["stable_active_packet_usually_emerges"] is True
    assert review["summary"]["continuity_signals"]["stabilized_into_one_active_packet"] is True
    assert review["summary"]["continuity_signals"]["holds_materially_shaped_recent_path"] is False
    assert review["summary"]["boundaries"]["diagnostic_only"] is True


def test_proposal_packet_continuity_classifies_hold_heavy(tmp_path: Path) -> None:
    proposals = [
        _proposal_row(relation_posture="holding", venue="operator_decision_required", executability="blocked_operator_required"),
        _proposal_row(relation_posture="holding", venue="operator_decision_required", executability="blocked_operator_required"),
        _proposal_row(relation_posture="holding", venue="operator_decision_required", executability="blocked_operator_required"),
    ]
    briefs = [
        {
            "source_next_move_proposal_ref": {"proposal_id": str(proposals[0]["proposal_id"])},
            "source_packetization_gate_ref": {"packetization_outcome": "packetization_hold_operator_review"},
        },
        {
            "source_next_move_proposal_ref": {"proposal_id": str(proposals[1]["proposal_id"])},
            "source_packetization_gate_ref": {"packetization_outcome": "packetization_hold_insufficient_confidence"},
        },
        {
            "source_next_move_proposal_ref": {"proposal_id": str(proposals[2]["proposal_id"])},
            "source_packetization_gate_ref": {"packetization_outcome": "packetization_hold_fragmentation"},
        },
    ]
    _write_jsonl(tmp_path / "glow/orchestration/orchestration_next_move_proposals.jsonl", proposals)
    _write_jsonl(tmp_path / "glow/orchestration/operator_action_briefs.jsonl", briefs)

    review = derive_proposal_packet_continuity_review(tmp_path)
    assert review["review_classification"] == "hold_heavy_continuity"
    assert review["continuity_counts"]["hold_related_count"] >= 3
    assert review["summary"]["continuity_signals"]["holds_materially_shaped_recent_path"] is True


def test_proposal_packet_continuity_classifies_redirect_heavy(tmp_path: Path) -> None:
    proposals = [
        _proposal_row(relation_posture="escalating", venue="codex_implementation", executability="stageable_external_work_order"),
        _proposal_row(relation_posture="escalating", venue="deep_research_audit", executability="stageable_external_work_order"),
        _proposal_row(relation_posture="escalating", venue="internal_direct_execution", executability="executable_now"),
    ]
    packets = [
        _packet_row(
            proposal_id=str(proposals[0]["proposal_id"]),
            packet_id="packet-redirect-1",
            refresh_reason="operator_redirected_venue_refresh",
        ),
        _packet_row(
            proposal_id=str(proposals[1]["proposal_id"]),
            packet_id="packet-redirect-2",
            refresh_reason="operator_redirected_venue_refresh",
        ),
        _packet_row(proposal_id=str(proposals[2]["proposal_id"]), packet_id="packet-redirect-3"),
    ]
    receipts = [
        {"source_next_move_proposal_ref": {"proposal_id": str(proposals[0]["proposal_id"])}, "resolution_kind": "redirected_venue"},
        {"source_next_move_proposal_ref": {"proposal_id": str(proposals[1]["proposal_id"])}, "resolution_kind": "redirected_venue"},
    ]
    _write_jsonl(tmp_path / "glow/orchestration/orchestration_next_move_proposals.jsonl", proposals)
    _write_jsonl(tmp_path / "glow/orchestration/orchestration_handoff_packets.jsonl", packets)
    _write_jsonl(tmp_path / "glow/orchestration/operator_resolution_receipts.jsonl", receipts)

    review = derive_proposal_packet_continuity_review(tmp_path)
    assert review["review_classification"] == "redirect_heavy_continuity"
    assert review["continuity_counts"]["redirect_related_count"] >= 2
    assert review["summary"]["continuity_signals"]["redirects_materially_shaped_recent_path"] is True


def test_proposal_packet_continuity_classifies_repacketization_churn(tmp_path: Path) -> None:
    proposals = [
        _proposal_row(relation_posture="affirming", venue="codex_implementation", executability="stageable_external_work_order"),
        _proposal_row(relation_posture="affirming", venue="deep_research_audit", executability="stageable_external_work_order"),
        _proposal_row(relation_posture="affirming", venue="internal_direct_execution", executability="executable_now"),
    ]
    packets = [
        _packet_row(
            proposal_id=str(proposals[0]["proposal_id"]),
            packet_id="packet-churn-1",
            supersedes="packet-churn-0",
            repacketized=True,
            current_candidate=False,
        ),
        _packet_row(
            proposal_id=str(proposals[1]["proposal_id"]),
            packet_id="packet-churn-2",
            supersedes="packet-churn-1",
            repacketized=True,
            current_candidate=False,
        ),
        _packet_row(
            proposal_id=str(proposals[2]["proposal_id"]),
            packet_id="packet-churn-3",
            supersedes="packet-churn-2",
            repacketized=True,
            current_candidate=False,
        ),
    ]
    _write_jsonl(tmp_path / "glow/orchestration/orchestration_next_move_proposals.jsonl", proposals)
    _write_jsonl(tmp_path / "glow/orchestration/orchestration_handoff_packets.jsonl", packets)

    review = derive_proposal_packet_continuity_review(tmp_path)
    assert review["review_classification"] == "repacketization_churn"
    assert review["summary"]["stable_active_packet_usually_emerges"] is False
    assert review["summary"]["continuity_signals"]["repacketization_prevented_stable_continuity"] is True


def test_proposal_packet_continuity_classifies_fragmented(tmp_path: Path) -> None:
    proposals = [
        _proposal_row(relation_posture="affirming", venue="codex_implementation", executability="stageable_external_work_order"),
        _proposal_row(relation_posture="nudging", venue="deep_research_audit", executability="stageable_external_work_order"),
        _proposal_row(relation_posture="affirming", venue="internal_direct_execution", executability="executable_now"),
    ]
    packets = [
        _packet_row(
            proposal_id=str(proposals[0]["proposal_id"]),
            packet_id="packet-frag-1",
            supersedes="missing-parent-packet",
        ),
    ]
    _write_jsonl(tmp_path / "glow/orchestration/orchestration_next_move_proposals.jsonl", proposals)
    _write_jsonl(tmp_path / "glow/orchestration/orchestration_handoff_packets.jsonl", packets)

    review = derive_proposal_packet_continuity_review(tmp_path)
    assert review["review_classification"] == "fragmented_continuity"
    assert review["continuity_counts"]["broken_lineage_count"] >= 1
    assert review["summary"]["continuity_signals"]["lineage_fragmentation_present"] is True


def test_proposal_packet_continuity_classifies_insufficient_history(tmp_path: Path) -> None:
    proposals = [
        _proposal_row(relation_posture="affirming", venue="codex_implementation", executability="stageable_external_work_order"),
        _proposal_row(relation_posture="affirming", venue="deep_research_audit", executability="stageable_external_work_order"),
    ]
    _write_jsonl(tmp_path / "glow/orchestration/orchestration_next_move_proposals.jsonl", proposals)

    review = derive_proposal_packet_continuity_review(tmp_path)
    assert review["review_classification"] == "insufficient_history"
    assert review["summary"]["boundaries"]["non_authoritative"] is True
    assert review["artifacts_read"]["active_packet_candidate_resolver"] == "resolve_active_handoff_packet_candidate"
    assert review["summary"]["continuity_basis"]["packetization_gate_basis"] == "source_packetization_gate_ref.packetization_outcome"
    assert review["decision_power"] == "none"


def test_multi_venue_history_flows_to_consumer_venue_mix_review_and_stays_non_authoritative(
    monkeypatch, tmp_path: Path
) -> None:
    _seed_venue_mix_history(
        tmp_path,
        records=[
            {"intent_kind": "internal_maintenance_execution", "handoff_outcome": "admitted_to_execution_substrate"},
            {"intent_kind": "codex_work_order", "handoff_outcome": "staged_only", "required_authority_posture": "operator_approval_required"},
            {"intent_kind": "deep_research_work_order", "handoff_outcome": "staged_only", "required_authority_posture": "operator_approval_required"},
            {"intent_kind": "internal_maintenance_execution", "handoff_outcome": "admitted_to_execution_substrate"},
        ],
    )
    monkeypatch.setattr("sentientos.scoped_lifecycle_diagnostic.SCOPED_ACTION_IDS", ("sentientos.manifest.generate",))
    monkeypatch.setattr(
        "sentientos.scoped_lifecycle_diagnostic.resolve_scoped_mutation_lifecycle",
        lambda _repo_root, *, action_id, correlation_id: {
            "typed_action_identity": action_id,
            "correlation_id": correlation_id,
            "outcome_class": "success",
        },
    )
    monkeypatch.setattr(
        "sentientos.scoped_lifecycle_diagnostic.synthesize_delegated_judgment",
        lambda _evidence: synthesize_delegated_judgment(_base_evidence()),
    )
    _write_json(tmp_path / "glow/contracts/contract_status.json", {"contracts": []})
    _write_jsonl(
        tmp_path / "pulse/forge_events.jsonl",
        [
            {
                "event": "constitutional_mutation_router_execution",
                "typed_action_id": "sentientos.manifest.generate",
                "correlation_id": "cid-venue-mix-consumer",
            }
        ],
    )

    diagnostic = build_scoped_lifecycle_diagnostic(tmp_path)
    venue_mix_review = diagnostic["orchestration_handoff"]["venue_mix_review"]
    assert venue_mix_review["review_classification"] in {
        "balanced_recent_venue_mix",
        "internal_execution_heavy",
        "codex_heavy",
        "deep_research_heavy",
        "operator_escalation_heavy",
        "mixed_venue_stress",
        "insufficient_history",
    }
    assert venue_mix_review["non_authoritative"] is True
    assert venue_mix_review["diagnostic_only"] is True
    assert venue_mix_review["decision_power"] == "none"
    assert venue_mix_review["review_only"] is True


def test_next_venue_recommendation_flows_to_consumer_and_stays_non_authoritative(
    monkeypatch, tmp_path: Path
) -> None:
    _seed_venue_mix_history(
        tmp_path,
        records=[
            {"intent_kind": "codex_work_order", "handoff_outcome": "staged_only", "required_authority_posture": "operator_approval_required"},
            {"intent_kind": "codex_work_order", "handoff_outcome": "staged_only", "required_authority_posture": "operator_approval_required"},
            {"intent_kind": "internal_maintenance_execution", "handoff_outcome": "admitted_to_execution_substrate"},
            {"intent_kind": "deep_research_work_order", "handoff_outcome": "staged_only", "required_authority_posture": "operator_approval_required"},
        ],
    )
    monkeypatch.setattr("sentientos.scoped_lifecycle_diagnostic.SCOPED_ACTION_IDS", ("sentientos.manifest.generate",))
    monkeypatch.setattr(
        "sentientos.scoped_lifecycle_diagnostic.resolve_scoped_mutation_lifecycle",
        lambda _repo_root, *, action_id, correlation_id: {
            "typed_action_identity": action_id,
            "correlation_id": correlation_id,
            "outcome_class": "success",
        },
    )
    monkeypatch.setattr(
        "sentientos.scoped_lifecycle_diagnostic.synthesize_delegated_judgment",
        lambda _evidence: synthesize_delegated_judgment(_base_evidence()),
    )
    _write_json(tmp_path / "glow/contracts/contract_status.json", {"contracts": []})
    _write_jsonl(
        tmp_path / "pulse/forge_events.jsonl",
        [
            {
                "event": "constitutional_mutation_router_execution",
                "typed_action_id": "sentientos.manifest.generate",
                "correlation_id": "cid-next-venue-consumer",
            }
        ],
    )

    diagnostic = build_scoped_lifecycle_diagnostic(tmp_path)
    next_venue = diagnostic["orchestration_handoff"]["next_venue_recommendation"]
    delegated_venue = diagnostic["delegated_judgment"]["recommended_venue"]

    assert next_venue["current_delegated_judgment_venue"] == delegated_venue
    assert next_venue["next_venue_recommendation"] in {
        "prefer_internal_execution",
        "prefer_codex_implementation",
        "prefer_deep_research_audit",
        "prefer_operator_decision",
        "hold_current_venue_mix",
        "insufficient_context",
    }
    assert next_venue["relation_to_delegated_judgment"] in {
        "affirming",
        "nudging",
        "holding",
        "escalating",
        "insufficient_context",
    }
    assert next_venue["diagnostic_only"] is True
    assert next_venue["non_authoritative"] is True
    assert next_venue["decision_power"] == "none"
    assert next_venue["recommendation_only"] is True
    assert next_venue["does_not_execute_or_route_work"] is True
    assert next_venue["does_not_override_delegated_judgment"] is True


def test_next_move_proposal_flows_to_consumer_artifact_and_stays_non_authoritative(
    monkeypatch, tmp_path: Path
) -> None:
    _seed_venue_mix_history(
        tmp_path,
        records=[
            {"intent_kind": "internal_maintenance_execution", "handoff_outcome": "admitted_to_execution_substrate"},
            {"intent_kind": "codex_work_order", "handoff_outcome": "staged_only", "required_authority_posture": "operator_approval_required"},
            {"intent_kind": "internal_maintenance_execution", "handoff_outcome": "admitted_to_execution_substrate"},
            {"intent_kind": "internal_maintenance_execution", "handoff_outcome": "admitted_to_execution_substrate"},
        ],
    )
    monkeypatch.setattr("sentientos.scoped_lifecycle_diagnostic.SCOPED_ACTION_IDS", ("sentientos.manifest.generate",))
    monkeypatch.setattr(
        "sentientos.scoped_lifecycle_diagnostic.resolve_scoped_mutation_lifecycle",
        lambda _repo_root, *, action_id, correlation_id: {
            "typed_action_identity": action_id,
            "correlation_id": correlation_id,
            "outcome_class": "success",
        },
    )
    monkeypatch.setattr(
        "sentientos.scoped_lifecycle_diagnostic.synthesize_delegated_judgment",
        lambda _evidence: synthesize_delegated_judgment(_base_evidence()),
    )
    _write_json(tmp_path / "glow/contracts/contract_status.json", {"contracts": []})
    _write_jsonl(
        tmp_path / "pulse/forge_events.jsonl",
        [
            {
                "event": "constitutional_mutation_router_execution",
                "typed_action_id": "sentientos.manifest.generate",
                "correlation_id": "cid-next-move-proposal-consumer",
            }
        ],
    )

    diagnostic = build_scoped_lifecycle_diagnostic(tmp_path)
    proposal = diagnostic["orchestration_handoff"]["next_move_proposal"]
    assert proposal["relation_posture"] in {"affirming", "nudging", "holding", "escalating", "insufficient_context"}
    assert proposal["executability_classification"] in {
        "executable_now",
        "stageable_external_work_order",
        "blocked_operator_required",
        "blocked_insufficient_context",
        "no_action_recommended",
    }
    assert proposal["proposal_only"] is True
    assert proposal["diagnostic_only"] is True
    assert proposal["non_authoritative"] is True
    assert proposal["decision_power"] == "none"
    assert proposal["does_not_execute_or_route_work"] is True
    assert proposal["requires_operator_or_existing_handoff_path"] is True
    assert proposal["ledger_path"] == "glow/orchestration/orchestration_next_move_proposals.jsonl"
    rows = (tmp_path / proposal["ledger_path"]).read_text(encoding="utf-8").splitlines()
    assert rows
    persisted = json.loads(rows[-1])
    assert persisted["proposal_id"] == proposal["proposal_id"]


def test_codex_next_move_proposal_becomes_typed_staged_handoff_packet() -> None:
    delegated = synthesize_delegated_judgment(_base_evidence())
    outcome_review = {
        "review_classification": "clean_recent_orchestration",
        "records_considered": 4,
        "condition_flags": {"blocked_heavy": False, "failure_heavy": False, "stall_heavy": False},
    }
    venue_mix_review = {"review_classification": "balanced_recent_venue_mix", "records_considered": 4}
    attention = {"operator_attention_recommendation": "none"}
    next_venue = derive_next_venue_recommendation(delegated, outcome_review, venue_mix_review, attention)
    proposal = synthesize_next_move_proposal(delegated, next_venue, outcome_review, venue_mix_review, attention)

    packet = synthesize_handoff_packet(proposal, delegated, created_at="2026-04-12T00:00:00Z")

    assert packet["target_venue"] == "codex_implementation"
    assert packet["packet_status"] == "ready_for_external_trigger"
    assert packet["venue_payload"]["staged_only_not_directly_invoked_here"] is True
    assert packet["readiness"]["staged_only"] is True
    assert packet["does_not_execute_or_route_work"] is True


def test_deep_research_next_move_proposal_becomes_typed_staged_handoff_packet() -> None:
    delegated = synthesize_delegated_judgment({**_base_evidence(), "governance_ambiguity_signal": True})
    outcome_review = {
        "review_classification": "mixed_orchestration_stress",
        "records_considered": 4,
        "condition_flags": {"blocked_heavy": False, "failure_heavy": True, "stall_heavy": False},
    }
    venue_mix_review = {"review_classification": "deep_research_heavy", "records_considered": 4}
    attention = {"operator_attention_recommendation": "review_mixed_orchestration_stress"}
    next_venue = derive_next_venue_recommendation(delegated, outcome_review, venue_mix_review, attention)
    proposal = synthesize_next_move_proposal(delegated, next_venue, outcome_review, venue_mix_review, attention)

    packet = synthesize_handoff_packet(proposal, delegated, created_at="2026-04-12T00:00:00Z")

    assert packet["target_venue"] == "deep_research_audit"
    assert packet["packet_status"] == "ready_for_external_trigger"
    assert packet["venue_payload"]["staged_only_not_directly_invoked_here"] is True
    assert packet["readiness"]["ready_for_external_trigger"] is True
    assert packet["does_not_invoke_external_tools"] is True


def test_internal_execution_next_move_proposal_becomes_internal_handoff_packet_with_honest_readiness() -> None:
    delegated = synthesize_delegated_judgment(
        {
            **_base_evidence(),
            "admission_denied_ratio": 0.75,
            "admission_sample_count": 8,
            "executor_failure_ratio": 0.4,
            "executor_sample_count": 8,
        }
    )
    outcome_review = {
        "review_classification": "clean_recent_orchestration",
        "records_considered": 4,
        "condition_flags": {"blocked_heavy": False, "failure_heavy": False, "stall_heavy": False},
    }
    venue_mix_review = {"review_classification": "internal_execution_heavy", "records_considered": 4}
    attention = {"operator_attention_recommendation": "none"}
    next_venue = derive_next_venue_recommendation(delegated, outcome_review, venue_mix_review, attention)
    proposal = synthesize_next_move_proposal(delegated, next_venue, outcome_review, venue_mix_review, attention)

    packet = synthesize_handoff_packet(proposal, delegated, created_at="2026-04-12T00:00:00Z")

    assert packet["target_venue"] == "internal_direct_execution"
    assert packet["packet_status"] == "ready_for_internal_trigger"
    assert packet["venue_payload"]["target_substrate"] == "task_admission_executor"
    assert packet["readiness"]["ready_for_internal_trigger"] is True
    assert packet["readiness"]["staged_only"] is False


def test_operator_required_and_insufficient_context_packets_remain_honestly_blocked() -> None:
    delegated_operator = synthesize_delegated_judgment(_base_evidence())
    blocked_operator_proposal = {
        "proposal_id": "proposal-blocked-operator",
        "proposed_next_action": {"proposed_venue": "codex_implementation", "proposed_posture": "escalate"},
        "executability_classification": "blocked_operator_required",
        "operator_escalation_requirement_state": {
            "requires_operator_or_escalation": True,
            "attention_signal": "inspect_handoff_blocks",
            "escalation_classification": "escalate_for_operator_priority",
        },
        "source_delegated_judgment": {"source_judgment_linkage_id": "jdg-link-1"},
    }
    operator_packet = synthesize_handoff_packet(
        blocked_operator_proposal,
        delegated_operator,
        created_at="2026-04-12T00:00:00Z",
    )
    assert operator_packet["packet_status"] == "blocked_operator_required"
    assert operator_packet["readiness"]["blocked"] is True

    delegated_missing = synthesize_delegated_judgment(
        {**_base_evidence(), "records_considered": 0, "admission_sample_count": 0, "executor_sample_count": 0}
    )
    blocked_context_proposal = {
        "proposal_id": "proposal-blocked-context",
        "proposed_next_action": {"proposed_venue": "insufficient_context", "proposed_posture": "hold"},
        "executability_classification": "blocked_insufficient_context",
        "operator_escalation_requirement_state": {
            "requires_operator_or_escalation": False,
            "attention_signal": "insufficient_context",
            "escalation_classification": "no_escalation_needed",
        },
        "source_delegated_judgment": {"source_judgment_linkage_id": "jdg-link-2"},
    }
    context_packet = synthesize_handoff_packet(
        blocked_context_proposal,
        delegated_missing,
        created_at="2026-04-12T00:00:00Z",
    )
    assert context_packet["packet_status"] == "blocked_insufficient_context"
    assert context_packet["readiness"]["blocked"] is True


def test_packetization_gate_can_hold_otherwise_stageable_packet_without_new_authority() -> None:
    delegated = synthesize_delegated_judgment(_base_evidence())
    proposal = {
        "proposal_id": "proposal-stageable-held-by-gate",
        "relation_posture": "affirming",
        "proposed_next_action": {"proposed_venue": "codex_implementation", "proposed_posture": "expand"},
        "executability_classification": "stageable_external_work_order",
        "operator_escalation_requirement_state": {
            "requires_operator_or_escalation": False,
            "attention_signal": "review_mixed_orchestration_stress",
            "escalation_classification": "no_escalation_needed",
        },
        "source_delegated_judgment": {"source_judgment_linkage_id": "jdg-link-gated"},
    }
    packet = synthesize_handoff_packet(
        proposal,
        delegated,
        {"review_classification": "mixed_proposal_stress", "records_considered": 6},
        {"trust_confidence_posture": "stressed_but_usable", "pressure_summary": {"primary_pressure": "mixed_stress"}},
        {"operator_attention_recommendation": "review_mixed_orchestration_stress"},
        created_at="2026-04-12T00:00:00Z",
    )
    assert packet["packetization_gate"]["packetization_outcome"] == "packetization_hold_escalation_required"
    assert packet["packet_status"] == "blocked_operator_required"
    assert packet["readiness"]["blocked"] is True
    assert packet["does_not_change_admission_or_execution"] is True
    assert packet["decision_power"] == "none"


def test_operator_review_hold_produces_operator_action_brief_with_approve_class() -> None:
    proposal = {
        "proposal_id": "proposal-hold-operator-review",
        "relation_posture": "affirming",
        "proposed_next_action": {"proposed_venue": "internal_direct_execution", "proposed_posture": "expand"},
        "executability_classification": "executable_now",
        "operator_escalation_requirement_state": {
            "requires_operator_or_escalation": True,
            "attention_signal": "observe",
            "escalation_classification": "no_escalation_needed",
        },
        "source_delegated_judgment": {"source_judgment_linkage_id": "jdg-link-operator-brief"},
    }
    gate = derive_packetization_gate(
        proposal,
        {"review_classification": "coherent_recent_proposals", "records_considered": 5},
        {"trust_confidence_posture": "trusted_for_bounded_use", "pressure_summary": {"primary_pressure": "none"}},
        {"operator_attention_recommendation": "observe"},
    )
    brief = synthesize_operator_action_brief(
        proposal,
        gate,
        {"trust_confidence_posture": "trusted_for_bounded_use", "pressure_summary": {"primary_pressure": "none"}},
        {"operator_attention_recommendation": "observe"},
        next_move_proposal_review={"review_classification": "coherent_recent_proposals"},
        created_at="2026-04-12T00:00:00Z",
    )

    assert gate["packetization_outcome"] == "packetization_hold_operator_review"
    assert brief is not None
    assert brief["intervention_class"] == "approve_and_continue"
    assert brief["source_packetization_gate_ref"]["packetization_outcome"] == "packetization_hold_operator_review"
    assert brief["operator_guidance_only"] is True
    assert brief["does_not_override_packetization_gate"] is True
    assert brief["does_not_create_execution_path"] is True


def test_insufficient_confidence_hold_produces_resolve_context_operator_brief() -> None:
    proposal = {
        "proposal_id": "proposal-hold-insufficient",
        "relation_posture": "insufficient_context",
        "proposed_next_action": {"proposed_venue": "insufficient_context", "proposed_posture": "hold"},
        "executability_classification": "blocked_insufficient_context",
        "operator_escalation_requirement_state": {
            "requires_operator_or_escalation": False,
            "attention_signal": "insufficient_context",
            "escalation_classification": "no_escalation_needed",
        },
        "source_delegated_judgment": {"source_judgment_linkage_id": "jdg-link-insufficient-brief"},
    }
    gate = derive_packetization_gate(
        proposal,
        {"review_classification": "proposal_insufficient_context_heavy", "records_considered": 3},
        {"trust_confidence_posture": "insufficient_history", "pressure_summary": {"primary_pressure": "insufficient_history"}},
        {"operator_attention_recommendation": "insufficient_context"},
    )
    brief = synthesize_operator_action_brief(
        proposal,
        gate,
        {"trust_confidence_posture": "insufficient_history", "pressure_summary": {"primary_pressure": "insufficient_history"}},
        {"operator_attention_recommendation": "insufficient_context"},
        next_move_proposal_review={"review_classification": "proposal_insufficient_context_heavy"},
    )

    assert gate["packetization_outcome"] == "packetization_hold_insufficient_confidence"
    assert brief is not None
    assert brief["intervention_class"] == "resolve_insufficient_context"
    assert brief["target_venue_or_posture"] == "insufficient_history"


def test_fragmentation_hold_produces_review_fragmentation_operator_brief() -> None:
    proposal = {
        "proposal_id": "proposal-hold-fragmentation",
        "relation_posture": "affirming",
        "proposed_next_action": {"proposed_venue": "internal_direct_execution", "proposed_posture": "expand"},
        "executability_classification": "executable_now",
        "operator_escalation_requirement_state": {
            "requires_operator_or_escalation": False,
            "attention_signal": "observe",
            "escalation_classification": "no_escalation_needed",
        },
        "source_delegated_judgment": {"source_judgment_linkage_id": "jdg-link-fragmentation-brief"},
    }
    gate = derive_packetization_gate(
        proposal,
        {"review_classification": "coherent_recent_proposals", "records_considered": 6},
        {"trust_confidence_posture": "fragmented_or_unreliable", "pressure_summary": {"primary_pressure": "fragmentation"}},
        {"operator_attention_recommendation": "observe"},
    )
    brief = synthesize_operator_action_brief(
        proposal,
        gate,
        {"trust_confidence_posture": "fragmented_or_unreliable", "pressure_summary": {"primary_pressure": "fragmentation"}},
        {"operator_attention_recommendation": "observe"},
        next_move_proposal_review={"review_classification": "coherent_recent_proposals"},
    )

    assert gate["packetization_outcome"] == "packetization_hold_fragmentation"
    assert brief is not None
    assert brief["intervention_class"] == "review_fragmentation"
    assert brief["target_venue_or_posture"] == "fragmented_or_unreliable"


def test_stageable_external_hold_can_produce_manual_external_trigger_operator_brief() -> None:
    proposal = {
        "proposal_id": "proposal-hold-manual-external-trigger",
        "relation_posture": "escalating",
        "proposed_next_action": {"proposed_venue": "codex_implementation", "proposed_posture": "escalate"},
        "executability_classification": "stageable_external_work_order",
        "operator_escalation_requirement_state": {
            "requires_operator_or_escalation": True,
            "attention_signal": "inspect_handoff_blocks",
            "escalation_classification": "escalate_for_operator_priority",
        },
        "source_delegated_judgment": {"source_judgment_linkage_id": "jdg-link-manual-trigger"},
    }
    gate = derive_packetization_gate(
        proposal,
        {"review_classification": "proposal_escalation_heavy", "records_considered": 7},
        {"trust_confidence_posture": "stressed_but_usable", "pressure_summary": {"primary_pressure": "escalation_operator_dependence"}},
        {"operator_attention_recommendation": "inspect_handoff_blocks"},
    )
    brief = synthesize_operator_action_brief(
        proposal,
        gate,
        {"trust_confidence_posture": "stressed_but_usable", "pressure_summary": {"primary_pressure": "escalation_operator_dependence"}},
        {"operator_attention_recommendation": "inspect_handoff_blocks"},
        next_move_proposal_review={"review_classification": "proposal_escalation_heavy"},
    )

    assert gate["packetization_outcome"] == "packetization_hold_operator_review"
    assert brief is not None
    assert brief["intervention_class"] == "manual_external_trigger_required"
    assert brief["target_venue_or_posture"] == "codex_implementation"
    assert "manually_trigger_staged_external_venue" in brief["requested_operator_action"]


def test_packetization_allowed_does_not_fabricate_operator_action_brief() -> None:
    proposal = {
        "proposal_id": "proposal-allowed-no-brief",
        "relation_posture": "affirming",
        "proposed_next_action": {"proposed_venue": "internal_direct_execution", "proposed_posture": "expand"},
        "executability_classification": "executable_now",
        "operator_escalation_requirement_state": {
            "requires_operator_or_escalation": False,
            "attention_signal": "none",
            "escalation_classification": "no_escalation_needed",
        },
        "source_delegated_judgment": {"source_judgment_linkage_id": "jdg-link-no-brief"},
    }
    gate = derive_packetization_gate(
        proposal,
        {"review_classification": "coherent_recent_proposals", "records_considered": 8},
        {"trust_confidence_posture": "trusted_for_bounded_use", "pressure_summary": {"primary_pressure": "none"}},
        {"operator_attention_recommendation": "none"},
    )
    brief = synthesize_operator_action_brief(
        proposal,
        gate,
        {"trust_confidence_posture": "trusted_for_bounded_use", "pressure_summary": {"primary_pressure": "none"}},
        {"operator_attention_recommendation": "none"},
        next_move_proposal_review={"review_classification": "coherent_recent_proposals"},
    )
    assert gate["packetization_outcome"] == "packetization_allowed"
    assert brief is None


def test_operator_action_brief_artifact_is_append_only_and_proof_visible(tmp_path: Path) -> None:
    brief_one = {
        "schema_version": "operator_action_brief.v1",
        "operator_action_brief_id": "oab-first",
        "intervention_class": "resolve_insufficient_context",
        "source_next_move_proposal_ref": {"proposal_id": "proposal-a"},
        "source_packetization_gate_ref": {"packetization_outcome": "packetization_hold_insufficient_confidence"},
        "operator_guidance_only": True,
        "non_authoritative": True,
        "decision_power": "none",
    }
    brief_two = {
        **brief_one,
        "operator_action_brief_id": "oab-second",
        "intervention_class": "review_fragmentation",
        "source_next_move_proposal_ref": {"proposal_id": "proposal-b"},
    }
    ledger_path = append_operator_action_brief_ledger(tmp_path, brief_one)
    append_operator_action_brief_ledger(tmp_path, brief_two)

    rows = ledger_path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2
    first = json.loads(rows[0])
    second = json.loads(rows[1])
    assert first["operator_action_brief_id"] == "oab-first"
    assert second["operator_action_brief_id"] == "oab-second"
    assert ledger_path == tmp_path / "glow/orchestration/operator_action_briefs.jsonl"


def test_operator_resolution_receipt_artifact_is_append_only_and_proof_visible(tmp_path: Path) -> None:
    brief = _operator_brief_for_receipt_flow()
    append_operator_action_brief_ledger(tmp_path, brief)
    receipt_one = ingest_operator_resolution_receipt(
        tmp_path,
        operator_action_brief_id=str(brief["operator_action_brief_id"]),
        resolution_kind="approved_continue",
        operator_note="approved after review",
        updated_context_refs=["glow/orchestration/operator_action_briefs.jsonl#1"],
        created_at="2026-04-12T00:01:00Z",
    )
    receipt_two = ingest_operator_resolution_receipt(
        tmp_path,
        operator_action_brief_id=str(brief["operator_action_brief_id"]),
        resolution_kind="declined",
        operator_note="declined in later pass",
        created_at="2026-04-12T00:02:00Z",
    )

    ledger_path = tmp_path / "glow/orchestration/operator_resolution_receipts.jsonl"
    rows = ledger_path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2
    first = json.loads(rows[0])
    second = json.loads(rows[1])
    assert first["operator_resolution_receipt_id"] == receipt_one["operator_resolution_receipt_id"]
    assert first["resolution_kind"] == "approved_continue"
    assert second["operator_resolution_receipt_id"] == receipt_two["operator_resolution_receipt_id"]
    assert second["resolution_kind"] == "declined"


def test_operator_resolution_ingestion_supports_multiple_resolution_kinds() -> None:
    with TemporaryDirectory() as tmp_dir:
        repo_root = Path(tmp_dir)
        brief = _operator_brief_for_receipt_flow()
        append_operator_action_brief_ledger(repo_root, brief)

        supplied = ingest_operator_resolution_receipt(
            repo_root,
            operator_action_brief_id=str(brief["operator_action_brief_id"]),
            resolution_kind="supplied_missing_context",
            operator_note="added missing context",
            updated_context_refs=["docs/context.md#section"],
            created_at="2026-04-12T00:01:00Z",
        )
        declined = ingest_operator_resolution_receipt(
            repo_root,
            operator_action_brief_id=str(brief["operator_action_brief_id"]),
            resolution_kind="declined",
            operator_note="not approved",
            created_at="2026-04-12T00:02:00Z",
        )
        redirected = ingest_operator_resolution_receipt(
            repo_root,
            operator_action_brief_id=str(brief["operator_action_brief_id"]),
            resolution_kind="redirected_venue",
            operator_note="use deep research instead",
            redirected_venue="deep_research_audit",
            created_at="2026-04-12T00:03:00Z",
        )

        assert supplied["resolution_kind"] == "supplied_missing_context"
        assert supplied["resolution_lifecycle_state"] == "operator_supplied_missing_context"
        assert supplied["ingested_operator_outcome"] is True
        assert supplied["does_not_imply_repo_self-authorization"] is True
        assert supplied["requires_existing_trigger_path_for_any_follow-on_action"] is True
        assert declined["resolution_lifecycle_state"] == "operator_declined"
        assert redirected["resolution_lifecycle_state"] == "operator_redirected"
        assert redirected["redirected_venue"] == "deep_research_audit"


def test_operator_resolution_ingestion_fails_closed_when_brief_missing_or_malformed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="operator action brief not found"):
        ingest_operator_resolution_receipt(
            tmp_path,
            operator_action_brief_id="oab-missing",
            resolution_kind="approved_continue",
            operator_note="missing",
        )

    malformed = {
        "schema_version": "operator_action_brief.v1",
        "operator_action_brief_id": "oab-malformed",
        "source_next_move_proposal_ref": {},
        "source_packetization_gate_ref": {},
    }
    append_operator_action_brief_ledger(tmp_path, malformed)
    with pytest.raises(ValueError, match="malformed"):
        ingest_operator_resolution_receipt(
            tmp_path,
            operator_action_brief_id="oab-malformed",
            resolution_kind="approved_continue",
            operator_note="should fail",
        )


def test_operator_brief_lifecycle_visibility_tracks_received_resolution() -> None:
    with TemporaryDirectory() as tmp_dir:
        repo_root = Path(tmp_dir)
        brief = _operator_brief_for_receipt_flow()
        append_operator_action_brief_ledger(repo_root, brief)
        before = resolve_operator_action_brief_lifecycle(repo_root, brief)
        ingest_operator_resolution_receipt(
            repo_root,
            operator_action_brief_id=str(brief["operator_action_brief_id"]),
            resolution_kind="approved_continue",
            operator_note="continue",
            created_at="2026-04-12T00:01:00Z",
        )
        after = resolve_operator_action_brief_lifecycle(repo_root, brief)

        assert before["lifecycle_state"] == "brief_emitted"
        assert before["operator_resolution_received"] is False
        assert before["awaiting_operator_input"] is True
        assert after["lifecycle_state"] == "operator_approved_continue"
        assert after["operator_resolution_received"] is True
        assert after["has_operator_guidance"] is True
        assert after["does_not_imply_repo_execution"] is True


def test_operator_approved_continue_can_relieve_operator_hold_without_execution_trigger() -> None:
    proposal = {
        "proposed_next_action": {"proposed_venue": "codex_implementation", "proposed_posture": "expand"},
        "executability_classification": "stageable_external_work_order",
        "relation_posture": "affirming",
        "operator_escalation_requirement_state": {
            "requires_operator_or_escalation": True,
            "attention_signal": "none",
            "escalation_classification": "escalate_for_operator_priority",
        },
    }
    review = {"review_classification": "coherent_recent_proposals"}
    trust = {"trust_confidence_posture": "caution_required", "pressure_summary": {"primary_pressure": "none"}}
    attention = {"operator_attention_recommendation": "observe"}
    influence = derive_operator_resolution_influence(
        {"resolution_kind": "approved_continue", "operator_resolution_receipt_id": "orr-1"}
    )

    gate = derive_packetization_gate(proposal, review, trust, attention, influence)
    assert gate["packetization_outcome"] == "packetization_allowed_with_caution"
    assert gate["packetization_allowed"] is True
    assert gate["does_not_change_admission_or_execution"] is True
    assert gate["does_not_imply_execution"] is True


def test_operator_supplied_context_can_relieve_insufficient_context_hold_conservatively() -> None:
    proposal = {
        "proposed_next_action": {"proposed_venue": "codex_implementation", "proposed_posture": "expand"},
        "executability_classification": "stageable_external_work_order",
        "relation_posture": "affirming",
        "operator_escalation_requirement_state": {
            "requires_operator_or_escalation": False,
            "attention_signal": "none",
            "escalation_classification": "no_escalation_needed",
        },
    }
    review = {"review_classification": "proposal_insufficient_context_heavy"}
    trust = {"trust_confidence_posture": "caution_required", "pressure_summary": {"primary_pressure": "none"}}
    attention = {"operator_attention_recommendation": "insufficient_context"}
    influence = derive_operator_resolution_influence(
        {
            "resolution_kind": "supplied_missing_context",
            "updated_context_refs": ["docs/context.md#new"],
            "operator_resolution_receipt_id": "orr-2",
        }
    )

    gate = derive_packetization_gate(proposal, review, trust, attention, influence)
    assert gate["packetization_outcome"] == "packetization_allowed_with_caution"
    assert gate["operator_influence"]["operator_context_applied"] is True
    assert gate["does_not_execute_or_route_work"] is True


def test_operator_resolution_does_not_falsely_clear_fragmentation_hold() -> None:
    proposal = {
        "proposed_next_action": {"proposed_venue": "codex_implementation", "proposed_posture": "expand"},
        "executability_classification": "stageable_external_work_order",
        "relation_posture": "affirming",
        "operator_escalation_requirement_state": {"requires_operator_or_escalation": False},
    }
    review = {"review_classification": "coherent_recent_proposals"}
    trust = {"trust_confidence_posture": "fragmented_or_unreliable", "pressure_summary": {"primary_pressure": "fragmentation"}}
    attention = {"operator_attention_recommendation": "observe"}
    influence = derive_operator_resolution_influence(
        {"resolution_kind": "approved_continue", "operator_resolution_receipt_id": "orr-3"}
    )

    gate = derive_packetization_gate(proposal, review, trust, attention, influence)
    assert gate["packetization_outcome"] == "packetization_hold_fragmentation"
    assert gate["packetization_held"] is True


def test_operator_decline_cancel_and_defer_preserve_hold() -> None:
    proposal = {
        "proposed_next_action": {"proposed_venue": "codex_implementation", "proposed_posture": "expand"},
        "executability_classification": "stageable_external_work_order",
        "relation_posture": "affirming",
        "operator_escalation_requirement_state": {
            "requires_operator_or_escalation": True,
            "attention_signal": "none",
            "escalation_classification": "escalate_for_operator_priority",
        },
    }
    review = {"review_classification": "coherent_recent_proposals"}
    trust = {"trust_confidence_posture": "caution_required", "pressure_summary": {"primary_pressure": "none"}}
    attention = {"operator_attention_recommendation": "observe"}

    declined = derive_packetization_gate(
        proposal,
        review,
        trust,
        attention,
        derive_operator_resolution_influence({"resolution_kind": "declined"}),
    )
    cancelled = derive_packetization_gate(
        proposal,
        review,
        trust,
        attention,
        derive_operator_resolution_influence({"resolution_kind": "cancelled"}),
    )
    deferred = derive_packetization_gate(
        proposal,
        review,
        trust,
        attention,
        derive_operator_resolution_influence({"resolution_kind": "deferred"}),
    )
    assert declined["packetization_held"] is True
    assert cancelled["packetization_held"] is True
    assert deferred["packetization_held"] is True


def test_operator_redirect_updates_current_venue_visibility_without_erasing_history() -> None:
    next_venue = {
        "next_venue_recommendation": "prefer_codex_implementation",
        "relation_to_delegated_judgment": "affirming",
    }
    proposal = {
        "proposed_next_action": {"proposed_venue": "codex_implementation", "proposed_posture": "expand"},
        "proposal_id": "proposal-redirect",
    }
    influence = derive_operator_resolution_influence(
        {
            "resolution_kind": "redirected_venue",
            "redirected_venue": "deep_research_audit",
            "operator_resolution_receipt_id": "orr-4",
        }
    )

    adjusted_venue = derive_operator_adjusted_next_venue_recommendation(next_venue, influence)
    adjusted_proposal = derive_operator_adjusted_next_move_proposal_visibility(proposal, influence)
    assert adjusted_venue["original_next_venue_recommendation"] == "prefer_codex_implementation"
    assert adjusted_venue["current_next_venue_recommendation"] == "prefer_deep_research_audit"
    assert adjusted_proposal["operator_feedback"]["original_proposed_venue"] == "codex_implementation"
    assert adjusted_proposal["operator_feedback"]["current_proposed_venue"] == "deep_research_audit"


def test_latest_operator_resolution_for_proposal_is_resolved_from_ledger(tmp_path: Path) -> None:
    brief = _operator_brief_for_receipt_flow()
    append_operator_action_brief_ledger(tmp_path, brief)
    ingest_operator_resolution_receipt(
        tmp_path,
        operator_action_brief_id=str(brief["operator_action_brief_id"]),
        resolution_kind="approved_continue",
        operator_note="continue",
        created_at="2026-04-12T00:01:00Z",
    )
    redirected = ingest_operator_resolution_receipt(
        tmp_path,
        operator_action_brief_id=str(brief["operator_action_brief_id"]),
        resolution_kind="redirected_venue",
        operator_note="redirect",
        redirected_venue="deep_research_audit",
        created_at="2026-04-12T00:02:00Z",
    )
    latest = resolve_latest_operator_resolution_for_proposal(tmp_path, str(brief["source_next_move_proposal_ref"]["proposal_id"]))
    assert latest is not None
    assert latest["resolution_kind"] == "redirected_venue"
    assert latest["operator_resolution_receipt_id"] == redirected["operator_resolution_receipt_id"]


def test_handoff_packet_artifact_is_append_only_and_proof_visible(tmp_path: Path) -> None:
    delegated = synthesize_delegated_judgment(_base_evidence())
    proposal = {
        "proposal_id": "proposal-codex-packet-artifact",
        "proposed_next_action": {"proposed_venue": "codex_implementation", "proposed_posture": "expand"},
        "executability_classification": "stageable_external_work_order",
        "operator_escalation_requirement_state": {
            "requires_operator_or_escalation": False,
            "attention_signal": "none",
            "escalation_classification": "no_escalation_needed",
        },
        "source_delegated_judgment": {"source_judgment_linkage_id": "jdg-link-artifact"},
    }
    packet = synthesize_handoff_packet(proposal, delegated, created_at="2026-04-12T00:00:00Z")
    ledger_path = append_handoff_packet_ledger(tmp_path, packet)
    append_handoff_packet_ledger(tmp_path, {**packet, "handoff_packet_id": "hpk-second"})

    rows = ledger_path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2
    first = json.loads(rows[0])
    second = json.loads(rows[1])
    assert first["packet_status"] == "ready_for_external_trigger"
    assert first["target_venue"] == "codex_implementation"
    assert second["handoff_packet_id"] == "hpk-second"


def test_next_move_proposal_review_flows_to_consumer_and_stays_non_authoritative(
    monkeypatch, tmp_path: Path
) -> None:
    _write_jsonl(
        tmp_path / "glow/orchestration/orchestration_next_move_proposals.jsonl",
        [
            _proposal_row(
                relation_posture="escalating",
                venue="operator_decision_required",
                executability="blocked_operator_required",
                requires_operator=True,
            ),
            _proposal_row(
                relation_posture="escalating",
                venue="operator_decision_required",
                executability="blocked_operator_required",
                requires_operator=True,
            ),
            _proposal_row(
                relation_posture="holding",
                venue="codex_implementation",
                executability="no_action_recommended",
            ),
        ],
    )
    _seed_venue_mix_history(
        tmp_path,
        records=[
            {"intent_kind": "codex_work_order", "handoff_outcome": "staged_only", "required_authority_posture": "operator_approval_required"},
            {"intent_kind": "internal_maintenance_execution", "handoff_outcome": "admitted_to_execution_substrate"},
            {"intent_kind": "codex_work_order", "handoff_outcome": "staged_only", "required_authority_posture": "operator_approval_required"},
        ],
    )
    monkeypatch.setattr("sentientos.scoped_lifecycle_diagnostic.SCOPED_ACTION_IDS", ("sentientos.manifest.generate",))
    monkeypatch.setattr(
        "sentientos.scoped_lifecycle_diagnostic.resolve_scoped_mutation_lifecycle",
        lambda _repo_root, *, action_id, correlation_id: {
            "typed_action_identity": action_id,
            "correlation_id": correlation_id,
            "outcome_class": "success",
        },
    )
    monkeypatch.setattr(
        "sentientos.scoped_lifecycle_diagnostic.synthesize_delegated_judgment",
        lambda _evidence: synthesize_delegated_judgment(_base_evidence()),
    )
    _write_json(tmp_path / "glow/contracts/contract_status.json", {"contracts": []})
    _write_jsonl(
        tmp_path / "pulse/forge_events.jsonl",
        [
            {
                "event": "constitutional_mutation_router_execution",
                "typed_action_id": "sentientos.manifest.generate",
                "correlation_id": "cid-next-move-review-consumer",
            }
        ],
    )

    diagnostic = build_scoped_lifecycle_diagnostic(tmp_path)
    review = diagnostic["orchestration_handoff"]["next_move_proposal_review"]

    assert review["review_classification"] in {
        "coherent_recent_proposals",
        "proposal_escalation_heavy",
        "proposal_hold_heavy",
        "proposal_insufficient_context_heavy",
        "proposal_venue_thrash",
        "mixed_proposal_stress",
        "insufficient_history",
    }
    assert review["recent_counts"]["escalation_or_operator_required"] >= 2
    assert review["summary"]["compact_reason"]
    assert review["diagnostic_only"] is True
    assert review["non_authoritative"] is True
    assert review["decision_power"] == "none"
    assert review["review_only"] is True


def test_handoff_packet_flows_to_diagnostic_consumer_and_stays_non_authoritative(monkeypatch, tmp_path: Path) -> None:
    _seed_venue_mix_history(
        tmp_path,
        records=[
            {"intent_kind": "codex_work_order", "handoff_outcome": "staged_only", "required_authority_posture": "operator_approval_required"},
            {"intent_kind": "internal_maintenance_execution", "handoff_outcome": "admitted_to_execution_substrate"},
            {"intent_kind": "deep_research_work_order", "handoff_outcome": "staged_only", "required_authority_posture": "operator_approval_required"},
        ],
    )
    monkeypatch.setattr("sentientos.scoped_lifecycle_diagnostic.SCOPED_ACTION_IDS", ("sentientos.manifest.generate",))
    monkeypatch.setattr(
        "sentientos.scoped_lifecycle_diagnostic.resolve_scoped_mutation_lifecycle",
        lambda _repo_root, *, action_id, correlation_id: {
            "typed_action_identity": action_id,
            "correlation_id": correlation_id,
            "outcome_class": "success",
        },
    )
    monkeypatch.setattr(
        "sentientos.scoped_lifecycle_diagnostic.synthesize_delegated_judgment",
        lambda _evidence: synthesize_delegated_judgment(_base_evidence()),
    )
    _write_json(tmp_path / "glow/contracts/contract_status.json", {"contracts": []})
    _write_jsonl(
        tmp_path / "pulse/forge_events.jsonl",
        [
            {
                "event": "constitutional_mutation_router_execution",
                "typed_action_id": "sentientos.manifest.generate",
                "correlation_id": "cid-handoff-packet-consumer",
            }
        ],
    )

    diagnostic = build_scoped_lifecycle_diagnostic(tmp_path)
    packet = diagnostic["orchestration_handoff"]["handoff_packet"]
    operator_brief_surface = diagnostic["orchestration_handoff"]["operator_action_brief"]

    assert packet["target_venue"] in {"internal_direct_execution", "codex_implementation", "deep_research_audit", "operator_decision_required", "insufficient_context"}
    assert packet["packet_status"] in {
        "prepared",
        "blocked_operator_required",
        "blocked_insufficient_context",
        "ready_for_external_trigger",
        "ready_for_internal_trigger",
    }
    assert packet["ledger_path"] == "glow/orchestration/orchestration_handoff_packets.jsonl"
    assert packet["packet_only"] is True
    assert packet["diagnostic_only"] is True
    assert packet["non_authoritative"] is True
    assert packet["decision_power"] == "none"
    assert packet["does_not_execute_or_route_work"] is True
    assert packet["requires_operator_or_existing_trigger_path"] is True
    assert "brief_produced" in operator_brief_surface
    assert "loop_held_pending_operator_intervention" in operator_brief_surface
    assert "lifecycle_visibility" in operator_brief_surface
    assert "operator_resolution_received" in operator_brief_surface
    assert operator_brief_surface["resolution_receipt_artifact_linkage"]["ledger_path"] == "glow/orchestration/operator_resolution_receipts.jsonl"
    assert operator_brief_surface["non_sovereign_boundaries"]["does_not_override_packetization_gate"] is True
    assert operator_brief_surface["non_sovereign_boundaries"]["does_not_convert_hold_to_execution"] is True
    assert operator_brief_surface["non_sovereign_boundaries"]["explicit_clarity"] == "ingested operator outcome, not repo execution"


def test_operator_brief_end_to_end_from_hold_to_diagnostic_surface(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("sentientos.scoped_lifecycle_diagnostic.SCOPED_ACTION_IDS", ("sentientos.manifest.generate",))
    monkeypatch.setattr(
        "sentientos.scoped_lifecycle_diagnostic.resolve_scoped_mutation_lifecycle",
        lambda _repo_root, *, action_id, correlation_id: {
            "typed_action_identity": action_id,
            "correlation_id": correlation_id,
            "outcome_class": "success",
        },
    )
    monkeypatch.setattr(
        "sentientos.scoped_lifecycle_diagnostic.synthesize_delegated_judgment",
        lambda _evidence: synthesize_delegated_judgment(
            {
                **_base_evidence(),
                "governance_ambiguity_signal": True,
                "admission_denied_ratio": 0.9,
                "executor_failure_ratio": 0.5,
            }
        ),
    )
    _write_json(tmp_path / "glow/contracts/contract_status.json", {"contracts": []})
    _write_jsonl(
        tmp_path / "pulse/forge_events.jsonl",
        [
            {
                "event": "constitutional_mutation_router_execution",
                "typed_action_id": "sentientos.manifest.generate",
                "correlation_id": "cid-operator-brief-e2e",
            }
        ],
    )

    diagnostic = build_scoped_lifecycle_diagnostic(tmp_path)
    orchestration = diagnostic["orchestration_handoff"]
    gate = orchestration["packetization_gating"]
    brief_surface = orchestration["operator_action_brief"]

    assert gate["packetization_held"] is True
    assert brief_surface["brief_produced"] is True
    assert brief_surface["loop_held_pending_operator_intervention"] is True
    assert brief_surface["intervention_class"] in {
        "approve_and_continue",
        "review_fragmentation",
        "resolve_insufficient_context",
        "resolve_escalation_priority",
        "inspect_recent_orchestration_stress",
        "manual_external_trigger_required",
    }
    assert brief_surface["brief_artifact_linkage"]["ledger_path"] == "glow/orchestration/operator_action_briefs.jsonl"
    assert brief_surface["brief"]["operator_guidance_only"] is True
    assert brief_surface["brief"]["does_not_override_packetization_gate"] is True
    assert brief_surface["brief"]["does_not_create_execution_path"] is True
    assert brief_surface["brief"]["non_authoritative"] is True
    assert brief_surface["awaiting_operator_input"] is True
    assert brief_surface["operator_resolution_received"] is False
    assert brief_surface["lifecycle_visibility"]["lifecycle_state"] == "brief_emitted"


def test_operator_resolution_end_to_end_updates_diagnostic_consumer_without_execution(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("sentientos.scoped_lifecycle_diagnostic.SCOPED_ACTION_IDS", ("sentientos.manifest.generate",))
    monkeypatch.setattr(
        "sentientos.scoped_lifecycle_diagnostic.resolve_scoped_mutation_lifecycle",
        lambda _repo_root, *, action_id, correlation_id: {
            "typed_action_identity": action_id,
            "correlation_id": correlation_id,
            "outcome_class": "success",
        },
    )
    monkeypatch.setattr(
        "sentientos.scoped_lifecycle_diagnostic.synthesize_delegated_judgment",
        lambda _evidence: synthesize_delegated_judgment(
            {
                **_base_evidence(),
                "governance_ambiguity_signal": True,
                "admission_denied_ratio": 0.9,
                "executor_failure_ratio": 0.5,
            }
        ),
    )
    original_append = append_operator_action_brief_ledger

    def _append_and_ingest(repo_root: Path, brief: dict[str, object]) -> Path:
        ledger_path = original_append(repo_root, brief)
        ingest_operator_resolution_receipt(
            repo_root,
            operator_action_brief_id=str(brief["operator_action_brief_id"]),
            resolution_kind="approved_continue",
            operator_note="operator approved continue",
            created_at="2026-04-12T00:01:00Z",
        )
        return ledger_path

    monkeypatch.setattr("sentientos.scoped_lifecycle_diagnostic.append_operator_action_brief_ledger", _append_and_ingest)
    _write_json(tmp_path / "glow/contracts/contract_status.json", {"contracts": []})
    _write_jsonl(
        tmp_path / "pulse/forge_events.jsonl",
        [
            {
                "event": "constitutional_mutation_router_execution",
                "typed_action_id": "sentientos.manifest.generate",
                "correlation_id": "cid-operator-resolution-e2e",
            }
        ],
    )

    diagnostic = build_scoped_lifecycle_diagnostic(tmp_path)
    gate = diagnostic["orchestration_handoff"]["packetization_gating"]
    brief_surface = diagnostic["orchestration_handoff"]["operator_action_brief"]
    operator_influence = diagnostic["orchestration_handoff"]["operator_influence"]
    proposal_visibility = diagnostic["orchestration_handoff"]["next_move_proposal"]["operator_feedback"]
    next_venue_visibility = diagnostic["orchestration_handoff"]["next_venue_recommendation"]["operator_feedback"]
    handoff = diagnostic["orchestration_handoff"]["handoff_result"]

    assert gate["packetization_outcome"] in {
        "packetization_allowed_with_caution",
        "packetization_hold_operator_review",
        "packetization_hold_insufficient_confidence",
    }
    assert gate["operator_influence"]["operator_influence_applied"] is True
    assert gate["operator_influence"]["resolution_kind"] == "approved_continue"
    assert brief_surface["brief_produced"] is True
    assert brief_surface["operator_resolution_received"] is True
    assert brief_surface["resolution_kind"] == "approved_continue"
    assert brief_surface["lifecycle_visibility"]["lifecycle_state"] == "operator_approved_continue"
    assert brief_surface["has_operator_guidance"] is True
    assert brief_surface["awaiting_operator_input"] is False
    assert brief_surface["non_sovereign_boundaries"]["ingested_operator_outcome"] is True
    assert brief_surface["non_sovereign_boundaries"]["explicit_clarity"] == "ingested operator outcome, not repo execution"
    assert operator_influence["operator_influence_state"] == "operator_approval_applied"
    assert operator_influence["does_not_imply_execution"] is True
    assert proposal_visibility["operator_influence_applied"] is True
    assert next_venue_visibility["operator_influence_applied"] is True
    assert handoff["handoff_outcome"] in {"blocked_by_operator_requirement", "blocked_by_insufficient_context", "staged_only", "admitted_to_execution_substrate", "blocked_by_admission"}
    assert brief_surface["non_sovereign_boundaries"]["does_not_convert_hold_to_execution"] is True


def test_attention_recommendation_does_not_change_admission_or_execution_behavior(tmp_path: Path) -> None:
    evidence = _base_evidence()
    evidence.update(
        {
            "admission_denied_ratio": 0.75,
            "admission_sample_count": 8,
            "executor_failure_ratio": 0.4,
            "executor_sample_count": 8,
        }
    )
    judgment = synthesize_delegated_judgment(evidence)
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    append_orchestration_intent_ledger(tmp_path, intent)
    before = admit_orchestration_intent(tmp_path, intent)
    review = derive_orchestration_outcome_review(tmp_path)
    attention = derive_orchestration_attention_recommendation(review)
    after = admit_orchestration_intent(tmp_path, intent)

    assert attention["does_not_change_admission_or_execution"] is True
    assert before["handoff_outcome"] == "admitted_to_execution_substrate"
    assert after["handoff_outcome"] == "admitted_to_execution_substrate"


def test_venue_mix_review_does_not_change_admission_or_execution_behavior(tmp_path: Path) -> None:
    evidence = _base_evidence()
    evidence.update(
        {
            "admission_denied_ratio": 0.75,
            "admission_sample_count": 8,
            "executor_failure_ratio": 0.4,
            "executor_sample_count": 8,
        }
    )
    judgment = synthesize_delegated_judgment(evidence)
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    append_orchestration_intent_ledger(tmp_path, intent)
    before = admit_orchestration_intent(tmp_path, intent)
    review = derive_orchestration_venue_mix_review(tmp_path)
    after = admit_orchestration_intent(tmp_path, intent)

    assert review["does_not_change_admission_or_execution"] is True
    assert before["handoff_outcome"] == "admitted_to_execution_substrate"
    assert after["handoff_outcome"] == "admitted_to_execution_substrate"


def test_next_venue_recommendation_does_not_change_admission_or_execution_behavior(tmp_path: Path) -> None:
    evidence = _base_evidence()
    judgment = synthesize_delegated_judgment(evidence)
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    append_orchestration_intent_ledger(tmp_path, intent)
    before = admit_orchestration_intent(tmp_path, intent)
    outcome_review = derive_orchestration_outcome_review(tmp_path)
    venue_mix_review = derive_orchestration_venue_mix_review(tmp_path)
    attention = derive_orchestration_attention_recommendation(outcome_review)
    next_venue = derive_next_venue_recommendation(judgment, outcome_review, venue_mix_review, attention)
    after = admit_orchestration_intent(tmp_path, intent)

    assert next_venue["does_not_change_admission_or_execution"] is True
    assert next_venue["does_not_execute_or_route_work"] is True
    assert next_venue["does_not_override_delegated_judgment"] is True
    assert before["handoff_outcome"] == "blocked_by_operator_requirement"
    assert after["handoff_outcome"] == "blocked_by_operator_requirement"


def test_next_move_proposal_does_not_change_admission_or_execution_behavior(tmp_path: Path) -> None:
    evidence = _base_evidence()
    judgment = synthesize_delegated_judgment(evidence)
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    append_orchestration_intent_ledger(tmp_path, intent)
    before = admit_orchestration_intent(tmp_path, intent)
    outcome_review = derive_orchestration_outcome_review(tmp_path)
    venue_mix_review = derive_orchestration_venue_mix_review(tmp_path)
    attention = derive_orchestration_attention_recommendation(outcome_review)
    next_venue = derive_next_venue_recommendation(judgment, outcome_review, venue_mix_review, attention)
    proposal = synthesize_next_move_proposal(judgment, next_venue, outcome_review, venue_mix_review, attention)
    append_next_move_proposal_ledger(tmp_path, proposal)
    after = admit_orchestration_intent(tmp_path, intent)

    assert proposal["does_not_change_admission_or_execution"] is True
    assert proposal["does_not_execute_or_route_work"] is True
    assert proposal["does_not_override_delegated_judgment"] is True
    assert before["handoff_outcome"] == "blocked_by_operator_requirement"
    assert after["handoff_outcome"] == "blocked_by_operator_requirement"


def test_next_move_proposal_review_does_not_change_admission_or_execution_behavior(tmp_path: Path) -> None:
    evidence = _base_evidence()
    judgment = synthesize_delegated_judgment(evidence)
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    append_orchestration_intent_ledger(tmp_path, intent)
    before = admit_orchestration_intent(tmp_path, intent)
    outcome_review = derive_orchestration_outcome_review(tmp_path)
    venue_mix_review = derive_orchestration_venue_mix_review(tmp_path)
    attention = derive_orchestration_attention_recommendation(outcome_review)
    next_venue = derive_next_venue_recommendation(judgment, outcome_review, venue_mix_review, attention)
    proposal = synthesize_next_move_proposal(judgment, next_venue, outcome_review, venue_mix_review, attention)
    append_next_move_proposal_ledger(tmp_path, proposal)
    proposal_review = derive_next_move_proposal_review(tmp_path)
    after = admit_orchestration_intent(tmp_path, intent)

    assert proposal_review["does_not_change_admission_or_execution"] is True
    assert proposal_review["review_only"] is True
    assert before["handoff_outcome"] == "blocked_by_operator_requirement"
    assert after["handoff_outcome"] == "blocked_by_operator_requirement"


def test_codex_staged_work_order_artifact_is_append_only_and_proof_visible(tmp_path: Path) -> None:
    judgment = synthesize_delegated_judgment(_base_evidence())
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    handoff = admit_orchestration_intent(tmp_path, intent)

    assert handoff["details"]["codex_work_order_ref"]["ledger_path"] == "glow/orchestration/codex_work_orders.jsonl"
    rows = (tmp_path / "glow/orchestration/codex_work_orders.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    work_order = json.loads(rows[0])
    assert work_order["venue"] == "codex_implementation"
    assert work_order["source_intent_id"] == intent["intent_id"]
    assert work_order["status"] == "blocked_operator_required"
    assert work_order["does_not_invoke_codex_directly"] is True
    assert work_order["requires_external_tool_or_operator_trigger"] is True


def test_deep_research_staged_work_order_artifact_is_append_only_and_proof_visible(tmp_path: Path) -> None:
    judgment = synthesize_delegated_judgment({**_base_evidence(), "governance_ambiguity_signal": True})
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    handoff = admit_orchestration_intent(tmp_path, intent)

    assert handoff["details"]["deep_research_work_order_ref"]["ledger_path"] == "glow/orchestration/deep_research_work_orders.jsonl"
    rows = (tmp_path / "glow/orchestration/deep_research_work_orders.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    work_order = json.loads(rows[0])
    assert work_order["venue"] == "deep_research_audit"
    assert work_order["source_intent_id"] == intent["intent_id"]
    assert work_order["status"] == "blocked_operator_required"
    assert work_order["does_not_invoke_deep_research_directly"] is True
    assert work_order["requires_external_tool_or_operator_trigger"] is True


def test_staged_codex_packet_can_ingest_externally_completed_receipt(tmp_path: Path) -> None:
    delegated = synthesize_delegated_judgment(_base_evidence())
    packet = _external_handoff_packet(
        delegated,
        venue_recommendation="prefer_codex_implementation",
        outcome_classification="clean_recent_orchestration",
        venue_mix_classification="balanced_recent_venue_mix",
        attention_signal="observe",
    )
    append_handoff_packet_ledger(tmp_path, packet)

    receipt = ingest_external_fulfillment_receipt(
        tmp_path,
        handoff_packet_id=str(packet["handoff_packet_id"]),
        fulfillment_kind="externally_completed",
        operator_or_adapter="operator:unit-test",
        summary_notes="implemented in external codex session",
        evidence_refs=["artifacts/codex_patch.diff"],
        created_at="2026-04-12T00:05:00Z",
    )

    assert receipt["source_venue"] == "codex_implementation"
    assert receipt["fulfillment_kind"] == "externally_completed"
    assert receipt["ingested_external_outcome"] is True
    assert receipt["does_not_imply_direct_repo_execution"] is True
    assert receipt["requires_external_actor_or_operator"] is True


def test_staged_deep_research_packet_can_ingest_externally_completed_receipt(tmp_path: Path) -> None:
    delegated = synthesize_delegated_judgment({**_base_evidence(), "governance_ambiguity_signal": True})
    packet = _external_handoff_packet(
        delegated,
        venue_recommendation="prefer_deep_research_audit",
        outcome_classification="mixed_orchestration_stress",
        venue_mix_classification="deep_research_heavy",
        attention_signal="review_mixed_orchestration_stress",
    )
    append_handoff_packet_ledger(tmp_path, packet)

    receipt = ingest_external_fulfillment_receipt(
        tmp_path,
        handoff_packet_id=str(packet["handoff_packet_id"]),
        fulfillment_kind="externally_completed",
        operator_or_adapter="adapter:research-broker",
        summary_notes="research summary returned from external process",
        evidence_refs=["reports/deep_research.md"],
        created_at="2026-04-12T00:05:00Z",
    )

    assert receipt["source_venue"] == "deep_research_audit"
    assert receipt["fulfillment_kind"] == "externally_completed"
    assert receipt["ingested_external_outcome"] is True
    assert receipt["does_not_imply_direct_repo_execution"] is True


def test_fulfillment_ingestion_fails_closed_when_packet_linkage_missing(tmp_path: Path) -> None:
    try:
        ingest_external_fulfillment_receipt(
            tmp_path,
            handoff_packet_id="hpk-missing",
            fulfillment_kind="externally_completed",
            operator_or_adapter="operator:test",
            summary_notes="should fail",
        )
    except ValueError as exc:
        assert "handoff packet not found" in str(exc)
    else:
        raise AssertionError("expected ValueError for missing handoff packet linkage")


def test_external_declined_abandoned_and_unusable_states_are_visible(tmp_path: Path) -> None:
    delegated = synthesize_delegated_judgment(_base_evidence())
    packet = _external_handoff_packet(
        delegated,
        venue_recommendation="prefer_codex_implementation",
        outcome_classification="clean_recent_orchestration",
        venue_mix_classification="balanced_recent_venue_mix",
        attention_signal="observe",
    )
    append_handoff_packet_ledger(tmp_path, packet)

    ingest_external_fulfillment_receipt(
        tmp_path,
        handoff_packet_id=str(packet["handoff_packet_id"]),
        fulfillment_kind="externally_declined",
        operator_or_adapter="operator:test",
        summary_notes="declined by external actor",
        created_at="2026-04-12T00:03:00Z",
    )
    declined = resolve_handoff_packet_fulfillment_lifecycle(tmp_path, packet)
    assert declined["lifecycle_state"] == "externally_declined"

    ingest_external_fulfillment_receipt(
        tmp_path,
        handoff_packet_id=str(packet["handoff_packet_id"]),
        fulfillment_kind="externally_abandoned",
        operator_or_adapter="operator:test",
        summary_notes="abandoned externally",
        created_at="2026-04-12T00:04:00Z",
    )
    abandoned = resolve_handoff_packet_fulfillment_lifecycle(tmp_path, packet)
    assert abandoned["lifecycle_state"] == "externally_abandoned"

    ingest_external_fulfillment_receipt(
        tmp_path,
        handoff_packet_id=str(packet["handoff_packet_id"]),
        fulfillment_kind="externally_result_unusable",
        operator_or_adapter="operator:test",
        summary_notes="result unusable",
        created_at="2026-04-12T00:05:00Z",
    )
    unusable = resolve_handoff_packet_fulfillment_lifecycle(tmp_path, packet)
    assert unusable["lifecycle_state"] == "externally_result_unusable"


def test_unified_result_resolves_internal_execution_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path / "logs"))
    reload(task_executor)
    reload(task_admission)
    evidence = _base_evidence()
    evidence.update(
        {
            "admission_denied_ratio": 0.75,
            "admission_sample_count": 8,
            "executor_failure_ratio": 0.4,
            "executor_sample_count": 8,
        }
    )
    judgment = synthesize_delegated_judgment(evidence)
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    handoff = admit_orchestration_intent(tmp_path, intent)
    task_id = handoff["details"]["task_admission"]["task_id"]
    _write_jsonl(
        tmp_path / "logs/task_executor.jsonl",
        [{"task_id": task_id, "event": "task_result", "status": "completed"}],
    )

    unified = resolve_unified_orchestration_result(
        tmp_path,
        handoff=handoff,
        executor_log_path=tmp_path / "logs/task_executor.jsonl",
    )

    assert unified["resolution_path"] == "internal_execution"
    assert unified["result_classification"] == "completed_successfully"
    assert unified["path_honesty"]["task_result_observed"] is True
    assert unified["path_honesty"]["fulfillment_receipt_observed"] is False


def test_unified_result_resolves_external_codex_fulfillment_path(tmp_path: Path) -> None:
    delegated = synthesize_delegated_judgment(_base_evidence())
    intent = synthesize_orchestration_intent(delegated, created_at="2026-04-12T00:00:00Z")
    handoff = admit_orchestration_intent(tmp_path, intent)
    packet = _external_handoff_packet(
        delegated,
        venue_recommendation="prefer_codex_implementation",
        outcome_classification="clean_recent_orchestration",
        venue_mix_classification="balanced_recent_venue_mix",
        attention_signal="observe",
    )
    append_handoff_packet_ledger(tmp_path, packet)
    ingest_external_fulfillment_receipt(
        tmp_path,
        handoff_packet_id=str(packet["handoff_packet_id"]),
        fulfillment_kind="externally_completed",
        operator_or_adapter="operator:test",
        summary_notes="done externally",
    )

    unified = resolve_unified_orchestration_result(tmp_path, handoff=handoff, handoff_packet=packet)
    assert unified["resolution_path"] == "external_fulfillment"
    assert unified["venue"] == "codex_implementation"
    assert unified["result_classification"] == "completed_successfully"
    assert unified["path_honesty"]["does_not_imply_direct_repo_execution"] is True
    assert unified["path_honesty"]["fulfillment_receipt_observed"] is True


def test_unified_result_resolves_external_deep_research_fulfillment_path(tmp_path: Path) -> None:
    delegated = synthesize_delegated_judgment({**_base_evidence(), "governance_ambiguity_signal": True})
    intent = synthesize_orchestration_intent(delegated, created_at="2026-04-12T00:00:00Z")
    handoff = admit_orchestration_intent(tmp_path, intent)
    packet = _external_handoff_packet(
        delegated,
        venue_recommendation="prefer_deep_research_audit",
        outcome_classification="mixed_orchestration_stress",
        venue_mix_classification="deep_research_heavy",
        attention_signal="review_mixed_orchestration_stress",
    )
    append_handoff_packet_ledger(tmp_path, packet)
    ingest_external_fulfillment_receipt(
        tmp_path,
        handoff_packet_id=str(packet["handoff_packet_id"]),
        fulfillment_kind="externally_completed_with_issues",
        operator_or_adapter="operator:test",
        summary_notes="completed with caveats",
    )

    unified = resolve_unified_orchestration_result(tmp_path, handoff=handoff, handoff_packet=packet)
    assert unified["resolution_path"] == "external_fulfillment"
    assert unified["venue"] == "deep_research_audit"
    assert unified["result_classification"] == "completed_with_issues"
    assert unified["path_honesty"]["fulfillment_receipt_observed"] is True


def test_unified_result_honestly_represents_declined_and_pending_and_fragmented(tmp_path: Path) -> None:
    delegated = synthesize_delegated_judgment(_base_evidence())
    intent = synthesize_orchestration_intent(delegated, created_at="2026-04-12T00:00:00Z")
    handoff = admit_orchestration_intent(tmp_path, intent)
    packet = _external_handoff_packet(
        delegated,
        venue_recommendation="prefer_codex_implementation",
        outcome_classification="clean_recent_orchestration",
        venue_mix_classification="balanced_recent_venue_mix",
        attention_signal="observe",
    )
    append_handoff_packet_ledger(tmp_path, packet)
    pending = resolve_unified_orchestration_result(tmp_path, handoff=handoff, handoff_packet=packet)
    assert pending["result_classification"] == "pending_or_unresolved"

    ingest_external_fulfillment_receipt(
        tmp_path,
        handoff_packet_id=str(packet["handoff_packet_id"]),
        fulfillment_kind="externally_declined",
        operator_or_adapter="operator:test",
        summary_notes="declined",
    )
    declined = resolve_unified_orchestration_result(tmp_path, handoff=handoff, handoff_packet=packet)
    assert declined["result_classification"] == "declined_or_abandoned"

    fragmented = resolve_unified_orchestration_result(tmp_path, handoff=handoff)
    assert fragmented["result_classification"] == "fragmented_result_history"
    assert fragmented["evidence_presence"]["fragmented_linkage"] is True


def test_unified_result_quality_review_classifies_healthy_recent_results(monkeypatch, tmp_path: Path) -> None:
    _mock_unified_surface(
        monkeypatch,
        counts={"completed_successfully": 4, "completed_with_issues": 1},
        path_counts={"internal_execution": 3, "external_fulfillment": 2},
    )
    review = derive_unified_result_quality_review(tmp_path)
    assert review["review_classification"] == "healthy_recent_results"
    assert review["summary"]["health_vs_stress"] == "healthy"


def test_unified_result_quality_review_classifies_issues_heavy(monkeypatch, tmp_path: Path) -> None:
    _mock_unified_surface(
        monkeypatch,
        counts={"completed_with_issues": 2, "failed_after_execution": 2, "completed_successfully": 1},
        path_counts={"internal_execution": 2, "external_fulfillment": 3},
    )
    review = derive_unified_result_quality_review(tmp_path)
    assert review["review_classification"] == "issues_heavy"
    assert review["condition_flags"]["issues_heavy"] is True


def test_unified_result_quality_review_classifies_abandonment_or_decline_heavy(monkeypatch, tmp_path: Path) -> None:
    _mock_unified_surface(
        monkeypatch,
        counts={"declined_or_abandoned": 3, "completed_successfully": 1},
        path_counts={"internal_execution": 1, "external_fulfillment": 3},
    )
    review = derive_unified_result_quality_review(tmp_path)
    assert review["review_classification"] == "abandonment_or_decline_heavy"
    assert review["condition_flags"]["abandonment_or_decline_heavy"] is True


def test_unified_result_quality_review_classifies_fragmentation_heavy(monkeypatch, tmp_path: Path) -> None:
    _mock_unified_surface(
        monkeypatch,
        counts={"pending_or_unresolved": 2, "fragmented_result_history": 1, "completed_successfully": 1},
        path_counts={"internal_execution": 2, "external_fulfillment": 2},
        fragmented_linkage_count=2,
    )
    review = derive_unified_result_quality_review(tmp_path)
    assert review["review_classification"] == "fragmentation_heavy"
    assert review["condition_flags"]["fragmentation_heavy"] is True


def test_unified_result_quality_review_classifies_mixed_result_stress(monkeypatch, tmp_path: Path) -> None:
    _mock_unified_surface(
        monkeypatch,
        counts={"completed_with_issues": 2, "failed_after_execution": 1, "declined_or_abandoned": 2},
        path_counts={"internal_execution": 2, "external_fulfillment": 3},
    )
    review = derive_unified_result_quality_review(tmp_path)
    assert review["review_classification"] == "mixed_result_stress"
    assert review["condition_flags"]["multiple_competing_stress_patterns"] is True


def test_unified_result_quality_review_classifies_insufficient_history(monkeypatch, tmp_path: Path) -> None:
    _mock_unified_surface(
        monkeypatch,
        counts={"completed_successfully": 1, "completed_with_issues": 1},
        path_counts={"internal_execution": 1, "external_fulfillment": 1},
        records_considered=2,
    )
    review = derive_unified_result_quality_review(tmp_path)
    assert review["review_classification"] == "insufficient_history"
    assert review["summary"]["health_vs_stress"] == "insufficient_evidence"


def test_unified_result_quality_review_does_not_change_admission_behavior(tmp_path: Path) -> None:
    judgment = synthesize_delegated_judgment(_base_evidence())
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    append_orchestration_intent_ledger(tmp_path, intent)
    before = admit_orchestration_intent(tmp_path, intent)

    review = derive_unified_result_quality_review(tmp_path)

    after = admit_orchestration_intent(tmp_path, intent)
    assert review["non_authoritative"] is True
    assert review["decision_power"] == "none"
    assert review["does_not_change_admission_or_execution"] is True
    assert before["handoff_outcome"] == "blocked_by_operator_requirement"
    assert after["handoff_outcome"] == "blocked_by_operator_requirement"


def test_orchestration_trust_confidence_classifies_trusted_for_bounded_use() -> None:
    posture = derive_orchestration_trust_confidence_posture(
        {"review_classification": "coherent_recent_proposals", "records_considered": 6},
        {"review_classification": "balanced_recent_venue_mix", "records_considered": 6},
        {"review_classification": "clean_recent_orchestration", "records_considered": 6, "condition_flags": {}},
        {"review_classification": "healthy_recent_results", "records_considered": 6, "condition_flags": {}},
        {"operator_attention_recommendation": "observe"},
    )
    assert posture["trust_confidence_posture"] == "trusted_for_bounded_use"
    assert posture["pressure_summary"]["primary_pressure"] == "none"


def test_orchestration_trust_confidence_classifies_caution_required() -> None:
    posture = derive_orchestration_trust_confidence_posture(
        {"review_classification": "coherent_recent_proposals", "records_considered": 5},
        {"review_classification": "balanced_recent_venue_mix", "records_considered": 5},
        {"review_classification": "clean_recent_orchestration", "records_considered": 5, "condition_flags": {}},
        {"review_classification": "mixed_result_stress", "records_considered": 5, "condition_flags": {}},
        {"operator_attention_recommendation": "observe"},
    )
    assert posture["trust_confidence_posture"] == "caution_required"
    assert posture["pressure_summary"]["stress_components"]["result_quality_stress"] is True


def test_orchestration_trust_confidence_classifies_stressed_but_usable() -> None:
    posture = derive_orchestration_trust_confidence_posture(
        {"review_classification": "proposal_escalation_heavy", "records_considered": 6},
        {"review_classification": "mixed_venue_stress", "records_considered": 6},
        {"review_classification": "clean_recent_orchestration", "records_considered": 6, "condition_flags": {}},
        {"review_classification": "healthy_recent_results", "records_considered": 6, "condition_flags": {}},
        {"operator_attention_recommendation": "observe"},
    )
    assert posture["trust_confidence_posture"] == "stressed_but_usable"
    assert posture["pressure_summary"]["primary_pressure"] == "mixed_stress"


def test_orchestration_trust_confidence_classifies_fragmented_or_unreliable() -> None:
    posture = derive_orchestration_trust_confidence_posture(
        {"review_classification": "mixed_proposal_stress", "records_considered": 7},
        {"review_classification": "mixed_venue_stress", "records_considered": 7},
        {
            "review_classification": "mixed_orchestration_stress",
            "records_considered": 7,
            "condition_flags": {"external_stress_heavy": True},
        },
        {"review_classification": "fragmentation_heavy", "records_considered": 7, "condition_flags": {"fragmentation_heavy": True}},
        {"operator_attention_recommendation": "inspect_handoff_blocks"},
    )
    assert posture["trust_confidence_posture"] == "fragmented_or_unreliable"
    assert posture["pressure_summary"]["primary_pressure"] == "fragmentation"


def test_orchestration_trust_confidence_classifies_insufficient_history() -> None:
    posture = derive_orchestration_trust_confidence_posture(
        {"review_classification": "coherent_recent_proposals", "records_considered": 2},
        {"review_classification": "balanced_recent_venue_mix", "records_considered": 2},
        {"review_classification": "clean_recent_orchestration", "records_considered": 2},
        {"review_classification": "healthy_recent_results", "records_considered": 2},
        {"operator_attention_recommendation": "none"},
    )
    assert posture["trust_confidence_posture"] == "insufficient_history"
    assert posture["pressure_summary"]["primary_pressure"] == "insufficient_history"


def test_delegated_operation_readiness_classifies_ready_for_bounded_supervised_operation() -> None:
    readiness = derive_delegated_operation_readiness_verdict(
        {
            "trust_confidence_posture": "trusted_for_bounded_use",
            "pressure_summary": {"primary_pressure": "none"},
            "window_considered": {"minimum_records_considered": 6},
        },
        {"review_classification": "coherent_proposal_packet_continuity", "records_considered": 6},
        {"review_classification": "healthy_recent_results", "records_considered": 6},
        {"packetization_outcome": "packetization_allowed", "packetization_allowed": True, "packetization_held": False},
        {"operator_attention_recommendation": "observe"},
        outcome_review={"review_classification": "clean_recent_orchestration"},
        venue_mix_review={"review_classification": "balanced_recent_venue_mix"},
        next_move_proposal_review={"review_classification": "coherent_recent_proposals"},
        active_packet_visibility={"status": "ready_for_external_trigger", "target_venue": "codex_implementation"},
    )
    assert readiness["readiness_verdict"] == "ready_for_bounded_supervised_operation"
    assert readiness["dominant_pressure_source"] == "none"
    assert readiness["current_resumed_operation_readiness"]["basis"]["derived_from_existing_surfaces_only"]


def test_delegated_operation_readiness_classifies_ready_with_caution() -> None:
    readiness = derive_delegated_operation_readiness_verdict(
        {
            "trust_confidence_posture": "caution_required",
            "pressure_summary": {"primary_pressure": "proposal_stress"},
            "window_considered": {"minimum_records_considered": 5},
        },
        {"review_classification": "coherent_proposal_packet_continuity", "records_considered": 5},
        {"review_classification": "mixed_result_stress", "records_considered": 5},
        {
            "packetization_outcome": "packetization_allowed_with_caution",
            "packetization_allowed": True,
            "packetization_held": False,
        },
        {"operator_attention_recommendation": "review_mixed_orchestration_stress"},
        outcome_review={"review_classification": "mixed_orchestration_stress"},
        venue_mix_review={"review_classification": "balanced_recent_venue_mix"},
        next_move_proposal_review={"review_classification": "mixed_proposal_stress"},
    )
    assert readiness["readiness_verdict"] == "ready_with_caution"
    assert readiness["dominant_pressure_source"] == "proposal_stress"


def test_delegated_operation_readiness_classifies_operator_review_required() -> None:
    readiness = derive_delegated_operation_readiness_verdict(
        {
            "trust_confidence_posture": "stressed_but_usable",
            "pressure_summary": {"primary_pressure": "escalation_operator_dependence"},
            "window_considered": {"minimum_records_considered": 6},
        },
        {"review_classification": "hold_heavy_continuity", "records_considered": 6},
        {"review_classification": "healthy_recent_results", "records_considered": 6},
        {
            "packetization_outcome": "packetization_hold_operator_review",
            "packetization_allowed": False,
            "packetization_held": True,
        },
        {"operator_attention_recommendation": "inspect_handoff_blocks"},
        outcome_review={"review_classification": "handoff_block_heavy"},
        venue_mix_review={"review_classification": "operator_escalation_heavy"},
        next_move_proposal_review={"review_classification": "proposal_escalation_heavy"},
    )
    assert readiness["readiness_verdict"] == "operator_review_required"
    assert readiness["dominant_pressure_source"] == "operator_dependence"


def test_delegated_operation_readiness_classifies_temporarily_unfit_due_to_fragmentation() -> None:
    readiness = derive_delegated_operation_readiness_verdict(
        {
            "trust_confidence_posture": "fragmented_or_unreliable",
            "pressure_summary": {"primary_pressure": "fragmentation"},
            "window_considered": {"minimum_records_considered": 6},
        },
        {"review_classification": "fragmented_continuity", "records_considered": 6},
        {"review_classification": "fragmentation_heavy", "records_considered": 6},
        {
            "packetization_outcome": "packetization_hold_fragmentation",
            "packetization_allowed": False,
            "packetization_held": True,
        },
        {"operator_attention_recommendation": "review_mixed_orchestration_stress"},
        outcome_review={"review_classification": "mixed_orchestration_stress"},
        venue_mix_review={"review_classification": "mixed_venue_stress"},
        next_move_proposal_review={"review_classification": "mixed_proposal_stress"},
    )
    assert readiness["readiness_verdict"] == "temporarily_unfit_due_to_fragmentation"
    assert readiness["dominant_pressure_source"] == "fragmentation"


def test_delegated_operation_readiness_classifies_insufficient_history() -> None:
    readiness = derive_delegated_operation_readiness_verdict(
        {
            "trust_confidence_posture": "insufficient_history",
            "pressure_summary": {"primary_pressure": "insufficient_history"},
            "window_considered": {"minimum_records_considered": 2},
        },
        {"review_classification": "insufficient_history", "records_considered": 2},
        {"review_classification": "insufficient_history", "records_considered": 2},
        {
            "packetization_outcome": "packetization_hold_insufficient_confidence",
            "packetization_allowed": False,
            "packetization_held": True,
        },
        {"operator_attention_recommendation": "insufficient_context"},
        outcome_review={"review_classification": "insufficient_history"},
        venue_mix_review={"review_classification": "insufficient_history"},
        next_move_proposal_review={"review_classification": "insufficient_history"},
    )
    assert readiness["readiness_verdict"] == "insufficient_history"
    assert readiness["dominant_pressure_source"] == "insufficient_history"


def test_packetization_gate_allows_trusted_coherent_proposal() -> None:
    proposal = {
        "executability_classification": "stageable_external_work_order",
        "relation_posture": "affirming",
        "proposed_next_action": {"proposed_posture": "expand"},
        "operator_escalation_requirement_state": {
            "requires_operator_or_escalation": False,
            "attention_signal": "observe",
            "escalation_classification": "no_escalation_needed",
        },
    }
    gate = derive_packetization_gate(
        proposal,
        {"review_classification": "coherent_recent_proposals", "records_considered": 6},
        {"trust_confidence_posture": "trusted_for_bounded_use", "pressure_summary": {"primary_pressure": "none"}},
        {"operator_attention_recommendation": "observe"},
    )
    assert gate["packetization_outcome"] == "packetization_allowed"
    assert gate["packetization_allowed"] is True


def test_packetization_gate_allows_with_caution_for_caution_posture() -> None:
    proposal = {
        "executability_classification": "stageable_external_work_order",
        "relation_posture": "nudging",
        "proposed_next_action": {"proposed_posture": "audit"},
        "operator_escalation_requirement_state": {
            "requires_operator_or_escalation": False,
            "attention_signal": "review_mixed_orchestration_stress",
            "escalation_classification": "no_escalation_needed",
        },
    }
    gate = derive_packetization_gate(
        proposal,
        {"review_classification": "coherent_recent_proposals", "records_considered": 6},
        {"trust_confidence_posture": "caution_required", "pressure_summary": {"primary_pressure": "mixed_stress"}},
        {"operator_attention_recommendation": "review_mixed_orchestration_stress"},
    )
    assert gate["packetization_outcome"] == "packetization_allowed_with_caution"
    assert gate["packetization_allowed"] is True


def test_packetization_gate_holds_fragmented_posture() -> None:
    proposal = {
        "executability_classification": "stageable_external_work_order",
        "relation_posture": "affirming",
        "proposed_next_action": {"proposed_posture": "expand"},
        "operator_escalation_requirement_state": {"requires_operator_or_escalation": False},
    }
    gate = derive_packetization_gate(
        proposal,
        {"review_classification": "mixed_proposal_stress", "records_considered": 6},
        {"trust_confidence_posture": "fragmented_or_unreliable", "pressure_summary": {"primary_pressure": "fragmentation"}},
        {"operator_attention_recommendation": "observe"},
    )
    assert gate["packetization_outcome"] == "packetization_hold_fragmentation"
    assert gate["packetization_held"] is True


def test_packetization_gate_holds_insufficient_history_or_context() -> None:
    proposal = {
        "executability_classification": "blocked_insufficient_context",
        "relation_posture": "insufficient_context",
        "proposed_next_action": {"proposed_posture": "hold"},
        "operator_escalation_requirement_state": {"requires_operator_or_escalation": False},
    }
    gate = derive_packetization_gate(
        proposal,
        {"review_classification": "insufficient_history", "records_considered": 1},
        {"trust_confidence_posture": "insufficient_history", "pressure_summary": {"primary_pressure": "insufficient_history"}},
        {"operator_attention_recommendation": "insufficient_context"},
    )
    assert gate["packetization_outcome"] == "packetization_hold_insufficient_confidence"
    assert gate["packetization_held"] is True


def test_packetization_gate_holds_operator_required_paths() -> None:
    proposal = {
        "executability_classification": "blocked_operator_required",
        "relation_posture": "escalating",
        "proposed_next_action": {"proposed_posture": "escalate"},
        "operator_escalation_requirement_state": {
            "requires_operator_or_escalation": True,
            "attention_signal": "inspect_handoff_blocks",
            "escalation_classification": "escalate_for_operator_priority",
        },
    }
    gate = derive_packetization_gate(
        proposal,
        {"review_classification": "proposal_escalation_heavy", "records_considered": 6},
        {"trust_confidence_posture": "stressed_but_usable", "pressure_summary": {"primary_pressure": "mixed_stress"}},
        {"operator_attention_recommendation": "inspect_handoff_blocks"},
    )
    assert gate["packetization_outcome"] == "packetization_hold_operator_review"
    assert gate["packetization_held"] is True


def test_receipt_ingestion_does_not_change_admission_or_execution_behavior(tmp_path: Path) -> None:
    judgment = synthesize_delegated_judgment(_base_evidence())
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    append_orchestration_intent_ledger(tmp_path, intent)
    before = admit_orchestration_intent(tmp_path, intent)

    delegated = synthesize_delegated_judgment(_base_evidence())
    packet = _external_handoff_packet(
        delegated,
        venue_recommendation="prefer_codex_implementation",
        outcome_classification="clean_recent_orchestration",
        venue_mix_classification="balanced_recent_venue_mix",
        attention_signal="observe",
    )
    append_handoff_packet_ledger(tmp_path, packet)
    ingest_external_fulfillment_receipt(
        tmp_path,
        handoff_packet_id=str(packet["handoff_packet_id"]),
        fulfillment_kind="externally_completed_with_issues",
        operator_or_adapter="operator:test",
        summary_notes="external completion with caveats",
    )

    after = admit_orchestration_intent(tmp_path, intent)
    assert before["handoff_outcome"] == "blocked_by_operator_requirement"
    assert after["handoff_outcome"] == "blocked_by_operator_requirement"

    split_map = build_split_closure_map()
    assert split_map["schema_version"] == "orchestration_split_closure_map.v1"


def test_operator_resolution_receipt_ingestion_does_not_change_admission_or_execution_behavior(tmp_path: Path) -> None:
    judgment = synthesize_delegated_judgment(_base_evidence())
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    append_orchestration_intent_ledger(tmp_path, intent)
    before = admit_orchestration_intent(tmp_path, intent)

    brief = _operator_brief_for_receipt_flow()
    append_operator_action_brief_ledger(tmp_path, brief)
    receipt = ingest_operator_resolution_receipt(
        tmp_path,
        operator_action_brief_id=str(brief["operator_action_brief_id"]),
        resolution_kind="approved_continue",
        operator_note="approved bounded continuation",
        created_at="2026-04-12T00:01:00Z",
    )
    after = admit_orchestration_intent(tmp_path, intent)

    assert receipt["ingested_operator_outcome"] is True
    assert receipt["does_not_change_admission_or_execution"] is True
    assert receipt["decision_power"] == "none"
    assert receipt["receipt_only"] is True
    assert before["handoff_outcome"] == "blocked_by_operator_requirement"
    assert after["handoff_outcome"] == "blocked_by_operator_requirement"


def test_codex_missing_metadata_yields_blocked_insufficient_and_lifecycle_fragment_visibility(tmp_path: Path) -> None:
    handoff = admit_orchestration_intent(
        tmp_path,
        {
            "intent_kind": "codex_work_order",
            "execution_target": "no_execution_target_yet",
            "executability_classification": "stageable_external_work_order",
        },
    )

    assert handoff["handoff_outcome"] == "blocked_by_insufficient_context"
    assert "codex_work_order_ref" in handoff["details"]
    resolution = resolve_orchestration_result(tmp_path, handoff)
    assert resolution["codex_staged_lifecycle"]["lifecycle_state"] == "blocked_insufficient_context"


def test_deep_research_missing_metadata_yields_blocked_insufficient_and_lifecycle_fragment_visibility(tmp_path: Path) -> None:
    handoff = admit_orchestration_intent(
        tmp_path,
        {
            "intent_kind": "deep_research_work_order",
            "execution_target": "no_execution_target_yet",
            "executability_classification": "stageable_external_work_order",
        },
    )

    assert handoff["handoff_outcome"] == "blocked_by_insufficient_context"
    assert "deep_research_work_order_ref" in handoff["details"]
    resolution = resolve_orchestration_result(tmp_path, handoff)
    assert resolution["deep_research_staged_lifecycle"]["lifecycle_state"] == "blocked_insufficient_context"


def test_end_to_end_codex_staged_venue_visibility_is_honest(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("sentientos.scoped_lifecycle_diagnostic.SCOPED_ACTION_IDS", ("sentientos.manifest.generate",))

    def _fake_resolver(_repo_root: Path, *, action_id: str, correlation_id: str) -> dict[str, object]:
        return {
            "typed_action_identity": action_id,
            "correlation_id": correlation_id,
            "outcome_class": "success",
        }

    monkeypatch.setattr("sentientos.scoped_lifecycle_diagnostic.resolve_scoped_mutation_lifecycle", _fake_resolver)
    monkeypatch.setattr(
        "sentientos.scoped_lifecycle_diagnostic.synthesize_delegated_judgment",
        lambda _evidence: synthesize_delegated_judgment(_base_evidence()),
    )
    _write_json(tmp_path / "glow/contracts/contract_status.json", {"contracts": []})
    _write_jsonl(
        tmp_path / "pulse/forge_events.jsonl",
        [
            {
                "event": "constitutional_mutation_router_execution",
                "typed_action_id": "sentientos.manifest.generate",
                "correlation_id": "cid-codex-e2e",
            }
        ],
    )

    diagnostic = build_scoped_lifecycle_diagnostic(tmp_path)

    assert diagnostic["delegated_judgment"]["recommended_venue"] == "codex_implementation"
    handoff = diagnostic["orchestration_handoff"]
    assert handoff["intent"]["intent_kind"] == "codex_work_order"
    assert handoff["handoff_result"]["handoff_outcome"] in {"blocked_by_operator_requirement", "blocked_by_insufficient_context", "staged_only"}
    assert handoff["execution_result"]["orchestration_result_state"] == "handoff_not_admitted"
    codex_diag = handoff["codex_staged_venue"]
    assert codex_diag is not None
    assert codex_diag["proof_artifact"]["ledger_path"] == "glow/orchestration/codex_work_orders.jsonl"
    assert codex_diag["lifecycle_visibility"]["lifecycle_state"] == "blocked_operator_required"
    assert codex_diag["packet_fulfillment_visibility"]["fulfillment_received"] is False
    assert codex_diag["executability_visibility"]["not_directly_executable_here"] is True
    assert handoff["handoff_packet"]["fulfillment_visibility"]["does_not_imply_direct_repo_execution"] is True


def test_end_to_end_deep_research_staged_venue_visibility_is_honest(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("sentientos.scoped_lifecycle_diagnostic.SCOPED_ACTION_IDS", ("sentientos.manifest.generate",))

    def _fake_resolver(_repo_root: Path, *, action_id: str, correlation_id: str) -> dict[str, object]:
        return {
            "typed_action_identity": action_id,
            "correlation_id": correlation_id,
            "outcome_class": "success",
        }

    monkeypatch.setattr("sentientos.scoped_lifecycle_diagnostic.resolve_scoped_mutation_lifecycle", _fake_resolver)
    monkeypatch.setattr(
        "sentientos.scoped_lifecycle_diagnostic.synthesize_delegated_judgment",
        lambda _evidence: synthesize_delegated_judgment({**_base_evidence(), "governance_ambiguity_signal": True}),
    )
    _write_json(tmp_path / "glow/contracts/contract_status.json", {"contracts": []})
    _write_jsonl(
        tmp_path / "pulse/forge_events.jsonl",
        [
            {
                "event": "constitutional_mutation_router_execution",
                "typed_action_id": "sentientos.manifest.generate",
                "correlation_id": "cid-deep-research-e2e",
            }
        ],
    )

    diagnostic = build_scoped_lifecycle_diagnostic(tmp_path)

    assert diagnostic["delegated_judgment"]["recommended_venue"] == "deep_research_audit"
    handoff = diagnostic["orchestration_handoff"]
    assert handoff["intent"]["intent_kind"] == "deep_research_work_order"
    assert handoff["handoff_result"]["handoff_outcome"] in {"blocked_by_operator_requirement", "blocked_by_insufficient_context", "staged_only"}
    assert handoff["execution_result"]["orchestration_result_state"] == "handoff_not_admitted"
    deep_research_diag = handoff["deep_research_staged_venue"]
    assert deep_research_diag is not None
    assert deep_research_diag["proof_artifact"]["ledger_path"] == "glow/orchestration/deep_research_work_orders.jsonl"
    assert deep_research_diag["lifecycle_visibility"]["lifecycle_state"] == "blocked_operator_required"
    assert deep_research_diag["packet_fulfillment_visibility"]["fulfillment_received"] is False
    assert deep_research_diag["executability_visibility"]["not_directly_executable_here"] is True


def test_end_to_end_staged_to_external_fulfillment_receipt_to_diagnostic_visibility(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("sentientos.scoped_lifecycle_diagnostic.SCOPED_ACTION_IDS", ("sentientos.manifest.generate",))

    def _fake_resolver(_repo_root: Path, *, action_id: str, correlation_id: str) -> dict[str, object]:
        return {
            "typed_action_identity": action_id,
            "correlation_id": correlation_id,
            "outcome_class": "success",
        }

    monkeypatch.setattr("sentientos.scoped_lifecycle_diagnostic.resolve_scoped_mutation_lifecycle", _fake_resolver)
    monkeypatch.setattr(
        "sentientos.scoped_lifecycle_diagnostic.synthesize_delegated_judgment",
        lambda _evidence: synthesize_delegated_judgment(_base_evidence()),
    )
    monkeypatch.setattr(
        "sentientos.scoped_lifecycle_diagnostic.derive_next_venue_recommendation",
        lambda *_args, **_kwargs: {
            "next_venue_recommendation": "prefer_codex_implementation",
            "relation_to_delegated_judgment": "affirming",
            "basis": {},
        },
    )
    _write_json(tmp_path / "glow/contracts/contract_status.json", {"contracts": []})
    _write_jsonl(
        tmp_path / "pulse/forge_events.jsonl",
        [
            {
                "event": "constitutional_mutation_router_execution",
                "typed_action_id": "sentientos.manifest.generate",
                "correlation_id": "cid-codex-fulfilled-e2e",
            }
        ],
    )

    first = build_scoped_lifecycle_diagnostic(tmp_path)
    handoff_packet = first["orchestration_handoff"]["handoff_packet"]
    assert handoff_packet["target_venue"] == "codex_implementation"
    receipt = ingest_external_fulfillment_receipt(
        tmp_path,
        handoff_packet_id=str(handoff_packet["handoff_packet_id"]),
        fulfillment_kind="externally_completed",
        operator_or_adapter="operator:e2e-test",
        summary_notes="external codex completion reported",
        evidence_refs=["artifacts/e2e.patch"],
        created_at="2026-04-12T00:10:00Z",
    )
    receipt_rows = (tmp_path / "glow/orchestration/orchestration_fulfillment_receipts.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(receipt_rows) == 1
    assert receipt["ingested_external_outcome"] is True
    assert receipt["non_authoritative"] is True
    assert receipt["receipt_only"] is True
    assert receipt["does_not_imply_direct_repo_execution"] is True

    second = build_scoped_lifecycle_diagnostic(tmp_path)
    codex_diag = second["orchestration_handoff"]["codex_staged_venue"]
    assert codex_diag is not None
    unified = second["orchestration_handoff"]["unified_result"]
    unified_surface = second["orchestration_handoff"]["unified_result_surface"]
    unified_quality_review = second["orchestration_handoff"]["unified_result_quality_review"]
    outcome_review = second["orchestration_handoff"]["outcome_review"]
    venue_mix_review = second["orchestration_handoff"]["venue_mix_review"]
    next_venue = second["orchestration_handoff"]["next_venue_recommendation"]
    feedback_visibility = second["orchestration_handoff"]["external_fulfillment_feedback_visibility"]
    packet_fulfillment = codex_diag["packet_fulfillment_visibility"]
    assert packet_fulfillment["fulfillment_received"] is True
    assert packet_fulfillment["lifecycle_state"] == "fulfilled_externally"
    assert packet_fulfillment["fulfillment_kind"] == "externally_completed"
    assert packet_fulfillment["receipt_artifact_path"] == "glow/orchestration/orchestration_fulfillment_receipts.jsonl"
    assert packet_fulfillment["does_not_imply_direct_repo_execution"] is True
    assert unified["resolution_path"] == "external_fulfillment"
    assert unified["result_classification"] == "completed_successfully"
    assert unified["path_honesty"]["fulfillment_receipt_observed"] is True
    assert unified["path_honesty"]["does_not_imply_direct_repo_execution"] is True
    assert unified_surface["records_considered"] >= 1
    assert unified_surface["resolution_path_counts"]["external_fulfillment"] >= 1
    assert unified_quality_review["review_kind"] == "unified_result_quality_retrospective"
    assert unified_quality_review["recent_resolution_path_counts"]["external_fulfillment"] >= 1
    assert unified_quality_review["diagnostic_only"] is True
    assert unified_quality_review["non_authoritative"] is True
    assert unified_quality_review["decision_power"] == "none"
    assert unified_quality_review["summary"]["boundaries"]["preserves_resolution_path_honesty"] is True
    assert outcome_review["summary"]["external_fulfillment_influence"]["influenced_outcome_review"] is True
    assert venue_mix_review["summary"]["external_fulfillment_influence"]["influenced_venue_mix_review"] is True
    trust_posture = second["orchestration_handoff"]["trust_confidence_posture"]
    readiness = second["orchestration_handoff"]["delegated_operation_readiness"]
    packetization_gating = second["orchestration_handoff"]["packetization_gating"]
    assert trust_posture["schema_version"] == "orchestration_trust_confidence_posture.v1"
    assert trust_posture["diagnostic_only"] is True
    assert trust_posture["non_authoritative"] is True
    assert trust_posture["decision_power"] == "none"
    assert feedback_visibility["outcome_review"]["external_fulfillment_influencing"] is True
    assert feedback_visibility["venue_mix_review"]["external_fulfillment_influencing"] is True
    assert next_venue["relation_to_delegated_judgment"] == "affirming"
    assert feedback_visibility["non_authoritative"] is True
    assert packetization_gating["schema_version"] == "orchestration_packetization_gate.v1"
    assert packetization_gating["signal_snapshot"]["trust_confidence_posture"] == trust_posture["trust_confidence_posture"]
    assert packetization_gating["packetization_outcome"] in {
        "packetization_allowed",
        "packetization_allowed_with_caution",
        "packetization_hold_operator_review",
        "packetization_hold_insufficient_confidence",
        "packetization_hold_fragmentation",
        "packetization_hold_escalation_required",
    }
    assert packetization_gating["non_sovereign_boundaries"]["does_not_execute_or_route_work"] is True
    readiness_basis = second["delegated_judgment"]["orchestration_substitution_readiness"]["trust_confidence_basis"]
    assert readiness_basis["orchestration_trust_confidence_posture"] == trust_posture["trust_confidence_posture"]
    assert readiness_basis["delegated_operation_readiness_verdict"] == readiness["readiness_verdict"]
    assert readiness_basis["does_not_change_existing_readiness_logic"] is True
    assert readiness["schema_version"] == "delegated_operation_readiness_verdict.v1"
    assert readiness["summary"]["boundaries"]["diagnostic_only"] is True
    assert readiness["summary"]["boundaries"]["decision_power"] == "none"
    assert readiness["does_not_execute_or_route_work"] is True


def test_current_orchestration_state_ready_to_packetize_when_allowed_without_packet(tmp_path: Path) -> None:
    state = resolve_current_orchestration_state(
        tmp_path,
        current_proposal={"proposal_id": "proposal-ready"},
        packetization_gate={"packetization_outcome": "packetization_allowed", "packetization_allowed": True},
        active_packet_visibility={"active_packet_present": False},
        operator_brief_lifecycle={"awaiting_operator_input": False},
        unified_result={"result_classification": "pending_or_unresolved", "resolution_path": "internal_execution"},
    )
    assert state["current_supervisory_state"] == "ready_to_packetize"
    assert state["state_focus"] == "proposal"
    assert state["awaiting_actor"] == "none"


def test_current_orchestration_state_waiting_for_internal_result_with_pending_internal_packet(tmp_path: Path) -> None:
    state = resolve_current_orchestration_state(
        tmp_path,
        current_proposal={"proposal_id": "proposal-internal"},
        packetization_gate={"packetization_outcome": "packetization_allowed", "packetization_allowed": True},
        active_packet_visibility={
            "active_packet_present": True,
            "active_handoff_packet_id": "packet-int",
            "active_packet_status": "ready_for_internal_trigger",
            "active_target_venue": "internal_direct_execution",
        },
        operator_brief_lifecycle={"awaiting_operator_input": False},
        unified_result={
            "orchestration_result_id": "oru-pending",
            "resolution_path": "internal_execution",
            "resolution_state": "handoff_admitted_pending_result",
            "result_classification": "pending_or_unresolved",
        },
    )
    assert state["current_supervisory_state"] == "waiting_for_internal_result"
    assert state["state_focus"] == "internal_execution"
    assert state["awaiting_actor"] == "internal_substrate"


def test_current_orchestration_state_waiting_for_external_fulfillment_when_staged_packet_unfulfilled(tmp_path: Path) -> None:
    proposal_id = "proposal-ext"
    _write_jsonl(
        tmp_path / "glow/orchestration/orchestration_handoff_packets.jsonl",
        [
            _packet_row(
                proposal_id=proposal_id,
                packet_id="packet-ext",
                status="prepared",
                venue="codex_implementation",
                gate_outcome="packetization_allowed",
            )
        ],
    )
    state = resolve_current_orchestration_state(
        tmp_path,
        current_proposal={"proposal_id": proposal_id},
        packetization_gate={"packetization_outcome": "packetization_allowed", "packetization_allowed": True},
        active_packet_visibility={
            "active_packet_present": True,
            "active_handoff_packet_id": "packet-ext",
            "active_packet_status": "prepared",
            "active_target_venue": "codex_implementation",
        },
        operator_brief_lifecycle={"awaiting_operator_input": False},
        unified_result={"result_classification": "pending_or_unresolved", "resolution_path": "external_fulfillment"},
    )
    assert state["current_supervisory_state"] == "waiting_for_external_fulfillment"
    assert state["state_focus"] == "external_fulfillment"
    assert state["awaiting_actor"] == "external_actor"


def test_current_orchestration_state_waiting_for_operator_resolution_when_brief_unresolved(tmp_path: Path) -> None:
    state = resolve_current_orchestration_state(
        tmp_path,
        current_proposal={"proposal_id": "proposal-operator"},
        packetization_gate={
            "packetization_outcome": "packetization_hold_operator_review",
            "packetization_allowed": False,
        },
        active_packet_visibility={"active_packet_present": False},
        operator_brief_lifecycle={
            "operator_action_brief_id": "brief-1",
            "awaiting_operator_input": True,
            "operator_resolution_received": False,
        },
    )
    assert state["current_supervisory_state"] == "waiting_for_operator_resolution"
    assert state["state_focus"] == "operator_brief"
    assert state["awaiting_actor"] == "operator"


def test_current_orchestration_state_reports_fragmentation_hold(tmp_path: Path) -> None:
    state = resolve_current_orchestration_state(
        tmp_path,
        current_proposal={"proposal_id": "proposal-hold"},
        packetization_gate={
            "packetization_outcome": "packetization_hold_fragmentation",
            "packetization_allowed": False,
        },
        active_packet_visibility={"active_packet_present": False},
        operator_brief_lifecycle={"awaiting_operator_input": False},
    )
    assert state["current_supervisory_state"] == "held_due_to_fragmentation"
    assert state["state_focus"] == "proposal"


def test_current_orchestration_state_reports_completed_without_active_item(tmp_path: Path) -> None:
    state = resolve_current_orchestration_state(
        tmp_path,
        current_proposal={},
        active_packet_visibility={"active_packet_present": False},
        operator_brief_lifecycle={"awaiting_operator_input": False},
        unified_result={
            "orchestration_result_id": "oru-complete",
            "result_classification": "completed_successfully",
            "resolution_path": "external_fulfillment",
        },
    )
    assert state["current_supervisory_state"] == "completed_recently_no_current_item"
    assert state["state_focus"] == "completed_or_idle"
    assert state["awaiting_actor"] == "none"


def test_current_orchestration_state_reports_no_active_item_when_no_evidence(tmp_path: Path) -> None:
    state = resolve_current_orchestration_state(
        tmp_path,
        current_proposal={},
        active_packet_visibility={"active_packet_present": False},
        operator_brief_lifecycle={"awaiting_operator_input": False},
        unified_result={},
    )
    assert state["current_supervisory_state"] == "no_active_orchestration_item"
    assert state["state_focus"] == "completed_or_idle"
    assert state["awaiting_actor"] == "none"


def test_orchestration_watchpoint_awaits_operator_resolution_from_current_state(tmp_path: Path) -> None:
    state = resolve_current_orchestration_state(
        tmp_path,
        current_proposal={"proposal_id": "proposal-operator"},
        packetization_gate={"packetization_outcome": "packetization_hold_operator_review", "packetization_allowed": False},
        active_packet_visibility={"active_packet_present": False},
        operator_brief_lifecycle={"awaiting_operator_input": True},
    )
    watchpoint = resolve_current_orchestration_watchpoint(tmp_path, current_orchestration_state=state)
    assert watchpoint["watchpoint_class"] == "await_operator_resolution"
    assert watchpoint["expected_actor"] == "operator"
    assert watchpoint["expected_signal_type"] == "operator_resolution_receipt"
    assert watchpoint["wake_condition_summary"]["loop_activity"] == "actively_blocked"


def test_orchestration_watchpoint_awaits_internal_execution_result(tmp_path: Path) -> None:
    state = resolve_current_orchestration_state(
        tmp_path,
        current_proposal={"proposal_id": "proposal-internal"},
        packetization_gate={"packetization_outcome": "packetization_allowed", "packetization_allowed": True},
        active_packet_visibility={
            "active_packet_present": True,
            "active_handoff_packet_id": "packet-int",
            "active_packet_status": "ready_for_internal_trigger",
            "active_target_venue": "internal_direct_execution",
        },
        operator_brief_lifecycle={"awaiting_operator_input": False},
        unified_result={"resolution_state": "handoff_admitted_pending_result", "result_classification": "pending_or_unresolved"},
    )
    watchpoint = resolve_current_orchestration_watchpoint(tmp_path, current_orchestration_state=state)
    assert watchpoint["watchpoint_class"] == "await_internal_execution_result"
    assert watchpoint["expected_actor"] == "internal_substrate"
    assert watchpoint["expected_signal_type"] == "internal_execution_result"


def test_orchestration_watchpoint_awaits_external_fulfillment_receipt(tmp_path: Path) -> None:
    proposal_id = "proposal-ext-watchpoint"
    _write_jsonl(
        tmp_path / "glow/orchestration/orchestration_handoff_packets.jsonl",
        [_packet_row(proposal_id=proposal_id, packet_id="packet-ext-watchpoint", status="prepared", venue="codex_implementation")],
    )
    state = resolve_current_orchestration_state(
        tmp_path,
        current_proposal={"proposal_id": proposal_id},
        packetization_gate={"packetization_outcome": "packetization_allowed", "packetization_allowed": True},
        active_packet_visibility={
            "active_packet_present": True,
            "active_handoff_packet_id": "packet-ext-watchpoint",
            "active_packet_status": "prepared",
            "active_target_venue": "codex_implementation",
        },
        operator_brief_lifecycle={"awaiting_operator_input": False},
        unified_result={"result_classification": "pending_or_unresolved", "resolution_path": "external_fulfillment"},
    )
    watchpoint = resolve_current_orchestration_watchpoint(tmp_path, current_orchestration_state=state)
    assert watchpoint["watchpoint_class"] == "await_external_fulfillment_receipt"
    assert watchpoint["expected_actor"] == "external_actor"
    assert watchpoint["expected_signal_type"] == "external_fulfillment_receipt"


def test_orchestration_watchpoint_awaits_packetization_relief_for_held_state(tmp_path: Path) -> None:
    state = resolve_current_orchestration_state(
        tmp_path,
        current_proposal={"proposal_id": "proposal-hold"},
        packetization_gate={"packetization_outcome": "packetization_hold_fragmentation", "packetization_allowed": False},
        active_packet_visibility={"active_packet_present": False},
        operator_brief_lifecycle={"awaiting_operator_input": False},
    )
    watchpoint = resolve_current_orchestration_watchpoint(tmp_path, current_orchestration_state=state)
    assert watchpoint["watchpoint_class"] == "await_packetization_relief"
    assert watchpoint["expected_actor"] == "orchestration_body"
    assert watchpoint["wake_condition_summary"]["loop_activity"] == "actively_blocked"


def test_orchestration_watchpoint_awaits_new_proposal_when_no_active_item(tmp_path: Path) -> None:
    state = resolve_current_orchestration_state(
        tmp_path,
        current_proposal={},
        active_packet_visibility={"active_packet_present": False},
        operator_brief_lifecycle={"awaiting_operator_input": False},
        unified_result={},
    )
    watchpoint = resolve_current_orchestration_watchpoint(tmp_path, current_orchestration_state=state)
    assert watchpoint["watchpoint_class"] == "await_new_proposal"
    assert watchpoint["expected_actor"] == "orchestration_body"
    assert watchpoint["expected_signal_type"] == "next_move_proposal"


def test_orchestration_watchpoint_reports_no_watchpoint_needed_for_completed_item(tmp_path: Path) -> None:
    state = resolve_current_orchestration_state(
        tmp_path,
        current_proposal={},
        active_packet_visibility={"active_packet_present": False},
        operator_brief_lifecycle={"awaiting_operator_input": False},
        unified_result={
            "orchestration_result_id": "oru-complete-watchpoint",
            "result_classification": "completed_successfully",
            "resolution_path": "external_fulfillment",
        },
    )
    watchpoint = resolve_current_orchestration_watchpoint(tmp_path, current_orchestration_state=state)
    assert watchpoint["watchpoint_class"] == "no_watchpoint_needed"
    assert watchpoint["expected_actor"] == "none"
    assert watchpoint["wake_condition_summary"]["loop_activity"] == "not_waiting"


def test_watchpoint_satisfaction_marks_operator_resolution_satisfied(tmp_path: Path) -> None:
    state = resolve_current_orchestration_state(
        tmp_path,
        current_proposal={"proposal_id": "proposal-operator"},
        packetization_gate={"packetization_outcome": "packetization_hold_operator_review", "packetization_allowed": False},
        operator_brief_lifecycle={
            "operator_action_brief_id": "brief-1",
            "awaiting_operator_input": True,
        },
    )
    watchpoint = resolve_current_orchestration_watchpoint(tmp_path, current_orchestration_state=state)
    satisfaction = resolve_watchpoint_satisfaction(
        tmp_path,
        current_orchestration_state=state,
        current_orchestration_watchpoint=watchpoint,
        operator_brief_lifecycle={"operator_resolution_received": True, "operator_resolution_receipt_id": "orr-1"},
    )
    assert satisfaction["satisfaction_status"] == "watchpoint_satisfied"
    assert satisfaction["satisfied_by_actor"] == "operator"


def test_watchpoint_satisfaction_marks_internal_result_satisfied(tmp_path: Path) -> None:
    state = resolve_current_orchestration_state(
        tmp_path,
        current_proposal={"proposal_id": "proposal-int"},
        packetization_gate={"packetization_outcome": "packetization_allowed", "packetization_allowed": True},
        active_packet_visibility={
            "active_packet_present": True,
            "active_handoff_packet_id": "packet-int",
            "active_packet_status": "ready_for_internal_trigger",
            "active_target_venue": "internal_direct_execution",
        },
        unified_result={
            "result_classification": "pending_or_unresolved",
            "resolution_path": "internal_execution",
            "resolution_state": "handoff_admitted_pending_result",
        },
    )
    watchpoint = resolve_current_orchestration_watchpoint(tmp_path, current_orchestration_state=state)
    satisfaction = resolve_watchpoint_satisfaction(
        tmp_path,
        current_orchestration_state=state,
        current_orchestration_watchpoint=watchpoint,
        unified_result={
            "resolution_path": "internal_execution",
            "result_classification": "completed_successfully",
            "evidence_presence": {"task_result_observed": True},
        },
    )
    assert satisfaction["satisfaction_status"] == "watchpoint_satisfied"
    assert satisfaction["satisfied_by_signal_type"] == "internal_execution_result"


def test_watchpoint_satisfaction_marks_external_receipt_satisfied(tmp_path: Path) -> None:
    state = resolve_current_orchestration_state(
        tmp_path,
        current_proposal={"proposal_id": "proposal-ext"},
        packetization_gate={"packetization_outcome": "packetization_allowed", "packetization_allowed": True},
        active_packet_visibility={
            "active_packet_present": True,
            "active_handoff_packet_id": "packet-ext",
            "active_packet_status": "prepared",
            "active_target_venue": "codex_implementation",
        },
        unified_result={"result_classification": "pending_or_unresolved", "resolution_path": "external_fulfillment"},
    )
    watchpoint = resolve_current_orchestration_watchpoint(tmp_path, current_orchestration_state=state)
    satisfaction = resolve_watchpoint_satisfaction(
        tmp_path,
        current_orchestration_state=state,
        current_orchestration_watchpoint=watchpoint,
        unified_result={
            "resolution_path": "external_fulfillment",
            "evidence_presence": {"fulfillment_receipt_observed": True},
            "result_classification": "completed_successfully",
        },
    )
    assert satisfaction["satisfaction_status"] == "watchpoint_satisfied"
    assert satisfaction["satisfied_by_actor"] == "external_actor"


def test_watchpoint_satisfaction_keeps_packetization_relief_pending_when_hold_unchanged(tmp_path: Path) -> None:
    state = resolve_current_orchestration_state(
        tmp_path,
        current_proposal={"proposal_id": "proposal-hold"},
        packetization_gate={"packetization_outcome": "packetization_hold_fragmentation", "packetization_allowed": False},
    )
    watchpoint = resolve_current_orchestration_watchpoint(tmp_path, current_orchestration_state=state)
    satisfaction = resolve_watchpoint_satisfaction(
        tmp_path,
        current_orchestration_state=state,
        current_orchestration_watchpoint=watchpoint,
        packetization_gate={"packetization_outcome": "packetization_hold_fragmentation", "packetization_held": True},
    )
    assert satisfaction["satisfaction_status"] == "watchpoint_pending"
    assert satisfaction["wake_readiness_summary"]["ready_for_re_evaluation"] is False


def test_watchpoint_satisfaction_marks_fragmented_when_linkage_missing(tmp_path: Path) -> None:
    state = resolve_current_orchestration_state(
        tmp_path,
        current_proposal={"proposal_id": "proposal-ext"},
        packetization_gate={"packetization_outcome": "packetization_allowed", "packetization_allowed": True},
        active_packet_visibility={
            "active_packet_present": True,
            "active_handoff_packet_id": "packet-ext",
            "active_packet_status": "prepared",
            "active_target_venue": "codex_implementation",
        },
        unified_result={"result_classification": "pending_or_unresolved", "resolution_path": "external_fulfillment"},
    )
    watchpoint = resolve_current_orchestration_watchpoint(tmp_path, current_orchestration_state=state)
    fragmented_state = {
        **state,
        "source_linkage": {
            **dict(state.get("source_linkage") or {}),
            "active_packet_ref": {"handoff_packet_id": None},
        },
    }
    satisfaction = resolve_watchpoint_satisfaction(
        tmp_path,
        current_orchestration_state=fragmented_state,
        current_orchestration_watchpoint=watchpoint,
        unified_result={"resolution_path": "external_fulfillment", "evidence_presence": {"fulfillment_receipt_observed": False}},
    )
    assert satisfaction["satisfaction_status"] == "watchpoint_fragmented"


def test_watchpoint_satisfaction_marks_stale_when_watchpoint_mismatches_state(tmp_path: Path) -> None:
    state = resolve_current_orchestration_state(
        tmp_path,
        current_proposal={"proposal_id": "proposal-operator"},
        packetization_gate={"packetization_outcome": "packetization_hold_operator_review", "packetization_allowed": False},
        operator_brief_lifecycle={"awaiting_operator_input": True},
    )
    stale_watchpoint = {
        **resolve_current_orchestration_watchpoint(tmp_path, current_orchestration_state=state),
        "watchpoint_class": "await_external_fulfillment_receipt",
    }
    satisfaction = resolve_watchpoint_satisfaction(
        tmp_path,
        current_orchestration_state=state,
        current_orchestration_watchpoint=stale_watchpoint,
    )
    assert satisfaction["satisfaction_status"] == "watchpoint_stale"


def test_watchpoint_satisfaction_reports_no_active_watchpoint(tmp_path: Path) -> None:
    state = resolve_current_orchestration_state(
        tmp_path,
        current_proposal={},
        active_packet_visibility={"active_packet_present": False},
        operator_brief_lifecycle={"awaiting_operator_input": False},
        unified_result={
            "orchestration_result_id": "oru-complete-watchpoint-satisfaction",
            "result_classification": "completed_successfully",
            "resolution_path": "external_fulfillment",
        },
    )
    watchpoint = resolve_current_orchestration_watchpoint(tmp_path, current_orchestration_state=state)
    satisfaction = resolve_watchpoint_satisfaction(
        tmp_path,
        current_orchestration_state=state,
        current_orchestration_watchpoint=watchpoint,
    )
    assert satisfaction["satisfaction_status"] == "no_active_watchpoint"
    assert satisfaction["satisfied_by_actor"] == "none"


def test_re_evaluation_trigger_operator_resolution_recommends_packet_synthesis(tmp_path: Path) -> None:
    state = {"current_orchestration_state_id": "ocs-re-eval-operator", "current_supervisory_state": "waiting_for_operator_resolution"}
    watchpoint = {
        "orchestration_watchpoint_id": "owp-re-eval-operator",
        "watchpoint_class": "await_operator_resolution",
        "expected_actor": "operator",
        "expected_signal_type": "operator_resolution_receipt",
    }
    satisfaction = {
        "watchpoint_satisfaction_id": "wps-re-eval-operator",
        "satisfaction_status": "watchpoint_satisfied",
    }
    trigger = resolve_re_evaluation_trigger_recommendation(
        tmp_path,
        current_orchestration_state=state,
        current_orchestration_watchpoint=watchpoint,
        watchpoint_satisfaction=satisfaction,
        operator_brief_lifecycle={"resolution_kind": "approved_with_constraints"},
    )
    assert trigger["recommendation"] == "rerun_packet_synthesis"
    assert trigger["expected_actor"] == "orchestration_body"


def test_re_evaluation_trigger_internal_result_recommends_judgment_rerun(tmp_path: Path) -> None:
    state = {
        "current_orchestration_state_id": "ocs-re-eval-internal",
        "current_supervisory_state": "waiting_for_internal_result",
        "current_resolution_path": "internal_execution",
    }
    watchpoint = {
        "orchestration_watchpoint_id": "owp-re-eval-internal",
        "watchpoint_class": "await_internal_execution_result",
        "expected_actor": "internal_substrate",
        "expected_signal_type": "internal_execution_result",
    }
    satisfaction = {
        "watchpoint_satisfaction_id": "wps-re-eval-internal",
        "satisfaction_status": "watchpoint_satisfied",
    }
    trigger = resolve_re_evaluation_trigger_recommendation(
        tmp_path,
        current_orchestration_state=state,
        current_orchestration_watchpoint=watchpoint,
        watchpoint_satisfaction=satisfaction,
        unified_result={"resolution_path": "internal_execution"},
    )
    assert trigger["recommendation"] == "rerun_delegated_judgment"


def test_re_evaluation_trigger_external_result_recommends_judgment_rerun(tmp_path: Path) -> None:
    state = {
        "current_orchestration_state_id": "ocs-re-eval-external",
        "current_supervisory_state": "waiting_for_external_fulfillment",
        "current_resolution_path": "external_fulfillment",
    }
    watchpoint = {
        "orchestration_watchpoint_id": "owp-re-eval-external",
        "watchpoint_class": "await_external_fulfillment_receipt",
        "expected_actor": "external_actor",
        "expected_signal_type": "external_fulfillment_receipt",
    }
    satisfaction = {
        "watchpoint_satisfaction_id": "wps-re-eval-external",
        "satisfaction_status": "watchpoint_satisfied",
    }
    trigger = resolve_re_evaluation_trigger_recommendation(
        tmp_path,
        current_orchestration_state=state,
        current_orchestration_watchpoint=watchpoint,
        watchpoint_satisfaction=satisfaction,
        unified_result={"resolution_path": "external_fulfillment"},
    )
    assert trigger["recommendation"] == "rerun_delegated_judgment"


def test_re_evaluation_trigger_fragmented_context_holds_for_manual_review(tmp_path: Path) -> None:
    state = {"current_orchestration_state_id": "ocs-re-eval-fragmented", "current_supervisory_state": "waiting_for_external_fulfillment"}
    watchpoint = {
        "orchestration_watchpoint_id": "owp-re-eval-fragmented",
        "watchpoint_class": "await_external_fulfillment_receipt",
        "expected_actor": "external_actor",
        "expected_signal_type": "external_fulfillment_receipt",
    }
    satisfaction = {"watchpoint_satisfaction_id": "wps-re-eval-fragmented", "satisfaction_status": "watchpoint_fragmented"}
    trigger = resolve_re_evaluation_trigger_recommendation(
        tmp_path,
        current_orchestration_state=state,
        current_orchestration_watchpoint=watchpoint,
        watchpoint_satisfaction=satisfaction,
    )
    assert trigger["recommendation"] == "hold_for_manual_review"
    assert trigger["expected_actor"] == "operator"


def test_re_evaluation_trigger_no_active_watchpoint_needs_no_re_evaluation(tmp_path: Path) -> None:
    state = resolve_current_orchestration_state(
        tmp_path,
        current_proposal={"proposal_id": None},
        packetization_gate={"packetization_outcome": "packetization_allowed", "packetization_allowed": True},
        active_packet_visibility={"active_packet_present": False},
        operator_brief_lifecycle={"awaiting_operator_input": False},
        unified_result={
            "orchestration_result_id": "oru-re-eval-none",
            "result_classification": "completed_successfully",
            "resolution_path": "external_fulfillment",
        },
    )
    watchpoint = resolve_current_orchestration_watchpoint(tmp_path, current_orchestration_state=state)
    satisfaction = resolve_watchpoint_satisfaction(
        tmp_path,
        current_orchestration_state=state,
        current_orchestration_watchpoint=watchpoint,
    )
    trigger = resolve_re_evaluation_trigger_recommendation(
        tmp_path,
        current_orchestration_state=state,
        current_orchestration_watchpoint=watchpoint,
        watchpoint_satisfaction=satisfaction,
    )
    assert watchpoint["watchpoint_class"] == "no_watchpoint_needed"
    assert trigger["recommendation"] == "no_re_evaluation_needed"
    assert trigger["expected_actor"] == "none"


def test_current_resumption_candidate_is_derived_from_existing_surfaces(tmp_path: Path) -> None:
    state = {
        "current_orchestration_state_id": "ocs-derived",
        "current_supervisory_state": "waiting_for_operator_resolution",
        "current_resolution_path": "operator_review",
        "source_linkage": {
            "current_proposal_ref": {"proposal_id": "prop-derived"},
            "active_packet_ref": {"handoff_packet_id": "pkt-derived"},
            "operator_brief_ref": {"operator_resolution_receipt_id": "orr-derived"},
            "unified_result_ref": {"orchestration_result_id": "oru-derived"},
        },
    }
    watchpoint = {"orchestration_watchpoint_id": "owp-derived", "watchpoint_class": "await_operator_resolution"}
    satisfaction = {"watchpoint_satisfaction_id": "wps-derived", "satisfaction_status": "watchpoint_satisfied"}
    trigger = {
        "re_evaluation_trigger_id": "ret-derived",
        "recommendation": "rerun_packet_synthesis",
        "expected_actor": "orchestration_body",
    }
    candidate = resolve_current_orchestration_resumption_candidate(
        tmp_path,
        current_orchestration_state=state,
        current_orchestration_watchpoint=watchpoint,
        watchpoint_satisfaction=satisfaction,
        re_evaluation_trigger_recommendation=trigger,
    )
    assert candidate["source_lineage"]["current_orchestration_state_ref"]["current_orchestration_state_id"] == "ocs-derived"
    assert candidate["source_lineage"]["current_orchestration_watchpoint_ref"]["orchestration_watchpoint_id"] == "owp-derived"
    assert candidate["source_lineage"]["watchpoint_satisfaction_ref"]["watchpoint_satisfaction_id"] == "wps-derived"
    assert candidate["source_lineage"]["re_evaluation_trigger_ref"]["re_evaluation_trigger_id"] == "ret-derived"
    assert candidate["bounded_resume_mode"] == trigger["recommendation"]
    assert candidate["resumption_candidate_only"] is True
    assert candidate["non_executing"] is True
    assert candidate["does_not_execute_or_route_work"] is True


def test_current_resumption_candidate_operator_resolution_wake_prefers_packet_refresh(tmp_path: Path) -> None:
    candidate = resolve_current_orchestration_resumption_candidate(
        tmp_path,
        current_orchestration_state={
            "current_orchestration_state_id": "ocs-resume-operator",
            "current_supervisory_state": "waiting_for_operator_resolution",
            "source_linkage": {"operator_brief_ref": {"operator_resolution_receipt_id": "orr-operator"}},
        },
        current_orchestration_watchpoint={
            "orchestration_watchpoint_id": "owp-resume-operator",
            "watchpoint_class": "await_operator_resolution",
        },
        watchpoint_satisfaction={"watchpoint_satisfaction_id": "wps-resume-operator", "satisfaction_status": "watchpoint_satisfied"},
        re_evaluation_trigger_recommendation={
            "re_evaluation_trigger_id": "ret-resume-operator",
            "recommendation": "rerun_packet_synthesis",
            "expected_actor": "orchestration_body",
        },
    )
    assert candidate["bounded_resume_mode"] == "rerun_packet_synthesis"
    assert candidate["continuity_posture"] == "refresh_packet_from_current_proposal_state"
    assert candidate["operator_influence_in_path"] is True


def test_current_resumption_candidate_internal_result_wake_uses_existing_unified_result_path(tmp_path: Path) -> None:
    candidate = resolve_current_orchestration_resumption_candidate(
        tmp_path,
        current_orchestration_state={
            "current_orchestration_state_id": "ocs-resume-internal",
            "current_supervisory_state": "waiting_for_internal_result",
            "source_linkage": {"unified_result_ref": {"orchestration_result_id": "oru-internal"}},
        },
        current_orchestration_watchpoint={
            "orchestration_watchpoint_id": "owp-resume-internal",
            "watchpoint_class": "await_internal_execution_result",
        },
        watchpoint_satisfaction={"watchpoint_satisfaction_id": "wps-resume-internal", "satisfaction_status": "watchpoint_satisfied"},
        re_evaluation_trigger_recommendation={
            "re_evaluation_trigger_id": "ret-resume-internal",
            "recommendation": "rerun_delegated_judgment",
            "expected_actor": "orchestration_body",
        },
    )
    assert candidate["bounded_resume_mode"] == "rerun_delegated_judgment"
    assert candidate["continuity_posture"] == "recompute_from_proposal_level_state"
    assert candidate["source_lineage"]["unified_result_ref"]["orchestration_result_id"] == "oru-internal"


def test_current_resumption_candidate_external_result_wake_uses_existing_unified_result_path(tmp_path: Path) -> None:
    candidate = resolve_current_orchestration_resumption_candidate(
        tmp_path,
        current_orchestration_state={
            "current_orchestration_state_id": "ocs-resume-external",
            "current_supervisory_state": "waiting_for_external_fulfillment",
            "source_linkage": {"unified_result_ref": {"orchestration_result_id": "oru-external"}},
        },
        current_orchestration_watchpoint={
            "orchestration_watchpoint_id": "owp-resume-external",
            "watchpoint_class": "await_external_fulfillment_receipt",
        },
        watchpoint_satisfaction={"watchpoint_satisfaction_id": "wps-resume-external", "satisfaction_status": "watchpoint_satisfied"},
        re_evaluation_trigger_recommendation={
            "re_evaluation_trigger_id": "ret-resume-external",
            "recommendation": "rerun_delegated_judgment",
            "expected_actor": "orchestration_body",
        },
    )
    assert candidate["bounded_resume_mode"] == "rerun_delegated_judgment"
    assert candidate["continuity_posture"] == "recompute_from_proposal_level_state"
    assert candidate["source_lineage"]["unified_result_ref"]["orchestration_result_id"] == "oru-external"


def test_current_resumption_candidate_continue_current_packet_continuity_case(tmp_path: Path) -> None:
    candidate = resolve_current_orchestration_resumption_candidate(
        tmp_path,
        current_orchestration_state={
            "current_orchestration_state_id": "ocs-resume-continue",
            "current_supervisory_state": "held_due_to_fragmentation",
            "source_linkage": {"active_packet_ref": {"handoff_packet_id": "pkt-continue"}},
        },
        current_orchestration_watchpoint={
            "orchestration_watchpoint_id": "owp-resume-continue",
            "watchpoint_class": "await_packetization_relief",
        },
        watchpoint_satisfaction={"watchpoint_satisfaction_id": "wps-resume-continue", "satisfaction_status": "watchpoint_satisfied"},
        re_evaluation_trigger_recommendation={
            "re_evaluation_trigger_id": "ret-resume-continue",
            "recommendation": "clear_wait_and_continue_current_packet",
            "expected_actor": "orchestration_body",
        },
    )
    assert candidate["bounded_resume_mode"] == "clear_wait_and_continue_current_packet"
    assert candidate["continuity_posture"] == "continue_current_active_packet"
    assert candidate["resume_ready"] is True


def test_current_resumption_candidate_fragmented_or_stale_context_holds_for_manual_review(tmp_path: Path) -> None:
    candidate = resolve_current_orchestration_resumption_candidate(
        tmp_path,
        current_orchestration_state={
            "current_orchestration_state_id": "ocs-resume-hold",
            "current_supervisory_state": "waiting_for_external_fulfillment",
        },
        current_orchestration_watchpoint={
            "orchestration_watchpoint_id": "owp-resume-hold",
            "watchpoint_class": "await_external_fulfillment_receipt",
        },
        watchpoint_satisfaction={"watchpoint_satisfaction_id": "wps-resume-hold", "satisfaction_status": "watchpoint_fragmented"},
        re_evaluation_trigger_recommendation={
            "re_evaluation_trigger_id": "ret-resume-hold",
            "recommendation": "hold_for_manual_review",
            "expected_actor": "operator",
        },
    )
    assert candidate["resumption_candidate_class"] == "manual_review_hold"
    assert candidate["bounded_resume_mode"] == "hold_for_manual_review"
    assert candidate["resume_ready"] is False


def test_current_resumption_candidate_no_active_watchpoint_case_remains_no_resume(tmp_path: Path) -> None:
    candidate = resolve_current_orchestration_resumption_candidate(
        tmp_path,
        current_orchestration_state={
            "current_orchestration_state_id": "ocs-resume-none",
            "current_supervisory_state": "completed_recently_no_current_item",
        },
        current_orchestration_watchpoint={
            "orchestration_watchpoint_id": "owp-resume-none",
            "watchpoint_class": "no_watchpoint_needed",
        },
        watchpoint_satisfaction={"watchpoint_satisfaction_id": "wps-resume-none", "satisfaction_status": "no_active_watchpoint"},
        re_evaluation_trigger_recommendation={
            "re_evaluation_trigger_id": "ret-resume-none",
            "recommendation": "no_re_evaluation_needed",
            "expected_actor": "none",
        },
    )
    assert candidate["resumption_candidate_class"] == "no_resume_candidate"
    assert candidate["bounded_resume_mode"] == "no_re_evaluation_needed"
    assert candidate["resume_ready"] is False


def test_current_resumed_operation_readiness_ready_to_proceed_case() -> None:
    readiness = resolve_current_resumed_operation_readiness_verdict(
        current_orchestration_state={"current_supervisory_state": "held_due_to_fragmentation"},
        current_orchestration_watchpoint={"watchpoint_class": "await_packetization_relief"},
        watchpoint_satisfaction={"satisfaction_status": "watchpoint_satisfied"},
        re_evaluation_trigger_recommendation={"recommendation": "clear_wait_and_continue_current_packet"},
        current_orchestration_resumption_candidate={
            "resumption_candidate_class": "resumption_candidate",
            "resume_ready": True,
            "continuity_posture": "continue_current_active_packet",
        },
        delegated_operation_readiness={"readiness_verdict": "ready_for_bounded_supervised_operation"},
        packetization_gate={"packetization_outcome": "packetization_allowed", "packetization_allowed": True},
        active_packet_visibility={"handoff_packet_id": "pkt-ready"},
    )
    assert readiness["resumed_operation_readiness_verdict"] == "ready_to_proceed"
    assert readiness["basis"]["based_on"]["continuity_confidence"] is True


def test_current_resumed_operation_readiness_proceed_with_caution_case() -> None:
    readiness = resolve_current_resumed_operation_readiness_verdict(
        current_orchestration_state={"current_supervisory_state": "waiting_for_external_fulfillment"},
        current_orchestration_watchpoint={"watchpoint_class": "await_external_fulfillment_receipt"},
        watchpoint_satisfaction={"satisfaction_status": "watchpoint_satisfied"},
        re_evaluation_trigger_recommendation={"recommendation": "rerun_delegated_judgment"},
        current_orchestration_resumption_candidate={
            "resumption_candidate_class": "resumption_candidate",
            "resume_ready": True,
            "continuity_posture": "recompute_from_proposal_level_state",
        },
        delegated_operation_readiness={"readiness_verdict": "ready_with_caution"},
        packetization_gate={"packetization_outcome": "packetization_allowed_with_caution", "packetization_allowed": True},
        current_proposal={"proposal_id": "prop-caution"},
    )
    assert readiness["resumed_operation_readiness_verdict"] == "proceed_with_caution"
    assert readiness["basis"]["based_on"]["continuity_confidence"] is True


def test_current_resumed_operation_readiness_stale_or_fragmented_context_holds() -> None:
    readiness = resolve_current_resumed_operation_readiness_verdict(
        current_orchestration_state={"current_supervisory_state": "waiting_for_external_fulfillment"},
        current_orchestration_watchpoint={"watchpoint_class": "await_external_fulfillment_receipt"},
        watchpoint_satisfaction={"satisfaction_status": "watchpoint_fragmented"},
        re_evaluation_trigger_recommendation={"recommendation": "hold_for_manual_review"},
        current_orchestration_resumption_candidate={
            "resumption_candidate_class": "manual_review_hold",
            "resume_ready": False,
            "continuity_posture": "none",
        },
        delegated_operation_readiness={"readiness_verdict": "temporarily_unfit_due_to_fragmentation"},
    )
    assert readiness["resumed_operation_readiness_verdict"] == "hold_for_operator_review"
    assert readiness["basis"]["based_on"]["stale_or_fragmented_wake_context"] is True


def test_current_resumed_operation_readiness_unresolved_operator_influence_holds() -> None:
    readiness = resolve_current_resumed_operation_readiness_verdict(
        current_orchestration_state={"current_supervisory_state": "waiting_for_operator_resolution"},
        current_orchestration_watchpoint={"watchpoint_class": "await_operator_resolution"},
        watchpoint_satisfaction={"satisfaction_status": "watchpoint_pending"},
        re_evaluation_trigger_recommendation={"recommendation": "rerun_packet_synthesis"},
        current_orchestration_resumption_candidate={
            "resumption_candidate_class": "resumption_candidate",
            "resume_ready": True,
            "continuity_posture": "refresh_packet_from_current_proposal_state",
        },
        delegated_operation_readiness={"readiness_verdict": "operator_review_required"},
        current_proposal={"proposal_id": "prop-operator-hold"},
        operator_resolution_influence={"operator_influence_state": "operator_defer_preserved_hold"},
    )
    assert readiness["resumed_operation_readiness_verdict"] == "hold_for_operator_review"
    assert readiness["basis"]["based_on"]["unresolved_operator_influence"] is True


def test_current_resumed_operation_readiness_no_active_watchpoint_or_resume_is_not_ready() -> None:
    readiness = resolve_current_resumed_operation_readiness_verdict(
        current_orchestration_state={"current_supervisory_state": "completed_recently_no_current_item"},
        current_orchestration_watchpoint={"watchpoint_class": "no_watchpoint_needed"},
        watchpoint_satisfaction={"satisfaction_status": "no_active_watchpoint"},
        re_evaluation_trigger_recommendation={"recommendation": "no_re_evaluation_needed"},
        current_orchestration_resumption_candidate={
            "resumption_candidate_class": "no_resume_candidate",
            "resume_ready": False,
            "continuity_posture": "none",
        },
    )
    assert readiness["resumed_operation_readiness_verdict"] == "not_ready"
    assert readiness["basis"]["based_on"]["continuity_confidence"] is False


def test_current_resumed_operation_readiness_surface_is_non_authoritative_and_non_executing(tmp_path: Path) -> None:
    judgment = synthesize_delegated_judgment(_base_evidence())
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    append_orchestration_intent_ledger(tmp_path, intent)
    before = admit_orchestration_intent(tmp_path, intent)
    readiness = resolve_current_resumed_operation_readiness_verdict(
        current_orchestration_state={"current_supervisory_state": "no_active_orchestration_item"},
        current_orchestration_watchpoint={"watchpoint_class": "no_watchpoint_needed"},
        watchpoint_satisfaction={"satisfaction_status": "no_active_watchpoint"},
        re_evaluation_trigger_recommendation={"recommendation": "no_re_evaluation_needed"},
        current_orchestration_resumption_candidate={
            "resumption_candidate_class": "no_resume_candidate",
            "resume_ready": False,
            "continuity_posture": "none",
        },
    )
    after = admit_orchestration_intent(tmp_path, intent)
    assert readiness["non_authoritative"] is True
    assert readiness["non_executing"] is True
    assert readiness["decision_power"] == "none"
    assert readiness["does_not_execute_or_route_work"] is True
    assert before["handoff_outcome"] == after["handoff_outcome"]


@pytest.mark.parametrize(
    ("watchpoint_class", "satisfaction_status", "expected_wait_kind"),
    [
        ("await_operator_resolution", "watchpoint_pending", "awaiting_operator_resolution"),
        ("await_external_fulfillment_receipt", "watchpoint_pending", "awaiting_external_fulfillment"),
        ("await_internal_execution_result", "watchpoint_pending", "awaiting_internal_result_closure"),
        ("await_external_fulfillment_receipt", "watchpoint_fragmented", "continuity_uncertain"),
        ("no_watchpoint_needed", "no_active_watchpoint", "no_active_watchpoint"),
    ],
)
def test_current_orchestration_watchpoint_brief_wait_kind_cases(
    tmp_path: Path,
    watchpoint_class: str,
    satisfaction_status: str,
    expected_wait_kind: str,
) -> None:
    brief = resolve_current_orchestration_watchpoint_brief(
        tmp_path,
        current_orchestration_state={
            "current_orchestration_state_id": f"ocs-brief-{watchpoint_class}",
            "current_supervisory_state": "waiting_for_external_fulfillment",
            "source_linkage": {
                "active_packet_ref": {"handoff_packet_id": "pkt-brief"},
                "current_proposal_ref": {"proposal_id": "prop-brief"},
                "operator_brief_ref": {"operator_resolution_receipt_id": "orr-brief"},
                "unified_result_ref": {"orchestration_result_id": "oru-brief"},
            },
        },
        current_orchestration_watchpoint={
            "orchestration_watchpoint_id": f"owp-brief-{watchpoint_class}",
            "watchpoint_class": watchpoint_class,
            "wake_condition": "bounded_test_wait_condition",
        },
        watchpoint_satisfaction={
            "watchpoint_satisfaction_id": f"wps-brief-{watchpoint_class}",
            "satisfaction_status": satisfaction_status,
        },
        re_evaluation_trigger_recommendation={
            "re_evaluation_trigger_id": f"ret-brief-{watchpoint_class}",
            "recommendation": "hold_for_manual_review" if satisfaction_status == "watchpoint_fragmented" else "no_re_evaluation_needed",
            "expected_actor": "operator" if satisfaction_status == "watchpoint_fragmented" else "none",
        },
        current_orchestration_resumption_candidate={
            "orchestration_resumption_candidate_id": f"orc-brief-{watchpoint_class}",
            "bounded_resume_mode": "no_re_evaluation_needed",
            "resume_ready": False,
        },
        current_resumed_operation_readiness={
            "resumed_operation_readiness_verdict": "hold_for_operator_review"
            if satisfaction_status == "watchpoint_fragmented"
            else "not_ready",
        },
    )
    assert brief["wait_kind"] == expected_wait_kind


def test_current_orchestration_watchpoint_brief_satisfaction_already_present_and_resume_possible(tmp_path: Path) -> None:
    brief = resolve_current_orchestration_watchpoint_brief(
        tmp_path,
        current_orchestration_state={
            "current_orchestration_state_id": "ocs-brief-satisfied",
            "current_supervisory_state": "waiting_for_external_fulfillment",
            "source_linkage": {"active_packet_ref": {"handoff_packet_id": "pkt-brief-satisfied"}},
        },
        current_orchestration_watchpoint={
            "orchestration_watchpoint_id": "owp-brief-satisfied",
            "watchpoint_class": "await_external_fulfillment_receipt",
            "wake_condition": "ingest_external_fulfillment_receipt_for_active_staged_external_packet",
        },
        watchpoint_satisfaction={
            "watchpoint_satisfaction_id": "wps-brief-satisfied",
            "satisfaction_status": "watchpoint_satisfied",
        },
        re_evaluation_trigger_recommendation={
            "re_evaluation_trigger_id": "ret-brief-satisfied",
            "recommendation": "rerun_delegated_judgment",
            "expected_actor": "orchestration_body",
        },
        current_orchestration_resumption_candidate={
            "orchestration_resumption_candidate_id": "orc-brief-satisfied",
            "bounded_resume_mode": "rerun_delegated_judgment",
            "resume_ready": True,
        },
        current_resumed_operation_readiness={"resumed_operation_readiness_verdict": "ready_to_proceed"},
    )
    assert brief["wait_kind"] == "continuity_uncertain"
    assert brief["watchpoint_posture"]["satisfaction_already_present"] is True
    assert brief["watchpoint_posture"]["resumed_work_currently_possible"] is True
    assert brief["watchpoint_posture"]["informational_only"] is True
    assert brief["watchpoint_posture"]["requires_conservative_hold"] is False
    assert brief["satisfying_condition_under_existing_logic"] == "current_watchpoint_satisfaction_surface_already_reports_satisfied"


def test_current_orchestration_watchpoint_brief_is_derived_only_and_non_executing(tmp_path: Path) -> None:
    internal_ready_evidence = {
        **_base_evidence(),
        "admission_denied_ratio": 0.75,
        "admission_sample_count": 8,
        "executor_failure_ratio": 0.4,
        "executor_sample_count": 8,
    }
    intent = synthesize_orchestration_intent(
        synthesize_delegated_judgment(internal_ready_evidence),
        created_at="2026-04-12T00:00:00Z",
    )
    append_orchestration_intent_ledger(tmp_path, intent)
    before = admit_orchestration_intent(tmp_path, intent)
    brief = resolve_current_orchestration_watchpoint_brief(
        tmp_path,
        current_orchestration_state={
            "current_orchestration_state_id": "ocs-brief-boundary",
            "current_supervisory_state": "waiting_for_operator_resolution",
        },
        current_orchestration_watchpoint={
            "orchestration_watchpoint_id": "owp-brief-boundary",
            "watchpoint_class": "await_operator_resolution",
        },
        watchpoint_satisfaction={
            "watchpoint_satisfaction_id": "wps-brief-boundary",
            "satisfaction_status": "watchpoint_pending",
        },
        re_evaluation_trigger_recommendation={
            "re_evaluation_trigger_id": "ret-brief-boundary",
            "recommendation": "no_re_evaluation_needed",
            "expected_actor": "none",
        },
        current_orchestration_resumption_candidate={
            "orchestration_resumption_candidate_id": "orc-brief-boundary",
            "bounded_resume_mode": "no_re_evaluation_needed",
            "resume_ready": False,
        },
        current_resumed_operation_readiness={"resumed_operation_readiness_verdict": "not_ready"},
    )
    after = admit_orchestration_intent(tmp_path, intent)
    assert brief["basis"]["derived_from_existing_surfaces_only"]
    assert brief["watchpoint_brief_only"] is True
    assert brief["non_authoritative"] is True
    assert brief["non_executing"] is True
    assert brief["does_not_execute_or_route_work"] is True
    assert brief["brief_boundaries"]["does_not_create_new_truth_source"] is True
    assert before["handoff_outcome"] == after["handoff_outcome"]


def test_current_orchestration_pressure_signal_is_derived_only_and_non_executing(tmp_path: Path) -> None:
    internal_ready_evidence = {
        **_base_evidence(),
        "admission_denied_ratio": 0.75,
        "admission_sample_count": 8,
        "executor_failure_ratio": 0.4,
        "executor_sample_count": 8,
    }
    intent = synthesize_orchestration_intent(
        synthesize_delegated_judgment(internal_ready_evidence),
        created_at="2026-04-12T00:00:00Z",
    )
    append_orchestration_intent_ledger(tmp_path, intent)
    before = admit_orchestration_intent(tmp_path, intent)
    pressure = resolve_current_orchestration_pressure_signal(
        tmp_path,
        current_orchestration_state={
            "current_orchestration_state_id": "ocs-pressure-derived",
            "current_supervisory_state": "waiting_for_operator_resolution",
        },
        current_orchestration_watchpoint={
            "orchestration_watchpoint_id": "owp-pressure-derived",
            "watchpoint_class": "await_operator_resolution",
        },
        watchpoint_satisfaction={
            "watchpoint_satisfaction_id": "wps-pressure-derived",
            "satisfaction_status": "watchpoint_pending",
        },
        re_evaluation_trigger_recommendation={
            "re_evaluation_trigger_id": "ret-pressure-derived",
            "recommendation": "hold_for_manual_review",
        },
        current_orchestration_resumption_candidate={
            "orchestration_resumption_candidate_id": "orc-pressure-derived",
            "resumption_candidate_class": "manual_review_hold",
            "resume_ready": False,
        },
        current_resumed_operation_readiness={"resumed_operation_readiness_verdict": "hold_for_operator_review"},
        current_orchestration_watchpoint_brief={"wait_kind": "awaiting_operator_resolution"},
        proposal_packet_continuity_review={"review_classification": "hold_heavy_continuity", "records_considered": 5},
        operator_resolution_influence={"operator_influence_state": "operator_defer_preserved_hold"},
        trust_confidence_posture={"trust_confidence_posture": "stressed_but_usable"},
    )
    after = admit_orchestration_intent(tmp_path, intent)
    assert pressure["pressure_classification"] == "hold_pressure"
    assert pressure["basis"]["derived_from_existing_surfaces_only"]
    assert pressure["boundaries"]["non_authoritative"] is True
    assert pressure["boundaries"]["non_executing"] is True
    assert pressure["pressure_signal_only"] is True
    assert pressure["does_not_execute_or_route_work"] is True
    assert before["handoff_outcome"] == after["handoff_outcome"]


@pytest.mark.parametrize(
    ("continuity_class", "watchpoint_class", "satisfaction_status", "trigger", "candidate_class", "wait_kind", "influence_state", "readiness_verdict", "counts", "expected"),
    [
        (
            "coherent_proposal_packet_continuity",
            "no_watchpoint_needed",
            "no_active_watchpoint",
            "no_re_evaluation_needed",
            "no_resume_candidate",
            "no_active_watchpoint",
            "no_operator_influence_yet",
            "not_ready",
            {"repacketization_count": 0, "broken_lineage_count": 0},
            "stable_or_low_pressure",
        ),
        (
            "hold_heavy_continuity",
            "await_operator_resolution",
            "watchpoint_pending",
            "hold_for_manual_review",
            "manual_review_hold",
            "awaiting_operator_resolution",
            "operator_defer_preserved_hold",
            "hold_for_operator_review",
            {"repacketization_count": 0, "broken_lineage_count": 0},
            "hold_pressure",
        ),
        (
            "redirect_heavy_continuity",
            "await_packetization_relief",
            "watchpoint_satisfied",
            "rerun_packet_synthesis",
            "resumption_candidate",
            "continuity_uncertain",
            "operator_redirect_applied",
            "proceed_with_caution",
            {"repacketization_count": 0, "broken_lineage_count": 0},
            "redirect_pressure",
        ),
        (
            "repacketization_churn",
            "await_packetization_relief",
            "watchpoint_satisfied",
            "rerun_packetization_gate",
            "resumption_candidate",
            "continuity_uncertain",
            "no_operator_influence_yet",
            "not_ready",
            {"repacketization_count": 6, "broken_lineage_count": 0},
            "repacketization_pressure",
        ),
        (
            "fragmented_continuity",
            "await_external_fulfillment_receipt",
            "watchpoint_fragmented",
            "hold_for_manual_review",
            "manual_review_hold",
            "continuity_uncertain",
            "no_operator_influence_yet",
            "hold_for_operator_review",
            {"repacketization_count": 0, "broken_lineage_count": 1},
            "fragmentation_pressure",
        ),
        (
            "hold_heavy_continuity",
            "await_operator_resolution",
            "watchpoint_stale",
            "hold_for_manual_review",
            "manual_review_hold",
            "continuity_uncertain",
            "operator_redirect_applied",
            "hold_for_operator_review",
            {"repacketization_count": 5, "broken_lineage_count": 1},
            "mixed_pressure",
        ),
    ],
)
def test_current_orchestration_pressure_signal_classifications(
    tmp_path: Path,
    continuity_class: str,
    watchpoint_class: str,
    satisfaction_status: str,
    trigger: str,
    candidate_class: str,
    wait_kind: str,
    influence_state: str,
    readiness_verdict: str,
    counts: dict[str, int],
    expected: str,
) -> None:
    pressure = resolve_current_orchestration_pressure_signal(
        tmp_path,
        current_orchestration_state={
            "current_orchestration_state_id": "ocs-pressure-cases",
            "current_supervisory_state": "waiting_for_operator_resolution"
            if watchpoint_class == "await_operator_resolution"
            else "waiting_for_external_fulfillment",
        },
        current_orchestration_watchpoint={
            "orchestration_watchpoint_id": "owp-pressure-cases",
            "watchpoint_class": watchpoint_class,
        },
        watchpoint_satisfaction={
            "watchpoint_satisfaction_id": "wps-pressure-cases",
            "satisfaction_status": satisfaction_status,
        },
        re_evaluation_trigger_recommendation={
            "re_evaluation_trigger_id": "ret-pressure-cases",
            "recommendation": trigger,
        },
        current_orchestration_resumption_candidate={
            "orchestration_resumption_candidate_id": "orc-pressure-cases",
            "resumption_candidate_class": candidate_class,
            "resume_ready": expected in {"stable_or_low_pressure", "redirect_pressure"},
        },
        current_resumed_operation_readiness={"resumed_operation_readiness_verdict": readiness_verdict},
        current_orchestration_watchpoint_brief={"wait_kind": wait_kind},
        proposal_packet_continuity_review={
            "review_classification": continuity_class,
            "records_considered": 6,
            "continuity_counts": counts,
        },
        operator_resolution_influence={"operator_influence_state": influence_state},
        trust_confidence_posture={"trust_confidence_posture": "stressed_but_usable"},
    )
    assert pressure["pressure_classification"] == expected
    assert pressure["boundaries"]["does_not_plan_or_schedule"] is True
    assert pressure["boundaries"]["does_not_imply_permission_to_execute"] is True


def test_current_orchestration_pressure_signal_insufficient_signal_case(tmp_path: Path) -> None:
    pressure = resolve_current_orchestration_pressure_signal(
        tmp_path,
        current_orchestration_state={"current_orchestration_state_id": "ocs-pressure-insufficient"},
        current_orchestration_watchpoint={"orchestration_watchpoint_id": "owp-pressure-insufficient"},
        watchpoint_satisfaction={"watchpoint_satisfaction_id": "wps-pressure-insufficient"},
        re_evaluation_trigger_recommendation={"re_evaluation_trigger_id": "ret-pressure-insufficient"},
        current_orchestration_resumption_candidate={"orchestration_resumption_candidate_id": "orc-pressure-insufficient"},
        proposal_packet_continuity_review={"review_classification": "insufficient_history", "records_considered": 0},
    )
    assert pressure["pressure_classification"] == "insufficient_signal"
    assert pressure["primary_pressure_driver"] == "insufficient_signal"
    assert pressure["signal_posture"] == "strongly_conservative"


@pytest.mark.parametrize(
    (
        "watchpoint_class",
        "satisfaction_status",
        "trigger",
        "candidate_class",
        "resume_ready",
        "readiness_verdict",
        "pressure_classification",
        "wait_kind",
        "influence_state",
        "expected",
    ),
    [
        (
            "await_external_fulfillment_receipt",
            "watchpoint_satisfied",
            "rerun_delegated_judgment",
            "resumption_candidate",
            True,
            "ready_to_proceed",
            "stable_or_low_pressure",
            "continuity_uncertain",
            "no_operator_influence_yet",
            "wake_ready",
        ),
        (
            "await_external_fulfillment_receipt",
            "watchpoint_satisfied",
            "rerun_delegated_judgment",
            "resumption_candidate",
            True,
            "proceed_with_caution",
            "redirect_pressure",
            "continuity_uncertain",
            "no_operator_influence_yet",
            "wake_ready_with_caution",
        ),
        (
            "await_external_fulfillment_receipt",
            "watchpoint_fragmented",
            "hold_for_manual_review",
            "manual_review_hold",
            False,
            "hold_for_operator_review",
            "fragmentation_pressure",
            "continuity_uncertain",
            "no_operator_influence_yet",
            "wake_blocked_by_fragmentation",
        ),
        (
            "await_operator_resolution",
            "watchpoint_pending",
            "hold_for_manual_review",
            "manual_review_hold",
            False,
            "hold_for_operator_review",
            "hold_pressure",
            "awaiting_operator_resolution",
            "operator_defer_preserved_hold",
            "wake_blocked_pending_operator",
        ),
        (
            "await_external_fulfillment_receipt",
            "watchpoint_pending",
            "rerun_delegated_judgment",
            "resumption_candidate",
            False,
            "not_ready",
            "stable_or_low_pressure",
            "awaiting_external_fulfillment",
            "no_operator_influence_yet",
            "not_wake_ready",
        ),
        (
            "no_watchpoint_needed",
            "no_active_watchpoint",
            "no_re_evaluation_needed",
            "no_resume_candidate",
            False,
            "not_ready",
            "stable_or_low_pressure",
            "no_active_watchpoint",
            "no_operator_influence_yet",
            "wake_not_applicable",
        ),
    ],
)
def test_current_orchestration_wake_readiness_detector_classifications(
    tmp_path: Path,
    watchpoint_class: str,
    satisfaction_status: str,
    trigger: str,
    candidate_class: str,
    resume_ready: bool,
    readiness_verdict: str,
    pressure_classification: str,
    wait_kind: str,
    influence_state: str,
    expected: str,
) -> None:
    detector = resolve_current_orchestration_wake_readiness_detector(
        tmp_path,
        current_orchestration_state={
            "current_orchestration_state_id": "ocs-wake-case",
            "current_supervisory_state": "waiting_for_operator_resolution"
            if watchpoint_class == "await_operator_resolution"
            else "waiting_for_external_fulfillment",
        },
        current_orchestration_watchpoint={
            "orchestration_watchpoint_id": "owp-wake-case",
            "watchpoint_class": watchpoint_class,
        },
        watchpoint_satisfaction={
            "watchpoint_satisfaction_id": "wps-wake-case",
            "satisfaction_status": satisfaction_status,
        },
        re_evaluation_trigger_recommendation={
            "re_evaluation_trigger_id": "ret-wake-case",
            "recommendation": trigger,
        },
        current_orchestration_resumption_candidate={
            "orchestration_resumption_candidate_id": "orc-wake-case",
            "resumption_candidate_class": candidate_class,
            "resume_ready": resume_ready,
        },
        current_resumed_operation_readiness={"resumed_operation_readiness_verdict": readiness_verdict},
        current_orchestration_watchpoint_brief={
            "wait_kind": wait_kind,
            "watchpoint_posture": {"requires_conservative_hold": expected.startswith("wake_blocked_")},
        },
        current_orchestration_pressure_signal={"pressure_classification": pressure_classification},
        operator_resolution_influence={"operator_influence_state": influence_state},
    )
    assert detector["wake_readiness_classification"] == expected
    assert detector["basis"]["derived_from_existing_surfaces_only"]
    assert detector["boundaries"]["does_not_imply_permission_to_execute"] is True


def test_current_orchestration_wake_readiness_detector_is_non_authoritative_and_non_executing(tmp_path: Path) -> None:
    intent = synthesize_orchestration_intent(synthesize_delegated_judgment(_base_evidence()), created_at="2026-04-12T00:00:00Z")
    append_orchestration_intent_ledger(tmp_path, intent)
    before = admit_orchestration_intent(tmp_path, intent)
    detector = resolve_current_orchestration_wake_readiness_detector(
        tmp_path,
        current_orchestration_state={"current_orchestration_state_id": "ocs-wake-boundary"},
        current_orchestration_watchpoint={"orchestration_watchpoint_id": "owp-wake-boundary"},
        watchpoint_satisfaction={"watchpoint_satisfaction_id": "wps-wake-boundary"},
        re_evaluation_trigger_recommendation={"re_evaluation_trigger_id": "ret-wake-boundary"},
        current_orchestration_resumption_candidate={"orchestration_resumption_candidate_id": "orc-wake-boundary"},
        current_resumed_operation_readiness={"resumed_operation_readiness_verdict": "not_ready"},
        current_orchestration_watchpoint_brief={"wait_kind": "continuity_uncertain"},
        current_orchestration_pressure_signal={"pressure_classification": "insufficient_signal"},
    )
    after = admit_orchestration_intent(tmp_path, intent)
    assert detector["wake_readiness_detector_only"] is True
    assert detector["non_authoritative"] is True
    assert detector["non_executing"] is True
    assert detector["does_not_execute_or_route_work"] is True
    assert detector["boundaries"]["does_not_create_new_truth_source"] is True
    assert before["handoff_outcome"] == after["handoff_outcome"]


@pytest.mark.parametrize(
    ("next_move_classification", "recommendation", "watchpoint_class", "satisfaction_status", "packetization_held", "active_packet", "stale_or_fragmented", "continuity_posture", "expected"),
    [
        ("continue_current_packet_next", "clear_wait_and_continue_current_packet", "await_external_fulfillment_receipt", "watchpoint_pending", False, True, False, "coherent_continuity", "continuing_active_packet"),
        ("rerun_packet_synthesis_next", "rerun_packet_synthesis", "await_new_proposal", "watchpoint_satisfied", False, True, False, "coherent_continuity", "refreshed_packet_required"),
        ("hold_for_operator_review_next", "hold_for_manual_review", "await_packetization_relief", "watchpoint_pending", True, True, False, "coherent_continuity", "packetization_gate_pending"),
        ("no_current_next_move", "no_re_evaluation_needed", "await_internal_execution_result", "watchpoint_pending", False, False, False, "coherent_continuity", "packet_not_currently_material"),
        ("continue_current_packet_next", "clear_wait_and_continue_current_packet", "await_external_fulfillment_receipt", "watchpoint_fragmented", False, True, True, "continuity_uncertain", "packet_continuity_uncertain"),
        ("no_current_next_move", "no_re_evaluation_needed", "no_watchpoint_needed", "no_active_watchpoint", False, False, False, "coherent_continuity", "no_current_packet_brief"),
    ],
)
def test_current_orchestration_handoff_packet_brief_classification_cases(
    tmp_path: Path,
    next_move_classification: str,
    recommendation: str,
    watchpoint_class: str,
    satisfaction_status: str,
    packetization_held: bool,
    active_packet: bool,
    stale_or_fragmented: bool,
    continuity_posture: str,
    expected: str,
) -> None:
    brief = resolve_current_orchestration_handoff_packet_brief(
        tmp_path,
        current_orchestration_state={"current_orchestration_state_id": "cos-handoff"},
        current_orchestration_watchpoint={"orchestration_watchpoint_id": "cow-handoff", "watchpoint_class": watchpoint_class},
        watchpoint_satisfaction={"watchpoint_satisfaction_id": "cws-handoff", "satisfaction_status": satisfaction_status},
        re_evaluation_trigger_recommendation={"re_evaluation_trigger_id": "ret-handoff", "recommendation": recommendation},
        current_re_evaluation_basis_brief={"basis_classification": "satisfaction_driven_re_evaluation"},
        current_orchestration_resumption_candidate={"orchestration_resumption_candidate_id": "crc-handoff", "resumption_candidate_class": "resumption_candidate", "continuity_posture": continuity_posture},
        current_resumed_operation_readiness={"resumed_operation_readiness_verdict": "ready_to_proceed"},
        current_orchestration_wake_readiness_detector={"wake_readiness_classification": "wake_ready"},
        current_orchestration_pressure_signal={"pressure_classification": "stable_or_low_pressure"},
        current_orchestration_next_move_brief={"next_move_classification": next_move_classification},
        active_packet_visibility={"active_packet_available": active_packet, "handoff_packet_id": "hp-active" if active_packet else None, "stale_or_fragmented": stale_or_fragmented, "packet_fulfillment_state": "staged_cleanly"},
        current_proposal={"proposal_id": "proposal-handoff-brief"},
        packetization_gate={"packetization_outcome": "packetization_hold_operator_review" if packetization_held else "packetization_allowed", "packetization_held": packetization_held},
        operator_resolution_influence={"operator_influence_state": "no_operator_influence_yet"},
        unified_result={"result_classification": "pending_or_unresolved"},
    )
    assert brief["handoff_packet_brief_classification"] == expected


def test_current_orchestration_handoff_packet_brief_is_derived_only_and_non_executing(tmp_path: Path) -> None:
    brief = resolve_current_orchestration_handoff_packet_brief(
        tmp_path,
        current_orchestration_state={"current_orchestration_state_id": "cos-derived"},
        current_orchestration_watchpoint={"orchestration_watchpoint_id": "cow-derived", "watchpoint_class": "await_operator_resolution"},
        watchpoint_satisfaction={"watchpoint_satisfaction_id": "cws-derived", "satisfaction_status": "watchpoint_pending"},
        re_evaluation_trigger_recommendation={"re_evaluation_trigger_id": "ret-derived", "recommendation": "hold_for_manual_review"},
        current_re_evaluation_basis_brief={"basis_classification": "operator_resolution_driven_re_evaluation"},
        current_orchestration_resumption_candidate={"orchestration_resumption_candidate_id": "crc-derived", "resumption_candidate_class": "manual_review_hold", "continuity_posture": "coherent_continuity"},
        current_resumed_operation_readiness={"resumed_operation_readiness_verdict": "hold_for_operator_review"},
        current_orchestration_wake_readiness_detector={"wake_readiness_classification": "wake_blocked_pending_operator"},
        current_orchestration_pressure_signal={"pressure_classification": "hold_pressure"},
        current_orchestration_next_move_brief={"next_move_classification": "hold_for_operator_review_next"},
        active_packet_visibility={"active_packet_available": True, "handoff_packet_id": "hp-derived", "stale_or_fragmented": False, "packet_fulfillment_state": "staged_cleanly"},
        current_proposal={"proposal_id": "proposal-derived"},
        packetization_gate={"packetization_outcome": "packetization_hold_operator_review", "packetization_held": True},
        operator_resolution_influence={"operator_influence_state": "operator_resolution_applied"},
        unified_result={"result_classification": "pending_or_unresolved"},
    )
    assert brief["basis"]["historical_honesty"]["derived_from_existing_surfaces_only"] is True
    assert brief["current_orchestration_handoff_packet_brief_only"] is True
    assert brief["boundaries"]["non_executing"] is True
    assert brief["does_not_execute_or_route_work"] is True
    assert brief["decision_power"] == "none"


@pytest.mark.parametrize(
    (
        "next_move_classification",
        "recommendation",
        "watchpoint_class",
        "satisfaction_status",
        "wake_classification",
        "pressure_classification",
        "handoff_packet_brief_classification",
        "wait_kind",
        "operator_influence_state",
        "operator_brief_state",
        "expected",
    ),
    [
        (
            "continue_current_packet_next",
            "clear_wait_and_continue_current_packet",
            "await_external_fulfillment_receipt",
            "watchpoint_pending",
            "wake_ready",
            "stable_or_low_pressure",
            "continuing_active_packet",
            "awaiting_external_fulfillment",
            "no_operator_influence_yet",
            "brief_not_emitted",
            "operator_attention_not_currently_needed",
        ),
        (
            "hold_for_operator_review_next",
            "hold_for_manual_review",
            "await_operator_resolution",
            "watchpoint_pending",
            "wake_blocked_pending_operator",
            "hold_pressure",
            "packetization_gate_pending",
            "awaiting_operator_resolution",
            "no_operator_influence_yet",
            "brief_emitted",
            "operator_should_review_hold",
        ),
        (
            "rerun_packet_synthesis_next",
            "rerun_packet_synthesis",
            "await_external_fulfillment_receipt",
            "watchpoint_fragmented",
            "wake_blocked_by_fragmentation",
            "fragmentation_pressure",
            "packet_continuity_uncertain",
            "continuity_uncertain",
            "no_operator_influence_yet",
            "brief_not_emitted",
            "operator_should_review_fragmentation",
        ),
        (
            "rerun_packet_synthesis_next",
            "rerun_packet_synthesis",
            "await_new_proposal",
            "watchpoint_satisfied",
            "wake_ready",
            "stable_or_low_pressure",
            "refreshed_packet_required",
            "awaiting_external_fulfillment",
            "no_operator_influence_yet",
            "brief_not_emitted",
            "operator_should_review_packet_refresh_context",
        ),
        (
            "rerun_delegated_judgment_next",
            "rerun_delegated_judgment",
            "await_new_proposal",
            "watchpoint_satisfied",
            "wake_ready_with_caution",
            "redirect_pressure",
            "packet_not_currently_material",
            "awaiting_external_fulfillment",
            "operator_redirect_applied",
            "operator_resolution_received",
            "operator_should_review_redirect_or_constraint_path",
        ),
        (
            "no_current_next_move",
            "no_re_evaluation_needed",
            "no_watchpoint_needed",
            "no_active_watchpoint",
            "wake_not_applicable",
            "stable_or_low_pressure",
            "no_current_packet_brief",
            "no_active_watchpoint",
            "no_operator_influence_yet",
            "brief_not_emitted",
            "operator_should_confirm_no_current_action",
        ),
    ],
)
def test_current_operator_facing_orchestration_brief_classification_cases(
    tmp_path: Path,
    next_move_classification: str,
    recommendation: str,
    watchpoint_class: str,
    satisfaction_status: str,
    wake_classification: str,
    pressure_classification: str,
    handoff_packet_brief_classification: str,
    wait_kind: str,
    operator_influence_state: str,
    operator_brief_state: str,
    expected: str,
) -> None:
    brief = resolve_current_operator_facing_orchestration_brief(
        tmp_path,
        current_orchestration_state={"current_orchestration_state_id": "cos-operator-facing"},
        current_orchestration_watchpoint={"orchestration_watchpoint_id": "cow-operator-facing", "watchpoint_class": watchpoint_class},
        current_orchestration_watchpoint_brief={"wait_kind": wait_kind},
        watchpoint_satisfaction={"watchpoint_satisfaction_id": "cws-operator-facing", "satisfaction_status": satisfaction_status},
        re_evaluation_trigger_recommendation={"re_evaluation_trigger_id": "ret-operator-facing", "recommendation": recommendation},
        current_re_evaluation_basis_brief={"basis_classification": "satisfaction_driven_re_evaluation"},
        current_orchestration_resumption_candidate={"orchestration_resumption_candidate_id": "crc-operator-facing"},
        current_resumed_operation_readiness={"resumed_operation_readiness_verdict": "hold_for_operator_review" if expected == "operator_should_review_hold" else "ready_to_proceed"},
        current_orchestration_wake_readiness_detector={"wake_readiness_classification": wake_classification},
        current_orchestration_pressure_signal={"pressure_classification": pressure_classification},
        current_orchestration_next_move_brief={"next_move_classification": next_move_classification},
        current_orchestration_handoff_packet_brief={"handoff_packet_brief_classification": handoff_packet_brief_classification},
        operator_action_brief_visibility={"lifecycle_state": operator_brief_state},
        operator_resolution_influence={"operator_influence_state": operator_influence_state},
        active_packet_visibility={"active_packet_available": True},
        current_proposal={"proposal_id": "proposal-operator-facing"},
        unified_result={"result_classification": "pending_or_unresolved", "resolution_path": "external_fulfillment"},
    )
    assert brief["operator_facing_classification"] == expected


def test_current_operator_facing_orchestration_brief_is_derived_only_non_authoritative_and_non_executing(tmp_path: Path) -> None:
    judgment = synthesize_delegated_judgment(_base_evidence())
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    append_orchestration_intent_ledger(tmp_path, intent)
    before = admit_orchestration_intent(tmp_path, intent)
    brief = resolve_current_operator_facing_orchestration_brief(
        tmp_path,
        current_orchestration_state={"current_orchestration_state_id": "cos-op-boundary"},
        current_orchestration_watchpoint={"orchestration_watchpoint_id": "cow-op-boundary", "watchpoint_class": "await_operator_resolution"},
        current_orchestration_watchpoint_brief={"wait_kind": "awaiting_operator_resolution"},
        watchpoint_satisfaction={"watchpoint_satisfaction_id": "cws-op-boundary", "satisfaction_status": "watchpoint_pending"},
        re_evaluation_trigger_recommendation={"re_evaluation_trigger_id": "ret-op-boundary", "recommendation": "hold_for_manual_review"},
        current_re_evaluation_basis_brief={"basis_classification": "operator_resolution_driven_re_evaluation"},
        current_orchestration_resumption_candidate={"orchestration_resumption_candidate_id": "crc-op-boundary"},
        current_resumed_operation_readiness={"resumed_operation_readiness_verdict": "hold_for_operator_review"},
        current_orchestration_wake_readiness_detector={"wake_readiness_classification": "wake_blocked_pending_operator"},
        current_orchestration_pressure_signal={"pressure_classification": "hold_pressure"},
        current_orchestration_next_move_brief={"next_move_classification": "hold_for_operator_review_next"},
        current_orchestration_handoff_packet_brief={"handoff_packet_brief_classification": "packetization_gate_pending"},
        operator_action_brief_visibility={"lifecycle_state": "brief_emitted"},
        operator_resolution_influence={"operator_influence_state": "no_operator_influence_yet"},
        active_packet_visibility={"active_packet_available": True},
        current_proposal={"proposal_id": "proposal-op-boundary"},
        unified_result={"result_classification": "pending_or_unresolved", "resolution_path": "external_fulfillment"},
    )
    after = admit_orchestration_intent(tmp_path, intent)
    assert brief["basis"]["historical_honesty"]["derived_from_existing_surfaces_only"] is True
    assert brief["current_operator_facing_orchestration_brief_only"] is True
    assert brief["boundaries"]["non_authoritative"] is True
    assert brief["boundaries"]["non_executing"] is True
    assert brief["does_not_execute_or_route_work"] is True
    assert brief["decision_power"] == "none"
    assert before["handoff_outcome"] == after["handoff_outcome"]


@pytest.mark.parametrize(
    ("watchpoint_class", "state_focus", "next_move_classification", "handoff_packet_brief_classification", "operator_facing_classification", "unified_resolution_path", "satisfaction_status", "wait_kind", "pressure_classification", "expected"),
    [
        (
            "await_new_proposal",
            "proposal",
            "rerun_delegated_judgment_next",
            "packet_not_currently_material",
            "operator_attention_not_currently_needed",
            "none",
            "watchpoint_pending",
            "awaiting_internal_result_closure",
            "stable_or_low_pressure",
            "proposal_centered_path",
        ),
        (
            "await_external_fulfillment_receipt",
            "packet",
            "continue_current_packet_next",
            "continuing_active_packet",
            "operator_attention_not_currently_needed",
            "external_fulfillment",
            "watchpoint_pending",
            "awaiting_external_fulfillment",
            "stable_or_low_pressure",
            "packet_centered_path",
        ),
        (
            "await_operator_resolution",
            "operator_brief",
            "hold_for_operator_review_next",
            "packetization_gate_pending",
            "operator_should_review_hold",
            "none",
            "watchpoint_pending",
            "awaiting_operator_resolution",
            "hold_pressure",
            "operator_resolution_path",
        ),
        (
            "await_internal_execution_result",
            "internal_execution",
            "continue_current_packet_next",
            "continuing_active_packet",
            "operator_attention_not_currently_needed",
            "internal_execution",
            "watchpoint_pending",
            "awaiting_internal_result_closure",
            "stable_or_low_pressure",
            "internal_result_path",
        ),
        (
            "await_external_fulfillment_receipt",
            "external_fulfillment",
            "continue_current_packet_next",
            "continuing_active_packet",
            "operator_attention_not_currently_needed",
            "external_fulfillment",
            "watchpoint_pending",
            "awaiting_external_fulfillment",
            "stable_or_low_pressure",
            "external_fulfillment_path",
        ),
        (
            "no_watchpoint_needed",
            "completed_or_idle",
            "no_current_next_move",
            "no_current_packet_brief",
            "operator_should_confirm_no_current_action",
            "external_fulfillment",
            "no_active_watchpoint",
            "no_active_watchpoint",
            "stable_or_low_pressure",
            "completed_or_no_active_path",
        ),
        (
            "await_external_fulfillment_receipt",
            "packet",
            "rerun_packet_synthesis_next",
            "packet_continuity_uncertain",
            "operator_should_review_fragmentation",
            "external_fulfillment",
            "watchpoint_fragmented",
            "continuity_uncertain",
            "fragmentation_pressure",
            "fragmented_path",
        ),
        (
            "no_watchpoint_needed",
            "completed_or_idle",
            "no_current_next_move",
            "no_current_packet_brief",
            "operator_attention_not_currently_needed",
            "none",
            "no_active_watchpoint",
            "no_active_watchpoint",
            "stable_or_low_pressure",
            "no_current_resolution_path",
        ),
    ],
)
def test_current_orchestration_resolution_path_brief_classification_cases(
    tmp_path: Path,
    watchpoint_class: str,
    state_focus: str,
    next_move_classification: str,
    handoff_packet_brief_classification: str,
    operator_facing_classification: str,
    unified_resolution_path: str,
    satisfaction_status: str,
    wait_kind: str,
    pressure_classification: str,
    expected: str,
) -> None:
    brief = resolve_current_orchestration_resolution_path_brief(
        tmp_path,
        current_orchestration_state={
            "current_orchestration_state_id": "cos-resolution-path",
            "current_supervisory_state": "completed_recently_no_current_item"
            if expected == "completed_or_no_active_path"
            else ("no_active_orchestration_item" if expected == "no_current_resolution_path" else "waiting_for_external_fulfillment"),
            "state_focus": state_focus,
            "current_resolution_path": unified_resolution_path,
        },
        current_orchestration_watchpoint={"orchestration_watchpoint_id": "cow-resolution-path", "watchpoint_class": watchpoint_class},
        current_orchestration_watchpoint_brief={"wait_kind": wait_kind},
        watchpoint_satisfaction={"watchpoint_satisfaction_id": "cws-resolution-path", "satisfaction_status": satisfaction_status},
        re_evaluation_trigger_recommendation={
            "re_evaluation_trigger_id": "ret-resolution-path",
            "recommendation": "no_re_evaluation_needed"
            if expected in {"completed_or_no_active_path", "no_current_resolution_path"}
            else "clear_wait_and_continue_current_packet",
        },
        current_re_evaluation_basis_brief={"basis_classification": "satisfaction_driven_re_evaluation"},
        current_orchestration_resumption_candidate={
            "orchestration_resumption_candidate_id": "crc-resolution-path",
            "resume_ready": expected not in {"completed_or_no_active_path", "no_current_resolution_path"},
        },
        current_resumed_operation_readiness={"resumed_operation_readiness_verdict": "ready_to_proceed"},
        current_orchestration_wake_readiness_detector={"wake_readiness_classification": "wake_ready"},
        current_orchestration_pressure_signal={"pressure_classification": pressure_classification},
        current_orchestration_next_move_brief={"next_move_classification": next_move_classification},
        current_orchestration_handoff_packet_brief={"handoff_packet_brief_classification": handoff_packet_brief_classification},
        current_operator_facing_orchestration_brief={
            "operator_facing_classification": operator_facing_classification,
            "loop_posture": "blocked" if operator_facing_classification == "operator_should_review_hold" else "informational",
        },
        active_packet_visibility={"active_packet_available": expected in {"packet_centered_path", "internal_result_path", "external_fulfillment_path"}},
        operator_action_brief_visibility={"lifecycle_state": "brief_emitted" if expected == "operator_resolution_path" else "brief_not_emitted"},
        operator_resolution_influence={"operator_influence_state": "no_operator_influence_yet"},
        internal_execution_result_visibility={
            "resolution_state": "execution_still_pending" if expected == "internal_result_path" else "not_supplied",
            "task_result_visible": expected == "internal_result_path",
        },
        external_fulfillment_receipt_visibility={"fulfillment_received": expected == "external_fulfillment_path"},
        unified_result={
            "resolution_path": unified_resolution_path,
            "result_classification": "completed_successfully" if expected == "completed_or_no_active_path" else "pending_or_unresolved",
        },
    )
    assert brief["resolution_path_classification"] == expected


def test_current_orchestration_resolution_path_brief_is_derived_only_non_authoritative_and_non_executing(tmp_path: Path) -> None:
    judgment = synthesize_delegated_judgment(_base_evidence())
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    append_orchestration_intent_ledger(tmp_path, intent)
    before = admit_orchestration_intent(tmp_path, intent)
    brief = resolve_current_orchestration_resolution_path_brief(
        tmp_path,
        current_orchestration_state={
            "current_orchestration_state_id": "cos-resolution-boundary",
            "current_supervisory_state": "waiting_for_operator_resolution",
            "state_focus": "operator_brief",
            "current_resolution_path": "operator_resolution",
        },
        current_orchestration_watchpoint={"orchestration_watchpoint_id": "cow-resolution-boundary", "watchpoint_class": "await_operator_resolution"},
        current_orchestration_watchpoint_brief={"wait_kind": "awaiting_operator_resolution"},
        watchpoint_satisfaction={"watchpoint_satisfaction_id": "cws-resolution-boundary", "satisfaction_status": "watchpoint_pending"},
        re_evaluation_trigger_recommendation={"re_evaluation_trigger_id": "ret-resolution-boundary", "recommendation": "hold_for_manual_review"},
        current_re_evaluation_basis_brief={"basis_classification": "operator_resolution_driven_re_evaluation"},
        current_orchestration_resumption_candidate={"orchestration_resumption_candidate_id": "crc-resolution-boundary", "resume_ready": False},
        current_resumed_operation_readiness={"resumed_operation_readiness_verdict": "hold_for_operator_review"},
        current_orchestration_wake_readiness_detector={"wake_readiness_classification": "wake_blocked_pending_operator"},
        current_orchestration_pressure_signal={"pressure_classification": "hold_pressure"},
        current_orchestration_next_move_brief={"next_move_classification": "hold_for_operator_review_next"},
        current_orchestration_handoff_packet_brief={"handoff_packet_brief_classification": "packetization_gate_pending"},
        current_operator_facing_orchestration_brief={"operator_facing_classification": "operator_should_review_hold", "loop_posture": "blocked"},
        active_packet_visibility={"active_packet_available": False},
        operator_action_brief_visibility={"lifecycle_state": "brief_emitted"},
        operator_resolution_influence={"operator_influence_state": "no_operator_influence_yet"},
        internal_execution_result_visibility={"resolution_state": "not_supplied"},
        external_fulfillment_receipt_visibility={"fulfillment_received": False},
        unified_result={"resolution_path": "none", "result_classification": "pending_or_unresolved"},
    )
    after = admit_orchestration_intent(tmp_path, intent)
    assert brief["basis"]["historical_honesty"]["derived_from_existing_surfaces_only"] is True
    assert brief["current_orchestration_resolution_path_brief_only"] is True
    assert brief["boundaries"]["non_authoritative"] is True
    assert brief["boundaries"]["non_executing"] is True
    assert brief["does_not_execute_or_route_work"] is True
    assert brief["decision_power"] == "none"
    assert before["handoff_outcome"] == after["handoff_outcome"]


@pytest.mark.parametrize(
    (
        "watchpoint_class",
        "wait_kind",
        "satisfaction_status",
        "state_class",
        "next_move_classification",
        "handoff_packet_classification",
        "resolution_path_classification",
        "expected",
    ),
    [
        (
            "await_operator_resolution",
            "awaiting_operator_resolution",
            "watchpoint_pending",
            "waiting_for_operator_resolution",
            "hold_for_operator_review_next",
            "packetization_gate_pending",
            "operator_resolution_path",
            "closure_pending_on_operator_resolution",
        ),
        (
            "await_internal_execution_result",
            "awaiting_internal_result_closure",
            "watchpoint_pending",
            "waiting_for_internal_result",
            "continue_current_packet_next",
            "continuing_active_packet",
            "internal_result_path",
            "closure_pending_on_internal_result",
        ),
        (
            "await_external_fulfillment_receipt",
            "awaiting_external_fulfillment",
            "watchpoint_pending",
            "waiting_for_external_fulfillment",
            "continue_current_packet_next",
            "continuing_active_packet",
            "external_fulfillment_path",
            "closure_pending_on_external_fulfillment",
        ),
        (
            "await_packetization_relief",
            "no_active_watchpoint",
            "watchpoint_pending",
            "held_due_to_insufficient_confidence",
            "rerun_packetization_gate_next",
            "packetization_gate_pending",
            "packet_centered_path",
            "closure_pending_on_packet_continuity",
        ),
        (
            "await_new_proposal",
            "no_active_watchpoint",
            "watchpoint_pending",
            "packet_ready_for_internal_trigger",
            "continue_current_packet_next",
            "continuing_active_packet",
            "packet_centered_path",
            "closure_materially_reachable",
        ),
        (
            "no_watchpoint_needed",
            "no_active_watchpoint",
            "watchpoint_satisfied",
            "completed_recently_no_current_item",
            "no_current_next_move",
            "packet_not_currently_material",
            "completed_or_no_active_path",
            "closure_already_satisfied",
        ),
        (
            "await_packetization_relief",
            "continuity_uncertain",
            "watchpoint_fragmented",
            "held_due_to_fragmentation",
            "rerun_packet_synthesis_next",
            "packet_continuity_uncertain",
            "fragmented_path",
            "closure_blocked_by_fragmentation",
        ),
        (
            "no_watchpoint_needed",
            "no_active_watchpoint",
            "no_active_watchpoint",
            "no_active_orchestration_item",
            "no_current_next_move",
            "no_current_packet_brief",
            "no_current_resolution_path",
            "no_current_closure_posture",
        ),
    ],
)
def test_current_orchestration_closure_brief_classification_cases(
    tmp_path: Path,
    watchpoint_class: str,
    wait_kind: str,
    satisfaction_status: str,
    state_class: str,
    next_move_classification: str,
    handoff_packet_classification: str,
    resolution_path_classification: str,
    expected: str,
) -> None:
    brief = resolve_current_orchestration_closure_brief(
        tmp_path,
        current_orchestration_state={
            "current_orchestration_state_id": "cos-closure",
            "current_supervisory_state": state_class,
        },
        current_orchestration_watchpoint={
            "orchestration_watchpoint_id": "cow-closure",
            "watchpoint_class": watchpoint_class,
        },
        current_orchestration_watchpoint_brief={"wait_kind": wait_kind},
        watchpoint_satisfaction={
            "watchpoint_satisfaction_id": "cws-closure",
            "satisfaction_status": satisfaction_status,
        },
        re_evaluation_trigger_recommendation={
            "re_evaluation_trigger_id": "ret-closure",
            "recommendation": (
                "no_re_evaluation_needed"
                if expected in {"closure_already_satisfied", "no_current_closure_posture"}
                else "clear_wait_and_continue_current_packet"
            ),
        },
        current_re_evaluation_basis_brief={
            "basis_classification": (
                "continuity_uncertainty_driven_re_evaluation"
                if expected == "closure_blocked_by_fragmentation"
                else "satisfaction_driven_re_evaluation"
            )
        },
        current_orchestration_resumption_candidate={
            "orchestration_resumption_candidate_id": "crc-closure",
            "resume_ready": expected in {"closure_materially_reachable", "closure_pending_on_internal_result"},
        },
        current_resumed_operation_readiness={
            "resumed_operation_readiness_verdict": (
                "ready_to_proceed"
                if expected in {"closure_materially_reachable", "closure_pending_on_internal_result"}
                else "hold_for_operator_review"
            )
        },
        current_orchestration_wake_readiness_detector={
            "wake_readiness_classification": (
                "wake_blocked_by_fragmentation"
                if expected == "closure_blocked_by_fragmentation"
                else ("wake_ready" if expected == "closure_materially_reachable" else "wake_not_applicable")
            )
        },
        current_orchestration_pressure_signal={
            "pressure_classification": (
                "fragmentation_pressure" if expected == "closure_blocked_by_fragmentation" else "stable_or_low_pressure"
            )
        },
        current_orchestration_next_move_brief={"next_move_classification": next_move_classification},
        current_orchestration_handoff_packet_brief={
            "handoff_packet_brief_classification": handoff_packet_classification
        },
        current_operator_facing_orchestration_brief={
            "operator_facing_classification": (
                "operator_should_review_hold"
                if expected == "closure_pending_on_operator_resolution"
                else "operator_attention_not_currently_needed"
            ),
            "loop_posture": (
                "blocked" if expected in {"closure_pending_on_operator_resolution", "closure_blocked_by_fragmentation"} else "informational"
            ),
        },
        current_orchestration_resolution_path_brief={"resolution_path_classification": resolution_path_classification},
        active_packet_visibility={"active_packet_available": expected in {"closure_materially_reachable"}},
        operator_action_brief_visibility={"lifecycle_state": "brief_emitted" if expected == "closure_pending_on_operator_resolution" else "brief_not_emitted"},
        operator_resolution_influence={"operator_influence_state": "no_operator_influence_yet"},
        internal_execution_result_visibility={
            "resolution_state": "execution_still_pending" if expected == "closure_pending_on_internal_result" else "not_supplied"
        },
        external_fulfillment_receipt_visibility={"fulfillment_received": False},
        unified_result={
            "result_classification": "completed_successfully" if expected == "closure_already_satisfied" else "pending_or_unresolved"
        },
    )
    assert brief["closure_classification"] == expected


def test_current_orchestration_closure_brief_is_derived_only_non_authoritative_and_non_executing(tmp_path: Path) -> None:
    judgment = synthesize_delegated_judgment(_base_evidence())
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    append_orchestration_intent_ledger(tmp_path, intent)
    before = admit_orchestration_intent(tmp_path, intent)
    brief = resolve_current_orchestration_closure_brief(
        tmp_path,
        current_orchestration_state={
            "current_orchestration_state_id": "cos-closure-boundary",
            "current_supervisory_state": "waiting_for_operator_resolution",
        },
        current_orchestration_watchpoint={"orchestration_watchpoint_id": "cow-closure-boundary", "watchpoint_class": "await_operator_resolution"},
        current_orchestration_watchpoint_brief={"wait_kind": "awaiting_operator_resolution"},
        watchpoint_satisfaction={"watchpoint_satisfaction_id": "cws-closure-boundary", "satisfaction_status": "watchpoint_pending"},
        re_evaluation_trigger_recommendation={"re_evaluation_trigger_id": "ret-closure-boundary", "recommendation": "hold_for_manual_review"},
        current_re_evaluation_basis_brief={"basis_classification": "operator_resolution_driven_re_evaluation"},
        current_orchestration_resumption_candidate={"orchestration_resumption_candidate_id": "crc-closure-boundary", "resume_ready": False},
        current_resumed_operation_readiness={"resumed_operation_readiness_verdict": "hold_for_operator_review"},
        current_orchestration_wake_readiness_detector={"wake_readiness_classification": "wake_blocked_pending_operator"},
        current_orchestration_pressure_signal={"pressure_classification": "hold_pressure"},
        current_orchestration_next_move_brief={"next_move_classification": "hold_for_operator_review_next"},
        current_orchestration_handoff_packet_brief={"handoff_packet_brief_classification": "packetization_gate_pending"},
        current_operator_facing_orchestration_brief={"operator_facing_classification": "operator_should_review_hold", "loop_posture": "blocked"},
        current_orchestration_resolution_path_brief={"resolution_path_classification": "operator_resolution_path"},
        active_packet_visibility={"active_packet_available": False},
        operator_action_brief_visibility={"lifecycle_state": "brief_emitted"},
        operator_resolution_influence={"operator_influence_state": "no_operator_influence_yet"},
        internal_execution_result_visibility={"resolution_state": "not_supplied"},
        external_fulfillment_receipt_visibility={"fulfillment_received": False},
        unified_result={"result_classification": "pending_or_unresolved"},
    )
    after = admit_orchestration_intent(tmp_path, intent)
    assert brief["basis"]["historical_honesty"]["derived_from_existing_surfaces_only"] is True
    assert brief["current_orchestration_closure_brief_only"] is True
    assert brief["boundaries"]["non_authoritative"] is True
    assert brief["boundaries"]["non_executing"] is True
    assert brief["does_not_execute_or_route_work"] is True
    assert brief["decision_power"] == "none"
    assert before["handoff_outcome"] == after["handoff_outcome"]


@pytest.mark.parametrize(
    (
        "pressure_classification",
        "continuity_classification",
        "wake_classification",
        "next_move_classification",
        "resolution_path_classification",
        "closure_classification",
        "recommendation",
        "readiness_verdict",
        "state_class",
        "watchpoint_class",
        "wait_kind",
        "satisfaction_status",
        "expected",
    ),
    [
        (
            "stable_or_low_pressure",
            "coherent_proposal_packet_continuity",
            "wake_ready",
            "continue_current_packet_next",
            "packet_centered_path",
            "closure_materially_reachable",
            "clear_wait_and_continue_current_packet",
            "ready_to_proceed",
            "packet_ready_for_internal_trigger",
            "await_internal_execution_result",
            "awaiting_internal_result_closure",
            "watchpoint_pending",
            "coherent_current_picture",
        ),
        (
            "hold_pressure",
            "hold_heavy_continuity",
            "wake_ready_with_caution",
            "hold_for_operator_review_next",
            "operator_resolution_path",
            "closure_pending_on_operator_resolution",
            "hold_for_manual_review",
            "proceed_with_caution",
            "waiting_for_operator_resolution",
            "await_operator_resolution",
            "awaiting_operator_resolution",
            "watchpoint_pending",
            "strained_but_coherent",
        ),
        (
            "fragmentation_pressure",
            "fragmented_continuity",
            "wake_blocked_by_fragmentation",
            "rerun_packet_synthesis_next",
            "fragmented_path",
            "closure_blocked_by_fragmentation",
            "rerun_packet_synthesis",
            "not_ready",
            "held_due_to_fragmentation",
            "await_packetization_relief",
            "continuity_uncertain",
            "watchpoint_fragmented",
            "fragmentation_dominant",
        ),
        (
            "stable_or_low_pressure",
            "coherent_proposal_packet_continuity",
            "wake_ready",
            "continue_current_packet_next",
            "completed_or_no_active_path",
            "closure_pending_on_operator_resolution",
            "hold_for_manual_review",
            "hold_for_operator_review",
            "waiting_for_operator_resolution",
            "await_operator_resolution",
            "awaiting_operator_resolution",
            "watchpoint_pending",
            "materially_contradictory",
        ),
        (
            "insufficient_signal",
            "insufficient_history",
            "not_wake_ready",
            "no_current_next_move",
            "no_current_resolution_path",
            "no_current_closure_posture",
            "no_re_evaluation_needed",
            "not_ready",
            "no_active_orchestration_item",
            "no_watchpoint_needed",
            "no_active_watchpoint",
            "no_active_watchpoint",
            "insufficient_current_signal",
        ),
    ],
)
def test_current_orchestration_coherence_brief_classification_cases(
    tmp_path: Path,
    pressure_classification: str,
    continuity_classification: str,
    wake_classification: str,
    next_move_classification: str,
    resolution_path_classification: str,
    closure_classification: str,
    recommendation: str,
    readiness_verdict: str,
    state_class: str,
    watchpoint_class: str,
    wait_kind: str,
    satisfaction_status: str,
    expected: str,
) -> None:
    brief = resolve_current_orchestration_coherence_brief(
        tmp_path,
        current_orchestration_state={
            "current_orchestration_state_id": "cos-coherence",
            "current_supervisory_state": state_class,
        },
        current_orchestration_watchpoint={
            "orchestration_watchpoint_id": "cow-coherence",
            "watchpoint_class": watchpoint_class,
        },
        current_orchestration_watchpoint_brief={"wait_kind": wait_kind},
        watchpoint_satisfaction={
            "watchpoint_satisfaction_id": "cws-coherence",
            "satisfaction_status": satisfaction_status,
        },
        re_evaluation_trigger_recommendation={
            "re_evaluation_trigger_id": "ret-coherence",
            "recommendation": recommendation,
        },
        current_re_evaluation_basis_brief={"basis_classification": "satisfaction_driven_re_evaluation"},
        current_orchestration_resumption_candidate={
            "orchestration_resumption_candidate_id": "crc-coherence",
            "resume_ready": expected in {"coherent_current_picture", "strained_but_coherent"},
        },
        current_resumed_operation_readiness={"resumed_operation_readiness_verdict": readiness_verdict},
        current_orchestration_wake_readiness_detector={"wake_readiness_classification": wake_classification},
        current_orchestration_pressure_signal={"pressure_classification": pressure_classification},
        proposal_packet_continuity_review={"review_classification": continuity_classification},
        current_orchestration_next_move_brief={"next_move_classification": next_move_classification},
        current_orchestration_handoff_packet_brief={
            "handoff_packet_brief_classification": (
                "packet_continuity_uncertain" if expected == "fragmentation_dominant" else "continuing_active_packet"
            )
        },
        current_operator_facing_orchestration_brief={
            "operator_facing_classification": (
                "operator_should_review_hold" if expected == "strained_but_coherent" else "operator_attention_not_currently_needed"
            ),
            "loop_posture": "cautionary" if expected == "strained_but_coherent" else "informational",
        },
        current_orchestration_resolution_path_brief={
            "resolution_path_classification": resolution_path_classification
        },
        current_orchestration_closure_brief={"closure_classification": closure_classification},
        active_packet_visibility={"active_packet_available": expected in {"coherent_current_picture", "strained_but_coherent"}},
        operator_resolution_influence={"operator_influence_state": "no_operator_influence_yet"},
        unified_result={"result_classification": "pending_or_unresolved"},
    )
    assert brief["coherence_classification"] == expected


def test_current_orchestration_coherence_brief_is_derived_only_non_authoritative_and_non_executing(tmp_path: Path) -> None:
    judgment = synthesize_delegated_judgment(_base_evidence())
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    append_orchestration_intent_ledger(tmp_path, intent)
    before = admit_orchestration_intent(tmp_path, intent)
    brief = resolve_current_orchestration_coherence_brief(
        tmp_path,
        current_orchestration_state={
            "current_orchestration_state_id": "cos-coherence-boundary",
            "current_supervisory_state": "waiting_for_operator_resolution",
        },
        current_orchestration_watchpoint={"orchestration_watchpoint_id": "cow-coherence-boundary", "watchpoint_class": "await_operator_resolution"},
        current_orchestration_watchpoint_brief={"wait_kind": "awaiting_operator_resolution"},
        watchpoint_satisfaction={"watchpoint_satisfaction_id": "cws-coherence-boundary", "satisfaction_status": "watchpoint_pending"},
        re_evaluation_trigger_recommendation={"re_evaluation_trigger_id": "ret-coherence-boundary", "recommendation": "hold_for_manual_review"},
        current_re_evaluation_basis_brief={"basis_classification": "operator_resolution_driven_re_evaluation"},
        current_orchestration_resumption_candidate={"orchestration_resumption_candidate_id": "crc-coherence-boundary", "resume_ready": False},
        current_resumed_operation_readiness={"resumed_operation_readiness_verdict": "hold_for_operator_review"},
        current_orchestration_wake_readiness_detector={"wake_readiness_classification": "wake_blocked_pending_operator"},
        current_orchestration_pressure_signal={"pressure_classification": "hold_pressure"},
        proposal_packet_continuity_review={"review_classification": "hold_heavy_continuity"},
        current_orchestration_next_move_brief={"next_move_classification": "hold_for_operator_review_next"},
        current_orchestration_handoff_packet_brief={"handoff_packet_brief_classification": "packetization_gate_pending"},
        current_operator_facing_orchestration_brief={"operator_facing_classification": "operator_should_review_hold", "loop_posture": "cautionary"},
        current_orchestration_resolution_path_brief={"resolution_path_classification": "operator_resolution_path"},
        current_orchestration_closure_brief={"closure_classification": "closure_pending_on_operator_resolution"},
        active_packet_visibility={"active_packet_available": False},
        operator_resolution_influence={"operator_influence_state": "no_operator_influence_yet"},
        unified_result={"result_classification": "pending_or_unresolved"},
    )
    after = admit_orchestration_intent(tmp_path, intent)
    assert brief["basis"]["historical_honesty"]["derived_from_existing_surfaces_only"] is True
    assert brief["current_orchestration_coherence_brief_only"] is True
    assert brief["boundaries"]["non_authoritative"] is True
    assert brief["boundaries"]["non_executing"] is True
    assert brief["does_not_execute_or_route_work"] is True
    assert brief["decision_power"] == "none"
    assert before["handoff_outcome"] == after["handoff_outcome"]


@pytest.mark.parametrize(
    (
        "coherence_classification",
        "pressure_classification",
        "continuity_classification",
        "next_move_classification",
        "path_classification",
        "closure_classification",
        "recommendation",
        "readiness_verdict",
        "wake_classification",
        "state_class",
        "watchpoint_class",
        "wait_kind",
        "satisfaction_status",
        "expected",
    ),
    [
        (
            "coherent_current_picture",
            "stable_or_low_pressure",
            "coherent_proposal_packet_continuity",
            "continue_current_packet_next",
            "packet_centered_path",
            "closure_materially_reachable",
            "clear_wait_and_continue_current_packet",
            "ready_to_proceed",
            "wake_ready",
            "waiting_for_internal_result",
            "await_internal_execution_result",
            "awaiting_internal_result_closure",
            "watchpoint_satisfied",
            "mature_current_picture",
        ),
        (
            "strained_but_coherent",
            "hold_pressure",
            "hold_heavy_continuity",
            "hold_for_operator_review_next",
            "operator_resolution_path",
            "closure_pending_on_operator_resolution",
            "hold_for_manual_review",
            "hold_for_operator_review",
            "wake_blocked_pending_operator",
            "waiting_for_operator_resolution",
            "await_operator_resolution",
            "awaiting_operator_resolution",
            "watchpoint_pending",
            "cautionary_current_picture",
        ),
        (
            "fragmentation_dominant",
            "fragmentation_pressure",
            "fragmented_continuity",
            "rerun_packet_synthesis_next",
            "fragmented_path",
            "closure_blocked_by_fragmentation",
            "rerun_packet_synthesis",
            "not_ready",
            "wake_blocked_by_fragmentation",
            "held_due_to_fragmentation",
            "await_packetization_relief",
            "continuity_uncertain",
            "watchpoint_fragmented",
            "fragmented_current_picture",
        ),
        (
            "materially_contradictory",
            "stable_or_low_pressure",
            "coherent_proposal_packet_continuity",
            "continue_current_packet_next",
            "completed_or_no_active_path",
            "closure_pending_on_operator_resolution",
            "hold_for_manual_review",
            "hold_for_operator_review",
            "wake_ready",
            "waiting_for_operator_resolution",
            "await_operator_resolution",
            "awaiting_operator_resolution",
            "watchpoint_pending",
            "contradictory_current_picture",
        ),
        (
            "insufficient_current_signal",
            "insufficient_signal",
            "coherent_proposal_packet_continuity",
            "no_current_next_move",
            "no_current_resolution_path",
            "no_current_closure_posture",
            "no_re_evaluation_needed",
            "not_ready",
            "not_wake_ready",
            "no_active_orchestration_item",
            "no_watchpoint_needed",
            "no_active_watchpoint",
            "no_active_watchpoint",
            "minimal_current_picture",
        ),
    ],
)
def test_current_orchestration_digest_classification_cases(
    tmp_path: Path,
    coherence_classification: str,
    pressure_classification: str,
    continuity_classification: str,
    next_move_classification: str,
    path_classification: str,
    closure_classification: str,
    recommendation: str,
    readiness_verdict: str,
    wake_classification: str,
    state_class: str,
    watchpoint_class: str,
    wait_kind: str,
    satisfaction_status: str,
    expected: str,
) -> None:
    digest = resolve_current_orchestration_digest(
        tmp_path,
        current_orchestration_state={
            "current_orchestration_state_id": "cos-digest",
            "current_supervisory_state": state_class,
        },
        current_orchestration_watchpoint={
            "orchestration_watchpoint_id": "cow-digest",
            "watchpoint_class": watchpoint_class,
        },
        current_orchestration_watchpoint_brief={"wait_kind": wait_kind},
        watchpoint_satisfaction={
            "watchpoint_satisfaction_id": "cws-digest",
            "satisfaction_status": satisfaction_status,
        },
        re_evaluation_trigger_recommendation={
            "re_evaluation_trigger_id": "ret-digest",
            "recommendation": recommendation,
        },
        current_re_evaluation_basis_brief={"basis_classification": "operator_resolution_driven_re_evaluation"},
        current_orchestration_resumption_candidate={
            "orchestration_resumption_candidate_id": "crc-digest",
            "bounded_resume_mode": "hold_for_manual_review",
        },
        current_resumed_operation_readiness={"resumed_operation_readiness_verdict": readiness_verdict},
        current_orchestration_wake_readiness_detector={"wake_readiness_classification": wake_classification},
        current_orchestration_pressure_signal={"pressure_classification": pressure_classification},
        proposal_packet_continuity_review={"review_classification": continuity_classification},
        current_orchestration_next_move_brief={"next_move_classification": next_move_classification},
        current_orchestration_handoff_packet_brief={"handoff_packet_brief_classification": "continuing_active_packet"},
        current_operator_facing_orchestration_brief={
            "operator_facing_classification": "operator_should_review_hold",
            "loop_posture": "cautionary" if expected == "cautionary_current_picture" else "informational",
        },
        current_orchestration_resolution_path_brief={"resolution_path_classification": path_classification},
        current_orchestration_closure_brief={"closure_classification": closure_classification},
        current_orchestration_coherence_brief={"coherence_classification": coherence_classification},
    )
    assert digest["digest_classification"] == expected


def test_current_orchestration_digest_is_derived_only_non_authoritative_and_non_executing(tmp_path: Path) -> None:
    judgment = synthesize_delegated_judgment(_base_evidence())
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    append_orchestration_intent_ledger(tmp_path, intent)
    before = admit_orchestration_intent(tmp_path, intent)
    digest = resolve_current_orchestration_digest(
        tmp_path,
        current_orchestration_state={"current_orchestration_state_id": "cos-boundary"},
        current_orchestration_watchpoint={"orchestration_watchpoint_id": "cow-boundary"},
        watchpoint_satisfaction={"watchpoint_satisfaction_id": "cws-boundary"},
        re_evaluation_trigger_recommendation={"re_evaluation_trigger_id": "ret-boundary"},
        current_orchestration_resumption_candidate={"orchestration_resumption_candidate_id": "crc-boundary"},
        current_orchestration_coherence_brief={"coherence_classification": "insufficient_current_signal"},
    )
    after = admit_orchestration_intent(tmp_path, intent)
    assert digest["basis"]["historical_honesty"]["derived_from_existing_surfaces_only"] is True
    assert digest["current_orchestration_digest_only"] is True
    assert digest["boundaries"]["non_authoritative"] is True
    assert digest["boundaries"]["non_executing"] is True
    assert digest["does_not_execute_or_route_work"] is True
    assert digest["decision_power"] == "none"
    assert before["handoff_outcome"] == after["handoff_outcome"]


@pytest.mark.parametrize(
    (
        "watchpoint_class",
        "satisfaction_status",
        "recommendation",
        "readiness_verdict",
        "wake_classification",
        "pressure_classification",
        "continuity_classification",
        "next_move_classification",
        "handoff_classification",
        "operator_classification",
        "path_classification",
        "closure_classification",
        "coherence_classification",
        "digest_classification",
        "state_class",
        "expected",
    ),
    [
        (
            "await_internal_execution_result",
            "watchpoint_satisfied",
            "clear_wait_and_continue_current_packet",
            "ready_to_proceed",
            "wake_ready",
            "stable_or_low_pressure",
            "coherent_proposal_packet_continuity",
            "continue_current_packet_next",
            "continuing_active_packet",
            "operator_attention_not_currently_needed",
            "internal_result_path",
            "closure_materially_reachable",
            "coherent_current_picture",
            "mature_current_picture",
            "waiting_for_internal_result",
            "poised_for_resumed_progress",
        ),
        (
            "await_packetization_relief",
            "watchpoint_pending",
            "rerun_packet_synthesis",
            "not_ready",
            "not_wake_ready",
            "repacketization_pressure",
            "repacketization_churn",
            "rerun_packet_synthesis_next",
            "refreshed_packet_required",
            "operator_attention_not_currently_needed",
            "packet_centered_path",
            "closure_pending_on_packet_continuity",
            "strained_but_coherent",
            "cautionary_current_picture",
            "held_due_to_insufficient_confidence",
            "poised_for_packet_refresh",
        ),
        (
            "await_operator_resolution",
            "watchpoint_pending",
            "hold_for_manual_review",
            "hold_for_operator_review",
            "wake_blocked_pending_operator",
            "hold_pressure",
            "hold_heavy_continuity",
            "hold_for_operator_review_next",
            "packetization_gate_pending",
            "operator_should_review_hold",
            "operator_resolution_path",
            "closure_pending_on_operator_resolution",
            "strained_but_coherent",
            "cautionary_current_picture",
            "waiting_for_operator_resolution",
            "poised_for_operator_resolution",
        ),
        (
            "await_external_fulfillment_receipt",
            "watchpoint_pending",
            "clear_wait_and_continue_current_packet",
            "proceed_with_caution",
            "wake_ready_with_caution",
            "stable_or_low_pressure",
            "coherent_proposal_packet_continuity",
            "continue_current_packet_next",
            "continuing_active_packet",
            "operator_attention_not_currently_needed",
            "external_fulfillment_path",
            "closure_pending_on_external_fulfillment",
            "coherent_current_picture",
            "mature_current_picture",
            "waiting_for_external_fulfillment",
            "poised_for_result_closure",
        ),
        (
            "await_packetization_relief",
            "watchpoint_pending",
            "hold_for_manual_review",
            "hold_for_operator_review",
            "wake_blocked_pending_operator",
            "hold_pressure",
            "hold_heavy_continuity",
            "hold_for_operator_review_next",
            "packetization_gate_pending",
            "operator_attention_not_currently_needed",
            "packet_centered_path",
            "closure_pending_on_packet_continuity",
            "strained_but_coherent",
            "cautionary_current_picture",
            "held_due_to_insufficient_confidence",
            "poised_for_conservative_hold",
        ),
        (
            "no_watchpoint_needed",
            "no_active_watchpoint",
            "no_re_evaluation_needed",
            "not_ready",
            "wake_not_applicable",
            "stable_or_low_pressure",
            "coherent_proposal_packet_continuity",
            "no_current_next_move",
            "no_current_packet_brief",
            "operator_should_confirm_no_current_action",
            "completed_or_no_active_path",
            "no_current_closure_posture",
            "insufficient_current_signal",
            "minimal_current_picture",
            "completed_recently_no_current_item",
            "poised_for_no_material_transition",
        ),
        (
            "await_packetization_relief",
            "watchpoint_fragmented",
            "rerun_packet_synthesis",
            "not_ready",
            "wake_blocked_by_fragmentation",
            "fragmentation_pressure",
            "fragmented_continuity",
            "rerun_packet_synthesis_next",
            "packet_continuity_uncertain",
            "operator_should_review_fragmentation",
            "fragmented_path",
            "closure_blocked_by_fragmentation",
            "fragmentation_dominant",
            "fragmented_current_picture",
            "held_due_to_fragmentation",
            "transition_uncertain",
        ),
        (
            "await_operator_resolution",
            "watchpoint_pending",
            "hold_for_manual_review",
            "hold_for_operator_review",
            "wake_ready",
            "stable_or_low_pressure",
            "coherent_proposal_packet_continuity",
            "continue_current_packet_next",
            "continuing_active_packet",
            "operator_attention_not_currently_needed",
            "completed_or_no_active_path",
            "closure_pending_on_operator_resolution",
            "materially_contradictory",
            "contradictory_current_picture",
            "waiting_for_operator_resolution",
            "transition_contradicted",
        ),
    ],
)
def test_current_orchestration_transition_brief_classification_cases(
    tmp_path: Path,
    watchpoint_class: str,
    satisfaction_status: str,
    recommendation: str,
    readiness_verdict: str,
    wake_classification: str,
    pressure_classification: str,
    continuity_classification: str,
    next_move_classification: str,
    handoff_classification: str,
    operator_classification: str,
    path_classification: str,
    closure_classification: str,
    coherence_classification: str,
    digest_classification: str,
    state_class: str,
    expected: str,
) -> None:
    brief = resolve_current_orchestration_transition_brief(
        tmp_path,
        current_orchestration_state={"current_orchestration_state_id": "cos-transition", "current_supervisory_state": state_class},
        current_orchestration_watchpoint={"orchestration_watchpoint_id": "cow-transition", "watchpoint_class": watchpoint_class},
        current_orchestration_watchpoint_brief={"wait_kind": "continuity_uncertain" if expected == "transition_uncertain" else "no_active_watchpoint"},
        watchpoint_satisfaction={"watchpoint_satisfaction_id": "cws-transition", "satisfaction_status": satisfaction_status},
        re_evaluation_trigger_recommendation={"re_evaluation_trigger_id": "ret-transition", "recommendation": recommendation},
        current_re_evaluation_basis_brief={"basis_classification": "satisfaction_driven_re_evaluation"},
        current_orchestration_resumption_candidate={"orchestration_resumption_candidate_id": "crc-transition"},
        current_resumed_operation_readiness={"resumed_operation_readiness_verdict": readiness_verdict},
        current_orchestration_wake_readiness_detector={"wake_readiness_classification": wake_classification},
        current_orchestration_pressure_signal={"pressure_classification": pressure_classification},
        proposal_packet_continuity_review={"review_classification": continuity_classification},
        current_orchestration_next_move_brief={"next_move_classification": next_move_classification},
        current_orchestration_handoff_packet_brief={"handoff_packet_brief_classification": handoff_classification},
        current_operator_facing_orchestration_brief={"operator_facing_classification": operator_classification},
        current_orchestration_resolution_path_brief={"resolution_path_classification": path_classification},
        current_orchestration_closure_brief={"closure_classification": closure_classification},
        current_orchestration_coherence_brief={"coherence_classification": coherence_classification},
        current_orchestration_digest={"digest_classification": digest_classification},
    )
    assert brief["transition_classification"] == expected


def test_current_orchestration_transition_brief_is_derived_only_non_authoritative_and_non_executing(tmp_path: Path) -> None:
    judgment = synthesize_delegated_judgment(_base_evidence())
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    append_orchestration_intent_ledger(tmp_path, intent)
    before = admit_orchestration_intent(tmp_path, intent)
    brief = resolve_current_orchestration_transition_brief(
        tmp_path,
        current_orchestration_state={"current_orchestration_state_id": "cos-transition-boundary"},
        current_orchestration_watchpoint={"orchestration_watchpoint_id": "cow-transition-boundary"},
        watchpoint_satisfaction={"watchpoint_satisfaction_id": "cws-transition-boundary"},
        re_evaluation_trigger_recommendation={"re_evaluation_trigger_id": "ret-transition-boundary"},
        current_orchestration_resumption_candidate={"orchestration_resumption_candidate_id": "crc-transition-boundary"},
        current_orchestration_coherence_brief={"coherence_classification": "insufficient_current_signal"},
    )
    after = admit_orchestration_intent(tmp_path, intent)
    assert brief["basis"]["historical_honesty"]["derived_from_existing_surfaces_only"] is True
    assert brief["current_orchestration_transition_brief_only"] is True
    assert brief["boundaries"]["non_authoritative"] is True
    assert brief["boundaries"]["non_executing"] is True
    assert brief["does_not_execute_or_route_work"] is True
    assert brief["decision_power"] == "none"
    assert before["handoff_outcome"] == after["handoff_outcome"]


@pytest.mark.parametrize(
    (
        "coherence_classification",
        "digest_classification",
        "transition_classification",
        "pressure_classification",
        "continuity_classification",
        "next_move_classification",
        "path_classification",
        "closure_classification",
        "recommendation",
        "readiness_verdict",
        "wake_classification",
        "wait_kind",
        "satisfaction_status",
        "expected",
    ),
    [
        (
            "coherent_current_picture",
            "mature_current_picture",
            "poised_for_resumed_progress",
            "stable_or_low_pressure",
            "coherent_proposal_packet_continuity",
            "continue_current_packet_next",
            "internal_result_path",
            "closure_materially_reachable",
            "clear_wait_and_continue_current_packet",
            "ready_to_proceed",
            "wake_ready",
            "awaiting_internal_result_closure",
            "watchpoint_satisfied",
            "export_packet_ready",
        ),
        (
            "strained_but_coherent",
            "cautionary_current_picture",
            "poised_for_conservative_hold",
            "hold_pressure",
            "hold_heavy_continuity",
            "hold_for_operator_review_next",
            "operator_resolution_path",
            "closure_pending_on_operator_resolution",
            "hold_for_manual_review",
            "hold_for_operator_review",
            "wake_blocked_pending_operator",
            "awaiting_operator_resolution",
            "watchpoint_pending",
            "export_packet_cautionary",
        ),
        (
            "fragmentation_dominant",
            "fragmented_current_picture",
            "transition_uncertain",
            "fragmentation_pressure",
            "fragmented_continuity",
            "rerun_packet_synthesis_next",
            "fragmented_path",
            "closure_blocked_by_fragmentation",
            "rerun_packet_synthesis",
            "not_ready",
            "wake_blocked_by_fragmentation",
            "continuity_uncertain",
            "watchpoint_fragmented",
            "export_packet_fragmented",
        ),
        (
            "materially_contradictory",
            "contradictory_current_picture",
            "transition_contradicted",
            "stable_or_low_pressure",
            "coherent_proposal_packet_continuity",
            "continue_current_packet_next",
            "completed_or_no_active_path",
            "closure_pending_on_operator_resolution",
            "hold_for_manual_review",
            "hold_for_operator_review",
            "wake_ready",
            "awaiting_operator_resolution",
            "watchpoint_pending",
            "export_packet_contradicted",
        ),
        (
            "insufficient_current_signal",
            "minimal_current_picture",
            "transition_uncertain",
            "insufficient_signal",
            "insufficient_history",
            "no_current_next_move",
            "no_current_resolution_path",
            "no_current_closure_posture",
            "no_re_evaluation_needed",
            "not_ready",
            "not_wake_ready",
            "no_active_watchpoint",
            "no_active_watchpoint",
            "export_packet_minimal",
        ),
    ],
)
def test_current_orchestration_export_packet_classification_cases(
    tmp_path: Path,
    coherence_classification: str,
    digest_classification: str,
    transition_classification: str,
    pressure_classification: str,
    continuity_classification: str,
    next_move_classification: str,
    path_classification: str,
    closure_classification: str,
    recommendation: str,
    readiness_verdict: str,
    wake_classification: str,
    wait_kind: str,
    satisfaction_status: str,
    expected: str,
) -> None:
    packet = resolve_current_orchestration_export_packet(
        tmp_path,
        current_orchestration_state={"current_orchestration_state_id": "cos-export", "current_supervisory_state": "waiting_for_internal_result"},
        current_orchestration_watchpoint={"orchestration_watchpoint_id": "cow-export", "watchpoint_class": "await_internal_execution_result"},
        current_orchestration_watchpoint_brief={"wait_kind": wait_kind},
        watchpoint_satisfaction={"watchpoint_satisfaction_id": "cws-export", "satisfaction_status": satisfaction_status},
        re_evaluation_trigger_recommendation={"re_evaluation_trigger_id": "ret-export", "recommendation": recommendation},
        current_re_evaluation_basis_brief={"basis_classification": "satisfaction_driven_re_evaluation"},
        current_orchestration_resumption_candidate={"orchestration_resumption_candidate_id": "crc-export", "bounded_resume_mode": "clear_wait_and_continue_current_packet"},
        current_resumed_operation_readiness={"resumed_operation_readiness_verdict": readiness_verdict},
        current_orchestration_wake_readiness_detector={"wake_readiness_classification": wake_classification},
        current_orchestration_pressure_signal={"pressure_classification": pressure_classification},
        proposal_packet_continuity_review={"review_classification": continuity_classification},
        current_orchestration_next_move_brief={"next_move_classification": next_move_classification},
        current_orchestration_handoff_packet_brief={"handoff_packet_brief_classification": "continuing_active_packet"},
        current_operator_facing_orchestration_brief={"operator_facing_classification": "operator_attention_not_currently_needed"},
        current_orchestration_resolution_path_brief={"resolution_path_classification": path_classification},
        current_orchestration_closure_brief={"closure_classification": closure_classification},
        current_orchestration_coherence_brief={"coherence_classification": coherence_classification},
        current_orchestration_digest={"digest_classification": digest_classification},
        current_orchestration_transition_brief={"transition_classification": transition_classification},
    )
    assert packet["export_packet_classification"] == expected


def test_current_orchestration_export_packet_is_derived_only_non_authoritative_and_non_executing(tmp_path: Path) -> None:
    judgment = synthesize_delegated_judgment(_base_evidence())
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    append_orchestration_intent_ledger(tmp_path, intent)
    before = admit_orchestration_intent(tmp_path, intent)
    packet = resolve_current_orchestration_export_packet(
        tmp_path,
        current_orchestration_state={"current_orchestration_state_id": "cos-export-boundary"},
        current_orchestration_watchpoint={"orchestration_watchpoint_id": "cow-export-boundary"},
        watchpoint_satisfaction={"watchpoint_satisfaction_id": "cws-export-boundary"},
        re_evaluation_trigger_recommendation={"re_evaluation_trigger_id": "ret-export-boundary"},
        current_orchestration_resumption_candidate={"orchestration_resumption_candidate_id": "crc-export-boundary"},
        current_orchestration_coherence_brief={"coherence_classification": "insufficient_current_signal"},
    )
    after = admit_orchestration_intent(tmp_path, intent)
    assert packet["basis"]["historical_honesty"]["derived_from_existing_surfaces_only"] is True
    assert packet["current_orchestration_export_packet_only"] is True
    assert packet["boundaries"]["non_authoritative"] is True
    assert packet["boundaries"]["non_executing"] is True
    assert packet["does_not_execute_or_route_work"] is True
    assert packet["decision_power"] == "none"
    assert "current_orchestration_digest_surface" in packet["basis"]["compressed_surface_linkage"]
    assert "current_orchestration_transition_brief_surface" in packet["basis"]["compressed_surface_linkage"]
    assert before["handoff_outcome"] == after["handoff_outcome"]


def test_current_orchestration_state_surface_is_present_in_consumer_and_non_authoritative(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("sentientos.scoped_lifecycle_diagnostic.SCOPED_ACTION_IDS", ("sentientos.manifest.generate",))

    def _fake_resolver(_repo_root: Path, *, action_id: str, correlation_id: str) -> dict[str, object]:
        return {
            "typed_action_identity": action_id,
            "correlation_id": correlation_id,
            "outcome_class": "success",
        }

    monkeypatch.setattr("sentientos.scoped_lifecycle_diagnostic.resolve_scoped_mutation_lifecycle", _fake_resolver)
    monkeypatch.setattr(
        "sentientos.scoped_lifecycle_diagnostic.synthesize_delegated_judgment",
        lambda _evidence: synthesize_delegated_judgment(_base_evidence()),
    )
    _write_json(tmp_path / "glow/contracts/contract_status.json", {"contracts": []})
    _write_jsonl(
        tmp_path / "pulse/forge_events.jsonl",
        [
            {
                "event": "constitutional_mutation_router_execution",
                "typed_action_id": "sentientos.manifest.generate",
                "correlation_id": "cid-current-state-consumer",
            }
        ],
    )

    before_intent = synthesize_orchestration_intent(synthesize_delegated_judgment(_base_evidence()), created_at="2026-04-12T00:00:00Z")
    append_orchestration_intent_ledger(tmp_path, before_intent)
    before = admit_orchestration_intent(tmp_path, before_intent)

    diagnostic = build_scoped_lifecycle_diagnostic(tmp_path)
    current_state = diagnostic["orchestration_handoff"]["current_orchestration_state"]
    current_watchpoint = diagnostic["orchestration_handoff"]["current_orchestration_watchpoint"]
    current_watchpoint_satisfaction = diagnostic["orchestration_handoff"]["current_orchestration_watchpoint_satisfaction"]
    re_evaluation_trigger = diagnostic["orchestration_handoff"]["re_evaluation_trigger_recommendation"]
    current_resumption_candidate = diagnostic["orchestration_handoff"]["current_orchestration_resumption_candidate"]
    resumed_readiness = diagnostic["orchestration_handoff"]["current_resumed_operation_readiness"]
    current_watchpoint_brief = diagnostic["orchestration_handoff"]["current_orchestration_watchpoint_brief"]
    current_pressure = diagnostic["orchestration_handoff"]["current_orchestration_pressure_signal"]
    current_wake_readiness = diagnostic["orchestration_handoff"]["current_orchestration_wake_readiness_detector"]
    current_re_evaluation_basis = diagnostic["orchestration_handoff"]["current_re_evaluation_basis_brief"]
    current_next_move = diagnostic["orchestration_handoff"]["current_orchestration_next_move_brief"]
    current_handoff_packet_brief = diagnostic["orchestration_handoff"]["current_orchestration_handoff_packet_brief"]
    current_operator_facing = diagnostic["orchestration_handoff"]["current_operator_facing_orchestration_brief"]
    current_resolution_path_brief = diagnostic["orchestration_handoff"]["current_orchestration_resolution_path_brief"]
    current_closure_brief = diagnostic["orchestration_handoff"]["current_orchestration_closure_brief"]
    current_coherence_brief = diagnostic["orchestration_handoff"]["current_orchestration_coherence_brief"]
    current_digest = diagnostic["orchestration_handoff"]["current_orchestration_digest"]
    current_transition_brief = diagnostic["orchestration_handoff"]["current_orchestration_transition_brief"]
    current_export_packet = diagnostic["orchestration_handoff"]["current_orchestration_export_packet"]
    current_watchpoint_summary = diagnostic["orchestration_handoff"]["current_orchestration_watchpoint_summary"]
    readiness = diagnostic["orchestration_handoff"]["delegated_operation_readiness"]

    after = admit_orchestration_intent(tmp_path, before_intent)
    assert current_state["schema_version"] == "current_orchestration_state.v1"
    assert current_state["state_focus"] in {
        "proposal",
        "packet",
        "operator_brief",
        "internal_execution",
        "external_fulfillment",
        "completed_or_idle",
    }
    assert current_state["awaiting_actor"] in {"none", "operator", "internal_substrate", "external_actor"}
    assert current_state["non_authoritative"] is True
    assert current_state["does_not_execute_or_route_work"] is True
    assert current_state["boundaries"]["non_authoritative"] is True
    assert current_state["boundaries"]["does_not_execute_or_route_work"] is True
    assert current_watchpoint["schema_version"] == "current_orchestration_watchpoint.v1"
    assert current_watchpoint["watchpoint_class"] in {
        "await_operator_resolution",
        "await_internal_execution_result",
        "await_external_fulfillment_receipt",
        "await_packetization_relief",
        "await_new_proposal",
        "no_watchpoint_needed",
    }
    assert current_watchpoint["wake_condition_summary"]["decision_power"] == "none"
    assert current_watchpoint["does_not_schedule_or_trigger_events"] is True
    assert current_watchpoint["boundaries"]["does_not_schedule_or_trigger_events"] is True
    assert current_watchpoint_satisfaction["schema_version"] == "current_orchestration_watchpoint_satisfaction.v1"
    assert current_watchpoint_satisfaction["satisfaction_status"] in {
        "watchpoint_pending",
        "watchpoint_satisfied",
        "watchpoint_stale",
        "watchpoint_fragmented",
        "no_active_watchpoint",
    }
    assert current_watchpoint_satisfaction["wake_readiness_summary"]["wake_readiness_only"] is True
    assert current_watchpoint_satisfaction["does_not_schedule_or_trigger_events"] is True
    assert current_watchpoint_satisfaction["boundaries"]["does_not_schedule_or_trigger_events"] is True
    assert re_evaluation_trigger["schema_version"] == "orchestration_re_evaluation_trigger.v1"
    assert re_evaluation_trigger["recommendation"] in {
        "rerun_delegated_judgment",
        "rerun_packetization_gate",
        "rerun_packet_synthesis",
        "clear_wait_and_continue_current_packet",
        "hold_for_manual_review",
        "no_re_evaluation_needed",
    }
    assert re_evaluation_trigger["expected_actor"] in {"orchestration_body", "operator", "none"}
    assert re_evaluation_trigger["re_entry_summary"]["non_sovereign_boundaries"]["decision_power"] == "none"
    assert re_evaluation_trigger["re_entry_recommendation_only"] is True
    assert re_evaluation_trigger["boundaries"]["does_not_schedule_or_trigger_events"] is True
    assert current_resumption_candidate["schema_version"] == "current_orchestration_resumption_candidate.v1"
    assert current_resumption_candidate["bounded_resume_mode"] in {
        "rerun_delegated_judgment",
        "rerun_packetization_gate",
        "rerun_packet_synthesis",
        "clear_wait_and_continue_current_packet",
        "hold_for_manual_review",
        "no_re_evaluation_needed",
    }
    assert current_resumption_candidate["continuity_posture"] in {
        "continue_current_active_packet",
        "refresh_packet_from_current_proposal_state",
        "recompute_from_proposal_level_state",
        "none",
    }
    assert current_resumption_candidate["resumption_summary"]["non_executing"] is True
    assert current_resumption_candidate["does_not_execute_or_route_work"] is True
    assert current_resumption_candidate["boundaries"]["does_not_schedule_or_trigger_events"] is True
    assert resumed_readiness["schema_version"] == "current_resumed_operation_readiness_verdict.v1"
    assert resumed_readiness["current_resumed_operation_readiness_id"].startswith("ord-")
    assert resumed_readiness["resumed_operation_readiness_verdict"] in {
        "ready_to_proceed",
        "proceed_with_caution",
        "hold_for_operator_review",
        "not_ready",
    }
    assert resumed_readiness["non_authoritative"] is True
    assert resumed_readiness["non_executing"] is True
    assert resumed_readiness["does_not_imply_permission_to_execute"] is True
    assert resumed_readiness["boundaries"]["does_not_schedule_or_trigger_events"] is True
    assert current_watchpoint_brief["schema_version"] == "current_orchestration_watchpoint_brief.v1"
    assert current_watchpoint_brief["wait_kind"] in {
        "awaiting_external_fulfillment",
        "awaiting_operator_resolution",
        "awaiting_internal_result_closure",
        "continuity_uncertain",
        "no_active_watchpoint",
    }
    assert current_watchpoint_brief["watchpoint_posture"]["watchpoint_class"] == current_watchpoint["watchpoint_class"]
    assert current_watchpoint_brief["watchpoint_posture"]["satisfaction_status"] == current_watchpoint_satisfaction["satisfaction_status"]
    assert current_watchpoint_brief["brief_boundaries"]["non_sovereign"] is True
    assert current_watchpoint_brief["does_not_execute_or_route_work"] is True
    assert current_pressure["schema_version"] == "current_orchestration_pressure_signal.v1"
    assert current_pressure["pressure_classification"] in {
        "stable_or_low_pressure",
        "hold_pressure",
        "redirect_pressure",
        "repacketization_pressure",
        "fragmentation_pressure",
        "mixed_pressure",
        "insufficient_signal",
    }
    assert current_pressure["primary_pressure_driver"] in {
        "none",
        "repeated_holds_or_manual_review",
        "repeated_redirects_or_reroutes",
        "repeated_packet_refresh_or_supersession",
        "fragmented_linkage_or_stale_context",
        "mixed_or_competing",
        "insufficient_signal",
    }
    assert current_pressure["boundaries"]["non_authoritative"] is True
    assert current_pressure["does_not_execute_or_route_work"] is True
    assert current_wake_readiness["schema_version"] == "current_orchestration_wake_readiness_detector.v1"
    assert current_wake_readiness["wake_readiness_classification"] in {
        "wake_ready",
        "wake_ready_with_caution",
        "not_wake_ready",
        "wake_blocked_by_fragmentation",
        "wake_blocked_pending_operator",
        "wake_not_applicable",
    }
    assert current_wake_readiness["boundaries"]["non_authoritative"] is True
    assert current_wake_readiness["does_not_execute_or_route_work"] is True
    assert current_re_evaluation_basis["schema_version"] == "current_re_evaluation_basis_brief.v1"
    assert current_next_move["schema_version"] == "current_orchestration_next_move_brief.v1"
    assert current_handoff_packet_brief["schema_version"] == "current_orchestration_handoff_packet_brief.v1"
    assert current_handoff_packet_brief["handoff_packet_brief_classification"] in {
        "continuing_active_packet",
        "refreshed_packet_required",
        "packetization_gate_pending",
        "packet_not_currently_material",
        "packet_continuity_uncertain",
        "no_current_packet_brief",
    }
    assert current_handoff_packet_brief["boundaries"]["non_authoritative"] is True
    assert current_handoff_packet_brief["does_not_execute_or_route_work"] is True
    assert current_operator_facing["schema_version"] == "current_operator_facing_orchestration_brief.v1"
    assert current_operator_facing["operator_facing_classification"] in {
        "operator_attention_not_currently_needed",
        "operator_should_review_hold",
        "operator_should_review_fragmentation",
        "operator_should_review_packet_refresh_context",
        "operator_should_review_redirect_or_constraint_path",
        "operator_should_confirm_no_current_action",
    }
    assert current_operator_facing["loop_posture"] in {"blocked", "cautionary", "informational"}
    assert current_operator_facing["boundaries"]["non_authoritative"] is True
    assert current_operator_facing["does_not_execute_or_route_work"] is True
    assert current_resolution_path_brief["schema_version"] == "current_orchestration_resolution_path_brief.v1"
    assert current_resolution_path_brief["resolution_path_classification"] in {
        "proposal_centered_path",
        "packet_centered_path",
        "operator_resolution_path",
        "internal_result_path",
        "external_fulfillment_path",
        "completed_or_no_active_path",
        "fragmented_path",
        "no_current_resolution_path",
    }
    assert current_resolution_path_brief["centered_on"] in {"proposal", "packet", "operator", "result_or_fulfillment", "none"}
    assert current_resolution_path_brief["path_posture"] in {"blocked", "cautionary", "informational"}
    assert current_resolution_path_brief["boundaries"]["non_authoritative"] is True
    assert current_resolution_path_brief["does_not_execute_or_route_work"] is True
    assert current_closure_brief["schema_version"] == "current_orchestration_closure_brief.v1"
    assert current_closure_brief["closure_classification"] in {
        "closure_pending_on_operator_resolution",
        "closure_pending_on_internal_result",
        "closure_pending_on_external_fulfillment",
        "closure_pending_on_packet_continuity",
        "closure_materially_reachable",
        "closure_blocked_by_fragmentation",
        "closure_already_satisfied",
        "no_current_closure_posture",
    }
    assert current_closure_brief["closure_primary_waiting_on"] in {
        "operator",
        "internal_result",
        "external_fulfillment",
        "packet_continuity",
        "already_satisfied",
        "none",
    }
    assert current_closure_brief["closure_posture"] in {"blocked", "cautionary", "informational"}
    assert current_closure_brief["boundaries"]["non_authoritative"] is True
    assert current_closure_brief["does_not_execute_or_route_work"] is True
    assert current_coherence_brief["schema_version"] == "current_orchestration_coherence_brief.v1"
    assert current_coherence_brief["coherence_classification"] in {
        "coherent_current_picture",
        "strained_but_coherent",
        "fragmentation_dominant",
        "materially_contradictory",
        "insufficient_current_signal",
    }
    assert current_coherence_brief["coherence_posture"] in {"informational_only", "conservative_caution"}
    assert current_coherence_brief["boundaries"]["non_authoritative"] is True
    assert current_coherence_brief["does_not_execute_or_route_work"] is True
    assert current_digest["schema_version"] == "current_orchestration_digest.v1"
    assert current_transition_brief["schema_version"] == "current_orchestration_transition_brief.v1"
    assert current_export_packet["schema_version"] == "current_orchestration_export_packet.v1"
    assert current_digest["digest_classification"] in {
        "mature_current_picture",
        "cautionary_current_picture",
        "fragmented_current_picture",
        "contradictory_current_picture",
        "minimal_current_picture",
    }
    assert current_digest["overall_picture_posture"] in {"aligned", "cautionary", "fragmented", "contradictory"}
    assert current_digest["resumed_bounded_motion"] in {"plausible", "blocked", "not_applicable"}
    assert current_digest["boundaries"]["non_authoritative"] is True
    assert current_digest["does_not_execute_or_route_work"] is True
    assert current_export_packet["export_packet_classification"] in {
        "export_packet_ready",
        "export_packet_cautionary",
        "export_packet_fragmented",
        "export_packet_contradicted",
        "export_packet_minimal",
    }
    assert current_export_packet["export_packet_maturity_posture"] in {
        "mature",
        "cautionary",
        "fragmented",
        "contradicted",
        "minimal",
    }
    assert current_export_packet["boundaries"]["non_authoritative"] is True
    assert current_export_packet["does_not_execute_or_route_work"] is True
    assert current_watchpoint_summary["watchpoint_class"] == current_watchpoint["watchpoint_class"]
    assert current_watchpoint_summary["current_watchpoint_class"] == current_watchpoint["watchpoint_class"]
    assert current_watchpoint_summary["watchpoint_satisfaction_status"] == current_watchpoint_satisfaction["satisfaction_status"]
    assert (
        current_watchpoint_summary["current_watchpoint_satisfaction_status"]
        == current_watchpoint_satisfaction["satisfaction_status"]
    )
    assert current_watchpoint_summary["re_evaluation_trigger_recommendation"] == re_evaluation_trigger["recommendation"]
    assert current_watchpoint_summary["current_re_evaluation_trigger_recommendation"] == re_evaluation_trigger["recommendation"]
    assert current_watchpoint_summary["re_evaluation_expected_actor"] == re_evaluation_trigger["expected_actor"]
    assert current_watchpoint_summary["current_resumption_candidate_mode"] == current_resumption_candidate["bounded_resume_mode"]
    assert current_watchpoint_summary["current_resumption_continuity_posture"] == current_resumption_candidate["continuity_posture"]
    assert (
        current_watchpoint_summary["current_resumption_candidate_continuity_posture"]
        == current_resumption_candidate["continuity_posture"]
    )
    assert (
        current_watchpoint_summary["current_resumed_operation_readiness_verdict"]
        == resumed_readiness["resumed_operation_readiness_verdict"]
    )
    assert current_watchpoint_summary["current_resumed_operation_readiness_id"] == resumed_readiness[
        "current_resumed_operation_readiness_id"
    ]
    assert current_watchpoint_summary["current_watchpoint_wait_kind"] == current_watchpoint_brief["wait_kind"]
    assert (
        current_watchpoint_summary["watchpoint_brief_requires_conservative_hold"]
        == current_watchpoint_brief["watchpoint_posture"]["requires_conservative_hold"]
    )
    assert (
        current_watchpoint_summary["watchpoint_brief_resumed_work_currently_possible"]
        == current_watchpoint_brief["watchpoint_posture"]["resumed_work_currently_possible"]
    )
    assert current_watchpoint_summary["current_pressure_classification"] == current_pressure["pressure_classification"]
    assert current_watchpoint_summary["current_pressure_primary_driver"] == current_pressure["primary_pressure_driver"]
    assert (
        current_watchpoint_summary["current_pressure_resumed_work_plausible"]
        == current_pressure["resumed_work_plausible_despite_pressure"]
    )
    assert (
        current_watchpoint_summary["current_wake_readiness_classification"]
        == current_wake_readiness["wake_readiness_classification"]
    )
    assert current_watchpoint_summary["current_wake_readiness_posture"] == current_wake_readiness["result_posture"]
    assert (
        current_watchpoint_summary["current_handoff_packet_brief_classification"]
        == current_handoff_packet_brief["handoff_packet_brief_classification"]
    )
    assert (
        current_watchpoint_summary["current_next_move_brief_classification"]
        == current_next_move["next_move_classification"]
    )
    assert (
        current_watchpoint_summary["current_handoff_packet_continues_active_packet"]
        == current_handoff_packet_brief["continues_active_packet"]
    )
    assert (
        current_watchpoint_summary["current_handoff_packet_refreshed_packet_implied"]
        == current_handoff_packet_brief["refreshed_packet_implied"]
    )
    assert (
        current_watchpoint_summary["current_operator_facing_classification"]
        == current_operator_facing["operator_facing_classification"]
    )
    assert current_watchpoint_summary["current_operator_facing_loop_posture"] == current_operator_facing["loop_posture"]
    assert (
        current_watchpoint_summary["current_operator_facing_informational_only"]
        == current_operator_facing["informational_only"]
    )
    assert (
        current_watchpoint_summary["current_resolution_path_classification"]
        == current_resolution_path_brief["resolution_path_classification"]
    )
    assert current_watchpoint_summary["current_resolution_path_centered_on"] == current_resolution_path_brief["centered_on"]
    assert current_watchpoint_summary["current_resolution_path_posture"] == current_resolution_path_brief["path_posture"]
    assert (
        current_watchpoint_summary["current_resolution_path_chain_active"]
        == current_resolution_path_brief["wake_resumption_next_move_chain_materially_active"]
    )
    assert (
        current_watchpoint_summary["current_closure_classification"]
        == current_closure_brief["closure_classification"]
    )
    assert (
        current_watchpoint_summary["current_closure_primary_waiting_on"]
        == current_closure_brief["closure_primary_waiting_on"]
    )
    assert current_watchpoint_summary["current_closure_posture"] == current_closure_brief["closure_posture"]
    assert (
        current_watchpoint_summary["current_closure_chain_reachable"]
        == current_closure_brief["wake_resumption_next_move_chain_points_to_reachable_closure"]
    )
    assert (
        current_watchpoint_summary["current_coherence_classification"]
        == current_coherence_brief["coherence_classification"]
    )
    assert current_watchpoint_summary["current_coherence_posture"] == current_coherence_brief["coherence_posture"]
    assert (
        current_watchpoint_summary["current_coherence_cross_surface_aligned"]
        == (current_coherence_brief["cross_surface_alignment"] or {}).get(
            "continuity_pressure_wake_next_move_path_closure_aligned"
        )
    )
    assert current_watchpoint_summary["current_digest_classification"] == current_digest["digest_classification"]
    assert current_watchpoint_summary["current_digest_overall_picture_posture"] == current_digest["overall_picture_posture"]
    assert current_watchpoint_summary["current_digest_resumed_bounded_motion"] == current_digest["resumed_bounded_motion"]
    assert current_watchpoint_summary["current_digest_posture"] == current_digest["digest_posture"]
    assert (
        current_watchpoint_summary["current_export_packet_classification"]
        == current_export_packet["export_packet_classification"]
    )
    assert (
        current_watchpoint_summary["current_export_packet_maturity_posture"]
        == current_export_packet["export_packet_maturity_posture"]
    )
    assert (
        current_watchpoint_summary["current_export_packet_suitable_for_bounded_downstream_inspection"]
        == current_export_packet["suitable_for_bounded_downstream_inspection"]
    )
    assert (
        current_watchpoint_summary["current_transition_classification"]
        == current_transition_brief["transition_classification"]
    )
    assert current_watchpoint_summary["current_transition_posture"] == current_transition_brief["transition_posture"]
    assert (
        current_watchpoint_summary["current_transition_resumed_bounded_motion"]
        == current_transition_brief["resumed_bounded_motion"]
    )
    assert current_watchpoint_summary["non_sovereign_boundaries"]["watchpoint_only"] is True
    assert current_watchpoint_summary["non_sovereign_boundaries"]["wake_readiness_only"] is True
    assert current_watchpoint_summary["non_sovereign_boundaries"]["re_entry_recommendation_only"] is True
    assert current_watchpoint_summary["non_sovereign_boundaries"]["resumption_candidate_only"] is True
    assert current_watchpoint_summary["non_sovereign_boundaries"]["resumption_readiness_only"] is True
    assert current_watchpoint_summary["non_sovereign_boundaries"]["current_resumed_operation_readiness_only"] is True
    assert current_watchpoint_summary["non_sovereign_boundaries"]["watchpoint_brief_only"] is True
    assert current_watchpoint_summary["non_sovereign_boundaries"]["pressure_signal_only"] is True
    assert current_watchpoint_summary["non_sovereign_boundaries"]["wake_readiness_detector_only"] is True
    assert current_watchpoint_summary["non_sovereign_boundaries"]["re_evaluation_basis_brief_only"] is True
    assert current_watchpoint_summary["non_sovereign_boundaries"]["current_orchestration_next_move_brief_only"] is True
    assert current_watchpoint_summary["non_sovereign_boundaries"]["current_orchestration_handoff_packet_brief_only"] is True
    assert current_watchpoint_summary["non_sovereign_boundaries"]["current_operator_facing_orchestration_brief_only"] is True
    assert current_watchpoint_summary["non_sovereign_boundaries"]["current_orchestration_resolution_path_brief_only"] is True
    assert current_watchpoint_summary["non_sovereign_boundaries"]["current_orchestration_closure_brief_only"] is True
    assert current_watchpoint_summary["non_sovereign_boundaries"]["current_orchestration_coherence_brief_only"] is True
    assert current_watchpoint_summary["non_sovereign_boundaries"]["current_orchestration_digest_only"] is True
    assert current_watchpoint_summary["non_sovereign_boundaries"]["current_orchestration_transition_brief_only"] is True
    assert current_watchpoint_summary["non_sovereign_boundaries"]["current_orchestration_export_packet_only"] is True
    assert readiness["summary"]["current_orchestration_state_basis"]["basis_only"] is True
    assert readiness["summary"]["current_orchestration_state_basis"]["does_not_change_verdict_logic"] is True
    assert readiness["summary"]["current_orchestration_state_basis"]["watchpoint_basis"]["basis_only"] is True
    assert readiness["summary"]["current_orchestration_state_basis"]["watchpoint_basis"]["watchpoint_satisfaction_status"] in {
        "watchpoint_pending",
        "watchpoint_satisfied",
        "watchpoint_stale",
        "watchpoint_fragmented",
        "no_active_watchpoint",
        "not_supplied",
    }
    assert (
        readiness["summary"]["current_orchestration_state_basis"]["re_evaluation_recommendation_basis"][
            "does_not_change_verdict_logic"
        ]
        is True
    )
    assert before["handoff_outcome"] == after["handoff_outcome"]


def test_orchestration_trust_confidence_posture_does_not_change_admission_behavior(tmp_path: Path) -> None:
    judgment = synthesize_delegated_judgment(_base_evidence())
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    append_orchestration_intent_ledger(tmp_path, intent)
    before = admit_orchestration_intent(tmp_path, intent)
    posture = derive_orchestration_trust_confidence_posture(
        {"review_classification": "mixed_proposal_stress", "records_considered": 5},
        {"review_classification": "mixed_venue_stress", "records_considered": 5},
        {"review_classification": "mixed_orchestration_stress", "records_considered": 5, "condition_flags": {}},
        {"review_classification": "mixed_result_stress", "records_considered": 5, "condition_flags": {}},
        {"operator_attention_recommendation": "inspect_execution_failures"},
    )
    after = admit_orchestration_intent(tmp_path, intent)
    assert posture["review_only"] is True
    assert posture["diagnostic_only"] is True
    assert posture["decision_power"] == "none"
    assert before["handoff_outcome"] == "blocked_by_operator_requirement"
    assert after["handoff_outcome"] == "blocked_by_operator_requirement"


def test_delegated_operation_readiness_does_not_change_admission_behavior(tmp_path: Path) -> None:
    judgment = synthesize_delegated_judgment(_base_evidence())
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    append_orchestration_intent_ledger(tmp_path, intent)
    before = admit_orchestration_intent(tmp_path, intent)
    readiness = derive_delegated_operation_readiness_verdict(
        {
            "trust_confidence_posture": "caution_required",
            "pressure_summary": {"primary_pressure": "result_quality_stress"},
            "window_considered": {"minimum_records_considered": 5},
        },
        {"review_classification": "coherent_proposal_packet_continuity", "records_considered": 5},
        {"review_classification": "mixed_result_stress", "records_considered": 5},
        {"packetization_outcome": "packetization_allowed_with_caution", "packetization_allowed": True, "packetization_held": False},
        {"operator_attention_recommendation": "observe"},
        outcome_review={"review_classification": "mixed_orchestration_stress"},
        venue_mix_review={"review_classification": "balanced_recent_venue_mix"},
        next_move_proposal_review={"review_classification": "coherent_recent_proposals"},
    )
    after = admit_orchestration_intent(tmp_path, intent)
    assert readiness["summary"]["boundaries"]["non_authoritative"] is True
    assert readiness["summary"]["boundaries"]["decision_power"] == "none"
    assert before["handoff_outcome"] == "blocked_by_operator_requirement"
    assert after["handoff_outcome"] == "blocked_by_operator_requirement"


def test_external_feedback_gap_map_reports_layer_influence_coherently() -> None:
    outcome_review = {
        "summary": {"external_fulfillment_influence": {"influenced_outcome_review": True, "influence_mode": "healthy_support"}}
    }
    venue_mix_review = {
        "summary": {"external_fulfillment_influence": {"influenced_venue_mix_review": True, "quality_signal": "healthy_or_mixed"}}
    }
    next_venue = {
        "basis": {
            "orchestration_venue_mix_review": {
                "external_fulfillment_contribution": {
                    "signal_present": True,
                    "external_feedback_stressed": False,
                    "external_feedback_affirming": True,
                }
            }
        }
    }

    gap_map = derive_external_feedback_gap_map(outcome_review, venue_mix_review, next_venue)
    assert gap_map["outcome_review"]["remaining_gap"] == "none"
    assert gap_map["venue_mix_review"]["remaining_gap"] == "none"
    assert gap_map["next_venue_recommendation"]["remaining_gap"] == "none"
    assert gap_map["diagnostic_only"] is True


def test_operator_feedback_gap_map_reports_resolution_visibility_by_layer() -> None:
    operator_influence = derive_operator_resolution_influence(
        {
            "resolution_kind": "supplied_missing_context",
            "updated_context_refs": ["docs/context.md#operator"],
            "operator_resolution_receipt_id": "orr-gap",
        }
    )
    proposal = derive_operator_adjusted_next_move_proposal_visibility(
        {"proposed_next_action": {"proposed_venue": "codex_implementation"}},
        operator_influence,
    )
    next_venue = derive_operator_adjusted_next_venue_recommendation(
        {
            "next_venue_recommendation": "prefer_codex_implementation",
            "relation_to_delegated_judgment": "affirming",
        },
        operator_influence,
    )
    gate = derive_packetization_gate(
        {
            "proposed_next_action": {"proposed_venue": "codex_implementation", "proposed_posture": "expand"},
            "executability_classification": "stageable_external_work_order",
            "relation_posture": "affirming",
            "operator_escalation_requirement_state": {"requires_operator_or_escalation": False},
        },
        {"review_classification": "coherent_recent_proposals"},
        {"trust_confidence_posture": "caution_required", "pressure_summary": {"primary_pressure": "none"}},
        {"operator_attention_recommendation": "observe"},
        operator_influence,
    )
    lifecycle = {"operator_resolution_received": True, "resolution_kind": "supplied_missing_context"}

    gap_map = derive_operator_resolution_feedback_gap_map(proposal, gate, next_venue, lifecycle, operator_influence)
    assert gap_map["next_move_proposal_visibility"]["remaining_gap"] == "none"
    assert gap_map["packetization_gating"]["remaining_gap"] == "none"
    assert gap_map["next_venue_recommendation"]["remaining_gap"] == "none"
    assert gap_map["operator_brief_lifecycle_visibility"]["remaining_gap"] == "none"
    assert gap_map["held_loop_static_after_operator_response"] is False


@pytest.mark.parametrize(
    ("resolution_kind", "expect_refresh"),
    [
        ("approved_continue", True),
        ("approved_with_constraints", True),
        ("supplied_missing_context", True),
        ("redirected_venue", True),
        ("declined", False),
        ("cancelled", False),
        ("deferred", False),
    ],
)
def test_operator_resolution_refresh_rules_are_bounded(
    tmp_path: Path,
    resolution_kind: str,
    expect_refresh: bool,
) -> None:
    delegated = synthesize_delegated_judgment(_base_evidence())
    next_venue = {
        "next_venue_recommendation": "prefer_codex_implementation",
        "relation_to_delegated_judgment": "affirming",
        "basis": {"rationale": "bounded test"},
    }
    proposal = synthesize_next_move_proposal(
        delegated,
        next_venue,
        {"review_classification": "clean_recent_orchestration", "records_considered": 6},
        {"review_classification": "balanced_recent_venue_mix", "records_considered": 6},
        {"operator_attention_recommendation": "observe"},
        created_at="2026-04-12T00:00:00Z",
    )
    packet = synthesize_handoff_packet(
        proposal,
        delegated,
        {"review_classification": "coherent_recent_proposals"},
        {"trust_confidence_posture": "trusted_for_bounded_use", "pressure_summary": {"primary_pressure": "none"}},
        {"operator_attention_recommendation": "observe"},
        created_at="2026-04-12T00:00:00Z",
    )
    append_handoff_packet_ledger(tmp_path, packet)
    receipt = {
        "operator_resolution_receipt_id": f"orr-{resolution_kind}",
        "resolution_kind": resolution_kind,
        "redirected_venue": "deep_research_audit" if resolution_kind == "redirected_venue" else None,
    }
    adjusted_proposal = derive_operator_adjusted_next_move_proposal_visibility(
        proposal,
        derive_operator_resolution_influence(receipt),
    )
    refreshed = synthesize_operator_refreshed_handoff_packet(
        adjusted_proposal,
        delegated,
        {"review_classification": "coherent_recent_proposals"},
        {"trust_confidence_posture": "trusted_for_bounded_use", "pressure_summary": {"primary_pressure": "none"}},
        {"operator_attention_recommendation": "observe"},
        receipt,
        packet,
    )
    if expect_refresh:
        assert refreshed is not None
        assert refreshed["packet_lineage"]["supersedes_handoff_packet_id"] == packet["handoff_packet_id"]
        assert refreshed["packet_lineage"]["source_operator_resolution_receipt_id"] == receipt["operator_resolution_receipt_id"]
        assert refreshed["historical_packet_state_preserved"] is True
        if resolution_kind == "redirected_venue":
            assert refreshed["target_venue"] == "deep_research_audit"
    else:
        assert refreshed is None


def test_repacketized_history_and_active_packet_visibility_are_append_only(tmp_path: Path) -> None:
    delegated = synthesize_delegated_judgment(_base_evidence())
    next_venue = {
        "next_venue_recommendation": "prefer_codex_implementation",
        "relation_to_delegated_judgment": "affirming",
        "basis": {"rationale": "bounded test"},
    }
    proposal = synthesize_next_move_proposal(
        delegated,
        next_venue,
        {"review_classification": "clean_recent_orchestration", "records_considered": 6},
        {"review_classification": "balanced_recent_venue_mix", "records_considered": 6},
        {"operator_attention_recommendation": "observe"},
        created_at="2026-04-12T00:00:00Z",
    )
    original_packet = synthesize_handoff_packet(
        proposal,
        delegated,
        {"review_classification": "coherent_recent_proposals"},
        {"trust_confidence_posture": "trusted_for_bounded_use", "pressure_summary": {"primary_pressure": "none"}},
        {"operator_attention_recommendation": "observe"},
        created_at="2026-04-12T00:00:00Z",
    )
    append_handoff_packet_ledger(tmp_path, original_packet)
    receipt = {
        "operator_resolution_receipt_id": "orr-refresh",
        "resolution_kind": "supplied_missing_context",
        "updated_context_refs": ["docs/context.md#1"],
    }
    refreshed_packet = synthesize_operator_refreshed_handoff_packet(
        derive_operator_adjusted_next_move_proposal_visibility(
            proposal,
            derive_operator_resolution_influence(receipt),
        ),
        delegated,
        {"review_classification": "coherent_recent_proposals"},
        {"trust_confidence_posture": "trusted_for_bounded_use", "pressure_summary": {"primary_pressure": "none"}},
        {"operator_attention_recommendation": "observe"},
        receipt,
        original_packet,
    )
    assert refreshed_packet is not None
    append_handoff_packet_ledger(tmp_path, refreshed_packet)

    history = resolve_handoff_packet_history_for_proposal(tmp_path, str(proposal["proposal_id"]))
    active = resolve_active_handoff_packet_candidate(
        tmp_path,
        str(proposal["proposal_id"]),
        operator_influence=derive_operator_resolution_influence(receipt),
    )

    assert history["history_count"] == 2
    assert history["timeline"][0]["handoff_packet_id"] == original_packet["handoff_packet_id"]
    assert history["timeline"][0]["superseded_by_handoff_packet_id"] == refreshed_packet["handoff_packet_id"]
    assert active["active_handoff_packet_id"] == refreshed_packet["handoff_packet_id"]
    assert active["is_refreshed_packet"] is True
    assert active["historical_packet_state_preserved"] is True
    assert active["does_not_imply_execution"] is True


def test_repacketization_gap_map_reports_manual_reconstruction_relief() -> None:
    operator_influence = derive_operator_resolution_influence(
        {
            "resolution_kind": "approved_continue",
            "operator_resolution_receipt_id": "orr-gap-refresh",
        }
    )
    gap_map = derive_repacketization_gap_map(
        {"operator_resolution_received": True, "resolution_kind": "approved_continue"},
        operator_influence,
        {"history_count": 2},
        {"is_refreshed_packet": True},
    )
    assert gap_map["operator_resolution_can_repacketize"] is True
    assert gap_map["history"]["manual_reconstruction_required"] is False
    assert gap_map["lineage_semantics"]["superseded_by_handoff_packet_id_resolved"] is True


def test_operator_repacketization_e2e_in_scoped_diagnostic(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("sentientos.scoped_lifecycle_diagnostic.SCOPED_ACTION_IDS", ("sentientos.manifest.generate",))
    monkeypatch.setattr(
        "sentientos.scoped_lifecycle_diagnostic.resolve_scoped_mutation_lifecycle",
        lambda _repo_root, *, action_id, correlation_id: {
            "typed_action_identity": action_id,
            "correlation_id": correlation_id,
            "outcome_class": "success",
        },
    )
    monkeypatch.setattr(
        "sentientos.scoped_lifecycle_diagnostic.synthesize_delegated_judgment",
        lambda _evidence: synthesize_delegated_judgment(
            {
                **_base_evidence(),
                "governance_ambiguity_signal": True,
                "admission_denied_ratio": 0.9,
                "executor_failure_ratio": 0.5,
            }
        ),
    )
    original_append = append_operator_action_brief_ledger

    def _append_and_ingest(repo_root: Path, brief: dict[str, object]) -> Path:
        ledger_path = original_append(repo_root, brief)
        ingest_operator_resolution_receipt(
            repo_root,
            operator_action_brief_id=str(brief["operator_action_brief_id"]),
            resolution_kind="approved_continue",
            operator_note="operator approved continue",
            created_at="2026-04-12T00:01:00Z",
        )
        return ledger_path

    monkeypatch.setattr("sentientos.scoped_lifecycle_diagnostic.append_operator_action_brief_ledger", _append_and_ingest)
    _write_json(tmp_path / "glow/contracts/contract_status.json", {"contracts": []})
    _write_jsonl(
        tmp_path / "pulse/forge_events.jsonl",
        [
            {
                "event": "constitutional_mutation_router_execution",
                "typed_action_id": "sentientos.manifest.generate",
                "correlation_id": "cid-operator-repacketization-e2e",
            }
        ],
    )

    diagnostic = build_scoped_lifecycle_diagnostic(tmp_path)
    handoff_packet = diagnostic["orchestration_handoff"]["handoff_packet"]
    active = handoff_packet["active_packet_candidate"]
    history = handoff_packet["lineage_history"]
    gap = diagnostic["orchestration_handoff"]["repacketization_gap_map"]
    continuity = diagnostic["orchestration_handoff"]["proposal_packet_continuity_review"]

    assert handoff_packet["repacketized_from_operator_feedback"] is True
    assert handoff_packet["historical_packet_state_preserved"] is True
    assert handoff_packet["initial_handoff_packet"]["handoff_packet_id"] != handoff_packet["handoff_packet_id"]
    assert history["history_count"] >= 2
    assert active["active_handoff_packet_id"] == handoff_packet["handoff_packet_id"]
    assert diagnostic["orchestration_handoff"]["operator_action_brief"]["operator_resolution_received"] is True
    assert gap["history"]["manual_reconstruction_required"] is False
    assert handoff_packet["does_not_execute_or_route_work"] is True
    assert gap["diagnostic_only"] is True
    assert continuity["review_classification"] in {
        "coherent_proposal_packet_continuity",
        "hold_heavy_continuity",
        "redirect_heavy_continuity",
        "repacketization_churn",
        "fragmented_continuity",
        "insufficient_history",
    }
    assert continuity["summary"]["boundaries"]["decision_power"] == "none"
    assert continuity["summary"]["boundaries"]["non_authoritative"] is True
    assert "continuity_signals" in continuity["summary"]
    assert continuity["does_not_execute_or_route_work"] is True


def test_contract_internal_lifecycle_identity_and_linkage_stays_continuous(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(task_executor, "LOG_PATH", str(tmp_path / "logs" / "task_executor.jsonl"))

    internal_ready_evidence = {
        **_base_evidence(),
        "admission_denied_ratio": 0.75,
        "admission_sample_count": 8,
        "executor_failure_ratio": 0.4,
        "executor_sample_count": 8,
    }
    intent = synthesize_orchestration_intent(
        synthesize_delegated_judgment(internal_ready_evidence),
        created_at="2026-04-12T00:00:00Z",
    )
    append_orchestration_intent_ledger(tmp_path, intent)
    handoff = admit_orchestration_intent(tmp_path, intent)
    assert handoff["handoff_outcome"] == "admitted_to_execution_substrate"

    task_id = str(handoff["details"]["task_admission"]["task_id"])
    _write_jsonl(
        tmp_path / "logs" / "task_executor.jsonl",
        [{"task_id": task_id, "event": "task_result", "status": "completed"}],
    )

    resolution = resolve_orchestration_result(tmp_path, handoff, executor_log_path=Path(task_executor.LOG_PATH))
    unified = resolve_unified_orchestration_result(
        tmp_path,
        handoff=handoff,
        executor_log_path=Path(task_executor.LOG_PATH),
    )

    assert handoff["intent_ref"]["intent_id"] == intent["intent_id"]
    assert resolution["intent_ref"]["intent_id"] == intent["intent_id"]
    assert unified["source_intent_ref"]["intent_id"] == intent["intent_id"]
    assert unified["source_linkage"]["handoff_outcome"] == handoff["handoff_outcome"]
    assert unified["resolution_path"] == "internal_execution"
    assert unified["result_classification"] == "completed_successfully"
    assert unified["evidence_presence"]["proof_linkage_present"] is True
    assert unified["decision_power"] == "none"
    assert unified["non_authoritative"] is True


def test_contract_projection_outputs_are_observational_and_do_not_mutate_inputs() -> None:
    outcome_review = {
        "review_classification": "execution_failure_heavy",
        "records_considered": 7,
        "condition_flags": {"blocked_heavy": False, "failure_heavy": True, "stall_heavy": False},
        "recent_outcome_counts": {"handoff_not_admitted": 0, "execution_failed": 4},
    }
    before = deepcopy(outcome_review)
    attention = derive_orchestration_attention_recommendation(outcome_review)

    assert outcome_review == before
    assert attention["non_authoritative"] is True
    assert attention["decision_power"] == "none"
    assert attention["does_not_change_admission_or_execution"] is True

    delegated = synthesize_delegated_judgment(_base_evidence())
    delegated_before = deepcopy(delegated)
    next_venue = derive_next_venue_recommendation(
        delegated,
        outcome_review,
        {"review_classification": "balanced_recent_venue_mix", "records_considered": 7},
        attention,
    )

    assert delegated == delegated_before
    assert next_venue["non_authoritative"] is True
    assert next_venue["decision_power"] == "none"
    assert next_venue["does_not_change_admission_or_execution"] is True


def test_contract_adapter_linkage_stays_raw_and_kernel_keeps_result_semantics(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(task_executor, "LOG_PATH", str(tmp_path / "logs" / "task_executor.jsonl"))

    internal_ready_evidence = {
        **_base_evidence(),
        "admission_denied_ratio": 0.75,
        "admission_sample_count": 8,
        "executor_failure_ratio": 0.4,
        "executor_sample_count": 8,
    }
    intent = synthesize_orchestration_intent(
        synthesize_delegated_judgment(internal_ready_evidence),
        created_at="2026-04-12T00:00:00Z",
    )
    handoff = admit_orchestration_intent(tmp_path, intent)
    task_id = str(handoff["details"]["task_admission"]["task_id"])
    _write_jsonl(
        tmp_path / "logs" / "task_executor.jsonl",
        [{"task_id": task_id, "event": "task_result", "status": "unknown_status_from_substrate"}],
    )

    handoff_before = deepcopy(handoff)
    linkage = orchestration_internal_adapters.resolve_task_executor_result_linkage(
        handoff=handoff,
        executor_log_path=tmp_path / "logs" / "task_executor.jsonl",
        read_jsonl=lambda path: [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()],
    )
    resolution = resolve_orchestration_result(tmp_path, handoff, executor_log_path=Path(task_executor.LOG_PATH))

    assert handoff == handoff_before
    assert len(linkage["task_result_rows"]) == 1
    assert linkage["task_result_rows"][0]["status"] == "unknown_status_from_substrate"
    assert resolution["orchestration_result_state"] == "execution_result_missing"
    assert resolution["loop_closed"] is False
