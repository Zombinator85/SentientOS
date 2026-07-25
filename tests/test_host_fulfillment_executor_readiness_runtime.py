from __future__ import annotations
from dataclasses import replace
import json, threading

import pytest
from sentientos.control_plane_kernel import AdmissionOutcome
from sentientos.host_fulfillment_executor_readiness_runtime import HostFulfillmentExecutorReadinessRuntimeCoordinator, build_request, dashboard_projection, validate_consumption_source, validate_persisted_readiness_bundle, world_state_records
from sentientos.fulfillment_authorization import fulfillment_authorization_consumption_receipt_digest
from sentientos.host_fulfillment_authorization_runtime import _digest_record as hfac_digest_record
from tests.test_host_fulfillment_authorization_runtime import Kernel, consume, chain

pytestmark = pytest.mark.no_legacy_skip

def reroute_result(result, domain):
    receipt={**result.consumption_receipt,"requested_fulfillment_domain":domain,"digest":""}
    receipt["digest"]=fulfillment_authorization_consumption_receipt_digest(receipt)
    entry={**result.ledger_entry,"consumption_receipt":receipt,"digest":""}; entry["digest"]=hfac_digest_record(entry)
    ledger={**result.ledger,"entries":[entry],"digest":""}; ledger["digest"]=hfac_digest_record(ledger)
    return replace(result,consumption_receipt=receipt,ledger_entry=entry,ledger=ledger)

def test_diagnostics_route_and_mismatched_overrides_fail_before_calls(tmp_path):
    issue,g,ver,led,exp,src,env=chain(); original=consume(tmp_path/'hfac', bundle=(issue,g,ver,led,exp,src,env))
    diagnostics=reroute_result(original,"diagnostics_fulfillment_authorization")
    c=HostFulfillmentExecutorReadinessRuntimeCoordinator(runtime_state_root=tmp_path/'state',kernel=Kernel(),clock=lambda:'2029-01-02T00:00:00+00:00')
    ev=c.evaluate(diagnostics,output_root=tmp_path/'diagnostics',grant=g,verification=ver,authorization_ledger=led,expiry_evaluation=exp)
    assert (ev.request.requested_fulfillment_domain,ev.request.executor_domain,ev.request.backend_class)==("diagnostics_fulfillment_authorization","diagnostics_executor_contract","diagnostic_backend_future")
    wrong=HostFulfillmentExecutorReadinessRuntimeCoordinator(runtime_state_root=tmp_path/'wrong-state',kernel=Kernel(),clock=lambda:'2029-01-02T00:00:00+00:00')
    blocked=wrong.evaluate(original,output_root=tmp_path/'wrong',grant=g,verification=ver,authorization_ledger=led,expiry_evaluation=exp,executor_domain="future_power_executor_contract",backend_class="power_backend_future")
    assert "noncanonical_executor_domain_override" in blocked.findings
    assert blocked.admission_call_count==0 and blocked.builder_call_count==0 and not blocked.persisted and not (tmp_path/'wrong').exists()
    unknown=reroute_result(original,"unknown_fulfillment_authorization")
    denied=wrong.evaluate(unknown,output_root=tmp_path/'unknown',grant=g,verification=ver,authorization_ledger=led,expiry_evaluation=exp)
    assert "unknown_requested_fulfillment_domain" in denied.findings
    assert denied.admission_call_count==0 and denied.builder_call_count==0 and not (tmp_path/'unknown').exists()

