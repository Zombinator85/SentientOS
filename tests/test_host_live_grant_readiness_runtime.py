from __future__ import annotations
import pytest
pytestmark = pytest.mark.no_legacy_skip
from dataclasses import replace
import json
from sentientos.control_plane_kernel import AdmissionOutcome, AuthorityClass, ControlActionDecision, ControlPlaneKernel, LifecyclePhase
from sentientos.host_controlled_authorization_runtime import HostControlledAuthorizationRuntimeCoordinator
from sentientos.host_live_grant_readiness_runtime import HostLiveGrantReadinessRuntimeCoordinator, persist_evidence_bundle, validate_evaluation, world_state_records
from tests.test_host_controlled_authorization_runtime import _exec_eval

def _controlled(tmp_path):
    ev, *_ = _exec_eval(tmp_path)
    c = HostControlledAuthorizationRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path)
    out = c.run_cycle(tick_id='tick-ca', source_evaluation=ev, correlation_id='ca-corr')
    assert out is not None
    return out

def test_consumes_exact_in_memory_controlled_evaluation_and_duplicate_returns_prior(tmp_path):
    ev = _controlled(tmp_path)
    c = HostLiveGrantReadinessRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path)
    out = c.run_cycle(tick_id='tick-live', source_evaluation=ev, correlation_id='same')
    again = c.run_cycle(tick_id='other', source_evaluation=ev, correlation_id='same')
    assert out is again and out is not None
    assert out.source_controlled_authorization_evaluation_id == ev.evaluation_id
    assert c.builder_call_count == out.summary.valid_item_count * 4
    assert validate_evaluation(out).ok
    assert out.summary.local_grant_issued is False and out.summary.operator_approval_granted is False

def test_non_allow_admission_zero_builders(tmp_path):
    ev = _controlled(tmp_path)
    c = HostLiveGrantReadinessRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path)
    deny = ControlActionDecision(AdmissionOutcome.DENY, ('test',), LifecyclePhase.MAINTENANCE, LifecyclePhase.MAINTENANCE, AuthorityClass.PROPOSAL_EVALUATION, 'host_live_grant_readiness_runtime', 'test', 'host_live_grant_readiness_runtime', {}, 'corr')
    assert c.run_cycle(tick_id='deny', source_evaluation=ev, decision=deny) is None
    assert c.builder_call_count == 0

def test_one_cycle_per_tick_and_timestamp_independent_identity(tmp_path):
    ev = _controlled(tmp_path)
    c = HostLiveGrantReadinessRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path)
    out = c.run_cycle(tick_id='tick', source_evaluation=ev, correlation_id='one')
    assert out is not None
    assert c.run_cycle(tick_id='tick', source_evaluation=ev, correlation_id='two') is None
    again = HostLiveGrantReadinessRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path).run_cycle(tick_id='tick', source_evaluation=ev, correlation_id='one')
    assert again is not None and out.semantic_digest == again.semantic_digest

def test_source_tampering_and_manifest_mismatch_fail_closed(tmp_path):
    ev = _controlled(tmp_path)
    bad_item = replace(ev.items[0], safety_bundle=replace(ev.items[0].safety_bundle, safety_gate_satisfaction_manifest=replace(ev.items[0].safety_bundle.safety_gate_satisfaction_manifest, source_controlled_authorization_contract_digest='tampered')))
    bad = replace(ev, items=(bad_item,) + ev.items[1:])
    c = HostLiveGrantReadinessRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path)
    out = c.run_cycle(tick_id='tamper', source_evaluation=bad)
    assert out is not None
    assert any(not i.valid_source for i in out.items)
    assert c.builder_call_count < len(out.items) * 4

def test_prerequisites_do_not_infer_approvals_or_effects_and_propagate_missing(tmp_path):
    ev = _controlled(tmp_path)
    out = HostLiveGrantReadinessRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path).run_cycle(tick_id='truth', source_evaluation=ev)
    assert out is not None
    item = next(i for i in out.items if i.readiness_records)
    rec = item.readiness_records
    assert rec.approval_packet.approval_not_granted is True
    assert rec.preflight_receipt.grant_not_issued is True
    assert 'control_plane_admission_required' in rec.prerequisite_matrix.missing_labels
    assert 'effect_receipt_required' in rec.prerequisite_matrix.missing_labels
    assert rec.denial_deferral_receipt.grant_not_issued is True

def test_atomic_external_bundle_world_state_and_no_authority(tmp_path):
    ev = _controlled(tmp_path)
    out = HostLiveGrantReadinessRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path).run_cycle(tick_id='bundle', source_evaluation=ev)
    assert out is not None
    receipt = persist_evidence_bundle(tmp_path, out, tick_id='bundle')
    assert receipt.artifact_root.startswith(str(tmp_path))
    latest = json.loads((tmp_path / 'host_live_grant_readiness_runtime' / 'latest.json').read_text())
    assert latest['local_grant_issued'] is False
    records = world_state_records(out)
    assert records and {r['stage'] for r in records} == {'review'}
    assert all(r['payload']['local_grant_issued'] is False and r['payload']['effect_proven'] is False for r in records)
