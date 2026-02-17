from __future__ import annotations

import json
from pathlib import Path

from sentientos.cathedral_forge import CathedralForge
from sentientos.forge_env import ForgeEnv
from sentientos.forge_goals import resolve_goal
from sentientos.forge_model import CommandResult, CommandSpec


def _fake_env(root: Path) -> ForgeEnv:
    return ForgeEnv(
        python="/tmp/fake-python",
        pip="/tmp/fake-pip",
        venv_path=str(root / ".forge" / "venv"),
        created=False,
        install_summary="reused",
    )


def _ok_step(command: CommandSpec, cwd: Path) -> CommandResult:
    return CommandResult(
        step=command.step,
        argv=command.argv,
        cwd=str(cwd),
        env_overlay={},
        timeout_seconds=command.timeout_seconds,
        returncode=0,
        stdout="ok",
        stderr="",
    )


def test_goal_registry_resolution() -> None:
    baseline = resolve_goal("baseline_reclamation")
    assert baseline.goal_id == "baseline_reclamation"
    assert baseline.apply_commands == []

    smoke = resolve_goal("forge_smoke_noop")
    assert smoke.gate_profile == "smoke_noop"

    adhoc = resolve_goal("custom migration")
    assert adhoc.goal_id == "adhoc"


def test_session_creation_and_cleanup(tmp_path: Path) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")
    session = forge._create_session("2025-01-01T00-00-00Z")

    assert Path(session.root_path).exists()
    assert session.root_path != str(tmp_path)

    forge._cleanup_session(session)
    assert session.cleanup_performed is True


def test_apply_records_command_results(tmp_path: Path, monkeypatch) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")
    goal = resolve_goal("forge_self_hosting")
    session = forge._create_session("2025-01-01T00-00-00Z")
    monkeypatch.setattr(forge, "_run_step", _ok_step)
    result = forge.apply(goal, session)

    assert result.status == "success"
    assert len(result.step_results) == len(goal.apply_commands)


def test_autopublish_flags_disabled_by_default(tmp_path: Path, monkeypatch) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")
    goal = resolve_goal("forge_self_hosting")
    session = forge._create_session("2025-01-01T00-00-00Z")

    monkeypatch.delenv("SENTIENTOS_FORGE_AUTOCOMMIT", raising=False)
    monkeypatch.delenv("SENTIENTOS_FORGE_AUTOPR", raising=False)

    notes = forge._maybe_publish(goal, session)

    assert notes == []
    assert not list((tmp_path / "glow" / "forge").glob("pr_*.json"))


def test_no_progress_emits_docket_and_stops(tmp_path: Path, monkeypatch) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")

    monkeypatch.setattr("sentientos.cathedral_forge.bootstrap_env", lambda root: _fake_env(root))

    def fake_create_session(generated_at: str):
        root = tmp_path / "session"
        root.mkdir(parents=True, exist_ok=True)
        return type("Session", (), {
            "session_id": "s1",
            "root_path": str(root),
            "strategy": "copy",
            "branch_name": "forge/s1",
            "preserved_on_failure": False,
            "cleanup_performed": False,
        })()

    run_counter = {"value": 0}

    def fake_run_step(command: CommandSpec, cwd: Path) -> CommandResult:
        if command.step == "contract_status":
            status_path = cwd / "glow" / "contracts"
            status_path.mkdir(parents=True, exist_ok=True)
            (status_path / "contract_status.json").write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
        if command.step.startswith("baseline_harvest_"):
            run_counter["value"] += 1
            return CommandResult(
                step=command.step,
                argv=command.argv,
                cwd=str(cwd),
                env_overlay={},
                timeout_seconds=command.timeout_seconds,
                returncode=1,
                stdout="FAILED tests/test_alpha.py::test_one - AssertionError: CHOICE_POINT ambiguous",
                stderr="",
            )
        return _ok_step(command, cwd)

    monkeypatch.setattr(forge, "_create_session", fake_create_session)
    monkeypatch.setattr(forge, "_run_step", fake_run_step)
    monkeypatch.setattr(forge, "_cleanup_session", lambda session: None)

    report = forge.run("baseline_reclamation")

    assert report.outcome == "failed"
    assert report.docket_path is not None
    assert Path(report.docket_path).exists()
    assert run_counter["value"] == 2


