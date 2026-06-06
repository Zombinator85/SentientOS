from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path("scripts/build_real_executor_execution_plan.py")
FIXTURE_ROOT = Path("tests/fixtures/real_executor_execution_plan")
READY = FIXTURE_ROOT / "ready_real_executor_execution_plan_candidate.json"
NOOP = FIXTURE_ROOT / "noop_real_executor_execution_plan_candidate.json"
MIXED = FIXTURE_ROOT / "mixed_real_executor_execution_plan_candidate.json"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], check=False, text=True, capture_output=True)


def test_cli_build_validate_evaluate_summarize_and_inspect() -> None:
    built = run_cli("build-default")
    assert built.returncode == 0
    assert json.loads(built.stdout)["validation"]["status"] == "valid"

    validated = run_cli("validate", str(READY))
    assert validated.returncode == 0
    assert json.loads(validated.stdout)["status"] == "real_executor_execution_plan_ready"

    evaluated = run_cli("evaluate", str(READY))
    assert evaluated.returncode == 0
    payload = json.loads(evaluated.stdout)
    assert payload["status"] == "real_executor_execution_plan_ready"

    summarized = run_cli("summarize", str(READY))
    assert summarized.returncode == 0
    summary = json.loads(summarized.stdout)
    assert summary["status"] == "real_executor_execution_plan_ready"
    assert summary["packet_digest"] == payload["packet"]["digest"]

    inspected = run_cli("inspect-fixture", "ready_real_executor_execution_plan_candidate")
    assert inspected.returncode == 0
    assert json.loads(inspected.stdout)["real_executor_execution_plan_candidates"][0]["candidate_id"] == "real-execution-plan-ready-001"


def test_cli_noop_mixed_and_blocked_exit_behavior(tmp_path: Path) -> None:
    assert run_cli("evaluate", str(NOOP)).returncode == 0
    assert run_cli("evaluate", str(MIXED)).returncode == 0

    before = {p.relative_to(tmp_path) for p in tmp_path.rglob("*")}
    evaluated = run_cli("evaluate", str(READY))
    after = {p.relative_to(tmp_path) for p in tmp_path.rglob("*")}
    assert evaluated.returncode == 0
    assert before == after

    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({"real_executor_execution_plan_candidates": []}), encoding="utf-8")
    blocked = run_cli("evaluate", str(invalid))
    assert blocked.returncode == 1
    assert json.loads(blocked.stdout)["status"] == "real_executor_execution_plan_blocked"
