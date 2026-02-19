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

    storm = resolve_goal("repo_green_storm")
    assert storm.goal_id == "repo_green_storm"

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

    notes, remote = forge._maybe_publish(goal, session, improvement_summary=None, ci_baseline_before=None, ci_baseline_after=None, metadata=None)

    assert notes == []
    assert remote["checks_overall"] == "unknown"
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
        if command.step.startswith("baseline_full_rerun_confirm_"):
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
    monkeypatch.setenv("SENTIENTOS_FORGE_NO_IMPROVEMENT_LIMIT", "1")

    report = forge.run("baseline_reclamation")

    assert report.outcome == "failed"
    assert "no progress" in report.failure_reasons
    assert report.docket_path is not None
    assert Path(report.docket_path).exists()
    assert report.baseline_progress
    assert run_counter["value"] == 2


def test_baseline_engine_progress_without_fix_application(tmp_path: Path, monkeypatch) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")
    monkeypatch.setattr("sentientos.cathedral_forge.bootstrap_env", lambda root: _fake_env(root))
    monkeypatch.setattr("sentientos.cathedral_forge.generate_fix_candidates", lambda clusters, root: [])

    state = {"iter": 0}

    def fake_run_step(command: CommandSpec, cwd: Path) -> CommandResult:
        if command.step == "contract_status":
            status_path = cwd / "glow" / "contracts"
            status_path.mkdir(parents=True, exist_ok=True)
            (status_path / "contract_status.json").write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
        if command.step.startswith("baseline_harvest_"):
            state["iter"] += 1
            if state["iter"] == 1:
                out = "\n".join([
                    "FAILED tests/test_alpha.py::test_one - AssertionError: one",
                    "FAILED tests/test_beta.py::test_two - AssertionError: two",
                ])
                return CommandResult(command.step, command.argv, str(cwd), {}, command.timeout_seconds, 1, out, "")
            if state["iter"] == 2:
                out = "FAILED tests/test_alpha.py::test_one - AssertionError: one"
                return CommandResult(command.step, command.argv, str(cwd), {}, command.timeout_seconds, 1, out, "")
            return CommandResult(command.step, command.argv, str(cwd), {}, command.timeout_seconds, 0, "", "")
        return _ok_step(command, cwd)

    monkeypatch.setattr(forge, "_run_step", fake_run_step)
    monkeypatch.setenv("SENTIENTOS_FORGE_NO_IMPROVEMENT_LIMIT", "1")

    report = forge.run("baseline_reclamation")

    assert report.outcome == "success"
    assert report.baseline_progress is not None
    assert any(
        isinstance(entry.get("delta"), dict) and entry["delta"].get("improved") is True
        for entry in report.baseline_progress
        if isinstance(entry, dict)
    )


def test_baseline_engine_cluster_digest_change_counts_as_improvement(tmp_path: Path, monkeypatch) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")
    monkeypatch.setattr("sentientos.cathedral_forge.bootstrap_env", lambda root: _fake_env(root))
    monkeypatch.setattr("sentientos.cathedral_forge.generate_fix_candidates", lambda clusters, root: [])
    monkeypatch.setenv("SENTIENTOS_FORGE_MAX_ITERS", "2")
    monkeypatch.setenv("SENTIENTOS_FORGE_NO_IMPROVEMENT_LIMIT", "1")

    state = {"iter": 0}

    def fake_run_step(command: CommandSpec, cwd: Path) -> CommandResult:
        if command.step == "contract_status":
            status_path = cwd / "glow" / "contracts"
            status_path.mkdir(parents=True, exist_ok=True)
            (status_path / "contract_status.json").write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
        if command.step.startswith("baseline_harvest_"):
            state["iter"] += 1
            msg = "a" if state["iter"] == 1 else "b"
            out = f"FAILED tests/test_alpha.py::test_one - AssertionError: {msg}"
            return CommandResult(command.step, command.argv, str(cwd), {}, command.timeout_seconds, 1, out, "")
        return _ok_step(command, cwd)

    monkeypatch.setattr(forge, "_run_step", fake_run_step)

    report = forge.run("baseline_reclamation")

    assert report.outcome == "failed"
    assert "no progress" not in report.failure_reasons