def test_exact_typed_consumption_builds_review_package_without_authority(tmp_path):
    issue,g,ver,led,exp,src,env=chain(); result=consume(tmp_path/'hfac', bundle=(issue,g,ver,led,exp,src,env))
    c=HostFulfillmentExecutorReadinessRuntimeCoordinator(runtime_state_root=tmp_path/'state', kernel=Kernel(), clock=lambda:'2029-01-02T00:00:00+00:00')
    ev=c.evaluate(result, output_root=tmp_path/'external', grant=g, verification=ver, authorization_ledger=led, expiry_evaluation=exp)
    assert ev.status in {'ready_for_executor_contract_review','ready_for_executor_contract_review_with_conditions'}
    assert ev.builder_call_count==6 and ev.admission_call_count==1 and ev.persisted is True
    assert ev.contract['source_consumption_receipt_digest']==result.consumption_receipt['digest']
    assert ev.backend_declaration['contract_digest']==ev.contract['digest']
    assert ev.precondition_manifest['contract_digest']==ev.contract['digest']
    assert ev.precondition_manifest['source_consumption_receipt_digest']==result.consumption_receipt['digest']
    assert ev.dry_run_plan['contract_digest']==ev.contract['digest']
    assert ev.admission_packet['contract_digest']==ev.contract['digest']
    assert ev.admission_packet['backend_declaration_digest']==ev.backend_declaration['digest']
    assert ev.admission_packet['precondition_manifest_digest']==ev.precondition_manifest['digest']
    assert ev.admission_packet['dry_run_plan_digest']==ev.dry_run_plan['digest']
    assert ev.readiness_receipt['admission_packet_digest']==ev.admission_packet['digest']
    for key,val in ev.runtime_receipt.no_authority.items(): assert val is False
    assert ev.backend_declaration['backend_loaded'] is False
    assert ev.dry_run_plan['dry_run_executed'] is False
    assert ev.admission_packet['control_plane_admission_granted'] is False
    assert ev.readiness_receipt['executor_implemented'] is False
    assert any(p.status=='missing' for p in ev.prerequisite_records)

def test_loose_or_denied_or_tampered_sources_fail_strict(tmp_path):
    issue,g,ver,led,exp,src,env=chain(); result=consume(tmp_path/'hfac', bundle=(issue,g,ver,led,exp,src,env))
    assert validate_consumption_source(result).ok
    denied=replace(result, status='denied')
    assert 'denial_only_result_rejected' in validate_consumption_source(denied).findings
    no_receipt=replace(result, consumption_receipt=None)
    assert 'missing_successful_consumption_receipt' in validate_consumption_source(no_receipt).findings
    bad=replace(result, consumption_receipt={**result.consumption_receipt,'digest':'sha256:bad'})
    assert 'consumption_receipt_digest_unverified' in validate_consumption_source(bad).findings
    entry={**result.ledger_entry,'consumption_receipt':{**result.consumption_receipt,'digest':'sha256:bad'}}
    assert 'ledger_entry_receipt_mismatch' in validate_consumption_source(replace(result, ledger_entry=entry)).findings
    ledger={**result.ledger,'entries':[]}
    assert 'ledger_missing_exact_entry' in validate_consumption_source(replace(result, ledger=ledger)).findings

def test_metadata_admission_non_allow_zero_builder_calls(tmp_path):
    issue,g,ver,led,exp,src,env=chain(); result=consume(tmp_path/'hfac', bundle=(issue,g,ver,led,exp,src,env))
    for outcome in (AdmissionOutcome.DENY, AdmissionOutcome.DEFER, AdmissionOutcome.QUARANTINE):
        k=Kernel(outcome); c=HostFulfillmentExecutorReadinessRuntimeCoordinator(runtime_state_root=tmp_path/outcome.value, kernel=k, clock=lambda:'2029-01-02T00:00:00+00:00')
        ev=c.evaluate(result, output_root=tmp_path/(outcome.value+'-out'), grant=g, verification=ver, authorization_ledger=led, expiry_evaluation=exp)
        assert ev.status=='blocked_contract_package'
        assert ev.builder_call_count==0 and c.builder_call_count==0
        assert 'metadata_admission_not_allowed' in ev.findings

