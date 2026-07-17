from __future__ import annotations
import json, threading
from dataclasses import replace
import pytest
from sentientos.control_plane_kernel import AdmissionOutcome, AuthorityClass, ControlActionDecision, ControlPlaneKernel, LifecyclePhase
from sentientos.host_live_grant_readiness_runtime import HostLiveGrantReadinessRuntimeCoordinator
from sentientos.host_local_authorization_runtime import *
from tests.test_host_live_grant_readiness_runtime import _controlled

pytestmark = pytest.mark.no_legacy_skip

def _ready(tmp_path):
    ev=_controlled(tmp_path)
    out=HostLiveGrantReadinessRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path).run_cycle(tick_id='tick-live-local', source_evaluation=ev, correlation_id='local')
    assert out and out.summary.status in {'ready_for_operator_policy_review', 'incomplete'}
    return out

def _chain(tmp_path):
    req=build_review_request(_ready(tmp_path), target_labels=['fan0'], not_before='2030-01-01T00:00:00+00:00', not_after='2030-01-02T00:00:00+00:00', expiry='2030-01-02T00:00:00+00:00')
    op=build_operator_decision(req, identity='operator-alice', role_or_policy_version='ops-v1', disposition='approve', reason_codes=['explicit'])
    pol=build_policy_decision(req, identity='policy-cooling-v1', role_or_policy_version='policy-v1', disposition='approve', reason_codes=['explicit'])
    plan=build_issue_plan(req, op, pol)
    return req,op,pol,plan

def test_deterministic_sealed_review_request_and_tampering(tmp_path):
    ev=_ready(tmp_path)
    a=build_review_request(ev,target_labels=['fan0'],not_before='2030-01-01T00:00:00+00:00',not_after='2030-01-02T00:00:00+00:00',expiry='2030-01-02T00:00:00+00:00')
    b=build_review_request(ev,target_labels=['fan0'],not_before=a.not_before,not_after=a.not_after,expiry=a.expiry,created_at='different')
    assert a.request_id == b.request_id and a.digest != ''
    assert validate_review_request(a).ok
    bad=replace(a, blocked_actions=a.blocked_actions+('new_action',))
    assert not validate_review_request(bad).ok
    assert a.operator_approval_granted is False and a.fulfillment_granted is False

def test_decisions_independent_identity_rejection_and_digest_changes(tmp_path):
    req,op,pol,_=_chain(tmp_path)
    assert validate_decision(op, req).ok and validate_decision(pol, req).ok
    assert not validate_decision(build_operator_decision(req, identity='sample_operator', role_or_policy_version='ops-v1', disposition='approve', reason_codes=['explicit']), req).ok
    assert op.digest != build_operator_decision(req, identity='operator-alice', role_or_policy_version='ops-v1', disposition='approve', reason_codes=['changed']).digest
    assert not validate_decision(replace(op, scope='other'), req).ok
    assert not validate_decision(op, req, now='2031-01-01T00:00:00+00:00').ok

def test_operator_or_policy_only_reject_defer_zero_plan(tmp_path):
    req,op,pol,_=_chain(tmp_path)
    with pytest.raises(ValueError): build_issue_plan(req, op, replace(pol, disposition='defer'))
    with pytest.raises(ValueError): build_issue_plan(req, replace(op, disposition='reject'), pol)

def test_admission_required_and_exact_success_idempotent_conflict(tmp_path):
    req,op,pol,plan=_chain(tmp_path)
    c=HostLocalAuthorizationRuntimeCoordinator(runtime_state_root=tmp_path, kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), clock=lambda:'2030-01-01T00:00:00+00:00')
    deny=ControlActionDecision(AdmissionOutcome.DENY, ('test',), LifecyclePhase.MAINTENANCE, LifecyclePhase.MAINTENANCE, AuthorityClass.LOCAL_AUTHORIZATION_GRANT_ISSUANCE, 'host_local_authorization_grant_issuance', 'test', 'host_local_authorization', {}, 'deny')
    with pytest.raises(PermissionError): c.issue(req,op,pol,plan,apply=True,admission=deny)
    assert not (tmp_path/'host_local_authorization_grant_custody'/'grant_record.json').exists()
    rec=c.issue(req,op,pol,plan,apply=True)
    assert rec.live_authorization_granted is True and rec.fulfillment_granted is False
    replay=c.issue(req,op,pol,plan,apply=True)
    assert replay.receipt_id == rec.receipt_id and replay.replayed is True
    with pytest.raises(ValueError): c.issue(req,op,pol,replace(plan, digest='different'),apply=True)

def test_wrong_admission_class_and_host_effect_are_not_substituted(tmp_path):
    req,op,pol,plan=_chain(tmp_path)
    decision=ControlActionDecision(AdmissionOutcome.ALLOW, ('test',), LifecyclePhase.MAINTENANCE, LifecyclePhase.MAINTENANCE, AuthorityClass.PRIVILEGED_OPERATOR_CONTROL, 'host_effect', 'test', 'host', {}, 'x')
    with pytest.raises(PermissionError): HostLocalAuthorizationRuntimeCoordinator(runtime_state_root=tmp_path).issue(req,op,pol,plan,apply=True,admission=decision)

def test_expiry_revocation_and_verification(tmp_path):
    req,op,pol,plan=_chain(tmp_path)
    c=HostLocalAuthorizationRuntimeCoordinator(runtime_state_root=tmp_path, kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), clock=lambda:'2030-01-01T00:00:00+00:00')
    c.issue(req,op,pol,plan,apply=True)
    grant=LocalAuthorizationGrant(**json.loads((tmp_path/'host_local_authorization_grant_custody'/'grant_record.json').read_text()))
    ledger=LocalAuthorizationGrantLedger(**json.loads((tmp_path/'host_local_authorization_grant_custody'/'ledger_snapshot.json').read_text())['ledger'])
    assert c.evaluate_expiry(grant, now='2029-01-01T00:00:00+00:00').expiry_status == 'local_authorization_expiry_not_expired'
    assert c.evaluate_expiry(grant, now='2031-01-01T00:00:00+00:00').expiry_status == 'local_authorization_expiry_expired'
    dec=build_revocation_decision(grant, ledger, identity='operator-alice', reason_codes=['reduce_authority'])
    rr=c.revoke(grant,dec,ledger,apply=True)
    assert rr.revocation_status == 'revoked' and rr.authorizes_fulfillment is False

def test_concurrent_duplicate_attempt_single_receipt(tmp_path):
    req,op,pol,plan=_chain(tmp_path); c=HostLocalAuthorizationRuntimeCoordinator(runtime_state_root=tmp_path, kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), clock=lambda:'2030-01-01T00:00:00+00:00')
    out=[]
    def run():
        try: out.append(c.issue(req,op,pol,plan,apply=True).receipt_id)
        except Exception as e: out.append(type(e).__name__)
    ts=[threading.Thread(target=run) for _ in range(2)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert len(set(x for x in out if x.startswith('hlair_'))) == 1

def test_world_state_dashboard_projection_no_effects(tmp_path):
    req,op,pol,plan=_chain(tmp_path)
    records=world_state_records(request=req, operator_decision=op, policy_decision=pol, plan=plan)
    proj=dashboard_projection(records)
    assert proj['pending_review_request_count'] == 1
    assert proj['decision_counts']['approve'] == 2
    assert proj['read_only'] is True and proj['fulfillment_granted'] is False
    assert all(r['payload']['host_mutation_performed'] is False for r in records)
