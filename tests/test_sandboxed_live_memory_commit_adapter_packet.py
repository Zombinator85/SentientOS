from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.sandboxed_live_memory_commit_adapter_packet import (
    FAIL_STATUSES,
    build_default_policy,
    evaluate_sandboxed_live_memory_commit_adapter_packet,
    validate_policy,
)

pytestmark = pytest.mark.no_legacy_skip

FIXTURES = Path("tests/fixtures/sandboxed_live_memory_commit_adapter_packet")


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_policy_is_metadata_only_default_deny() -> None:
    validation = validate_policy(build_default_policy())
    assert validation["status"] == "valid"
    policy = validation["policy"]
    assert policy["metadata_only"] is True
    assert policy["default_deny"] is True
    assert policy["real_memory_root_admission_enabled"] is False
    assert policy["live_memory_write_enabled"] is False
    assert policy["live_adapter_created"] is False


def test_ready_candidate_produces_metadata_only_adapter_record() -> None:
    result = evaluate_sandboxed_live_memory_commit_adapter_packet(load("ready_sandboxed_live_memory_commit_adapter_packet_candidate.json"))
    assert result.status == "sandboxed_live_memory_commit_adapter_packet_ready"
    assert result.packet is not None
    packet = result.packet.to_dict()
    assert packet["future_sandboxed_live_memory_commit_adapter_envelope_required"] is True
    assert packet["live_memory_write_enabled"] is False
    assert packet["live_adapter_created"] is False
    record = packet["records"][0]
    assert record["sandboxed_live_memory_commit_adapter_packet_decision"] == "sandboxed_live_memory_commit_adapter_packet_ready_for_later_sandboxed_live_memory_commit_adapter_envelope"
    assert record["real_memory_root_admission_packet_passed"] is False
    assert record["sandboxed_live_memory_commit_adapter_packet_authority_created"] is False


def test_noop_and_mixed_statuses() -> None:
    noop = evaluate_sandboxed_live_memory_commit_adapter_packet(load("noop_sandboxed_live_memory_commit_adapter_packet_candidate.json"))
    mixed = evaluate_sandboxed_live_memory_commit_adapter_packet(load("mixed_sandboxed_live_memory_commit_adapter_packet_candidate.json"))
    assert noop.status == "sandboxed_live_memory_commit_adapter_packet_noop"
    assert mixed.status == "sandboxed_live_memory_commit_adapter_packet_ready_with_warnings"


def test_expected_blocked_fixtures_fail_closed() -> None:
    for path in sorted(FIXTURES.glob("*_blocked.json")):
        result = evaluate_sandboxed_live_memory_commit_adapter_packet(load(path.name))
        assert result.status in FAIL_STATUSES, path.name
        assert result.packet is None
