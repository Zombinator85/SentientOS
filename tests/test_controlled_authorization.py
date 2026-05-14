from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.actuation_fulfillment import build_actuation_fulfillment_plan, build_actuation_fulfillment_rehearsal_receipt
from sentientos.authorization_review import build_authorization_review_wing_for_execution_readiness
from sentientos.controlled_authorization import (
    build_controlled_authorization_grant_contract,
    build_controlled_authorization_grant_record,
    build_controlled_authorization_ledger,
    build_controlled_authorization_revocation_record,
    build_controlled_authorization_wing_for_review_receipt,
    controlled_authorization_grant_contract_digest,
    summarize_controlled_authorization_grant_contract,
    summarize_controlled_authorization_grant_record,
    summarize_controlled_authorization_ledger,
    summarize_controlled_authorization_revocation_record,
    validate_controlled_authorization_grant_contract,
    validate_controlled_authorization_grant_record,
    validate_controlled_authorization_ledger,
    validate_controlled_authorization_revocation_record,
)
from sentientos.effect_proof import build_execution_proof_wing_for_rehearsal_receipt
from tests.test_actuation_fulfillment import _broker_receipt_for

pytestmark = pytest.mark.no_legacy_skip


def _review(kind: str = "inspect_cpu_pressure_candidate", **kwargs):
    rehearsal = build_actuation_fulfillment_rehearsal_receipt(build_actuation_fulfillment_plan(_broker_receipt_for(kind, recorded=True, **kwargs)))
    proof = build_execution_proof_wing_for_rehearsal_receipt(rehearsal)
    return build_authorization_review_wing_for_execution_readiness(proof.execution_readiness_manifest)


def test_valid_authorization_review_receipt_builds_contract_and_schema_only_grant_record() -> None:
    review = _review(cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)
    wing = build_controlled_authorization_wing_for_review_receipt(review.receipt, review.future_authorization_grant_schema)
    assert wing.contract.status == "controlled_authorization_contract_ready"
    assert wing.grant_record.grant_status == "controlled_authorization_grant_schema_recorded"
    assert wing.contract.live_authorization_granted is False
    assert wing.grant_record.schema_only is True
    assert wing.grant_record.future_use_only is True
    assert wing.ledger.metadata_only is True
    assert wing.ledger.live_authorization_granted is False
    assert validate_controlled_authorization_grant_contract(wing.contract).ok
    assert validate_controlled_authorization_grant_record(wing.grant_record).ok
    assert validate_controlled_authorization_revocation_record(wing.revocation_record).ok
    assert validate_controlled_authorization_ledger(wing.ledger).ok


@pytest.mark.parametrize(
    ("receipt_status", "schema_status", "contract_status", "grant_status"),
    [
        ("authorization_review_receipt_blocked", "future_authorization_grant_schema_blocked", "controlled_authorization_contract_blocked", "controlled_authorization_grant_blocked"),
        ("authorization_review_receipt_incomplete", "future_authorization_grant_schema_incomplete", "controlled_authorization_contract_incomplete", "controlled_authorization_grant_incomplete"),
        ("authorization_review_receipt_contradicted", "future_authorization_grant_schema_contradicted", "controlled_authorization_contract_contradicted", "controlled_authorization_grant_contradicted"),
    ],
)
def test_review_terminal_statuses_map_to_controlled_authorization_statuses(receipt_status: str, schema_status: str, contract_status: str, grant_status: str) -> None:
    review = _review(cpu_utilization_percent=95)
    receipt = replace(review.receipt, receipt_status=receipt_status, digest="")
    schema = replace(review.future_authorization_grant_schema, schema_status=schema_status, source_authorization_review_receipt_digest=receipt.digest, digest="")
    contract = build_controlled_authorization_grant_contract(receipt, schema)
    record = build_controlled_authorization_grant_record(contract)
    assert contract.status == contract_status
    assert record.grant_status == grant_status


