from __future__ import annotations
import hashlib, json, multiprocessing, os, shutil, stat, threading
from pathlib import Path
from typing import Any
import pytest
import sentientos.host_local_diagnostic_lifecycle_closure as closure
from sentientos.host_local_diagnostic_execution_source_runtime import _canon, _raw_sha, _sha, digest_record
from sentientos.host_local_diagnostic_lifecycle_closure import build_lifecycle_closure, derive_closure_id, load_latest_summary, validate_lifecycle_closure
from tests.test_host_local_diagnostic_execution_runtime import _rewrite_manifests
from tests.test_host_local_diagnostic_rollback_runtime import _reseal as _reseal_rollback
from tests.test_host_local_diagnostic_rollback_runtime import _args, _execution

NOW="2026-07-28T12:00:00+00:00"
pytestmark=pytest.mark.no_legacy_skip

def _process_worker(config:dict[str,Any], barrier:Any=None, connection:Any=None, release:Any=None)->None:
    import sentientos.host_local_diagnostic_lifecycle_closure as worker_closure
    def hook(event:str,path:Path)->None:
        if event in {"locked_enter","locked_exit"} and config.get("events"):
            with Path(config["events"]).open("a") as stream:
                stream.write(json.dumps({"event":event,"pid":os.getpid()})+"\n"); stream.flush(); os.fsync(stream.fileno())
        if event==config.get("death_event"):
            if connection is not None: connection.send({"event":event,"pid":os.getpid(),"path":str(path)})
            os._exit(int(config.get("death_code",71)))
        if event=="locked_enter" and release is not None:
            if connection is not None: connection.send({"event":event,"pid":os.getpid(),"path":str(path)})
            release.wait(20)
    worker_closure._publication_hook=hook
    if barrier is not None: barrier.wait(20)
    result=worker_closure.build_lifecycle_closure(
        execution_bundle_root=config["execution_root"],execution_bundle_digest=config["execution_digest"],
        rollback_bundle_root=config["rollback_root"],rollback_bundle_digest=config["rollback_digest"],
        closure_time=NOW,output_root=config["output_root"])
    Path(config["result"]).write_text(json.dumps({"pid":os.getpid(),**result.to_dict()}))

def _process_config(execution:Any,rollback:Any,out:Path,result:Path,**extra:Any)->dict[str,Any]:
    ed,rd=_digests(execution,rollback)
    return {"execution_root":execution.bundle_root,"execution_digest":ed,"rollback_root":rollback.bundle_root,
            "rollback_digest":rd,"output_root":str(out),"result":str(result),**extra}

def _join(process:Any,expected:int=0)->None:
    process.join(30)
    if process.is_alive(): process.terminate(); process.join(10); pytest.fail("spawned closure worker hung")
    assert process.exitcode==expected

def _packet_snapshot(root:Path)->dict[str,tuple[Any,...]]:
    answer={}
    for path in sorted(root.rglob("*")):
        info=path.stat(); raw=path.read_bytes() if path.is_file() else b""
        answer[path.relative_to(root).as_posix()]=(raw,hashlib.sha256(raw).hexdigest(),len(raw),stat.S_IMODE(info.st_mode),info.st_dev,info.st_ino,info.st_mtime_ns)
    return answer

def _closed(root:Path)->tuple[Any,Any,Any,Any,list[Any],list[Any]]:
    fixture,execution,execution_digest,execution_calls=_execution(root)
    coordinator,_,args=_args(root,fixture,execution,execution_digest); args["correlation_id"]=execution.records["runtime_request"]["correlation_id"]; rollback_calls=[]; original=coordinator.rollback
    def rollback(*a:Any,**kw:Any)->Any: rollback_calls.append(1); return original(*a,**kw)
    coordinator.rollback=rollback; result=coordinator.rollback_execution(**args)
    rollback_digest=json.loads((Path(result.bundle_root)/"bundle_manifest.json").read_text())["bundle_digest"]
    packet=build_lifecycle_closure(execution_bundle_root=execution.bundle_root,execution_bundle_digest=execution_digest,rollback_bundle_root=result.bundle_root,rollback_bundle_digest=rollback_digest,closure_time=NOW,output_root=root/"lifecycle-closure")
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
    again=build_lifecycle_closure(execution_bundle_root=execution.bundle_root,execution_bundle_digest=ed,rollback_bundle_root=rollback.bundle_root,rollback_bundle_digest=rd,closure_time=NOW,output_root=tmp_path/"lifecycle-closure")
    assert again.replayed and again.packet_root==packet.packet_root and before=={p:p.read_bytes() for root in (Path(execution.bundle_root),Path(rollback.bundle_root)) for p in root.iterdir() if p.is_file()}

