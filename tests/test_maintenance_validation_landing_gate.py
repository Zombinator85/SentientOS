import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from sentientos import maintenance_commit_publication as landing
from sentientos import maintenance_validation_controller as validation
from tests.maintenance_commit_publication_fixtures import NOW, setup

pytestmark=pytest.mark.no_legacy_skip
MODES=['pull_request','fast_forward_base_ref',landing.LOCAL_FAST_FORWARD_MODE]


def object_inventory(repo):
    return {str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (repo/'.git/objects').rglob('*') if p.is_file()}


def contradict(s,v):
    ref=v['validation_ref_id']; command=next((s/'maintenance_validation_commands'/ref).glob('*.json'))
    data=json.loads(command.read_text()); data.update(exit_code=2,failure_class='diff_check_failure')
    data['result_digest']=validation.seal(data,'result_digest'); command.write_bytes(validation.cj(data)+b'\n')
    result=json.loads((s/'maintenance_validation_results'/(ref+'.json')).read_text())
    result['command_result_digests']=[data['result_digest']]
    result['required_stage_outcomes']=[{'stage_id':data['stage_id'],'exit_code':2,'failure_class':'diff_check_failure'}]
    result['result_digest']=validation.seal(result,'result_digest')
    (s/'maintenance_validation_results'/(ref+'.json')).write_bytes(validation.cj(result)+b'\n')
    return result


@pytest.mark.parametrize('mode',MODES)
@pytest.mark.parametrize('entry',['plan','commit','commit_retry','publication','publication_retry'])
def test_semantically_failed_custody_stops_every_real_landing_entry(tmp_path,monkeypatch,mode,entry):
    r,w,s,le,v,p=setup(tmp_path,mode)
    kw=dict(state_root=s,repository_root=r,worktree_root=w,lease=le,validation_result=v,landing_policy=p,evaluation_time=NOW)
    built=None
    if entry in {'commit_retry','publication','publication_retry'}:
        built=landing.create_commit_and_enqueue(**kw)
    if entry=='publication_retry':
        # Produce an actual failed publication attempt with valid custody first.
        # Only remote transport is stubbed; local absorption and its denial run.
        if mode==landing.LOCAL_FAST_FORWARD_MODE:
            subprocess.run(['git','branch','-m','main'],cwd=r,check=True)
            (r/'untracked').write_text('canonical checkout is not clean\n')
        original=landing._git
        def transport(git,root,args,**kwargs):
            if args[0]=='ls-remote':
                stdout=(le['base_sha']+'\trefs/heads/main\n').encode() if mode=='fast_forward_base_ref' else b''
                return subprocess.CompletedProcess(args,0,stdout,b'')
            if args[0]=='push': return subprocess.CompletedProcess(args,1,b'',b'fixture transport unavailable')
            return original(git,root,args,**kwargs)
        with monkeypatch.context() as m:
            m.setattr(landing,'_git',transport)
            earlier=landing.publish_one_maintenance_request(state_root=s,repository_root=r,lease=le,landing_policy=p,
                publication_id=built['publication_request']['publication_id'],evaluation_time=NOW)
        assert earlier['terminal_status']!='publication_succeeded'
        assert len(list((s/'maintenance_publication_attempts').glob('*.json')))==1
    forged=contradict(s,v); kw['validation_result']=forged
    before=object_inventory(r)
    artifacts={str(f):f.read_bytes() for name in ['maintenance_commit_results','maintenance_publication_requests'] for f in (s/name).glob('*')}
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=r)
    calls=[]
    def no_git(*args,**kwargs):
        calls.append(args)
        pytest.fail('Git called after contradictory validation was presented')
    monkeypatch.setattr(landing,'_git',no_git)
    monkeypatch.setattr(landing,'_publish_pr',lambda *a,**k:pytest.fail('PR transport invoked'))
    if entry.startswith('publication'):
        for _ in range(2 if entry=='publication_retry' else 1):
            result=landing.publish_one_maintenance_request(state_root=s,repository_root=r,lease=le,landing_policy=p,
                publication_id=built['publication_request']['publication_id'],evaluation_time=NOW)
            assert result['terminal_status']=='publication_integrity_failed'
            assert 'aggregate_semantic_contradiction' in result['reason_code']
    else:
        operation=landing.build_commit_plan if entry=='plan' else landing.create_commit_and_enqueue
        with pytest.raises(landing.MaintenanceLandingError,match='aggregate_semantic_contradiction'): operation(**kw)
    assert calls==[] and object_inventory(r)==before
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=r)==head
    assert artifacts=={str(f):f.read_bytes() for name in ['maintenance_commit_results','maintenance_publication_requests'] for f in (s/name).glob('*')}


