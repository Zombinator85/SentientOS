from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.controlled_authorization import build_controlled_authorization_wing_for_review_receipt
from sentientos.fulfillment_authorization import (
    build_fulfillment_authorization_request,
    build_fulfillment_authorization_wing,
    fulfillment_authorization_request_digest,
    summarize_fulfillment_authorization_consumption_receipt,
    summarize_fulfillment_authorization_denial_receipt,
    summarize_fulfillment_authorization_request,
    summarize_fulfillment_scope_match_assessment,
    summarize_grant_consumption_verification,
    validate_fulfillment_authorization_consumption_receipt,
    validate_fulfillment_authorization_denial_receipt,
    validate_fulfillment_authorization_request,
    validate_fulfillment_scope_match_assessment,
    validate_grant_consumption_verification,
)
from sentientos.host_actuation_safety import build_safety_gates_for_domain
from sentientos.live_grant_readiness import build_live_grant_readiness_wing
from sentientos.local_authorization_grant import (
    build_local_authorization_grant,
    build_local_authorization_grant_expiry_evaluation,
    build_local_authorization_grant_revocation_receipt,
    build_operator_approval_evidence,
    build_policy_approval_evidence,
    verify_local_authorization_grant,
)
from tests.test_controlled_authorization import _review

pytestmark = pytest.mark.no_legacy_skip
FIXED = "2025-08-01T00:00:00+00:00"


def _grant(scope: str = "future_cooling_scope", domain: str = "future_cooling_local_authorization", readiness_domain: str = "future_cooling_live_grant_review"):
    review = _review("future_cooling_policy_candidate", thermal_zone_temperatures_c={"cpu": 91})
    ledger = build_controlled_authorization_wing_for_review_receipt(review.receipt, review.future_authorization_grant_schema, created_at=FIXED).ledger
    safety = build_safety_gates_for_domain("cooling_control_future", created_at=FIXED).safety_gate_satisfaction_manifest
    readiness = build_live_grant_readiness_wing(ledger, safety, {"manifest_id": "proof", "metadata_only": True}, readiness_domain=readiness_domain, created_at=FIXED)
    op = build_operator_approval_evidence(
        approval_scope_labels=(scope,),
        approval_time_bounds=("not_before:1970-01-01T00:00:00+00:00", "not_after:2999-01-01T00:00:00+00:00"),
        approval_expiry_label="expires:2999-01-01T00:00:00+00:00",
        created_at=FIXED,
    )
    pol = build_policy_approval_evidence(
        policy_scope_labels=(scope,),
        policy_time_bounds=("not_before:1970-01-01T00:00:00+00:00", "not_after:2999-01-01T00:00:00+00:00"),
        policy_expiry_label="expires:2999-01-01T00:00:00+00:00",
        created_at=FIXED,
    )
    grant = build_local_authorization_grant(readiness.preflight_receipt, readiness.prerequisite_matrix, op, pol, authorization_domain=domain, grant_scope=scope, created_at=FIXED)
    expiry = build_local_authorization_grant_expiry_evaluation(grant, evaluated_at=FIXED)
    verification = verify_local_authorization_grant(grant, checked_scope_labels=(scope,), checked_time_label=FIXED, expiry_evaluation=expiry)
    return grant, verification


def _wing(scope: str = "future_cooling_scope", fulfillment_domain: str = "future_cooling_fulfillment_authorization"):
    grant, verification = _grant(scope=scope, domain=fulfillment_domain.replace("_fulfillment_authorization", "_local_authorization"))
    return build_fulfillment_authorization_wing(
        grant,
        verification,
        requested_fulfillment_domain=fulfillment_domain,
        requested_backend_class="future_metadata_only_executor",
        requested_scope_labels=(scope,),
        requested_time_label=FIXED,
        created_at=FIXED,
    )


