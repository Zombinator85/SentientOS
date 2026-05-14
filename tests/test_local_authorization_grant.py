from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.controlled_authorization import build_controlled_authorization_wing_for_review_receipt
from sentientos.host_actuation_safety import build_safety_gates_for_domain
from sentientos.live_grant_readiness import build_live_grant_readiness_wing
from sentientos.local_authorization_grant import (
    build_local_authorization_grant,
    build_local_authorization_grant_expiry_evaluation,
    build_local_authorization_grant_ledger,
    build_local_authorization_grant_revocation_receipt,
    build_local_authorization_grant_wing,
    build_operator_approval_evidence,
    build_policy_approval_evidence,
    local_authorization_grant_digest,
    summarize_local_authorization_grant,
    summarize_local_authorization_grant_expiry_evaluation,
    summarize_local_authorization_grant_ledger,
    summarize_local_authorization_grant_revocation_receipt,
    summarize_local_authorization_grant_verification,
    summarize_operator_approval_evidence,
    summarize_policy_approval_evidence,
    validate_local_authorization_grant,
    validate_local_authorization_grant_expiry_evaluation,
    validate_local_authorization_grant_ledger,
    validate_local_authorization_grant_revocation_receipt,
    validate_local_authorization_grant_verification,
    validate_operator_approval_evidence,
    validate_policy_approval_evidence,
    verify_local_authorization_grant,
)
from tests.test_controlled_authorization import _review

pytestmark = pytest.mark.no_legacy_skip
FIXED = "2025-08-01T00:00:00+00:00"


def _readiness(kind: str = "future_cooling_policy_candidate", readiness_domain: str = "future_cooling_live_grant_review", safety_domain: str = "cooling_control_future"):
    review = _review(kind, thermal_zone_temperatures_c={"cpu": 91}) if kind == "future_cooling_policy_candidate" else _review(kind)
    ledger = build_controlled_authorization_wing_for_review_receipt(review.receipt, review.future_authorization_grant_schema, created_at=FIXED).ledger
    safety = build_safety_gates_for_domain(safety_domain, created_at=FIXED).safety_gate_satisfaction_manifest
    return build_live_grant_readiness_wing(ledger, safety, {"manifest_id": "reviewer-proof", "metadata_only": True}, readiness_domain=readiness_domain, created_at=FIXED)


def _approvals(scope: str = "future_cooling_scope"):
    return (
        build_operator_approval_evidence(approval_scope_labels=(scope,), created_at=FIXED),
        build_policy_approval_evidence(policy_scope_labels=(scope,), created_at=FIXED),
    )


def test_ready_preflight_and_valid_approval_evidence_produces_active_non_fulfillment_grant() -> None:
    readiness = _readiness()
    operator, policy = _approvals()
    wing = build_local_authorization_grant_wing(readiness.preflight_receipt, readiness.prerequisite_matrix, operator, policy, created_at=FIXED)
    grant = wing.grant
    assert grant.grant_status in {"local_authorization_grant_active", "local_authorization_grant_active_with_conditions"}
    assert grant.live_authorization_granted is True
    assert grant.fulfillment_granted is False
    assert grant.effect_performed is False
    assert grant.host_mutation_performed is False
    assert validate_operator_approval_evidence(operator).ok
    assert validate_policy_approval_evidence(policy).ok
    assert validate_local_authorization_grant(grant).ok
    assert wing.verification.authorizes_fulfillment is False
    assert validate_local_authorization_grant_verification(wing.verification).ok


@pytest.mark.parametrize(
    ("preflight_status", "readiness_status", "expected"),
    [
        ("grant_issue_preflight_blocked", "live_grant_readiness_blocked", "local_authorization_grant_blocked"),
        ("grant_issue_preflight_incomplete", "live_grant_readiness_incomplete", "local_authorization_grant_incomplete"),
        ("grant_issue_preflight_contradicted", "live_grant_readiness_contradicted", "local_authorization_grant_contradicted"),
    ],
)
def test_non_ready_preflights_produce_non_active_grant(preflight_status: str, readiness_status: str, expected: str) -> None:
    readiness = _readiness()
    preflight = replace(readiness.preflight_receipt, preflight_status=preflight_status, readiness_status=readiness_status, digest="")
    preflight = replace(preflight, digest=readiness.preflight_receipt.digest)
    operator, policy = _approvals()
    grant = build_local_authorization_grant(preflight, readiness.prerequisite_matrix, operator, policy, created_at=FIXED)
    assert grant.grant_status == expected
    assert grant.live_authorization_granted is False


@pytest.mark.parametrize(
    ("operator_status", "policy_status", "expected"),
    [
        ("approval_evidence_missing", "approval_evidence_present", "local_authorization_grant_incomplete"),
        ("approval_evidence_present", "approval_evidence_missing", "local_authorization_grant_incomplete"),
        ("approval_evidence_blocked", "approval_evidence_present", "local_authorization_grant_blocked"),
        ("approval_evidence_present", "approval_evidence_contradicted", "local_authorization_grant_contradicted"),
    ],
)
def test_missing_or_bad_approval_evidence_blocks_or_incompletes(operator_status: str, policy_status: str, expected: str) -> None:
    readiness = _readiness()
    operator = build_operator_approval_evidence(approval_status=operator_status, created_at=FIXED)
    policy = build_policy_approval_evidence(approval_status=policy_status, created_at=FIXED)
    grant = build_local_authorization_grant(readiness.preflight_receipt, readiness.prerequisite_matrix, operator, policy, created_at=FIXED)
    assert grant.grant_status == expected
    assert grant.live_authorization_granted is False


