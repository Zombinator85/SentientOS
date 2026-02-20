from __future__ import annotations

from pathlib import Path
import subprocess

from scripts import reconcile_audits
from sentientos.audit_reconcile import parse_audit_drift_output, reconcile_privileged_audit
from sentientos.forge_goals.registry import resolve_goal


def test_parse_audit_drift_output_best_effort() -> None:
    result = parse_audit_drift_output("logs/privileged_audit.jsonl:12: hash mismatch")
    assert result.status == "drift"
    assert result.findings


def test_repair_mode_moves_appended_lines_into_runtime(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir(parents=True)
    baseline = logs / "privileged_audit.jsonl"
    baseline.write_text('{"timestamp":"2026-01-01T00:00:00Z","prev_hash":"0000000000000000000000000000000000000000000000000000000000000000","rolling_hash":"a","data":{"x":1}}\n', encoding="utf-8")

    # make baseline appear as an appended drift relative to HEAD
    baseline.write_text(
        baseline.read_text(encoding="utf-8") + '{"timestamp":"2026-01-02T00:00:00Z","prev_hash":"a","rolling_hash":"b","data":{"x":2},"tool":"tester"}\n',
        encoding="utf-8",
    )

    result = reconcile_privileged_audit(tmp_path, mode="repair")
    assert result.status in {"repaired", "needs_decision"}


def test_check_mode_emits_docket_on_drift(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    (tmp_path / "logs").mkdir(parents=True)
    (tmp_path / "logs/privileged_audit.jsonl").write_text('{"timestamp":"2026-01-01T00:00:00Z","rolling_hash":"a","data":{"x":1}}\n', encoding="utf-8")

    class Done:
        def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    monkeypatch.setattr(
        "scripts.reconcile_audits.subprocess.run",
        lambda *args, **kwargs: Done(1, stdout="logs/privileged_audit.jsonl:1: hash mismatch"),
    )

    rc = reconcile_audits.main(["--check"])
    assert rc == 1
    dockets = list((tmp_path / "glow/forge").glob("audit_docket_*.json"))
    assert dockets


def test_accept_mode_requires_env_flag(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    (tmp_path / "logs").mkdir(parents=True)
    (tmp_path / "logs/privileged_audit.jsonl").write_text('{"timestamp":"2026-01-01T00:00:00Z","rolling_hash":"a","data":{"x":1}}\n', encoding="utf-8")
    monkeypatch.delenv("SENTIENTOS_AUDIT_ACCEPT_DRIFT", raising=False)
    rc = reconcile_audits.main(["--accept-drift"])
    assert rc == 2


def test_stability_repair_runs_audit_repair_gate() -> None:
    spec = resolve_goal("stability_repair")
    commands = [item.command for item in spec.apply_commands]
    assert "make audit-repair" in commands


def test_repair_uses_doctor_and_recovers_runtime(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "logs").mkdir(parents=True)
    (tmp_path / "pulse" / "audit").mkdir(parents=True)
    baseline = tmp_path / "logs" / "privileged_audit.jsonl"
    baseline.write_text("", encoding="utf-8")
    runtime = tmp_path / "pulse" / "audit" / "privileged_audit.runtime.jsonl"
    runtime.write_text('{"timestamp":"2026-01-01T00:00:00Z","data":\n', encoding="utf-8")

    subprocess.run(["git", "init"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "audit@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Audit Bot"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "logs/privileged_audit.jsonl"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=tmp_path, check=True)

    monkeypatch.setenv("SENTIENTOS_AUDIT_BASELINE_PATH", str(baseline))
    monkeypatch.setenv("SENTIENTOS_AUDIT_RUNTIME_DIR", str(tmp_path / "pulse" / "audit"))
    rc = reconcile_audits.main(["--repair"])
    assert rc == 0
    assert list((tmp_path / "glow" / "forge").glob("audit_doctor_*.json"))


def test_append_only_baseline_drift_moves_lines_to_runtime(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    runtime_dir = tmp_path / "pulse" / "audit"
    logs.mkdir(parents=True)
    runtime_dir.mkdir(parents=True)
    baseline = logs / "privileged_audit.jsonl"
    head_line = '{"timestamp":"2026-01-01T00:00:00Z","prev_hash":"0000000000000000000000000000000000000000000000000000000000000000","rolling_hash":"a","data":{"x":1}}\n'
    baseline.write_text(head_line, encoding="utf-8")

    subprocess.run(["git", "init"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "audit@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Audit Bot"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "logs/privileged_audit.jsonl"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=tmp_path, check=True)

    appended = '{"timestamp":"2026-01-02T00:00:00Z","prev_hash":"a","rolling_hash":"b","data":{"x":2}}\n'
    baseline.write_text(head_line + appended, encoding="utf-8")

    result = reconcile_privileged_audit(tmp_path, mode="repair")
    assert result.status == "repaired"
    runtime = runtime_dir / "privileged_audit.runtime.jsonl"
    assert appended.strip() in runtime.read_text(encoding="utf-8")
    assert baseline.read_text(encoding="utf-8") == head_line
