from __future__ import annotations
import json, shutil, threading
from pathlib import Path
import pytest
from sentientos.host_local_diagnostic_execution_runtime import HostLocalDiagnosticExecutionRuntimeCoordinator
from sentientos.host_local_diagnostic_rollback_runtime import HostLocalDiagnosticRollbackRuntimeCoordinator, validate_persisted_rollback_bundle
from sentientos.host_local_diagnostic_execution_source_runtime import _raw_sha, _sha
from sentientos.local_diagnostic_effect import run_local_diagnostic_exact_rollback_wing
from tests.host_local_diagnostic_execution_fixture import NOW, build_diagnostic_execution_fixture

pytestmark=pytest.mark.no_legacy_skip

def _execution(root:Path):
    f=build_diagnostic_execution_fixture(root); calls=[]
    from sentientos.builtin_runner_transaction_orchestrator import run_builtin_runner_transaction_wing
    def runner(**kw): calls.append(1); return run_builtin_runner_transaction_wing(**kw)
    c=HostLocalDiagnosticExecutionRuntimeCoordinator(runner=runner); p=c.preflight(execution_source_bundle_root=f.source_bundle,expected_source_bundle_digest=f.source_digest,current_snapshot=f.snapshot,current_verification=f.verification,execution_time=NOW); ch=p.records['confirmation_challenge']
    e=c.execute(execution_source_bundle_root=f.source_bundle,expected_source_bundle_digest=f.source_digest,current_snapshot=f.snapshot,current_verification=f.verification,execution_time=NOW,output_root=root/'execution',confirm_local_diagnostic_write=True,confirm_source_bundle_digest=f.source_digest,confirm_effect_output_dir=str(f.target),confirmation_challenge_digest=ch['confirmation_challenge_digest'])
    digest=json.loads((Path(e.bundle_root)/'bundle_manifest.json').read_text())['bundle_digest']; return f,e,digest,calls

def _args(root:Path,f,e,digest):
    c=HostLocalDiagnosticRollbackRuntimeCoordinator(); p=c.preflight(execution_bundle_root=e.bundle_root,expected_execution_bundle_digest=digest,current_snapshot=f.snapshot,current_verification=f.verification,rollback_time=NOW); ch=p.records['confirmation_challenge']
    return c,p,dict(execution_bundle_root=e.bundle_root,expected_execution_bundle_digest=digest,current_snapshot=f.snapshot,current_verification=f.verification,rollback_time=NOW,output_root=root/'rollback',confirm_exact_rollback=True,confirm_execution_bundle_digest=digest,confirm_artifact_path=ch['historical_artifact_path'],confirmation_challenge_digest=ch['confirmation_challenge_digest'],correlation_id='rollback-proof')

def test_preflight_is_read_only_and_binds_completed_execution(tmp_path:Path)->None:
    f,e,digest,_=_execution(tmp_path); before={p:str(p.stat().st_mtime_ns) for p in tmp_path.rglob('*')}; _,p,_=_args(tmp_path,f,e,digest)
    assert p.status=='host_local_diagnostic_rollback_preflight_ready'; ch=p.records['confirmation_challenge']; assert ch['completed_execution_bundle_digest']==digest and ch['required_authority_scope']=='local_diagnostic_exact_rollback'; assert before=={p:str(p.stat().st_mtime_ns) for p in tmp_path.rglob('*')}

def test_operator_confirmed_exact_rollback_executes_once_and_validates_bundle(tmp_path:Path)->None:
    f,e,digest,execution_calls=_execution(tmp_path); sibling=f.target/'sibling.txt'; sibling.write_text('keep'); c,_,args=_args(tmp_path,f,e,digest); calls=[]
    def rollback(*a,**kw): calls.append(1); return run_local_diagnostic_exact_rollback_wing(*a,**kw)
    c.rollback=rollback; r=c.rollback_execution(**args); assert r.status=='host_local_diagnostic_rollback_completed' and len(execution_calls)==1 and calls==[1] and r.rollback_call_count==1; assert not (f.target/'sentientos_local_diagnostic_effect.json').exists() and sibling.read_text()=='keep'; assert validate_persisted_rollback_bundle(r.bundle_root).status=='host_local_diagnostic_rollback_completed'; assert r.records['updated_lifecycle_report']['lifecycle_status']=='local_effect_lifecycle_complete_with_rollback'

