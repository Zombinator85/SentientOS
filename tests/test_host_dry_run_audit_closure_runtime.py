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

from sentientos.host_dry_run_audit_closure_runtime import validate_persisted_closure_bundle, digest_record as closure_digest_record, _sha as closure_sha
import hashlib, shutil

def _closure_file_digest(path: Path) -> str:
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()

def _rewrite_closure_manifests(bundle: Path, *, legacy: bool = False) -> None:
    schema='host_dry_run_audit_closure_runtime.v1' if legacy else 'host_dry_run_audit_closure_runtime.v2'
    for manifest_name, kind, key, skip in (
        ('content_manifest.json','host_dry_run_audit_closure_runtime_content_manifest','content_manifest_digest', {'runtime_receipt.json','content_manifest.json','final_bundle_manifest.json'}),
        ('final_bundle_manifest.json','host_dry_run_audit_closure_runtime_final_bundle_manifest','final_bundle_digest', {'final_bundle_manifest.json'}),
    ):
        files=[]
        for path in sorted(p for p in bundle.iterdir() if p.is_file() and p.name not in skip and not p.name.startswith('.')):
            files.append({'relative_filename': path.name, 'size': path.stat().st_size, 'digest': _closure_file_digest(path), 'artifact_kind': path.stem, 'schema_version': schema})
        data={'schema_version':schema,'artifact_kind':kind,'files':files,key:closure_sha({'files':files,'artifact_kind':kind})}
        (bundle/manifest_name).write_text(json.dumps(data, sort_keys=True, indent=2), encoding='utf-8')

def _rewrite_closure_runtime_receipt(bundle: Path) -> None:
    content=json.loads((bundle/'content_manifest.json').read_text())
    rr=json.loads((bundle/'runtime_receipt.json').read_text()); rr['content_manifest_digest']=content['content_manifest_digest']; rr['digest']=closure_digest_record(rr)
    (bundle/'runtime_receipt.json').write_text(json.dumps(rr, sort_keys=True, indent=2), encoding='utf-8')
    _rewrite_closure_manifests(bundle)

def _closure_bundle(tmp_path: Path) -> tuple[Path, Path, object]:
    src=source_bundle(tmp_path/'src')
    ev=HostDryRunAuditClosureRuntimeCoordinator().evaluate(dry_run_runtime_bundle_root=src, output_root=tmp_path/'out')
    assert ev.status == 'host_dry_run_audit_closure_runtime_closed'
    return src, tmp_path/'out'/ev.request.request_id, ev

def test_closure_v2_embeds_source_receipt_and_replays_after_source_deletion_or_mutation(tmp_path):
    src,bundle,ev=_closure_bundle(tmp_path)
    assert (bundle/'source_dry_run_receipt.json').exists()
    shutil.rmtree(src)
    v=validate_persisted_closure_bundle(bundle)
    assert v.ok and v.evaluation and v.evaluation.replayed is True
    assert HostDryRunAuditClosureRuntimeCoordinator().evaluate(dry_run_runtime_bundle_root=source_bundle(tmp_path/'newsrc'), output_root=tmp_path/'out', correlation_id=ev.request.correlation_id).status.startswith('blocked')

def test_closure_v1_missing_and_altered_embedded_receipt_rejected_with_recomputed_manifests(tmp_path):
    _src,bundle,_ev=_closure_bundle(tmp_path)
    _rewrite_closure_manifests(bundle, legacy=True)
    assert 'legacy_v1_closure_bundle_rejected' in validate_persisted_closure_bundle(bundle).findings
    _src,bundle,_ev=_closure_bundle(tmp_path/'b')
    (bundle/'source_dry_run_receipt.json').unlink(); _rewrite_closure_manifests(bundle)
    assert 'embedded_source_dry_run_receipt_required' in validate_persisted_closure_bundle(bundle).findings
    _src,bundle,_ev=_closure_bundle(tmp_path/'c')
    receipt=json.loads((bundle/'source_dry_run_receipt.json').read_text()); receipt['simulated_backend_class']='operator_manual_backend_simulated'; (bundle/'source_dry_run_receipt.json').write_text(json.dumps(receipt, sort_keys=True), encoding='utf-8')
    _rewrite_closure_manifests(bundle); _rewrite_closure_runtime_receipt(bundle)
    findings=validate_persisted_closure_bundle(bundle).findings
    assert any('source_receipt:' in f or 'chain:' in f or 'source_dry_run' in f for f in findings)

def test_closure_record_substitution_rejected_and_replay_zero_builder_calls(tmp_path):
    _src,bundle,ev=_closure_bundle(tmp_path)
    effect=json.loads((bundle/'dry_run_effect_verification.json').read_text()); effect['source_dry_run_receipt_id']='substituted'; (bundle/'dry_run_effect_verification.json').write_text(json.dumps(effect, sort_keys=True), encoding='utf-8')
    _rewrite_closure_manifests(bundle); _rewrite_closure_runtime_receipt(bundle)
    assert not validate_persisted_closure_bundle(bundle).ok
    src=source_bundle(tmp_path/'zsrc'); c=HostDryRunAuditClosureRuntimeCoordinator(); ev1=c.evaluate(dry_run_runtime_bundle_root=src, output_root=tmp_path/'zout'); before=c.builder_call_count; ev2=c.evaluate(dry_run_runtime_bundle_root=src, output_root=tmp_path/'zout')
    assert ev2.replayed is True and c.builder_call_count == before
