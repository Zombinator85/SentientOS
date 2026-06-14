from __future__ import annotations

import json
import pytest
import subprocess
import sys
from pathlib import Path

SCRIPT = Path("scripts/build_real_memory_root_admission_gate.py")
pytestmark = pytest.mark.no_legacy_skip

FIXTURES = Path("tests/fixtures/real_memory_root_admission_gate")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], check=False, text=True, capture_output=True)


def test_build_default_and_validate() -> None:
    default = _run("build-default")
    assert default.returncode == 0
    assert json.loads(default.stdout)["policy"]["default_posture"] == "deny"
    validate = _run("validate")
    assert validate.returncode == 0
    assert json.loads(validate.stdout)["status"] == "valid"


def test_inspect_fixture_and_evaluate_write_nothing(tmp_path: Path) -> None:
    fixture = "valid_ai_capsule_real_memory_root_admission_gate_candidate.json"
    inspect = _run("inspect-fixture", "--fixture-name", fixture)
    assert inspect.returncode == 0
    assert json.loads(inspect.stdout)["real_memory_root_admission_gate_candidates"][0]["candidate_type"] == "ai_capsule_real_memory_root_admission_gate_candidate"
    before = sorted(tmp_path.rglob("*"))
    evaluate = _run("evaluate", "--input", str(FIXTURES / fixture))
    assert evaluate.returncode == 0
    assert json.loads(evaluate.stdout)["status"] == "real_memory_root_admission_gate_ready"
    assert sorted(tmp_path.rglob("*")) == before


def test_summarize_and_blocked_exit_nonzero() -> None:
    summary = _run("summarize", "--input", str(FIXTURES / "valid_ai_capsule_real_memory_root_admission_gate_candidate.json"))
    assert summary.returncode == 0
    assert json.loads(summary.stdout)["packet_digest"].startswith("sha256:")
    blocked = _run("evaluate", "--input", str(FIXTURES / "digest_mismatch_blocked.json"))
    assert blocked.returncode != 0
    assert json.loads(blocked.stdout)["status"] == "real_memory_root_admission_gate_blocked"


def test_validate_input_metadata_uses_embedded_policy() -> None:
    validate = _run("validate", "--input", str(FIXTURES / "mixed_real_memory_root_admission_gate_candidate.json"))
    assert validate.returncode == 0
    assert json.loads(validate.stdout)["status"] == "real_memory_root_admission_gate_ready_with_warnings"
