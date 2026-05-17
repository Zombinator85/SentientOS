from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile

import pytest

from sentientos.capability_registry import (
    CapabilityRecord,
    CapabilityRegistry,
    build_default_capability_registry,
    capability_registry_digest,
    replace_capability_record,
    summarize_capability_registry,
    validate_capability_registry,
)

pytestmark = pytest.mark.no_legacy_skip


def test_default_registry_builds_deterministically_and_validates() -> None:
    first = build_default_capability_registry()
    second = build_default_capability_registry()
    assert capability_registry_digest(first) == capability_registry_digest(second)
    assert validate_capability_registry(first).ok
    assert first.metadata_only is True


def test_summary_shape_is_metadata_only_and_digest_changes_on_metadata() -> None:
    registry = build_default_capability_registry()
    summary = summarize_capability_registry(registry)
    assert summary["metadata_only"] is True
    assert summary["no_runtime_authority_expansion"] is True
    assert "direct_fan_pwm_thermal_control" in summary["capability_ids"]
    changed = replace_capability_record(registry, "host_resource_telemetry", status="implemented")
    assert capability_registry_digest(changed) != summary["digest"]


def test_direct_fan_pwm_is_deferred_or_blocked_not_implemented() -> None:
    record = build_default_capability_registry().by_id()["direct_fan_pwm_thermal_control"]
    assert record.status in {"blocked", "deferred"}
    assert record.host_actuation_performed is False
    assert "fan/PWM writes" in record.deferred_surfaces


def test_hardware_driver_awareness_references_driver_manager() -> None:
    record = build_default_capability_registry().by_id()["hardware_driver_awareness"]
    assert record.status in {"implemented", "partial"}
    assert "sentientos/daemons/driver_manager.py" in record.source_paths
    assert "driver installation" in record.deferred_surfaces


def test_gui_and_browser_interaction_implemented_but_gated() -> None:
    records = build_default_capability_registry().by_id()
    for capability_id in ("gui_host_interaction", "browser_host_interaction"):
        record = records[capability_id]
        assert record.status == "implemented"
        assert record.authority_level == "gated_host_interaction"
        assert record.requires_control_plane_admission is True
        assert record.requires_operator_approval is True
        assert record.requires_panic_stop is True
        assert record.requires_audit_receipt is True
        assert record.host_actuation_performed is False


def test_federation_evidence_is_implemented_but_not_transport_adoption_or_sync() -> None:
    records = build_default_capability_registry().by_id()
    evidence = records["federation_evidence_custody"]
    transport = records["federation_transport_sync_adoption"]
    assert evidence.status == "implemented"
    assert evidence.authority_level == "federation_evidence"
    assert {"transport", "sync", "adoption"}.issubset(set(evidence.deferred_surfaces))
    assert transport.status in {"blocked", "deferred"}


def test_provider_invocation_remains_blocked_or_deferred() -> None:
    record = build_default_capability_registry().by_id()["provider_invocation"]
    assert record.status in {"blocked", "deferred"}
    assert record.provider_required is False
    assert record.network_required is False
    assert record.prompt_assembly_required is False
    assert "provider invocation" in record.deferred_surfaces


def test_validation_rejects_unsupported_implemented_host_actuation_without_requirements() -> None:
    registry = CapabilityRegistry(
        registry_id="bad",
        records=(
            CapabilityRecord(
                capability_id="bad_actuation",
                category="host_resource_telemetry",
                status="implemented",
                authority_level="observation",
                host_actuation_performed=True,
            ),
        ),
    )
    result = validate_capability_registry(registry)
    assert not result.ok
    assert any("host_actuation" in finding for finding in result.findings)


def test_validation_rejects_fan_pwm_implemented_claim_without_source_or_proof() -> None:
    registry = CapabilityRegistry(
        registry_id="bad",
        records=(
            CapabilityRecord(
                capability_id="bad_fan",
                category="host_resource_telemetry",
                status="implemented",
                authority_level="privileged_host_action",
                implemented_surfaces=("fan/PWM actuation",),
                host_actuation_performed=True,
                requires_control_plane_admission=True,
                requires_operator_approval=True,
                requires_panic_stop=True,
                requires_audit_receipt=True,
                requires_rollback_receipt=True,
            ),
        ),
    )
    result = validate_capability_registry(registry)
    assert not result.ok
    assert any("fan_pwm" in finding for finding in result.findings)


def test_validation_rejects_provider_network_prompt_authority_claims() -> None:
    base = build_default_capability_registry().by_id()["local_model_chat"]
    bad = replace(base, provider_required=True)
    result = validate_capability_registry(CapabilityRegistry(registry_id="bad", records=(bad,)))
    assert not result.ok
    assert any("provider_network_prompt" in finding for finding in result.findings)


def test_validation_rejects_federation_evidence_as_transport() -> None:
    bad = CapabilityRecord(
        capability_id="bad_federation",
        category="federation_evidence",
        status="implemented",
        authority_level="federation_evidence",
        implemented_surfaces=("transport and adoption",),
    )
    result = validate_capability_registry(CapabilityRegistry(registry_id="bad", records=(bad,)))
    assert not result.ok
    assert any("federation_evidence" in finding for finding in result.findings)