def test_current_grant_posture_blocks_without_rewriting_consumption(tmp_path):
    issue,g,ver,led,exp,src,env=chain(); result=consume(tmp_path/'hfac', bundle=(issue,g,ver,led,exp,src,env))
    for posture in ('expired','revoked','stale','contradicted','unavailable'):
        ev=HostFulfillmentExecutorReadinessRuntimeCoordinator(runtime_state_root=tmp_path/posture, kernel=Kernel(), clock=lambda:'2029-01-02T00:00:00+00:00').evaluate(result, output_root=tmp_path/(posture+'-out'), grant=g, verification=ver, authorization_ledger=led, expiry_evaluation=exp, current_grant_posture=posture)
        assert ev.status in {'blocked_contract_package','contradicted_contract_package','stale_contract_package'} and ev.builder_call_count==0
        assert result.consumption_receipt is not None

def test_backend_label_safety_and_timestamp_semantics(tmp_path):
    issue,g,ver,led,exp,src,env=chain(); result=consume(tmp_path/'hfac', bundle=(issue,g,ver,led,exp,src,env))
    c=HostFulfillmentExecutorReadinessRuntimeCoordinator(runtime_state_root=tmp_path/'state', kernel=Kernel())
    assert 'backend_label_rejected' in c.evaluate(result, output_root=tmp_path/'out', grant=g, verification=ver, authorization_ledger=led, expiry_evaluation=exp, backend_label='../evil').findings
    r1=build_request(result, created_at='2029-01-01T00:00:00+00:00')
    r2=build_request(result, created_at='2030-01-01T00:00:00+00:00')
    assert r1.request_id==r2.request_id and r1.digest==r2.digest

def test_world_state_and_dashboard_projection_are_review_only(tmp_path):
    issue,g,ver,led,exp,src,env=chain(); result=consume(tmp_path/'hfac', bundle=(issue,g,ver,led,exp,src,env))
    ev=HostFulfillmentExecutorReadinessRuntimeCoordinator(runtime_state_root=tmp_path/'state', kernel=Kernel()).evaluate(result, output_root=tmp_path/'external', grant=g, verification=ver, authorization_ledger=led, expiry_evaluation=exp)
    records=world_state_records(ev)
    assert records and {r['stage'] for r in records} <= {'proposal','review','admission'}
    proj=dashboard_projection(records)
    assert proj['read_only'] is True and proj['execution_ready'] is False and proj['backend_invoked'] is False and proj['effect_performed'] is False
    assert proj['contract_package_count'] >= 1

def test_repository_local_root_rejected_and_no_git_or_host_mutation(tmp_path):
    issue,g,ver,led,exp,src,env=chain(); result=consume(tmp_path/'hfac', bundle=(issue,g,ver,led,exp,src,env))
    ev=HostFulfillmentExecutorReadinessRuntimeCoordinator(runtime_state_root=tmp_path/'state', kernel=Kernel(), clock=lambda:'2029-01-02T00:00:00+00:00').evaluate(result, output_root='runtime_artifacts', grant=g, verification=ver, authorization_ledger=led, expiry_evaluation=exp)
    assert 'repository_local_runtime_root_rejected' in ev.findings

