from __future__ import annotations

import json
from pathlib import Path

from sentientos.delegated_judgment_fabric import collect_delegated_judgment_evidence, synthesize_delegated_judgment
from sentientos.scoped_lifecycle_diagnostic import build_scoped_lifecycle_diagnostic
from sentientos.scoped_mutation_lifecycle import SCOPED_ACTION_IDS


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


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


def test_coherent_bounded_implementation_recommends_codex_expand_no_escalation() -> None:
    judgment = synthesize_delegated_judgment(_base_evidence())

    assert judgment["work_class"] == "bounded_repo_implementation", json.dumps(judgment, indent=2, sort_keys=True)
    assert judgment["recommended_venue"] == "codex_implementation"
    assert judgment["next_move_posture"] == "expand"
    assert judgment["consolidation_expansion_posture"] == "expansion_currently_favored"
    assert judgment["escalation_classification"] == "no_escalation_needed"


def test_architectural_uncertainty_recommends_deep_research_audit_and_remains_non_sovereign() -> None:
    evidence = _base_evidence()
    evidence.update(
        {
            "governance_ambiguity_signal": True,
            "contract_drifted_domains": 2,
            "slice_stability_classification": "oscillating",
            "slice_review_classification": "mixed_stress_pattern",
            "slice_health_status": "fragmented",
        }
    )

    judgment = synthesize_delegated_judgment(evidence)

    assert judgment["recommended_venue"] == "deep_research_audit", json.dumps(judgment, indent=2, sort_keys=True)
    assert judgment["next_move_posture"] == "audit"
    assert judgment["consolidation_expansion_posture"] in {"audit_currently_favored", "consolidation_currently_favored"}
    assert judgment["escalation_classification"] == "escalate_for_governance_ambiguity"
    assert judgment["recommendation_only"] is True
    assert judgment["decision_power"] == "none"
    assert judgment["does_not_execute_tools"] is True


def test_external_tool_orchestration_without_adapter_escalates_operator() -> None:
    evidence = _base_evidence()
    evidence["adapter_count"] = 0

    judgment = synthesize_delegated_judgment(evidence, requested_work_hint="external_tool_orchestration")

    assert judgment["work_class"] == "external_tool_orchestration"
    assert judgment["recommended_venue"] == "operator_decision_required"
    assert judgment["next_move_posture"] == "expand"
    assert judgment["escalation_classification"] == "escalate_for_unmodeled_external_action"


def test_collect_evidence_reads_existing_repo_artifacts(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "glow/contracts/contract_status.json",
        {
            "contracts": [
                {"domain_name": "authority_of_judgment_jurisprudence", "drifted": True, "drift_type": "policy_gap"},
                {"domain_name": "stability_doctrine", "drifted": False, "drift_type": "none"},
            ]
        },
    )
    _write_jsonl(
        tmp_path / "logs/task_admission.jsonl",
        [
            {"event": "TASK_ADMITTED"},
            {"event": "TASK_ADMISSION_DENIED"},
            {"event": "TASK_ADMISSION_DENIED"},
            {"event": "TASK_ADMISSION_DENIED"},
        ],
    )
    _write_jsonl(
        tmp_path / "logs/task_executor.jsonl",
        [
            {"event": "task_result", "status": "completed"},
            {"event": "task_result", "status": "failed"},
            {"event": "task_result", "status": "failed"},
            {"event": "task_result", "status": "completed"},
        ],
    )
    _write_jsonl(tmp_path / "logs/federation_handshake.jsonl", [{"event": "handshake"}])

    evidence = collect_delegated_judgment_evidence(
        tmp_path,
        scoped_lifecycle={
            "slice_health": {"slice_health_status": "degraded"},
            "slice_stability": {"stability_classification": "degrading"},
            "slice_retrospective_integrity_review": {"review_classification": "failure_heavy", "records_considered": 5},
        },
    )

    assert evidence["governance_ambiguity_signal"] is True
    assert evidence["contract_drifted_domains"] == 1
    assert evidence["admission_denied_ratio"] == 0.75
    assert evidence["executor_failure_ratio"] == 0.5
    assert evidence["slice_review_classification"] == "failure_heavy"


def test_scoped_lifecycle_consumer_surfaces_delegated_judgment(monkeypatch, tmp_path: Path) -> None:
    def _fake_resolver(_repo_root: Path, *, action_id: str, correlation_id: str) -> dict[str, object]:
        outcome = "fragmented_unresolved" if action_id == SCOPED_ACTION_IDS[0] else "success"
        return {
            "typed_action_identity": action_id,
            "correlation_id": correlation_id,
            "outcome_class": outcome,
        }

    monkeypatch.setattr("sentientos.scoped_lifecycle_diagnostic.resolve_scoped_mutation_lifecycle", _fake_resolver)

    _write_json(
        tmp_path / "glow/contracts/contract_status.json",
        {
            "contracts": [
                {"domain_name": "authority_of_judgment_jurisprudence", "drifted": True, "drift_type": "policy_gap"},
            ]
        },
    )

    _write_jsonl(
        tmp_path / "pulse/forge_events.jsonl",
        [
            {
                "event": "constitutional_mutation_router_execution",
                "typed_action_id": action_id,
                "correlation_id": f"cid-{index}",
            }
            for index, action_id in enumerate(SCOPED_ACTION_IDS)
        ],
    )

    for _ in range(3):
        diagnostic = build_scoped_lifecycle_diagnostic(tmp_path)

    delegated = diagnostic["delegated_judgment"]
    assert delegated["recommended_venue"] == "deep_research_audit", json.dumps(delegated, indent=2, sort_keys=True)
    assert delegated["next_move_posture"] in {"consolidate", "audit"}
    assert delegated["recommendation_only"] is True
    assert delegated["non_authoritative"] is True
    assert delegated["decision_power"] == "none"