def test_closure_builder_never_invokes_execution_or_rollback_primitives(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path); ed=json.loads((Path(execution.bundle_root)/"bundle_manifest.json").read_text())["bundle_digest"]; rd=json.loads((Path(rollback.bundle_root)/"bundle_manifest.json").read_text())["bundle_digest"]
    monkeypatch.setattr("sentientos.builtin_runner_transaction_orchestrator.run_builtin_runner_transaction_wing",lambda **k:pytest.fail("execution invoked")); monkeypatch.setattr("sentientos.local_diagnostic_effect.run_local_diagnostic_exact_rollback_wing",lambda **k:pytest.fail("rollback invoked"))
    assert build_lifecycle_closure(execution_bundle_root=execution.bundle_root,execution_bundle_digest=ed,rollback_bundle_root=rollback.bundle_root,rollback_bundle_digest=rd,closure_time=NOW+"x",output_root=tmp_path/"zero").status=="host_local_diagnostic_lifecycle_closure_valid"

def _digests(execution:Any,rollback:Any)->tuple[str,str]:
    return (json.loads((Path(execution.bundle_root)/"bundle_manifest.json").read_text())["bundle_digest"],json.loads((Path(rollback.bundle_root)/"bundle_manifest.json").read_text())["bundle_digest"])

def _reseal_outer(root:Path)->None:
    """Regenerate all attacker-computable outer hashes without production validation."""
    report=json.loads((root/"closure_report.json").read_text()); report["digest"]=digest_record(report); (root/"closure_report.json").write_text(_canon(report)+"\n")
    summary=json.loads((root/"summary.json").read_text()); summary["digest"]=digest_record(summary); (root/"summary.json").write_text(_canon(summary)+"\n")
    content=json.loads((root/"content_manifest.json").read_text())
    content["files"]=[{"relative_filename":n,"size_bytes":len((root/n).read_bytes()),"sha256":_raw_sha((root/n).read_bytes())} for n in sorted(x["relative_filename"] for x in content["files"])]
    content["content_manifest_digest"]=_sha({k:v for k,v in content.items() if k!="content_manifest_digest"}); (root/"content_manifest.json").write_text(_canon(content)+"\n")
    receipt=json.loads((root/"receipt.json").read_text()); receipt.update(closure_report_digest=_sha(report),summary_digest=_sha(summary),content_manifest_digest=content["content_manifest_digest"]); receipt["digest"]=digest_record(receipt); (root/"receipt.json").write_text(_canon(receipt)+"\n")
    final=json.loads((root/"final_manifest.json").read_text()); final["files"]=[{"relative_filename":n,"size_bytes":len((root/n).read_bytes()),"sha256":_raw_sha((root/n).read_bytes())} for n in sorted(x["relative_filename"] for x in final["files"])]
    final["packet_digest"]=_sha({k:v for k,v in final.items() if k!="packet_digest"}); (root/"final_manifest.json").write_text(_canon(final)+"\n")
    for manifest,digest_name in ((content,"content_manifest_digest"),(final,"packet_digest")):
        check=dict(manifest); assert check.pop(digest_name)==_sha(check)
        for entry in manifest["files"]:
            raw=(root/entry["relative_filename"]).read_bytes(); assert (entry["size_bytes"],entry["sha256"])==(len(raw),_raw_sha(raw))

def test_closure_identity_is_recomputed_and_bound_to_packet_path(tmp_path:Path)->None:
    _,execution,rollback,packet,_,_=_closed(tmp_path); ed,rd=_digests(execution,rollback)
    assert Path(packet.packet_root).name==derive_closure_id(ed,rd,NOW)
    moved=Path(packet.packet_root).with_name("hldlc-"+"0"*24); Path(packet.packet_root).rename(moved)
    assert "closure_identity_custody_mismatch" in validate_lifecycle_closure(moved).findings

