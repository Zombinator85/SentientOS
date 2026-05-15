from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.fulfillment_executor_contract import (
    build_fulfillment_executor_contract_wing,
    executor_contract_readiness_receipt_digest,
    summarize_executor_admission_packet,
    summarize_executor_backend_declaration,
    summarize_executor_contract_readiness_receipt,
    summarize_executor_dry_run_plan,
    summarize_executor_precondition_manifest,
    summarize_fulfillment_executor_contract,
    validate_executor_admission_packet,
    validate_executor_backend_declaration,
    validate_executor_contract_readiness_receipt,
    validate_executor_dry_run_plan,
    validate_executor_precondition_manifest,
    validate_fulfillment_executor_contract,
)
from tests.test_fulfillment_authorization import FIXED, _wing

pytestmark = pytest.mark.no_legacy_skip


def _consumed_receipt(domain: str = "future_cooling_fulfillment_authorization"):
    scope = domain.replace("_fulfillment_authorization", "_scope").replace("future_cooling_scope", "future_cooling_scope")
    if domain == "future_power_fulfillment_authorization":
        scope = "future_power_scope"
    elif domain == "future_cleanup_fulfillment_authorization":
        scope = "future_cleanup_scope"
    elif domain == "future_service_fulfillment_authorization":
        scope = "future_service_scope"
    return _wing(scope=scope, fulfillment_domain=domain).consumption_receipt


def test_consumed_authorization_builds_executor_contract_wing_without_execution() -> None:
    wing = build_fulfillment_executor_contract_wing(_consumed_receipt(), created_at=FIXED)
    assert wing.contract.contract_status in {"fulfillment_executor_contract_ready", "fulfillment_executor_contract_ready_with_conditions"}
    assert wing.contract.contract_only is True
    assert wing.contract.executor_implemented is False
    assert wing.contract.backend_loaded is False
    assert wing.backend_declaration.declaration_only is True
    assert wing.backend_declaration.backend_loaded is False
    assert wing.backend_declaration.backend_invoked is False
    assert wing.precondition_manifest.precondition_only is True
    assert wing.dry_run_plan.dry_run_plan_only is True
    assert wing.dry_run_plan.dry_run_executed is False
    assert wing.admission_packet.admission_packet_only is True
    assert wing.admission_packet.control_plane_admission_granted is False
    assert wing.readiness_receipt.readiness_receipt_only is True
    assert wing.readiness_receipt.executor_implemented is False
    assert wing.readiness_receipt.fulfillment_granted is False
    assert wing.readiness_receipt.effect_performed is False
    assert wing.readiness_receipt.host_mutation_performed is False
    assert validate_fulfillment_executor_contract(wing.contract).ok
    assert validate_executor_backend_declaration(wing.backend_declaration).ok
    assert validate_executor_precondition_manifest(wing.precondition_manifest).ok
    assert validate_executor_dry_run_plan(wing.dry_run_plan).ok
    assert validate_executor_admission_packet(wing.admission_packet).ok
    assert validate_executor_contract_readiness_receipt(wing.readiness_receipt).ok


@pytest.mark.parametrize(
    ("consumption_status", "consumed", "expected"),
    [
        ("fulfillment_authorization_consumption_blocked", False, "executor_contract_readiness_blocked"),
        ("fulfillment_authorization_consumption_expired", False, "executor_contract_readiness_blocked"),
        ("fulfillment_authorization_consumption_revoked", False, "executor_contract_readiness_blocked"),
        ("fulfillment_authorization_consumption_out_of_scope", False, "executor_contract_readiness_blocked"),
        ("fulfillment_authorization_consumption_incomplete", False, "executor_contract_readiness_incomplete"),
        ("fulfillment_authorization_consumption_contradicted", False, "executor_contract_readiness_contradicted"),
    ],
)
def test_blocked_incomplete_and_contradicted_consumption_map_to_readiness_statuses(consumption_status: str, consumed: bool, expected: str) -> None:
    receipt = replace(_consumed_receipt(), consumption_status=consumption_status, authorization_consumed_for_future_fulfillment=consumed, digest="")
    wing = build_fulfillment_executor_contract_wing(receipt, created_at=FIXED)
    assert wing.readiness_receipt.readiness_status == expected
    if expected != "executor_contract_readiness_contradicted":
        assert wing.precondition_manifest.missing_precondition_labels == ("valid_fulfillment_authorization_consumption_required",)


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
    wing = build_fulfillment_executor_contract_wing(_consumed_receipt(domain), created_at=FIXED)
    assert blocked <= set(wing.contract.blocked_actions)
    assert blocked <= set(wing.readiness_receipt.blocked_actions)