@pytest.mark.parametrize(
    ("domain", "scope", "readiness_domain", "safety_domain", "blocked"),
    [
        ("future_cooling_local_authorization", "future_cooling_scope", "future_cooling_live_grant_review", "cooling_control_future", {"fan_pwm_write", "thermal_actuation"}),
        ("future_power_local_authorization", "future_power_scope", "future_power_live_grant_review", "power_control_future", {"power_profile_mutation"}),
        ("future_cleanup_local_authorization", "future_cleanup_scope", "future_cleanup_live_grant_review", "cleanup_control_future", {"file_cleanup", "file_delete"}),
        ("future_service_local_authorization", "future_service_scope", "future_service_live_grant_review", "service_control_future", {"service_restart", "process_kill"}),
    ],
)
def test_future_domains_preserve_blocked_real_actions(domain: str, scope: str, readiness_domain: str, safety_domain: str, blocked: set[str]) -> None:
    readiness = _readiness(readiness_domain=readiness_domain, safety_domain=safety_domain)
    operator, policy = _approvals(scope)
    grant = build_local_authorization_grant(readiness.preflight_receipt, readiness.prerequisite_matrix, operator, policy, authorization_domain=domain, grant_scope=scope, created_at=FIXED)
    assert blocked.issubset(set(grant.blocked_actions))
    assert set(grant.required_future_fulfillment_gates) >= {"control_plane_admission_required_for_future_fulfillment", "effect_receipt_required_for_future_fulfillment"}
    assert grant.host_mutation_performed is False


def test_revocation_expiry_verification_and_ledger_are_metadata_only() -> None:
    readiness = _readiness()
    operator, policy = _approvals()
    grant = build_local_authorization_grant(readiness.preflight_receipt, readiness.prerequisite_matrix, operator, policy, created_at=FIXED)
    revocation = build_local_authorization_grant_revocation_receipt(grant, created_at=FIXED)
    expiry = build_local_authorization_grant_expiry_evaluation(grant, evaluated_at="1970-01-03T00:00:00+00:00")
    verification = verify_local_authorization_grant(grant, expiry_evaluation=expiry, revocation_receipts=(revocation,))
    ledger = build_local_authorization_grant_ledger((grant,), (revocation,), (expiry,), created_at=FIXED)
    assert revocation.live_authorization_revoked is True
    assert revocation.does_not_execute is True and revocation.does_not_mutate_host is True
    assert expiry.metadata_only is True and expiry.expiry_evaluation_only is True
    assert expiry.expiry_status == "local_authorization_expiry_expired"
    assert verification.authorizes_fulfillment is False
    assert ledger.active_grant_count == 0
    assert ledger.revoked_grant_count == 1
    assert ledger.expired_grant_count == 1
    assert ledger.host_mutation_performed is False
    assert validate_local_authorization_grant_revocation_receipt(revocation).ok
    assert validate_local_authorization_grant_expiry_evaluation(expiry).ok
    assert validate_local_authorization_grant_verification(verification).ok
    assert validate_local_authorization_grant_ledger(ledger).ok


@pytest.mark.parametrize("flag", [
    "fulfillment_granted", "effect_performed", "host_mutation_performed", "fan_pwm_write_performed",
    "thermal_actuation_performed", "power_profile_mutation_performed", "process_kill_performed",
    "service_restart_performed", "file_cleanup_performed", "provider_invocation_performed", "network_performed", "prompt_assembly_performed",
])
def test_validation_rejects_forbidden_action_flags(flag: str) -> None:
    readiness = _readiness()
    operator, policy = _approvals()
    grant = build_local_authorization_grant(readiness.preflight_receipt, readiness.prerequisite_matrix, operator, policy, created_at=FIXED)
    bad = replace(grant, **{flag: True})
    result = validate_local_authorization_grant(bad)
    assert not result.ok
    assert any(flag in finding for finding in result.findings)


def test_digests_are_deterministic_and_change_on_meaningful_metadata() -> None:
    readiness = _readiness()
    operator, policy = _approvals()
    grant = build_local_authorization_grant(readiness.preflight_receipt, readiness.prerequisite_matrix, operator, policy, created_at=FIXED)
    assert grant.digest == local_authorization_grant_digest(grant)
    same = build_local_authorization_grant(readiness.preflight_receipt, readiness.prerequisite_matrix, operator, policy, created_at=FIXED)
    changed = build_local_authorization_grant(readiness.preflight_receipt, readiness.prerequisite_matrix, operator, policy, grant_scope="operator_review_scope", authorization_domain="operator_review_local_authorization", created_at=FIXED)
    assert same.digest == grant.digest
    assert changed.digest != grant.digest


def test_summaries_are_metadata_only() -> None:
    readiness = _readiness()
    operator, policy = _approvals()
    wing = build_local_authorization_grant_wing(readiness.preflight_receipt, readiness.prerequisite_matrix, operator, policy, created_at=FIXED)
    summaries = (
        summarize_operator_approval_evidence(operator),
        summarize_policy_approval_evidence(policy),
        summarize_local_authorization_grant(wing.grant),
        summarize_local_authorization_grant_revocation_receipt(wing.revocation_receipt),
        summarize_local_authorization_grant_expiry_evaluation(wing.expiry_evaluation),
        summarize_local_authorization_grant_verification(wing.verification),
        summarize_local_authorization_grant_ledger(wing.ledger),
    )
    assert all(summary["metadata_only"] is True for summary in summaries)
    assert wing.verification.authorizes_fulfillment is False