def test_baseline_engine_confirm_rerun_prevents_false_no_progress(tmp_path: Path, monkeypatch) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")
    monkeypatch.setattr("sentientos.cathedral_forge.bootstrap_env", lambda root: _fake_env(root))
    monkeypatch.setattr("sentientos.cathedral_forge.generate_fix_candidates", lambda clusters, root: [])
    monkeypatch.setenv("SENTIENTOS_FORGE_NO_IMPROVEMENT_LIMIT", "1")

    state = {"iter": 0}

    def fake_run_step(command: CommandSpec, cwd: Path) -> CommandResult:
        if command.step == "contract_status":
            status_path = cwd / "glow" / "contracts"
            status_path.mkdir(parents=True, exist_ok=True)
            (status_path / "contract_status.json").write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
        if command.step.startswith("baseline_harvest_"):
            state["iter"] += 1
            out = "FAILED tests/test_alpha.py::test_one - AssertionError: same"
            return CommandResult(command.step, command.argv, str(cwd), {}, command.timeout_seconds, 1, out, "")
        if command.step.startswith("baseline_full_rerun_confirm_"):
            return CommandResult(command.step, command.argv, str(cwd), {}, command.timeout_seconds, 0, "", "")
        return _ok_step(command, cwd)

    monkeypatch.setattr(forge, "_run_step", fake_run_step)

    report = forge.run("baseline_reclamation")

    assert report.outcome == "success"
    assert report.baseline_progress is not None
    assert any(
        isinstance(entry.get("notes"), list) and "confirm_full_rerun" in entry["notes"]
        for entry in report.baseline_progress
        if isinstance(entry, dict)
    )


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
    assert report.session.env_venv_path.endswith(".forge/venv")
    assert report.session.env_reused is True
    assert report.session.env_install_summary == "reused"


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

    argv = forge._baseline_harvest_argv("/tmp/py", "baseline_reclamation")

    assert argv[:3] == ["/tmp/py", "-m", "scripts.run_tests"]


def test_repo_green_storm_harvest_runner_defaults_to_run_tests(tmp_path: Path, monkeypatch) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")
    monkeypatch.delenv("SENTIENTOS_FORGE_HARVEST_RUNNER", raising=False)

    argv = forge._baseline_harvest_argv("/tmp/py", "repo_green_storm")

    assert argv[:3] == ["/tmp/py", "-m", "scripts.run_tests"]


def test_repo_green_storm_report_progress_delta(tmp_path: Path, monkeypatch) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")
    monkeypatch.setattr("sentientos.cathedral_forge.bootstrap_env", lambda root: _fake_env(root))

    def fake_run_step(command: CommandSpec, cwd: Path) -> CommandResult:
        if command.step == "contract_status":
            status_dir = cwd / "glow" / "contracts"
            status_dir.mkdir(parents=True, exist_ok=True)
            (status_dir / "contract_status.json").write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
        if command.step.startswith("baseline_harvest_"):
            return CommandResult(command.step, command.argv, str(cwd), {}, command.timeout_seconds, 1, "FAILED tests/test_a.py::test_x - AssertionError: x", "")
        return CommandResult(command.step, command.argv, str(cwd), {}, command.timeout_seconds, 0, "ok", "")

    monkeypatch.setattr(forge, "_run_step", fake_run_step)
    monkeypatch.setattr("sentientos.cathedral_forge.generate_fix_candidates", lambda clusters, root: [])

    # avoid running full test suite in ci baseline emitter
    monkeypatch.setattr("sentientos.cathedral_forge.emit_ci_baseline", lambda **kwargs: type("S", (), {
        "schema_version": 1,
        "generated_at": "2025-01-01T00:00:00Z",
        "git_sha": "abc",
        "runner": "scripts.run_tests",
        "passed": False,
        "failed_count": 10 if kwargs.get("run_command", False) else 7,
        "top_clusters": [],
        "last_green_sha": None,
    })())

    report = forge.run("repo_green_storm")

    assert report.outcome == "failed"
    assert report.progress_delta is not None
    assert int(report.progress_delta["failed_count_before"]) >= int(report.progress_delta["failed_count_after"])


def test_smoke_noop_uses_short_timeouts(tmp_path: Path, monkeypatch) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")
    monkeypatch.setattr("sentientos.cathedral_forge.bootstrap_env", lambda root: _fake_env(root))
    monkeypatch.setenv("SENTIENTOS_FORGE_SMOKE_TIMEOUT_SECONDS", "17")

    seen: dict[str, int] = {}

    def fake_run_step(command: CommandSpec, cwd: Path) -> CommandResult:
        seen[command.step] = command.timeout_seconds
        if command.step == "contract_status":
            status_dir = cwd / "glow" / "contracts"
            status_dir.mkdir(parents=True, exist_ok=True)
            (status_dir / "contract_status.json").write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
        return CommandResult(command.step, command.argv, str(cwd), {}, command.timeout_seconds, 0, "ok", "")

    monkeypatch.setattr(forge, "_run_step", fake_run_step)

    report = forge.run("forge_smoke_noop")

    assert report.outcome == "success"
    assert seen["contract_drift"] == 17
    assert seen["contract_status"] == 17
    assert seen["env_import_sentientos"] == 17
    assert seen["tests"] == 17


