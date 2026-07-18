from __future__ import annotations
import pytest
pytestmark = pytest.mark.no_legacy_skip
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from sentientos.control_plane_kernel import AdmissionOutcome, AuthorityClass, ControlActionDecision, LifecyclePhase
from sentientos.host_local_authorization_runtime import HostLocalAuthorizationIssueReceipt
from sentientos.local_authorization_grant import build_operator_approval_evidence, build_policy_approval_evidence, build_local_authorization_grant, build_local_authorization_grant_expiry_evaluation, verify_local_authorization_grant, build_local_authorization_grant_ledger, build_local_authorization_grant_revocation_receipt
from sentientos.host_fulfillment_authorization_runtime import build_source_ref, build_request_envelope, HostFulfillmentAuthorizationRuntimeCoordinator, validate_request_envelope, world_state_records, dashboard_projection

NOW="2026-07-17T00:00:00+00:00"

def fixtures():
    op=build_operator_approval_evidence(operator_identity_label="operator_a", approval_scope_labels=("future_cooling_scope",), approval_time_bounds=("not_before:2026-07-17T00:00:00+00:00","not_after:2026-07-18T00:00:00+00:00"), approval_expiry_label="expires:2026-07-18T00:00:00+00:00")
    pol=build_policy_approval_evidence(policy_identity_label="policy_a", policy_scope_labels=("future_cooling_scope",), policy_time_bounds=("not_before:2026-07-17T00:00:00+00:00","not_after:2026-07-18T00:00:00+00:00"), policy_expiry_label="expires:2026-07-18T00:00:00+00:00")
    pre={"receipt_id":"preflight1","digest":"sha256:pre","preflight_status":"grant_issue_preflight_recorded","readiness_status":"live_grant_readiness_ready_for_operator_policy_review","readiness_domain":"future_cooling_live_grant_review","blocked_actions":()}
    mat={"matrix_id":"matrix1","digest":"sha256:mat","blocked_actions":()}
    grant=build_local_authorization_grant(pre,mat,op,pol,created_at=NOW)
    expiry=build_local_authorization_grant_expiry_evaluation(grant,evaluated_at=NOW)
    ver=verify_local_authorization_grant(grant,checked_scope_labels=("future_cooling_scope",),checked_time_label=NOW,expiry_evaluation=expiry)
    ledger=build_local_authorization_grant_ledger((grant,),(),(expiry,),created_at=NOW)
    issue0=HostLocalAuthorizationIssueReceipt("host_local_authorization_runtime.v1","issue1","","issued","review1","sha256:req","plan1","sha256:plan","kernel_decision:1","allow",grant.grant_id,grant.digest,ledger.ledger_id,ledger.digest,"idem_issue","attempt_issue",NOW,False,True)
    import sentientos.host_local_authorization_runtime as hlar
    issue=replace(issue0,digest=hlar._digest_record(issue0.to_dict()))
    src=build_source_ref(issue,grant,ver,ledger,expiry,())
    env=build_request_envelope(requesting_actor="operator_a",requesting_subsystem="operator_cli",reason_codes=("operator_requested_future_fulfillment",),source_ref=src,requested_fulfillment_domain="future_cooling_fulfillment_authorization",requested_backend_label="future_cooling_backend",requested_scope_labels=("future_cooling_scope",),requested_target_labels=(),requested_time=NOW,expected_not_before="2026-07-17T00:00:00+00:00",expected_not_after="2026-07-18T00:00:00+00:00")
    return issue,grant,ver,ledger,expiry,src,env

def allow():
    return ControlActionDecision(AdmissionOutcome.ALLOW,(),LifecyclePhase.MAINTENANCE,LifecyclePhase.MAINTENANCE,AuthorityClass.FULFILLMENT_AUTHORIZATION_CONSUMPTION,"host_fulfillment_authorization_consumption","operator","host_fulfillment_authorization_runtime",{},"corr")

