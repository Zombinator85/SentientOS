from __future__ import annotations
import json, shutil, threading
from pathlib import Path
from unittest import mock
import pytest
from sentientos.host_real_effect_admission_runtime import HostRealEffectAdmissionRuntimeCoordinator, load_latest_evaluation, validate_persisted_admission_bundle, NO_AUTHORITY
from sentientos.host_dry_run_audit_closure_runtime import _sha as closure_sha, digest_record as closure_digest_record, validate_persisted_closure_bundle
from tests.test_host_dry_run_audit_closure_runtime import _closure_bundle, _rewrite_closure_manifests, _rewrite_closure_runtime_receipt
pytestmark = pytest.mark.no_legacy_skip

def closure_bundle(tmp_path: Path) -> Path:
    _src,bundle,_ev=_closure_bundle(tmp_path)
    return bundle

def test_valid_diagnostics_closure_produces_planning_eligible_evidence(tmp_path):
    ev=HostRealEffectAdmissionRuntimeCoordinator().evaluate(closure_bundle_root=closure_bundle(tmp_path), output_root=tmp_path/'out', admission_domain='diagnostics_real_effect_candidate')
    assert ev.status == 'host_real_effect_admission_runtime_recorded'
    assert ev.persisted is True
    assert ev.decision and ev.decision['admission_status'] == 'real_effect_admission_eligible_for_planning'
    assert ev.admission_bundle and ev.admission_bundle['bundle_status'] == 'real_effect_admission_eligible_for_planning'
    assert validate_persisted_admission_bundle(tmp_path/'out'/ev.request.request_id).ok  # type: ignore[union-attr]
    summary=load_latest_evaluation(tmp_path/'out')
    assert summary and summary.replayed is True

def test_policy_outcomes_preserved(tmp_path):
    bundle=closure_bundle(tmp_path)
    thermal=HostRealEffectAdmissionRuntimeCoordinator().evaluate(closure_bundle_root=bundle, output_root=tmp_path/'thermal', admission_domain='thermal_safety_real_effect_candidate')
    assert thermal.decision and thermal.decision['admission_status'] == 'real_effect_admission_eligible_with_conditions'
    for domain in ('future_cooling_real_effect_candidate','future_service_real_effect_candidate','future_power_real_effect_candidate','future_cleanup_real_effect_candidate'):
        ev=HostRealEffectAdmissionRuntimeCoordinator().evaluate(closure_bundle_root=bundle, output_root=tmp_path/domain, admission_domain=domain)
        assert ev.decision and ev.decision['admission_status'] == 'real_effect_admission_blocked'

def test_invalid_sources_stop_before_builder_calls(tmp_path):
    bundle=closure_bundle(tmp_path)
    c=HostRealEffectAdmissionRuntimeCoordinator()
    _rewrite_closure_manifests(bundle, legacy=True)
    assert c.evaluate(closure_bundle_root=bundle, output_root=tmp_path/'legacy').status.startswith('blocked')
    assert c.builder_call_count == 0
    bundle=closure_bundle(tmp_path/'tamper')
    (bundle/'source_dry_run_closure_bundle.json').write_text('{"tampered": true}', encoding='utf-8') if (bundle/'source_dry_run_closure_bundle.json').exists() else None
    (bundle/'dry_run_closure_bundle.json').write_text('{"tampered": true}', encoding='utf-8')
    assert c.evaluate(closure_bundle_root=bundle, output_root=tmp_path/'tampered').status.startswith('blocked')
    assert c.builder_call_count == 0
    bundle=closure_bundle(tmp_path/'incomplete')
    (bundle/'source_dry_run_receipt.json').unlink(); _rewrite_closure_manifests(bundle)
    assert c.evaluate(closure_bundle_root=bundle, output_root=tmp_path/'incomplete-out').status.startswith('blocked')
    assert c.builder_call_count == 0
    bundle=closure_bundle(tmp_path/'contradicted')
    closure=json.loads((bundle/'dry_run_closure_bundle.json').read_text()); closure['real_effect_performed']=True; (bundle/'dry_run_closure_bundle.json').write_text(json.dumps(closure, sort_keys=True), encoding='utf-8'); _rewrite_closure_manifests(bundle); _rewrite_closure_runtime_receipt(bundle)
    assert c.evaluate(closure_bundle_root=bundle, output_root=tmp_path/'contradicted-out').status.startswith('blocked')
    assert c.builder_call_count == 0

def test_domain_validators_corruption_and_authority_flags(tmp_path):
    ev=HostRealEffectAdmissionRuntimeCoordinator().evaluate(closure_bundle_root=closure_bundle(tmp_path), output_root=tmp_path/'out')
    root=tmp_path/'out'/ev.request.request_id  # type: ignore[union-attr]
    assert validate_persisted_admission_bundle(root).ok
    cand=json.loads((root/'candidate.json').read_text()); cand['digest']='sha256:bad'; (root/'candidate.json').write_text(json.dumps(cand, sort_keys=True), encoding='utf-8')
    assert not validate_persisted_admission_bundle(root).ok
    for payload in (ev.candidate, ev.decision, ev.plan_or_block_receipt, ev.admission_bundle, ev.runtime_receipt.to_dict()): # type: ignore[union-attr]
        for k,v in NO_AUTHORITY.items():
            if k in payload: assert payload[k] is v

def test_replay_after_source_deletion_zero_builder_calls_concurrency_and_conflict(tmp_path):
    source=closure_bundle(tmp_path); out=tmp_path/'out'; c=HostRealEffectAdmissionRuntimeCoordinator()
    ev1=c.evaluate(closure_bundle_root=source, output_root=out, correlation_id='same'); before=c.builder_call_count
    shutil.rmtree(source)
    ev2=c.evaluate(closure_bundle_root=source, output_root=out, correlation_id='same')
    assert ev2.replayed is True and c.builder_call_count == before
    assert validate_persisted_admission_bundle(out/ev1.request.request_id).ok  # type: ignore[union-attr]
    other=closure_bundle(tmp_path/'other')
    assert c.evaluate(closure_bundle_root=other, output_root=out, correlation_id='same').status.startswith('blocked')
    out2=tmp_path/'concurrent'; source2=closure_bundle(tmp_path/'csrc'); results=[]
    def run(): results.append(HostRealEffectAdmissionRuntimeCoordinator().evaluate(closure_bundle_root=source2, output_root=out2, correlation_id='cc'))
    ts=[threading.Thread(target=run) for _ in range(2)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert len([p for p in out2.iterdir() if p.is_dir()]) == 1 and sum(r.replayed for r in results) == 1

def test_replay_uses_zero_builder_calls(tmp_path):
    source=closure_bundle(tmp_path); out=tmp_path/'out'; c=HostRealEffectAdmissionRuntimeCoordinator()
    c.evaluate(closure_bundle_root=source, output_root=out, correlation_id='zero')
    with mock.patch('sentientos.host_real_effect_admission_runtime.build_real_effect_admission_wing', side_effect=AssertionError('builder called')):
        ev=c.evaluate(closure_bundle_root=source, output_root=out, correlation_id='zero')
    assert ev.replayed is True
