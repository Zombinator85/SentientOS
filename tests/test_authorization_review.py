from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.actuation_fulfillment import build_actuation_fulfillment_plan, build_actuation_fulfillment_rehearsal_receipt
from sentientos.authorization_review import (
    authorization_review_decision_digest,
    authorization_review_receipt_digest,
    build_authorization_review_packet,
    build_authorization_review_wing_for_execution_readiness,
    build_default_authorization_review_policy,
    build_future_authorization_grant_schema,
    evaluate_authorization_review,
    future_authorization_grant_schema_digest,
    summarize_authorization_review_decision,
    summarize_authorization_review_packet,
    summarize_authorization_review_receipt,
    summarize_future_authorization_grant_schema,
    validate_authorization_review_decision,
    validate_authorization_review_packet,
    validate_authorization_review_receipt,
    validate_future_authorization_grant_schema,
)
from sentientos.effect_proof import build_execution_proof_wing_for_rehearsal_receipt, build_execution_readiness_manifest
from sentientos.host_collectors import collect_fan_pwm_observation, collect_thermal_sensor_observation
from sentientos.host_resource_governor import build_host_resource_telemetry_from_collector_results, evaluate_host_resource_pressure
from sentientos.host_resource_policy import build_host_resource_proposal_receipts, evaluate_host_resource_policy
from sentientos.privilege_broker import build_privilege_broker_review_receipt, evaluate_privilege_broker_eligibility
from tests.test_actuation_fulfillment import _broker_receipt_for

pytestmark = pytest.mark.no_legacy_skip


def _manifest(kind: str, *, recorded: bool = False, **kwargs):
    rehearsal = build_actuation_fulfillment_rehearsal_receipt(build_actuation_fulfillment_plan(_broker_receipt_for(kind, recorded=recorded, **kwargs)))
    return build_execution_proof_wing_for_rehearsal_receipt(rehearsal).execution_readiness_manifest


def _wing(kind: str, *, recorded: bool = False, **kwargs):
    return build_authorization_review_wing_for_execution_readiness(_manifest(kind, recorded=recorded, **kwargs))


def test_valid_execution_readiness_manifest_builds_authorization_review_wing() -> None:
    wing = _wing("inspect_cpu_pressure_candidate", cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)
    assert wing.packet.packet_status == "authorization_review_packet_ready"
    assert wing.decision.decision_status == "authorization_review_eligible_for_operator_review"
    assert wing.receipt.receipt_status == "authorization_review_receipt_recorded"
    assert wing.future_authorization_grant_schema.schema_status == "future_authorization_grant_schema_ready"
    assert wing.decision.authorization_granted is False
    assert wing.decision.fulfillment_granted is False
    assert wing.receipt.authorization_not_granted is True
    assert wing.receipt.does_not_authorize_fulfillment is True
    assert wing.future_authorization_grant_schema.schema_only is True
    assert wing.future_authorization_grant_schema.future_use_only is True
    assert validate_authorization_review_packet(wing.packet).ok
    assert validate_authorization_review_decision(wing.decision).ok
    assert validate_authorization_review_receipt(wing.receipt).ok
    assert validate_future_authorization_grant_schema(wing.future_authorization_grant_schema).ok


@pytest.mark.parametrize(
    ("readiness_status", "expected"),
    [
        ("execution_readiness_blocked", "authorization_review_blocked"),
        ("execution_readiness_incomplete", "authorization_review_incomplete"),
        ("execution_readiness_contradicted", "authorization_review_contradicted"),
        ("execution_readiness_for_authorization_review_with_conditions", "authorization_review_eligible_with_conditions"),
    ],
)
def test_readiness_statuses_map_to_authorization_decisions(readiness_status: str, expected: str) -> None:
    manifest = replace(_manifest("inspect_cpu_pressure_candidate", cpu_utilization_percent=95), readiness_status=readiness_status)
    packet = build_authorization_review_packet(manifest)
    decision = evaluate_authorization_review(packet)
    assert decision.decision_status == expected


def test_future_cooling_requires_hardware_operator_policy_panic_control_audit_rollback_effect_postcondition_immutable_backend_bounds_cooldown() -> None:
    wing = _wing("future_cooling_policy_candidate", recorded=True, thermal_zone_temperatures_c={"cpu": 90}, cpu_utilization_percent=10, ram_utilization_percent=20, disk_utilization_percent=30)
    gates = set(wing.packet.required_authorization_gates)
    for gate in [
        "hardware_allowlist_required_for_future_action",
        "operator_or_policy_approval_required_for_future_action",
        "panic_stop_required_for_future_action",
        "control_plane_admission_required_for_future_action",
        "audit_receipt_required_for_future_action",
        "rollback_receipt_required_for_future_action",
        "effect_receipt_required_for_future_action",
        "postcondition_check_required_for_future_action",
        "immutable_trace_required_for_future_action",
        "os_backend_declaration_required_for_future_action",
        "bounds_policy_required_for_future_action",
        "cooldown_policy_required_for_future_action",
    ]:
        assert gate in gates
    assert wing.packet.approval_class == "future_hardware_safety_approval_required"
    assert {"fan_pwm_write", "thermal_actuation"}.issubset(set(wing.packet.blocked_actions))
    assert wing.decision.authorization_granted is False


