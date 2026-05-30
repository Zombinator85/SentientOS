from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

SCRIPT = Path("scripts/build_memory_commit_plan_packet.py")
FIXTURES = Path("tests/fixtures/memory_commit_plan_packet")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], check=False, text=True, capture_output=True)


def test_cli_build_default_and_validate() -> None:
    built = _run("build-default")
    assert built.returncode == 0
    assert json.loads(built.stdout)["policy"]["default_commit_posture"] == "deny"
    validated = _run("validate")
    assert validated.returncode == 0
    assert json.loads(validated.stdout)["ok"] is True


def test_cli_evaluate_summarize_and_output(tmp_path: Path) -> None:
    fixture = FIXTURES / "valid_ai_capsule_commit_plan_candidate.json"
    output = tmp_path / "plan.json"
    evaluated = _run("evaluate", "--input", str(fixture), "--output", str(output))
    assert evaluated.returncode == 0
    payload = json.loads(evaluated.stdout)
    assert payload["status"] == "memory_commit_plan_ready"
    assert output.exists()
    summarized = _run("summarize", "--input", str(fixture))
    assert summarized.returncode == 0
    summary = json.loads(summarized.stdout)
    assert summary["summary_counts"]["candidate_count"] == 1
    assert summary["packet_digest"]


def test_cli_inspect_fixture() -> None:
    inspected = _run("inspect-fixture", "--fixture-name", "valid_noop_commit_plan_candidate.json")
    assert inspected.returncode == 0
    assert json.loads(inspected.stdout)["plan_candidate"]["candidate_type"] == "noop_commit_plan_candidate"


def test_cli_blocked_status_exits_nonzero() -> None:
    blocked = _run("evaluate", "--input", str(FIXTURES / "live_write_claim_blocked.json"))
    assert blocked.returncode == 1
    assert json.loads(blocked.stdout)["status"] == "memory_commit_plan_blocked_live_write_claim"
