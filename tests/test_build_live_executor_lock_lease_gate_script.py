from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

FIXTURE = Path("tests/fixtures/live_executor_lock_lease_gate/valid_ai_capsule_lock_lease_candidate.json")
BLOCKED = Path("tests/fixtures/live_executor_lock_lease_gate/executor_plan_digest_mismatch_blocked.json")
SCRIPT = Path("scripts/build_live_executor_lock_lease_gate.py")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], check=False, capture_output=True, text=True)


def test_build_default_validate_summarize_and_inspect_fixture() -> None:
    assert _run("build-default").returncode == 0
    assert _run("validate").returncode == 0
    assert _run("validate", str(FIXTURE)).returncode == 0
    summary = _run("summarize", str(FIXTURE))
    assert summary.returncode == 0
    payload = json.loads(summary.stdout)
    assert payload["status"] == "lock_lease_ready"
    inspected = _run("inspect-fixture", "valid_ai_capsule_lock_lease_candidate")
    assert inspected.returncode == 0
    assert json.loads(inspected.stdout)["lock_lease_candidates"][0]["candidate_type"] == "ai_capsule_lock_lease_candidate"


def test_evaluate_outputs_json_nonzero_for_blocked_and_writes_nothing(tmp_path: Path) -> None:
    before = {p.relative_to(tmp_path) for p in tmp_path.rglob("*")}
    good = _run("evaluate", str(FIXTURE))
    assert good.returncode == 0
    payload = json.loads(good.stdout)
    assert payload["packet"]["real_lock_acquisition_enabled"] is False
    assert payload["packet"]["lockfile_creation_enabled"] is False
    assert {p.relative_to(tmp_path) for p in tmp_path.rglob("*")} == before
    blocked = _run("evaluate", str(BLOCKED))
    assert blocked.returncode == 1
    assert json.loads(blocked.stdout)["status"] == "lock_lease_blocked"