def test_future_power_cleanup_and_service_require_domain_specific_authorization_gates() -> None:
    power = _wing("future_power_policy_candidate", recorded=True, battery_percent=5, battery_charging=False)
    cleanup = _wing("future_cleanup_policy_candidate", recorded=True, disk_utilization_percent=95)
    service_health = _wing("inspect_service_health_candidate", service_health_labels=("daemon_degraded",))
    service_manifest = replace(_manifest("inspect_service_health_candidate", service_health_labels=("daemon_degraded",)), effect_domain="future_service_effect")
    service = build_authorization_review_wing_for_execution_readiness(service_manifest)
    for gate in ["operator_or_policy_approval_required_for_future_action", "os_backend_declaration_required_for_future_action", "bounds_policy_required_for_future_action", "control_plane_admission_required_for_future_action", "audit_receipt_required_for_future_action", "rollback_receipt_required_for_future_action", "effect_receipt_required_for_future_action", "postcondition_check_required_for_future_action", "immutable_trace_required_for_future_action"]:
        assert gate in power.packet.required_authorization_gates
    for gate in ["filesystem_scope_required_for_future_action", "dry_run_rehearsal_evidence_required_for_future_action", "path_scope_labels_required_for_future_action", "control_plane_admission_required_for_future_action", "audit_receipt_required_for_future_action", "rollback_receipt_required_for_future_action", "effect_receipt_required_for_future_action", "postcondition_check_required_for_future_action"]:
        assert gate in cleanup.packet.required_authorization_gates
    for gate in ["service_scope_required_for_future_action", "runtime_supervisor_observation_required", "control_plane_admission_required_for_future_action", "audit_receipt_required_for_future_action", "rollback_receipt_required_for_future_action", "effect_receipt_required_for_future_action", "postcondition_check_required_for_future_action"]:
        assert gate in service.packet.required_authorization_gates
    assert "power_profile_mutation" in power.packet.blocked_actions
    assert {"file_cleanup", "file_delete"}.issubset(cleanup.packet.blocked_actions)
    assert {"service_restart", "process_kill"}.issubset(service.packet.blocked_actions)
    assert "runtime_supervisor_observation_required" in service_health.packet.required_authorization_gates


def test_diagnostics_and_operator_review_can_be_eligible_but_never_authorize() -> None:
    diagnostics = _wing("inspect_cpu_pressure_candidate", cpu_utilization_percent=95)
    operator_manifest = replace(_manifest("inspect_cpu_pressure_candidate", cpu_utilization_percent=95), effect_domain="operator_review")
    operator = build_authorization_review_wing_for_execution_readiness(operator_manifest)
    assert diagnostics.decision.decision_status == "authorization_review_eligible_for_operator_review"
    assert operator.decision.decision_status == "authorization_review_eligible_for_operator_review"
    for wing in [diagnostics, operator]:
        assert wing.packet.authorization_granted is False
        assert wing.decision.authorization_granted is False
        assert wing.receipt.authorization_not_granted is True
        assert wing.future_authorization_grant_schema.authorization_granted is False


@pytest.mark.parametrize("flag", ["authorization_granted", "fulfillment_granted", "effect_performed", "host_mutation_performed"])
def test_source_manifest_claiming_authority_or_effect_is_contradicted(flag: str) -> None:
    manifest = replace(_manifest("inspect_cpu_pressure_candidate", cpu_utilization_percent=95), **{flag: True})
    wing = build_authorization_review_wing_for_execution_readiness(manifest)
    assert wing.packet.packet_status == "authorization_review_packet_contradicted"
    assert wing.decision.decision_status == "authorization_review_contradicted"


def test_missing_required_gates_produce_incomplete_decision() -> None:
    manifest = _manifest("future_cooling_policy_candidate", recorded=True, thermal_zone_temperatures_c={"cpu": 90})
    manifest = replace(manifest, satisfied_proof_gates=tuple(g for g in manifest.satisfied_proof_gates if g != "panic_stop_required"))
    wing = build_authorization_review_wing_for_execution_readiness(manifest)
    assert "panic_stop_required_for_future_action" in wing.packet.missing_authorization_gates
    assert wing.decision.decision_status == "authorization_review_incomplete"


def test_digests_are_deterministic_and_change_on_meaningful_metadata() -> None:
    wing = _wing("inspect_cpu_pressure_candidate", cpu_utilization_percent=95)
    assert authorization_review_decision_digest(wing.decision) == authorization_review_decision_digest(wing.decision)
    assert authorization_review_decision_digest(replace(wing.decision, reason_codes=wing.decision.reason_codes + ("extra_reason",))) != authorization_review_decision_digest(wing.decision)
    assert authorization_review_receipt_digest(wing.receipt) == authorization_review_receipt_digest(wing.receipt)
    assert authorization_review_receipt_digest(replace(wing.receipt, evidence_summary=wing.receipt.evidence_summary + ("extra_evidence",), digest="")) != authorization_review_receipt_digest(wing.receipt)
    schema = wing.future_authorization_grant_schema
    assert future_authorization_grant_schema_digest(schema) == future_authorization_grant_schema_digest(schema)
    assert future_authorization_grant_schema_digest(replace(schema, required_scope_labels=schema.required_scope_labels + ("extra_scope",), digest="")) != future_authorization_grant_schema_digest(schema)