def test_active_valid_matching_scope_records_consumed_authorization_without_fulfillment() -> None:
    wing = _wing()
    assert wing.denial_receipt is None
    assert wing.consumption_receipt is not None
    assert wing.grant_consumption_verification.consumption_status in {"grant_consumption_verified", "grant_consumption_verified_with_conditions"}
    assert wing.scope_match_assessment.scope_match_status in {"fulfillment_scope_match", "fulfillment_scope_match_with_conditions"}
    assert wing.consumption_receipt.authorization_consumed_for_future_fulfillment is True
    assert wing.consumption_receipt.fulfillment_granted is False
    assert wing.consumption_receipt.effect_performed is False
    assert wing.consumption_receipt.host_mutation_performed is False
    assert validate_fulfillment_authorization_request(wing.request).ok
    assert validate_grant_consumption_verification(wing.grant_consumption_verification).ok
    assert validate_fulfillment_scope_match_assessment(wing.scope_match_assessment).ok
    assert validate_fulfillment_authorization_consumption_receipt(wing.consumption_receipt).ok


def test_grant_consumption_verification_does_not_authorize_fulfillment() -> None:
    wing = _wing()
    assert wing.grant_consumption_verification.authorizes_fulfillment is False
    assert wing.grant_consumption_verification.does_not_execute is True
    assert wing.grant_consumption_verification.does_not_mutate_host is True


@pytest.mark.parametrize(
    ("grant_status", "verification_status", "expected"),
    [
        ("local_authorization_grant_blocked", "local_authorization_verification_blocked", "grant_consumption_blocked"),
        ("local_authorization_grant_incomplete", "local_authorization_verification_incomplete", "grant_consumption_incomplete"),
        ("local_authorization_grant_contradicted", "local_authorization_verification_contradicted", "grant_consumption_contradicted"),
        ("local_authorization_grant_expired", "local_authorization_verification_expired", "grant_consumption_expired"),
        ("local_authorization_grant_revoked", "local_authorization_verification_revoked", "grant_consumption_revoked"),
    ],
)
def test_non_active_grants_produce_denial(grant_status: str, verification_status: str, expected: str) -> None:
    grant, verification = _grant()
    grant = replace(grant, grant_status=grant_status, live_authorization_granted=False, digest="")
    verification = replace(verification, verification_status=verification_status, digest="")
    wing = build_fulfillment_authorization_wing(
        grant,
        verification,
        requested_fulfillment_domain="future_cooling_fulfillment_authorization",
        requested_backend_class="future_metadata_only_executor",
        requested_scope_labels=("future_cooling_scope",),
        requested_time_label=FIXED,
        created_at=FIXED,
    )
    assert wing.consumption_receipt is None
    assert wing.denial_receipt is not None
    assert wing.grant_consumption_verification.consumption_status == expected
    assert expected in wing.denial_receipt.denial_reason_codes
    assert wing.denial_receipt.effect_performed is False
    assert wing.denial_receipt.host_mutation_performed is False
    assert validate_fulfillment_authorization_denial_receipt(wing.denial_receipt).ok


def test_requested_scope_exceeding_grant_scope_produces_out_of_scope_denial() -> None:
    grant, verification = _grant()
    wing = build_fulfillment_authorization_wing(
        grant,
        verification,
        requested_fulfillment_domain="future_cooling_fulfillment_authorization",
        requested_backend_class="future_metadata_only_executor",
        requested_scope_labels=("future_cooling_scope", "future_power_scope"),
        requested_time_label=FIXED,
        created_at=FIXED,
    )
    assert wing.denial_receipt is not None
    assert wing.grant_consumption_verification.consumption_status == "grant_consumption_out_of_scope"
    assert wing.scope_match_assessment.scope_match_status == "fulfillment_scope_mismatch"
    assert "future_power_scope" in wing.denial_receipt.missing_labels


def test_missing_required_request_labels_produce_incomplete_denial() -> None:
    grant, verification = _grant()
    request = build_fulfillment_authorization_request(
        grant,
        verification,
        requested_fulfillment_domain="future_cooling_fulfillment_authorization",
        requested_backend_class="future_metadata_only_executor",
        requested_scope_labels=("future_cooling_scope",),
        requested_time_label=FIXED,
        required_request_labels=("local_authorization_grant_required",),
        created_at=FIXED,
    )
    assert request.request_status == "fulfillment_authorization_request_incomplete"
    assert validate_fulfillment_authorization_request(request).ok


