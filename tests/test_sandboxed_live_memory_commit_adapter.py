from __future__ import annotations

import json
from pathlib import Path

from sentientos.sandboxed_live_memory_commit_adapter import (
    FORBIDDEN_NEXT_STEPS,
    NON_AUTHORITY_STATEMENTS,
    build_receipt_manifest,
    build_rollback_manifest,
    evaluate_sandboxed_live_memory_commit_adapter,
    write_sandbox_artifacts,
)

FIXTURES = Path("tests/fixtures/sandboxed_live_memory_commit_adapter")


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_valid_candidate_builds_sandbox_only_packet() -> None:
    result = evaluate_sandboxed_live_memory_commit_adapter(_fixture("valid_ai_capsule_sandbox_commit_candidate.json"))
    assert result.status == "sandbox_commit_artifacts_ready"
    assert result.packet is not None
    packet = result.packet.to_dict()
    assert packet["sandbox_only"] is True
    for key in [
        "sandbox_commit_is_not_real_memory_write",
        "sandbox_commit_is_not_memory_deletion",
        "sandbox_commit_is_not_memory_purge",
        "sandbox_commit_is_not_index_mutation",
        "sandbox_commit_is_not_policy",
        "sandbox_commit_is_not_truth",
        "sandbox_commit_is_not_consent",
        "sandbox_commit_is_not_authority",
        "sandbox_commit_is_not_prompt_assembly",
        "sandbox_commit_is_not_action_execution",
        "sandbox_commit_is_not_external_disclosure",
        "future_real_live_memory_adapter_required",
        "future_real_memory_root_admission_required",
    ]:
        assert packet[key] is True
    for key in ["live_memory_write_enabled", "live_memory_delete_enabled", "live_memory_purge_enabled", "live_index_mutation_enabled", "prompt_materialization_enabled", "action_execution_enabled", "external_disclosure_enabled"]:
        assert packet[key] is False
    assert set(NON_AUTHORITY_STATEMENTS).issubset(set(packet["non_authority_statements"]))
    assert {"write_live_memory_now", "delete_live_memory_now", "purge_live_memory_now", "mutate_live_index", "assemble_prompt_now", "retrieve_live_context", "execute_action_ingress", "bypass_safety_interlock", "enable_external_disclosure"}.issubset(set(FORBIDDEN_NEXT_STEPS))


def test_expected_decision_fixtures() -> None:
    expected = {
        "valid_ai_capsule_sandbox_commit_candidate.json": "sandbox_commit_artifacts_ready",
        "warning_sandbox_commit_candidate.json": "sandbox_commit_artifacts_ready_with_warnings",
        "operator_review_sandbox_commit_candidate.json": "sandbox_commit_deferred_for_operator_review",
        "rejected_sandbox_commit_candidate.json": "sandbox_commit_rejected",
        "noop_sandbox_commit_candidate.json": "sandbox_commit_noop",
    }
    for fixture, status in expected.items():
        assert evaluate_sandboxed_live_memory_commit_adapter(_fixture(fixture)).status == status


def test_blocker_fixtures_cover_safety_boundary_and_smuggling() -> None:
    expected_codes = {
        "missing_safety_interlock_blocked.json": "missing_safety_interlock_packet",
        "invalid_safety_interlock_blocked.json": "invalid_safety_interlock_packet",
        "missing_candidate_blocked.json": "missing_sandbox_commit_candidate",
        "digest_mismatch_blocked.json": "safety_interlock_digest_mismatch",
        "decision_mismatch_blocked.json": "safety_interlock_decision_mismatch",
        "scope_mismatch_blocked.json": "scope_mismatch",
        "path_traversal_blocked.json": "path_traversal",
        "real_memory_root_claim_blocked.json": "real_memory_root_claim",
        "live_write_claim_blocked.json": "live_write_claim",
        "live_delete_claim_blocked.json": "live_delete_claim",
        "live_purge_claim_blocked.json": "live_purge_claim",
        "index_mutation_claim_blocked.json": "index_mutation_claim",
        "prompt_materialization_blocked.json": "prompt_materialization",
        "action_execution_blocked.json": "action_execution",
        "external_disclosure_blocked.json": "external_disclosure",
        "authority_smuggling_blocked.json": "authority_smuggling",
        "consent_smuggling_blocked.json": "consent_smuggling",
        "policy_smuggling_blocked.json": "policy_smuggling",
        "truth_smuggling_blocked.json": "truth_smuggling",
        "raw_payload_leak_blocked.json": "raw_payload_leak",
    }
    for fixture, code in expected_codes.items():
        result = evaluate_sandboxed_live_memory_commit_adapter(_fixture(fixture))
        assert result.status == "sandbox_commit_blocked", fixture
        assert result.report.findings[0].code == code
        assert result.packet is None


