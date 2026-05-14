from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from sentientos.actuation_fulfillment import (
    BASE_REQUIRED_GATES,
    REQUIRED_FUTURE_GATES,
    actuation_fulfillment_plan_digest,
    actuation_fulfillment_rehearsal_receipt_digest,
    build_actuation_fulfillment_plan,
    build_actuation_fulfillment_rehearsal_receipt,
    build_actuation_rehearsals_for_broker_receipts,
    summarize_actuation_fulfillment_plan,
    summarize_actuation_fulfillment_rehearsal_receipt,
    validate_actuation_fulfillment_plan,
    validate_actuation_fulfillment_rehearsal_receipt,
)
from sentientos.capability_registry import (
    build_default_capability_registry,
    update_registry_from_actuation_rehearsal_receipt,
    validate_capability_registry,
)
from sentientos.host_collectors import collect_fan_pwm_observation, collect_thermal_sensor_observation
from sentientos.host_resource_governor import build_host_resource_telemetry_from_collector_results, build_host_resource_telemetry_snapshot, evaluate_host_resource_pressure
from sentientos.host_resource_policy import build_host_resource_proposal_receipts, evaluate_host_resource_policy
from sentientos.privilege_broker import (
    COOLING_POLICY_GATES,
    POWER_POLICY_GATES,
    build_privilege_broker_review_receipt,
    evaluate_privilege_broker_eligibility,
)

pytestmark = pytest.mark.no_legacy_skip


def _broker_receipt_for(kind: str, *, recorded: bool = False, **snapshot_kwargs):
    snapshot = build_host_resource_telemetry_snapshot(snapshot_id=f"snap-{kind}", observed_at="2026-01-01T00:00:00+00:00", **snapshot_kwargs)
    report = evaluate_host_resource_pressure(snapshot, thermal_pressure_c=85)
    decision = evaluate_host_resource_policy(report)
    receipt = {receipt.proposal_kind: receipt for receipt in build_host_resource_proposal_receipts(decision)}[kind]
    if recorded:
        receipt = replace(receipt, proposal_status="host_resource_proposal_recorded", digest="")
    broker_decision = evaluate_privilege_broker_eligibility(receipt)
    return build_privilege_broker_review_receipt(broker_decision)


def test_eligible_inspect_cpu_creates_resource_rehearsal_plan() -> None:
    receipt = _broker_receipt_for("inspect_cpu_pressure_candidate", cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)
    plan = build_actuation_fulfillment_plan(receipt)
    rehearsal = build_actuation_fulfillment_rehearsal_receipt(plan)
    assert plan.plan_status == "actuation_fulfillment_plan_rehearsal_ready"
    assert plan.fulfillment_domain == "resource_pressure_review"
    assert plan.backend_class == "diagnostic_backend_future"
    assert plan.authorization_granted is False
    assert plan.fulfillment_granted is False
    assert validate_actuation_fulfillment_plan(plan).ok
    assert rehearsal.rehearsal_status == "actuation_fulfillment_rehearsal_recorded"
    assert rehearsal.effect_not_performed is True
    assert validate_actuation_fulfillment_rehearsal_receipt(rehearsal).ok


def test_eligible_with_conditions_future_cooling_preserves_gates_and_blocks_control() -> None:
    receipt = _broker_receipt_for("future_cooling_policy_candidate", recorded=True, cpu_utilization_percent=10, ram_utilization_percent=20, disk_utilization_percent=30, thermal_zone_temperatures_c={"cpu": 90})
    plan = build_actuation_fulfillment_plan(receipt)
    assert plan.plan_status == "actuation_fulfillment_plan_rehearsal_ready_with_conditions"
    assert plan.fulfillment_domain == "future_cooling_rehearsal"
    assert plan.backend_class == "cooling_backend_future"
    for gate in COOLING_POLICY_GATES:
        assert gate in plan.required_future_gates
    for gate in REQUIRED_FUTURE_GATES:
        assert gate in plan.required_future_gates
    assert "fan_pwm_write" in plan.blocked_actions
    assert "thermal_actuation" in plan.blocked_actions
    assert plan.fan_pwm_write_performed is False
    assert plan.thermal_actuation_performed is False


def test_future_power_rehearsal_keeps_power_profile_mutation_blocked() -> None:
    receipt = _broker_receipt_for("future_power_policy_candidate", recorded=True, cpu_utilization_percent=10, ram_utilization_percent=20, disk_utilization_percent=30, battery_percent=5, battery_charging=False)
    plan = build_actuation_fulfillment_plan(receipt)
    assert plan.fulfillment_domain == "future_power_rehearsal"
    assert plan.backend_class == "power_backend_future"
    for gate in POWER_POLICY_GATES:
        assert gate in plan.required_future_gates
    assert "power_profile_mutation" in plan.blocked_actions
    assert plan.power_profile_mutation_performed is False


