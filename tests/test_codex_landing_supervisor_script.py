from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone

import pytest

from sentientos.landing_validation_plan import SOLO_MATRIX_STATUS, seal_validation_plan

pytestmark = pytest.mark.no_legacy_skip


def _matrix_payload(required_failure_count: int = 0) -> str:
    return json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "required_failure_count": required_failure_count, "required_failures": ["mypy_baseline"] if required_failure_count else []})


def _solo_plan_payload() -> dict[str, object]:
    required = ["focused_tests", "targeted_mypy", "mypy_baseline", "prompt_boundary", "strict_audits", "audit_immutability"]
    stages = {stage: {"status": "passed"} for stage in required}
    stages["strict_audits"] = {"status": "deferred_to_hosted"}
    stages["audit_immutability"] = {"status": "deferred_to_hosted"}
    return seal_validation_plan({
        "requested_profile": "solo", "effective_profile": "solo", "repository_sha": "1" * 40,
        "phase": "pr-metadata", "title": "[codex:x] ok", "intended_commit_title": "[codex:x] ok",
        "changed_file_identity": [], "focused_test_command_contract": ["focused"],
        "targeted_mypy_command_contract": ["mypy"], "required_stage_ids": required,
        "conditionally_required_stage_ids": [], "skipped_or_deferred_stage_ids": ["matrix_summary"],
        "stage_results": stages, "total_validation_duration_seconds": 1.0,
        "configured_total_budget_seconds": 300, "remaining_budget_seconds": 100,
        "exhaustive_matrix_status": SOLO_MATRIX_STATUS, "exhaustive_matrix_digest": None,
        "hosted_verification": {"status": "pending", "required": True,
            "required_check_context": "Required / Quality Gate", "required_check_integration_id": 15368,
            "pending_stages": ["strict_audits", "audit_immutability"], "merge_permitted": False},
        "overall_status": "ready_for_pr_submission",
    })


def test_cli_accepts_inline_matrix_json() -> None:
    proc = subprocess.run([sys.executable, "scripts/codex_landing_supervisor.py", "evaluate", "--title", "[codex:x] ok", "--intended-commit-title", "[codex:x] ok", "--matrix-json", _matrix_payload(), "--landing-gate-status", "passed", "--summary"], check=False, capture_output=True, text=True)
    assert proc.returncode == 0


def test_cli_exits_nonzero_for_failed_matrix() -> None:
    proc = subprocess.run([sys.executable, "scripts/codex_landing_supervisor.py", "evaluate", "--title", "[codex:x] ok", "--intended-commit-title", "[codex:x] ok", "--matrix-json", _matrix_payload(1)], check=False, capture_output=True, text=True)
    assert proc.returncode == 1


def test_cli_accepts_landing_gate_status_and_can_pass() -> None:
    proc = subprocess.run([sys.executable, "scripts/codex_landing_supervisor.py", "evaluate", "--title", "[codex:x] ok", "--intended-commit-title", "[codex:x] ok", "--matrix-json", _matrix_payload(), "--landing-gate-status", "passed"], check=False, capture_output=True, text=True)
    assert proc.returncode == 0


def test_cli_blocks_when_landing_gate_missing() -> None:
    proc = subprocess.run([sys.executable, "scripts/codex_landing_supervisor.py", "evaluate", "--title", "[codex:x] ok", "--intended-commit-title", "[codex:x] ok", "--matrix-json", _matrix_payload()], check=False, capture_output=True, text=True)
    assert proc.returncode == 1


def test_cli_accepts_sealed_solo_plan_without_matrix(tmp_path) -> None:
    plan_path = tmp_path / "solo-plan.json"
    plan_path.write_text(json.dumps(_solo_plan_payload()), encoding="utf-8")
    proc = subprocess.run([
        sys.executable, "scripts/codex_landing_supervisor.py", "evaluate",
        "--title", "[codex:x] ok", "--intended-commit-title", "[codex:x] ok",
        "--validation-plan-json-path", str(plan_path), "--landing-gate-status", "passed",
    ], check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    result = json.loads(proc.stdout)
    assert result["report"]["validation_profile"] == "solo"
    assert result["report"]["validation_plan_digest"] == _solo_plan_payload()["artifact_digest"]