def test_evaluate_mode_is_deterministic_and_non_mutating(tmp_path: Path) -> None:
    payload = _fixture("valid_ai_capsule_sandbox_commit_candidate.json")
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    first = evaluate_sandboxed_live_memory_commit_adapter(payload).to_dict()
    second = evaluate_sandboxed_live_memory_commit_adapter(payload).to_dict()
    after = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    assert first == second
    assert before == after == []


def test_write_sandbox_artifacts_confined_to_sandbox_root_and_deterministic(tmp_path: Path) -> None:
    payload = _fixture("valid_ai_capsule_sandbox_commit_candidate.json")
    outside = tmp_path / "outside"
    root = tmp_path / "sandbox"
    outside.mkdir()
    first = write_sandbox_artifacts(payload, root)
    second = write_sandbox_artifacts(payload, root)
    assert first["status"] == "sandbox_commit_artifacts_ready"
    assert first == second
    written = [Path(p) for p in first["written_files"]]
    assert written
    assert all(root.resolve() in (p.resolve(), *p.resolve().parents) for p in written)
    assert list(outside.rglob("*")) == []
    receipt = json.loads((root / "sandbox_receipt_manifest.json").read_text(encoding="utf-8"))
    rollback = json.loads((root / "sandbox_rollback_manifest.json").read_text(encoding="utf-8"))
    assert receipt["manifest_kind"] == "sandbox_live_memory_commit_receipt_manifest"
    assert rollback["manifest_kind"] == "sandbox_live_memory_commit_rollback_manifest"
    assert receipt["sandbox_only"] is True
    assert rollback["records"][0]["live_memory_was_mutated"] is False


def test_write_sandbox_artifacts_blocks_unsafe_roots_and_traversal(tmp_path: Path) -> None:
    payload = _fixture("valid_ai_capsule_sandbox_commit_candidate.json")
    blocked = write_sandbox_artifacts(_fixture("path_traversal_blocked.json"), tmp_path / "sandbox")
    assert blocked["status"] == "sandbox_commit_blocked"
    assert blocked["written_files"] == []
    for unsafe in [tmp_path / "live_memory", tmp_path / "real_memory"]:
        try:
            write_sandbox_artifacts(payload, unsafe)
        except ValueError as exc:
            assert str(exc) == "unsafe_sandbox_root"
        else:
            raise AssertionError("unsafe sandbox root was accepted")


def test_noop_is_deterministic_and_non_mutating(tmp_path: Path) -> None:
    payload = _fixture("noop_sandbox_commit_candidate.json")
    first = evaluate_sandboxed_live_memory_commit_adapter(payload)
    second = evaluate_sandboxed_live_memory_commit_adapter(payload)
    assert first.to_dict() == second.to_dict()
    assert first.status == "sandbox_commit_noop"
    assert list(tmp_path.rglob("*")) == []


def test_receipt_and_rollback_manifests_are_deterministic_sandbox_only() -> None:
    result = evaluate_sandboxed_live_memory_commit_adapter(_fixture("valid_ai_capsule_sandbox_commit_candidate.json"))
    assert build_receipt_manifest(result) == build_receipt_manifest(result)
    assert build_rollback_manifest(result) == build_rollback_manifest(result)
    assert build_receipt_manifest(result)["sandbox_only"] is True
    assert build_rollback_manifest(result)["sandbox_only"] is True


def test_module_does_not_introduce_unsafe_runtime_surfaces() -> None:
    text = Path("sentientos/sandboxed_live_memory_commit_adapter.py").read_text(encoding="utf-8")
    forbidden = ["append_memory(", "purge_memory(", "apply_forgetting_curve(", "requests.", "subprocess.", "openai", "prompt_assembler"]
    assert not any(marker in text for marker in forbidden)
