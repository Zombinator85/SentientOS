from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.real_executor_invocation_gate import (  # noqa: E402
    EVIDENCE_MATCH_FIELDS,
    INVARIANTS,
    NON_NOOP_METADATA_FIELDS,
    RealExecutorInvocationGatePolicy,
    evaluate_real_executor_invocation_gate,
    validate_policy,
)

FIXTURE_ROOT = Path("tests/fixtures/real_executor_invocation_gate")
READY_FIXTURE = FIXTURE_ROOT / "ready_real_executor_invocation_gate_candidate.json"
NOOP_FIXTURE = FIXTURE_ROOT / "noop_real_executor_invocation_gate_candidate.json"
MIXED_FIXTURE = FIXTURE_ROOT / "mixed_real_executor_invocation_gate_candidate.json"


def load_ready() -> dict[str, object]:
    return json.loads(READY_FIXTURE.read_text(encoding="utf-8"))


def candidate(payload: dict[str, object]) -> dict[str, object]:
    return payload["real_executor_invocation_gate_candidates"][0]  # type: ignore[index,return-value]


def assert_blocked(payload: dict[str, object], code: str) -> None:
    result = evaluate_real_executor_invocation_gate(payload)
    assert result.status == "real_executor_invocation_gate_blocked"
    assert any(f.code == code for f in result.report.findings)


def test_ready_gate_is_deterministic_metadata_only_and_default_deny() -> None:
    payload = load_ready()
    before = copy.deepcopy(payload)
    first = evaluate_real_executor_invocation_gate(payload)
    second = evaluate_real_executor_invocation_gate(copy.deepcopy(payload))
    assert payload == before
    assert first.to_dict() == second.to_dict()
    assert first.status == "real_executor_invocation_gate_ready"
    assert first.packet is not None
    packet = first.packet.to_dict()
    for key, expected in INVARIANTS.items():
        assert packet[key] is expected
    record = packet["records"][0]
    assert record["real_executor_invocation_gate_decision"] == "real_executor_invocation_gate_ready_for_later_real_executor_run_packet"
    assert record["real_executor_invocation_enabled"] is False
    assert record["live_commit_executed"] is False
    assert record["lockfile_created"] is False
    assert record["future_real_executor_run_packet_required"] is True
    assert record["guarded_invocation_confirmation_records"][0]["metadata_only"] is True
    assert record["invocation_authority_denial_records"][0]["permission_granted"] is False
    assert record["final_invocation_hold_point_records"][0]["executed"] is False


def test_validate_policy_blocks_runtime_authority() -> None:
    assert validate_policy()["status"] == "valid"
    invalid = validate_policy(RealExecutorInvocationGatePolicy(real_executor_invocation_enabled=True))
    assert invalid["status"] == "invalid"
    assert invalid["findings"][0]["code"] == "real_executor_invocation_enabled"


@pytest.mark.parametrize(("label", "digest_field", "_record_digest", "decision_field"), EVIDENCE_MATCH_FIELDS)
def test_digest_mismatch_blocks(label: str, digest_field: str, _record_digest: str, decision_field: str) -> None:
    payload = load_ready()
    candidate(payload)[digest_field] = "sha256:mismatch"
    assert_blocked(payload, f"{label}_digest_mismatch")
    payload = load_ready()
    candidate(payload)[decision_field] = "mismatch_decision"
    assert_blocked(payload, f"{label}_decision_mismatch")


@pytest.mark.parametrize("field", NON_NOOP_METADATA_FIELDS)
def test_missing_required_non_noop_metadata_blocks(field: str) -> None:
    payload = load_ready()
    candidate(payload).pop(field)
    assert_blocked(payload, f"missing_{field}")


def test_scope_mismatch_blocks() -> None:
    payload = load_ready()
    candidate(payload)["operator_scope_keys"] = ["other"]
    assert_blocked(payload, "scope_mismatch")


def test_noop_behavior_is_deterministic_and_non_mutating() -> None:
    payload = json.loads(NOOP_FIXTURE.read_text(encoding="utf-8"))
    before = copy.deepcopy(payload)
    first = evaluate_real_executor_invocation_gate(payload)
    second = evaluate_real_executor_invocation_gate(copy.deepcopy(payload))
    assert payload == before
    assert first.to_dict() == second.to_dict()
    assert first.status == "real_executor_invocation_gate_noop"
    assert first.packet is not None
    assert first.packet.records[0].real_executor_invocation_gate_decision == "real_executor_invocation_gate_noop"


def test_mixed_diagnostics_warn_only_when_policy_allows() -> None:
    payload = json.loads(MIXED_FIXTURE.read_text(encoding="utf-8"))
    result = evaluate_real_executor_invocation_gate(payload)
    assert result.status == "real_executor_invocation_gate_ready_with_warnings"
    assert any(f.code == "mixed_scope_diagnostic" for f in result.report.findings)


FORBIDDEN_CLAIMS = [
    ("real_executor_invocation_gate_invoked", "real_executor_invocation_gate_claim"),
    ("runtime_enablement_claimed", "runtime_enablement_claim"),
    ("runtime_flags_flipped", "runtime_flag_flipping_claim"),
    ("executor_enabled", "executor_enablement_claim"),
    ("executor_invoked", "executor_invocation_claim"),
    ("executor_activated", "executor_activation_claim"),
    ("live_commit_executed", "live_execution_claim"),
    ("permission_to_execute_now", "executor_permission_claim"),
    ("live_memory_write_claimed", "live_write_claim"),
    ("lockfile_creation_claimed", "lockfile_creation_claim"),
    ("real_lock_acquisition_claimed", "real_lock_acquisition_claim"),
    ("external_service_called", "external_service_call"),
    ("authority_granted", "authority_smuggling"),
    ("consent_granted", "consent_smuggling"),
    ("policy_created", "policy_smuggling"),
    ("truth_asserted", "truth_smuggling"),
]


@pytest.mark.parametrize(("claim", "code"), FORBIDDEN_CLAIMS)
def test_forbidden_claims_block(claim: str, code: str) -> None:
    payload = load_ready()
    candidate(payload)["real_executor_invocation_gate_claims"] = {claim: True}
    assert_blocked(payload, code)