def test_non_smoke_skips_env_import_by_default(tmp_path: Path, monkeypatch) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")
    monkeypatch.setattr("sentientos.cathedral_forge.bootstrap_env", lambda root: _fake_env(root))

    steps: list[str] = []

    def fake_run_step(command: CommandSpec, cwd: Path) -> CommandResult:
        steps.append(command.step)
        if command.step == "contract_status":
            status_dir = cwd / "glow" / "contracts"
            status_dir.mkdir(parents=True, exist_ok=True)
            (status_dir / "contract_status.json").write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
        return CommandResult(command.step, command.argv, str(cwd), {}, command.timeout_seconds, 0, "ok", "")

    monkeypatch.setattr(forge, "_run_step", fake_run_step)

    report = forge.run("baseline_reclamation")

    assert report.outcome == "success"
    assert "env_import_sentientos" not in steps


def test_non_smoke_can_require_env_import(tmp_path: Path, monkeypatch) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")
    monkeypatch.setattr("sentientos.cathedral_forge.bootstrap_env", lambda root: _fake_env(root))
    monkeypatch.setenv("SENTIENTOS_FORGE_REQUIRE_ENV_IMPORT", "1")

    steps: list[str] = []

    def fake_run_step(command: CommandSpec, cwd: Path) -> CommandResult:
        steps.append(command.step)
        if command.step == "contract_status":
            status_dir = cwd / "glow" / "contracts"
            status_dir.mkdir(parents=True, exist_ok=True)
            (status_dir / "contract_status.json").write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
        return CommandResult(command.step, command.argv, str(cwd), {}, command.timeout_seconds, 0, "ok", "")

    monkeypatch.setattr(forge, "_run_step", fake_run_step)

    report = forge.run("baseline_reclamation")

    assert report.outcome == "success"
    assert "env_import_sentientos" in steps


def test_campaign_goal_executes_order_and_stops_on_failure(tmp_path: Path, monkeypatch) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")
    calls: list[str] = []

    original_run = CathedralForge.run

    def fake_run(self: CathedralForge, goal: str):
        if goal.startswith("campaign:"):
            return original_run(self, goal)
        calls.append(goal)
        report = type("R", (), {})()
        report.schema_version = 2
        report.generated_at = "2025-01-01T00:00:00Z"
        report.goal = goal
        report.goal_id = goal
        report.goal_profile = "default"
        report.git_sha = "sha"
        report.plan_path = "glow/forge/plan_x.json"
        report.preflight = type("P", (), {"contract_drift": None, "contract_status_path": "", "contract_status_embedded": {}})()
        report.tests = type("T", (), {"status": "pass", "command": "", "summary": ""})()
        report.ci_commands_run = []
        report.session = type("S", (), {"root_path": str(tmp_path)})()
        report.step_results = []
        report.artifacts_written = []
        report.outcome = "failed" if goal == "repo_green_storm" else "success"
        report.failure_reasons = ["x"] if report.outcome == "failed" else []
        report.notes = []
        report.test_failures_before = None
        report.test_failures_after = None
        report.docket_path = None
        report.baseline_harvests = None
        report.baseline_fixes = None
        report.baseline_budget = None
        report.baseline_progress = None
        report.ci_baseline_before = None
        report.ci_baseline_after = None
        report.progress_delta = None
        return report

    monkeypatch.setattr(CathedralForge, "run", fake_run)

    campaign_report = original_run(forge, "campaign:ci_baseline_recovery")

    assert calls == ["repo_green_storm"]
    assert campaign_report.outcome == "failed"