def test_future_cleanup_rehearsal_keeps_file_cleanup_blocked() -> None:
    receipt = _broker_receipt_for("future_cleanup_policy_candidate", recorded=True, cpu_utilization_percent=10, ram_utilization_percent=20, disk_utilization_percent=95)
    plan = build_actuation_fulfillment_plan(receipt)
    assert plan.fulfillment_domain == "future_cleanup_rehearsal"
    assert plan.backend_class == "cleanup_backend_future"
    assert {"file_cleanup", "file_delete", "disk_cleanup_mutation"}.issubset(plan.blocked_actions)
    assert plan.file_cleanup_performed is False


def test_service_health_rehearsal_keeps_service_restart_blocked() -> None:
    receipt = _broker_receipt_for("inspect_service_health_candidate", cpu_utilization_percent=10, ram_utilization_percent=20, disk_utilization_percent=30, service_health_labels=("daemon_degraded",))
    plan = build_actuation_fulfillment_plan(receipt)
    assert plan.fulfillment_domain == "service_health_review"
    assert plan.backend_class == "service_backend_future"
    assert "service_restart" in plan.blocked_actions
    assert plan.service_restart_performed is False


@pytest.mark.parametrize(
    ("broker_status", "plan_status"),
    [
        ("privilege_broker_blocked", "actuation_fulfillment_plan_blocked"),
        ("privilege_broker_incomplete", "actuation_fulfillment_plan_incomplete"),
        ("privilege_broker_contradicted", "actuation_fulfillment_plan_contradicted"),
    ],
)
def test_noneligible_broker_receipts_map_to_nonready_plans(broker_status: str, plan_status: str) -> None:
    receipt = _broker_receipt_for("inspect_cpu_pressure_candidate", cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)
    receipt = replace(receipt, eligibility_status=broker_status, review_status="privilege_broker_receipt_blocked", digest="")
    plan = build_actuation_fulfillment_plan(receipt)
    assert plan.plan_status == plan_status


@pytest.mark.parametrize("flag", ["authorization_granted", "fulfillment_granted", "host_mutation_performed"])
def test_source_broker_receipt_claiming_effect_or_authority_is_contradicted(flag: str) -> None:
    receipt = _broker_receipt_for("inspect_cpu_pressure_candidate", cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)
    data = receipt.to_dict()
    data[flag] = True
    source = SimpleNamespace(**data)
    plan = build_actuation_fulfillment_plan(source)
    assert plan.plan_status == "actuation_fulfillment_plan_contradicted"
    assert any("source_broker_receipt_claims_forbidden" in item for item in plan.missing_prerequisites)


def test_missing_required_future_gates_produces_incomplete_plan() -> None:
    receipt = _broker_receipt_for("future_cooling_policy_candidate", recorded=True, cpu_utilization_percent=10, ram_utilization_percent=20, disk_utilization_percent=30, thermal_zone_temperatures_c={"cpu": 90})
    receipt = replace(receipt, required_future_gates=tuple(gate for gate in receipt.required_future_gates if gate != "hardware_allowlist_required"), digest="")
    plan = build_actuation_fulfillment_plan(receipt)
    assert plan.plan_status == "actuation_fulfillment_plan_incomplete"
    assert "receipt_digest_mismatch" in plan.missing_prerequisites or "broker_condition_gates_missing" in plan.reason_codes


def test_plan_digest_deterministic_and_changes_on_metadata() -> None:
    receipt = _broker_receipt_for("inspect_cpu_pressure_candidate", cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)
    first = build_actuation_fulfillment_plan(receipt)
    second = build_actuation_fulfillment_plan(receipt)
    assert actuation_fulfillment_plan_digest(first) == actuation_fulfillment_plan_digest(second)
    changed = replace(first, warning_codes=first.warning_codes + ("extra_warning",))
    assert actuation_fulfillment_plan_digest(changed) != actuation_fulfillment_plan_digest(first)


def test_rehearsal_receipt_digest_deterministic_and_changes_on_metadata() -> None:
    receipt = _broker_receipt_for("inspect_cpu_pressure_candidate", cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)
    plan = build_actuation_fulfillment_plan(receipt)
    first = build_actuation_fulfillment_rehearsal_receipt(plan)
    second = build_actuation_fulfillment_rehearsal_receipt(plan)
    assert first.digest == second.digest
    changed = replace(first, warning_codes=first.warning_codes + ("extra_warning",), digest="")
    assert actuation_fulfillment_rehearsal_receipt_digest(changed) != first.digest


def test_plan_and_rehearsal_summaries_are_metadata_only() -> None:
    receipt = _broker_receipt_for("inspect_cpu_pressure_candidate", cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)
    plan = build_actuation_fulfillment_plan(receipt)
    rehearsal = build_actuation_fulfillment_rehearsal_receipt(plan)
    plan_summary = summarize_actuation_fulfillment_plan(plan)
    rehearsal_summary = summarize_actuation_fulfillment_rehearsal_receipt(rehearsal)
    assert plan_summary["metadata_only"] is True
    assert plan_summary["rehearsal_only"] is True
    assert plan_summary["authorization_granted"] is False
    assert plan_summary["fulfillment_granted"] is False
    assert plan_summary["host_mutation_performed"] is False
    assert rehearsal_summary["rehearsal_only"] is True
    assert rehearsal_summary["dry_run_only"] is True
    assert rehearsal_summary["effect_not_performed"] is True


