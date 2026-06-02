from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

FIXTURE = Path("tests/fixtures/real_live_memory_commit_executor_implementation_skeleton/ready_executor_skeleton_candidate.json")


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/build_real_live_memory_commit_executor_implementation_skeleton.py", *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_build_default_and_validate_policy() -> None:
    result = run_cli("build-default")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["validation"]["status"] == "valid"
    assert payload["policy"]["real_executor_enabled"] is False

    result = run_cli("validate")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "valid"


def test_evaluate_summarize_validate_and_inspect_fixture() -> None:
    result = run_cli("evaluate", str(FIXTURE))
    assert result.returncode == 0, result.stderr
    evaluated = json.loads(result.stdout)
    assert evaluated["status"] == "executor_skeleton_ready"
    assert evaluated["packet"]["real_executor_enabled"] is False

    result = run_cli("summarize", str(FIXTURE))
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["status"] == "executor_skeleton_ready"
    assert summary["summary_counts"]["candidate_count"] == 1

    result = run_cli("validate", str(FIXTURE))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "executor_skeleton_ready"

    result = run_cli("inspect-fixture", "ready_executor_skeleton_candidate")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["executor_skeleton_candidates"][0]["candidate_id"] == "executor-skeleton-ready-001"


def test_evaluate_writes_no_files(tmp_path: Path) -> None:
    packet = tmp_path / "packet.json"
    packet.write_text(FIXTURE.read_text(), encoding="utf-8")
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    result = run_cli("evaluate", str(packet))
    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    assert result.returncode == 0, result.stderr
    assert after == before
    assert json.loads(result.stdout)["packet"]["real_memory_root_write_enabled"] is False


def test_blocked_evaluate_exits_nonzero(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"executor_skeleton_candidates": []}), encoding="utf-8")
    result = run_cli("evaluate", str(bad))
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "executor_skeleton_blocked"
