from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from sentientos.codex_landing_supervisor import CodexLandingSupervisorRequest, evaluate_landing_supervisor
from sentientos.landing_validation_plan import SOLO_MATRIX_STATUS, seal_validation_plan

pytestmark = pytest.mark.no_legacy_skip


def _matrix(required_failure_count: int = 0, required_failures: list[str] | None = None) -> str:
    return json.dumps(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "required_failure_count": required_failure_count,
            "required_failures": required_failures or [],
        }
    )


def _solo_plan(*, title: str = "[codex:x] ok", intended_commit_title: str = "[codex:x] ok") -> dict[str, object]:
    required_stages = ["focused_tests", "targeted_mypy", "mypy_baseline", "prompt_boundary", "strict_audits", "audit_immutability"]
    stages = {stage: {"status": "passed"} for stage in required_stages}
    stages["strict_audits"] = {"status": "deferred_to_hosted"}
    stages["audit_immutability"] = {"status": "deferred_to_hosted"}
    return seal_validation_plan({
        "requested_profile": "solo",
        "effective_profile": "solo",
        "repository_sha": "1" * 40,
        "phase": "pr-metadata",
        "title": title,
        "intended_commit_title": intended_commit_title,
        "changed_file_identity": [],
        "focused_test_command_contract": ["python -m scripts.run_tests -q tests/test_codex_landing_supervisor.py"],
        "targeted_mypy_command_contract": ["python -m mypy sentientos/codex_landing_supervisor.py"],
        "required_stage_ids": required_stages,
        "conditionally_required_stage_ids": [],
        "skipped_or_deferred_stage_ids": ["matrix_summary"],
        "stage_results": stages,
        "total_validation_duration_seconds": 1.0,
        "configured_total_budget_seconds": 300,
        "remaining_budget_seconds": 100,
        "exhaustive_matrix_status": SOLO_MATRIX_STATUS,
        "exhaustive_matrix_digest": None,
        "hosted_verification": {
            "status": "pending",
            "required": True,
            "required_check_context": "Required / Quality Gate",
            "required_check_integration_id": 15368,
            "pending_stages": ["strict_audits", "audit_immutability"],
            "merge_permitted": False,
        },
        "overall_status": "ready_for_pr_submission",
    })


def test_ready_for_pr_metadata_when_matrix_and_gate_pass() -> None:
    req = CodexLandingSupervisorRequest(
        title="[codex:x] ok",
        intended_commit_title="[codex:x] ok",
        matrix_json_text=_matrix(),
        pr_landing_gate_result={"decision": "pr_metadata_allowed"},
    )
    result = evaluate_landing_supervisor(req)
    assert result.decision.status == "ready_for_pr_metadata"


def test_matrix_failure_requires_repair() -> None:
    req = CodexLandingSupervisorRequest(
        title="[codex:x] ok",
        intended_commit_title="[codex:x] ok",
        matrix_json_text=_matrix(1, ["mypy_baseline"]),
        pr_landing_gate_result={"decision": "pr_metadata_allowed"},
    )
    result = evaluate_landing_supervisor(req)
    assert result.decision.status == "repair_required_task_caused"


def test_baseline_new_errors_requires_repair() -> None:
    req = CodexLandingSupervisorRequest(
        title="[codex:x] ok",
        intended_commit_title="[codex:x] ok",
        matrix_json_text=_matrix(),
        baseline_summary={"new_errors": 3},
        pr_landing_gate_result={"decision": "pr_metadata_allowed"},
    )
    result = evaluate_landing_supervisor(req)
    assert result.decision.status == "repair_required_task_caused"


def test_title_mismatch_blocks() -> None:
    req = CodexLandingSupervisorRequest(title="a", intended_commit_title="b", matrix_json_text=_matrix())
    result = evaluate_landing_supervisor(req)
    assert result.decision.status == "do_not_finalize"


def test_landing_gate_missing_blocks() -> None:
    req = CodexLandingSupervisorRequest(title="[codex:x] ok", intended_commit_title="[codex:x] ok", matrix_json_text=_matrix())
    result = evaluate_landing_supervisor(req)
    assert "landing_gate_missing" in result.report.reasons


def test_landing_gate_failed_blocks() -> None:
    req = CodexLandingSupervisorRequest(title="[codex:x] ok", intended_commit_title="[codex:x] ok", matrix_json_text=_matrix(), pr_landing_gate_result={"decision": "pr_metadata_blocked"})
    result = evaluate_landing_supervisor(req)
    assert result.decision.status == "repair_required_task_caused"


def test_supervisor_recommends_strict_audit_repair_for_strict_lane() -> None:
    req = CodexLandingSupervisorRequest(title="[codex:x] ok", intended_commit_title="[codex:x] ok", matrix_json_text=_matrix(1, ["strict_audits"]), pr_landing_gate_result={"decision": "pr_metadata_allowed"})
    result = evaluate_landing_supervisor(req)
    lane = result.report.failed_lanes[0]
    assert lane.lane == "strict_audits"
    assert any("codex_strict_audit_repair.py" in c for c in lane.rerun_commands)


def test_solo_plan_is_supervised_without_matrix_and_keeps_exact_plan_digest() -> None:
    plan = _solo_plan()
    req = CodexLandingSupervisorRequest(
        title="[codex:x] ok",
        intended_commit_title="[codex:x] ok",
        pr_landing_gate_result={"decision": "pr_metadata_allowed"},
        validation_plan_json_text=json.dumps(plan),
    )
    result = evaluate_landing_supervisor(req)
    assert result.decision.status == "ready_for_pr_metadata"
    assert result.report.validation_profile == "solo"
    assert result.report.validation_plan_digest == plan["artifact_digest"]


def test_solo_plan_digest_or_title_tampering_blocks_supervision() -> None:
    plan = _solo_plan()
    plan["title"] = "[codex:x] changed"
    req = CodexLandingSupervisorRequest(
        title="[codex:x] ok",
        intended_commit_title="[codex:x] ok",
        pr_landing_gate_result={"decision": "pr_metadata_allowed"},
        validation_plan_json_text=json.dumps(plan),
    )
    result = evaluate_landing_supervisor(req)
    assert result.decision.status == "do_not_finalize"
    assert "validation_plan_digest_mismatch" in result.report.reasons
    assert "validation_plan_title_mismatch" in result.report.reasons


def test_solo_supervision_rejects_matrix_evidence() -> None:
    req = CodexLandingSupervisorRequest(
        title="[codex:x] ok",
        intended_commit_title="[codex:x] ok",
        matrix_json_text=_matrix(1, ["historical_matrix_failure"]),
        pr_landing_gate_result={"decision": "pr_metadata_allowed"},
        validation_plan_json_text=json.dumps(_solo_plan()),
    )
    result = evaluate_landing_supervisor(req)
    assert result.decision.status == "do_not_finalize"
    assert "matrix_supplied_for_solo_profile" in result.report.reasons
