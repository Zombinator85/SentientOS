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
