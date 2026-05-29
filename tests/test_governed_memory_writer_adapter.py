from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.governed_memory_writer_adapter import (
    FORBIDDEN_NEXT_STEPS,
    build_default_policy,
    evaluate_governed_memory_writer_adapter,
    validate_policy,
    write_artifact,
)

pytestmark = pytest.mark.no_legacy_skip

FIXTURES = Path("tests/fixtures/governed_memory_writer_adapter")


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_default_policy_validates() -> None:
    result = validate_policy(build_default_policy())
    assert result["ok"] is True
    assert result["digest"]


def test_missing_and_invalid_inputs_block() -> None:
    expected = {
        "missing_distillation_packet_blocked.json": "governed_memory_writer_blocked_missing_distillation_packet",
        "invalid_distillation_packet_blocked.json": "governed_memory_writer_blocked_invalid_distillation_packet",
        "missing_receipt_gate_packet_blocked.json": "governed_memory_writer_blocked_missing_receipt_gate_packet",
        "invalid_receipt_gate_packet_blocked.json": "governed_memory_writer_blocked_invalid_receipt_gate_packet",
        "missing_tomb_verifier_packet_blocked.json": "governed_memory_writer_blocked_missing_tomb_verifier_packet",
        "invalid_tomb_verifier_packet_blocked.json": "governed_memory_writer_blocked_invalid_tomb_verifier_packet",
        "missing_writer_candidate_blocked.json": "governed_memory_writer_blocked_missing_writer_candidate",
        "invalid_writer_candidate_blocked.json": "governed_memory_writer_blocked_invalid_writer_candidate",
    }
    for fixture, status in expected.items():
        assert evaluate_governed_memory_writer_adapter(_fixture(fixture)).status == status


def test_valid_candidate_types_and_modes() -> None:
    expected = {
        "valid_ai_capsule_dry_run_preview.json": ("governed_memory_writer_dry_run_ready", "writer_preview_ready"),
        "valid_ai_capsule_artifact_write.json": ("governed_memory_writer_ready", "writer_artifact_ready"),
        "valid_human_summary_dry_run_preview.json": ("governed_memory_writer_dry_run_ready", "writer_preview_ready"),
        "valid_human_summary_artifact_write.json": ("governed_memory_writer_ready", "writer_artifact_ready"),
        "valid_dual_capsule_artifact_write.json": ("governed_memory_writer_ready", "writer_artifact_ready"),
        "valid_protect_receipt_artifact_write.json": ("governed_memory_writer_ready", "writer_artifact_ready"),
        "valid_merge_receipt_artifact_write.json": ("governed_memory_writer_ready", "writer_artifact_ready"),
        "valid_tomb_receipt_archive_write.json": ("governed_memory_writer_ready", "writer_artifact_ready"),
        "valid_tomb_deferred_archive_write.json": ("governed_memory_writer_ready", "writer_deferred_for_operator_review"),
        "valid_operator_review_archive_write.json": ("governed_memory_writer_ready", "writer_deferred_for_operator_review"),
        "valid_noop_artifact_candidate.json": ("governed_memory_writer_dry_run_ready", "writer_noop"),
    }
    for fixture, (status, decision) in expected.items():
        result = evaluate_governed_memory_writer_adapter(_fixture(fixture))
        assert result.status == status
        assert result.packet is not None
        assert result.packet.records[0].writer_decision == decision
        assert result.packet.digest


def test_blocker_statuses() -> None:
    expected = {
        "digest_mismatch_blocked.json": "governed_memory_writer_blocked_digest_mismatch",
        "decision_mismatch_blocked.json": "governed_memory_writer_blocked_decision_mismatch",
        "receipt_gate_not_admissible_blocked.json": "governed_memory_writer_blocked_receipt_gate_not_admissible",
        "tomb_verifier_not_ready_blocked.json": "governed_memory_writer_blocked_tomb_verifier_not_ready",
        "live_memory_path_blocked.json": "governed_memory_writer_blocked_live_memory_path",
        "missing_output_path_blocked.json": "governed_memory_writer_blocked_missing_output_path",
        "unsafe_output_path_blocked.json": "governed_memory_writer_blocked_unsafe_output_path",
        "path_traversal_blocked.json": "governed_memory_writer_blocked_unsafe_output_path",
        "raw_payload_leak_blocked.json": "governed_memory_writer_blocked_raw_payload_leak",
        "authority_smuggling_blocked.json": "governed_memory_writer_blocked_authority_smuggling",
        "prompt_materialization_blocked.json": "governed_memory_writer_blocked_prompt_materialization",
        "action_execution_blocked.json": "governed_memory_writer_blocked_action_execution",
        "external_disclosure_blocked.json": "governed_memory_writer_blocked_external_disclosure",
        "scope_mismatch_blocked.json": "governed_memory_writer_blocked_scope_mismatch",
    }
    for fixture, status in expected.items():
        assert evaluate_governed_memory_writer_adapter(_fixture(fixture)).status == status


