from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.dry_run_execution_harness import (
    DryRunExecutionBlockReceipt,
    build_default_simulated_backend_registry,
    build_dry_run_execution_harness_wing,
    dry_run_execution_receipt_digest,
    run_dry_run_execution,
    summarize_dry_run_execution_block_receipt,
    summarize_dry_run_execution_receipt,
    summarize_dry_run_execution_request,
    summarize_dry_run_execution_result,
    summarize_simulated_backend_registry,
    validate_dry_run_execution_block_receipt,
    validate_dry_run_execution_receipt,
    validate_dry_run_execution_request,
    validate_dry_run_execution_result,
    validate_simulated_backend_registry,
)
from sentientos.fulfillment_executor_contract import build_fulfillment_executor_contract_wing
from tests.test_fulfillment_executor_contract import _consumed_receipt
from tests.test_fulfillment_authorization import FIXED

pytestmark = pytest.mark.no_legacy_skip


def _readiness(domain: str = "future_cooling_fulfillment_authorization"):
    return build_fulfillment_executor_contract_wing(_consumed_receipt(domain), created_at=FIXED).readiness_receipt


def test_ready_executor_contract_runs_simulated_dry_run_without_real_effects() -> None:
    wing = build_dry_run_execution_harness_wing(_readiness(), created_at=FIXED)
    assert wing.request.request_status in {"dry_run_execution_request_recorded", "dry_run_execution_request_recorded_with_warnings"}
    assert wing.receipt is not None
    result = wing.result_or_block_receipt
    assert result.result_status in {"dry_run_execution_simulated", "dry_run_execution_simulated_with_warnings"}
    assert result.dry_run_executed is True
    assert result.real_backend_invoked is False
    assert result.real_fulfillment_performed is False
    assert result.effect_performed is False
    assert result.host_mutation_performed is False
    assert wing.receipt.real_fulfillment_performed is False
    assert wing.receipt.real_effect_performed is False
    assert wing.receipt.host_mutation_performed is False
    assert validate_simulated_backend_registry(wing.registry).ok
    assert validate_dry_run_execution_request(wing.request).ok
    assert validate_dry_run_execution_result(result).ok
    assert validate_dry_run_execution_receipt(wing.receipt).ok


@pytest.mark.parametrize(
    ("readiness_status", "expected"),
    [
        ("executor_contract_readiness_blocked", "dry_run_execution_receipt_blocked"),
        ("executor_contract_readiness_incomplete", "dry_run_execution_receipt_incomplete"),
        ("executor_contract_readiness_contradicted", "dry_run_execution_receipt_contradicted"),
    ],
)
def test_non_ready_executor_readiness_produces_block_receipt(readiness_status: str, expected: str) -> None:
    receipt = replace(_readiness(), readiness_status=readiness_status, digest="")
    wing = build_dry_run_execution_harness_wing(receipt, created_at=FIXED)
    assert wing.receipt is None
    assert isinstance(wing.result_or_block_receipt, DryRunExecutionBlockReceipt)
    assert wing.result_or_block_receipt.block_status == expected
    assert wing.result_or_block_receipt.dry_run_executed is False
    assert wing.result_or_block_receipt.host_mutation_performed is False
    assert validate_dry_run_execution_block_receipt(wing.result_or_block_receipt).ok


def test_unknown_backend_class_produces_block_receipt() -> None:
    wing = build_dry_run_execution_harness_wing(_readiness(), requested_simulated_backend_class="unknown_backend", created_at=FIXED)
    assert wing.receipt is None
    assert isinstance(wing.result_or_block_receipt, DryRunExecutionBlockReceipt)
    assert "request:unknown_simulated_backend_class" in wing.result_or_block_receipt.block_reason_codes


@pytest.mark.parametrize(
    ("domain", "dry_run_domain", "backend", "blocked"),
    [
        ("future_cooling_fulfillment_authorization", "future_cooling_dry_run", "cooling_backend_simulated", {"fan_pwm_write", "thermal_actuation"}),
        ("future_power_fulfillment_authorization", "future_power_dry_run", "power_backend_simulated", {"power_profile_mutation"}),
        ("future_cleanup_fulfillment_authorization", "future_cleanup_dry_run", "cleanup_backend_simulated", {"file_cleanup", "file_delete"}),
        ("future_service_fulfillment_authorization", "future_service_dry_run", "service_backend_simulated", {"service_restart", "process_kill"}),
    ],
)
def test_future_domain_specific_blocks_are_preserved(domain: str, dry_run_domain: str, backend: str, blocked: set[str]) -> None:
    wing = build_dry_run_execution_harness_wing(_readiness(domain), requested_dry_run_domain=dry_run_domain, requested_simulated_backend_class=backend, created_at=FIXED)
    assert wing.receipt is not None
    assert blocked <= set(wing.request.blocked_actions)
    assert blocked <= set(wing.result_or_block_receipt.blocked_actions)
    assert blocked <= set(wing.receipt.blocked_actions)


