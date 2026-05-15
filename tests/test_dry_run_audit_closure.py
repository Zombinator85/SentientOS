from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.dry_run_audit_closure import (
    build_dry_run_audit_closure_wing,
    dry_run_effect_verification_digest,
    summarize_dry_run_audit_closure_receipt,
    summarize_dry_run_closure_bundle,
    summarize_dry_run_effect_verification,
    summarize_dry_run_postcondition_verification,
    summarize_dry_run_rollback_rehearsal,
    validate_dry_run_audit_closure_receipt,
    validate_dry_run_closure_bundle,
    validate_dry_run_effect_verification,
    validate_dry_run_postcondition_verification,
    validate_dry_run_rollback_rehearsal,
)
from sentientos.dry_run_execution_harness import build_dry_run_execution_harness_wing, dry_run_execution_receipt_digest
from sentientos.fulfillment_executor_contract import build_fulfillment_executor_contract_wing
from tests.test_fulfillment_authorization import FIXED
from tests.test_fulfillment_executor_contract import _consumed_receipt

pytestmark = pytest.mark.no_legacy_skip


def _receipt(domain: str = "future_cooling_fulfillment_authorization", **changes):
    executor = build_fulfillment_executor_contract_wing(_consumed_receipt(domain), created_at=FIXED)
    dry_run = build_dry_run_execution_harness_wing(executor.readiness_receipt, created_at=FIXED)
    assert dry_run.receipt is not None
    receipt = dry_run.receipt
    if changes:
        receipt = replace(receipt, **changes)
        if "digest" not in changes:
            receipt = replace(receipt, digest=dry_run_execution_receipt_digest(receipt))
    return receipt


def test_recorded_dry_run_receipt_builds_metadata_only_closure_records() -> None:
    wing = build_dry_run_audit_closure_wing(_receipt(), created_at=FIXED)
    assert wing.effect_verification.verification_status in {"dry_run_verification_recorded", "dry_run_verification_recorded_with_warnings"}
    assert wing.postcondition_verification.postcondition_status in {"dry_run_postcondition_verified", "dry_run_postcondition_verified_with_warnings"}
    assert wing.rollback_rehearsal.rollback_status in {"dry_run_rollback_rehearsed", "dry_run_rollback_rehearsed_with_warnings"}
    assert wing.audit_closure_receipt.audit_closure_status in {"dry_run_audit_closure_recorded", "dry_run_audit_closure_recorded_with_warnings"}
    assert wing.closure_bundle.bundle_status in {"dry_run_closure_bundle_ready", "dry_run_closure_bundle_ready_with_warnings"}
    assert wing.effect_verification.real_effect_receipt_created is False
    assert wing.postcondition_verification.real_postcondition_check_performed is False
    assert wing.rollback_rehearsal.real_rollback_performed is False
    assert wing.audit_closure_receipt.production_audit_receipt_created is False
    assert wing.closure_bundle.metadata_only is True
    assert validate_dry_run_effect_verification(wing.effect_verification).ok
    assert validate_dry_run_postcondition_verification(wing.postcondition_verification).ok
    assert validate_dry_run_rollback_rehearsal(wing.rollback_rehearsal).ok
    assert validate_dry_run_audit_closure_receipt(wing.audit_closure_receipt).ok
    assert validate_dry_run_closure_bundle(wing.closure_bundle).ok


@pytest.mark.parametrize(
    ("receipt_status", "expected"),
    [
        ("dry_run_execution_receipt_blocked", "blocked"),
        ("dry_run_execution_receipt_incomplete", "incomplete"),
        ("dry_run_execution_receipt_contradicted", "contradicted"),
    ],
)
def test_non_recorded_receipt_status_propagates_to_closure(receipt_status: str, expected: str) -> None:
    wing = build_dry_run_audit_closure_wing(_receipt(receipt_status=receipt_status), created_at=FIXED)
    assert wing.effect_verification.verification_status == f"dry_run_verification_{expected}"
    assert wing.postcondition_verification.postcondition_status == f"dry_run_postcondition_{'verified' if expected == 'recorded' else expected}"
    assert wing.rollback_rehearsal.rollback_status == f"dry_run_rollback_{'rehearsed' if expected == 'recorded' else expected}"
    assert wing.audit_closure_receipt.audit_closure_status == f"dry_run_audit_closure_{expected}"
    assert wing.closure_bundle.bundle_status == f"dry_run_closure_bundle_{expected}"