def test_publish_blocked_when_transaction_regressed(tmp_path: Path, monkeypatch) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")

    monkeypatch.setattr("sentientos.cathedral_forge.bootstrap_env", lambda root: _fake_env(root))

    def fake_create_session(generated_at: str):
        root = tmp_path / "session"
        root.mkdir(parents=True, exist_ok=True)
        (root / "glow/contracts").mkdir(parents=True, exist_ok=True)
        (root / "glow/contracts/ci_baseline.json").write_text('{"passed": true, "failed_count": 0}', encoding="utf-8")
        (root / "glow/contracts/contract_status.json").write_text('{"contracts": []}', encoding="utf-8")
        return type("Session", (), {
            "session_id": "s1",
            "root_path": str(root),
            "strategy": "copy",
            "branch_name": "forge/s1",
            "preserved_on_failure": False,
            "cleanup_performed": False,
            "env_python_path": "",
            "env_venv_path": "",
            "env_reused": True,
            "env_install_summary": "",
            "env_cache_key": "",
        })()

    def fake_run_step(command: CommandSpec, cwd: Path) -> CommandResult:
        if command.step == "contract_status":
            (cwd / "glow/contracts/contract_status.json").write_text('{"contracts": []}', encoding="utf-8")
        if command.step == "tests":
            (cwd / "glow/contracts/ci_baseline.json").write_text('{"passed": false, "failed_count": 2}', encoding="utf-8")
        return _ok_step(command, cwd)

    called = {"publish": 0}

    def fake_publish(*args, **kwargs):
        called["publish"] += 1
        return []

    monkeypatch.setattr(forge, "_create_session", fake_create_session)
    monkeypatch.setattr(forge, "_run_step", fake_run_step)
    monkeypatch.setattr(forge, "_cleanup_session", lambda session: None)
    monkeypatch.setattr(forge, "_maybe_publish", fake_publish)

    report = forge.run("forge_self_hosting")

    assert report.outcome == "failed"
    assert report.transaction_status in {"quarantined", "rolled_back"}
    assert called["publish"] == 0


def test_canary_publish_holds_on_failed_checks(tmp_path: Path, monkeypatch) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")
    goal = resolve_goal("forge_self_hosting")
    session = forge._create_session("2025-01-01T00-00-00Z")

    monkeypatch.setenv("SENTIENTOS_FORGE_ALLOW_AUTOPUBLISH", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOPR", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_CANARY_PUBLISH", "1")
    monkeypatch.setattr("sentientos.cathedral_forge.detect_capabilities", lambda: {"gh": True, "token": False})

    from sentientos.github_checks import PRChecks, PRRef, CheckRun

    pr = PRRef(number=10, url="https://github.com/o/r/pull/10", head_sha="abc", branch="b", created_at="2026-01-01T00:00:00Z")
    monkeypatch.setattr(
        "sentientos.cathedral_forge.wait_for_pr_checks",
        lambda _ref, timeout_seconds, poll_interval_seconds: (
            PRChecks(pr=pr, checks=[CheckRun(name="ci", status="completed", conclusion="failure", details_url="u")], overall="failure"),
            {"timed_out": False, "elapsed_seconds": 1.0, "polls": 1},
        ),
    )

    notes, remote = forge._maybe_publish(goal, session, improvement_summary="ok", ci_baseline_before=None, ci_baseline_after=None, metadata={"sentinel_triggered": True})

    assert "held_failed_checks" in notes
    assert remote["checks_overall"] == "failure"
    assert list((tmp_path / "glow" / "forge").glob("quarantine_*.json"))


def test_canary_publish_records_ready_to_merge(tmp_path: Path, monkeypatch) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")
    goal = resolve_goal("forge_self_hosting")
    session = forge._create_session("2025-01-01T00-00-00Z")

    monkeypatch.setenv("SENTIENTOS_FORGE_ALLOW_AUTOPUBLISH", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOPR", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_CANARY_PUBLISH", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOMERGE", "0")
    monkeypatch.setattr("sentientos.cathedral_forge.detect_capabilities", lambda: {"gh": True, "token": False})

    from sentientos.github_checks import PRChecks, PRRef, CheckRun

    pr = PRRef(number=11, url="https://github.com/o/r/pull/11", head_sha="abc", branch="b", created_at="2026-01-01T00:00:00Z")
    monkeypatch.setattr(
        "sentientos.cathedral_forge.wait_for_pr_checks",
        lambda _ref, timeout_seconds, poll_interval_seconds: (
            PRChecks(pr=pr, checks=[CheckRun(name="ci", status="completed", conclusion="success", details_url="u")], overall="success"),
            {"timed_out": False, "elapsed_seconds": 1.0, "polls": 1},
        ),
    )

    notes, remote = forge._maybe_publish(goal, session, improvement_summary="ok", ci_baseline_before=None, ci_baseline_after=None, metadata=None)
    assert "ready_to_merge" in notes
    assert remote["checks_overall"] == "success"
