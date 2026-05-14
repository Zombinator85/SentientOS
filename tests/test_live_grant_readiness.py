from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.controlled_authorization import build_controlled_authorization_wing_for_review_receipt
from sentientos.host_actuation_safety import build_safety_gates_for_domain
from sentientos.live_grant_readiness import (
    REQUIRED_PREREQUISITE_LABELS,
    build_grant_denial_deferral_receipt,
    build_grant_issue_preflight_receipt,
    build_live_grant_prerequisite_matrix,
    build_live_grant_readiness_wing,
    build_operator_policy_approval_packet,
    grant_issue_preflight_receipt_digest,
    summarize_grant_denial_deferral_receipt,
    summarize_grant_issue_preflight_receipt,
    summarize_live_grant_prerequisite_matrix,
    summarize_operator_policy_approval_packet,
    validate_grant_denial_deferral_receipt,
    validate_grant_issue_preflight_receipt,
    validate_live_grant_prerequisite_matrix,
    validate_operator_policy_approval_packet,
)
from tests.test_controlled_authorization import _review

pytestmark = pytest.mark.no_legacy_skip
FIXED = "2025-08-01T00:00:00+00:00"


def _ledger(kind: str = "future_cooling_policy_candidate"):
    review = _review(kind, thermal_zone_temperatures_c={"cpu": 91}) if kind == "future_cooling_policy_candidate" else _review(kind)
    return build_controlled_authorization_wing_for_review_receipt(review.receipt, review.future_authorization_grant_schema, created_at=FIXED).ledger


def _proof_manifest():
    return {"manifest_id": "reviewer-proof-bundle-test", "warning_codes": (), "risk_codes": (), "metadata_only": True, "reviewer_proof_only": True}


def test_future_cooling_requires_full_prerequisites_and_blocks_fan_pwm_and_thermal() -> None:
    manifest = build_safety_gates_for_domain("cooling_control_future", created_at=FIXED).safety_gate_satisfaction_manifest
    matrix = build_live_grant_prerequisite_matrix(
        "future_cooling_live_grant_review",
        controlled_authorization_ledger=_ledger(),
        safety_gate_manifest=manifest,
        reviewer_proof_bundle_manifest=_proof_manifest(),
        created_at=FIXED,
    )
    labels = {p.label for p in matrix.prerequisites}
    assert REQUIRED_PREREQUISITE_LABELS.issubset(labels)
    assert matrix.missing_labels == ()
    assert {"fan_pwm_write", "thermal_actuation", "live_authorization_grant", "host_mutation"}.issubset(matrix.blocked_actions)
    assert matrix.grants_live_authorization is False
    assert matrix.effect_performed is False
    assert validate_live_grant_prerequisite_matrix(matrix).ok


@pytest.mark.parametrize(
    ("domain", "safety_domain", "blocked"),
    [
        ("future_power_live_grant_review", "power_control_future", "power_profile_mutation"),
        ("future_cleanup_live_grant_review", "cleanup_control_future", "file_cleanup"),
        ("future_cleanup_live_grant_review", "cleanup_control_future", "file_delete"),
        ("future_service_live_grant_review", "service_control_future", "service_restart"),
        ("future_service_live_grant_review", "service_control_future", "process_kill"),
    ],
)
def test_future_domains_keep_real_actions_blocked(domain: str, safety_domain: str, blocked: str) -> None:
    manifest = build_safety_gates_for_domain(safety_domain, created_at=FIXED).safety_gate_satisfaction_manifest
    matrix = build_live_grant_prerequisite_matrix(domain, controlled_authorization_ledger=_ledger(), safety_gate_manifest=manifest, reviewer_proof_bundle_manifest=_proof_manifest(), created_at=FIXED)
    assert blocked in matrix.blocked_actions
    assert matrix.grants_live_authorization is False
    assert matrix.host_mutation_performed is False


@pytest.mark.parametrize("domain,safety_domain", [("diagnostics_live_grant_review", "diagnostics_only"), ("operator_review_live_grant_review", "operator_review")])
def test_diagnostics_and_operator_review_can_be_ready_but_grant_no_authority(domain: str, safety_domain: str) -> None:
    manifest = build_safety_gates_for_domain(safety_domain, created_at=FIXED).safety_gate_satisfaction_manifest
    wing = build_live_grant_readiness_wing(_ledger(), manifest, _proof_manifest(), readiness_domain=domain, created_at=FIXED)
    assert wing.preflight_receipt.readiness_status in {"live_grant_readiness_ready_for_operator_policy_review", "live_grant_readiness_ready_with_conditions"}
    assert wing.preflight_receipt.live_authorization_granted is False
    assert wing.approval_packet.approval_not_granted is True