def test_correlation_override_is_rejected_before_any_publication(tmp_path:Path)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); ed,rd=_digests(execution,rollback); out=tmp_path/"rejected"
    result=build_lifecycle_closure(execution_bundle_root=execution.bundle_root,execution_bundle_digest=ed,rollback_bundle_root=rollback.bundle_root,rollback_bundle_digest=rd,closure_time=NOW,output_root=out,correlation_id="alias")
    assert result.findings==("correlation_override_mismatch",) and not out.exists()

def test_staged_copy_is_deeply_validated_before_publication(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); ed,rd=_digests(execution,rollback); original=closure._copy_bundle; calls=[]
    def racing_copy(source:Path,destination:Path)->None:
        calls.append(source); original(source,destination)
        if len(calls)==1: (destination/"runtime_result.json").write_text("{}\n")
    monkeypatch.setattr(closure,"_copy_bundle",racing_copy); out=tmp_path/"race"
    result=build_lifecycle_closure(execution_bundle_root=execution.bundle_root,execution_bundle_digest=ed,rollback_bundle_root=rollback.bundle_root,rollback_bundle_digest=rd,closure_time=NOW,output_root=out)
    assert result.status.startswith("blocked_") and not (out/derive_closure_id(ed,rd,NOW)).exists() and not (out/"latest.json").exists() and not list(out.glob(".hldlc-*"))

def test_pending_lifecycle_is_rejected_after_nested_reseal(tmp_path:Path)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); rb=Path(rollback.bundle_root); value=json.loads((rb/"updated_lifecycle_report.json").read_text()); value["lifecycle_status"]="local_effect_lifecycle_rollback_pending"; (rb/"updated_lifecycle_report.json").write_text(_canon(value)+"\n"); _reseal_rollback(rb)
    ed=json.loads((Path(execution.bundle_root)/"bundle_manifest.json").read_text())["bundle_digest"]; rd=json.loads((rb/"bundle_manifest.json").read_text())["bundle_digest"]
    result=build_lifecycle_closure(execution_bundle_root=execution.bundle_root,execution_bundle_digest=ed,rollback_bundle_root=rb,rollback_bundle_digest=rd,closure_time=NOW,output_root=tmp_path/"pending")
    assert result.status.startswith("blocked_") and not (tmp_path/"pending"/"latest.json").exists()

def test_nested_execution_and_rollback_tampering_is_rejected_after_full_outer_reseal(tmp_path:Path)->None:
    for nested,name in (("execution","runtime_result"),("rollback","runtime_result")):
        _,_,_,packet,_,_=_closed(tmp_path/nested); root=Path(packet.packet_root); bundle=root/"bundles"/nested; value=json.loads((bundle/(name+".json")).read_text()); value["network_performed"]=True; value["digest"]=digest_record(value); (bundle/(name+".json")).write_text(_canon(value)+"\n")
        if nested=="execution": _rewrite_manifests(bundle)
        else: _reseal_rollback(bundle)
        _reseal_outer(root)
        assert validate_lifecycle_closure(root).status=="host_local_diagnostic_lifecycle_closure_invalid"

def test_exact_manifest_metadata_and_unsafe_membership_are_rejected(tmp_path:Path)->None:
    _,_,_,packet,_,_=_closed(tmp_path); root=Path(packet.packet_root); manifest=json.loads((root/"content_manifest.json").read_text()); manifest["extra"]="x"; (root/"content_manifest.json").write_text(_canon(manifest)+"\n"); _reseal_outer(root)
    assert validate_lifecycle_closure(root).status=="host_local_diagnostic_lifecycle_closure_invalid"

def test_concurrent_identical_builders_publish_one_valid_packet(tmp_path:Path)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); ed,rd=_digests(execution,rollback); out=tmp_path/"concurrent"; barrier=threading.Barrier(3); results=[]
    def worker()->None:
        barrier.wait(); results.append(build_lifecycle_closure(execution_bundle_root=execution.bundle_root,execution_bundle_digest=ed,rollback_bundle_root=rollback.bundle_root,rollback_bundle_digest=rd,closure_time=NOW,output_root=out))
    workers=[threading.Thread(target=worker) for _ in range(2)]
    for worker_thread in workers: worker_thread.start()
    barrier.wait()
    for worker_thread in workers: worker_thread.join(20)
    assert len(results)==2 and all(x.status.endswith("_valid") for x in results) and len({x.packet_root for x in results})==1
    assert len([p for p in out.iterdir() if p.is_dir()])==1 and not list(out.glob(".hldlc-*")) and load_latest_summary(out).status.endswith("_valid")

