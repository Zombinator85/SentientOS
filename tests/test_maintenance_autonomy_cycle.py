from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos import maintenance_autonomy_cycle as cycle


def test_configuration_rejects_wider_cycle_bounds(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported_bound"):
        cycle.validate_config({"maximum_collector_invocations_per_cycle": 2})


def test_print_run_command_is_structured_argv(tmp_path: Path) -> None:
    result = cycle.print_run_command(tmp_path / "cycle.json", evaluation_time="2030-01-01T00:00:00Z")
    assert result["status"] == "run_command_ready"
    assert result["argv"][-1] == "cycle-once"
    assert result["shell"] is False
    assert result["scheduler_installation"] is False


def test_receipt_inspection_fails_closed_on_tampering(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    journal = tmp_path / "receipts.jsonl"
    journal.write_text(json.dumps({"schema_version": cycle.RECEIPT_SCHEMA, "sequence": 1,
        "predecessor_receipt_digest": cycle.ZERO_DIGEST, "receipt_digest": "sha256:bad"}) + "\n")
    monkeypatch.setattr(cycle, "validate_config", lambda value: dict(value))
    result = cycle.inspect_receipts({"cycle_receipt_journal_path": str(journal)})
    assert result["status"] == "receipts_blocked"
