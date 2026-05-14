from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.host_resource_governor import build_host_resource_telemetry_snapshot, evaluate_host_resource_pressure
from sentientos.host_resource_policy import (
    build_host_resource_proposal_receipts,
    evaluate_host_resource_policy,
    evaluate_privilege_broker_for_host_resource_receipts,
)
from sentientos.privilege_broker import (
    CLEANUP_POLICY_GATES,
    COOLING_POLICY_GATES,
    POWER_POLICY_GATES,
    build_privilege_broker_review_receipt,
    evaluate_privilege_broker_eligibility,
    privilege_broker_decision_digest,
    privilege_broker_receipt_digest,
    summarize_privilege_broker_eligibility_decision,
    summarize_privilege_broker_review_receipt,
    validate_privilege_broker_eligibility_decision,
    validate_privilege_broker_review_receipt,
)

pytestmark = pytest.mark.no_legacy_skip


def _receipt_for(**snapshot_kwargs):
    snapshot = build_host_resource_telemetry_snapshot(snapshot_id="broker-snap", **snapshot_kwargs)
    report = evaluate_host_resource_pressure(snapshot, thermal_pressure_c=85)
    decision = evaluate_host_resource_policy(report)
    return {receipt.proposal_kind: receipt for receipt in build_host_resource_proposal_receipts(decision)}


def _recorded(receipt):
    return replace(receipt, proposal_status="host_resource_proposal_recorded", digest="")


def test_inspect_pressure_receipts_become_eligible_for_future_review() -> None:
    cases = [
        (_receipt_for(cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)["inspect_cpu_pressure_candidate"], "resource_pressure_review"),
        (_receipt_for(cpu_utilization_percent=10, ram_utilization_percent=95, disk_utilization_percent=30)["inspect_memory_pressure_candidate"], "resource_pressure_review"),
        (_receipt_for(cpu_utilization_percent=10, ram_utilization_percent=20, disk_utilization_percent=95)["inspect_disk_pressure_candidate"], "disk_safety_review"),
        (_receipt_for(cpu_utilization_percent=10, ram_utilization_percent=20, disk_utilization_percent=30, thermal_zone_temperatures_c={"cpu": 90})["inspect_thermal_state_candidate"], "thermal_safety_review"),
    ]
    for receipt, domain in cases:
        decision = evaluate_privilege_broker_eligibility(receipt)
        assert decision.eligibility_status == "privilege_broker_eligible_for_future_review"
        assert decision.privilege_domain == domain
        assert decision.authorization_granted is False
        assert decision.fulfillment_granted is False
        assert decision.host_mutation_performed is False
        assert validate_privilege_broker_eligibility_decision(decision).ok


def test_future_cleanup_candidate_requires_dry_run_path_operator_audit_rollback_and_fulfillment_gates() -> None:
    receipt = _receipt_for(cpu_utilization_percent=10, ram_utilization_percent=20, disk_utilization_percent=95)["future_cleanup_policy_candidate"]
    decision = evaluate_privilege_broker_eligibility(_recorded(receipt))
    assert decision.eligibility_status == "privilege_broker_eligible_with_conditions"
    for gate in CLEANUP_POLICY_GATES:
        assert gate in decision.required_future_gates
    assert "file_path_scope_declaration_required" in decision.required_future_gates
    assert "file_delete" in decision.blocked_actions
    assert decision.fulfillment_granted is False


def test_future_cooling_candidate_never_direct_fulfillment_and_requires_all_cooling_gates() -> None:
    receipt = _receipt_for(cpu_utilization_percent=10, ram_utilization_percent=20, disk_utilization_percent=30, thermal_zone_temperatures_c={"cpu": 90})["future_cooling_policy_candidate"]
    decision = evaluate_privilege_broker_eligibility(_recorded(receipt))
    assert decision.eligibility_status == "privilege_broker_eligible_with_conditions"
    assert decision.eligibility_status != "privilege_broker_eligible_for_future_review"
    for gate in COOLING_POLICY_GATES:
        assert gate in decision.required_future_gates
    assert "fan_pwm_write" in decision.blocked_actions
    assert "thermal_actuation" in decision.blocked_actions
    assert decision.fan_pwm_write_performed is False
    assert decision.thermal_actuation_performed is False
    assert decision.fulfillment_granted is False


def test_future_power_candidate_requires_backend_policy_operator_audit_rollback_and_fulfillment_gates() -> None:
    receipt = _receipt_for(cpu_utilization_percent=10, ram_utilization_percent=20, disk_utilization_percent=30, battery_percent=5, battery_charging=False)["future_power_policy_candidate"]
    decision = evaluate_privilege_broker_eligibility(_recorded(receipt))
    assert decision.eligibility_status == "privilege_broker_eligible_with_conditions"
    for gate in POWER_POLICY_GATES:
        assert gate in decision.required_future_gates
    assert "power_profile_mutation" in decision.blocked_actions


def test_inspect_service_health_is_review_only_and_does_not_grant_restart() -> None:
    receipt = _receipt_for(cpu_utilization_percent=10, ram_utilization_percent=20, disk_utilization_percent=30, service_health_labels=("daemon_degraded",))["inspect_service_health_candidate"]
    decision = evaluate_privilege_broker_eligibility(receipt)
    review = build_privilege_broker_review_receipt(decision)
    assert decision.eligibility_status == "privilege_broker_eligible_for_future_review"
    assert decision.privilege_domain == "service_health_review"
    assert "service_restart" in decision.blocked_actions
    assert decision.service_restart_performed is False
    assert review.does_not_authorize_fulfillment is True