def test_summaries_are_metadata_only_and_schema_is_not_real_grant() -> None:
    wing = _wing("inspect_cpu_pressure_candidate", cpu_utilization_percent=95)
    assert summarize_authorization_review_packet(wing.packet)["metadata_only"] is True
    assert summarize_authorization_review_decision(wing.decision)["review_only"] is True
    assert summarize_authorization_review_receipt(wing.receipt)["authorization_not_granted"] is True
    schema_summary = summarize_future_authorization_grant_schema(wing.future_authorization_grant_schema)
    assert schema_summary["schema_only"] is True
    assert schema_summary["future_use_only"] is True
    assert schema_summary["authorization_granted"] is False


@pytest.mark.parametrize(
    "flag",
    [
        "authorization_granted", "fulfillment_granted", "effect_performed", "host_mutation_performed",
        "fan_pwm_write_performed", "thermal_actuation_performed", "power_profile_mutation_performed",
        "service_restart_performed", "file_cleanup_performed", "provider_invocation_performed", "network_performed",
        "prompt_assembly_performed",
    ],
)
def test_validation_rejects_forbidden_authority_and_effect_flags(flag: str) -> None:
    decision = replace(_wing("inspect_cpu_pressure_candidate", cpu_utilization_percent=95).decision, **{flag: True})
    result = validate_authorization_review_decision(decision)
    assert not result.ok
    assert any(flag in finding for finding in result.findings)


def test_integration_pipeline_to_authorization_review_remains_non_mutating() -> None:
    tree = {"/thermal": ("thermal_zone0",), "/thermal/thermal_zone0": ("type", "temp"), "/hwmon": ("hwmon0",), "/hwmon/hwmon0": ("name", "pwm1", "fan1_input")}
    files = {"/thermal/thermal_zone0/type": "cpu\n", "/thermal/thermal_zone0/temp": "90000\n", "/hwmon/hwmon0/name": "test\n", "/hwmon/hwmon0/pwm1": "120\n", "/hwmon/hwmon0/fan1_input": "1400\n"}
    results = (
        collect_thermal_sensor_observation(thermal_path="/thermal", hwmon_path="/empty", directory_lister=lambda path: tree.get(path, ()), text_reader=lambda path: files[path], observed_at="2026-01-01T00:00:00+00:00"),
        collect_fan_pwm_observation(hwmon_path="/hwmon", directory_lister=lambda path: tree.get(path, ()), text_reader=lambda path: files[path], observed_at="2026-01-01T00:00:00+00:00"),
    )
    snapshot = build_host_resource_telemetry_from_collector_results(results, snapshot_id="collector-snap")
    report = evaluate_host_resource_pressure(snapshot, thermal_pressure_c=85)
    policy_decision = evaluate_host_resource_policy(report)
    proposal_receipts = build_host_resource_proposal_receipts(policy_decision)
    broker_decisions = tuple(evaluate_privilege_broker_eligibility(replace(receipt, proposal_status="host_resource_proposal_recorded", digest="") if receipt.proposal_kind == "future_cooling_policy_candidate" else receipt) for receipt in proposal_receipts)
    broker_receipts = tuple(build_privilege_broker_review_receipt(decision) for decision in broker_decisions)
    rehearsals = tuple(build_actuation_fulfillment_rehearsal_receipt(build_actuation_fulfillment_plan(receipt)) for receipt in broker_receipts)
    execution_wings = tuple(build_execution_proof_wing_for_rehearsal_receipt(receipt) for receipt in rehearsals)
    authorization_wings = tuple(build_authorization_review_wing_for_execution_readiness(wing.execution_readiness_manifest) for wing in execution_wings)
    assert authorization_wings
    for wing in authorization_wings:
        decision = wing.decision
        assert decision.authorization_granted is False
        assert decision.fulfillment_granted is False
        assert decision.effect_performed is False
        assert decision.host_mutation_performed is False
        assert decision.fan_pwm_write_performed is False
        assert decision.thermal_actuation_performed is False
        assert decision.power_profile_mutation_performed is False
        assert decision.service_restart_performed is False
        assert decision.file_cleanup_performed is False
        assert getattr(decision, "file_delete_performed", False) is False
        assert decision.provider_invocation_performed is False
        assert decision.network_performed is False
        assert decision.prompt_assembly_performed is False


def test_policy_mapping_is_deterministic() -> None:
    policy = build_default_authorization_review_policy()
    assert policy.domain_approval_classes["future_cooling_authorization_review"] == "future_hardware_safety_approval_required"
    assert "cooldown_policy_required_for_future_action" in policy.domain_required_gates["future_cooling_authorization_review"]