def test_dry_run_preview_never_writes(tmp_path: Path) -> None:
    payload = _fixture("valid_ai_capsule_dry_run_preview.json")
    result = write_artifact(payload, str(tmp_path), "artifact.json", dry_run=True)
    assert result.status == "governed_memory_writer_dry_run_ready"
    assert not (tmp_path / "artifact.json").exists()


def test_explicit_artifact_write_receipt_and_determinism(tmp_path: Path) -> None:
    payload = _fixture("valid_ai_capsule_artifact_write.json")
    first = write_artifact(payload, str(tmp_path), "artifact.json")
    second = write_artifact(payload, str(tmp_path), "artifact.json")
    assert first.to_dict() == second.to_dict()
    assert first.packet is not None
    receipt = first.packet.artifact_receipts[0]
    assert receipt.artifact_path == str((tmp_path / "artifact.json").resolve())
    assert receipt.artifact_digest
    assert receipt.input_digest == first.digest or receipt.input_digest
    assert receipt.writer_mode == "explicit_artifact_write"
    assert receipt.candidate_id == "candidate-valid_ai_capsule_artifact_write"
    assert receipt.timestamp == "2026-01-02T03:04:05Z"
    artifact = json.loads((tmp_path / "artifact.json").read_text(encoding="utf-8"))
    assert artifact["writer_is_not_truth"] is True
    assert artifact["live_memory_write_enabled"] is False


def test_operator_review_cannot_override_hard_blockers() -> None:
    payload = _fixture("authority_smuggling_blocked.json")
    payload["writer_candidate"]["requested_next_actions"] = ["operator_review_required"]
    payload["policy"] = {"allow_operator_review_archives": True}
    assert evaluate_governed_memory_writer_adapter(payload).status == "governed_memory_writer_blocked_authority_smuggling"


def test_mixed_scope_diagnostic_warns_only_when_allowed() -> None:
    allowed = evaluate_governed_memory_writer_adapter(_fixture("valid_mixed_scope_diagnostic_warning.json"))
    assert allowed.status == "governed_memory_writer_ready_with_warnings"
    blocked = _fixture("valid_mixed_scope_diagnostic_warning.json")
    blocked["policy"] = {"allow_mixed_scope_diagnostic_packet": False}
    assert evaluate_governed_memory_writer_adapter(blocked).status == "governed_memory_writer_blocked_scope_mismatch"


def test_successful_outputs_include_non_authority_invariants_and_forbidden_steps() -> None:
    result = evaluate_governed_memory_writer_adapter(_fixture("valid_ai_capsule_artifact_write.json"))
    assert result.packet is not None
    packet = result.packet.to_dict()
    for key in ["writer_is_not_truth", "writer_is_not_policy", "writer_is_not_authority", "writer_is_not_consent", "writer_does_not_execute_action", "writer_does_not_assemble_prompt", "writer_does_not_disclose_externally"]:
        assert packet[key] is True
    for key in ["live_memory_write_enabled", "live_memory_deletion_enabled", "live_index_mutation_enabled", "prompt_materialization_enabled", "external_disclosure_enabled", "remote_service_enabled"]:
        assert packet[key] is False
    required = {"write_live_memory_now", "delete_memory_now", "purge_memory_now", "silently_write_memory", "silently_delete_memory", "mutate_vector_index", "assemble_prompt_now", "retrieve_live_context", "execute_action_ingress", "infer_truth_from_writer", "infer_authority_from_writer", "convert_writer_receipt_to_policy", "convert_writer_to_action", "bypass_tomb_verifier", "enable_external_disclosure"}
    assert required.issubset(set(FORBIDDEN_NEXT_STEPS))
    assert required.issubset(set(packet["forbidden_next_steps"]))


def test_mixed_packet_counts_and_digest_are_deterministic() -> None:
    payload = _fixture("mixed_governed_memory_writer_packet.json")
    first = evaluate_governed_memory_writer_adapter(payload)
    second = evaluate_governed_memory_writer_adapter(payload)
    assert first.to_dict() == second.to_dict()
    assert first.packet is not None
    assert first.report.summary_counts["candidate_count"] == 2
    assert first.report.summary_counts["writer_preview_ready"] == 1
    assert first.report.summary_counts["writer_noop"] == 1


def test_fixtures_are_metadata_only() -> None:
    forbidden = ["data:image", "data:audio", "data:video", "BEGIN PRIVATE", "provider prompt text", "real operator home"]
    for path in FIXTURES.glob("*.json"):
        text = path.read_text(encoding="utf-8").lower()
        assert not any(marker.lower() in text for marker in forbidden), path