def test_missing_sources_produce_incomplete_and_missing_proof_bundle_warns() -> None:
    matrix = build_live_grant_prerequisite_matrix("future_cooling_live_grant_review", created_at=FIXED)
    assert "authorization_ledger_present" in matrix.missing_labels
    assert "safety_gate_satisfaction_manifest_present" in matrix.missing_labels
    assert "reviewer_proof_bundle_present" in matrix.missing_labels
    assert "reviewer_proof_bundle_manifest_missing" in matrix.warning_codes
    packet = build_operator_policy_approval_packet(matrix)
    receipt = build_grant_issue_preflight_receipt(matrix, packet)
    assert packet.approval_packet_status == "operator_policy_approval_packet_incomplete"
    assert receipt.preflight_status == "grant_issue_preflight_incomplete"


def test_packet_preflight_and_denial_deferral_are_non_authorizing_non_mutating() -> None:
    manifest = build_safety_gates_for_domain("cooling_control_future", created_at=FIXED).safety_gate_satisfaction_manifest
    wing = build_live_grant_readiness_wing(_ledger(), manifest, _proof_manifest(), created_at=FIXED)
    assert wing.approval_packet.approval_packet_only is True
    assert wing.approval_packet.approval_not_granted is True
    assert wing.approval_packet.grants_live_authorization is False
    assert wing.preflight_receipt.preflight_only is True
    assert wing.preflight_receipt.grant_not_issued is True
    assert wing.preflight_receipt.live_authorization_granted is False
    assert wing.denial_deferral_receipt.denial_deferral_only is True
    assert wing.denial_deferral_receipt.grant_not_issued is True
    assert wing.denial_deferral_receipt.does_not_mutate_host is True
    assert validate_operator_policy_approval_packet(wing.approval_packet).ok
    assert validate_grant_issue_preflight_receipt(wing.preflight_receipt).ok
    assert validate_grant_denial_deferral_receipt(wing.denial_deferral_receipt).ok


@pytest.mark.parametrize("flag", ["grants_live_authorization", "fulfillment_granted", "effect_performed", "host_mutation_performed"])
def test_matrix_validation_rejects_forbidden_flags(flag: str) -> None:
    matrix = build_live_grant_prerequisite_matrix("future_cooling_live_grant_review", created_at=FIXED)
    bad = replace(matrix, **{flag: True})
    result = validate_live_grant_prerequisite_matrix(bad)
    assert not result.ok
    assert any(flag in finding for finding in result.findings)


@pytest.mark.parametrize("flag", ["live_authorization_granted", "does_not_execute", "does_not_mutate_host", "grant_not_issued"])
def test_preflight_validation_rejects_live_authorization_and_missing_non_authority_flags(flag: str) -> None:
    matrix = build_live_grant_prerequisite_matrix("future_cooling_live_grant_review", created_at=FIXED)
    packet = build_operator_policy_approval_packet(matrix)
    receipt = build_grant_issue_preflight_receipt(matrix, packet)
    bad = replace(receipt, **({flag: True} if flag == "live_authorization_granted" else {flag: False}))
    result = validate_grant_issue_preflight_receipt(bad)
    assert not result.ok
    assert any(flag in finding for finding in result.findings)


def test_source_claiming_network_provider_prompt_or_host_action_contradicts_readiness() -> None:
    manifest = replace(build_safety_gates_for_domain("cooling_control_future", created_at=FIXED).safety_gate_satisfaction_manifest, network_performed=True)
    wing = build_live_grant_readiness_wing(_ledger(), manifest, _proof_manifest(), created_at=FIXED)
    assert wing.preflight_receipt.readiness_status == "live_grant_readiness_contradicted"
    assert wing.preflight_receipt.preflight_status == "grant_issue_preflight_contradicted"
    assert any("network_performed" in risk for risk in wing.preflight_receipt.risk_codes)


def test_digests_are_deterministic_and_change_on_meaningful_metadata() -> None:
    matrix1 = build_live_grant_prerequisite_matrix("future_cooling_live_grant_review", created_at=FIXED)
    matrix2 = build_live_grant_prerequisite_matrix("future_cooling_live_grant_review", created_at=FIXED)
    assert matrix1.digest == matrix2.digest
    packet = build_operator_policy_approval_packet(matrix1)
    receipt = build_grant_issue_preflight_receipt(matrix1, packet)
    changed = replace(receipt, warning_codes=("new_warning",), digest="")
    assert grant_issue_preflight_receipt_digest(changed) != receipt.digest


def test_summaries_are_metadata_only() -> None:
    matrix = build_live_grant_prerequisite_matrix("future_cooling_live_grant_review", created_at=FIXED)
    packet = build_operator_policy_approval_packet(matrix)
    preflight = build_grant_issue_preflight_receipt(matrix, packet)
    denial = build_grant_denial_deferral_receipt(preflight)
    assert summarize_live_grant_prerequisite_matrix(matrix)["metadata_only"] is True
    assert summarize_operator_policy_approval_packet(packet)["approval_not_granted"] is True
    assert summarize_grant_issue_preflight_receipt(preflight)["grant_not_issued"] is True
    assert summarize_grant_denial_deferral_receipt(denial)["does_not_mutate_host"] is True
