from __future__ import annotations

from importlib import reload
import json
from pathlib import Path

import control_plane
import task_admission
import task_executor
from sentientos.delegated_judgment_fabric import synthesize_delegated_judgment
from sentientos.orchestration_intent_fabric import (
    admit_orchestration_intent,
    append_orchestration_intent_ledger,
    build_handoff_execution_gap_map,
    executable_handoff_map,
    resolve_orchestration_result,
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
    judgment = synthesize_delegated_judgment(_base_evidence())
    intent = synthesize_orchestration_intent(judgment, created_at="2026-04-12T00:00:00Z")
    handoff = admit_orchestration_intent(tmp_path, intent)

    assert judgment["recommended_venue"] == "codex_implementation"
    assert handoff["handoff_outcome"] == "staged_only"
    assert "task_admission" not in handoff["details"]
    resolution = resolve_orchestration_result(tmp_path, handoff)
    assert resolution["orchestration_result_state"] == "handoff_not_admitted"
    assert resolution["execution_task_ref"]["task_id"] is None


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
    assert handoff["handoff_result"]["handoff_outcome"] == "staged_only"
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
    assert external_handoff["handoff_outcome"] == "staged_only"
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