def test_receipt_claiming_real_effect_fulfillment_or_host_mutation_is_contradicted() -> None:
    wing = build_dry_run_audit_closure_wing(_receipt(real_effect_performed=True, real_fulfillment_performed=True, host_mutation_performed=True), created_at=FIXED)
    assert wing.effect_verification.verification_status == "dry_run_verification_contradicted"
    assert wing.audit_closure_receipt.audit_closure_status == "dry_run_audit_closure_contradicted"
    assert wing.closure_bundle.bundle_status == "dry_run_closure_bundle_contradicted"


@pytest.mark.parametrize(
    ("domain", "blocked"),
    [
        ("future_cooling_fulfillment_authorization", {"fan_pwm_write", "thermal_actuation"}),
        ("future_power_fulfillment_authorization", {"power_profile_mutation"}),
        ("future_cleanup_fulfillment_authorization", {"file_cleanup", "file_delete"}),
        ("future_service_fulfillment_authorization", {"service_restart", "process_kill"}),
    ],
)
def test_future_domain_specific_blocks_are_preserved(domain: str, blocked: set[str]) -> None:
    wing = build_dry_run_audit_closure_wing(_receipt(domain), created_at=FIXED)
    assert blocked <= set(wing.effect_verification.blocked_actions)
    assert blocked <= set(wing.audit_closure_receipt.blocked_actions)
    assert blocked <= set(wing.closure_bundle.blocked_actions)


@pytest.mark.parametrize(
    ("record_name", "flag", "validator"),
    [
        ("effect_verification", "real_effect_receipt_created", validate_dry_run_effect_verification),
        ("postcondition_verification", "real_postcondition_check_performed", validate_dry_run_postcondition_verification),
        ("rollback_rehearsal", "real_rollback_performed", validate_dry_run_rollback_rehearsal),
        ("audit_closure_receipt", "production_audit_receipt_created", validate_dry_run_audit_closure_receipt),
        ("audit_closure_receipt", "real_fulfillment_performed", validate_dry_run_audit_closure_receipt),
        ("audit_closure_receipt", "real_effect_performed", validate_dry_run_audit_closure_receipt),
        ("audit_closure_receipt", "host_mutation_performed", validate_dry_run_audit_closure_receipt),
        ("audit_closure_receipt", "fan_pwm_write_performed", validate_dry_run_audit_closure_receipt),
        ("audit_closure_receipt", "thermal_actuation_performed", validate_dry_run_audit_closure_receipt),
        ("audit_closure_receipt", "power_profile_mutation_performed", validate_dry_run_audit_closure_receipt),
        ("audit_closure_receipt", "service_restart_performed", validate_dry_run_audit_closure_receipt),
        ("audit_closure_receipt", "file_cleanup_performed", validate_dry_run_audit_closure_receipt),
        ("audit_closure_receipt", "network_performed", validate_dry_run_audit_closure_receipt),
        ("audit_closure_receipt", "provider_invocation_performed", validate_dry_run_audit_closure_receipt),
        ("audit_closure_receipt", "prompt_assembly_performed", validate_dry_run_audit_closure_receipt),
        ("closure_bundle", "real_fulfillment_performed", validate_dry_run_closure_bundle),
    ],
)
def test_validation_rejects_forbidden_true_flags(record_name: str, flag: str, validator) -> None:
    wing = build_dry_run_audit_closure_wing(_receipt(), created_at=FIXED)
    record = getattr(wing, record_name)
    bad = replace(record, **{flag: True})
    result = validator(bad)
    assert not result.ok
    assert any(f"forbidden_flag:{flag}" in finding for finding in result.findings)


def test_digests_are_deterministic_and_change_on_meaningful_metadata() -> None:
    receipt = _receipt()
    first = build_dry_run_audit_closure_wing(receipt, created_at=FIXED).effect_verification
    second = build_dry_run_audit_closure_wing(receipt, created_at=FIXED).effect_verification
    changed = replace(first, warning_codes=("new_warning",), digest="")
    changed = replace(changed, digest=dry_run_effect_verification_digest(changed))
    assert first.digest == second.digest
    assert first.digest != changed.digest


def test_summaries_are_metadata_only_and_non_effect() -> None:
    wing = build_dry_run_audit_closure_wing(_receipt(), created_at=FIXED)
    assert summarize_dry_run_effect_verification(wing.effect_verification)["real_effect_receipt_created"] is False
    assert summarize_dry_run_postcondition_verification(wing.postcondition_verification)["real_postcondition_check_performed"] is False
    assert summarize_dry_run_rollback_rehearsal(wing.rollback_rehearsal)["real_rollback_performed"] is False
    assert summarize_dry_run_audit_closure_receipt(wing.audit_closure_receipt)["production_audit_receipt_created"] is False
    assert summarize_dry_run_closure_bundle(wing.closure_bundle)["metadata_only"] is True