def deny(outcome=AdmissionOutcome.DENY):
    return ControlActionDecision(outcome,("denied",),LifecyclePhase.MAINTENANCE,LifecyclePhase.MAINTENANCE,AuthorityClass.FULFILLMENT_AUTHORIZATION_CONSUMPTION,"host_fulfillment_authorization_consumption","operator","host_fulfillment_authorization_runtime",{},"corr")

def test_deterministic_request_and_successful_consumption(tmp_path: Path):
    issue,grant,ver,ledger,expiry,src,env=fixtures()
    assert validate_request_envelope(env).ok
    env2=build_request_envelope(requesting_actor="operator_a",requesting_subsystem="operator_cli",reason_codes=("operator_requested_future_fulfillment",),source_ref=src,requested_fulfillment_domain="future_cooling_fulfillment_authorization",requested_backend_label="future_cooling_backend",requested_scope_labels=("future_cooling_scope",),requested_target_labels=(),requested_time=NOW,expected_not_before="2026-07-17T00:00:00+00:00",expected_not_after="2026-07-18T00:00:00+00:00")
    assert env.digest == env2.digest
    coord=HostFulfillmentAuthorizationRuntimeCoordinator(tmp_path, clock=lambda: datetime(2026,7,17,tzinfo=timezone.utc))
    ev,rec=coord.evaluate(env,src,issue,grant,ver,ledger,expiry,(),apply=True,admission=allow())
    assert rec.authorization_consumed_for_future_fulfillment is True
    assert ev.fulfillment_granted is False and ev.effect_performed is False
    ev2,rec2=coord.evaluate(env,src,issue,grant,ver,ledger,expiry,(),apply=True,admission=allow())
    assert rec2.status == "replayed"
    led=coord._load_ledger()
    assert len(led.entries) == 1

def test_denied_admission_zero_successful_consumption(tmp_path: Path):
    issue,grant,ver,ledger,expiry,src,env=fixtures()
    coord=HostFulfillmentAuthorizationRuntimeCoordinator(tmp_path, clock=lambda: datetime(2026,7,17,tzinfo=timezone.utc))
    ev,rec=coord.evaluate(env,src,issue,grant,ver,ledger,expiry,(),apply=True,admission=deny())
    assert rec.authorization_consumed_for_future_fulfillment is False
    assert ev.consumption_receipt is None
    assert not (tmp_path/"host_fulfillment_authorization"/"ledger.json").exists()

def test_out_of_scope_expired_revoked_and_tampering(tmp_path: Path):
    issue,grant,ver,ledger,expiry,src,env=fixtures()
    bad=replace(env, requested_scope_labels=("future_power_scope",), digest="")
    bad=replace(bad, digest=env.digest)  # stale digest proves nested semantic tampering fails closed
    coord=HostFulfillmentAuthorizationRuntimeCoordinator(tmp_path, clock=lambda: datetime(2026,7,17,tzinfo=timezone.utc))
    ev,_=coord.evaluate(bad,src,issue,grant,ver,ledger,expiry,(),apply=True,admission=allow())
    assert "digest_mismatch" in ev.findings and "out_of_scope_request" in ev.findings
    exp=build_local_authorization_grant_expiry_evaluation(grant,evaluated_at="2026-07-19T00:00:00+00:00")
    ev2,_=coord.evaluate(env,src,issue,grant,ver,ledger,exp,(),apply=True,admission=allow())
    assert "expiry_mismatch" in ev2.findings or "expired_grant" in ev2.findings
    rev=build_local_authorization_grant_revocation_receipt(grant)
    ev3,_=coord.evaluate(env,src,issue,grant,ver,ledger,expiry,(rev,),apply=True,admission=allow())
    assert "revoked_grant" in ev3.findings