def test_changed_or_missing_live_target_blocks_before_rollback(tmp_path:Path)->None:
    for mode in ('changed','missing'):
        root=tmp_path/mode; f,e,digest,_=_execution(root); artifact=f.target/'sentientos_local_diagnostic_effect.json'; artifact.write_text('changed') if mode=='changed' else artifact.unlink(); calls=[]; c=HostLocalDiagnosticRollbackRuntimeCoordinator(rollback=lambda *a,**k:calls.append(1)); p=c.preflight(execution_bundle_root=e.bundle_root,expected_execution_bundle_digest=digest,current_snapshot=f.snapshot,current_verification=f.verification,rollback_time=NOW); assert p.status.startswith('blocked_') and calls==[] and not (root/'rollback').exists()

def test_completed_rollback_replay_is_read_only_after_execution_bundle_deletion(tmp_path:Path)->None:
    f,e,digest,_=_execution(tmp_path); c,_,args=_args(tmp_path,f,e,digest); r=c.rollback_execution(**args); shutil.rmtree(e.bundle_root); before={p:p.read_bytes() for p in (tmp_path/'rollback').rglob('*') if p.is_file()}; again=c.rollback_execution(**args); assert again.replayed and again.rollback_call_count==0 and again.status=='host_local_diagnostic_rollback_completed'; assert before=={p:p.read_bytes() for p in (tmp_path/'rollback').rglob('*') if p.is_file()}

def test_rollback_returned_crash_reconciles_without_second_call(tmp_path:Path)->None:
    f,e,digest,_=_execution(tmp_path); calls=[]
    def rollback(*a,**kw): calls.append(1); return run_local_diagnostic_exact_rollback_wing(*a,**kw)
    def fail(state):
        if state=='rollback_returned': raise RuntimeError('crash')
    c,_,args=_args(tmp_path,f,e,digest); c.rollback=rollback; c.failure_hook=fail
    with pytest.raises(RuntimeError): c.rollback_execution(**args)
    c.failure_hook=None; r=c.rollback_execution(**args); assert r.reconciled and r.rollback_call_count==0 and calls==[1]

def test_rollback_committed_crash_never_retries(tmp_path:Path)->None:
    f,e,digest,_=_execution(tmp_path); calls=[]; c,_,args=_args(tmp_path,f,e,digest); c.rollback=lambda *a,**k:calls.append(1); c.failure_hook=lambda state: (_ for _ in ()).throw(RuntimeError('crash')) if state=='invocation_committed' else None
    with pytest.raises(RuntimeError): c.rollback_execution(**args)
    c.failure_hook=None; r=c.rollback_execution(**args); assert r.status=='host_local_diagnostic_rollback_ambiguous' and r.rollback_call_count==0 and calls==[]

def test_concurrent_identical_rollback_invokes_once(tmp_path:Path)->None:
    f,e,digest,_=_execution(tmp_path); c,_,args=_args(tmp_path,f,e,digest); calls=[]; entered=threading.Event(); release=threading.Event()
    def rollback(*a,**kw): calls.append(1); entered.set(); release.wait(); return run_local_diagnostic_exact_rollback_wing(*a,**kw)
    c.rollback=rollback; results=[]; t1=threading.Thread(target=lambda:results.append(c.rollback_execution(**args))); t2=threading.Thread(target=lambda:results.append(c.rollback_execution(**args))); t1.start(); entered.wait(); t2.start(); release.set(); t1.join(); t2.join(); assert calls==[1] and sorted(x.rollback_call_count for x in results)==[0,1]

