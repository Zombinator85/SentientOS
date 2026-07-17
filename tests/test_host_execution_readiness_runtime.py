from __future__ import annotations
from dataclasses import replace

import pytest

from sentientos.control_plane_kernel import AdmissionOutcome, AuthorityClass, ControlActionDecision, ControlPlaneKernel, LifecyclePhase
from sentientos.host_privilege_review_runtime import HostPrivilegeReviewRuntimeCoordinator
from sentientos.host_execution_readiness_runtime import HostExecutionReadinessRuntimeCoordinator, persist_evidence_bundle, validate_evaluation, world_state_records
from tests.test_host_privilege_review_runtime import _host_eval
from sentientos.effect_proof import build_execution_readiness_manifest, build_effect_receipt_contract, build_future_effect_receipt_schema, build_postcondition_check_plan, build_rollback_plan

pytestmark = pytest.mark.no_legacy_skip

def _priv_eval(tmp_path):
    host_eval, host_coord = _host_eval(tmp_path)
    priv = HostPrivilegeReviewRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path)
    ev = priv.run_cycle(tick_id="tick", source_evaluation=host_eval)
    assert ev is not None
    return ev, host_coord, priv

def test_consumes_exact_in_memory_rehearsal_and_duplicate_returns_prior(tmp_path):
    ev, host_coord, priv = _priv_eval(tmp_path)
    c = HostExecutionReadinessRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path)
    out = c.run_cycle(tick_id="tick2", source_evaluation=ev, correlation_id="corr")
    again = c.run_cycle(tick_id="tick3", source_evaluation=ev, correlation_id="corr")
    assert out is again
    assert out is not None and out.source_privilege_review_evaluation_id == ev.evaluation_id
    assert host_coord.collector_call_count == 3
    assert priv.builder_call_count == len(ev.items) * 4
    assert c.builder_call_count == out.summary.valid_item_count * 9
    assert validate_evaluation(out).ok
    assert all(i.source_ref and i.source_ref.fulfillment_rehearsal_receipt_id == i.effect_receipt_contract.source_rehearsal_receipt_id for i in out.items if i.valid_source)

def test_non_allow_admission_zero_builders(tmp_path):
    ev, _, _ = _priv_eval(tmp_path)
    c = HostExecutionReadinessRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path)
    deny = ControlActionDecision(AdmissionOutcome.DENY, ("test",), LifecyclePhase.MAINTENANCE, LifecyclePhase.MAINTENANCE, AuthorityClass.PROPOSAL_EVALUATION, "host_execution_readiness_authorization_review_runtime", "test", "host_execution_readiness_authorization_review_runtime", {}, "corr")
    assert c.run_cycle(tick_id="deny", source_evaluation=ev, decision=deny) is None
    assert c.builder_call_count == 0

def test_gate_truthfulness_and_no_effect_posture(tmp_path):
    ev, _, _ = _priv_eval(tmp_path)
    receipt = next(i.fulfillment_rehearsal_receipt for i in ev.items if i.fulfillment_rehearsal_receipt is not None)
    contract = build_effect_receipt_contract(receipt)
    schema = build_future_effect_receipt_schema(contract)
    post = build_postcondition_check_plan(contract)
    rollback = build_rollback_plan(contract)
    manifest = build_execution_readiness_manifest(contract, schema, post, rollback)
    assert set(manifest.satisfied_proof_gates) >= {"rehearsal_required", "dry_run_required", "rollback_plan_required"}
    assert "effect_receipt_required" in manifest.missing_proof_gates
    assert "postcondition_check_required" in manifest.missing_proof_gates
    assert "control_plane_admission_required" in manifest.missing_proof_gates
    assert not manifest.authorization_granted and not manifest.effect_performed

def test_external_bundle_and_world_state_review_only(tmp_path):
    ev, _, _ = _priv_eval(tmp_path)
    c = HostExecutionReadinessRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path)
    out = c.run_cycle(tick_id="bundle", source_evaluation=ev)
    assert out is not None
    receipt = persist_evidence_bundle(tmp_path, out, tick_id="bundle")
    assert receipt.artifact_root.startswith(str(tmp_path))
    records = world_state_records(out)
    assert records and {r["stage"] for r in records} == {"review"}
    assert all(r["authorization_granted"] is False and r["effect_proven"] is False and r["host_mutation_performed"] is False for r in records)

def test_malformed_sibling_contained(tmp_path):
    ev, _, _ = _priv_eval(tmp_path)
    bad_item = replace(ev.items[0], fulfillment_rehearsal_receipt=replace(ev.items[0].fulfillment_rehearsal_receipt, does_not_execute=False))
    tampered = replace(ev, items=(bad_item,) + ev.items[1:])
    c = HostExecutionReadinessRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path)
    out = c.run_cycle(tick_id="tamper", source_evaluation=tampered)
    assert out is not None
    assert any(not i.valid_source for i in out.items)
    assert any(i.valid_source for i in out.items)