def test_budget_governor_stops_after_max_iterations(tmp_path: Path, monkeypatch) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")

    monkeypatch.setattr("sentientos.cathedral_forge.bootstrap_env", lambda root: _fake_env(root))

    def fake_create_session(generated_at: str):
        root = tmp_path / "session"
        root.mkdir(parents=True, exist_ok=True)
        return type("Session", (), {
            "session_id": "s1",
            "root_path": str(root),
            "strategy": "copy",
            "branch_name": "forge/s1",
            "preserved_on_failure": False,
            "cleanup_performed": False,
        })()

    monkeypatch.setenv("SENTIENTOS_FORGE_MAX_ITERS", "1")

    def fake_run_step(command: CommandSpec, cwd: Path) -> CommandResult:
        if command.step == "contract_status":
            status_path = cwd / "glow" / "contracts"
            status_path.mkdir(parents=True, exist_ok=True)
            (status_path / "contract_status.json").write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
        if command.step.startswith("baseline_harvest_"):
            return CommandResult(
                step=command.step,
                argv=command.argv,
                cwd=str(cwd),
                env_overlay={},
                timeout_seconds=command.timeout_seconds,
                returncode=1,
                stdout="FAILED tests/test_alpha.py::test_one - AssertionError: still broken",
                stderr="",
            )
        return _ok_step(command, cwd)

    monkeypatch.setattr(forge, "_create_session", fake_create_session)
    monkeypatch.setattr(forge, "_run_step", fake_run_step)
    monkeypatch.setattr(forge, "_cleanup_session", lambda session: None)

    report = forge.run("baseline_reclamation")

    assert report.outcome == "failed"
    assert report.baseline_budget is not None
    assert report.baseline_budget["iterations_used"] == 1


def test_progress_reduces_failure_count(tmp_path: Path, monkeypatch) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")

    monkeypatch.setattr("sentientos.cathedral_forge.bootstrap_env", lambda root: _fake_env(root))

    def fake_create_session(generated_at: str):
        root = tmp_path / "session"
        root.mkdir(parents=True, exist_ok=True)
        return type("Session", (), {
            "session_id": "s1",
            "root_path": str(root),
            "strategy": "copy",
            "branch_name": "forge/s1",
            "preserved_on_failure": False,
            "cleanup_performed": False,
        })()

    state = {"iter": 0}

    def fake_run_step(command: CommandSpec, cwd: Path) -> CommandResult:
        if command.step == "contract_status":
            status_path = cwd / "glow" / "contracts"
            status_path.mkdir(parents=True, exist_ok=True)
            (status_path / "contract_status.json").write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
        if command.step.startswith("baseline_harvest_"):
            state["iter"] += 1
            if state["iter"] == 1:
                stdout = "\n".join([
                    "FAILED tests/test_alpha.py::test_one - AssertionError: one",
                    "FAILED tests/test_beta.py::test_two - AssertionError: two",
                ])
                return CommandResult(command.step, command.argv, str(cwd), {}, command.timeout_seconds, 1, stdout, "")
            return CommandResult(command.step, command.argv, str(cwd), {}, command.timeout_seconds, 0, "", "")
        return _ok_step(command, cwd)

    monkeypatch.setattr(forge, "_create_session", fake_create_session)
    monkeypatch.setattr(forge, "_run_step", fake_run_step)
    monkeypatch.setattr(forge, "_cleanup_session", lambda session: None)
    monkeypatch.setattr("sentientos.cathedral_forge.generate_fix_candidates", lambda clusters, root: [])

    report = forge.run("baseline_reclamation")

    assert report.test_failures_before == 2
    assert report.test_failures_after == 0
    assert report.outcome == "success"


