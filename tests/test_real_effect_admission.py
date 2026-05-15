from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.dry_run_audit_closure import build_dry_run_audit_closure_wing, dry_run_closure_bundle_digest
from sentientos.dry_run_execution_harness import build_dry_run_execution_harness_wing
from sentientos.fulfillment_executor_contract import build_fulfillment_executor_contract_wing
from sentientos.real_effect_admission import (
    RealEffectAdmissionBundle,
    build_real_effect_admission_wing,
    real_effect_capability_candidate_digest,
    summarize_real_effect_admission_bundle,
    summarize_real_effect_capability_admission_decision,
    summarize_real_effect_capability_block_receipt,
    summarize_real_effect_capability_candidate,
    summarize_real_effect_implementation_plan_scaffold,
    validate_real_effect_admission_bundle,
    validate_real_effect_capability_admission_decision,
    validate_real_effect_capability_block_receipt,
    validate_real_effect_capability_candidate,
    validate_real_effect_implementation_plan_scaffold,
)
from tests.test_fulfillment_authorization import FIXED
from tests.test_fulfillment_executor_contract import _consumed_receipt

pytestmark = pytest.mark.no_legacy_skip


def _closure(domain: str = "resource_pressure_fulfillment_authorization", **changes):
    executor = build_fulfillment_executor_contract_wing(_consumed_receipt(domain), created_at=FIXED)
    dry_run = build_dry_run_execution_harness_wing(executor.readiness_receipt, created_at=FIXED)
    assert dry_run.receipt is not None
    wing = build_dry_run_audit_closure_wing(dry_run.receipt, created_at=FIXED)
    bundle = wing.closure_bundle
    if changes:
        bundle = replace(bundle, **changes)
        if "digest" not in changes:
            bundle = replace(bundle, digest=dry_run_closure_bundle_digest(bundle))
    return bundle


def test_ready_dry_run_closure_builds_candidate_decision_plan_and_bundle() -> None:
    wing = build_real_effect_admission_wing(_closure("resource_pressure_fulfillment_authorization"), admission_domain="resource_pressure_real_effect_candidate", created_at=FIXED)
    assert wing.candidate.candidate_status in {"real_effect_candidate_recorded", "real_effect_candidate_recorded_with_warnings"}
    assert wing.decision.admission_status == "real_effect_admission_eligible_for_planning"
    assert hasattr(wing.plan_or_block_receipt, "plan_id")
    assert wing.admission_bundle.bundle_status == "real_effect_admission_eligible_for_planning"
    assert wing.decision.authorizes_implementation is False
    assert wing.decision.authorizes_execution is False
    assert wing.plan_or_block_receipt.implementation_not_started is True
    assert wing.plan_or_block_receipt.backend_loaded is False
    assert wing.plan_or_block_receipt.backend_invoked is False
    assert validate_real_effect_capability_candidate(wing.candidate).ok
    assert validate_real_effect_capability_admission_decision(wing.decision).ok
    assert validate_real_effect_implementation_plan_scaffold(wing.plan_or_block_receipt).ok
    assert validate_real_effect_admission_bundle(wing.admission_bundle).ok


@pytest.mark.parametrize("domain", ["diagnostics_real_effect_candidate", "resource_pressure_real_effect_candidate"])
def test_low_risk_domains_can_become_eligible_for_planning(domain: str) -> None:
    wing = build_real_effect_admission_wing(_closure(), admission_domain=domain, requested_implementation_tier="tier3_local_low_risk_effect_future", created_at=FIXED)
    assert wing.decision.admission_status == "real_effect_admission_eligible_for_planning"
    assert wing.decision.authorizes_implementation is False
    assert wing.decision.authorizes_execution is False


@pytest.mark.parametrize(
    ("bundle_status", "expected"),
    [
        ("dry_run_closure_bundle_blocked", "real_effect_admission_blocked"),
        ("dry_run_closure_bundle_incomplete", "real_effect_admission_incomplete"),
        ("dry_run_closure_bundle_contradicted", "real_effect_admission_contradicted"),
    ],
)
def test_non_ready_dry_run_closure_produces_non_ready_admission(bundle_status: str, expected: str) -> None:
    wing = build_real_effect_admission_wing(_closure(bundle_status=bundle_status), created_at=FIXED)
    assert wing.decision.admission_status == expected
    assert hasattr(wing.plan_or_block_receipt, "receipt_id")
    assert wing.plan_or_block_receipt.host_mutation_performed is False
    assert validate_real_effect_capability_block_receipt(wing.plan_or_block_receipt).ok


def test_dry_run_closure_claiming_real_effect_or_host_mutation_is_contradicted() -> None:
    wing = build_real_effect_admission_wing(_closure(real_effect_performed=True, host_mutation_performed=True), created_at=FIXED)
    assert wing.candidate.candidate_status == "real_effect_candidate_contradicted"
    assert wing.decision.admission_status == "real_effect_admission_contradicted"


