from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

FIXTURE = Path("tests/fixtures/live_executor_activation_record/ready_activation_candidate.json")


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "scripts/build_live_executor_activation_record.py", *args], text=True, capture_output=True, check=False)


def test_evaluate_emits_deterministic_json_and_writes_no_files(tmp_path: Path) -> None:
    before = {p: p.stat().st_mtime_ns for p in tmp_path.iterdir()}
    one = run_cli("evaluate", str(FIXTURE))
    two = run_cli("evaluate", str(FIXTURE))
    assert one.returncode == 0, one.stderr
    assert two.returncode == 0, two.stderr
    assert json.loads(one.stdout) == json.loads(two.stdout)
    assert {p: p.stat().st_mtime_ns for p in tmp_path.iterdir()} == before
    assert json.loads(one.stdout)["status"] == "activation_ready"


def test_validate_policy_and_packet() -> None:
    policy = run_cli("validate")
    assert policy.returncode == 0, policy.stderr
    assert json.loads(policy.stdout)["status"] == "valid"
    packet = run_cli("validate", str(FIXTURE))
    assert packet.returncode == 0, packet.stderr
    assert json.loads(packet.stdout)["status"] == "activation_ready"


def test_summarize_emits_status_digest_counts_and_findings() -> None:
    result = run_cli("summarize", str(FIXTURE))
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["status"] == "activation_ready"
    assert data["digest"].startswith("sha256:")
    assert data["packet_digest"].startswith("sha256:")
    assert data["summary_counts"]["candidate_count"] == 1
    assert data["findings"] == []


def test_inspect_fixture_prints_fixture_json() -> None:
    result = run_cli("inspect-fixture", "ready_activation_candidate")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["activation_candidates"][0]["candidate_type"] == "ai_capsule_activation_candidate"


def test_blocked_outcome_exits_nonzero(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE.read_text())
    payload["activation_candidates"][0]["claimed_preflight_packet_digest"] = "sha256:mismatch"
    path = tmp_path / "blocked.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = run_cli("evaluate", str(path))
    assert result.returncode != 0
    assert json.loads(result.stdout)["status"] == "activation_blocked"