def test_registry_updates_from_collector_backed_inventory_and_resource_report_without_control() -> None:
    from sentientos.capability_registry import update_registry_from_host_inventory, update_registry_from_host_resource_report
    from sentientos.host_collectors import collect_fan_pwm_observation
    from sentientos.host_inventory import build_host_inventory_from_collector_results
    from sentientos.host_resource_governor import build_host_resource_telemetry_from_collector_results, evaluate_host_resource_pressure

    tree = {"/hwmon": ("hwmon0",), "/hwmon/hwmon0": ("fan1_input", "pwm1")}
    files = {"/hwmon/hwmon0/fan1_input": "1000\n", "/hwmon/hwmon0/pwm1": "1\n"}
    results = (collect_fan_pwm_observation(hwmon_path="/hwmon", directory_lister=lambda path: tree.get(path, ()), text_reader=lambda path: files[path], observed_at="2026-01-01T00:00:00+00:00"),)
    manifest = build_host_inventory_from_collector_results(results, manifest_id="m", node_id="n")
    snapshot = build_host_resource_telemetry_from_collector_results(results, snapshot_id="s")
    report = evaluate_host_resource_pressure(snapshot)
    registry = update_registry_from_host_resource_report(update_registry_from_host_inventory(build_default_capability_registry(), manifest), report)
    records = registry.by_id()
    assert records["hardware_sensor_inventory"].status in {"implemented", "partial"}
    assert records["host_resource_telemetry"].status in {"implemented", "partial"}
    assert records["host_resource_telemetry"].authority_level == "proposal_only"
    assert records["host_resource_telemetry"].host_actuation_performed is False
    assert records["direct_fan_pwm_thermal_control"].status in {"blocked", "deferred"}
    assert validate_capability_registry(registry).ok


def test_phase3_policy_registry_records_are_proposal_only_and_defer_privileged_organs() -> None:
    from sentientos.capability_registry import update_registry_from_host_resource_policy
    from sentientos.host_resource_governor import build_host_resource_telemetry_snapshot, evaluate_host_resource_pressure
    from sentientos.host_resource_policy import build_host_resource_proposal_receipts, evaluate_host_resource_policy

    snapshot = build_host_resource_telemetry_snapshot(snapshot_id="s", cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)
    report = evaluate_host_resource_pressure(snapshot)
    decision = evaluate_host_resource_policy(report)
    receipts = build_host_resource_proposal_receipts(decision)
    registry = update_registry_from_host_resource_policy(build_default_capability_registry(), decision, receipts)
    records = registry.by_id()
    assert records["host_resource_policy"].status == "implemented"
    assert records["host_resource_policy"].authority_level == "proposal_only"
    assert records["host_resource_policy"].host_actuation_performed is False
    assert records["host_resource_proposal_receipts"].status == "implemented"
    assert records["host_resource_proposal_receipts"].authority_level == "proposal_only"
    assert records["direct_fan_pwm_thermal_control"].status == "blocked"
    assert records["privilege_broker"].status == "implemented"
    assert records["privilege_broker"].authority_level == "eligibility_only"
    assert records["actuation_fulfillment"].status == "implemented"
    assert validate_capability_registry(registry).ok


def test_default_registry_represents_phase4_privilege_broker_as_eligibility_only() -> None:
    records = build_default_capability_registry().by_id()
    assert records["privilege_broker"].status == "implemented"
    assert records["privilege_broker"].authority_level == "eligibility_only"
    assert records["privilege_broker"].host_actuation_performed is False
    assert records["actuation_fulfillment"].status == "implemented"
    assert records["direct_fan_pwm_thermal_control"].status == "blocked"


def test_phase5_registry_represents_actuation_fulfillment_as_rehearsal_only() -> None:
    records = build_default_capability_registry().by_id()
    assert records["actuation_fulfillment"].status == "implemented"
    assert records["actuation_fulfillment"].authority_level == "rehearsal_only"
    assert records["actuation_fulfillment"].host_actuation_performed is False
    assert "real actuation fulfillment" in records["actuation_fulfillment"].deferred_surfaces
    assert records["real_actuation_fulfillment"].status == "deferred"
    assert records["real_actuation_fulfillment"].host_actuation_performed is False
    assert records["direct_fan_pwm_thermal_control"].status == "blocked"
    assert validate_capability_registry(build_default_capability_registry()).ok


def test_execution_proof_wing_capabilities_are_proof_only_and_real_actions_deferred() -> None:
    records = build_default_capability_registry().by_id()
    assert records["effect_receipt_contract"].status == "implemented"
    assert records["effect_receipt_contract"].authority_level == "proof_only"
    assert records["postcondition_checks"].authority_level == "proof_only"
    assert records["rollback_planning"].authority_level == "proof_only"
    assert records["runtime_supervisor"].authority_level == "telemetry_readiness_only"
    assert records["execution_readiness_manifest"].authority_level == "readiness_only"
    for capability_id in ["real_effect_execution", "real_rollback_execution", "real_actuation_fulfillment"]:
        assert records[capability_id].status == "deferred"
    for capability_id in ["real_service_restart", "real_fan_pwm_control", "real_power_profile_mutation", "real_file_cleanup"]:
        assert records[capability_id].status == "blocked"
    assert validate_capability_registry(build_default_capability_registry()).ok


def test_registry_updates_from_execution_readiness_and_supervisor_keep_real_actions_blocked() -> None:
    from sentientos.actuation_fulfillment import build_actuation_fulfillment_plan, build_actuation_fulfillment_rehearsal_receipt
    from sentientos.capability_registry import update_registry_from_execution_readiness_manifest, update_registry_from_runtime_supervisor_report
    from sentientos.effect_proof import build_execution_proof_wing_for_rehearsal_receipt
    from sentientos.runtime_supervisor import RuntimeServiceRecord, build_runtime_supervisor_readiness_report, build_runtime_supervisor_snapshot
    from tests.test_actuation_fulfillment import _broker_receipt_for

    rehearsal = build_actuation_fulfillment_rehearsal_receipt(build_actuation_fulfillment_plan(_broker_receipt_for("inspect_cpu_pressure_candidate", cpu_utilization_percent=95)))
    manifest = build_execution_proof_wing_for_rehearsal_receipt(rehearsal).execution_readiness_manifest
    service = RuntimeServiceRecord("svc", "svc", "daemon", "service_status_nominal", "desired_nominal", (), (), ())
    report = build_runtime_supervisor_readiness_report(build_runtime_supervisor_snapshot(service_records=(service,)))
    registry = update_registry_from_runtime_supervisor_report(update_registry_from_execution_readiness_manifest(build_default_capability_registry(), manifest), report)
    records = registry.by_id()
    assert records["execution_readiness_manifest"].status == "implemented"
    assert records["runtime_supervisor"].status == "implemented"
    assert records["real_service_restart"].status == "blocked"
    assert records["real_fan_pwm_control"].status == "blocked"
    assert records["real_power_profile_mutation"].status == "blocked"
    assert records["real_file_cleanup"].status == "blocked"
    assert records["real_effect_execution"].status == "deferred"
    assert validate_capability_registry(registry).ok