@pytest.mark.parametrize(
    ("domain", "blocked"),
    [
        ("future_cooling_real_effect_candidate", {"fan_pwm_write", "thermal_actuation"}),
        ("future_power_real_effect_candidate", {"power_profile_mutation"}),
        ("future_cleanup_real_effect_candidate", {"file_cleanup", "file_delete"}),
        ("future_service_real_effect_candidate", {"service_restart", "process_kill"}),
    ],
)
def test_future_high_risk_domains_remain_blocked_by_default(domain: str, blocked: set[str]) -> None:
    wing = build_real_effect_admission_wing(_closure(), admission_domain=domain, requested_implementation_tier="tier5_hardware_control_effect_future", created_at=FIXED)
    assert wing.decision.admission_status == "real_effect_admission_blocked"
    assert blocked <= set(wing.decision.blocked_actions)
    assert blocked <= set(wing.admission_bundle.blocked_actions)
    assert hasattr(wing.plan_or_block_receipt, "receipt_id")
    assert wing.plan_or_block_receipt.host_mutation_performed is False


@pytest.mark.parametrize(
    ("record_name", "flag", "validator"),
    [
        ("decision", "authorizes_implementation", validate_real_effect_capability_admission_decision),
        ("decision", "authorizes_execution", validate_real_effect_capability_admission_decision),
        ("decision", "real_backend_implemented", validate_real_effect_capability_admission_decision),
        ("decision", "real_fulfillment_performed", validate_real_effect_capability_admission_decision),
        ("decision", "real_effect_performed", validate_real_effect_capability_admission_decision),
        ("decision", "host_mutation_performed", validate_real_effect_capability_admission_decision),
        ("plan_or_block_receipt", "backend_loaded", validate_real_effect_implementation_plan_scaffold),
        ("plan_or_block_receipt", "backend_invoked", validate_real_effect_implementation_plan_scaffold),
        ("plan_or_block_receipt", "real_fulfillment_performed", validate_real_effect_implementation_plan_scaffold),
        ("plan_or_block_receipt", "real_effect_performed", validate_real_effect_implementation_plan_scaffold),
        ("plan_or_block_receipt", "host_mutation_performed", validate_real_effect_implementation_plan_scaffold),
    ],
)
def test_validation_rejects_forbidden_true_fields(record_name: str, flag: str, validator) -> None:
    wing = build_real_effect_admission_wing(_closure(), admission_domain="resource_pressure_real_effect_candidate", created_at=FIXED)
    record = getattr(wing, record_name)
    bad = replace(record, **{flag: True})
    assert not validator(bad).ok


@pytest.mark.parametrize("flag", ["fan_pwm_write_performed", "thermal_actuation_performed", "power_profile_mutation_performed", "service_restart_performed", "file_cleanup_performed", "network_performed", "provider_invocation_performed", "prompt_assembly_performed", "subprocess_execution_performed", "shell_execution_performed", "control_plane_admission_execution_performed"])
def test_validation_rejects_forbidden_mapping_flags(flag: str) -> None:
    wing = build_real_effect_admission_wing(_closure(), created_at=FIXED)
    payload = wing.decision.to_dict()
    payload[flag] = True
    assert not validate_real_effect_capability_admission_decision(payload).ok


def test_digests_are_deterministic_and_change_on_meaningful_metadata() -> None:
    first = build_real_effect_admission_wing(_closure(), created_at=FIXED).candidate
    second = build_real_effect_admission_wing(_closure(), created_at=FIXED).candidate
    assert first.digest == second.digest
    changed = replace(first, admission_domain="operator_review_real_effect_candidate", digest="")
    assert real_effect_capability_candidate_digest(first) != real_effect_capability_candidate_digest(changed)


def test_summaries_are_metadata_only_and_non_authorizing() -> None:
    wing = build_real_effect_admission_wing(_closure(), created_at=FIXED)
    summaries = (
        summarize_real_effect_capability_candidate(wing.candidate),
        summarize_real_effect_capability_admission_decision(wing.decision),
        summarize_real_effect_implementation_plan_scaffold(wing.plan_or_block_receipt),
        summarize_real_effect_admission_bundle(wing.admission_bundle),
    )
    for summary in summaries:
        assert summary["metadata_only"] is True
    assert summaries[1]["authorizes_implementation"] is False
    assert summaries[1]["authorizes_execution"] is False
    blocked = build_real_effect_admission_wing(_closure(), admission_domain="future_cooling_real_effect_candidate", created_at=FIXED)
    assert summarize_real_effect_capability_block_receipt(blocked.plan_or_block_receipt)["host_mutation_performed"] is False


def test_bundle_validation_rejects_authorization_claim() -> None:
    wing = build_real_effect_admission_wing(_closure(), created_at=FIXED)
    bad = replace(wing.admission_bundle, authorizes_execution=True)
    assert not validate_real_effect_admission_bundle(bad).ok
