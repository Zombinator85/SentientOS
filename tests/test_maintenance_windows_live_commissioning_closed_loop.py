from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos import maintenance_windows_live_commissioning as commissioning

pytestmark = pytest.mark.no_legacy_skip


@pytest.mark.parametrize("crash_stage", ["canary_defect_proven", "wake_returned"])
def test_recovery_custody_is_reconcilable_without_duplicate_terminal_effects(tmp_path: Path, crash_stage: str) -> None:
    """A sealed terminal receipt is the idempotency boundary after either crash window."""
    command = {"status": "windows_deployment_ready", "argv": ["schtasks.exe", "/Create"], "powershell": "& 'schtasks.exe' '/Create'", "executed": False, "scheduler_mutation_performed": False}
    body = {"schema_version": commissioning.RECEIPT_SCHEMA, "sequence": 1,
            "predecessor_receipt_digest": commissioning.ZERO_DIGEST,
            "crash_reconciled_after": crash_stage, "scheduler_install_command": command,
            "scheduler_install_command_digest": commissioning._digest_bytes(commissioning._bytes(command)),
            "scheduler_mutation_performed": False, "credentials_inspected": False,
            "terminal_status": commissioning.STATUS_COMPLETED}
    receipt = dict(body); receipt["receipt_digest"] = "sha256:terminal"
    (tmp_path / "commissioning-receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    first = commissioning.print_scheduler_install_command(tmp_path)
    second = commissioning.print_scheduler_install_command(tmp_path)
    assert first == second
    assert first["executed"] is False
    assert len(list(tmp_path.glob("commissioning-receipt.json"))) == 1


def test_cli_exposes_only_bounded_commissioning_commands() -> None:
    source = (Path(__file__).parents[1] / "scripts" / "maintenance_windows_live_commissioning.py").read_text(encoding="utf-8")
    assert 'sub.add_parser("doctor")' in source
    assert 'sub.add_parser("commission-once")' in source
    assert '("inspect", "print-scheduler-install-command")' in source
    assert "install-scheduler" not in source