def test_legitimate_real_validation_commits_and_enqueues_idempotently(tmp_path):
    r,w,s,le,v,p=setup(tmp_path)
    kw=dict(state_root=s,repository_root=r,worktree_root=w,lease=le,validation_result=v,landing_policy=p,evaluation_time=NOW)
    first=landing.create_commit_and_enqueue(**kw); second=landing.create_commit_and_enqueue(**kw)
    assert first['commit_result']['commit_sha']==second['commit_result']['commit_sha']
    assert first['publication_request']['publication_request_digest']==second['publication_request']['publication_request_digest']
    assert first['commit_result']['object_verification']['manifest_matches']


def test_queued_proof_does_not_require_a_retained_detached_worktree(tmp_path):
    r,w,s,le,v,p=setup(tmp_path,landing.LOCAL_FAST_FORWARD_MODE)
    subprocess.run(['git','branch','-m','main'],cwd=r,check=True)
    built=landing.create_commit_and_enqueue(state_root=s,repository_root=r,worktree_root=w,lease=le,validation_result=v,landing_policy=p,evaluation_time=NOW)
    subprocess.run(['git','worktree','remove','--force',str(w)],cwd=r,check=True)
    result=landing.publish_one_maintenance_request(state_root=s,repository_root=r,lease=le,landing_policy=p,
        publication_id=built['publication_request']['publication_id'],evaluation_time=NOW)
    assert result['terminal_status']=='publication_succeeded',result


def test_staged_tree_is_checked_before_commit_object_creation(tmp_path,monkeypatch):
    r,w,s,le,v,p=setup(tmp_path); original=landing._git; mutations=[]
    def race(git,root,args,**kwargs):
        if args[0]=='add': (w/'a.txt').write_text('changed during staging\n')
        if args[0]=='commit-tree': mutations.append(args)
        return original(git,root,args,**kwargs)
    monkeypatch.setattr(landing,'_git',race)
    with pytest.raises(landing.MaintenanceLandingError,match='staged_tree_bytes_or_mode_mismatch'):
        landing.create_commit_and_enqueue(state_root=s,repository_root=r,worktree_root=w,lease=le,validation_result=v,landing_policy=p,evaluation_time=NOW)
    assert mutations==[]
    assert not (s/'maintenance_commit_results').exists()


@pytest.mark.parametrize('directory',['maintenance_commit_results','maintenance_publication_requests'])
@pytest.mark.parametrize('side',['before','after'])
def test_landing_enqueue_interruption_rechecks_evidence_before_new_effects(tmp_path,monkeypatch,directory,side):
    from tests.test_maintenance_validation_acceptance import Interrupted
    r,w,s,le,v,p=setup(tmp_path)
    kw=dict(state_root=s,repository_root=r,worktree_root=w,lease=le,validation_result=v,landing_policy=p,evaluation_time=NOW)
    write=landing._write_immutable
    def stop(path,data):
        if directory in path.parts and side=='before': raise Interrupted()
        out=write(path,data)
        if directory in path.parts and side=='after': raise Interrupted()
        return out
    with monkeypatch.context() as m:
        m.setattr(landing,'_write_immutable',stop)
        with pytest.raises(Interrupted): landing.create_commit_and_enqueue(**kw)
    kw['validation_result']=contradict(s,v)
    objects=object_inventory(r)
    artifacts={str(f):f.read_bytes() for folder in ['maintenance_commit_results','maintenance_publication_requests'] for f in (s/folder).glob('*')}
    monkeypatch.setattr(landing,'_git',lambda *a,**k:pytest.fail('Git invoked in invalid enqueue recovery'))
    with pytest.raises(landing.MaintenanceLandingError,match='aggregate_semantic_contradiction'):
        landing.create_commit_and_enqueue(**kw)
    assert objects==object_inventory(r)
    assert artifacts=={str(f):f.read_bytes() for folder in ['maintenance_commit_results','maintenance_publication_requests'] for f in (s/folder).glob('*')}