@pytest.mark.parametrize(
    ("domain", "scope", "expected_blocks"),
    [
        ("future_cooling_fulfillment_authorization", "future_cooling_scope", {"fan_pwm_write", "thermal_actuation"}),
        ("future_power_fulfillment_authorization", "future_power_scope", {"power_profile_mutation"}),
        ("future_cleanup_fulfillment_authorization", "future_cleanup_scope", {"file_cleanup", "file_delete"}),
        ("future_service_fulfillment_authorization", "future_service_scope", {"service_restart", "process_kill"}),
    ],
)
def test_future_domain_consumption_preserves_blocked_actions(domain: str, scope: str, expected_blocks: set[str]) -> None:
    wing = _wing(scope=scope, fulfillment_domain=domain)
    record = wing.consumption_receipt or wing.denial_receipt
    assert record is not None
    assert expected_blocks <= set(record.blocked_actions)


@pytest.mark.parametrize("flag", ["fulfillment_granted", "effect_performed", "host_mutation_performed", "fan_pwm_write_performed", "thermal_actuation_performed", "power_profile_mutation_performed", "service_restart_performed", "file_cleanup_performed", "provider_invocation_performed", "network_performed", "prompt_assembly_performed"])
def test_consumption_validation_rejects_forbidden_action_flags(flag: str) -> None:
    receipt = _wing().consumption_receipt
    assert receipt is not None
    bad = dict(receipt.to_dict())
    bad[flag] = True
    assert not validate_fulfillment_authorization_consumption_receipt(bad).ok


def test_request_validation_rejects_fulfillment_effect_or_host_mutation_claims() -> None:
    request = _wing().request
    for flag in ("fulfillment_granted", "effect_performed", "host_mutation_performed"):
        bad = dict(request.to_dict())
        bad[flag] = True
        assert not validate_fulfillment_authorization_request(bad).ok


def test_denial_receipt_does_not_execute_or_mutate() -> None:
    grant, verification = _grant()
    wing = build_fulfillment_authorization_wing(
        grant,
        verification,
        requested_fulfillment_domain="future_cooling_fulfillment_authorization",
        requested_backend_class="future_metadata_only_executor",
        requested_scope_labels=("future_power_scope",),
        requested_time_label=FIXED,
        created_at=FIXED,
    )
    assert wing.denial_receipt is not None
    assert wing.denial_receipt.authorization_consumed_for_future_fulfillment is False
    assert wing.denial_receipt.does_not_execute is True
    assert wing.denial_receipt.does_not_mutate_host is True


def test_digests_are_deterministic_and_change_on_meaningful_metadata() -> None:
    request = _wing().request
    same = replace(request, digest="")
    same = replace(same, digest=fulfillment_authorization_request_digest(same))
    assert same.digest == request.digest
    changed = replace(request, requested_backend_class="other_future_backend", digest="")
    changed = replace(changed, digest=fulfillment_authorization_request_digest(changed))
    assert changed.digest != request.digest


def test_summaries_are_metadata_only_and_non_executing() -> None:
    wing = _wing()
    assert summarize_fulfillment_authorization_request(wing.request)["metadata_only"] is True
    assert summarize_grant_consumption_verification(wing.grant_consumption_verification)["authorizes_fulfillment"] is False
    assert summarize_fulfillment_scope_match_assessment(wing.scope_match_assessment)["authorizes_fulfillment"] is False
    assert summarize_fulfillment_authorization_consumption_receipt(wing.consumption_receipt)["effect_performed"] is False
    denial_wing = build_fulfillment_authorization_wing(
        _grant()[0],
        _grant()[1],
        requested_fulfillment_domain="future_cooling_fulfillment_authorization",
        requested_backend_class="future_metadata_only_executor",
        requested_scope_labels=("future_power_scope",),
        requested_time_label=FIXED,
        created_at=FIXED,
    )
    assert denial_wing.denial_receipt is not None
    assert summarize_fulfillment_authorization_denial_receipt(denial_wing.denial_receipt)["effect_performed"] is False
