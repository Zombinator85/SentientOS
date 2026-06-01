from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

FIXTURE = Path("tests/fixtures/live_executor_preflight_packet/valid_ai_capsule_preflight_candidate.json")


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "scripts/build_live_executor_preflight_packet.py", *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def test_build_default_and_validate_policy() -> None:
    result = run_cli("build-default")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["validation"]["status"] == "valid"
    assert data["policy"]["default_posture"] == "deny"


def test_evaluate_emits_deterministic_json_and_writes_nothing(tmp_path: Path) -> None:
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    first = run_cli("evaluate", str(FIXTURE))
    second = run_cli("evaluate", str(FIXTURE))
    after = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert json.loads(first.stdout) == json.loads(second.stdout)
    assert before == after
    assert json.loads(first.stdout)["status"] == "preflight_ready"


def test_validate_and_summarize() -> None:
    validate = run_cli("validate", str(FIXTURE))
    assert validate.returncode == 0, validate.stderr
    summarize = run_cli("summarize", str(FIXTURE))
    assert summarize.returncode == 0, summarize.stderr
    summary = json.loads(summarize.stdout)
    assert summary["status"] == "preflight_ready"
    assert summary["summary_counts"]["candidate_count"] == 1


def test_inspect_fixture_prints_fixture_json() -> None:
    result = run_cli("inspect-fixture", "valid_ai_capsule_preflight_candidate")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["preflight_candidates"][0]["candidate_type"] == "ai_capsule_preflight_candidate"


def test_blocked_outcome_exits_nonzero(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["preflight_candidates"][0]["claimed_lock_lease_gate_packet_digest"] = "wrong"
    packet = tmp_path / "blocked.json"
    packet.write_text(json.dumps(payload), encoding="utf-8")
    result = run_cli("evaluate", str(packet))
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "preflight_blocked"
