from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.host_actuation_safety import (
    build_bounds_policy,
    build_cooldown_policy,
    build_hardware_allowlist_manifest,
    build_host_action_scope_manifest,
    build_os_backend_declaration,
    build_panic_stop_contract,
    build_safety_gate_satisfaction_manifest,
    build_safety_gates_for_controlled_authorization_contract,
    build_safety_gates_for_domain,
    safety_gate_satisfaction_manifest_digest,
    summarize_safety_gate_satisfaction_manifest,
    validate_bounds_policy,
    validate_cooldown_policy,
    validate_hardware_allowlist_manifest,
    validate_host_action_scope_manifest,
    validate_os_backend_declaration,
    validate_panic_stop_contract,
    validate_safety_gate_satisfaction_manifest,
)
from sentientos.controlled_authorization import ControlledAuthorizationGrantContract

FIXED = "2025-07-30T00:00:00+00:00"


def test_default_cooling_safety_gate_manifest_requires_declared_gates_and_blocks_actuation() -> None:
    bundle = build_safety_gates_for_domain("cooling_control_future", created_at=FIXED)
    manifest = bundle.safety_gate_satisfaction_manifest
    assert manifest.safety_status == "host_actuation_safety_ready_with_conditions"
    for gate in [
        "hardware_allowlist_required", "os_backend_declaration_required", "bounds_policy_required",
        "cooldown_policy_required", "panic_stop_required", "operator_identity_required", "policy_identity_required",
        "explicit_scope_required", "target_scope_declared", "time_bounds_required", "expiry_required",
        "revocation_path_required", "control_plane_admission_required", "audit_receipt_required",
        "rollback_plan_required", "rollback_receipt_required", "effect_receipt_required",
        "postcondition_check_required", "runtime_supervisor_observation_required", "immutable_trace_required",
    ]:
        assert gate in manifest.satisfied_gate_labels
    assert manifest.missing_gate_labels == ()
    assert {"fan_pwm_write", "thermal_actuation", "live_authorization_grant", "host_mutation"}.issubset(manifest.blocked_actions)
    assert manifest.grants_live_authorization is False
    assert manifest.grants_control_authority is False
    assert manifest.fulfillment_granted is False
    assert manifest.effect_performed is False
    assert manifest.host_mutation_performed is False


@pytest.mark.parametrize(
    ("domain", "blocked"),
    [
        ("power_control_future", "power_profile_mutation"),
        ("cleanup_control_future", "file_cleanup"),
        ("cleanup_control_future", "file_delete"),
        ("service_control_future", "service_restart"),
        ("service_control_future", "process_kill"),
    ],
)
def test_future_domains_keep_real_actions_blocked(domain: str, blocked: str) -> None:
    manifest = build_safety_gates_for_domain(domain, created_at=FIXED).safety_gate_satisfaction_manifest
    assert blocked in manifest.blocked_actions
    assert manifest.grants_live_authorization is False
    assert manifest.host_mutation_performed is False


@pytest.mark.parametrize("domain", ["diagnostics_only", "operator_review"])
def test_diagnostics_and_operator_review_are_ready_but_grant_no_authority(domain: str) -> None:
    manifest = build_safety_gates_for_domain(domain, created_at=FIXED).safety_gate_satisfaction_manifest
    assert manifest.safety_status in {"host_actuation_safety_ready", "host_actuation_safety_ready_with_conditions"}
    assert manifest.grants_control_authority is False
    assert manifest.grants_live_authorization is False


def test_metadata_records_do_not_execute_or_enforce_live_actions() -> None:
    hardware = build_hardware_allowlist_manifest("cooling_control_future", created_at=FIXED)
    os_backend = build_os_backend_declaration("cooling_control_future", created_at=FIXED)
    bounds = build_bounds_policy("cooling_control_future", created_at=FIXED)
    cooldown = build_cooldown_policy("cooling_control_future", created_at=FIXED)
    panic = build_panic_stop_contract("cooling_control_future", created_at=FIXED)
    scope = build_host_action_scope_manifest("cooling_control_future", created_at=FIXED)
    assert hardware.grants_control_authority is False
    assert os_backend.backend_loaded is False and os_backend.backend_invoked is False
    assert bounds.bounds_enforced_live is False
    assert cooldown.cooldown_enforced_live is False
    assert panic.panic_stop_executed is False
    assert scope.grants_control_authority is False
    assert validate_hardware_allowlist_manifest(hardware).ok
    assert validate_os_backend_declaration(os_backend).ok
    assert validate_bounds_policy(bounds).ok
    assert validate_cooldown_policy(cooldown).ok
    assert validate_panic_stop_contract(panic).ok
    assert validate_host_action_scope_manifest(scope).ok


