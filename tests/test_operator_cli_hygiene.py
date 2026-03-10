from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import audit_immutability as ai


def _env(repo_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    env["LUMOS_AUTO_APPROVE"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    return env


def test_entrypoints_expose_repo_root_help(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = _env(repo_root)
    entrypoints = [
        [sys.executable, "scripts/node_bootstrap.py", "--help"],
        [sys.executable, "scripts/node_health.py", "--help"],
        [sys.executable, "scripts/incident_bundle.py", "--help"],
        [sys.executable, "scripts/system_constitution.py", "--help"],
        [sys.executable, "scripts/forge_status.py", "--help"],
        [sys.executable, "scripts/forge_replay.py", "--help"],
        [sys.executable, "scripts/verify_audits.py", "--help"],
    ]
    for command in entrypoints:
        cp = subprocess.run(command, cwd=repo_root, env=env, capture_output=True, text=True, check=False)
        assert cp.returncode == 0, cp.stdout + cp.stderr
        assert "--repo-root" in cp.stdout


def test_verify_audits_script_and_module_parity(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = _env(repo_root)

    logs = tmp_path / "logs"
    logs.mkdir()
    ai.append_entry(logs / "ok.jsonl", {"x": 1})

    script_cp = subprocess.run(
        [sys.executable, "scripts/verify_audits.py", str(logs), "--json", "--repo-root", str(tmp_path)],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    module_cp = subprocess.run(
        [sys.executable, "-m", "sentientos.verify_audits", str(logs), "--json", "--repo-root", str(tmp_path)],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert script_cp.returncode == module_cp.returncode == 0
    script_payload = json.loads(script_cp.stdout.strip().splitlines()[-1])
    module_payload = json.loads(module_cp.stdout.strip().splitlines()[-1])
    assert script_payload["tool"] == "verify_audits"
    assert module_payload["tool"] == "verify_audits"
    assert script_payload["status"] == module_payload["status"] == "passed"
    assert script_payload["exit_code"] == module_payload["exit_code"] == 0


def test_audit_immutability_json_includes_exit_code(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = _env(repo_root)

    tracked = tmp_path / "tracked.txt"
    tracked.write_text("stable", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"files": {str(tracked): {"sha256": "0" * 64}}}), encoding="utf-8")

    cp = subprocess.run(
        [sys.executable, "-m", "scripts.audit_immutability_verifier", "--manifest", str(manifest)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert cp.returncode == 1
    payload = json.loads(cp.stdout.strip().splitlines()[-1])
    assert payload["tool"] == "audit_immutability_verifier"
    assert payload["exit_code"] == 1
