from __future__ import annotations

import json
import pytest
import subprocess
import sys
from pathlib import Path

pytestmark = pytest.mark.no_legacy_skip

FIXTURE = Path("tests/fixtures/real_live_memory_commit_adapter_readiness_envelope/valid_ai_capsule_live_adapter_readiness_candidate.json")
BLOCKED = Path("tests/fixtures/real_live_memory_commit_adapter_readiness_envelope/final_review_digest_mismatch_blocked.json")
SCRIPT = Path("scripts/build_real_live_memory_commit_adapter_readiness_envelope.py")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], check=False, text=True, capture_output=True)


def test_build_default_and_validate_policy() -> None:
    result = _run("build-default")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["validation"]["status"] == "valid"
    assert payload["policy"]["adapter_runtime_execution_enabled"] is False


def test_evaluate_emits_json_and_writes_nothing(tmp_path: Path) -> None:
    probe = tmp_path / "probe"
    probe.mkdir()
    before = sorted(p.relative_to(probe) for p in probe.rglob("*"))
    result = _run("evaluate", str(FIXTURE))
    after = sorted(p.relative_to(probe) for p in probe.rglob("*"))
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "live_adapter_readiness_ready"
    assert payload["packet"]["adapter_runtime_execution_enabled"] is False
    assert before == after == []


def test_validate_and_summarize_success() -> None:
    valid = _run("validate", str(FIXTURE))
    assert valid.returncode == 0
    summary = _run("summarize", str(FIXTURE))
    assert summary.returncode == 0
    payload = json.loads(summary.stdout)
    assert payload["status"] == "live_adapter_readiness_ready"
    assert payload["packet_digest"].startswith("sha256:")


def test_blocked_outcomes_exit_nonzero() -> None:
    result = _run("evaluate", str(BLOCKED))
    assert result.returncode != 0
    assert json.loads(result.stdout)["status"] == "live_adapter_readiness_blocked"


def test_inspect_fixture_prints_fixture_json() -> None:
    result = _run("inspect-fixture", "valid_ai_capsule_live_adapter_readiness_candidate")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert "final_live_memory_commit_review_packet" in payload
