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

def _write_record(root:Path,name:str,value)->None:
    (root/(name+'.json')).write_text(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n')

def _reseal(root:Path)->None:
    """Regenerate every attacker-computable inner and enclosing custody field."""
    import hashlib
    from sentientos.host_local_diagnostic_execution_source_runtime import digest_record
    from sentientos.local_authorization_grant import local_authorization_grant_verification_digest
    from sentientos.local_diagnostic_effect import local_diagnostic_effect_digest
    from sentientos.local_effect_transaction_ledger import local_effect_transaction_digest

    verification=json.loads((root/'fresh_current_verification.json').read_text())
    verification['digest']=local_authorization_grant_verification_digest(verification); _write_record(root,'fresh_current_verification',verification)
    authority=json.loads((root/'fresh_authority_validation.json').read_text())
    authority['verification_digest']=verification['digest']
    authority_without_id={k:v for k,v in authority.items() if k not in ('authority_validation_id','digest')}
    authority['authority_validation_id']='hlder-authority-'+hashlib.sha256(json.dumps(authority_without_id,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:24]
    authority['digest']=digest_record(authority); _write_record(root,'fresh_authority_validation',authority)
    challenge=json.loads((root/'confirmation_challenge.json').read_text())
    challenge['fresh_verification_digest']=verification['digest']; challenge['grant_digest']=authority['grant_digest']
    challenge_without_id={k:v for k,v in challenge.items() if k not in ('confirmation_challenge_id','confirmation_challenge_digest')}
    challenge['confirmation_challenge_id']='hldrr-challenge-'+hashlib.sha256(json.dumps(challenge_without_id,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:24]
    challenge.pop('confirmation_challenge_digest',None); challenge['confirmation_challenge_digest']=digest_record(challenge); _write_record(root,'confirmation_challenge',challenge)
    confirmation=json.loads((root/'operator_confirmation.json').read_text())
    confirmation['confirmed_challenge_digest']=challenge['confirmation_challenge_digest']
    confirmation_without_id={k:v for k,v in confirmation.items() if k not in ('operator_confirmation_id','digest')}
    confirmation['operator_confirmation_id']='hldrr-confirmation-'+hashlib.sha256(json.dumps(confirmation_without_id,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:24]
    confirmation['digest']=digest_record(confirmation); _write_record(root,'operator_confirmation',confirmation)
    history=json.loads((root/'rollback_intent_history.json').read_text()); previous=''
    for state in history:
        identity=state['identity']; identity['confirmation_digest']=challenge['confirmation_challenge_digest']; identity['verification_digest']=challenge['fresh_verification_digest']; identity['artifact_path']=challenge['historical_artifact_path']; identity['artifact_digest']=challenge['historical_artifact_digest']; identity['rollback_plan_digest']=challenge['rollback_plan_digest']
        state['previous_state_digest']=previous; state['digest']=digest_record(state); previous=state['digest']
    _write_record(root,'rollback_intent_history',history)
    rollback=json.loads((root/'rollback_records.json').read_text())
    if rollback['result'].get('rollback_status')!='local_diagnostic_exact_rollback_performed':
        rollback['result']['digest']=local_diagnostic_effect_digest(rollback['result'])
    _write_record(root,'rollback_records',rollback)
    ledger_id=''
    for name,id_field,prefix in (('updated_transaction_ledger','ledger_id','local-effect-transaction-ledger-'),('updated_lifecycle_report','report_id','local-effect-lifecycle-report-')):
        record=json.loads((root/(name+'.json')).read_text()); payload=dict(record); payload['digest']=''; payload[id_field]=''
        if name=='updated_lifecycle_report': record['ledger_id']=ledger_id; payload['ledger_id']=ledger_id
        record[id_field]=prefix+hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:16]
        record['digest']=local_effect_transaction_digest(record); _write_record(root,name,record)
        if name=='updated_transaction_ledger': ledger_id=record['ledger_id']
    runtime=json.loads((root/'runtime_result.json').read_text()); runtime['digest']=digest_record(runtime); _write_record(root,'runtime_result',runtime)
    summary=json.loads((root/'summary.json').read_text()); summary['digest']=digest_record(summary); _write_record(root,'summary',summary)
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

def _assert_inner_integrity(root:Path)->None:
    """Assert hash consistency without invoking the production bundle validator."""
    from sentientos.host_local_diagnostic_execution_source_runtime import digest_record
    from sentientos.local_authorization_grant import local_authorization_grant_verification_digest
    verification=json.loads((root/'fresh_current_verification.json').read_text()); assert verification['digest']==local_authorization_grant_verification_digest(verification)
    for name in ('fresh_authority_validation','operator_confirmation','runtime_result','summary','record_bindings'):
        value=json.loads((root/(name+'.json')).read_text()); assert value['digest']==digest_record(value)
    challenge=json.loads((root/'confirmation_challenge.json').read_text()); challenge_payload=dict(challenge); claimed=challenge_payload.pop('confirmation_challenge_digest'); assert claimed==digest_record(challenge_payload)
    history=json.loads((root/'rollback_intent_history.json').read_text()); previous=''
    for state in history: assert state['previous_state_digest']==previous and state['digest']==digest_record(state); previous=state['digest']
    bindings=json.loads((root/'record_bindings.json').read_text())
    assert all(digest==_sha(json.loads((root/(name+'.json')).read_text())) for name,digest in bindings['record_digests'].items())
    content=json.loads((root/'content_manifest.json').read_text()); check=dict(content); assert check.pop('content_manifest_digest')==_sha(check)
    for entry in content['files']: raw=(root/entry['relative_filename']).read_bytes(); assert (entry['size_bytes'],entry['sha256'])==(len(raw),_raw_sha(raw))
    receipt=json.loads((root/'runtime_receipt.json').read_text()); assert receipt['digest']==digest_record(receipt) and receipt['content_manifest_digest']==content['content_manifest_digest']
    manifest=json.loads((root/'bundle_manifest.json').read_text()); check=dict(manifest); assert check.pop('bundle_digest')==_sha(check)
    for entry in manifest['files']: raw=(root/entry['relative_filename']).read_bytes(); assert (entry['size_bytes'],entry['sha256'])==(len(raw),_raw_sha(raw))

def _completed(root:Path):
    f,e,digest,_=_execution(root); c,_,args=_args(root,f,e,digest); result=c.rollback_execution(**args); assert result.status=='host_local_diagnostic_rollback_completed'; return f,e,digest,result

def _reject_mutations(tmp_path:Path, mutations)->None:
    _,_,_,result=_completed(tmp_path/'base')
    for index,mutation in enumerate(mutations):
        root=tmp_path/f'tamper-{index}'; shutil.copytree(result.bundle_root,root); mutation(root); _reseal(root); _assert_inner_integrity(root)
        assert validate_persisted_rollback_bundle(root).status=='host_local_diagnostic_rollback_bundle_invalid'

def _edit(root:Path,name:str,change)->None:
    path=root/(name+'.json'); value=json.loads(path.read_text()); change(value); path.write_text(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n')

def test_confirmation_challenge_binds_actual_execution_identity(tmp_path:Path)->None:
    f,e,digest,_=_execution(tmp_path); _,pre,_=_args(tmp_path,f,e,digest)
    assert pre.records['confirmation_challenge']['execution_id']==Path(e.bundle_root).name
    assert pre.records['confirmation_challenge']['execution_id']!=pre.records['confirmation_challenge']['correlation_id']

def test_inner_reseal_helper_preserves_valid_direct_and_reconciled_bundles(tmp_path:Path)->None:
    f,e,digest,direct=_completed(tmp_path/'direct'); shutil.rmtree(e.bundle_root); shutil.rmtree(f.source_bundle); shutil.rmtree(f.target)
    _reseal(Path(direct.bundle_root)); _assert_inner_integrity(Path(direct.bundle_root)); assert validate_persisted_rollback_bundle(direct.bundle_root).status=='host_local_diagnostic_rollback_completed'
    f,e,digest,_=_execution(tmp_path/'reconciled'); calls=[]
    def rollback(*a,**kw): calls.append(1); return run_local_diagnostic_exact_rollback_wing(*a,**kw)
    c,_,args=_args(tmp_path/'reconciled',f,e,digest); c.rollback=rollback; c.failure_hook=lambda state: (_ for _ in ()).throw(RuntimeError('crash')) if state=='rollback_returned' else None
    with pytest.raises(RuntimeError): c.rollback_execution(**args)
    c.failure_hook=None; reconciled=c.rollback_execution(**args); shutil.rmtree(e.bundle_root); shutil.rmtree(f.source_bundle); shutil.rmtree(f.target)
    _reseal(Path(reconciled.bundle_root)); _assert_inner_integrity(Path(reconciled.bundle_root)); assert calls==[1] and reconciled.reconciled and validate_persisted_rollback_bundle(reconciled.bundle_root).status=='host_local_diagnostic_rollback_completed'

def test_inner_resealed_authority_and_challenge_contradictions_are_rejected(tmp_path:Path)->None:
    _reject_mutations(tmp_path,[lambda r:_edit(r,'fresh_current_verification',lambda v:v.__setitem__('checked_scope_labels',[])),lambda r:_edit(r,'confirmation_challenge',lambda v:v.__setitem__('historical_artifact_path',v['historical_artifact_path']+'-other')),lambda r:_edit(r,'confirmation_challenge',lambda v:v.__setitem__('rollback_plan_digest','sha256:'+'1'*64))])

def test_inner_resealed_confirmation_and_intent_contradictions_are_rejected(tmp_path:Path)->None:
    def rewrite_intent(root:Path)->None: _edit(root,'rollback_intent_history',lambda states:[state['identity'].__setitem__('execution_bundle_digest','sha256:'+'2'*64) for state in states])
    _reject_mutations(tmp_path,[lambda r:_edit(r,'operator_confirmation',lambda v:v.__setitem__('confirmed_artifact_path',v['confirmed_artifact_path']+'-other')),rewrite_intent])

def test_inner_resealed_rollback_and_lifecycle_contradictions_are_rejected(tmp_path:Path)->None:
    _reject_mutations(tmp_path,[lambda r:_edit(r,'rollback_records',lambda v:v['result'].__setitem__('rollback_status','not_performed')),lambda r:_edit(r,'updated_transaction_ledger',lambda v:v.__setitem__('current_transaction_status','pending')),lambda r:_edit(r,'updated_lifecycle_report',lambda v:v.__setitem__('lifecycle_status','local_effect_lifecycle_rollback_pending'))])

def test_inner_resealed_snapshot_receipt_and_summary_contradictions_are_rejected(tmp_path:Path)->None:
    _reject_mutations(tmp_path,[lambda r:_edit(r,'pre_rollback_artifact_snapshot',lambda v:v.__setitem__('sha256','sha256:'+'3'*64)),lambda r:_edit(r,'unrelated_siblings_after',lambda v:v.__setitem__('injected.txt',{'exists':True})),lambda r:_edit(r,'runtime_result',lambda v:v.__setitem__('rollback_call_count',7)),lambda r:_edit(r,'summary',lambda v:v.__setitem__('execution_id','substitute'))])

def test_validly_redigested_latest_and_replay_pointer_substitution_is_rejected(tmp_path:Path)->None:
    from sentientos.host_local_diagnostic_rollback_runtime import validate_rollback_pointer
    from sentientos.host_local_diagnostic_execution_source_runtime import digest_record
    _,_,_,result=_completed(tmp_path); output=Path(result.bundle_root).parent; pointer=json.loads((output/'latest.json').read_text())
    for field in ('execution_id','request_digest','correlation_id','execution_bundle_digest','bundle_digest'):
        changed=dict(pointer); changed[field]='substitute'; changed['digest']=digest_record(changed); assert changed['digest']==digest_record(changed)
        assert validate_rollback_pointer(output,changed).status=='host_local_diagnostic_rollback_bundle_invalid'
