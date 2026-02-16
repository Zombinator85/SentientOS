"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import audit_immutability as ai


def _repo_env(repo_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    env["LUMOS_AUTO_APPROVE"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    return env


def _read_result(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_verify_audits_module_writes_result_success_and_failure(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    logs = tmp_path / "logs"
    logs.mkdir()
    ai.append_entry(logs / "ok.jsonl", {"x": 1})

    env = _repo_env(repo_root)
    success = subprocess.run(
        [sys.executable, "-m", "scripts.verify_audits", str(logs)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert success.returncode == 0, success.stdout + success.stderr
    success_payload = _read_result(tmp_path / "glow" / "audits" / "verify_audits_result.json")
    assert success_payload["tool"] == "verify_audits"
    assert success_payload["ok"] is True
    assert isinstance(success_payload["issues"], list)
    assert success_payload["error"] is None

    (logs / "broken.jsonl").write_text('{"bad": true\n', encoding="utf-8")
    failure = subprocess.run(
        [sys.executable, "-m", "scripts.verify_audits", str(logs)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert failure.returncode == 1
    failure_payload = _read_result(tmp_path / "glow" / "audits" / "verify_audits_result.json")
    assert failure_payload["tool"] == "verify_audits"
    assert failure_payload["ok"] is False
    assert isinstance(failure_payload["issues"], list)


def test_audit_immutability_module_writes_result_success_and_failure(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = _repo_env(repo_root)

    tracked = tmp_path / "tracked.txt"
    tracked.write_text("stable", encoding="utf-8")
    good_hash = hashlib.sha256(tracked.read_bytes()).hexdigest()

    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"files": {str(tracked): {"sha256": good_hash}}}),
        encoding="utf-8",
    )

    success = subprocess.run(
        [sys.executable, "-m", "scripts.audit_immutability_verifier", "--manifest", str(manifest)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert success.returncode == 0, success.stdout + success.stderr
    success_payload = _read_result(tmp_path / "glow" / "audits" / "audit_immutability_result.json")
    assert success_payload["tool"] == "audit_immutability_verifier"
    assert success_payload["ok"] is True
    assert success_payload["error"] is None

    manifest.write_text(
        json.dumps({"files": {str(tracked): {"sha256": "0" * 64}}}),
        encoding="utf-8",
    )
    failure = subprocess.run(
        [sys.executable, "-m", "scripts.audit_immutability_verifier", "--manifest", str(manifest)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert failure.returncode == 1
    failure_payload = _read_result(tmp_path / "glow" / "audits" / "audit_immutability_result.json")
    assert failure_payload["tool"] == "audit_immutability_verifier"
    assert failure_payload["ok"] is False
    assert isinstance(failure_payload["issues"], list)
