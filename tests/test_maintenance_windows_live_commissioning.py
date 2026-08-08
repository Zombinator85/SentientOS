from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos import maintenance_windows_live_commissioning as commissioning

pytestmark = pytest.mark.no_legacy_skip


def test_scheduler_command_is_blocked_until_terminal_receipt(tmp_path: Path) -> None:
    result = commissioning.print_scheduler_install_command(tmp_path)
    assert result["status"] == "windows_commissioning_blocked"
    assert result["scheduler_mutation_performed"] is False


def test_completed_scheduler_command_is_digest_bound_and_never_executed(tmp_path: Path) -> None:
    command = {
        "status": "windows_deployment_ready",
        "argv": ["schtasks.exe", "/Create", "/TN", "SentientOS Maintenance Wake", "/XML", r"D:\Custody\deployment\maintenance-wake-task.xml"],
        "powershell": "& 'schtasks.exe' '/Create'",
        "executed": False,
        "scheduler_mutation_performed": False,
    }
    receipt = {
        "terminal_status": "windows_commissioning_completed",
        "scheduler_install_command": command,
        "scheduler_install_command_digest": commissioning._digest_bytes(commissioning._bytes(command)),
    }
    (tmp_path / "commissioning-receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    result = commissioning.print_scheduler_install_command(tmp_path)
    assert result["status"] == "windows_deployment_ready"
    assert result["argv"][0] == "schtasks.exe"
    assert result["executed"] is False
    assert result["scheduler_mutation_performed"] is False


def test_inspect_is_read_only_and_reports_phase_custody(tmp_path: Path) -> None:
    state = {"schema_version": commissioning.STATE_SCHEMA, "manifest_digest": "sha256:x", "completed_stages": ["canary_defect_proven"], "evidence": {}}
    path = tmp_path / "commissioning-state.json"; path.write_text(json.dumps(state), encoding="utf-8")
    before = path.read_bytes()
    result = commissioning.inspect(tmp_path)
    assert result["status"] == "windows_commissioning_inspected"
    assert result["state"]["completed_stages"] == ["canary_defect_proven"]
    assert path.read_bytes() == before
