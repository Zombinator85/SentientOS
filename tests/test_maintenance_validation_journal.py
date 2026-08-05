import pytest
pytestmark = pytest.mark.no_legacy_skip
from pathlib import Path
from sentientos import maintenance_task_journal as j

def _ev(t,p,seq=1,prev=j.ZERO_DIGEST): return j.build_event(event_id=f'e{seq}',task_id='task',sequence=seq,event_type=t,previous_event_digest=prev,payload=p,recorded_at=f'2026-01-01T00:00:0{seq}+00:00')
def _base():
    e1=_ev('task_created',{'base_sha':'b','admitted_scope_digest':'s','maximum_attempts':3,'maximum_corrective_retries':1},1)
    e2=_ev('authority_lease_bound',{'lease_id':'l','lease_digest':'ld','scope_digest':'s'},2,e1.event_digest)
    e3=_ev('attempt_started',{'attempt_id':'a1','lease_id':'l','admitted_scope_digest':'s'},3,e2.event_digest)
    e4=_ev('implementation_completed',{'session_id':'s1','result_digest':'r'},4,e3.event_digest)
    return [e1,e2,e3,e4]
def test_validation_pass_requires_matching_started_cycle():
    ev=_base(); p={'validation_ref_id':'v1','attempt_id':'a1','plan_digest':'p','result_digest':'r'}
    bad=j.reduce_events(ev+[_ev('validation_passed',p,5,ev[-1].event_digest)])
    assert bad['reason_code']=='validation_cycle_not_active'
    s=_ev('validation_started',{'validation_ref_id':'v1','attempt_id':'a1','plan_digest':'p'},5,ev[-1].event_digest)
    ok=j.reduce_events(ev+[s,_ev('validation_passed',p,6,s.event_digest)])
    assert ok['validation_state']=='passed'
def test_validation_failure_before_start_is_rejected():
    snap=j.reduce_events(_base()+[_ev('validation_failed',{'validation_ref_id':'v1','attempt_id':'a1'},5,_base()[-1].event_digest)])
    assert snap['reason_code']=='validation_cycle_not_active'
def test_validation_cycle_history_is_preserved():
    ev=_base(); s=_ev('validation_started',{'validation_ref_id':'v1','attempt_id':'a1'},5,ev[-1].event_digest); f=_ev('validation_failed',{'validation_ref_id':'v1','attempt_id':'a1','result_digest':'r1'},6,s.event_digest); a2=_ev('attempt_started',{'attempt_id':'a2','lease_id':'l','admitted_scope_digest':'s','parent_validation_ref_id':'v1','corrective_retry_ordinal':1},7,f.event_digest); c2=_ev('implementation_completed',{'session_id':'s2','result_digest':'r2'},8,a2.event_digest); s2=_ev('validation_started',{'validation_ref_id':'v2','attempt_id':'a2'},9,c2.event_digest); p=_ev('validation_passed',{'validation_ref_id':'v2','attempt_id':'a2','result_digest':'r3'},10,s2.event_digest)
    snap=j.reduce_events(ev+[s,f,a2,c2,s2,p]); assert [c['status'] for c in snap['validation_cycles']]==['failed','passed']
def test_ready_to_commit_binds_latest_passing_cycle_and_implementation():
    ev=_base(); s=_ev('validation_started',{'validation_ref_id':'v1','attempt_id':'a1'},5,ev[-1].event_digest); p=_ev('validation_passed',{'validation_ref_id':'v1','attempt_id':'a1','result_digest':'r'},6,s.event_digest); r=_ev('ready_to_commit_recorded',{'validation_ref_id':'v1','attempt_id':'a1'},7,p.event_digest)
    assert j.reduce_events(ev+[s,p,r])['lifecycle_state']=='ready_to_commit'
def test_corrective_attempt_invalidates_prior_commit_readiness():
    ev=_base(); s=_ev('validation_started',{'validation_ref_id':'v1','attempt_id':'a1'},5,ev[-1].event_digest); f=_ev('validation_failed',{'validation_ref_id':'v1','attempt_id':'a1','result_digest':'r'},6,s.event_digest); a2=_ev('attempt_started',{'attempt_id':'a2','lease_id':'l','admitted_scope_digest':'s','parent_validation_ref_id':'v1','corrective_retry_ordinal':1},7,f.event_digest)
    snap=j.reduce_events(ev+[s,f,a2]); assert snap['commit_readiness'] is None and snap['active_attempt']['attempt_id']=='a2'