def test_contract_drift_gate_prevents_success_at_end(tmp_path: Path, monkeypatch) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")

    monkeypatch.setattr("sentientos.cathedral_forge.bootstrap_env", lambda root: _fake_env(root))

    def fake_create_session(generated_at: str):
        root = tmp_path / "session"
        root.mkdir(parents=True, exist_ok=True)
        return type("Session", (), {
            "session_id": "s1",
            "root_path": str(root),
            "strategy": "copy",
            "branch_name": "forge/s1",
            "preserved_on_failure": False,
            "cleanup_performed": False,
        })()

    def fake_run_step(command: CommandSpec, cwd: Path) -> CommandResult:
        if command.step == "contract_status":
            status_path = cwd / "glow" / "contracts"
            status_path.mkdir(parents=True, exist_ok=True)
            (status_path / "contract_status.json").write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
        if command.step == "contract_drift_end":
            return CommandResult(command.step, command.argv, str(cwd), {}, command.timeout_seconds, 1, "drift", "")
        if command.step.startswith("baseline_harvest_"):
            return CommandResult(command.step, command.argv, str(cwd), {}, command.timeout_seconds, 0, "", "")
        return _ok_step(command, cwd)

    monkeypatch.setattr(forge, "_create_session", fake_create_session)
    monkeypatch.setattr(forge, "_run_step", fake_run_step)
    monkeypatch.setattr(forge, "_cleanup_session", lambda session: None)

    report = forge.run("baseline_reclamation")

    assert report.outcome == "failed"
    assert "apply_failed" in report.failure_reasons


def test_run_smoke_profile_still_works(tmp_path: Path, monkeypatch) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")

    monkeypatch.setattr("sentientos.cathedral_forge.bootstrap_env", lambda root: _fake_env(root))

    def fake_run_step(command: CommandSpec, cwd: Path) -> CommandResult:
        if command.step == "contract_status":
            status_dir = cwd / "glow" / "contracts"
            status_dir.mkdir(parents=True, exist_ok=True)
            (status_dir / "contract_status.json").write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
        return CommandResult(
            step=command.step,
            argv=command.argv,
            cwd=str(cwd),
            env_overlay={},
            timeout_seconds=command.timeout_seconds,
            returncode=0,
            stdout="ok",
            stderr="",
        )

    monkeypatch.setattr(forge, "_run_step", fake_run_step)
    report = forge.run("forge_smoke_noop")

    assert report.goal_profile == "smoke_noop"
    assert report.outcome == "success"
    assert report.session.env_python_path == "/tmp/fake-python"


def test_run_uses_forge_env_python_for_all_python_steps(tmp_path: Path, monkeypatch) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")
    fake_python = "/tmp/forge-python"
    monkeypatch.setattr("sentientos.cathedral_forge.bootstrap_env", lambda root: ForgeEnv(fake_python, "pip", str(root / ".forge" / "venv"), False, "reused"))

    seen: dict[str, list[str]] = {}

    def fake_run_step(command: CommandSpec, cwd: Path) -> CommandResult:
        seen[command.step] = command.argv
        if command.step == "contract_status":
            status_dir = cwd / "glow" / "contracts"
            status_dir.mkdir(parents=True, exist_ok=True)
            (status_dir / "contract_status.json").write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
        if command.step.startswith("baseline_harvest_"):
            return CommandResult(command.step, command.argv, str(cwd), {}, command.timeout_seconds, 0, "", "")
        return CommandResult(command.step, command.argv, str(cwd), {}, command.timeout_seconds, 0, "ok", "")

    monkeypatch.setattr(forge, "_run_step", fake_run_step)

    report = forge.run("baseline_reclamation")

    assert report.outcome == "success"
    assert seen["contract_drift"][0] == fake_python
    assert seen["contract_status"][0] == fake_python
    assert seen["tests"][0] == fake_python
    assert seen["baseline_harvest_1"][0] == fake_python


def test_baseline_harvest_runner_run_tests_mode(tmp_path: Path, monkeypatch) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")
    monkeypatch.setenv("SENTIENTOS_FORGE_HARVEST_RUNNER", "run_tests")

    argv = forge._baseline_harvest_argv("/tmp/py")

    assert argv[:3] == ["/tmp/py", "-m", "scripts.run_tests"]
