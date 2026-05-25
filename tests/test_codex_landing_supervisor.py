from __future__ import annotations

import json
from datetime import datetime, timezone

from sentientos.codex_landing_supervisor import CodexLandingSupervisorRequest, evaluate_landing_supervisor


def _matrix(required_failure_count: int = 0, required_failures: list[str] | None = None) -> str:
    return json.dumps(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "required_failure_count": required_failure_count,
            "required_failures": required_failures or [],
        }
    )


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