def test_backend_label_and_world_state_dashboard(tmp_path: Path):
    issue,grant,ver,ledger,expiry,src,env=fixtures()
    unsafe=replace(env, requested_backend_label="pkg.module.Class", digest="sha256:stale")
    assert not validate_request_envelope(unsafe).ok
    coord=HostFulfillmentAuthorizationRuntimeCoordinator(tmp_path, clock=lambda: datetime(2026,7,17,tzinfo=timezone.utc))
    ev,rec=coord.evaluate(env,src,issue,grant,ver,ledger,expiry,(),apply=True,admission=allow())
    records=world_state_records(env, ev, rec, observed_at=NOW)
    proj=dashboard_projection(records)
    assert proj["read_only"] is True
    assert proj["fulfillment_granted"] is False
    assert proj["effect_performed"] is False
    assert proj["consumption_recorded_count"] >= 1

class CountingKernel:
    def __init__(self):
        self.calls = 0
    def admit(self, request):
        self.calls += 1
        return allow()

def _env_for(src, when: str, *, not_after: str = "2026-07-18T00:00:00+00:00"):
    return build_request_envelope(requesting_actor="operator_a",requesting_subsystem="operator_cli",reason_codes=("operator_requested_future_fulfillment",),source_ref=src,requested_fulfillment_domain="future_cooling_fulfillment_authorization",requested_backend_label="future_cooling_backend",requested_scope_labels=("future_cooling_scope",),requested_target_labels=(),requested_time=when,expected_not_before="2026-07-17T00:00:00+00:00",expected_not_after=not_after)

def test_stale_expiry_valid_digest_blocks_admission_receipt_and_append(tmp_path: Path):
    issue,grant,ver,ledger,expiry,src,_=fixtures()
    env=_env_for(src,"2026-07-17T12:00:00+00:00")
    kernel=CountingKernel()
    coord=HostFulfillmentAuthorizationRuntimeCoordinator(tmp_path, kernel=kernel, clock=lambda: datetime(2026,7,17,12,tzinfo=timezone.utc))
    ev,rec=coord.evaluate(env,src,issue,grant,ver,ledger,expiry,(),apply=True)
    assert "stale_expiry_evidence" in ev.findings
    assert kernel.calls == 0
    assert ev.consumption_receipt is None
    assert rec.authorization_consumed_for_future_fulfillment is False
    assert not (tmp_path/"host_fulfillment_authorization"/"ledger.json").exists()

def test_requested_and_current_time_after_expiry_are_denied_without_append(tmp_path: Path):
    issue,grant,ver,ledger,expiry,src,_=fixtures()
    env=_env_for(src,"2026-07-18T00:01:00+00:00")
    kernel=CountingKernel()
    coord=HostFulfillmentAuthorizationRuntimeCoordinator(tmp_path, kernel=kernel, clock=lambda: datetime(2026,7,18,0,1,tzinfo=timezone.utc))
    ev,rec=coord.evaluate(env,src,issue,grant,ver,ledger,expiry,(),apply=True)
    assert "expired_grant" in ev.findings
    assert "stale_expiry_evidence" in ev.findings
    assert kernel.calls == 0
    assert rec.authorization_consumed_for_future_fulfillment is False
    assert not (tmp_path/"host_fulfillment_authorization"/"ledger.json").exists()

def test_expiry_for_different_grant_and_future_evaluation_time_fail(tmp_path: Path):
    issue,grant,ver,ledger,expiry,src,_=fixtures()
    other=replace(grant, grant_id="local-auth-grant-other", digest="")
    import sentientos.local_authorization_grant as lag
    other=replace(other, digest=lag.local_authorization_grant_digest(other))
    wrong_expiry=build_local_authorization_grant_expiry_evaluation(other,evaluated_at=NOW)
    env=_env_for(build_source_ref(issue,grant,ver,ledger,wrong_expiry,()),NOW)
    coord=HostFulfillmentAuthorizationRuntimeCoordinator(tmp_path, clock=lambda: datetime(2026,7,17,tzinfo=timezone.utc))
    ev,_=coord.evaluate(env,build_source_ref(issue,grant,ver,ledger,wrong_expiry,()),issue,grant,ver,ledger,wrong_expiry,(),apply=True,admission=allow())
    assert "expiry_mismatch" in ev.findings
    future_expiry=build_local_authorization_grant_expiry_evaluation(grant,evaluated_at="2026-07-17T01:00:00+00:00")
    env2=_env_for(build_source_ref(issue,grant,ver,ledger,future_expiry,()),NOW)
    ev2,_=coord.evaluate(env2,build_source_ref(issue,grant,ver,ledger,future_expiry,()),issue,grant,ver,ledger,future_expiry,(),apply=True,admission=allow())
    assert "expiry_evaluation_after_requested_time_unsupported" in ev2.findings

