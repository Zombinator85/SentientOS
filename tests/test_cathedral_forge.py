from __future__ import annotations

import json
from pathlib import Path
import subprocess

from sentientos.cathedral_forge import CathedralForge, resolve_goal_profile


def _completed(command: list[str], returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr=stderr)


def test_plan_emits_required_schema(tmp_path: Path) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")

    plan = forge.plan("massive refactor")

    plan_path = tmp_path / "glow" / "forge" / f"plan_{plan.generated_at.replace(':', '-')}.json"
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["goal"] == "massive refactor"
    assert isinstance(payload["phases"], list) and payload["phases"]
    assert "risk_notes" in payload
    assert "rollback_notes" in payload


def test_resolve_goal_profile_smoke_and_default() -> None:
    smoke = resolve_goal_profile("forge_smoke_noop")
    assert smoke.name == "smoke_noop"
    assert smoke.test_command_display == "python -m scripts.run_tests -q tests/test_cathedral_forge.py"

    prefixed_smoke = resolve_goal_profile("forge_smoke_anything")
    assert prefixed_smoke.name == "smoke_noop"

    default = resolve_goal_profile("massive refactor")
    assert default.name == "default"
    assert default.test_command_display == "python -m scripts.run_tests -q"


def test_run_embeds_contract_status_payload(tmp_path: Path, monkeypatch) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")

    contract_status_path = tmp_path / "glow" / "contracts" / "contract_status.json"

    def fake_run(command: list[str]) -> subprocess.CompletedProcess[str]:
        command_text = " ".join(command)
        if "emit_contract_status" in command_text:
            contract_status_path.parent.mkdir(parents=True, exist_ok=True)
            contract_status_path.write_text(
                json.dumps({"schema_version": 1, "contracts": [{"domain_name": "audits", "drifted": False}]}),
                encoding="utf-8",
            )
        return _completed(command, returncode=0, stdout="ok")

    monkeypatch.setattr(forge, "_run_command", fake_run)

    report = forge.run("forge_smoke_noop")

    assert report.outcome == "success"
    assert report.goal_profile == "smoke_noop"
    assert report.preflight.contract_status_embedded["schema_version"] == 1
    assert report.preflight.contract_status_embedded["contracts"][0]["domain_name"] == "audits"
    assert report.ci_commands_run[-1] == "python -m scripts.run_tests -q tests/test_cathedral_forge.py"
    assert all(command != "python -m scripts.run_tests -q" for command in report.ci_commands_run)


def test_run_fails_and_stops_when_drift_detected(tmp_path: Path, monkeypatch) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")

    calls: list[str] = []

    def fake_run(command: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(" ".join(command))
        if "scripts.contract_drift" in " ".join(command):
            return _completed(command, returncode=1, stderr="drift detected")
        if "emit_contract_status" in " ".join(command):
            status_path = tmp_path / "glow" / "contracts" / "contract_status.json"
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text(json.dumps({"schema_version": 1, "contracts": []}), encoding="utf-8")
            return _completed(command, returncode=0, stdout="status emitted")
        return _completed(command, returncode=0, stdout="ok")

    monkeypatch.setattr(forge, "_run_command", fake_run)

    report = forge.run("dangerous refactor")

    assert report.outcome == "failed"
    assert "contract_drift_failed" in report.failure_reasons
    assert report.tests.summary == "skipped: preflight failed"
    assert not any("scripts.run_tests" in command for command in calls)


def test_run_default_goal_uses_full_test_runner(tmp_path: Path, monkeypatch) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")

    commands: list[str] = []

    def fake_run(command: list[str]) -> subprocess.CompletedProcess[str]:
        command_text = " ".join(command)
        commands.append(command_text)
        if "emit_contract_status" in command_text:
            status_path = tmp_path / "glow" / "contracts" / "contract_status.json"
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text(json.dumps({"schema_version": 1, "contracts": []}), encoding="utf-8")
        return _completed(command, returncode=0, stdout="ok")

    monkeypatch.setattr(forge, "_run_command", fake_run)

    report = forge.run("wide refactor")

    assert report.outcome == "success"
    assert report.goal_profile == "default"
    assert any("scripts.run_tests -q" in command for command in commands)


def test_run_fails_when_tests_fail_and_captures_metadata(tmp_path: Path, monkeypatch) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")

    def fake_run(command: list[str]) -> subprocess.CompletedProcess[str]:
        command_text = " ".join(command)
        if "emit_contract_status" in command_text:
            status_path = tmp_path / "glow" / "contracts" / "contract_status.json"
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text(json.dumps({"schema_version": 1, "contracts": []}), encoding="utf-8")
            return _completed(command, returncode=0, stdout="status emitted")
        if "scripts.run_tests" in command_text:
            return _completed(command, returncode=1, stderr="tests failed")
        return _completed(command, returncode=0, stdout="ok")

    monkeypatch.setattr(forge, "_run_command", fake_run)

    report = forge.run("wide refactor")

    assert report.outcome == "failed"
    assert "tests_failed" in report.failure_reasons
    assert report.tests.status == "fail"
    assert report.command_results
    failing_result = report.command_results[-1]
    assert failing_result.status == "fail"
    payload = json.loads(failing_result.summary)
    assert payload["step"] == "tests"
    assert payload["exit_code"] == 1
    assert payload["stderr"] == "tests failed"
