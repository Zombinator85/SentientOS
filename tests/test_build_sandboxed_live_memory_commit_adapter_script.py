from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path("scripts/build_sandboxed_live_memory_commit_adapter.py")
FIXTURES = Path("tests/fixtures/sandboxed_live_memory_commit_adapter")


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
    fixture = "valid_ai_capsule_sandbox_commit_candidate.json"
    inspect = _run("inspect-fixture", "--fixture-name", fixture)
    assert inspect.returncode == 0
    assert json.loads(inspect.stdout)["sandbox_commit_candidates"][0]["candidate_type"] == "ai_capsule_sandbox_commit_candidate"
    before = sorted(tmp_path.rglob("*"))
    evaluate = _run("evaluate", "--input", str(FIXTURES / fixture))
    assert evaluate.returncode == 0
    assert json.loads(evaluate.stdout)["status"] == "sandbox_commit_artifacts_ready"
    assert sorted(tmp_path.rglob("*")) == before


def test_summarize_and_blocked_exit_nonzero() -> None:
    summary = _run("summarize", "--input", str(FIXTURES / "valid_ai_capsule_sandbox_commit_candidate.json"))
    assert summary.returncode == 0
    assert json.loads(summary.stdout)["packet_digest"].startswith("sha256:")
    blocked = _run("evaluate", "--input", str(FIXTURES / "digest_mismatch_blocked.json"))
    assert blocked.returncode != 0
    assert json.loads(blocked.stdout)["status"] == "sandbox_commit_blocked"


def test_write_sandbox_artifacts_requires_explicit_safe_sandbox_root(tmp_path: Path) -> None:
    missing = _run("write-sandbox-artifacts", "--input", str(FIXTURES / "valid_ai_capsule_sandbox_commit_candidate.json"))
    assert missing.returncode != 0
    assert json.loads(missing.stdout)["error"] == "missing_sandbox_root"
    root = tmp_path / "sandbox"
    written = _run("write-sandbox-artifacts", "--input", str(FIXTURES / "valid_ai_capsule_sandbox_commit_candidate.json"), "--sandbox-root", str(root))
    assert written.returncode == 0
    out = json.loads(written.stdout)
    assert out["status"] == "sandbox_commit_artifacts_ready"
    assert (root / "sandbox_receipt_manifest.json").is_file()
    assert (root / "sandbox_rollback_manifest.json").is_file()
    assert all(root.resolve() in (Path(path).resolve(), *Path(path).resolve().parents) for path in out["written_files"])


def test_write_sandbox_artifacts_blocks_invalid_outcomes(tmp_path: Path) -> None:
    result = _run("write-sandbox-artifacts", "--input", str(FIXTURES / "path_traversal_blocked.json"), "--sandbox-root", str(tmp_path / "sandbox"))
    assert result.returncode != 0
    out = json.loads(result.stdout)
    assert out["status"] == "sandbox_commit_blocked"
    assert out["written_files"] == []