def test_authorization_review_capabilities_are_review_and_schema_only() -> None:
    records = build_default_capability_registry().by_id()
    assert records["authorization_review"].status == "implemented"
    assert records["authorization_review"].authority_level == "review_only"
    assert records["authorization_review"].host_actuation_performed is False
    assert "real authorization grants" in records["authorization_review"].deferred_surfaces
    assert records["future_authorization_grant_schema"].status == "implemented"
    assert records["future_authorization_grant_schema"].authority_level == "schema_only"
    assert records["future_authorization_grant_schema"].host_actuation_performed is False
    assert records["real_authorization_grant"].status == "deferred"
    for capability_id in ["real_effect_execution", "real_rollback_execution", "real_actuation_fulfillment"]:
        assert records[capability_id].status == "deferred"
    for capability_id in ["real_service_restart", "real_fan_pwm_control", "real_power_profile_mutation", "real_file_cleanup"]:
        assert records[capability_id].status == "blocked"
    assert validate_capability_registry(build_default_capability_registry()).ok


def test_registry_updates_from_authorization_review_keep_real_actions_deferred_or_blocked() -> None:
    from sentientos.authorization_review import build_authorization_review_wing_for_execution_readiness
    from sentientos.capability_registry import update_registry_from_authorization_review_decision, update_registry_from_future_authorization_schema
    from sentientos.effect_proof import build_execution_proof_wing_for_rehearsal_receipt
    from sentientos.actuation_fulfillment import build_actuation_fulfillment_plan, build_actuation_fulfillment_rehearsal_receipt
    from tests.test_actuation_fulfillment import _broker_receipt_for

    rehearsal = build_actuation_fulfillment_rehearsal_receipt(build_actuation_fulfillment_plan(_broker_receipt_for("inspect_cpu_pressure_candidate", cpu_utilization_percent=95)))
    manifest = build_execution_proof_wing_for_rehearsal_receipt(rehearsal).execution_readiness_manifest
    wing = build_authorization_review_wing_for_execution_readiness(manifest)
    registry = update_registry_from_future_authorization_schema(update_registry_from_authorization_review_decision(build_default_capability_registry(), wing.decision), wing.future_authorization_grant_schema)
    records = registry.by_id()
    assert records["authorization_review"].status == "implemented"
    assert records["authorization_review"].authority_level == "review_only"
    assert records["future_authorization_grant_schema"].authority_level == "schema_only"
    assert records["real_authorization_grant"].status == "deferred"
    assert records["real_effect_execution"].status == "deferred"
    assert records["real_rollback_execution"].status == "deferred"
    assert records["real_service_restart"].status == "blocked"
    assert records["real_fan_pwm_control"].status == "blocked"
    assert records["real_power_profile_mutation"].status == "blocked"
    assert records["real_file_cleanup"].status == "blocked"
    assert validate_capability_registry(registry).ok


def test_controlled_authorization_and_trace_capabilities_are_non_live() -> None:
    records = build_default_capability_registry().by_id()
    assert records["controlled_authorization_contract"].status == "implemented"
    assert records["controlled_authorization_contract"].authority_level == "contract_only"
    assert records["controlled_authorization_grant_record"].status == "implemented"
    assert records["controlled_authorization_grant_record"].authority_level == "schema_only"
    assert records["controlled_authorization_ledger"].status == "implemented"
    assert records["controlled_authorization_ledger"].authority_level == "ledger_only"
    assert records["host_embodiment_trace"].status == "implemented"
    assert records["host_embodiment_trace"].authority_level == "demo_proof_only"
    assert records["live_authorization_grant"].status == "deferred"
    assert records["real_effect_execution"].status == "deferred"
    assert records["real_rollback_execution"].status == "deferred"
    assert records["real_service_restart"].status == "blocked"
    assert records["real_fan_pwm_control"].status == "blocked"
    assert records["real_power_profile_mutation"].status == "blocked"
    assert records["real_file_cleanup"].status == "blocked"
    assert all(record.host_actuation_performed is False for record in records.values())


def test_trace_export_and_reviewer_demo_capabilities_are_proof_only() -> None:
    from sentientos.capability_registry import update_registry_from_trace_export
    from sentientos.host_embodiment_trace import build_host_embodiment_demo_trace

    trace = build_host_embodiment_demo_trace()
    registry = update_registry_from_trace_export(build_default_capability_registry(), trace)
    records = registry.by_id()
    assert records["host_embodiment_trace_export"].status == "implemented"
    assert records["host_embodiment_trace_export"].authority_level == "demo_proof_only"
    assert records["host_embodiment_trace_export"].host_actuation_performed is False
    assert records["reviewer_demo_trace"].status == "implemented"
    assert records["reviewer_demo_trace"].authority_level == "demo_proof_only"
    assert records["live_host_trace_collection"].status == "deferred"
    assert records["live_authorization_grant"].status == "deferred"
    assert records["real_effect_execution"].status == "deferred"
    assert records["real_fan_pwm_control"].status == "blocked"
    assert records["real_power_profile_mutation"].status == "blocked"
    assert records["real_service_restart"].status == "blocked"
    assert records["real_file_cleanup"].status == "blocked"
    assert validate_capability_registry(registry).ok