def test_current_exact_non_expired_expiry_can_succeed(tmp_path: Path):
    issue,grant,ver,ledger,_,_,_=fixtures()
    expiry=build_local_authorization_grant_expiry_evaluation(grant,evaluated_at="2026-07-17T12:00:00+00:00")
    ver=verify_local_authorization_grant(grant,checked_scope_labels=("future_cooling_scope",),checked_time_label="2026-07-17T12:00:00+00:00",expiry_evaluation=expiry)
    ledger=build_local_authorization_grant_ledger((grant,),(),(expiry,),created_at="2026-07-17T12:00:00+00:00")
    import sentientos.host_local_authorization_runtime as hlar
    issue=replace(issue, ledger_id=ledger.ledger_id, ledger_digest=ledger.digest, digest="")
    issue=replace(issue,digest=hlar._digest_record(issue.to_dict()))
    src=build_source_ref(issue,grant,ver,ledger,expiry,())
    env=_env_for(src,"2026-07-17T12:00:00+00:00")
    coord=HostFulfillmentAuthorizationRuntimeCoordinator(tmp_path, clock=lambda: datetime(2026,7,17,12,tzinfo=timezone.utc))
    ev,rec=coord.evaluate(env,src,issue,grant,ver,ledger,expiry,(),apply=True,admission=allow())
    assert ev.findings == ()
    assert rec.authorization_consumed_for_future_fulfillment is True

def test_forged_source_refs_never_admit_or_append(tmp_path: Path):
    issue,grant,ver,ledger,expiry,src,env=fixtures()
    forged=replace(src, grant_digest="sha256:forged", digest=src.digest)
    kernel=CountingKernel()
    coord=HostFulfillmentAuthorizationRuntimeCoordinator(tmp_path, kernel=kernel, clock=lambda: datetime(2026,7,17,tzinfo=timezone.utc))
    ev,rec=coord.evaluate(env,forged,issue,grant,ver,ledger,expiry,(),apply=True)
    assert "source_ref_mismatch" in ev.findings
    assert "source_ref_grant_mismatch" in ev.findings
    assert kernel.calls == 0
    assert ev.consumption_receipt is None
    assert rec.authorization_consumed_for_future_fulfillment is False
    assert not (tmp_path/"host_fulfillment_authorization"/"ledger.json").exists()

def test_source_ref_predecessor_expiry_digest_and_nested_source_tampering_fail(tmp_path: Path):
    issue,grant,ver,ledger,expiry,src,env=fixtures()
    coord=HostFulfillmentAuthorizationRuntimeCoordinator(tmp_path, clock=lambda: datetime(2026,7,17,tzinfo=timezone.utc))
    forged_pred=replace(src, ledger_predecessor_digest="sha256:forged", digest=src.digest)
    ev,_=coord.evaluate(env,forged_pred,issue,grant,ver,ledger,expiry,(),apply=True,admission=allow())
    assert "source_ref_mismatch" in ev.findings
    forged_exp=replace(src, expiry_evaluation_digest="sha256:forged", digest=src.digest)
    ev2,_=coord.evaluate(env,forged_exp,issue,grant,ver,ledger,expiry,(),apply=True,admission=allow())
    assert "source_ref_expiry_mismatch" in ev2.findings
    tampered_grant=replace(grant, blocked_actions=("fan_pwm_write",), digest=grant.digest)
    ev3,_=coord.evaluate(env,src,issue,tampered_grant,ver,ledger,expiry,(),apply=True,admission=allow())
    assert "source_ref_mismatch" in ev3.findings or "grant_digest_mismatch" in ev3.findings
