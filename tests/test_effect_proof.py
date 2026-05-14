from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.actuation_fulfillment import build_actuation_fulfillment_plan, build_actuation_fulfillment_rehearsal_receipt
from sentientos.effect_proof import (
    build_effect_receipt_contract,
    build_execution_proof_wing_for_rehearsal_receipt,
    build_execution_readiness_manifest,
    build_future_effect_receipt_schema,
    build_postcondition_check_plan,
    build_postcondition_check_receipt,
    build_rollback_plan,
    build_rollback_receipt,
    effect_receipt_contract_digest,
    execution_readiness_manifest_digest,
    future_effect_receipt_digest,
    postcondition_check_plan_digest,
    postcondition_check_receipt_digest,
    rollback_plan_digest,
    rollback_receipt_digest,
    summarize_effect_receipt_contract,
    summarize_execution_readiness_manifest,
    summarize_future_effect_receipt_schema,
    summarize_postcondition_check_plan,
    summarize_postcondition_check_receipt,
    summarize_rollback_plan,
    summarize_rollback_receipt,
    validate_effect_receipt_contract,
    validate_execution_readiness_manifest,
    validate_future_effect_receipt_schema,
    validate_postcondition_check_plan,
    validate_postcondition_check_receipt,
    validate_rollback_plan,
    validate_rollback_receipt,
)
from tests.test_actuation_fulfillment import _broker_receipt_for

pytestmark = pytest.mark.no_legacy_skip


def _rehearsal(kind: str, **kwargs):
    return build_actuation_fulfillment_rehearsal_receipt(build_actuation_fulfillment_plan(_broker_receipt_for(kind, **kwargs)))


def test_valid_phase5_rehearsal_builds_execution_proof_wing() -> None:
    wing = build_execution_proof_wing_for_rehearsal_receipt(_rehearsal("inspect_cpu_pressure_candidate", cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30))
    assert wing.effect_contract.status == "effect_receipt_contract_ready"
    assert wing.future_effect_receipt.status == "future_effect_receipt_schema_ready"
    assert wing.postcondition_plan.status == "postcondition_plan_ready"
    assert wing.rollback_plan.status == "rollback_plan_ready"
    assert wing.execution_readiness_manifest.readiness_status == "execution_readiness_for_authorization_review"
    assert validate_effect_receipt_contract(wing.effect_contract).ok
    assert validate_future_effect_receipt_schema(wing.future_effect_receipt).ok
    assert validate_postcondition_check_plan(wing.postcondition_plan).ok
    assert validate_rollback_plan(wing.rollback_plan).ok
    assert validate_execution_readiness_manifest(wing.execution_readiness_manifest).ok


@pytest.mark.parametrize(
    ("source_status", "expected"),
    [
        ("actuation_fulfillment_rehearsal_blocked", "execution_readiness_blocked"),
        ("actuation_fulfillment_rehearsal_incomplete", "execution_readiness_incomplete"),
        ("actuation_fulfillment_rehearsal_contradicted", "execution_readiness_contradicted"),
    ],
)
def test_blocked_incomplete_contradicted_rehearsal_status_flows_to_readiness(source_status: str, expected: str) -> None:
    rehearsal = replace(_rehearsal("inspect_cpu_pressure_candidate", cpu_utilization_percent=95), rehearsal_status=source_status)
    wing = build_execution_proof_wing_for_rehearsal_receipt(rehearsal)
    assert wing.execution_readiness_manifest.readiness_status == expected


def test_future_cooling_rehearsal_requires_cooling_gates_and_keeps_control_blocked() -> None:
    rehearsal = _rehearsal("future_cooling_policy_candidate", recorded=True, thermal_zone_temperatures_c={"cpu": 90})
    wing = build_execution_proof_wing_for_rehearsal_receipt(rehearsal)
    gates = set(wing.effect_contract.required_proof_gates)
    for gate in ["hardware_allowlist_required", "os_backend_declaration_required", "bounds_policy_required", "cooldown_policy_required", "panic_stop_required", "postcondition_check_required", "rollback_plan_required", "rollback_receipt_required", "audit_receipt_required", "runtime_supervisor_observation_required", "immutable_trace_required"]:
        assert gate in gates
    assert "fan_pwm_write_without_allowlist" in wing.effect_contract.blocked_actions
    assert "thermal_actuation_without_policy" in wing.effect_contract.blocked_actions