def test_reviewer_proof_bundle_capabilities_are_export_only_and_real_actions_deferred() -> None:
    records = build_default_capability_registry().by_id()
    assert records["reviewer_proof_bundle"].status == "implemented"
    assert records["reviewer_proof_bundle"].authority_level == "demo_proof_only"
    assert records["reviewer_proof_bundle"].host_actuation_performed is False
    assert records["reviewer_proof_bundle_cli"].status == "implemented"
    assert records["reviewer_proof_bundle_cli"].authority_level == "demo_proof_only"
    assert records["reviewer_proof_bundle_cli"].host_actuation_performed is False
    assert records["proof_command_manifest"].status == "implemented"
    assert records["proof_command_manifest"].authority_level == "proof_only"
    assert records["live_host_trace_collection"].status == "deferred"
    assert records["live_authorization_grant"].status == "deferred"
    assert records["real_effect_execution"].status == "deferred"
    for capability_id in ["real_fan_pwm_control", "real_power_profile_mutation", "real_service_restart", "real_file_cleanup"]:
        assert records[capability_id].status in {"blocked", "deferred"}
        assert records[capability_id].host_actuation_performed is False


def test_registry_updates_from_reviewer_proof_bundle_keep_authority_deferred() -> None:
    from sentientos.capability_registry import update_registry_from_reviewer_proof_bundle
    from sentientos.reviewer_proof_bundle import build_reviewer_proof_bundle_payload

    manifest = build_reviewer_proof_bundle_payload()["manifest"]
    registry = update_registry_from_reviewer_proof_bundle(build_default_capability_registry(), manifest)
    records = registry.by_id()
    assert records["reviewer_proof_bundle"].status == "implemented"
    assert records["reviewer_proof_bundle_cli"].status == "implemented"
    assert records["proof_command_manifest"].status == "implemented"
    assert records["live_host_trace_collection"].status == "deferred"
    assert records["live_authorization_grant"].status == "deferred"
    assert records["real_effect_execution"].status == "deferred"
    assert records["real_fan_pwm_control"].status == "blocked"
    assert records["real_power_profile_mutation"].status == "blocked"
    assert records["real_service_restart"].status == "blocked"
    assert records["real_file_cleanup"].status == "blocked"
    assert validate_capability_registry(registry).ok


def test_host_actuation_safety_capabilities_are_metadata_only_and_real_actions_blocked() -> None:
    registry = build_default_capability_registry()
    by_id = registry.by_id()
    expected = {
        "host_actuation_safety_gates": "metadata_proof_only",
        "hardware_allowlist_manifest": "allowlist_only",
        "os_backend_declaration": "declaration_only",
        "bounds_policy": "policy_only",
        "cooldown_policy": "policy_only",
        "panic_stop_contract": "contract_only",
        "host_action_scope_manifest": "scope_only",
        "safety_gate_satisfaction_manifest": "safety_gate_only",
    }
    for capability_id, authority in expected.items():
        record = by_id[capability_id]
        assert record.status == "implemented"
        assert record.authority_level == authority
        assert record.metadata_only is True
        assert record.host_actuation_performed is False
    for capability_id in [
        "live_authorization_grant", "real_effect_execution", "real_fan_pwm_control", "real_thermal_actuation",
        "real_power_profile_mutation", "real_service_restart", "real_file_cleanup",
    ]:
        assert by_id[capability_id].status in {"deferred", "blocked"}
        assert by_id[capability_id].authority_level == "none"
        assert by_id[capability_id].host_actuation_performed is False


def test_live_grant_readiness_capabilities_are_metadata_only_and_real_actions_remain_deferred() -> None:
    registry = build_default_capability_registry()
    records = registry.by_id()
    assert records["live_grant_readiness"].status == "implemented"
    assert records["live_grant_readiness"].authority_level == "readiness_only"
    assert records["live_grant_prerequisite_matrix"].authority_level == "metadata_proof_only"
    assert records["operator_policy_approval_packet"].authority_level == "packet_only"
    assert records["grant_issue_preflight_receipt"].authority_level == "preflight_only"
    assert records["grant_denial_deferral_receipt"].authority_level == "denial_deferral_only"
    for capability_id in ["live_authorization_grant", "real_effect_execution"]:
        assert records[capability_id].status == "deferred"
        assert records[capability_id].host_actuation_performed is False
    for capability_id in ["real_fan_pwm_control", "real_thermal_actuation", "real_power_profile_mutation", "real_service_restart", "real_file_cleanup"]:
        assert records[capability_id].status == "blocked"
        assert records[capability_id].host_actuation_performed is False


def test_local_authorization_capabilities_are_record_only_and_real_actions_deferred() -> None:
    records = build_default_capability_registry().by_id()
    assert records["local_authorization_grant"].status == "implemented"
    assert records["local_authorization_grant"].authority_level == "local_authorization_record_only"
    assert records["local_authorization_grant"].host_actuation_performed is False
    assert "host mutation" in records["local_authorization_grant"].deferred_surfaces
    assert records["local_authorization_grant_ledger"].authority_level == "authorization_ledger_only"
    assert records["local_authorization_revocation_receipt"].authority_level == "revocation_record_only"
    assert records["local_authorization_expiry_evaluation"].authority_level == "expiry_evaluation_only"
    assert records["local_authorization_verification"].authority_level == "verification_only"
    assert records["fulfillment_authorization_consumption"].status == "implemented"
    assert records["real_effect_execution"].status == "deferred"
    assert records["real_fan_pwm_control"].status in {"blocked", "deferred"}
    assert records["real_thermal_actuation"].status in {"blocked", "deferred"}
    assert records["real_power_profile_mutation"].status in {"blocked", "deferred"}
    assert records["real_service_restart"].status in {"blocked", "deferred"}
    assert records["real_file_cleanup"].status in {"blocked", "deferred"}
    assert validate_capability_registry(build_default_capability_registry()).ok