def test_interrupted_latest_publication_recovers_without_rewriting_packet(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); ed,rd=_digests(execution,rollback); out=tmp_path/"interrupted"; original=closure._publish_latest
    monkeypatch.setattr(closure,"_publish_latest",lambda *_: (_ for _ in ()).throw(RuntimeError("interrupt")))
    with pytest.raises(RuntimeError): build_lifecycle_closure(execution_bundle_root=execution.bundle_root,execution_bundle_digest=ed,rollback_bundle_root=rollback.bundle_root,rollback_bundle_digest=rd,closure_time=NOW,output_root=out)
    packet=out/derive_closure_id(ed,rd,NOW); before={p.relative_to(packet):p.read_bytes() for p in packet.rglob("*") if p.is_file()}; monkeypatch.setattr(closure,"_publish_latest",original)
    recovered=build_lifecycle_closure(execution_bundle_root=execution.bundle_root,execution_bundle_digest=ed,rollback_bundle_root=rollback.bundle_root,rollback_bundle_digest=rd,closure_time=NOW,output_root=out)
    assert recovered.replayed and recovered.publication_posture=="recovered" and before=={p.relative_to(packet):p.read_bytes() for p in packet.rglob("*") if p.is_file()}

def test_spawned_process_builders_publish_one_valid_closure_packet(tmp_path:Path)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); out=tmp_path/"spawned"; ctx=multiprocessing.get_context("spawn"); barrier=ctx.Barrier(3)
    configs=[_process_config(execution,rollback,out,tmp_path/f"result-{index}.json") for index in range(2)]
    workers=[ctx.Process(target=_process_worker,args=(config,barrier)) for config in configs]
    for worker in workers: worker.start()
    barrier.wait(20)
    for worker in workers: _join(worker)
    results=[json.loads(Path(config["result"]).read_text()) for config in configs]
    assert len({result["pid"] for result in results})==2
    assert len({result["packet_root"] for result in results})==1 and {result["publication_posture"] for result in results}=={"published","replayed"}
    packets=[path for path in out.iterdir() if path.is_dir()]
    assert len(packets)==1 and validate_lifecycle_closure(packets[0]).status.endswith("_valid")
    assert load_latest_summary(out).status.endswith("_valid") and not list(out.glob(".hldlc-*"))

def test_process_death_after_packet_rename_recovers_pointer_without_rewriting_packet(tmp_path:Path)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); out=tmp_path/"rename-death"; ctx=multiprocessing.get_context("spawn"); parent,child=ctx.Pipe(False)
    dying=_process_config(execution,rollback,out,tmp_path/"unused.json",death_event="packet_published",death_code=72)
    process=ctx.Process(target=_process_worker,args=(dying,None,child)); process.start(); notice=parent.recv(); _join(process,72)
    packet=Path(notice["path"]); before=_packet_snapshot(packet); assert not (out/"latest.json").exists()
    recovery=_process_config(execution,rollback,out,tmp_path/"recovered.json"); worker=ctx.Process(target=_process_worker,args=(recovery,)); worker.start(); _join(worker)
    result=json.loads(Path(recovery["result"]).read_text())
    assert result["publication_posture"]=="recovered" and result["replayed"] is True
    assert before==_packet_snapshot(packet) and load_latest_summary(out).status.endswith("_valid")

def test_process_death_with_staging_releases_lock_and_next_builder_reconciles_residue(tmp_path:Path)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); out=tmp_path/"staging-death"; ctx=multiprocessing.get_context("spawn"); parent,child=ctx.Pipe(False)
    dying=_process_config(execution,rollback,out,tmp_path/"unused.json",death_event="staging_created",death_code=73)
    process=ctx.Process(target=_process_worker,args=(dying,None,child)); process.start(); notice=parent.recv(); _join(process,73)
    stale=Path(notice["path"]); assert stale.is_dir() and (stale/"staging_identity.json").is_file()
    recovery=_process_config(execution,rollback,out,tmp_path/"recovered.json"); worker=ctx.Process(target=_process_worker,args=(recovery,)); worker.start(); _join(worker)
    assert not stale.exists() and not list(out.glob(".hldlc-*"))
    assert json.loads(Path(recovery["result"]).read_text())["publication_posture"]=="published" and load_latest_summary(out).status.endswith("_valid")

