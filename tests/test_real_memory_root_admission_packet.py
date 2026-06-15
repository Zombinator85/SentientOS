from __future__ import annotations

import json
from pathlib import Path

from sentientos.real_memory_root_admission_packet import (
    FALSE_FLAGS,
    FORBIDDEN_NEXT_STEPS,
    FUTURE_FLAGS,
    INVARIANTS,
    evaluate_real_memory_root_admission_packet,
)

FIXTURES = Path("tests/fixtures/real_memory_root_admission_packet")


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_ready_candidate_builds_metadata_only_packet_for_later_adapter() -> None:
    result = evaluate_real_memory_root_admission_packet(_fixture("ready_real_memory_root_admission_packet_candidate.json"))
    assert result.status == "real_memory_root_admission_packet_ready"
    assert result.gate is not None
    gate = result.gate.to_dict()
    for key, expected in INVARIANTS.items():
        assert gate[key] is expected
    for key, expected in FALSE_FLAGS.items():
        assert gate[key] is expected
    for key, expected in FUTURE_FLAGS.items():
        assert gate[key] is expected
    record = gate["records"][0]
    assert record["real_memory_root_admission_packet_decision"] == "real_memory_root_admission_packet_ready_for_later_sandboxed_live_memory_commit_adapter"
    assert record["final_live_memory_commit_review_gate_decision"] == "real_memory_root_admission_gate_ready_for_later_real_memory_root_admission_packet"
    assert record["future_sandboxed_live_memory_commit_adapter_required"] is True
    assert record["real_memory_root_admitted"] is False
    assert record["real_memory_root_admission_packet_created"] is False
    assert record["live_commit_execution_enabled"] is False
    assert record["real_executor_invoked"] is False
    assert record["lockfile_created"] is False
    assert "real_memory_root_admission_gate" in record["carried_evidence"]
    assert {"admit_real_memory_root_now", "create_real_memory_root_admission_packet_now", "live_memory_write_enabled", "real_executor_invoked", "lockfile_created"}.issubset(set(FORBIDDEN_NEXT_STEPS))


def test_ready_noop_mixed_and_operator_review_are_deterministic() -> None:
    expected = {
        "ready_real_memory_root_admission_packet_candidate.json": "real_memory_root_admission_packet_ready",
        "operator_review_real_memory_root_admission_packet_candidate.json": "real_memory_root_admission_packet_deferred_for_operator_review",
        "noop_real_memory_root_admission_packet_candidate.json": "real_memory_root_admission_packet_noop",
        "mixed_real_memory_root_admission_packet_candidate.json": "real_memory_root_admission_packet_ready_with_warnings",
    }
    for fixture, status in expected.items():
        first = evaluate_real_memory_root_admission_packet(_fixture(fixture)).to_dict()
        second = evaluate_real_memory_root_admission_packet(_fixture(fixture)).to_dict()
        assert first == second
        assert first["status"] == status


def test_compatibility_fixture_names_still_evaluate() -> None:
    expected = {
        "valid_ai_capsule_real_root_admission_candidate.json": "real_memory_root_admission_packet_ready",
        "noop_real_root_admission_candidate.json": "real_memory_root_admission_packet_noop",
        "mixed_real_root_admission_candidate.json": "real_memory_root_admission_packet_ready_with_warnings",
    }
    for fixture, status in expected.items():
        assert evaluate_real_memory_root_admission_packet(_fixture(fixture)).status == status


def test_blocker_fixtures_cover_final_review_and_boundary_claims() -> None:
    expected_codes = {
        "missing_final_review_gate_blocked.json": "missing_real_memory_root_admission_gate",
        "missing_candidate_blocked.json": "missing_real_memory_root_admission_packet_candidate",
        "invalid_candidate_blocked.json": "invalid_real_memory_root_admission_packet_candidate",
        "digest_mismatch_blocked.json": "real_memory_root_admission_gate_digest_mismatch",
        "decision_mismatch_blocked.json": "real_memory_root_admission_gate_decision_mismatch",
        "scope_mismatch_blocked.json": "scope_mismatch",
        "live_write_claim_blocked.json": "live_memory_write_enabled",
        "action_execution_blocked.json": "action_execution_enabled",
        "authority_smuggling_blocked.json": "real_lock_acquired",
        "admission_packet_creation_blocked.json": "real_memory_root_admission_packet_created",
    }
    for fixture, code in expected_codes.items():
        result = evaluate_real_memory_root_admission_packet(_fixture(fixture))
        assert result.status == "real_memory_root_admission_packet_blocked", fixture
        assert result.report.findings[0].code == code
        assert result.gate is None


def test_text_keeps_hard_boundary_words() -> None:
    text = Path("sentientos/real_memory_root_admission_packet.py").read_text(encoding="utf-8")
    for phrase in [
        "never admits roots",
        "never admits roots, creates an admission packet",
        "real_memory_root_admission_packet_does_not_admit_real_memory_roots",
        "real_memory_root_admission_packet_does_not_create_real_memory_root_admission_packet",
        "future_sandboxed_live_memory_commit_adapter_required",
    ]:
        assert phrase in text
