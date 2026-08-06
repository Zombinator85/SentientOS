from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos import maintenance_candidate_collector as collector
from sentientos import work_item_intake

pytestmark = pytest.mark.no_legacy_skip


def test_normalized_packet_validator_uses_exact_production_packet() -> None:
    packet, _ = work_item_intake.normalize_work_item_intake({
        "source_kind": "generic_issue", "source_ref": "issue:1", "title": "Repair collector",
        "description": "Repair the bounded collector", "requested_outcome": "Collector passes",
        "acceptance_criteria": ["focused test passes"], "declared_constraints": ["no network"],
        "declared_authority_requests": ["filesystem_write"], "declared_targets": ["sentientos/a.py"],
        "declared_tests": ["tests/test_a.py"],
    })
    payload = work_item_intake.summarize_work_item_packet(packet) | {"schema_version": collector.NORMALIZED_WORK_ITEM_SCHEMA}
    assert collector._work_packet(payload) == packet
    with pytest.raises(ValueError, match="closed_schema"):
        collector._work_packet(payload | {"objective": "invented"})


def test_print_run_command_is_argv_only() -> None:
    value = collector.print_run_command("/tmp/config.json", evaluation_time="2030-01-01T00:00:00Z")
    assert value["argv"][-1] == "collect-once"
    assert value["scheduler_installation"] is value["watchdog_invocation"] is False
    assert all(isinstance(part, str) for part in value["argv"])


def test_receipt_chain_tampering_and_truncation_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = tmp_path / "state"; inbox = tmp_path / "inbox"; state.mkdir(mode=0o700); inbox.mkdir()
    cfg = {"receipt_journal_path": str(state / "receipts.jsonl"), "maintenance_candidate_inbox": str(inbox)}
    monkeypatch.setattr(collector, "validate_config", lambda _: cfg)
    receipt = state / "receipts.jsonl"; receipt.write_bytes(b'{"bad":true}\n')
    assert collector.inspect_receipts({})["status"] == "receipts_blocked"
    receipt.write_bytes(b'{"partial":')
    assert collector.inspect_receipts({})["status"] == "receipts_blocked"