def test_process_shared_lock_allows_only_one_publication_critical_section(tmp_path:Path)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); out=tmp_path/"serialized"; events=tmp_path/"events.jsonl"; ctx=multiprocessing.get_context("spawn"); release=ctx.Event(); parent,child=ctx.Pipe(False)
    first=_process_config(execution,rollback,out,tmp_path/"first.json",events=str(events)); second=_process_config(execution,rollback,out,tmp_path/"second.json",events=str(events))
    one=ctx.Process(target=_process_worker,args=(first,None,child,release)); one.start(); entered=parent.recv(); assert entered["event"]=="locked_enter"
    two=ctx.Process(target=_process_worker,args=(second,)); two.start(); release.set(); _join(one); _join(two)
    occupancy=maximum=0
    records=[json.loads(line) for line in events.read_text().splitlines()]
    for record in records:
        occupancy += 1 if record["event"]=="locked_enter" else -1; maximum=max(maximum,occupancy)
    assert maximum==1 and occupancy==0 and len({record["pid"] for record in records})==2

def test_malformed_or_symlinked_staging_residue_fails_closed_without_unrelated_deletion(tmp_path:Path)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); out=tmp_path/"malformed"; out.mkdir(); target=tmp_path/"outside"; target.mkdir(); (target/"sentinel").write_bytes(b"outside")
    symlink=out/".hldlc-symlink"; symlink.symlink_to(target, target_is_directory=True)
    regular=out/".hldlc-file"; regular.write_bytes(b"file")
    malformed=out/".hldlc-malformed"; malformed.mkdir(); (malformed/"unknown").write_bytes(b"unknown")
    unrelated=out/"unrelated"; unrelated.mkdir(); sentinel=unrelated/"sentinel"; sentinel.write_bytes(b"preserve"); before=_packet_snapshot(unrelated)|_packet_snapshot(target)
    config=_process_config(execution,rollback,out,tmp_path/"blocked.json"); _process_worker(config)
    result=json.loads(Path(config["result"]).read_text())
    assert result["status"].startswith("blocked_") and all(path.exists() for path in (symlink,regular,malformed,unrelated,sentinel))
    assert before==(_packet_snapshot(unrelated)|_packet_snapshot(target)) and not (out/"latest.json").exists()

def test_cross_process_results_bind_one_closure_and_packet_digest(tmp_path:Path)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); out=tmp_path/"identity"; ctx=multiprocessing.get_context("spawn"); barrier=ctx.Barrier(3)
    configs=[_process_config(execution,rollback,out,tmp_path/f"identity-{index}.json") for index in range(2)]; workers=[ctx.Process(target=_process_worker,args=(config,barrier)) for config in configs]
    for worker in workers: worker.start()
    barrier.wait(20)
    for worker in workers: _join(worker)
    results=[json.loads(Path(config["result"]).read_text()) for config in configs]; packet=validate_lifecycle_closure(results[0]["packet_root"]); final=packet.records["final_manifest"]
    keys=("closure_id","closure_time","correlation_id","execution_id","rollback_id","execution_bundle_digest","rollback_bundle_digest","final_lifecycle")
    for result in results:
        worker_final=result["records"]["final_manifest"]
        assert all(worker_final[key]==final[key] for key in keys) and worker_final["packet_digest"]==final["packet_digest"]
    assert len({result["pid"] for result in results})==2 and len({result["records"]["final_manifest"]["packet_digest"] for result in results})==1

def test_validly_redigested_latest_pointer_substitution_is_rejected(tmp_path:Path)->None:
    _,_,_,packet,_,_=_closed(tmp_path); out=Path(packet.packet_root).parent; pristine=json.loads((out/"latest.json").read_text())
    for field in ("execution_id","source_request_digest","final_lifecycle"):
        pointer=dict(pristine); pointer[field]="substituted"; pointer["digest"]=digest_record(pointer); (out/"latest.json").write_text(_canon(pointer)+"\n")
        assert load_latest_summary(out).status=="host_local_diagnostic_lifecycle_closure_latest_invalid"