def test_exact_current_evidence_adversarial_blocks_zero_calls(tmp_path):
    from dataclasses import replace
    from sentientos.local_authorization_grant import build_local_authorization_grant_revocation_receipt, build_local_authorization_grant_ledger, local_authorization_grant_digest, build_local_authorization_grant_expiry_evaluation
    issue,g,ver,led,exp,src,env=chain(); result=consume(tmp_path/'hfac', bundle=(issue,g,ver,led,exp,src,env))
    c=HostFulfillmentExecutorReadinessRuntimeCoordinator(runtime_state_root=tmp_path/'s', kernel=Kernel(), clock=lambda:'2031-01-01T00:00:00+00:00')
    expired=c.evaluate(result, output_root=tmp_path/'out1', grant=g, verification=ver, authorization_ledger=led, expiry_evaluation=exp, current_grant_posture='currently_active')
    assert 'current_grant_posture_expectation_mismatch' in expired.findings and expired.builder_call_count==0 and expired.admission_call_count==0
    rev=build_local_authorization_grant_revocation_receipt(g, created_at='2029-01-03T00:00:00+00:00')
    revoked=c.evaluate(result, output_root=tmp_path/'out2', grant=g, verification=ver, authorization_ledger=led, expiry_evaluation=exp, revocation_receipts=(rev,), current_grant_posture='currently_active')
    assert 'grant_revoked' in revoked.findings and revoked.builder_call_count==0 and revoked.admission_call_count==0
    badg=replace(g, digest='sha256:forged')
    forged=c.evaluate(result, output_root=tmp_path/'out3', grant=badg, verification=ver, authorization_ledger=led, expiry_evaluation=exp)
    assert 'forged_grant_digest' in forged.findings and forged.builder_call_count==0 and forged.admission_call_count==0
    other=replace(exp, grant_id='other')
    assert 'expiry_evaluation_for_another_grant' in c.evaluate(result, output_root=tmp_path/'out4', grant=g, verification=ver, authorization_ledger=led, expiry_evaluation=other).findings
    empty_led=build_local_authorization_grant_ledger((), (), (), created_at='2029-01-01T00:00:00+00:00')
    assert 'ledger_missing_exact_grant' in c.evaluate(result, output_root=tmp_path/'out5', grant=g, verification=ver, authorization_ledger=empty_led, expiry_evaluation=exp).findings
    g2=replace(g, grant_scope='future_power_scope'); g2=replace(g2, digest=local_authorization_grant_digest(g2))
    dup_led=build_local_authorization_grant_ledger((g,g2),(),(exp,),created_at='2029-01-01T00:00:00+00:00')
    assert 'duplicate_grant_id_different_bytes' in c.evaluate(result, output_root=tmp_path/'out6', grant=g, verification=ver, authorization_ledger=dup_led, expiry_evaluation=exp).findings

def test_replay_conflict_concurrency_and_prerequisite_evidence(tmp_path):
    from sentientos.local_authorization_grant import build_local_authorization_grant_expiry_evaluation
    issue,g,ver,led,exp,src,env=chain(); result=consume(tmp_path/'hfac', bundle=(issue,g,ver,led,exp,src,env))
    c=HostFulfillmentExecutorReadinessRuntimeCoordinator(runtime_state_root=tmp_path/'s', kernel=Kernel(), clock=lambda:'2029-01-02T00:00:00+00:00')
    out=tmp_path/'external'
    ev1=c.evaluate(result, output_root=out, grant=g, verification=ver, authorization_ledger=led, expiry_evaluation=exp)
    before=c.builder_call_count
    ev2=c.evaluate(result, output_root=out, grant=g, verification=ver, authorization_ledger=led, expiry_evaluation=exp)
    assert ev2.replayed is True and ev2.builder_call_count==0 and c.builder_call_count==before
    by={p.label:p for p in ev1.prerequisite_records}
    assert by['fulfillment_authorization_consumption_required'].evidence_digest==result.consumption_receipt['digest']
    assert by['local_authorization_grant_required'].evidence_digest==g.digest
    assert by['grant_not_expired_required'].evidence_digest==exp.digest and 'validation_time=' in by['grant_not_expired_required'].finding
    assert by['grant_not_revoked_required'].evidence_digest==ev1.request.current_grant_evidence_digest
    conflict=c.evaluate(result, output_root=out, grant=g, verification=ver, authorization_ledger=led, expiry_evaluation=exp, backend_label='different-safe-label')
    assert conflict.status=='contradicted_contract_package' and 'semantic_replay_conflict' in conflict.findings
    (out/ev1.request.request_id/'runtime_receipt.json').write_text('{"digest":"sha256:corrupt"}', encoding='utf-8')
    corrupt=c.evaluate(result, output_root=out, grant=g, verification=ver, authorization_ledger=led, expiry_evaluation=exp)
    assert corrupt.status=='contradicted_contract_package'

