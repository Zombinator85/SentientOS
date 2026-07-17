from __future__ import annotations
from dataclasses import replace

import pytest
from sentientos.control_plane_kernel import AdmissionOutcome, AuthorityClass, ControlActionDecision, ControlPlaneKernel, LifecyclePhase
from sentientos.host_controlled_authorization_runtime import HostControlledAuthorizationRuntimeCoordinator, persist_evidence_bundle, validate_evaluation, world_state_records
from sentientos.host_execution_readiness_runtime import HostExecutionReadinessRuntimeCoordinator
from tests.test_host_execution_readiness_runtime import _priv_eval

pytestmark = pytest.mark.no_legacy_skip

def _exec_eval(tmp_path):
    ev, host_coord, priv = _priv_eval(tmp_path)
    ex = HostExecutionReadinessRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path)
    out = ex.run_cycle(tick_id='tick-exec', source_evaluation=ev, correlation_id='exec-corr')
    assert out is not None
    return out, host_coord, priv, ex

def test_consumes_exact_in_memory_execution_readiness_and_duplicate_returns_prior(tmp_path):
    ev, host_coord, priv, ex = _exec_eval(tmp_path)
    c = HostControlledAuthorizationRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path)
    out = c.run_cycle(tick_id='tick-ca', source_evaluation=ev, correlation_id='same')
    again = c.run_cycle(tick_id='another', source_evaluation=ev, correlation_id='same')
    assert out is again
    assert out is not None and out.source_execution_readiness_evaluation_id == ev.evaluation_id
    assert host_coord.collector_call_count == 3
    assert c.builder_call_count == out.summary.valid_item_count * 5
    assert validate_evaluation(out).ok
    assert all(i.controlled_authorization.contract.source_authorization_review_receipt_id == i.source_ref.authorization_review_receipt_id for i in out.items if i.valid_source)

def test_non_allow_admission_zero_builders(tmp_path):
    ev, *_ = _exec_eval(tmp_path)
    c = HostControlledAuthorizationRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path)
    deny = ControlActionDecision(AdmissionOutcome.DENY, ('test',), LifecyclePhase.MAINTENANCE, LifecyclePhase.MAINTENANCE, AuthorityClass.PROPOSAL_EVALUATION, 'host_controlled_authorization_safety_runtime', 'test', 'host_controlled_authorization_safety_runtime', {}, 'corr')
    assert c.run_cycle(tick_id='deny', source_evaluation=ev, decision=deny) is None
    assert c.builder_call_count == 0

def test_linkage_safety_truth_and_timestamp_independent_identity(tmp_path):
    ev, *_ = _exec_eval(tmp_path)
    c = HostControlledAuthorizationRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path)
    out = c.run_cycle(tick_id='link', source_evaluation=ev)
    assert out is not None
    item = next(i for i in out.items if i.valid_source)
    ca = item.controlled_authorization; sb = item.safety_bundle
    assert ca.grant_record.contract_id == ca.contract.contract_id
    assert ca.ledger.live_authorization_granted is False
    assert sb.safety_gate_satisfaction_manifest.source_controlled_authorization_contract_id == ca.contract.contract_id
    assert sb.safety_gate_satisfaction_manifest.grants_live_authorization is False
    again = HostControlledAuthorizationRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path).run_cycle(tick_id='link', source_evaluation=ev)
    assert again is not None
    assert out.semantic_digest == again.semantic_digest

def test_mismatch_and_nested_tampering_contained(tmp_path):
    ev, *_ = _exec_eval(tmp_path)
    bad = replace(ev.items[0], future_authorization_grant_schema=replace(ev.items[0].future_authorization_grant_schema, source_authorization_review_receipt_digest='tampered'))
    tampered = replace(ev, items=(bad,) + ev.items[1:])
    c = HostControlledAuthorizationRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path)
    out = c.run_cycle(tick_id='tamper', source_evaluation=tampered)
    assert out is not None
    assert any(not i.valid_source for i in out.items)
    assert any(i.valid_source for i in out.items)

def test_external_bundle_and_world_state_review_only(tmp_path):
    ev, *_ = _exec_eval(tmp_path)
    c = HostControlledAuthorizationRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path)
    out = c.run_cycle(tick_id='bundle', source_evaluation=ev)
    assert out is not None
    receipt = persist_evidence_bundle(tmp_path, out, tick_id='bundle')
    assert receipt.artifact_root.startswith(str(tmp_path))
    records = world_state_records(out)
    assert records and {r['stage'] for r in records} == {'review'}
    assert all(r['live_authorization_granted'] is False and r['effect_proven'] is False and r['host_mutation_performed'] is False for r in records)
