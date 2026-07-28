from __future__ import annotations
import json, shutil
from pathlib import Path
import pytest
from sentientos.host_local_diagnostic_lifecycle_closure import build_lifecycle_closure, validate_lifecycle_closure
from tests.test_host_local_diagnostic_rollback_runtime import _args, _execution

NOW="2026-07-28T12:00:00+00:00"
pytestmark=pytest.mark.no_legacy_skip

def _closed(root:Path):
    fixture,execution,execution_digest,execution_calls=_execution(root)
    coordinator,_,args=_args(root,fixture,execution,execution_digest); args["correlation_id"]=execution.records["runtime_request"]["correlation_id"]; rollback_calls=[]; original=coordinator.rollback
    def rollback(*a,**kw): rollback_calls.append(1); return original(*a,**kw)
    coordinator.rollback=rollback; result=coordinator.rollback_execution(**args)
    rollback_digest=json.loads((Path(result.bundle_root)/"bundle_manifest.json").read_text())["bundle_digest"]
    packet=build_lifecycle_closure(execution_bundle_root=execution.bundle_root,execution_bundle_digest=execution_digest,rollback_bundle_root=result.bundle_root,rollback_bundle_digest=rollback_digest,closure_time=NOW,output_root=root/"closure")
    return fixture,execution,result,packet,execution_calls,rollback_calls

def test_real_execution_and_rollback_build_self_contained_closure(tmp_path:Path)->None:
    _,_,_,packet,ecalls,rcalls=_closed(tmp_path)
    assert packet.status=="host_local_diagnostic_lifecycle_closure_valid" and ecalls==[1] and rcalls==[1]
    report=packet.records["closure_report"]
    assert report["historical_lifecycle"]=="local_effect_lifecycle_rollback_pending"
    assert report["final_lifecycle"]=="local_effect_lifecycle_complete_with_rollback"
    assert report["closure_processing_execution_call_count"]==report["closure_processing_rollback_call_count"]==0

def test_closure_validates_after_original_bundles_and_live_target_are_deleted(tmp_path:Path)->None:
    fixture,execution,rollback,packet,_,_=_closed(tmp_path)
    shutil.rmtree(execution.bundle_root); shutil.rmtree(rollback.bundle_root); shutil.rmtree(fixture.source_bundle); shutil.rmtree(fixture.target)
    assert validate_lifecycle_closure(packet.packet_root).status=="host_local_diagnostic_lifecycle_closure_valid"

def test_mismatched_or_pending_lifecycle_is_rejected_before_publication(tmp_path:Path)->None:
    fixture,execution,rollback,_,_,_=_closed(tmp_path/"one")
    _,_,other,_,_,_=_closed(tmp_path/"two")
    ed=json.loads((Path(execution.bundle_root)/"bundle_manifest.json").read_text())["bundle_digest"]
    rd=json.loads((Path(other.bundle_root)/"bundle_manifest.json").read_text())["bundle_digest"]
    out=tmp_path/"rejected"; result=build_lifecycle_closure(execution_bundle_root=execution.bundle_root,execution_bundle_digest=ed,rollback_bundle_root=other.bundle_root,rollback_bundle_digest=rd,closure_time=NOW,output_root=out)
    assert result.status.startswith("blocked_") and not (out/"latest.json").exists()

def test_nested_execution_or_rollback_tampering_is_rejected_after_outer_reseal(tmp_path:Path)->None:
    _,_,_,packet,_,_=_closed(tmp_path); nested=Path(packet.packet_root)/"bundles/execution/runtime_result.json"; nested.write_text("{}\n")
    assert validate_lifecycle_closure(packet.packet_root).status=="host_local_diagnostic_lifecycle_closure_invalid"

def test_rebuild_is_deterministic_atomic_and_source_read_only(tmp_path:Path)->None:
    _,execution,rollback,packet,_,_=_closed(tmp_path); before={p:p.read_bytes() for root in (Path(execution.bundle_root),Path(rollback.bundle_root)) for p in root.iterdir() if p.is_file()}
    ed=json.loads((Path(execution.bundle_root)/"bundle_manifest.json").read_text())["bundle_digest"]; rd=json.loads((Path(rollback.bundle_root)/"bundle_manifest.json").read_text())["bundle_digest"]
    again=build_lifecycle_closure(execution_bundle_root=execution.bundle_root,execution_bundle_digest=ed,rollback_bundle_root=rollback.bundle_root,rollback_bundle_digest=rd,closure_time=NOW,output_root=tmp_path/"closure")
    assert again.replayed and again.packet_root==packet.packet_root and before=={p:p.read_bytes() for root in (Path(execution.bundle_root),Path(rollback.bundle_root)) for p in root.iterdir() if p.is_file()}

def test_closure_builder_never_invokes_execution_or_rollback_primitives(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path); ed=json.loads((Path(execution.bundle_root)/"bundle_manifest.json").read_text())["bundle_digest"]; rd=json.loads((Path(rollback.bundle_root)/"bundle_manifest.json").read_text())["bundle_digest"]
    monkeypatch.setattr("sentientos.builtin_runner_transaction_orchestrator.run_builtin_runner_transaction_wing",lambda **k:pytest.fail("execution invoked")); monkeypatch.setattr("sentientos.local_diagnostic_effect.run_local_diagnostic_exact_rollback_wing",lambda **k:pytest.fail("rollback invoked"))
    assert build_lifecycle_closure(execution_bundle_root=execution.bundle_root,execution_bundle_digest=ed,rollback_bundle_root=rollback.bundle_root,rollback_bundle_digest=rd,closure_time=NOW+"x",output_root=tmp_path/"zero").status=="host_local_diagnostic_lifecycle_closure_valid"
