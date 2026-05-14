from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.capability_registry import build_default_capability_registry, update_registry_from_controlled_authorization_ledger, update_registry_from_host_embodiment_trace
from sentientos.host_embodiment_trace import (
    build_host_embodiment_demo_trace,
    host_embodiment_trace_digest,
    summarize_host_embodiment_trace,
    validate_host_embodiment_trace,
    validate_host_embodiment_trace_step,
)

pytestmark = pytest.mark.no_legacy_skip


def test_default_demo_trace_builds_full_non_mutating_ladder_with_pwm_presence() -> None:
    trace = build_host_embodiment_demo_trace()
    kinds = [step.step_kind for step in trace.steps]
    for kind in [
        "collector_result", "host_inventory_manifest", "telemetry_snapshot", "pressure_report", "policy_decision",
        "proposal_receipt", "broker_decision", "broker_review_receipt", "fulfillment_plan", "fulfillment_rehearsal_receipt",
        "effect_contract", "future_effect_schema", "postcondition_plan", "rollback_plan", "execution_readiness_manifest",
        "authorization_review_packet", "authorization_review_decision", "authorization_review_receipt", "future_authorization_schema",
        "controlled_authorization_contract", "controlled_authorization_grant_record", "controlled_authorization_revocation_record", "controlled_authorization_ledger",
    ]:
        assert kind in kinds
    collector_summaries = [step.summary for step in trace.steps if step.step_kind == "collector_result"]
    assert any(summary.get("values", {}).get("pwm_signal_observed") is True for summary in collector_summaries)
    assert "fan_pwm_write" in trace.blocked_action_labels
    assert "real_fan_pwm_control" in trace.deferred_capability_labels
    assert trace.live_authorization_granted is False
    assert trace.effect_performed is False
    assert trace.host_mutation_performed is False
    assert validate_host_embodiment_trace(trace).ok


def test_trace_includes_required_blocked_and_deferred_labels() -> None:
    trace = build_host_embodiment_demo_trace()
    for label in ["fan_pwm_write", "thermal_actuation", "service_restart", "power_profile_mutation", "file_cleanup", "file_delete", "network_egress", "provider_invocation", "prompt_assembly", "federation_transport", "remote_execution"]:
        assert label in trace.blocked_action_labels
    for label in ["live_authorization_grant", "real_effect_execution", "real_rollback_execution", "real_service_restart", "real_power_profile_mutation", "real_file_cleanup"]:
        assert label in trace.deferred_capability_labels


def test_trace_summary_and_digest_are_reviewer_friendly_and_deterministic() -> None:
    trace = build_host_embodiment_demo_trace()
    summary = summarize_host_embodiment_trace(trace)
    assert summary["metadata_only"] is True
    assert summary["demo_only"] is True
    assert summary["live_authorization_granted"] is False
    assert host_embodiment_trace_digest(trace) == trace.digest
    changed = replace(trace, scenario_label="changed reviewer label", digest="")
    assert host_embodiment_trace_digest(changed) != trace.digest


def test_trace_validation_rejects_forbidden_runtime_claims() -> None:
    trace = build_host_embodiment_demo_trace()
    for flag in ["live_authorization_granted", "effect_performed", "host_mutation_performed", "network_performed", "provider_invocation_performed", "prompt_assembly_performed"]:
        assert not validate_host_embodiment_trace(replace(trace, **{flag: True})).ok
    step = trace.steps[0]
    assert not validate_host_embodiment_trace_step(replace(step, effect_performed=True)).ok
    assert not validate_host_embodiment_trace_step(replace(step, host_mutation_performed=True)).ok


def test_capability_registry_reflects_trace_as_demo_proof_and_live_execution_deferred() -> None:
    trace = build_host_embodiment_demo_trace()
    registry = update_registry_from_host_embodiment_trace(update_registry_from_controlled_authorization_ledger(build_default_capability_registry(), trace.steps[-1]), trace)
    by_id = registry.by_id()
    assert by_id["host_embodiment_trace"].status == "implemented"
    assert by_id["host_embodiment_trace"].authority_level == "demo_proof_only"
    assert by_id["controlled_authorization_contract"].authority_level == "contract_only"
    assert by_id["controlled_authorization_grant_record"].authority_level == "schema_only"
    assert by_id["controlled_authorization_ledger"].authority_level == "ledger_only"
    assert by_id["live_authorization_grant"].status == "deferred"
    assert by_id["real_effect_execution"].status == "deferred"
    assert by_id["real_rollback_execution"].status == "deferred"
    assert by_id["real_service_restart"].status == "blocked"
    assert by_id["real_fan_pwm_control"].status == "blocked"
    assert by_id["real_power_profile_mutation"].status == "blocked"
    assert by_id["real_file_cleanup"].status == "blocked"