def test_future_scope_blocks_and_gates_are_preserved() -> None:
    cooling = build_controlled_authorization_wing_for_review_receipt(_review("future_cooling_policy_candidate", thermal_zone_temperatures_c={"cpu": 91}).receipt, _review("future_cooling_policy_candidate", thermal_zone_temperatures_c={"cpu": 91}).future_authorization_grant_schema)
    gates = set(cooling.contract.required_grant_gates)
    for gate in ["operator_identity_required", "policy_identity_required", "explicit_scope_required", "time_bounds_required", "expiry_required", "revocation_path_required", "control_plane_admission_required", "audit_receipt_required", "rollback_plan_required", "rollback_receipt_required", "effect_receipt_required", "postcondition_check_required", "runtime_supervisor_observation_required", "immutable_trace_required", "panic_stop_required"]:
        assert gate in gates
    assert {"fan_pwm_write", "thermal_actuation"}.issubset(set(cooling.contract.blocked_actions))

    power = build_controlled_authorization_wing_for_review_receipt(_review("future_power_policy_candidate", battery_percent=5, battery_charging=False).receipt, _review("future_power_policy_candidate", battery_percent=5, battery_charging=False).future_authorization_grant_schema)
    cleanup = build_controlled_authorization_wing_for_review_receipt(_review("future_cleanup_policy_candidate", disk_utilization_percent=95).receipt, _review("future_cleanup_policy_candidate", disk_utilization_percent=95).future_authorization_grant_schema)
    service_review = _review("inspect_service_health_candidate", service_health_labels=("daemon_degraded",))
    service = build_controlled_authorization_wing_for_review_receipt(service_review.receipt, service_review.future_authorization_grant_schema)
    assert "power_profile_mutation" in power.contract.blocked_actions
    assert {"file_cleanup", "file_delete"}.issubset(set(cleanup.contract.blocked_actions))
    assert {"service_restart", "process_kill"}.issubset(set(service.contract.blocked_actions))


def test_records_summaries_and_digests_are_metadata_only_and_deterministic() -> None:
    review = _review(cpu_utilization_percent=95)
    wing = build_controlled_authorization_wing_for_review_receipt(review.receipt, review.future_authorization_grant_schema)
    changed = replace(wing.contract, warning_codes=("meaningful_metadata_change",), digest="")
    assert controlled_authorization_grant_contract_digest(wing.contract) == wing.contract.digest
    assert controlled_authorization_grant_contract_digest(changed) != wing.contract.digest
    assert summarize_controlled_authorization_grant_contract(wing.contract)["contract_only"] is True
    assert summarize_controlled_authorization_grant_record(wing.grant_record)["schema_only"] is True
    assert summarize_controlled_authorization_revocation_record(wing.revocation_record)["future_use_only"] is True
    assert summarize_controlled_authorization_ledger(wing.ledger)["metadata_only"] is True


def test_validation_rejects_live_authority_effect_mutation_and_missing_forbidden_blocks() -> None:
    review = _review(cpu_utilization_percent=95)
    wing = build_controlled_authorization_wing_for_review_receipt(review.receipt, review.future_authorization_grant_schema)
    assert not validate_controlled_authorization_grant_contract(replace(wing.contract, live_authorization_granted=True)).ok
    assert not validate_controlled_authorization_grant_contract(replace(wing.contract, fulfillment_granted=True)).ok
    assert not validate_controlled_authorization_grant_contract(replace(wing.contract, effect_performed=True)).ok
    assert not validate_controlled_authorization_grant_contract(replace(wing.contract, host_mutation_performed=True)).ok
    assert not validate_controlled_authorization_grant_record(replace(wing.grant_record, live_authorization_granted=True)).ok
    assert not validate_controlled_authorization_revocation_record(replace(wing.revocation_record, live_revocation_performed=True)).ok
    assert not validate_controlled_authorization_ledger(replace(wing.ledger, live_authorization_granted=True)).ok
    assert not validate_controlled_authorization_grant_contract(replace(wing.contract, blocked_actions=())).ok