def test_registry_updates_from_local_authorization_ledger_without_fulfillment() -> None:
    from sentientos.capability_registry import update_registry_from_local_authorization_ledger
    from sentientos.local_authorization_grant import build_local_authorization_grant_ledger

    registry = update_registry_from_local_authorization_ledger(build_default_capability_registry(), build_local_authorization_grant_ledger(()))
    records = registry.by_id()
    assert records["local_authorization_grant"].authority_level == "local_authorization_record_only"
    assert records["local_authorization_grant_ledger"].authority_level == "authorization_ledger_only"
    assert records["fulfillment_authorization_consumption"].status == "implemented"
    assert records["real_effect_execution"].status == "deferred"
    assert records["real_fan_pwm_control"].status == "blocked"
    assert validate_capability_registry(registry).ok


def test_fulfillment_authorization_capabilities_are_metadata_only_and_execution_deferred() -> None:
    records = build_default_capability_registry().by_id()
    assert records["fulfillment_authorization_request"].status == "implemented"
    assert records["fulfillment_authorization_request"].authority_level == "request_only"
    assert records["grant_consumption_verification"].status == "implemented"
    assert records["grant_consumption_verification"].authority_level == "verification_only"
    assert records["fulfillment_scope_match_assessment"].status == "implemented"
    assert records["fulfillment_scope_match_assessment"].authority_level == "assessment_only"
    assert records["fulfillment_authorization_consumption_receipt"].status == "implemented"
    assert records["fulfillment_authorization_consumption_receipt"].authority_level == "consumption_receipt_only"
    assert records["fulfillment_authorization_denial_receipt"].status == "implemented"
    assert records["fulfillment_authorization_denial_receipt"].authority_level == "denial_receipt_only"
    assert records["fulfillment_execution"].status == "deferred"
    assert records["real_effect_execution"].status == "deferred"
    for capability_id in ["real_fan_pwm_control", "real_thermal_actuation", "real_power_profile_mutation", "real_service_restart", "real_file_cleanup"]:
        assert records[capability_id].status == "blocked"
    assert validate_capability_registry(build_default_capability_registry()).ok


def test_registry_update_from_fulfillment_authorization_consumption_keeps_real_actions_blocked() -> None:
    from sentientos.capability_registry import update_registry_from_fulfillment_authorization_consumption
    from tests.test_fulfillment_authorization import _wing

    registry = update_registry_from_fulfillment_authorization_consumption(build_default_capability_registry(), _wing())
    records = registry.by_id()
    assert records["fulfillment_authorization_consumption_receipt"].status == "implemented"
    assert records["fulfillment_execution"].status == "deferred"
    assert records["real_effect_execution"].status == "deferred"
    assert records["real_fan_pwm_control"].status == "blocked"
    assert records["real_thermal_actuation"].status == "blocked"
    assert records["real_power_profile_mutation"].status == "blocked"
    assert records["real_service_restart"].status == "blocked"
    assert records["real_file_cleanup"].status == "blocked"
    assert validate_capability_registry(registry).ok


def test_fulfillment_executor_contract_capabilities_are_contract_only_and_real_execution_deferred() -> None:
    records = build_default_capability_registry().by_id()
    assert records["fulfillment_executor_contract"].status == "implemented"
    assert records["fulfillment_executor_contract"].authority_level == "contract_only"
    assert records["executor_backend_declaration"].authority_level == "declaration_only"
    assert records["executor_precondition_manifest"].authority_level == "precondition_only"
    assert records["executor_dry_run_plan"].authority_level == "plan_only"
    assert records["executor_admission_packet"].authority_level == "packet_only"
    assert records["executor_contract_readiness_receipt"].authority_level == "readiness_receipt_only"
    for capability_id in ["executor_implementation", "backend_invocation", "control_plane_admission_for_fulfillment", "fulfillment_execution", "real_effect_execution"]:
        assert records[capability_id].status == "deferred"
        assert records[capability_id].host_actuation_performed is False
    for capability_id in ["real_fan_pwm_control", "real_thermal_actuation", "real_power_profile_mutation", "real_service_restart", "real_file_cleanup"]:
        assert records[capability_id].status in {"blocked", "deferred"}
        assert records[capability_id].host_actuation_performed is False
    assert validate_capability_registry(build_default_capability_registry()).ok


def test_registry_update_from_executor_contract_readiness_preserves_deferred_execution() -> None:
    from sentientos.capability_registry import update_registry_from_executor_contract_readiness
    from sentientos.fulfillment_executor_contract import build_fulfillment_executor_contract_wing
    from tests.test_fulfillment_authorization import _wing, FIXED

    receipt = _wing().consumption_receipt
    wing = build_fulfillment_executor_contract_wing(receipt, created_at=FIXED)
    registry = update_registry_from_executor_contract_readiness(build_default_capability_registry(), wing)
    records = registry.by_id()
    assert records["fulfillment_executor_contract"].authority_level == "contract_only"
    assert records["executor_contract_readiness_receipt"].authority_level == "readiness_receipt_only"
    assert records["executor_implementation"].status == "deferred"
    assert records["backend_invocation"].status == "deferred"
    assert records["control_plane_admission_for_fulfillment"].status == "deferred"
    assert records["fulfillment_execution"].status == "deferred"
    assert records["real_fan_pwm_control"].status == "blocked"
    assert validate_capability_registry(registry).ok


def test_dry_run_execution_harness_capabilities_are_simulation_only_and_real_actions_deferred() -> None:
    records = build_default_capability_registry().by_id()
    assert records["dry_run_execution_harness"].status == "implemented"
    assert records["dry_run_execution_harness"].authority_level == "simulated_only"
    assert records["simulated_backend_registry"].authority_level == "simulated_only"
    assert records["dry_run_execution_request"].authority_level == "request_only"
    assert records["dry_run_execution_result"].authority_level == "simulated_only"
    assert records["dry_run_execution_receipt"].authority_level == "dry_run_receipt_only"
    assert records["real_backend_invocation"].status == "deferred"
    assert records["fulfillment_execution"].status == "deferred"
    assert records["real_effect_execution"].status == "deferred"
    for capability_id in ["real_fan_pwm_control", "real_thermal_actuation", "real_power_profile_mutation", "real_service_restart", "real_file_cleanup"]:
        assert records[capability_id].status == "blocked"
        assert records[capability_id].host_actuation_performed is False
    assert validate_capability_registry(build_default_capability_registry()).ok