@pytest.mark.parametrize(
    "field",
    [
        "authorization_granted",
        "fulfillment_granted",
        "host_mutation_performed",
        "fan_pwm_write_performed",
        "thermal_actuation_performed",
        "power_profile_mutation_performed",
        "process_kill_performed",
        "service_restart_performed",
        "package_install_performed",
        "driver_install_performed",
        "file_cleanup_performed",
        "provider_invocation_performed",
        "network_performed",
        "prompt_assembly_performed",
    ],
)
def test_validation_rejects_plan_forbidden_flags(field: str) -> None:
    receipt = _broker_receipt_for("inspect_cpu_pressure_candidate", cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)
    plan = build_actuation_fulfillment_plan(receipt)
    bad = replace(plan, **{field: True})
    result = validate_actuation_fulfillment_plan(bad)
    assert not result.ok
    assert f"plan_forbidden_flag:{field}" in result.findings


def test_validation_rejects_rehearsal_receipt_claiming_effect_performed() -> None:
    receipt = _broker_receipt_for("inspect_cpu_pressure_candidate", cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)
    plan = build_actuation_fulfillment_plan(receipt)
    rehearsal = build_actuation_fulfillment_rehearsal_receipt(plan)
    bad = replace(rehearsal, effect_not_performed=False)
    result = validate_actuation_fulfillment_rehearsal_receipt(bad)
    assert not result.ok
    assert "receipt_claims_effect_or_missing_gate:effect_not_performed" in result.findings


def test_fake_collectors_to_fulfillment_rehearsal_pipeline_is_non_mutating() -> None:
    tree = {"/thermal": ("thermal_zone0",), "/hwmon": ("hwmon0",), "/hwmon/hwmon0": ("fan1_input", "pwm1")}
    files = {"/thermal/thermal_zone0/temp": "90000\n", "/thermal/thermal_zone0/type": "cpu\n", "/hwmon/hwmon0/fan1_input": "1400\n", "/hwmon/hwmon0/pwm1": "128\n"}
    results = (
        collect_thermal_sensor_observation(thermal_path="/thermal", hwmon_path="/empty", directory_lister=lambda path: tree.get(path, ()), text_reader=lambda path: files[path], observed_at="2026-01-01T00:00:00+00:00"),
        collect_fan_pwm_observation(hwmon_path="/hwmon", directory_lister=lambda path: tree.get(path, ()), text_reader=lambda path: files[path], observed_at="2026-01-01T00:00:00+00:00"),
    )
    snapshot = build_host_resource_telemetry_from_collector_results(results, snapshot_id="collector-snap")
    report = evaluate_host_resource_pressure(snapshot, thermal_pressure_c=85)
    decision = evaluate_host_resource_policy(report)
    proposal_receipts = build_host_resource_proposal_receipts(decision)
    broker_decisions = tuple(evaluate_privilege_broker_eligibility(replace(receipt, proposal_status="host_resource_proposal_recorded", digest="") if receipt.proposal_kind == "future_cooling_policy_candidate" else receipt) for receipt in proposal_receipts)
    broker_receipts = tuple(build_privilege_broker_review_receipt(decision) for decision in broker_decisions)
    plans, rehearsals = build_actuation_rehearsals_for_broker_receipts(broker_receipts)
    cooling_plans = [plan for plan in plans if plan.fulfillment_domain == "future_cooling_rehearsal"]
    assert cooling_plans
    assert all(plan.host_mutation_performed is False for plan in plans)
    assert all(plan.fan_pwm_write_performed is False for plan in plans)
    assert all(plan.thermal_actuation_performed is False for plan in plans)
    assert all(receipt.does_not_mutate_host is True and receipt.effect_not_performed is True for receipt in rehearsals)


def test_service_degraded_pipeline_rehearses_service_health_not_restart() -> None:
    receipt = _broker_receipt_for("inspect_service_health_candidate", cpu_utilization_percent=10, ram_utilization_percent=20, disk_utilization_percent=30, service_health_labels=("daemon_degraded",))
    plans, rehearsals = build_actuation_rehearsals_for_broker_receipts((receipt,))
    assert plans[0].fulfillment_domain == "service_health_review"
    assert "service_restart" in plans[0].blocked_actions
    assert rehearsals[0].does_not_execute is True


def test_capability_registry_reflects_rehearsal_only_and_real_actuation_deferred() -> None:
    receipt = _broker_receipt_for("inspect_cpu_pressure_candidate", cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)
    plan = build_actuation_fulfillment_plan(receipt)
    rehearsal = build_actuation_fulfillment_rehearsal_receipt(plan)
    registry = update_registry_from_actuation_rehearsal_receipt(build_default_capability_registry(), rehearsal)
    records = registry.by_id()
    assert records["actuation_fulfillment"].status == "implemented"
    assert records["actuation_fulfillment"].authority_level == "rehearsal_only"
    assert records["actuation_fulfillment"].host_actuation_performed is False
    assert records["real_actuation_fulfillment"].status == "deferred"
    assert records["direct_fan_pwm_thermal_control"].status == "blocked"
    assert validate_capability_registry(registry).ok