def test_blocked_incomplete_and_contradicted_source_statuses_do_not_become_eligible() -> None:
    receipt = _receipt_for(cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)["inspect_cpu_pressure_candidate"]
    assert evaluate_privilege_broker_eligibility(replace(receipt, proposal_status="host_resource_proposal_blocked", digest="")).eligibility_status == "privilege_broker_blocked"
    assert evaluate_privilege_broker_eligibility(replace(receipt, proposal_status="host_resource_proposal_incomplete", digest="")).eligibility_status == "privilege_broker_incomplete"
    assert evaluate_privilege_broker_eligibility(replace(receipt, proposal_status="host_resource_proposal_contradicted", digest="")).eligibility_status == "privilege_broker_contradicted"


def test_source_receipt_claiming_effects_or_missing_gates_is_rejected() -> None:
    receipt = _receipt_for(cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)["inspect_cpu_pressure_candidate"]
    assert evaluate_privilege_broker_eligibility(replace(receipt, does_not_execute=False, digest="")).eligibility_status == "privilege_broker_contradicted"
    assert evaluate_privilege_broker_eligibility(replace(receipt, does_not_mutate_host=False, digest="")).eligibility_status == "privilege_broker_contradicted"
    missing_gates = replace(receipt, required_future_gates=(), digest="")
    blocked = evaluate_privilege_broker_eligibility(missing_gates)
    assert blocked.eligibility_status == "privilege_broker_blocked"
    assert "source_receipt_missing_future_gates" in blocked.missing_prerequisites


def test_digests_are_deterministic_and_summaries_are_metadata_only() -> None:
    receipt = _receipt_for(cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)["inspect_cpu_pressure_candidate"]
    first = evaluate_privilege_broker_eligibility(receipt)
    second = evaluate_privilege_broker_eligibility(receipt)
    assert privilege_broker_decision_digest(first) == privilege_broker_decision_digest(second)
    review_first = build_privilege_broker_review_receipt(first)
    review_second = build_privilege_broker_review_receipt(second)
    assert privilege_broker_receipt_digest(review_first) == privilege_broker_receipt_digest(review_second)
    decision_summary = summarize_privilege_broker_eligibility_decision(first)
    receipt_summary = summarize_privilege_broker_review_receipt(review_first)
    assert decision_summary["metadata_only"] is True
    assert decision_summary["eligibility_only"] is True
    assert decision_summary["authorization_granted"] is False
    assert decision_summary["fulfillment_granted"] is False
    assert receipt_summary["review_only"] is True
    assert receipt_summary["does_not_authorize_fulfillment"] is True
    assert validate_privilege_broker_review_receipt(review_first).ok


@pytest.mark.parametrize(
    "field",
    [
        "authorization_granted",
        "fulfillment_granted",
        "host_mutation_performed",
        "fan_pwm_write_performed",
        "thermal_actuation_performed",
        "process_kill_performed",
        "service_restart_performed",
        "package_install_performed",
        "driver_install_performed",
        "provider_invocation_performed",
        "network_performed",
        "prompt_assembly_performed",
    ],
)
def test_validation_rejects_forbidden_decision_flags(field: str) -> None:
    receipt = _receipt_for(cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)["inspect_cpu_pressure_candidate"]
    decision = evaluate_privilege_broker_eligibility(receipt)
    result = validate_privilege_broker_eligibility_decision(replace(decision, **{field: True}))
    assert not result.ok
    assert f"forbidden_decision_flag:{field}" in result.findings


def test_pipeline_integration_from_telemetry_through_broker_review_receipts() -> None:
    snapshot = build_host_resource_telemetry_snapshot(
        snapshot_id="pipeline",
        cpu_utilization_percent=95,
        ram_utilization_percent=20,
        disk_utilization_percent=95,
        thermal_zone_temperatures_c={"cpu": 90},
        fan_rpm_observations={"fan0": 1200},
        service_health_labels=("daemon_degraded",),
    )
    report = evaluate_host_resource_pressure(snapshot, thermal_pressure_c=85)
    policy_decision = evaluate_host_resource_policy(report)
    proposal_receipts = build_host_resource_proposal_receipts(policy_decision)
    broker_decisions, review_receipts = evaluate_privilege_broker_for_host_resource_receipts(proposal_receipts)
    assert len(broker_decisions) == len(proposal_receipts)
    assert len(review_receipts) == len(proposal_receipts)
    cooling = [decision for decision in broker_decisions if decision.source_proposal_kind == "future_cooling_policy_candidate"][0]
    service = [decision for decision in broker_decisions if decision.source_proposal_kind == "inspect_service_health_candidate"][0]
    assert "fan_pwm_write" in cooling.blocked_actions
    assert "thermal_actuation" in cooling.blocked_actions
    assert cooling.fan_pwm_write_performed is False
    assert "service_restart" in service.blocked_actions
    assert service.service_restart_performed is False
    assert all(validate_privilege_broker_review_receipt(receipt).ok for receipt in review_receipts)


def test_capability_registry_reflects_privilege_broker_without_actuation_fulfillment() -> None:
    from sentientos.capability_registry import build_default_capability_registry, update_registry_from_privilege_broker_decision, validate_capability_registry

    receipt = _receipt_for(cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)["inspect_cpu_pressure_candidate"]
    decision = evaluate_privilege_broker_eligibility(receipt)
    review = build_privilege_broker_review_receipt(decision)
    registry = update_registry_from_privilege_broker_decision(build_default_capability_registry(), decision, (review,))
    records = registry.by_id()
    assert records["privilege_broker"].status == "implemented"
    assert records["privilege_broker"].authority_level == "eligibility_only"
    assert records["privilege_broker"].host_actuation_performed is False
    assert records["actuation_fulfillment"].status == "implemented"
    assert records["direct_fan_pwm_thermal_control"].status == "blocked"
    assert validate_capability_registry(registry).ok