def test_registry_update_from_dry_run_execution_receipt_preserves_real_action_deferral() -> None:
    from sentientos.capability_registry import update_registry_from_dry_run_execution_receipt
    from sentientos.dry_run_execution_harness import build_dry_run_execution_harness_wing
    from sentientos.fulfillment_executor_contract import build_fulfillment_executor_contract_wing
    from tests.test_fulfillment_authorization import _wing, FIXED

    executor = build_fulfillment_executor_contract_wing(_wing().consumption_receipt, created_at=FIXED)
    dry_run = build_dry_run_execution_harness_wing(executor.readiness_receipt, created_at=FIXED)
    registry = update_registry_from_dry_run_execution_receipt(build_default_capability_registry(), dry_run.receipt)
    records = registry.by_id()
    assert records["dry_run_execution_receipt"].status == "implemented"
    assert records["dry_run_execution_receipt"].authority_level == "dry_run_receipt_only"
    assert records["real_backend_invocation"].status == "deferred"
    assert records["fulfillment_execution"].status == "deferred"
    assert records["real_effect_execution"].status == "deferred"
    assert records["real_fan_pwm_control"].status == "blocked"
    assert validate_capability_registry(registry).ok


def test_dry_run_audit_closure_capabilities_are_dry_run_only_and_real_actions_deferred() -> None:
    records = build_default_capability_registry().by_id()
    assert records["dry_run_effect_verification"].status == "implemented"
    assert records["dry_run_effect_verification"].authority_level == "dry_run_verification_only"
    assert records["dry_run_postcondition_verification"].authority_level == "dry_run_postcondition_only"
    assert records["dry_run_rollback_rehearsal"].authority_level == "dry_run_rollback_only"
    assert records["dry_run_audit_closure_receipt"].authority_level == "dry_run_audit_only"
    assert records["dry_run_closure_bundle"].authority_level == "dry_run_closure_only"
    for capability_id in ["real_effect_receipt_creation", "real_postcondition_check", "real_rollback_execution", "production_audit_receipt_for_host_effect", "fulfillment_execution", "real_effect_execution"]:
        assert records[capability_id].status == "deferred"
    for capability_id in ["real_fan_pwm_control", "real_thermal_actuation", "real_power_profile_mutation", "real_service_restart", "real_file_cleanup"]:
        assert records[capability_id].status == "blocked"
    assert validate_capability_registry(build_default_capability_registry()).ok


def test_registry_update_from_dry_run_audit_closure_preserves_real_action_deferral() -> None:
    from sentientos.capability_registry import update_registry_from_dry_run_audit_closure
    from sentientos.dry_run_audit_closure import build_dry_run_audit_closure_wing
    from sentientos.dry_run_execution_harness import build_dry_run_execution_harness_wing
    from sentientos.fulfillment_executor_contract import build_fulfillment_executor_contract_wing
    from tests.test_fulfillment_authorization import _wing, FIXED

    executor = build_fulfillment_executor_contract_wing(_wing().consumption_receipt, created_at=FIXED)
    dry_run = build_dry_run_execution_harness_wing(executor.readiness_receipt, created_at=FIXED)
    closure = build_dry_run_audit_closure_wing(dry_run.receipt, created_at=FIXED)
    registry = update_registry_from_dry_run_audit_closure(build_default_capability_registry(), closure)
    records = registry.by_id()
    assert records["dry_run_audit_closure_receipt"].status == "implemented"
    assert records["dry_run_closure_bundle"].authority_level == "dry_run_closure_only"
    assert records["real_effect_receipt_creation"].status == "deferred"
    assert records["real_postcondition_check"].status == "deferred"
    assert records["real_rollback_execution"].status == "deferred"
    assert records["production_audit_receipt_for_host_effect"].status == "deferred"
    assert records["real_fan_pwm_control"].status == "blocked"
    assert validate_capability_registry(registry).ok


def test_real_effect_admission_registry_records_are_planning_only_and_real_actions_deferred() -> None:
    records = build_default_capability_registry().by_id()
    assert records["real_effect_capability_admission"].status == "implemented"
    assert records["real_effect_capability_admission"].authority_level == "admission_planning_only"
    assert records["real_effect_capability_candidate"].authority_level == "candidate_only"
    assert records["real_effect_implementation_plan_scaffold"].authority_level == "plan_scaffold_only"
    assert records["real_effect_capability_block_receipt"].authority_level == "block_receipt_only"
    for capability_id in ["real_backend_implementation", "real_backend_invocation", "fulfillment_execution", "real_effect_execution", "real_effect_receipt_creation", "real_postcondition_check", "real_rollback_execution", "production_audit_receipt_for_host_effect"]:
        assert records[capability_id].status == "deferred"
        assert records[capability_id].host_actuation_performed is False
    for capability_id in ["real_fan_pwm_control", "real_thermal_actuation", "real_power_profile_mutation", "real_service_restart", "real_file_cleanup"]:
        assert records[capability_id].status == "blocked"
        assert records[capability_id].host_actuation_performed is False
    assert validate_capability_registry(build_default_capability_registry()).ok


def test_update_registry_from_real_effect_admission_preserves_deferred_real_backends() -> None:
    from sentientos.capability_registry import update_registry_from_real_effect_admission
    from sentientos.real_effect_admission import build_real_effect_admission_wing
    from tests.test_real_effect_admission import _closure

    wing = build_real_effect_admission_wing(_closure(), created_at="2025-07-30T00:00:00+00:00")
    records = update_registry_from_real_effect_admission(build_default_capability_registry(), wing).by_id()
    assert records["real_effect_capability_admission"].status == "implemented"
    assert records["real_backend_implementation"].status == "deferred"
    assert records["real_backend_invocation"].status == "deferred"
    assert records["real_effect_execution"].status == "deferred"
    assert records["real_fan_pwm_control"].status == "blocked"