def _snapshot_for(grant, ledger, issue_source, *, created_at='2029-01-02T00:00:00+00:00', host_revocations=()):
    from sentientos.host_local_authorization_runtime import HostLocalAuthorizationIssueReceipt, HostLocalAuthorizationLedgerSnapshot, _digest_record
    from sentientos.host_fulfillment_executor_readiness_runtime import _id
    issue0=HostLocalAuthorizationIssueReceipt('host_local_authorization_runtime.v1','hlair_test','', 'issued','req','sha256:req','plan','sha256:plan','adm','allow',grant.grant_id,grant.digest,ledger.ledger_id,ledger.digest,'idem','attempt',created_at)
    issue=replace(issue0,digest=_digest_record(issue0.to_dict()))
    snap0=HostLocalAuthorizationLedgerSnapshot('host_local_authorization_runtime.v1',_id('hlas_test_', {'ledger':ledger.digest,'host_revocations':[getattr(r,'digest',None) for r in host_revocations]}),'',ledger,(issue,),tuple(host_revocations),ledger.active_grant_count,ledger.expired_grant_count,ledger.revoked_grant_count,0,created_at)
    return replace(snap0,digest=_digest_record(snap0.to_dict()))

def test_current_snapshot_allows_later_current_digests_and_blocks_revocation_omission(tmp_path):
    from sentientos.local_authorization_grant import build_local_authorization_grant_ledger, build_local_authorization_grant_expiry_evaluation, verify_local_authorization_grant, build_local_authorization_grant_revocation_receipt
    from sentientos.host_local_authorization_runtime import HostLocalAuthorizationRevocationReceipt, _digest_record
    issue,g,ver,led,exp,src,env=chain(); result=consume(tmp_path/'hfac', bundle=(issue,g,ver,led,exp,src,env))
    later_exp=build_local_authorization_grant_expiry_evaluation(g, evaluated_at='2029-01-02T00:00:00+00:00')
    later_ver=verify_local_authorization_grant(g, checked_scope_labels=g.granted_scope_labels, checked_time_label='2029-01-02T00:00:00+00:00', expiry_evaluation=later_exp)
    later_led=build_local_authorization_grant_ledger((g,), (), (later_exp,), created_at='2029-01-02T00:00:00+00:00')
    snap=_snapshot_for(g,later_led,src)
    ev=HostFulfillmentExecutorReadinessRuntimeCoordinator(runtime_state_root=tmp_path/'s', kernel=Kernel(), clock=lambda:'2029-01-02T00:00:00+00:00').evaluate(result, output_root=tmp_path/'external', grant=g, verification=later_ver, current_snapshot=snap, expiry_evaluation=later_exp)
    assert ev.status in {'ready_for_executor_contract_review','ready_for_executor_contract_review_with_conditions'}
    assert ev.request.current_grant_evidence_digest
    by={p.label:p for p in ev.prerequisite_records}
    assert by['grant_not_revoked_required'].evidence_digest != ev.request.current_grant_evidence_digest
    rev=build_local_authorization_grant_revocation_receipt(g, created_at='2029-01-03T00:00:00+00:00')
    revoked_led=build_local_authorization_grant_ledger((g,), (rev,), (later_exp,), created_at='2029-01-03T00:00:00+00:00')
    host0=HostLocalAuthorizationRevocationReceipt('host_local_authorization_runtime.v1','hlarr_test','', 'revoked','decision','sha256:decision',g.grant_id,g.digest,revoked_led.ledger_id,revoked_led.digest,rev.receipt_id,rev.digest,'2029-01-03T00:00:00+00:00')
    host=replace(host0,digest=_digest_record(host0.to_dict()))
    revoked_snap=_snapshot_for(g,revoked_led,src,created_at='2029-01-03T00:00:00+00:00',host_revocations=(host,))
    blocked=HostFulfillmentExecutorReadinessRuntimeCoordinator(runtime_state_root=tmp_path/'s2', kernel=Kernel(), clock=lambda:'2029-01-03T00:00:00+00:00').evaluate(result, output_root=tmp_path/'revoked', grant=g, verification=later_ver, current_snapshot=revoked_snap, expiry_evaluation=later_exp, revocation_receipts=())
    assert blocked.status=='blocked_contract_package'
    assert 'caller_revocation_omission_ignored' in blocked.findings
    assert blocked.admission_call_count==0 and blocked.builder_call_count==0

