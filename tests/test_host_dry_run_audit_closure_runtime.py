from __future__ import annotations
import json, threading
from dataclasses import replace
from pathlib import Path
import pytest
from sentientos.host_dry_run_audit_closure_runtime import HostDryRunAuditClosureRuntimeCoordinator, dashboard_projection, validate_evaluation, world_state_records
from sentientos.dry_run_audit_closure import dry_run_effect_verification_digest, validate_dry_run_audit_closure_chain
from tests.test_host_dry_run_execution_runtime import readiness, Kernel
from sentientos.host_dry_run_execution_runtime import HostDryRunExecutionRuntimeCoordinator
pytestmark = pytest.mark.no_legacy_skip

def source_bundle(tmp_path: Path) -> Path:
    src=readiness(tmp_path)
    ev=HostDryRunExecutionRuntimeCoordinator(runtime_state_root=tmp_path/'hdr-state', kernel=Kernel(), clock=lambda:'2029-01-02T00:00:00+00:00').evaluate(src, output_root=tmp_path/'hdr-external')
    assert ev.status == 'dry_run_runtime_simulated'
    return tmp_path/'hdr-external'/ev.request.request_id

def test_exact_persisted_source_closes_and_persists(tmp_path):
    bundle=source_bundle(tmp_path); c=HostDryRunAuditClosureRuntimeCoordinator(runtime_state_root=tmp_path/'state', clock=lambda:'2029-01-02T00:00:00+00:00')
    ev=c.evaluate(dry_run_runtime_bundle_root=bundle, output_root=tmp_path/'external')
    assert ev.status == 'host_dry_run_audit_closure_runtime_closed'
    assert ev.persisted is True and validate_evaluation(ev).ok
    assert ev.effect_verification['metadata_only'] is True and ev.runtime_receipt.simulation_only is True
    assert ev.audit_closure_receipt['production_audit_receipt_created'] is False
    assert ev.runtime_receipt.dry_run_executed is True
    assert (tmp_path/'external'/ev.request.request_id/'final_bundle_manifest.json').exists()

def test_standalone_loose_and_tampered_sources_rejected(tmp_path):
    bundle=source_bundle(tmp_path); c=HostDryRunAuditClosureRuntimeCoordinator()
    assert c.evaluate(dry_run_runtime_bundle_root=bundle/'dry_run_receipt.json', output_root=tmp_path/'out').status.startswith('blocked')
    (bundle/'dry_run_receipt.json').write_text('{"tampered": true}', encoding='utf-8')
    ev=c.evaluate(dry_run_runtime_bundle_root=bundle, output_root=tmp_path/'out2')
    assert ev.status.startswith('blocked')
    assert any('source_artifact_custody_mismatch' in f for f in ev.findings)

def test_blocked_incomplete_false_dry_run_and_real_effect_claims_rejected(tmp_path):
    bundle=source_bundle(tmp_path)
    receipt=json.loads((bundle/'dry_run_receipt.json').read_text())
    receipt['dry_run_executed']=False
    (bundle/'dry_run_receipt.json').write_text(json.dumps(receipt, sort_keys=True), encoding='utf-8')
    assert any('source_artifact_custody_mismatch' in f for f in HostDryRunAuditClosureRuntimeCoordinator().evaluate(dry_run_runtime_bundle_root=bundle, output_root=tmp_path/'out').findings)
    bundle=source_bundle(tmp_path/'b')
    receipt=json.loads((bundle/'dry_run_receipt.json').read_text()); receipt['host_mutation_performed']=True
    (bundle/'dry_run_receipt.json').write_text(json.dumps(receipt, sort_keys=True), encoding='utf-8')
    assert HostDryRunAuditClosureRuntimeCoordinator().evaluate(dry_run_runtime_bundle_root=bundle, output_root=tmp_path/'out2').status.startswith('blocked')

def test_parent_lineage_and_timestamp_independent_semantics(tmp_path):
    ev=HostDryRunAuditClosureRuntimeCoordinator(clock=lambda:'2029-01-02T00:00:00+00:00').evaluate(dry_run_runtime_bundle_root=source_bundle(tmp_path), output_root=tmp_path/'external')
    chain=validate_dry_run_audit_closure_chain(json.loads((Path(ev.request.source_bundle_root)/'dry_run_receipt.json').read_text()), ev.effect_verification, ev.postcondition_verification, ev.rollback_rehearsal, ev.audit_closure_receipt, ev.closure_bundle)
    assert chain.ok
    bad={**ev.effect_verification, 'source_dry_run_receipt_digest':'sha256:substitute'}
    assert not validate_dry_run_audit_closure_chain(json.loads((Path(ev.request.source_bundle_root)/'dry_run_receipt.json').read_text()), bad, ev.postcondition_verification, ev.rollback_rehearsal, ev.audit_closure_receipt, ev.closure_bundle).ok
    changed_time={**ev.effect_verification, 'created_at':'2099-01-01T00:00:00+00:00'}
    changed_parent={**ev.effect_verification, 'source_dry_run_receipt_id':'different'}
    assert dry_run_effect_verification_digest(changed_time) == ev.effect_verification['digest']
    assert dry_run_effect_verification_digest(changed_parent) != ev.effect_verification['digest']

def test_replay_corruption_conflict_and_concurrency(tmp_path):
    bundle=source_bundle(tmp_path); out=tmp_path/'external'; c=HostDryRunAuditClosureRuntimeCoordinator()
    ev1=c.evaluate(dry_run_runtime_bundle_root=bundle, output_root=out); before=c.builder_call_count
    ev2=c.evaluate(dry_run_runtime_bundle_root=bundle, output_root=out)
    assert ev2.replayed is True and c.builder_call_count == before
    assert c.evaluate(dry_run_runtime_bundle_root=bundle, output_root=out, correlation_id='different').status in {'host_dry_run_audit_closure_runtime_closed','blocked_host_dry_run_audit_closure_runtime'}
    (out/ev1.request.request_id/'dry_run_effect_verification.json').write_text('{"corrupt":true}', encoding='utf-8')
    assert c.evaluate(dry_run_runtime_bundle_root=bundle, output_root=out).status.startswith('blocked')
    out2=tmp_path/'concurrent'; results=[]
    def run(): results.append(HostDryRunAuditClosureRuntimeCoordinator().evaluate(dry_run_runtime_bundle_root=bundle, output_root=out2))
    ts=[threading.Thread(target=run) for _ in range(2)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert len([p for p in out2.iterdir() if p.is_dir()]) == 1 and sum(r.replayed for r in results) == 1

def test_world_state_dashboard_are_read_only_zero_calls_and_no_repo_root(tmp_path):
    c=HostDryRunAuditClosureRuntimeCoordinator(); ev=c.evaluate(dry_run_runtime_bundle_root=source_bundle(tmp_path), output_root=tmp_path/'external')
    before=c.builder_call_count; proj=dashboard_projection(world_state_records(ev))
    assert proj['metadata_only'] is True and proj['simulation_only'] is True and proj['host_mutation_performed'] is False and c.builder_call_count == before
    blocked=c.evaluate(dry_run_runtime_bundle_root=Path(ev.request.source_bundle_root), output_root='runtime_artifacts')
    assert 'repository_local_runtime_root_rejected' in blocked.findings
