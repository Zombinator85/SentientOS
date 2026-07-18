from __future__ import annotations
from dataclasses import replace
from datetime import datetime, timezone
import threading

import pytest

pytestmark = pytest.mark.no_legacy_skip
from sentientos.control_plane_kernel import AdmissionOutcome, AuthorityClass, ControlActionDecision, LifecyclePhase
from sentientos.host_fulfillment_authorization_runtime import HostFulfillmentAuthorizationRuntimeCoordinator, build_request_envelope, recompute_source, world_state_records, dashboard_projection
from sentientos.local_authorization_grant import build_local_authorization_grant_expiry_evaluation, verify_local_authorization_grant, build_local_authorization_grant_ledger, LocalAuthorizationGrant, local_authorization_grant_digest, build_local_authorization_grant_revocation_receipt

class Kernel:
    def __init__(self, outcome=AdmissionOutcome.ALLOW): self.outcome=outcome; self.calls=0
    def admit(self, req):
        self.calls += 1
        return ControlActionDecision(self.outcome, ('test',), LifecyclePhase.MAINTENANCE, LifecyclePhase.MAINTENANCE, req.authority_class, req.action_kind, req.actor, req.target_subsystem, {}, req.metadata['correlation_id'])

def grant(expiry='2030-01-01T00:00:00+00:00'):
    g0=LocalAuthorizationGrant('g1','pre','sha256:pre','matrix','op','sha256:op','pol','sha256:pol','future_cooling_local_authorization','future_cooling_scope','local_authorization_grant_active',('future_cooling_scope',),('not_before:2029-01-01T00:00:00+00:00','not_after:2030-01-01T00:00:00+00:00'),'expires:'+expiry,('revocable',),('gate',),('host_mutation','fan_pwm_write'),(),('local_authorization_is_not_fulfillment',),'2029-01-01T00:00:00+00:00','')
    return replace(g0, digest=local_authorization_grant_digest(g0))

def chain(expiry='2030-01-01T00:00:00+00:00', eval_at='2029-01-01T00:00:00+00:00'):
    g=grant(expiry); exp=build_local_authorization_grant_expiry_evaluation(g,evaluated_at=eval_at); ver=verify_local_authorization_grant(g, checked_scope_labels=('future_cooling_scope',), checked_time_label='2029-01-02T00:00:00+00:00', expiry_evaluation=exp); led=build_local_authorization_grant_ledger((g,),(),(exp,),created_at=eval_at); issue={'receipt_id':'issue1','digest':'sha256:issue','grant_id':g.grant_id,'grant_digest':g.digest}; src=recompute_source(issue_receipt=issue,grant=g,verification=ver,authorization_ledger=led,ledger_predecessor_digest='sha256:empty',expiry_evaluation=exp); env=build_request_envelope(src, requested_time='2029-01-02T00:00:00+00:00')
    return issue,g,ver,led,exp,src,env

def consume(tmp_path, **kw):
    if 'bundle' in kw:
        issue,g,ver,led,exp,src,env=kw['bundle']
    else:
        issue,g,ver,led,exp,src,env=chain(**{k:v for k,v in kw.items() if k in {'expiry','eval_at'}})
    c=HostFulfillmentAuthorizationRuntimeCoordinator(runtime_state_root=tmp_path,kernel=kw.get('kernel') or Kernel(),clock=lambda:kw.get('now','2029-01-02T00:00:00+00:00'))
    return c.consume(issue_receipt=issue,grant=kw.get('grant',g),verification=kw.get('verification',ver),authorization_ledger=kw.get('ledger',led),ledger_predecessor_digest=kw.get('pred','sha256:empty'),expiry_evaluation=kw.get('expiry_eval',exp),revocation_receipts=kw.get('revocations',()),envelope=kw.get('envelope',env),supplied_source=kw.get('supplied_source',src.to_dict()))

def test_canonical_fresh_success_and_world_state_dashboard(tmp_path):
    r=consume(tmp_path)
    assert r.status=='recorded' and r.consumption_receipt and r.ledger_append_count==1 and r.admission_call_count==1
    assert r.consumption_receipt['fulfillment_granted'] is False and r.consumption_receipt['effect_performed'] is False
    records=world_state_records(r)
    projection=dashboard_projection(records)
    assert projection['dedicated_metadata_consumption_admission_required'] is True
    assert projection['backend_invoked'] is False and projection['execution_triggered'] is False

def test_stale_valid_digest_expiry_evidence_zero_calls(tmp_path):
    r=consume(tmp_path, now='2031-01-01T00:00:00+00:00')
    assert 'stale_non_expired_expiry_evidence' in r.findings and r.admission_call_count==0 and r.ledger_append_count==0 and r.ledger is None

