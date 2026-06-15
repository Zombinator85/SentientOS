from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path("scripts/build_real_memory_root_admission_packet.py")
FIXTURES = Path("tests/fixtures/real_memory_root_admission_packet")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], check=False, text=True, capture_output=True)


def test_build_default_and_inspect_fixture() -> None:
    default = _run("build-default")
    assert default.returncode == 0
    assert json.loads(default.stdout)["validation"]["status"] == "valid"
    inspect = _run("inspect-fixture", "ready_real_memory_root_admission_packet_candidate")
    assert inspect.returncode == 0
    assert json.loads(inspect.stdout)["real_memory_root_admission_packet_candidates"][0]["candidate_type"] == "ai_capsule_real_memory_root_admission_packet_candidate"


def test_evaluate_summarize_validate_and_blocked_exit_codes() -> None:
    ready = str(FIXTURES / "ready_real_memory_root_admission_packet_candidate.json")
    evaluate = _run("evaluate", ready)
    assert evaluate.returncode == 0
    assert json.loads(evaluate.stdout)["status"] == "real_memory_root_admission_packet_ready"
    summary = _run("summarize", ready)
    assert summary.returncode == 0
    assert json.loads(summary.stdout)["status"] == "real_memory_root_admission_packet_ready"
    validate = _run("validate", str(FIXTURES / "mixed_real_memory_root_admission_packet_candidate.json"))
    assert validate.returncode == 0
    assert json.loads(validate.stdout)["status"] == "real_memory_root_admission_packet_ready_with_warnings"
    blocked = _run("evaluate", str(FIXTURES / "digest_mismatch_blocked.json"))
    assert blocked.returncode != 0
    assert json.loads(blocked.stdout)["status"] == "real_memory_root_admission_packet_blocked"