def test_local_diagnostic_effect_registry_records_are_narrow_and_general_effects_deferred() -> None:
    records = build_default_capability_registry().by_id()
    assert records["local_diagnostic_effect"].status == "implemented"
    assert records["local_diagnostic_effect"].authority_level == "local_diagnostic_effect_only"
    assert "explicit optional low-risk local diagnostic file write" in records["local_diagnostic_effect"].implemented_surfaces
    assert records["local_diagnostic_effect_receipt"].status == "implemented"
    assert records["local_diagnostic_effect_receipt"].authority_level == "real_effect_receipt_only"
    assert records["local_diagnostic_postcondition_check"].authority_level == "real_postcondition_check_only"
    assert records["local_diagnostic_production_audit_receipt"].authority_level == "production_audit_only"
    assert records["local_diagnostic_rollback_plan"].status == "implemented"
    assert records["local_diagnostic_rollback_execution"].status == "deferred"
    for capability_id in ["real_backend_implementation", "real_backend_invocation", "fulfillment_execution", "real_effect_execution"]:
        assert records[capability_id].status == "deferred"
    for capability_id in ["real_fan_pwm_control", "real_thermal_actuation", "real_power_profile_mutation", "real_service_restart", "real_file_cleanup"]:
        assert records[capability_id].status == "blocked"


def test_local_diagnostic_exact_rollback_capabilities_are_exact_artifact_only() -> None:
    records = build_default_capability_registry().by_id()
    rollback = records["local_diagnostic_exact_rollback"]
    postcondition = records["local_diagnostic_rollback_postcondition_check"]
    audit = records["local_diagnostic_rollback_audit_receipt"]
    assert rollback.status == "implemented"
    assert rollback.authority_level == "exact_artifact_rollback_only"
    assert "explicit exact-artifact rollback for local diagnostic artifact only" in rollback.implemented_surfaces
    assert {"general cleanup", "recursive delete", "wildcard delete", "unrelated file delete"}.issubset(set(rollback.deferred_surfaces))
    assert postcondition.status == "implemented"
    assert postcondition.authority_level == "exact_artifact_postcondition_only"
    assert audit.status == "implemented"
    assert audit.authority_level == "exact_artifact_rollback_audit_only"
    for capability_id in ["real_file_cleanup", "real_fan_pwm_control", "real_thermal_actuation", "real_power_profile_mutation", "real_service_restart", "provider_invocation", "federation_transport_sync_adoption"]:
        assert records[capability_id].status in {"blocked", "deferred"}
    assert validate_capability_registry(build_default_capability_registry()).ok


def test_local_effect_transaction_ledger_capabilities_are_bounded() -> None:
    registry = build_default_capability_registry()
    records = registry.by_id()
    assert records["local_effect_transaction_ledger"].status == "implemented"
    assert records["local_effect_transaction_ledger"].authority_level == "local_effect_transaction_ledger_only"
    assert records["local_effect_lifecycle_report"].status == "implemented"
    assert records["local_effect_lifecycle_report"].authority_level == "local_effect_lifecycle_report_only"
    assert records["local_effect_transaction_ledger_artifact"].status == "implemented"
    assert records["local_effect_transaction_ledger_artifact"].authority_level == "explicit_local_artifact_only"
    assert records["general_effect_transaction_ledger"].status == "deferred"
    for capability_id in ["general_cleanup", "recursive_delete", "unrelated_file_delete", "real_fan_pwm_control", "real_thermal_actuation", "real_power_profile_mutation", "real_service_restart", "package_install", "driver_install", "network_egress", "provider_invocation", "prompt_assembly", "remote_execution"]:
        assert records[capability_id].status == "blocked"


def test_host_steward_boundary_capabilities_are_metadata_only_and_runners_blocked() -> None:
    records = build_default_capability_registry().by_id()
    expected = {
        "host_steward_authority_profile": "authority_profile_only",
        "delegated_runner_boundary_profile": "boundary_profile_only",
        "execution_containment_profile": "containment_profile_only",
        "backend_adapter_authority_declaration": "declaration_only",
        "runner_capability_grant_scaffold": "grant_scaffold_only",
        "runner_boundary_assessment": "assessment_only",
        "runner_boundary_violation_receipt": "violation_receipt_only",
    }
    for capability_id, authority_level in expected.items():
        record = records[capability_id]
        assert record.status == "implemented"
        assert record.authority_level == authority_level
        assert record.metadata_only is True
        assert record.host_actuation_performed is False
    assert records["live_runner_execution"].status == "deferred"
    for capability_id in [
        "real_subprocess_runner",
        "shell_runner",
        "network_runner",
        "provider_runner",
        "prompt_assembly_runner",
        "hardware_control_runner",
        "service_control_runner",
        "power_control_runner",
        "cleanup_runner",
        "real_fan_pwm_control",
        "real_thermal_actuation",
    ]:
        assert records[capability_id].status in {"blocked", "deferred"}
        assert records[capability_id].host_actuation_performed is False