def test_request_after_expiry_and_current_clock_after_expiry(tmp_path):
    issue,g,ver,led,exp,src,env=chain(expiry='2029-01-03T00:00:00+00:00')
    env=build_request_envelope(src, requested_time='2029-01-04T00:00:00+00:00')
    r=consume(tmp_path, now='2029-01-04T00:00:00+00:00', envelope=env, bundle=(issue,g,ver,led,exp,src,env))
    assert {'request_after_expiry','current_clock_after_expiry'} <= set(r.findings)

def test_expiry_for_other_grant_and_forged_expiry_digest(tmp_path):
    issue,g,ver,led,exp,src,env=chain(); bad=replace(exp, grant_id='other')
    r=consume(tmp_path, expiry_eval=bad)
    assert 'expiry_evaluation_wrong_grant' in r.findings and 'expiry_digest_mismatch' in r.findings

def test_unsupported_future_eval_backdating_and_future_window(tmp_path):
    issue,g,ver,led,exp,src,env=chain(eval_at='2030-01-01T00:00:00+00:00')
    r=consume(tmp_path, now='2029-01-01T00:00:00+00:00', bundle=(issue,g,ver,led,exp,src,env))
    assert 'unsupported_future_expiry_evaluation' in r.findings
    oldenv=build_request_envelope(src, requested_time='2028-01-01T00:00:00+00:00')
    assert 'unsupported_backdating' in consume(tmp_path/'b', envelope=oldenv, bundle=(issue,g,ver,led,exp,src,oldenv)).findings
    future=build_request_envelope(src, requested_time='2029-02-03T00:00:00+00:00')
    assert 'future_request_outside_window' in consume(tmp_path/'c', envelope=future, bundle=(issue,g,ver,led,exp,src,future)).findings

def test_forged_source_grant_ledger_predecessor_and_nested_tamper(tmp_path):
    issue,g,ver,led,exp,src,env=chain(); forged=replace(env, source_ref_digest='sha256:bad')
    assert 'envelope_source_ref_mismatch' in consume(tmp_path, envelope=forged, bundle=(issue,g,ver,led,exp,src,forged)).findings
    badg=replace(g, grant_scope='tampered')
    assert 'grant_digest_mismatch' in consume(tmp_path/'g', grant=badg).findings
    assert 'forged_ledger_predecessor' in consume(tmp_path/'p', pred='sha256:notledger').findings
    supplied=src.to_dict(); supplied['grant_digest']='sha256:bad'
    assert 'supplied_source_mismatch' in consume(tmp_path/'s', supplied_source=supplied).findings

def test_scope_target_backend_and_admission_denials_zero_writes(tmp_path):
    issue,g,ver,led,exp,src,env=chain()
    scope_env=build_request_envelope(src, requested_scope_labels=('future_power_scope',), requested_time=env.requested_time)
    assert 'scope_expansion' in consume(tmp_path/'scope', envelope=scope_env, bundle=(issue,g,ver,led,exp,src,scope_env)).findings
    target_env=build_request_envelope(src, target_labels=('pump',), requested_time=env.requested_time)
    assert 'target_expansion' in consume(tmp_path/'target', envelope=target_env, bundle=(issue,g,ver,led,exp,src,target_env)).findings
    backend_env=build_request_envelope(src, requested_backend_class='real_backend', requested_time=env.requested_time)
    assert 'backend_label_rejected' in consume(tmp_path/'backend', envelope=backend_env, bundle=(issue,g,ver,led,exp,src,backend_env)).findings
    for outcome in (AdmissionOutcome.DENY, AdmissionOutcome.DEFER, AdmissionOutcome.QUARANTINE):
        r=consume(tmp_path/outcome.value, kernel=Kernel(outcome))
        assert r.status=='denied' and r.ledger_append_count==0

def test_exact_replay_idempotency_conflict_and_concurrent_duplicate(tmp_path):
    r1=consume(tmp_path); r2=consume(tmp_path)
    assert r2.replayed is True and r2.ledger_append_count==0
    issue,g,ver,led,exp,src,env=chain(); env2=build_request_envelope(src, requested_time='2029-01-03T00:00:00+00:00', idempotency_key=env.idempotency_key)
    assert 'idempotency_conflict' in consume(tmp_path, envelope=env2, bundle=(issue,g,ver,led,exp,src,env2)).findings
    results=[]
    def run(): results.append(consume(tmp_path/'conc').replayed)
    ts=[threading.Thread(target=run) for _ in range(4)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert results.count(False)==1 and results.count(True)==3

def test_historical_receipt_survives_later_revocation_future_denied(tmp_path):
    r=consume(tmp_path); assert r.status=='recorded'
    issue,g,ver,led,exp,src,env=chain(); rev=build_local_authorization_grant_revocation_receipt(g, created_at='2029-01-03T00:00:00+00:00')
    r2=consume(tmp_path/'revoked', revocations=(rev,))
    assert 'grant_revoked' in r2.findings and r2.ledger_append_count==0

