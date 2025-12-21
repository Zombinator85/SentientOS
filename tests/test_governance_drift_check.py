from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_governance_drift import main


def test_governance_drift_requires_ack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    critical = tmp_path / "task_admission.py"
    checklist = tmp_path / "docs" / "governance_claims_checklist.md"
    state = tmp_path / ".governance_drift_state.json"

    checklist.parent.mkdir(parents=True, exist_ok=True)
    critical.write_text("original", encoding="utf-8")
    checklist.write_text("checklist", encoding="utf-8")
    state.write_text(json.dumps({}, indent=2), encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    # First run seeds the state
    assert main([]) == 0

    # Change critical file without updating checklist or ack
    critical.write_text("modified", encoding="utf-8")
    assert main([]) == 1

    # Update checklist and acknowledge drift
    checklist.write_text("updated", encoding="utf-8")
    assert main(["--ack-governance-drift"]) == 0