def test_future_power_cleanup_and_service_rehearsals_keep_mutations_blocked() -> None:
    power = build_execution_proof_wing_for_rehearsal_receipt(_rehearsal("future_power_policy_candidate", recorded=True, battery_percent=5, battery_charging=False))
    cleanup = build_execution_proof_wing_for_rehearsal_receipt(_rehearsal("future_cleanup_policy_candidate", recorded=True, disk_utilization_percent=95))
    service = build_execution_proof_wing_for_rehearsal_receipt(_rehearsal("inspect_service_health_candidate", service_health_labels=("daemon_degraded",)))
    assert "power_profile_mutation_without_policy" in power.effect_contract.blocked_actions
    assert {"file_cleanup_without_scope", "file_delete_without_scope"}.issubset(cleanup.effect_contract.blocked_actions)
    assert "service_restart_without_authorization" in service.effect_contract.blocked_actions
    assert power.execution_readiness_manifest.authorization_granted is False
    assert cleanup.execution_readiness_manifest.effect_performed is False
    assert service.execution_readiness_manifest.host_mutation_performed is False


def test_readiness_future_receipts_postconditions_and_rollback_remain_non_effects() -> None:
    wing = build_execution_proof_wing_for_rehearsal_receipt(_rehearsal("inspect_cpu_pressure_candidate", cpu_utilization_percent=95))
    post_receipt = build_postcondition_check_receipt(wing.postcondition_plan)
    rollback_receipt = build_rollback_receipt(wing.rollback_plan)
    assert wing.execution_readiness_manifest.authorization_granted is False
    assert wing.execution_readiness_manifest.fulfillment_granted is False
    assert wing.future_effect_receipt.schema_only is True
    assert wing.future_effect_receipt.effect_performed is False
    assert post_receipt.check_is_schema_or_rehearsal_only is True
    assert rollback_receipt.rollback_is_schema_or_rehearsal_only is True
    assert validate_postcondition_check_receipt(post_receipt).ok
    assert validate_rollback_receipt(rollback_receipt).ok


def test_digests_are_deterministic_for_all_records_and_summaries_metadata_only() -> None:
    wing = build_execution_proof_wing_for_rehearsal_receipt(_rehearsal("inspect_cpu_pressure_candidate", cpu_utilization_percent=95))
    post_receipt = build_postcondition_check_receipt(wing.postcondition_plan)
    rollback_receipt = build_rollback_receipt(wing.rollback_plan)
    assert effect_receipt_contract_digest(wing.effect_contract) == effect_receipt_contract_digest(wing.effect_contract)
    assert future_effect_receipt_digest(wing.future_effect_receipt) == wing.future_effect_receipt.digest
    assert postcondition_check_plan_digest(wing.postcondition_plan) == postcondition_check_plan_digest(wing.postcondition_plan)
    assert postcondition_check_receipt_digest(post_receipt) == post_receipt.digest
    assert rollback_plan_digest(wing.rollback_plan) == rollback_plan_digest(wing.rollback_plan)
    assert rollback_receipt_digest(rollback_receipt) == rollback_receipt.digest
    assert execution_readiness_manifest_digest(wing.execution_readiness_manifest) == wing.execution_readiness_manifest.digest
    assert summarize_effect_receipt_contract(wing.effect_contract)["metadata_only"] is True
    assert summarize_future_effect_receipt_schema(wing.future_effect_receipt)["schema_only"] is True
    assert summarize_postcondition_check_plan(wing.postcondition_plan)["metadata_only"] is True
    assert summarize_postcondition_check_receipt(post_receipt)["receipt_only"] is True
    assert summarize_rollback_plan(wing.rollback_plan)["metadata_only"] is True
    assert summarize_rollback_receipt(rollback_receipt)["receipt_only"] is True
    assert summarize_execution_readiness_manifest(wing.execution_readiness_manifest)["readiness_only"] is True