def test_replay_bundle_manifest_deep_corruption_blocks(tmp_path):
    issue,g,ver,led,exp,src,env=chain(); result=consume(tmp_path/'hfac', bundle=(issue,g,ver,led,exp,src,env))
    c=HostFulfillmentExecutorReadinessRuntimeCoordinator(runtime_state_root=tmp_path/'s', kernel=Kernel(), clock=lambda:'2029-01-02T00:00:00+00:00')
    out=tmp_path/'external'; ev=c.evaluate(result, output_root=out, grant=g, verification=ver, authorization_ledger=led, expiry_evaluation=exp)
    assert ev.persisted is True
    (out/ev.request.request_id/'backend_declaration.json').write_text('{"corrupt": true}', encoding='utf-8')
    replay=c.evaluate(result, output_root=out, grant=g, verification=ver, authorization_ledger=led, expiry_evaluation=exp)
    assert replay.status=='contradicted_contract_package'
    assert 'semantic_replay_conflict' in replay.findings

def test_public_persisted_bundle_validator_loads_disk_records_and_rejects_custody_tampering(tmp_path):
    issue,g,ver,led,exp,src,env=chain(); result=consume(tmp_path/'hfac', bundle=(issue,g,ver,led,exp,src,env))
    coordinator=HostFulfillmentExecutorReadinessRuntimeCoordinator(runtime_state_root=tmp_path/'state', kernel=Kernel(), clock=lambda:'2029-01-02T00:00:00+00:00')
    evaluation=coordinator.evaluate(result, output_root=tmp_path/'external', grant=g, verification=ver, authorization_ledger=led, expiry_evaluation=exp)
    bundle=tmp_path/'external'/evaluation.request.request_id
    validation=validate_persisted_readiness_bundle(bundle)
    assert validation.ok and validation.evaluation is not None and validation.current_grant_evidence is not None
    assert validation.evaluation.request == evaluation.request
    assert validation.request_digest == evaluation.request.digest and validation.bundle_digest
    (bundle/'unmanifested.json').write_text('{}', encoding='utf-8')
    assert 'unexpected_unmanifested_artifact:unmanifested.json' in validate_persisted_readiness_bundle(bundle).findings

def test_public_persisted_bundle_validator_rejects_symlinks(tmp_path):
    issue,g,ver,led,exp,src,env=chain(); result=consume(tmp_path/'hfac', bundle=(issue,g,ver,led,exp,src,env))
    evaluation=HostFulfillmentExecutorReadinessRuntimeCoordinator(runtime_state_root=tmp_path/'state', kernel=Kernel(), clock=lambda:'2029-01-02T00:00:00+00:00').evaluate(result, output_root=tmp_path/'external', grant=g, verification=ver, authorization_ledger=led, expiry_evaluation=exp)
    bundle=tmp_path/'external'/evaluation.request.request_id
    linked=tmp_path/'linked'; linked.symlink_to(bundle, target_is_directory=True)
    assert validate_persisted_readiness_bundle(linked).findings == ('symlink_bundle_root_rejected',)
    target=bundle/'README.md'; saved=target.read_text(); target.unlink(); external=tmp_path/'outside.md'; external.write_text(saved); target.symlink_to(external)
    assert any(x.startswith('symlink_manifested_artifact_rejected:README.md') for x in validate_persisted_readiness_bundle(bundle).findings)