def test_builtin_local_effect_runner_capabilities_are_bounded_in_process_only() -> None:
    records = build_default_capability_registry().by_id()
    assert records["builtin_local_effect_runner"].status == "implemented"
    assert records["builtin_local_effect_runner"].authority_level == "bounded_in_process_runner"
    assert "local diagnostic artifact write, exact-artifact rollback, workspace-scoped file update, and workspace exact rollback" in records["builtin_local_effect_runner"].implemented_surfaces
    assert records["builtin_runner_local_diagnostic_artifact_write"].status == "implemented"
    assert records["builtin_runner_local_diagnostic_artifact_write"].authority_level == "builtin_runner_action_only"
    assert records["builtin_runner_exact_artifact_rollback"].status == "implemented"
    assert records["builtin_runner_exact_artifact_rollback"].authority_level == "builtin_runner_action_only"
    assert records["general_runner_framework"].status == "deferred"
    for capability_id in [
        "generated_code_runner",
        "plugin_runner",
        "federation_import_runner",
        "subprocess_runner",
        "shell_runner",
        "network_runner",
        "provider_runner",
        "prompt_assembly_runner",
        "hardware_control_runner",
        "service_control_runner",
        "power_control_runner",
        "cleanup_runner",
    ]:
        assert records[capability_id].status == "blocked"
        assert records[capability_id].host_actuation_performed is False
    assert validate_capability_registry(build_default_capability_registry()).ok


def test_builtin_runner_transaction_orchestrator_capabilities_are_bounded() -> None:
    from sentientos.builtin_runner_transaction_orchestrator import run_builtin_runner_transaction_wing
    from sentientos.capability_registry import update_registry_from_builtin_runner_transaction_receipt
    import tempfile

    records = build_default_capability_registry().by_id()
    assert records["builtin_runner_transaction_orchestrator"].status == "implemented"
    assert records["builtin_runner_transaction_orchestrator"].authority_level == "bounded-orchestrator"
    assert records["builtin_runner_transaction_write_only"].status == "implemented"
    assert records["builtin_runner_transaction_write_with_rollback"].status == "implemented"
    assert records["builtin_runner_transaction_ledger_build"].status == "implemented"
    assert records["general_runner_orchestration"].status == "deferred"
    for capability_id in ["generated_code_runner", "plugin_runner", "federation_import_runner", "subprocess_runner", "shell_runner"]:
        assert records[capability_id].status == "blocked"
    for capability_id in ["network_runner", "provider_runner", "prompt_assembly_runner", "hardware_control_runner", "service_control_runner", "power_control_runner", "cleanup_runner"]:
        assert records[capability_id].status in {"blocked", "deferred"}

    with tempfile.TemporaryDirectory() as d:
        wing = run_builtin_runner_transaction_wing(output_dir=d, transaction_mode="diagnostic_write_rollback_with_ledger", force=True)
        updated = update_registry_from_builtin_runner_transaction_receipt(build_default_capability_registry(), wing.receipt)
    assert validate_capability_registry(updated).ok


def test_workspace_file_effect_capabilities_are_explicit_single_file_only() -> None:
    from sentientos.capability_registry import update_registry_from_workspace_file_effect_receipt
    from sentientos.workspace_file_effect import run_workspace_file_effect_wing
    import tempfile
    from pathlib import Path

    records = build_default_capability_registry().by_id()
    effect = records["workspace_scoped_file_effect"]
    assert effect.status == "implemented"
    assert "explicit single-file create/update inside caller-supplied workspace root" in effect.implemented_surfaces
    assert "general filesystem access" in effect.deferred_surfaces
    assert records["workspace_file_preimage_capture"].status == "implemented"
    assert "exact-target preimage capture before replacement" in records["workspace_file_preimage_capture"].implemented_surfaces
    assert records["workspace_file_postcondition_check"].status == "implemented"
    assert records["workspace_file_exact_rollback"].status == "implemented"
    assert records["workspace_file_production_audit"].status == "implemented"
    for capability_id in ["general_filesystem_access", "general_cleanup", "recursive_delete", "wildcard_delete", "unrelated_file_delete"]:
        assert records[capability_id].status in {"blocked", "deferred"}
    for capability_id in ["real_service_restart", "real_power_profile_mutation", "real_fan_pwm_control", "real_thermal_actuation", "package_install", "driver_install", "network_egress", "provider_invocation", "prompt_assembly", "subprocess_runner", "shell_runner"]:
        assert records[capability_id].status in {"blocked", "deferred"}
    with tempfile.TemporaryDirectory() as td:
        wing = run_workspace_file_effect_wing(workspace_root=Path(td), relative_target_path="demo.txt", payload_text="hello")
        updated = update_registry_from_workspace_file_effect_receipt(build_default_capability_registry(), wing.receipt).by_id()
    assert updated["workspace_scoped_file_effect"].status == "implemented"
    assert updated["general_filesystem_access"].status == "blocked"


def test_workspace_file_runner_transaction_capabilities_are_bounded() -> None:
    from sentientos.capability_registry import update_registry_from_workspace_file_transaction_ledger
    from sentientos.workspace_file_effect import run_workspace_file_effect_wing
    from sentientos.workspace_file_transaction_ledger import build_transaction_ledger_from_workspace_file_records

    records = build_default_capability_registry().by_id()
    assert records["builtin_runner_workspace_scoped_file_update"].status == "implemented"
    assert records["builtin_runner_workspace_file_exact_rollback"].status == "implemented"
    assert records["workspace_file_transaction_ledger"].authority_level == "metadata_ledger_only"
    assert records["workspace_file_lifecycle_report"].authority_level == "report_only"
    assert records["workspace_file_transaction_ledger_artifact"].authority_level == "explicit-local-artifact-only"
    assert records["workspace_file_transaction_orchestration"].status == "deferred"
    assert records["general_filesystem_runner"].status == "blocked"
    with tempfile.TemporaryDirectory() as td:
        wing = run_workspace_file_effect_wing(workspace_root=Path(td), relative_target_path="demo.txt", payload_text="hello")
        bundle = build_transaction_ledger_from_workspace_file_records(preimage=wing.preimage, effect_receipt=wing.receipt, postcondition_check=wing.postcondition, production_audit=wing.production_audit, rollback_plan=wing.rollback_plan)
        updated = update_registry_from_workspace_file_transaction_ledger(build_default_capability_registry(), bundle.ledger).by_id()
    assert updated["workspace_file_transaction_ledger"].status == "implemented"
    assert updated["general_filesystem_access"].status == "blocked"
    assert updated["general_cleanup"].status == "blocked"