def _rehash(root:Path)->None:
    content=json.loads((root/'content_manifest.json').read_text()); content['files']=[{'relative_filename':n,'size_bytes':len((root/n).read_bytes()),'sha256':_raw_sha((root/n).read_bytes())} for n in sorted(x['relative_filename'] for x in content['files'])]; check=dict(content); check.pop('content_manifest_digest',None); content['content_manifest_digest']=_sha(check); (root/'content_manifest.json').write_text(json.dumps(content,sort_keys=True,separators=(',',':'))+'\n')
    receipt=json.loads((root/'runtime_receipt.json').read_text()); receipt['content_manifest_digest']=content['content_manifest_digest']; receipt['digest']=''; from sentientos.host_local_diagnostic_execution_source_runtime import digest_record; receipt['digest']=digest_record(receipt); (root/'runtime_receipt.json').write_text(json.dumps(receipt,sort_keys=True,separators=(',',':'))+'\n')
    manifest=json.loads((root/'bundle_manifest.json').read_text()); manifest['files']=[{'relative_filename':n,'size_bytes':len((root/n).read_bytes()),'sha256':_raw_sha((root/n).read_bytes())} for n in sorted(x['relative_filename'] for x in manifest['files'])]; check=dict(manifest); check.pop('bundle_digest',None); manifest['bundle_digest']=_sha(check); (root/'bundle_manifest.json').write_text(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n')

def test_recomputed_rollback_bundle_tampering_is_rejected(tmp_path:Path)->None:
    f,e,digest,_=_execution(tmp_path); c,_,args=_args(tmp_path,f,e,digest); r=c.rollback_execution(**args); root=Path(r.bundle_root); data=json.loads((root/'runtime_result.json').read_text()); data['network_performed']=True; (root/'runtime_result.json').write_text(json.dumps(data,sort_keys=True,separators=(',',':'))+'\n'); _rehash(root); assert validate_persisted_rollback_bundle(root).status=='host_local_diagnostic_rollback_bundle_invalid'

def _reseal(root:Path)->None:
    from sentientos.host_local_diagnostic_execution_source_runtime import digest_record
    bindings=json.loads((root/'record_bindings.json').read_text())
    names=set(bindings['record_digests'])
    bindings['record_digests']={name:_sha(json.loads((root/(name+'.json')).read_text())) for name in sorted(names)}
    bindings['digest']=digest_record(bindings); (root/'record_bindings.json').write_text(json.dumps(bindings,sort_keys=True,separators=(',',':'))+'\n')
    receipt=json.loads((root/'runtime_receipt.json').read_text())
    links={'runtime_result_digest':'runtime_result','challenge_digest':'confirmation_challenge','operator_confirmation_digest':'operator_confirmation','rollback_records_digest':'rollback_records','updated_lifecycle_digest':'updated_lifecycle_report','record_bindings_digest':'record_bindings'}
    for field,name in links.items(): receipt[field]=_sha(json.loads((root/(name+'.json')).read_text()))
    content=json.loads((root/'content_manifest.json').read_text()); content['files']=[{'relative_filename':n,'size_bytes':len((root/n).read_bytes()),'sha256':_raw_sha((root/n).read_bytes())} for n in sorted(x['relative_filename'] for x in content['files'])]; check=dict(content); check.pop('content_manifest_digest',None); content['content_manifest_digest']=_sha(check); (root/'content_manifest.json').write_text(json.dumps(content,sort_keys=True,separators=(',',':'))+'\n')
    receipt['content_manifest_digest']=content['content_manifest_digest']; receipt['digest']=digest_record(receipt); (root/'runtime_receipt.json').write_text(json.dumps(receipt,sort_keys=True,separators=(',',':'))+'\n')
    manifest=json.loads((root/'bundle_manifest.json').read_text()); manifest['files']=[{'relative_filename':n,'size_bytes':len((root/n).read_bytes()),'sha256':_raw_sha((root/n).read_bytes())} for n in sorted(x['relative_filename'] for x in manifest['files'])]; check=dict(manifest); check.pop('bundle_digest',None); manifest['bundle_digest']=_sha(check); (root/'bundle_manifest.json').write_text(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n')

def _completed(root:Path):
    f,e,digest,_=_execution(root); c,_,args=_args(root,f,e,digest); result=c.rollback_execution(**args); assert result.status=='host_local_diagnostic_rollback_completed'; return f,e,digest,result

def _reject_mutations(tmp_path:Path, mutations)->None:
    _,_,_,result=_completed(tmp_path/'base')
    for index,mutation in enumerate(mutations):
        root=tmp_path/f'tamper-{index}'; shutil.copytree(result.bundle_root,root); mutation(root); _reseal(root)
        assert validate_persisted_rollback_bundle(root).status=='host_local_diagnostic_rollback_bundle_invalid'

def _edit(root:Path,name:str,change)->None:
    path=root/(name+'.json'); value=json.loads(path.read_text()); change(value); path.write_text(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n')

def test_confirmation_challenge_binds_actual_execution_identity(tmp_path:Path)->None:
    f,e,digest,_=_execution(tmp_path); _,pre,_=_args(tmp_path,f,e,digest)
    assert pre.records['confirmation_challenge']['execution_id']==Path(e.bundle_root).name
    assert pre.records['confirmation_challenge']['execution_id']!=pre.records['confirmation_challenge']['correlation_id']

def test_deep_historical_validation_accepts_direct_and_reconciled_bundles(tmp_path:Path)->None:
    f,e,digest,direct=_completed(tmp_path/'direct'); shutil.rmtree(e.bundle_root); shutil.rmtree(f.source_bundle); shutil.rmtree(f.target)
    assert validate_persisted_rollback_bundle(direct.bundle_root).status=='host_local_diagnostic_rollback_completed'
    f,e,digest,_=_execution(tmp_path/'reconciled'); calls=[]
    def rollback(*a,**kw): calls.append(1); return run_local_diagnostic_exact_rollback_wing(*a,**kw)
    c,_,args=_args(tmp_path/'reconciled',f,e,digest); c.rollback=rollback; c.failure_hook=lambda state: (_ for _ in ()).throw(RuntimeError('crash')) if state=='rollback_returned' else None
    with pytest.raises(RuntimeError): c.rollback_execution(**args)
    c.failure_hook=None; reconciled=c.rollback_execution(**args); shutil.rmtree(e.bundle_root); shutil.rmtree(f.source_bundle); shutil.rmtree(f.target)
    assert calls==[1] and reconciled.reconciled and validate_persisted_rollback_bundle(reconciled.bundle_root).status=='host_local_diagnostic_rollback_completed'

def test_embedded_execution_and_authority_tampering_is_rejected(tmp_path:Path)->None:
    _reject_mutations(tmp_path,[lambda r:_edit(r,'embedded_execution_records',lambda v:v['runtime_result'].__setitem__('rollback_performed',True)),lambda r:_edit(r,'embedded_execution_records',lambda v:v['target_snapshots'].pop('rollback_plan.json')),lambda r:_edit(r,'fresh_authority_validation',lambda v:v.__setitem__('grant_id','substitute')),lambda r:_edit(r,'fresh_current_verification',lambda v:v.__setitem__('checked_scope_labels',[]))])

def test_confirmation_and_intent_tampering_is_rejected(tmp_path:Path)->None:
    _reject_mutations(tmp_path,[lambda r:_edit(r,'confirmation_challenge',lambda v:v.__setitem__('historical_artifact_path',v['historical_artifact_path']+'-other')),lambda r:_edit(r,'operator_confirmation',lambda v:v.__setitem__('exact_rollback_scope','broader')),lambda r:_edit(r,'rollback_intent_history',lambda v:v[0]['identity'].__setitem__('artifact_digest','substitute')),lambda r:_edit(r,'rollback_intent_history',lambda v:v.pop())])

def test_rollback_records_and_lifecycle_tampering_is_rejected(tmp_path:Path)->None:
    _reject_mutations(tmp_path,[lambda r:_edit(r,'rollback_records',lambda v:v['result'].__setitem__('rollback_status','not_performed')),lambda r:_edit(r,'updated_transaction_ledger',lambda v:v.__setitem__('current_transaction_status','pending')),lambda r:_edit(r,'updated_lifecycle_report',lambda v:v.__setitem__('lifecycle_status','local_effect_lifecycle_rollback_pending'))])

def test_target_snapshots_and_sibling_custody_tampering_is_rejected(tmp_path:Path)->None:
    _reject_mutations(tmp_path,[lambda r:_edit(r,'pre_rollback_artifact_snapshot',lambda v:v.__setitem__('sha256','sha256:substitute')),lambda r:_edit(r,'post_rollback_snapshot',lambda v:v.__setitem__('exists',True)),lambda r:_edit(r,'unrelated_siblings_after',lambda v:v.pop(next(iter(v))))])

def test_runtime_receipt_and_exact_manifests_reject_recomputed_tampering(tmp_path:Path)->None:
    _reject_mutations(tmp_path,[lambda r:_edit(r,'runtime_result',lambda v:v.__setitem__('network_performed',True)),lambda r:_edit(r,'runtime_result',lambda v:v.__setitem__('rollback_call_count',7)),lambda r:_edit(r,'summary',lambda v:v.__setitem__('execution_id','substitute'))])

def test_latest_and_replay_pointer_substitution_is_rejected(tmp_path:Path)->None:
    from sentientos.host_local_diagnostic_rollback_runtime import validate_rollback_pointer
    _,_,_,result=_completed(tmp_path); output=Path(result.bundle_root).parent; pointer=json.loads((output/'latest.json').read_text())
    for field in ('execution_id','request_digest','correlation_id','bundle_digest'):
        changed=dict(pointer); changed[field]='substitute'; changed['digest']='substitute'
        assert validate_rollback_pointer(output,changed).status=='host_local_diagnostic_rollback_bundle_invalid'
