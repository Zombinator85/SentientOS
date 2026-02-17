from __future__ import annotations

import json
from pathlib import Path

from sentientos.cathedral_forge import CathedralForge
from sentientos.forge_goals import resolve_goal
from sentientos.forge_model import CommandResult, CommandSpec


def test_goal_registry_resolution() -> None:
    baseline = resolve_goal("baseline_reclamation")
    assert baseline.goal_id == "baseline_reclamation"
    assert baseline.apply_commands

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

    def fake_run_step(command: CommandSpec, cwd: Path) -> CommandResult:
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


def test_docket_emission_on_choice_point(tmp_path: Path, monkeypatch) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")

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
        stdout = ""
        if command.step == "inventory_failures":
            stdout = "CHOICE_POINT: ambiguous fix required"
        return CommandResult(
            step=command.step,
            argv=command.argv,
            cwd=str(cwd),
            env_overlay={},
            timeout_seconds=command.timeout_seconds,
            returncode=0,
            stdout=stdout,
            stderr="",
        )

    monkeypatch.setattr(forge, "_create_session", fake_create_session)
    monkeypatch.setattr(forge, "_run_step", fake_run_step)
    monkeypatch.setattr(forge, "_cleanup_session", lambda session: None)

    report = forge.run("baseline_reclamation")

    assert report.docket_path is not None
    docket_path = Path(report.docket_path)
    assert docket_path.exists()
    payload = json.loads(docket_path.read_text(encoding="utf-8"))
    assert payload["choices"]


def test_run_smoke_profile_still_works(tmp_path: Path, monkeypatch) -> None:
    forge = CathedralForge(repo_root=tmp_path, forge_dir=tmp_path / "glow" / "forge")

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
