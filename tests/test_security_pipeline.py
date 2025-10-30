from __future__ import annotations

from pathlib import Path

from security.threat_model import build_threat_model
from security.commit_scanner import scan_repository
from security.validation_harness import ValidationHarness
from security_guardian import run_security_guardian


def test_threat_model_parses_agents() -> None:
    model = build_threat_model()
    assert model.agents, "Expected at least one agent in threat model"


def test_commit_scanner_detects_shell_usage(tmp_path: Path) -> None:
    specimen = tmp_path / "specimen.py"
    specimen.write_text(
        "import subprocess\n"
        "def run(cmd):\n"
        "    return subprocess.run(cmd, shell=True)\n",
        encoding="utf-8",
    )
    model = build_threat_model()
    findings = scan_repository(tmp_path, model, changed_only=False)
    assert any(f.pattern == "subprocess.run" for f in findings)
    harness = ValidationHarness(tmp_path)
    results = harness.validate(findings)
    assert any(r.status == "confirmed" for r in results)


def test_run_security_guardian_summary_fields(tmp_path: Path, monkeypatch) -> None:
    def fake_scan_repository(repo_root, threat_model, changed_only=True):  # type: ignore[override]
        return []

    monkeypatch.setattr("security_guardian.scan_repository", fake_scan_repository)
    summary = run_security_guardian(full_scan=False, write_threat_model=False, validate=False)
    assert "finding_count" in summary
    assert "max_agent_risk" in summary