@pytest.mark.parametrize(
    ("record_name", "flag"),
    [
        ("contract", "fulfillment_granted"),
        ("contract", "effect_performed"),
        ("contract", "host_mutation_performed"),
        ("contract", "backend_loaded"),
        ("backend_declaration", "backend_loaded"),
        ("backend_declaration", "backend_invoked"),
        ("dry_run_plan", "dry_run_executed"),
        ("admission_packet", "control_plane_admission_granted"),
        ("readiness_receipt", "fan_pwm_write_performed"),
        ("readiness_receipt", "thermal_actuation_performed"),
        ("readiness_receipt", "power_profile_mutation_performed"),
        ("readiness_receipt", "service_restart_performed"),
        ("readiness_receipt", "file_cleanup_performed"),
        ("readiness_receipt", "provider_invocation_performed"),
        ("readiness_receipt", "network_performed"),
        ("readiness_receipt", "prompt_assembly_performed"),
    ],
)
def test_validation_rejects_forbidden_true_flags(record_name: str, flag: str) -> None:
    wing = build_fulfillment_executor_contract_wing(_consumed_receipt(), created_at=FIXED)
    record = replace(getattr(wing, record_name), **{flag: True, "digest": ""})
    validators = {
        "contract": validate_fulfillment_executor_contract,
        "backend_declaration": validate_executor_backend_declaration,
        "dry_run_plan": validate_executor_dry_run_plan,
        "admission_packet": validate_executor_admission_packet,
        "readiness_receipt": validate_executor_contract_readiness_receipt,
    }
    result = validators[record_name](record)
    assert not result.ok
    assert any(flag in finding for finding in result.findings)


def test_digests_are_deterministic_and_change_on_meaningful_metadata() -> None:
    one = build_fulfillment_executor_contract_wing(_consumed_receipt(), created_at=FIXED)
    two = build_fulfillment_executor_contract_wing(_consumed_receipt(), created_at=FIXED)
    assert one.readiness_receipt.digest == two.readiness_receipt.digest
    changed = replace(one.readiness_receipt, evidence_summary=one.readiness_receipt.evidence_summary + ("additional_reviewer_note",), digest="")
    assert executor_contract_readiness_receipt_digest(changed) != one.readiness_receipt.digest


def test_summaries_are_metadata_only_and_non_authorizing() -> None:
    wing = build_fulfillment_executor_contract_wing(_consumed_receipt(), created_at=FIXED)
    summaries = (
        summarize_fulfillment_executor_contract(wing.contract),
        summarize_executor_backend_declaration(wing.backend_declaration),
        summarize_executor_precondition_manifest(wing.precondition_manifest),
        summarize_executor_dry_run_plan(wing.dry_run_plan),
        summarize_executor_admission_packet(wing.admission_packet),
        summarize_executor_contract_readiness_receipt(wing.readiness_receipt),
    )
    for summary in summaries:
        assert summary["metadata_only"] is True
        assert summary.get("effect_performed") is not True
        assert summary.get("host_mutation_performed") is not True
    assert summaries[0]["executor_implemented"] is False
    assert summaries[1]["backend_invoked"] is False
    assert summaries[3]["dry_run_executed"] is False
    assert summaries[4]["control_plane_admission_granted"] is False
    assert summaries[5]["fulfillment_granted"] is False
