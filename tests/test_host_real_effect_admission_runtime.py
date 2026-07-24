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

def _rewrite_admission_manifests(root: Path) -> None:
    coord=HostRealEffectAdmissionRuntimeCoordinator()
    content=coord._manifest(root)
    (root/'content_manifest.json').write_text(json.dumps(content, sort_keys=True, indent=2), encoding='utf-8')
    receipt=json.loads((root/'runtime_receipt.json').read_text())
    receipt['content_manifest_digest']=content['content_manifest_digest']
    from sentientos.host_real_effect_admission_runtime import HostRealEffectAdmissionRuntimeReceipt, digest_record
    receipt['digest']=''
    rec=HostRealEffectAdmissionRuntimeReceipt(**receipt)
    receipt['digest']=digest_record(rec)
    (root/'runtime_receipt.json').write_text(json.dumps(receipt, sort_keys=True, indent=2), encoding='utf-8')
    final=coord._manifest(root, final=True)
    (root/'final_bundle_manifest.json').write_text(json.dumps(final, sort_keys=True, indent=2), encoding='utf-8')

def _fresh_runtime_root(tmp_path: Path, *, domain: str='diagnostics_real_effect_candidate') -> Path:
    ev=HostRealEffectAdmissionRuntimeCoordinator().evaluate(closure_bundle_root=closure_bundle(tmp_path), output_root=tmp_path/'out', admission_domain=domain)
    assert ev.request is not None
    return tmp_path/'out'/ev.request.request_id

def test_deep_validator_rejects_recomputed_semantic_substitutions(tmp_path):
    cases=(
        ('source_closure_reference.json', lambda d: d.update(source_closure_bundle_digest='sha256:substituted')),
        ('source_dry_run_closure_bundle.json', lambda d: d.update(bundle_id='substituted-bundle')),
        ('runtime_plan.json', lambda d: d.update(request_id='substituted-request')),
        ('candidate.json', lambda d: d.update(source_dry_run_closure_bundle_id='substituted-source')),
        ('admission_decision.json', lambda d: d.update(admission_domain='future_power_real_effect_candidate')),
        ('plan_or_block_receipt.json', lambda d: d.update(candidate_id='substituted-candidate')),
        ('real_effect_admission_bundle.json', lambda d: d.update(candidate_id='substituted-candidate')),
        ('runtime_receipt.json', lambda d: d.update(candidate_digest='sha256:substituted')),
    )
    for i,(name, mutate) in enumerate(cases):
        root=_fresh_runtime_root(tmp_path/f'case{i}')
        data=json.loads((root/name).read_text())
        mutate(data)
        if name in {'candidate.json','admission_decision.json','plan_or_block_receipt.json','real_effect_admission_bundle.json','runtime_receipt.json'}:
            data['digest']=''
        (root/name).write_text(json.dumps(data, sort_keys=True, indent=2), encoding='utf-8')
        _rewrite_admission_manifests(root)
        assert not validate_persisted_admission_bundle(root).ok, name

def test_deep_validator_rejects_plan_block_and_authority_substitution(tmp_path):
    root=_fresh_runtime_root(tmp_path/'blocked', domain='future_power_real_effect_candidate')
    block=json.loads((root/'plan_or_block_receipt.json').read_text())
    block['receipt_id']=None
    block['plan_id']='fake-plan'
    block['digest']='sha256:fake'
    (root/'plan_or_block_receipt.json').write_text(json.dumps(block, sort_keys=True, indent=2), encoding='utf-8')
    _rewrite_admission_manifests(root)
    assert not validate_persisted_admission_bundle(root).ok
    root=_fresh_runtime_root(tmp_path/'flag')
    receipt=json.loads((root/'runtime_receipt.json').read_text())
    receipt['authorizes_execution']=True
    receipt['digest']=''
    (root/'runtime_receipt.json').write_text(json.dumps(receipt, sort_keys=True, indent=2), encoding='utf-8')
    _rewrite_admission_manifests(root)
    assert not validate_persisted_admission_bundle(root).ok

def test_manifest_duplicates_unmanifested_and_symlinks_rejected(tmp_path):
    root=_fresh_runtime_root(tmp_path/'manifest')
    final=json.loads((root/'final_bundle_manifest.json').read_text())
    final['files'].append(dict(final['files'][0]))
    final['final_bundle_digest']=closure_sha({'files': final['files'], 'artifact_kind': final['artifact_kind']})
    (root/'final_bundle_manifest.json').write_text(json.dumps(final, sort_keys=True), encoding='utf-8')
    assert not validate_persisted_admission_bundle(root).ok
    root=_fresh_runtime_root(tmp_path/'extra')
    (root/'evil.json').write_text('{}', encoding='utf-8')
    assert not validate_persisted_admission_bundle(root).ok
    root=_fresh_runtime_root(tmp_path/'linkroot')
    link=tmp_path/'bundle-link'; link.symlink_to(root, target_is_directory=True)
    assert not validate_persisted_admission_bundle(link).ok
    root=_fresh_runtime_root(tmp_path/'linkfile')
    (root/'candidate.json').unlink(); (root/'candidate.json').symlink_to(root/'runtime_request.json')
    assert not validate_persisted_admission_bundle(root).ok

def test_latest_loading_uses_deep_validator_without_builder_calls(tmp_path):
    source=closure_bundle(tmp_path); out=tmp_path/'out'
    HostRealEffectAdmissionRuntimeCoordinator().evaluate(closure_bundle_root=source, output_root=out, correlation_id='latest-zero')
    with mock.patch('sentientos.host_real_effect_admission_runtime.build_real_effect_admission_wing', side_effect=AssertionError('builder called')):
        assert load_latest_evaluation(out) is not None
