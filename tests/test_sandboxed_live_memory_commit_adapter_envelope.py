from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.sandboxed_live_memory_commit_adapter_envelope import (
    FAIL_STATUSES,
    build_default_policy,
    evaluate_sandboxed_live_memory_commit_adapter_envelope,
    validate_policy,
)

pytestmark = pytest.mark.no_legacy_skip

FIXTURES = Path("tests/fixtures/sandboxed_live_memory_commit_adapter_envelope")


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
    result = evaluate_sandboxed_live_memory_commit_adapter_envelope(load("ready_sandboxed_live_memory_commit_adapter_envelope_candidate.json"))
    assert result.status == "sandboxed_live_memory_commit_adapter_envelope_ready"
    assert result.envelope is not None
    envelope = result.envelope.to_dict()
    assert envelope["future_sandboxed_live_memory_commit_adapter_readiness_gate_required"] is True
    assert envelope["live_memory_write_enabled"] is False
    assert envelope["live_adapter_created"] is False
    record = envelope["records"][0]
    assert record["sandboxed_live_memory_commit_adapter_envelope_decision"] == "sandboxed_live_memory_commit_adapter_envelope_ready_for_later_sandboxed_live_memory_commit_adapter_readiness_gate"
    assert record["real_memory_root_admission_packet_passed"] is False
    assert record["sandboxed_live_memory_commit_adapter_envelope_authority_created"] is False


def test_noop_and_mixed_statuses() -> None:
    noop = evaluate_sandboxed_live_memory_commit_adapter_envelope(load("noop_sandboxed_live_memory_commit_adapter_envelope_candidate.json"))
    mixed = evaluate_sandboxed_live_memory_commit_adapter_envelope(load("mixed_sandboxed_live_memory_commit_adapter_envelope_candidate.json"))
    assert noop.status == "sandboxed_live_memory_commit_adapter_envelope_noop"
    assert mixed.status == "sandboxed_live_memory_commit_adapter_envelope_ready_with_warnings"


def test_expected_blocked_fixtures_fail_closed() -> None:
    for path in sorted(FIXTURES.glob("*_blocked.json")):
        result = evaluate_sandboxed_live_memory_commit_adapter_envelope(load(path.name))
        assert result.status in FAIL_STATUSES, path.name
        assert result.envelope is None