@pytest.mark.parametrize(
    ("flag", "validator"),
    [
        ("real_backend_invoked", validate_dry_run_execution_result),
        ("real_fulfillment_performed", validate_dry_run_execution_result),
        ("real_effect_performed", validate_dry_run_execution_result),
        ("host_mutation_performed", validate_dry_run_execution_result),
        ("fan_pwm_write_performed", validate_dry_run_execution_result),
        ("thermal_actuation_performed", validate_dry_run_execution_result),
        ("power_profile_mutation_performed", validate_dry_run_execution_result),
        ("service_restart_performed", validate_dry_run_execution_result),
        ("file_cleanup_performed", validate_dry_run_execution_result),
        ("network_performed", validate_dry_run_execution_result),
        ("provider_invocation_performed", validate_dry_run_execution_result),
        ("prompt_assembly_performed", validate_dry_run_execution_result),
        ("subprocess_execution_performed", validate_dry_run_execution_result),
        ("shell_execution_performed", validate_dry_run_execution_result),
        ("control_plane_admission_execution_performed", validate_dry_run_execution_result),
    ],
)
def test_validation_rejects_forbidden_execution_flags(flag, validator) -> None:
    wing = build_dry_run_execution_harness_wing(_readiness(), created_at=FIXED)
    bad = replace(wing.result_or_block_receipt, **{flag: True}) if hasattr(wing.result_or_block_receipt, flag) else {**wing.result_or_block_receipt.to_dict(), flag: True}
    result = validator(bad)
    assert not result.ok
    assert any(flag in finding for finding in result.findings)


def test_receipt_validation_rejects_real_fulfillment_and_host_mutation() -> None:
    wing = build_dry_run_execution_harness_wing(_readiness(), created_at=FIXED)
    assert wing.receipt is not None
    for flag in ["real_backend_invoked", "real_fulfillment_performed", "real_effect_performed", "host_mutation_performed", "network_performed", "provider_invocation_performed", "prompt_assembly_performed"]:
        bad = replace(wing.receipt, **{flag: True})
        result = validate_dry_run_execution_receipt(bad)
        assert not result.ok
        assert any(flag in finding for finding in result.findings)


def test_digests_are_deterministic_and_change_on_meaningful_metadata() -> None:
    first = build_dry_run_execution_harness_wing(_readiness(), created_at=FIXED)
    second = build_dry_run_execution_harness_wing(_readiness(), created_at=FIXED)
    assert first.receipt is not None and second.receipt is not None
    assert first.receipt.digest == second.receipt.digest
    changed = replace(first.receipt, evidence_summary=first.receipt.evidence_summary + ("extra_review_note",), digest="")
    changed = replace(changed, digest=dry_run_execution_receipt_digest(changed))
    assert changed.digest != first.receipt.digest


def test_summaries_are_metadata_only_and_registry_is_simulated_only() -> None:
    wing = build_dry_run_execution_harness_wing(_readiness(), created_at=FIXED)
    assert summarize_simulated_backend_registry(wing.registry)["metadata_only"] is True
    assert summarize_simulated_backend_registry(wing.registry)["simulated_only"] is True
    assert summarize_simulated_backend_registry(wing.registry)["no_real_backends"] is True
    assert summarize_dry_run_execution_request(wing.request)["metadata_only"] is True
    assert summarize_dry_run_execution_result(wing.result_or_block_receipt)["simulated_only"] is True
    assert wing.receipt is not None
    assert summarize_dry_run_execution_receipt(wing.receipt)["dry_run_receipt_only"] is True


def test_registry_missing_backend_blocks_execution() -> None:
    registry = replace(build_default_simulated_backend_registry(created_at=FIXED), backend_records=(), digest="")
    wing = build_dry_run_execution_harness_wing(_readiness(), registry=registry, created_at=FIXED)
    assert wing.receipt is None
    assert summarize_dry_run_execution_block_receipt(wing.result_or_block_receipt)["dry_run_executed"] is False


def test_executor_contract_readiness_to_dry_run_wing_records_non_mutating_posture() -> None:
    wing = build_dry_run_execution_harness_wing(_readiness(), created_at=FIXED)
    assert wing.registry.no_real_backends is True
    assert wing.request.does_not_execute_real_backend is True
    assert wing.receipt is not None
    assert wing.receipt.dry_run_executed is True
    assert wing.receipt.real_backend_invoked is False
    assert wing.receipt.real_fulfillment_performed is False
    assert wing.receipt.real_effect_performed is False