def test_missing_required_gates_produce_incomplete_manifest() -> None:
    manifest = build_safety_gate_satisfaction_manifest("cooling_control_future", created_at=FIXED)
    assert manifest.safety_status == "host_actuation_safety_incomplete"
    assert "hardware_allowlist_required" in manifest.missing_gate_labels
    assert "os_backend_declaration_required" in manifest.missing_gate_labels


@pytest.mark.parametrize(
    "flag",
    [
        "grants_live_authorization", "grants_control_authority", "fulfillment_granted", "effect_performed",
        "host_mutation_performed", "fan_pwm_write_performed", "thermal_actuation_performed",
        "power_profile_mutation_performed", "service_restart_performed", "file_cleanup_performed",
        "network_performed", "provider_invocation_performed", "prompt_assembly_performed",
    ],
)
def test_safety_manifest_validation_rejects_forbidden_flags(flag: str) -> None:
    manifest = build_safety_gates_for_domain("cooling_control_future", created_at=FIXED).safety_gate_satisfaction_manifest
    bad = replace(manifest, **{flag: True})
    result = validate_safety_gate_satisfaction_manifest(bad)
    assert not result.ok
    assert any(flag in finding for finding in result.findings)


def test_record_specific_validation_rejects_live_claims() -> None:
    assert not validate_hardware_allowlist_manifest(replace(build_hardware_allowlist_manifest("cooling_control_future"), grants_control_authority=True)).ok
    assert not validate_os_backend_declaration(replace(build_os_backend_declaration("cooling_control_future"), backend_loaded=True)).ok
    assert not validate_bounds_policy(replace(build_bounds_policy("cooling_control_future"), bounds_enforced_live=True)).ok
    assert not validate_cooldown_policy(replace(build_cooldown_policy("cooling_control_future"), cooldown_enforced_live=True)).ok
    assert not validate_panic_stop_contract(replace(build_panic_stop_contract("cooling_control_future"), panic_stop_executed=True)).ok
    assert not validate_host_action_scope_manifest(replace(build_host_action_scope_manifest("cooling_control_future"), grants_control_authority=True)).ok


def test_digests_are_deterministic_and_change_on_meaningful_metadata() -> None:
    first = build_safety_gates_for_domain("cooling_control_future", created_at=FIXED).safety_gate_satisfaction_manifest
    second = build_safety_gates_for_domain("cooling_control_future", created_at=FIXED).safety_gate_satisfaction_manifest
    assert first.digest == second.digest
    changed = replace(first, warning_codes=("changed",), digest="")
    assert safety_gate_satisfaction_manifest_digest(changed) != first.digest


def test_summaries_are_metadata_only() -> None:
    manifest = build_safety_gates_for_domain("cooling_control_future", created_at=FIXED).safety_gate_satisfaction_manifest
    summary = summarize_safety_gate_satisfaction_manifest(manifest)
    assert summary["metadata_only"] is True
    assert summary["safety_gate_only"] is True
    assert summary["grants_live_authorization"] is False
    assert summary["effect_performed"] is False


def test_controlled_authorization_contract_integrates_to_safety_gates() -> None:
    contract = ControlledAuthorizationGrantContract(
        contract_id="contract-1",
        source_authorization_review_receipt_id="receipt-1",
        source_authorization_review_receipt_digest="sha256:receipt",
        future_authorization_grant_schema_id="schema-1",
        authorization_domain="future_cooling_authorization_review",
        approval_class="future_controlled_grant_contract",
        authorization_scope="future_cooling_scope",
        required_grant_gates=(),
        required_operator_identity_labels=("operator",),
        required_policy_labels=("policy",),
        required_scope_labels=("scope",),
        required_time_bound_labels=("time",),
        required_expiry_labels=("expiry",),
        required_revocation_labels=("revocation",),
        required_audit_labels=("audit",),
        required_control_plane_labels=("control-plane",),
        blocked_actions=("fan_pwm_write",),
        missing_prerequisites=(),
        status="controlled_authorization_contract_ready",
        warning_codes=(),
        risk_codes=(),
        created_at=FIXED,
        digest="sha256:contract",
    )
    bundle = build_safety_gates_for_controlled_authorization_contract(contract, created_at=FIXED)
    manifest = bundle.safety_gate_satisfaction_manifest
    assert manifest.domain == "cooling_control_future"
    assert manifest.source_controlled_authorization_contract_id == "contract-1"
    assert manifest.source_controlled_authorization_contract_digest == "sha256:contract"
    assert "fan_pwm_write" in manifest.blocked_actions