@pytest.mark.parametrize("flag", ["authorization_granted", "fulfillment_granted", "effect_performed", "host_mutation_performed", "fan_pwm_write_performed", "thermal_actuation_performed", "power_profile_mutation_performed", "service_restart_performed", "file_cleanup_performed", "provider_invocation_performed", "network_performed", "prompt_assembly_performed"])
def test_validation_rejects_authority_effect_and_forbidden_flags(flag: str) -> None:
    contract = build_effect_receipt_contract(_rehearsal("inspect_cpu_pressure_candidate", cpu_utilization_percent=95))
    bad = replace(contract, **{flag: True}) if hasattr(contract, flag) else contract
    result = validate_effect_receipt_contract(bad)
    if hasattr(contract, flag):
        assert not result.ok


def test_source_rehearsal_claiming_effect_or_host_mutation_contradicts_readiness() -> None:
    rehearsal = replace(_rehearsal("inspect_cpu_pressure_candidate", cpu_utilization_percent=95), effect_not_performed=False)
    wing = build_execution_proof_wing_for_rehearsal_receipt(rehearsal)
    assert wing.execution_readiness_manifest.readiness_status == "execution_readiness_contradicted"


def test_missing_proof_gates_produce_incomplete_readiness() -> None:
    contract = build_effect_receipt_contract(_rehearsal("inspect_cpu_pressure_candidate", cpu_utilization_percent=95))
    future = build_future_effect_receipt_schema(contract)
    post = build_postcondition_check_plan(contract)
    rollback = build_rollback_plan(contract)
    manifest = build_execution_readiness_manifest(contract, future, post, rollback, satisfied_proof_gates=("audit_receipt_required",))
    assert manifest.readiness_status == "execution_readiness_incomplete"
    assert manifest.missing_proof_gates
    assert validate_execution_readiness_manifest(manifest).ok


def test_full_non_mutating_pipeline_from_collector_to_execution_readiness() -> None:
    from sentientos.host_collectors import collect_thermal_sensor_observation
    from sentientos.host_resource_governor import build_host_resource_telemetry_from_collector_results, evaluate_host_resource_pressure
    from sentientos.host_resource_policy import build_host_resource_proposal_receipts, evaluate_host_resource_policy
    from sentientos.privilege_broker import build_privilege_broker_review_receipt, evaluate_privilege_broker_eligibility

    result = collect_thermal_sensor_observation(
        thermal_path="/thermal",
        directory_lister=lambda path: ("thermal_zone0",) if path == "/thermal" else (),
        text_reader=lambda path: "90000\n" if path.endswith("temp") else "x86_pkg_temp\n",
        observed_at="2026-01-01T00:00:00+00:00",
    )
    snapshot = build_host_resource_telemetry_from_collector_results((result,), snapshot_id="collector-snap")
    pressure = evaluate_host_resource_pressure(snapshot, thermal_pressure_c=80)
    decision = evaluate_host_resource_policy(pressure)
    proposal = {receipt.proposal_kind: receipt for receipt in build_host_resource_proposal_receipts(decision)}["future_cooling_policy_candidate"]
    broker = build_privilege_broker_review_receipt(evaluate_privilege_broker_eligibility(proposal))
    rehearsal = build_actuation_fulfillment_rehearsal_receipt(build_actuation_fulfillment_plan(broker))
    wing = build_execution_proof_wing_for_rehearsal_receipt(rehearsal)

    assert wing.effect_contract.effect_performed is False
    assert wing.execution_readiness_manifest.host_mutation_performed is False
    assert "fan_pwm_write_without_allowlist" in wing.execution_readiness_manifest.blocked_actions
    assert "thermal_actuation_without_policy" in wing.execution_readiness_manifest.blocked_actions
    assert "power_profile_mutation_without_policy" in wing.execution_readiness_manifest.blocked_actions
    assert "service_restart_without_authorization" in wing.execution_readiness_manifest.blocked_actions
    assert "file_cleanup_without_scope" in wing.execution_readiness_manifest.blocked_actions
    assert "provider_invocation" in wing.execution_readiness_manifest.blocked_actions
    assert "network_egress" in wing.execution_readiness_manifest.blocked_actions
    assert "prompt_assembly" in wing.execution_readiness_manifest.blocked_actions
    assert wing.execution_readiness_manifest.authorization_granted is False
