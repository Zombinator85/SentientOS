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
        if event in {"lock_waiting","locked_enter"} and config.get("report_lock_events") and connection is not None:
            connection.send({"event":event,"pid":os.getpid(),"path":str(path)})
        if event in {"lock_waiting","locked_enter","locked_exit"} and config.get("events"):
            with Path(config["events"]).open("a") as stream:
                stream.write(json.dumps({"event":event,"pid":os.getpid()})+"\n"); stream.flush(); os.fsync(stream.fileno())
        if event==config.get("death_event"):
            notice={"event":event,"pid":os.getpid(),"path":str(path)}
            if event=="staging_identity_prepared":
                record=json.loads(path.read_text()); notice["temporary_identity_path"]=str(path); notice["staging_path"]=str(Path(config["output_root"])/record["staging_name"])
            if connection is not None: connection.send(notice)
            os._exit(int(config.get("death_code",71)))
        if event=="lock_waiting" and config.get("pause_before_flock"):
            if connection is not None: connection.send({"event":event,"pid":os.getpid(),"path":str(path)})
            assert release is not None and release.wait(20)
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

def _latest_reader_worker(output_root:str,result_path:str,connection:Any,release:Any)->None:
    import sentientos.host_local_diagnostic_lifecycle_closure as worker_closure
    def observe(event:str,payload:Any)->None:
        if event=="latest_pointer_custody_acquired":
            connection.send({"event":"reader_lock_held","pid":os.getpid()})
            assert release.wait(20)
    worker_closure._custody_observation_hook=observe
    result=worker_closure.load_latest_summary(output_root)
    Path(result_path).write_text(json.dumps({"pid":os.getpid(),**result.to_dict()}))

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
    for path in [root,*sorted(root.rglob("*"))]:
        info=path.lstat(); raw=path.read_bytes() if stat.S_ISREG(info.st_mode) else b""
        kind="file" if stat.S_ISREG(info.st_mode) else "directory" if stat.S_ISDIR(info.st_mode) else "symlink" if stat.S_ISLNK(info.st_mode) else "other"
        answer["." if path==root else path.relative_to(root).as_posix()]=(kind,raw,hashlib.sha256(raw).hexdigest(),info.st_size,stat.S_IMODE(info.st_mode),info.st_dev,info.st_ino,info.st_mtime_ns)
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
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); ed,rd=_digests(execution,rollback); fired=False
    def hook(event:str,path:Path)->None:
        nonlocal fired
        if event=="lifecycle_packet_after_staged_validation" and not fired: fired=True; (path/"summary.json").write_text("{}\n")
    monkeypatch.setattr(closure,"_publication_hook",hook); out=tmp_path/"race"
    result=build_lifecycle_closure(execution_bundle_root=execution.bundle_root,execution_bundle_digest=ed,rollback_bundle_root=rollback.bundle_root,rollback_bundle_digest=rd,closure_time=NOW,output_root=out)
    assert result.status.startswith("blocked_") and not (out/derive_closure_id(ed,rd,NOW)).exists() and not (out/"latest.json").exists() and list(out.glob(".hldlc-*"))

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

def test_process_death_after_packet_rename_preserves_packet_root_and_descendants(tmp_path:Path)->None:
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

def test_process_death_before_staging_identity_publication_recovers(tmp_path:Path)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); out=tmp_path/"reserved-death"; ctx=multiprocessing.get_context("spawn"); parent,child=ctx.Pipe(False)
    dying=_process_config(execution,rollback,out,tmp_path/"unused.json",death_event="staging_directory_reserved",death_code=74)
    process=ctx.Process(target=_process_worker,args=(dying,None,child)); process.start(); notice=parent.recv(); _join(process,74)
    stale=Path(notice["path"]); assert notice["pid"]==process.pid and stale.is_dir() and not any(stale.iterdir())
    assert not list(out.glob(".hldlc-staging-identity-*")) and not (out/"latest.json").exists()
    recovery=_process_config(execution,rollback,out,tmp_path/"recovered.json"); worker=ctx.Process(target=_process_worker,args=(recovery,)); worker.start(); _join(worker)
    result=json.loads(Path(recovery["result"]).read_text()); final=result["records"]["final_manifest"]
    assert worker.pid!=process.pid and final["closure_id"] and final["packet_digest"] and not stale.exists()
    assert len([p for p in out.iterdir() if p.is_dir()])==1 and (out/"latest.json").is_file() and not list(out.glob(".hldlc-*"))

def test_process_death_after_staging_identity_prepare_recovers(tmp_path:Path)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); out=tmp_path/"prepared-death"; ctx=multiprocessing.get_context("spawn"); parent,child=ctx.Pipe(False)
    dying=_process_config(execution,rollback,out,tmp_path/"unused.json",death_event="staging_identity_prepared",death_code=75)
    process=ctx.Process(target=_process_worker,args=(dying,None,child)); process.start(); notice=parent.recv(); _join(process,75)
    staging=Path(notice["staging_path"]); temporary=Path(notice["temporary_identity_path"]); raw=temporary.read_bytes(); record=json.loads(raw)
    assert notice["pid"]==process.pid and staging.is_dir() and not any(staging.iterdir()) and raw.endswith(b"\n")
    assert closure._valid_staging_record(record,out=out.resolve(),staging_name=staging.name)[0] and not (staging/"staging_identity.json").exists()
    recovery=_process_config(execution,rollback,out,tmp_path/"recovered.json"); worker=ctx.Process(target=_process_worker,args=(recovery,)); worker.start(); _join(worker)
    assert worker.pid!=process.pid and not staging.exists() and not temporary.exists() and not list(out.glob(".hldlc-*"))
    assert json.loads(Path(recovery["result"]).read_text())["status"].endswith("_valid")

def test_process_shared_lock_waiter_is_blocked_until_owner_release(tmp_path:Path)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); out=tmp_path/"serialized"; events=tmp_path/"events.jsonl"; ctx=multiprocessing.get_context("spawn"); release=ctx.Event(); parent,child=ctx.Pipe(False)
    first=_process_config(execution,rollback,out,tmp_path/"first.json",events=str(events)); second=_process_config(execution,rollback,out,tmp_path/"second.json",events=str(events))
    one=ctx.Process(target=_process_worker,args=(first,None,child,release)); one.start(); entered=parent.recv(); assert entered["event"]=="locked_enter"
    waiter_permit=ctx.Event(); waiting_parent,waiting_child=ctx.Pipe(False); second["pause_before_flock"]=True
    two=ctx.Process(target=_process_worker,args=(second,None,waiting_child,waiter_permit)); two.start(); waiting=waiting_parent.recv(); assert waiting["event"]=="lock_waiting"
    waiter_permit.set(); assert two.is_alive() and not Path(second["result"]).exists() and not waiting_parent.poll(0.25)
    assert not any(json.loads(line)["event"]=="locked_enter" and json.loads(line)["pid"]==two.pid for line in events.read_text().splitlines())
    release.set(); _join(one); _join(two)
    occupancy=maximum=0
    records=[json.loads(line) for line in events.read_text().splitlines()]
    for record in records:
        if record["event"]=="locked_enter": occupancy += 1; maximum=max(maximum,occupancy)
        elif record["event"]=="locked_exit": occupancy -= 1
    assert maximum==1 and occupancy==0 and len({record["pid"] for record in records})==2

def test_bootstrap_staging_reconciliation_is_bounded_and_preserves_unsafe_residue(tmp_path:Path)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); out=(tmp_path/"unsafe-bootstrap").resolve(); out.mkdir(); outside=tmp_path/"outside"; outside.mkdir(); (outside/"sentinel").write_bytes(b"outside")
    safe=out/".hldlc-safe-empty"; safe.mkdir(); nonempty=out/".hldlc-nonempty"; nonempty.mkdir(); (nonempty/"child").write_bytes(b"keep")
    malformed=out/".hldlc-staging-identity-malformed"; malformed.write_bytes(b'{"partial":')
    symlink=out/".hldlc-staging-identity-symlink"; symlink.symlink_to(outside/"sentinel")
    directory=out/".hldlc-staging-identity-directory"; directory.mkdir()
    for suffix,root,name in (("wrong-root",outside,".hldlc-wrong-root"),("unsafe-name",out,"../escape")):
        record=closure._staging_record("hldlc-"+"1"*24,name,root.resolve()); (out/f".hldlc-staging-identity-{suffix}").write_text(_canon(record)+"\n")
    unrelated=out/"unrelated-empty"; unrelated.mkdir(); sentinel=out/"sentinel"; sentinel.write_bytes(b"preserve")
    paths=[safe,nonempty,malformed,symlink,directory,unrelated,sentinel,outside]; before={str(path):_packet_snapshot(path) if path.is_dir() and not path.is_symlink() else (path.lstat(),path.read_bytes() if path.is_file() and not path.is_symlink() else b"") for path in paths}
    config=_process_config(execution,rollback,out,tmp_path/"blocked.json"); _process_worker(config); result=json.loads(Path(config["result"]).read_text())
    after={str(path):_packet_snapshot(path) if path.is_dir() and not path.is_symlink() else (path.lstat(),path.read_bytes() if path.is_file() and not path.is_symlink() else b"") for path in paths}
    assert result["status"].startswith("blocked_") and before==after and all(path.exists() or path.is_symlink() for path in paths)

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

def test_bootstrap_crash_recovery_binds_one_closure_and_packet_digest(tmp_path:Path)->None:
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

def _rebuild(execution:Any,rollback:Any,out:Path)->Any:
    ed,rd=_digests(execution,rollback)
    return build_lifecycle_closure(execution_bundle_root=execution.bundle_root,execution_bundle_digest=ed,rollback_bundle_root=rollback.bundle_root,rollback_bundle_digest=rd,closure_time=NOW,output_root=out)

def _prepared_staging_residue(out:Path,name:str=".hldlc-prepared") -> tuple[Path,Path]:
    out.mkdir(parents=True,exist_ok=True); staging=out/name; staging.mkdir(); identity=out/".hldlc-staging-identity-test"
    identity.write_text(_canon(closure._staging_record("hldlc-"+"1"*24,name,out.resolve()))+"\n")
    return identity,staging

def _canonical_staging_residue(source:Path,out:Path,name:str=".hldlc-canonical") -> Path:
    out.mkdir(parents=True,exist_ok=True); staging=out/name; staging.mkdir(); shutil.copytree(source,staging/source.name)
    (staging/"staging_identity.json").write_text(_canon(closure._staging_record(source.name,name,out.resolve()))+"\n")
    return staging

def test_reconciliation_rejects_reserved_directory_substitution_before_delete(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); out=(tmp_path/"out").resolve(); out.mkdir(); reserved=out/".hldlc-reserved"; reserved.mkdir(); original=out/"reserved-original"; replacement=reserved/"replacement"
    def hook(event:str,path:Path)->None:
        nonlocal replacement
        if event=="staging_reconciliation_classified": reserved.rename(original); (original/"sentinel").write_bytes(b"original"); reserved.mkdir(); replacement=reserved/"replacement"; replacement.write_bytes(b"replacement")
    monkeypatch.setattr(closure,"_publication_hook",hook); result=_rebuild(execution,rollback,out)
    assert "staging_reconciliation_candidate_identity_changed" in result.findings and (original/"sentinel").read_bytes()==b"original" and replacement.read_bytes()==b"replacement" and not (out/"latest.json").exists()

def test_reconciliation_rejects_prepared_identity_substitution_before_delete(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); out=(tmp_path/"out").resolve(); identity,associated=_prepared_staging_residue(out); original=out/"identity-original"; replacement=b"replacement\n"; fired=False
    def hook(event:str,path:Path)->None:
        nonlocal fired
        if event=="staging_reconciliation_before_remove_candidate" and path.name==identity.name and not fired: fired=True; identity.rename(original); identity.write_bytes(replacement)
    monkeypatch.setattr(closure,"_publication_hook",hook); result=_rebuild(execution,rollback,out)
    assert "staging_reconciliation_candidate_bytes_changed" in result.findings and "zero_candidates_removed" in " ".join(result.findings) and identity.read_bytes()==replacement and original.is_file() and associated.is_dir() and not (out/"latest.json").exists()

def test_reconciliation_rejects_canonical_staging_root_substitution_before_recursive_delete(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,execution,rollback,packet,_,_=_closed(tmp_path/"inputs"); out=(tmp_path/"out").resolve(); staging=_canonical_staging_residue(Path(packet.packet_root),out); original=out/"canonical-original"; fired=False
    def hook(event:str,path:Path)->None:
        nonlocal fired
        if event=="staging_reconciliation_before_remove_candidate" and path.name==staging.name and not fired: fired=True; staging.rename(original); staging.mkdir(); (staging/"replacement").write_bytes(b"replacement")
    monkeypatch.setattr(closure,"_publication_hook",hook); result=_rebuild(execution,rollback,out)
    assert "staging_reconciliation_candidate_identity_changed" in result.findings and "zero_candidates_removed" in " ".join(result.findings) and (staging/"replacement").read_bytes()==b"replacement" and original.is_dir()

def test_reconciliation_rejects_canonical_nested_member_substitution_before_recursive_delete(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,execution,rollback,packet,_,_=_closed(tmp_path/"inputs"); out=(tmp_path/"out").resolve(); staging=_canonical_staging_residue(Path(packet.packet_root),out); target=staging/"staging_identity.json"; original=staging/"identity-original"; sibling=staging/Path(packet.packet_root).name; before=_packet_snapshot(sibling); fired=False
    def hook(event:str,path:Path)->None:
        nonlocal fired
        if event=="staging_reconciliation_before_remove_member" and path.name==target.name and not fired: fired=True; target.rename(original); target.write_bytes(b"replacement\n")
    monkeypatch.setattr(closure,"_publication_hook",hook); result=_rebuild(execution,rollback,out)
    assert "staging_reconciliation_nested_member_identity_changed" in result.findings and target.read_bytes()==b"replacement\n" and original.is_file() and before==_packet_snapshot(sibling) and not (out/"latest.json").exists()

def test_reconciliation_rejects_publication_root_replacement_before_delete(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); out=(tmp_path/"out").resolve(); out.mkdir(); reserved=out/".hldlc-reserved"; reserved.mkdir(); original=tmp_path/"publication-original"; fired=False
    def hook(event:str,path:Path)->None:
        nonlocal fired
        if event=="staging_reconciliation_classified" and not fired: fired=True; out.rename(original); out.mkdir(); (out/"replacement").write_bytes(b"replacement")
    monkeypatch.setattr(closure,"_publication_hook",hook); result=_rebuild(execution,rollback,out)
    assert result.findings==("staging_reconciliation_publication_root_identity_changed",) and (original/reserved.name).is_dir() and (out/"replacement").read_bytes()==b"replacement" and not (original/"latest.json").exists() and not (out/"latest.json").exists()

def test_descriptor_relative_reconciliation_removes_only_identity_bound_candidates(tmp_path:Path)->None:
    _,execution,rollback,packet,_,_=_closed(tmp_path/"inputs"); out=(tmp_path/"out").resolve(); out.mkdir(); reserved=out/".hldlc-reserved"; reserved.mkdir(); identity,associated=_prepared_staging_residue(out); canonical=_canonical_staging_residue(Path(packet.packet_root),out); sentinel=out/"unrelated"; sentinel.mkdir(); (sentinel/"bytes").write_bytes(b"unchanged"); before=_packet_snapshot(sentinel)
    result=_rebuild(execution,rollback,out)
    assert result.status.endswith("_valid") and not any(path.exists() for path in (reserved,identity,associated,canonical)) and not list(out.glob(".hldlc-*")) and before==_packet_snapshot(sentinel)
    assert len([path for path in out.iterdir() if path.is_dir() and path.name.startswith("hldlc-")])==1 and (out/"latest.json").is_file() and validate_lifecycle_closure(result.packet_root).status.endswith("_valid")

def test_reconciliation_rejects_reserved_directory_mode_change_before_delete(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); out=(tmp_path/"out").resolve(); out.mkdir(); target=out/".hldlc-reserved"; target.mkdir(); sentinel=out/"sentinel"; sentinel.write_bytes(b"keep"); before=sentinel.stat()
    def hook(event:str,path:Path)->None:
        if event=="staging_reconciliation_before_remove_candidate" and path.name==target.name: target.chmod(0o700)
    monkeypatch.setattr(closure,"_publication_hook",hook); result=_rebuild(execution,rollback,out)
    assert "staging_reconciliation_candidate_metadata_changed" in result.findings and "zero_candidates_removed" in " ".join(result.findings)
    assert target.is_dir() and sentinel.read_bytes()==b"keep" and (sentinel.stat().st_dev,sentinel.stat().st_ino)==(before.st_dev,before.st_ino) and not (out/"latest.json").exists()


def test_reconciliation_rejects_canonical_root_mtime_change_before_recursive_delete(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,execution,rollback,packet,_,_=_closed(tmp_path/"inputs"); out=(tmp_path/"out").resolve(); target=_canonical_staging_residue(Path(packet.packet_root),out); original=target.stat().st_mtime_ns
    def hook(event:str,path:Path)->None:
        if event=="staging_reconciliation_before_remove_candidate" and path.name==target.name: os.utime(target,ns=(target.stat().st_atime_ns,original+1_000_000))
    monkeypatch.setattr(closure,"_publication_hook",hook); result=_rebuild(execution,rollback,out)
    assert "staging_reconciliation_candidate_metadata_changed" in result.findings and "zero_candidates_removed" in " ".join(result.findings) and target.is_dir() and not (out/"latest.json").exists()


def test_reconciliation_rejects_nested_file_metadata_change_before_unlink(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,execution,rollback,packet,_,_=_closed(tmp_path/"inputs"); out=(tmp_path/"out").resolve(); staging=_canonical_staging_residue(Path(packet.packet_root),out); target=staging/"staging_identity.json"; raw=target.read_bytes(); original=target.stat().st_mtime_ns
    def hook(event:str,path:Path)->None:
        if event=="staging_reconciliation_before_remove_member" and path.name==target.name: os.utime(target,ns=(target.stat().st_atime_ns,original+1_000_000))
    monkeypatch.setattr(closure,"_publication_hook",hook); result=_rebuild(execution,rollback,out)
    assert "staging_reconciliation_nested_member_metadata_changed" in result.findings and "zero_candidates_removed" in " ".join(result.findings) and target.read_bytes()==raw and not (out/"latest.json").exists()


def test_reconciliation_rejects_nested_directory_metadata_change_before_recursive_delete(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,execution,rollback,packet,_,_=_closed(tmp_path/"inputs"); out=(tmp_path/"out").resolve(); staging=_canonical_staging_residue(Path(packet.packet_root),out); target=staging/Path(packet.packet_root).name/"bundles"; before=_packet_snapshot(target); fired=False
    def hook(event:str,path:Path)->None:
        nonlocal fired
        if event=="staging_reconciliation_before_remove_member" and path.name==target.name and not fired: fired=True; target.chmod(0o755)
    monkeypatch.setattr(closure,"_publication_hook",hook); result=_rebuild(execution,rollback,out)
    assert "staging_reconciliation_nested_member_metadata_changed" in result.findings and target.is_dir() and before.keys()==_packet_snapshot(target).keys() and not (out/"latest.json").exists()


def _replace_root(out:Path, original:Path)->bytes:
    out.rename(original); out.mkdir(); sentinel=out/"replacement-sentinel"; sentinel.write_bytes(b"replacement"); return sentinel.read_bytes()


def test_publication_root_replacement_after_reconciliation_does_not_redirect_staging(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); out=(tmp_path/"out").resolve(); original=tmp_path/"original"; fired=False
    def hook(event:str,path:Path)->None:
        nonlocal fired
        if event=="lifecycle_publication_after_reconciliation" and not fired: fired=True; _replace_root(out,original)
    monkeypatch.setattr(closure,"_publication_hook",hook); result=_rebuild(execution,rollback,out)
    assert result.findings==("lifecycle_publication_root_identity_changed_after_reconciliation",) and (out/"replacement-sentinel").read_bytes()==b"replacement" and not list(out.glob(".hldlc-*")) and not (out/"latest.json").exists()


def test_publication_root_replacement_before_packet_publish_preserves_replacement(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); out=(tmp_path/"out").resolve(); original=tmp_path/"original"; fired=False
    def hook(event:str,path:Path)->None:
        nonlocal fired
        if event=="lifecycle_publication_before_packet_publish" and not fired: fired=True; _replace_root(out,original)
    monkeypatch.setattr(closure,"_publication_hook",hook); result=_rebuild(execution,rollback,out)
    assert result.findings==("lifecycle_publication_root_identity_changed_before_packet_publish",) and (out/"replacement-sentinel").read_bytes()==b"replacement" and not (out/"latest.json").exists() and len(list(original.glob(".hldlc-*")))==1


def test_publication_root_replacement_before_pointer_publish_withholds_pointer_from_replacement(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); out=(tmp_path/"out").resolve(); original=tmp_path/"original"; fired=False
    def hook(event:str,path:Path)->None:
        nonlocal fired
        if event=="lifecycle_publication_before_pointer_publish" and not fired: fired=True; _replace_root(out,original)
    monkeypatch.setattr(closure,"_publication_hook",hook); result=_rebuild(execution,rollback,out)
    assert result.findings==("lifecycle_publication_root_identity_changed_before_pointer_publish",) and (out/"replacement-sentinel").read_bytes()==b"replacement" and not (out/"latest.json").exists()
    packet=original/derive_closure_id(*_digests(execution,rollback),NOW); before=_packet_snapshot(packet); shutil.rmtree(out); original.rename(out); monkeypatch.setattr(closure,"_publication_hook",lambda *_:None); recovered=_rebuild(execution,rollback,out)
    assert recovered.publication_posture=="recovered" and before==_packet_snapshot(out/packet.name) and (out/"latest.json").is_file()


def test_descriptor_bound_publication_commits_packet_and_pointer_to_bound_root(tmp_path:Path)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); out=(tmp_path/"out").resolve(); out.mkdir(); sentinel=out/"sentinel"; sentinel.write_bytes(b"unchanged"); result=_rebuild(execution,rollback,out)
    assert result.status.endswith("_valid") and result.packet_root==str(out/derive_closure_id(*_digests(execution,rollback),NOW)) and sentinel.read_bytes()==b"unchanged"
    assert len([p for p in out.iterdir() if p.is_dir() and p.name.startswith("hldlc-")])==1 and (out/"latest.json").is_file() and not list(out.glob(".hldlc-*")) and not list(out.glob(".latest-*"))


def test_staging_identity_source_substitution_before_atomic_commit_is_rejected(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); out=(tmp_path/"out").resolve(); backup=tmp_path/"identity-backup"
    def hook(event:str,path:Path)->None:
        if event=="staging_identity_prepared": path.rename(backup); path.write_bytes(b"substitute")
    monkeypatch.setattr(closure,"_publication_hook",hook); result=_rebuild(execution,rollback,out)
    assert result.findings==("lifecycle_staging_identity_source_changed",) and backup.is_file() and backup.read_text().endswith("\n")
    assert next(out.glob(".hldlc-staging-identity-*")).read_bytes()==b"substitute" and not (out/"latest.json").exists() and not list(out.glob("hldlc-*"))


def test_staging_identity_destination_injection_is_preserved(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); out=(tmp_path/"out").resolve(); captured:dict[str,Any]={}
    def hook(event:str,path:Path)->None:
        if event=="staging_identity_prepared":
            record=json.loads(path.read_text()); target=out/record["staging_name"]/"staging_identity.json"; target.write_bytes(b"sentinel"); captured["target"]=target; captured["stat"]=target.stat()
    monkeypatch.setattr(closure,"_publication_hook",hook); result=_rebuild(execution,rollback,out); target=Path(captured["target"]); before=captured["stat"]; after=target.stat()
    assert result.findings==("lifecycle_staging_identity_destination_conflict",) and target.read_bytes()==b"sentinel" and (before.st_dev,before.st_ino,before.st_mode,before.st_mtime_ns)==(after.st_dev,after.st_ino,after.st_mode,after.st_mtime_ns)
    assert list(out.glob(".hldlc-staging-identity-*")) and not (out/"latest.json").exists()


def test_packet_source_substitution_before_atomic_commit_is_rejected(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); out=(tmp_path/"out").resolve(); backup=tmp_path/"packet-backup"
    def hook(event:str,path:Path)->None:
        if event=="lifecycle_publication_before_packet_publish": path.rename(backup); path.mkdir(); (path/"sentinel").write_bytes(b"replacement")
    monkeypatch.setattr(closure,"_publication_hook",hook); result=_rebuild(execution,rollback,out)
    assert result.findings==("lifecycle_packet_source_changed_before_commit",) and backup.is_dir() and not (out/backup.name).exists() and not (out/"latest.json").exists()
    assert next(out.glob(".hldlc-*/hldlc-*/sentinel")).read_bytes()==b"replacement"


def test_packet_destination_injection_is_preserved_by_no_replace_commit(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); out=(tmp_path/"out").resolve(); captured:dict[str,Any]={}
    def hook(event:str,path:Path)->None:
        if event=="lifecycle_publication_before_packet_publish":
            target=out/path.name; target.mkdir(); sentinel=target/"sentinel"; sentinel.write_bytes(b"destination"); captured.update(target=target,snapshot=_packet_snapshot(target))
    monkeypatch.setattr(closure,"_publication_hook",hook); result=_rebuild(execution,rollback,out); target=Path(captured["target"])
    assert result.findings==("lifecycle_packet_destination_conflict",) and _packet_snapshot(target)==captured["snapshot"] and not (out/"latest.json").exists()
    assert list(out.glob(".hldlc-*/hldlc-*"))


def test_pointer_source_substitution_before_atomic_commit_is_rejected(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); out=(tmp_path/"out").resolve(); backup=tmp_path/"pointer-backup"
    def hook(event:str,path:Path)->None:
        if event=="lifecycle_pointer_before_commit": (out/path.name).rename(backup); (out/path.name).write_bytes(b"substitute")
    monkeypatch.setattr(closure,"_publication_hook",hook); result=_rebuild(execution,rollback,out)
    assert result.findings==("lifecycle_pointer_source_changed_before_commit",) and backup.is_file() and next(out.glob(".latest-*")).read_bytes()==b"substitute" and not (out/"latest.json").exists()
    assert validate_lifecycle_closure(out/derive_closure_id(*_digests(execution,rollback),NOW)).status.endswith("_valid")


def test_pointer_destination_injection_is_preserved_by_no_replace_commit(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); out=(tmp_path/"out").resolve(); captured:dict[str,Any]={}
    def hook(event:str,path:Path)->None:
        if event=="lifecycle_pointer_before_commit": (out/"latest.json").write_bytes(b"sentinel"); captured["stat"]=(out/"latest.json").stat()
    monkeypatch.setattr(closure,"_publication_hook",hook); result=_rebuild(execution,rollback,out); before=captured["stat"]; after=(out/"latest.json").stat()
    assert result.findings==("lifecycle_pointer_destination_conflict",) and (out/"latest.json").read_bytes()==b"sentinel" and (before.st_dev,before.st_ino,before.st_mode,before.st_mtime_ns)==(after.st_dev,after.st_ino,after.st_mode,after.st_mtime_ns)
    assert list(out.glob(".latest-*")) and validate_lifecycle_closure(out/derive_closure_id(*_digests(execution,rollback),NOW)).status.endswith("_valid")


def test_publication_cleanup_rejects_regular_member_substitution_before_unlink(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); out=(tmp_path/"out").resolve(); fired=False
    def hook(event:str,path:Path)->None:
        nonlocal fired
        if event=="lifecycle_cleanup_before_remove_member" and not fired:
            fired=True; target=out/path; target.rename(target.with_suffix(".original")); target.write_bytes(b"replacement")
    monkeypatch.setattr(closure,"_publication_hook",hook); result=_rebuild(execution,rollback,out)
    assert "publication_cleanup_member_identity_changed" in result.findings and result.publication_posture=="cleanup_blocked" and next(out.glob(".hldlc-*/staging_identity.json")).read_bytes()==b"replacement"
    assert (out/"latest.json").is_file() and validate_lifecycle_closure(result.packet_root).status.endswith("_valid")


def test_publication_cleanup_rejects_directory_substitution_before_descent(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); out=(tmp_path/"out").resolve(); injected=False; swapped=False
    def hook(event:str,path:Path)->None:
        nonlocal injected,swapped
        if event=="lifecycle_pointer_before_commit" and not injected:
            injected=True; staging=next(out.glob(".hldlc-*")); (staging/"cleanup-dir").mkdir(); (staging/"cleanup-dir"/"original").write_bytes(b"original")
        if event=="lifecycle_cleanup_before_remove_directory" and path.name=="cleanup-dir" and not swapped:
            swapped=True; target=out/path; target.rename(target.with_name("cleanup-original")); target.mkdir(); (target/"sentinel").write_bytes(b"replacement")
    monkeypatch.setattr(closure,"_publication_hook",hook); result=_rebuild(execution,rollback,out)
    assert "publication_cleanup_member_identity_changed" in result.findings and result.publication_posture=="cleanup_blocked" and next(out.glob(".hldlc-*/cleanup-dir/sentinel")).read_bytes()==b"replacement"
    assert next(out.glob(".hldlc-*/cleanup-original/original")).read_bytes()==b"original" and (out/"latest.json").is_file() and validate_lifecycle_closure(result.packet_root).status.endswith("_valid")


def test_atomic_no_replace_publication_commits_exact_packet_and_pointer(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); out=(tmp_path/"out").resolve(); calls:list[tuple[str,str]]=[]; original=closure._atomic_rename_noreplace
    def observed(source_fd:int,source_name:str,destination_fd:int,destination_name:str)->None:
        calls.append((source_name,destination_name)); original(source_fd,source_name,destination_fd,destination_name)
    monkeypatch.setattr(closure,"_atomic_rename_noreplace",observed); result=_rebuild(execution,rollback,out)
    assert result.status.endswith("_valid") and len(calls)==3 and calls[0][1]=="staging_identity.json" and calls[1][0]==calls[1][1]==Path(result.packet_root).name and calls[2][1]=="latest.json"
    assert not list(out.glob(".hldlc-*")) and not list(out.glob(".latest-*")) and (out/"latest.json").is_file() and validate_lifecycle_closure(result.packet_root).status.endswith("_valid")


def _race_inputs(tmp_path:Path)->tuple[Any,Any,str,str,Path]:
    _,execution,rollback,_,_,_=_closed(tmp_path/"inputs"); ed,rd=_digests(execution,rollback); return execution,rollback,ed,rd,(tmp_path/"out").resolve()


def test_descriptor_native_copy_rejects_source_file_substitution_before_open(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    execution,rollback,ed,rd,out=_race_inputs(tmp_path); target=Path(execution.bundle_root)/"runtime_result.json"; original=target.with_name("runtime_result.original"); replacement=b'replacement'; fired=False
    def hook(event:str,path:Path)->None:
        nonlocal fired
        if event=="lifecycle_copy_before_source_member_open" and path.as_posix().endswith("bundles/execution/runtime_result.json") and not fired: fired=True; target.rename(original); target.write_bytes(replacement)
    monkeypatch.setattr(closure,"_publication_hook",hook); result=_rebuild(execution,rollback,out)
    assert result.findings==("lifecycle_source_member_identity_changed_before_copy",) and target.read_bytes()==replacement and original.is_file() and not (out/derive_closure_id(ed,rd,NOW)).exists() and not (out/"latest.json").exists()
    assert all(replacement not in path.read_bytes() for path in out.rglob("*") if path.is_file())


def test_descriptor_native_copy_rejects_source_symlink_injection_without_reading_external_target(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    execution,rollback,ed,rd,out=_race_inputs(tmp_path); target=Path(execution.bundle_root)/"runtime_result.json"; original=target.with_name("runtime_result.original"); external=tmp_path/"external"; external.write_bytes(b'external-secret'); before=external.stat(); fired=False
    def hook(event:str,path:Path)->None:
        nonlocal fired
        if event=="lifecycle_copy_before_source_member_open" and path.as_posix().endswith("bundles/execution/runtime_result.json") and not fired: fired=True; target.rename(original); target.symlink_to(external)
    monkeypatch.setattr(closure,"_publication_hook",hook); result=_rebuild(execution,rollback,out); after=external.stat()
    assert result.status.startswith("blocked_") and target.is_symlink() and external.read_bytes()==b'external-secret' and (before.st_dev,before.st_ino,before.st_mtime_ns)==(after.st_dev,after.st_ino,after.st_mtime_ns)
    assert all(b'external-secret' not in path.read_bytes() for path in out.rglob("*") if path.is_file()) and not (out/derive_closure_id(ed,rd,NOW)).exists() and not (out/"latest.json").exists()


def test_descriptor_native_copy_rejects_source_metadata_change_during_copy(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    execution,rollback,_,_,out=_race_inputs(tmp_path); target=Path(execution.bundle_root)/"runtime_result.json"; fired=False
    def hook(event:str,path:Path)->None:
        nonlocal fired
        if event=="lifecycle_copy_before_source_member_finalize" and path.as_posix().endswith("bundles/execution/runtime_result.json") and not fired: fired=True; target.chmod(0o640)
    monkeypatch.setattr(closure,"_publication_hook",hook); result=_rebuild(execution,rollback,out)
    assert result.findings==("lifecycle_source_member_metadata_changed_during_copy",) and not (out/"latest.json").exists()


@pytest.mark.parametrize(("kind","finding"),(('file','lifecycle_destination_file_conflict'),('directory','lifecycle_destination_directory_conflict')))
def test_descriptor_native_copy_preserves_injected_destination(tmp_path:Path,monkeypatch:pytest.MonkeyPatch,kind:str,finding:str)->None:
    execution,rollback,_,_,out=_race_inputs(tmp_path); captured:dict[str,Any]={}; event="lifecycle_copy_before_destination_member_create" if kind=='file' else "lifecycle_copy_before_destination_directory_create"
    def hook(current:str,path:Path)->None:
        if current==event and path.as_posix().endswith("bundles/execution/runtime_result.json" if kind=='file' else "bundles/execution") and not captured:
            if kind=='file': path.write_bytes(b'sentinel')
            else: path.mkdir(); (path/"sentinel").write_bytes(b'keep')
            captured.update(path=path,snapshot=_packet_snapshot(path) if kind=='directory' else (path.stat(),path.read_bytes()))
    monkeypatch.setattr(closure,"_publication_hook",hook); result=_rebuild(execution,rollback,out); path=Path(captured['path'])
    assert result.findings==(finding,) and not (out/"latest.json").exists()
    if kind=='file': assert path.read_bytes()==b'sentinel' and (path.stat().st_dev,path.stat().st_ino)==(captured['snapshot'][0].st_dev,captured['snapshot'][0].st_ino)
    else: assert _packet_snapshot(path)==captured['snapshot']


def test_descriptor_native_copy_preserves_injected_destination_file(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    test_descriptor_native_copy_preserves_injected_destination(tmp_path,monkeypatch,'file','lifecycle_destination_file_conflict')


def test_descriptor_native_copy_preserves_injected_destination_directory(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    test_descriptor_native_copy_preserves_injected_destination(tmp_path,monkeypatch,'directory','lifecycle_destination_directory_conflict')


@pytest.mark.parametrize(("mutation","finding"),(('bytes','lifecycle_packet_member_bytes_changed_before_commit'),('metadata','lifecycle_packet_member_metadata_changed_before_commit'),('membership','lifecycle_packet_membership_changed_before_commit')))
def test_packet_mutation_after_staged_validation_blocks(tmp_path:Path,monkeypatch:pytest.MonkeyPatch,mutation:str,finding:str)->None:
    execution,rollback,ed,rd,out=_race_inputs(tmp_path); renamed=False
    original=closure._atomic_rename_noreplace
    def rename(*args:Any,**kwargs:Any)->None:
        nonlocal renamed
        if args[1]==args[3] and str(args[1]).startswith('hldlc-'): renamed=True
        original(*args,**kwargs)
    def hook(event:str,path:Path)->None:
        if event=="lifecycle_publication_before_packet_publish":
            target=path/"summary.json"
            if mutation=='bytes': target.write_bytes(b'changed\n')
            elif mutation=='metadata': target.chmod(0o640)
            else: (path/"injected").write_bytes(b'injected')
    monkeypatch.setattr(closure,"_atomic_rename_noreplace",rename); monkeypatch.setattr(closure,"_publication_hook",hook); result=_rebuild(execution,rollback,out)
    assert result.findings==(finding,) and not renamed and not (out/derive_closure_id(ed,rd,NOW)).exists() and not (out/"latest.json").exists() and list(out.glob(".hldlc-*"))


def test_packet_byte_mutation_after_staged_validation_blocks_before_final_rename(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None: test_packet_mutation_after_staged_validation_blocks(tmp_path,monkeypatch,'bytes','lifecycle_packet_member_bytes_changed_before_commit')
def test_packet_metadata_mutation_after_staged_validation_blocks_before_final_rename(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None: test_packet_mutation_after_staged_validation_blocks(tmp_path,monkeypatch,'metadata','lifecycle_packet_member_metadata_changed_before_commit')
def test_packet_membership_injection_after_staged_validation_blocks_before_final_rename(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None: test_packet_mutation_after_staged_validation_blocks(tmp_path,monkeypatch,'membership','lifecycle_packet_membership_changed_before_commit')


def test_descriptor_native_packet_construction_uses_no_copytree_or_alias_mutation(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    execution,rollback,_,_,out=_race_inputs(tmp_path); monkeypatch.setattr(shutil,"copytree",lambda *_a,**_k:pytest.fail("copytree used")); monkeypatch.setattr(closure,"_copy_bundle",lambda *_a,**_k:pytest.fail("pathname copy used"))
    result=_rebuild(execution,rollback,out); assert result.status.endswith('_valid') and validate_lifecycle_closure(result.packet_root).status.endswith('_valid')


def test_descriptor_native_packet_snapshots_match_before_and_after_commit(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    execution,rollback,_,_,out=_race_inputs(tmp_path); snapshots=[]; original=closure._packet_snapshot
    def observed(fd:int)->Any:
        value=original(fd); snapshots.append(value); return value
    monkeypatch.setattr(closure,"_packet_snapshot",observed); result=_rebuild(execution,rollback,out)
    assert result.status.endswith('_valid') and any(a==b for a,b in zip(snapshots,snapshots[1:]))


def test_atomic_rename_basename_validation_rejects_dot_and_dotdot()->None:
    for name in ('','.', '..','a/b','a\\b','/absolute'): assert not closure._safe_basename(name)
    assert closure._safe_basename('.hldlc-safe')

def test_public_validation_rejects_packet_root_replacement_after_open(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,_,_,packet,_,_=_closed(tmp_path); root=Path(packet.packet_root); original=root.with_name(root.name+'.original'); before=_packet_snapshot(root)
    def hook(event:str,path:Path)->None:
        if event=='lifecycle_validation_after_packet_root_open': root.rename(original); root.mkdir(); (root/'sentinel').write_bytes(b'keep')
    monkeypatch.setattr(closure,'_publication_hook',hook); result=validate_lifecycle_closure(root)
    assert 'lifecycle_validation_packet_root_identity_changed' in result.findings and _packet_snapshot(original)==before and (root/'sentinel').read_bytes()==b'keep' and _packet_snapshot(root)=={'.':_packet_snapshot(root)['.'],'sentinel':_packet_snapshot(root)['sentinel']} and '/proc/self/fd' not in result.packet_root


def _validation_mutation(tmp_path:Path,monkeypatch:pytest.MonkeyPatch,kind:str)->tuple[Any,Path,dict[str,Any]]:
    _,_,_,packet,_,_=_closed(tmp_path); root=Path(packet.packet_root); fired=False; evidence:dict[str,Any]={}; target=root/'summary.json'; evidence['before']=target.read_bytes(); evidence['inode']=target.stat().st_ino; evidence['mode']=stat.S_IMODE(target.stat().st_mode)
    def hook(event:str,path:Path)->None:
        nonlocal fired
        if event=='lifecycle_validation_after_initial_snapshot' and not fired:
            fired=True
            if kind=='identity': target.rename(root.parent/'summary.original'); target.write_bytes(b'{}\n'); evidence['replacement_inode']=target.stat().st_ino
            elif kind=='metadata': target.chmod(0o640)
            else: (root/'injected').write_bytes(b'keep')
    monkeypatch.setattr(closure,'_publication_hook',hook); return validate_lifecycle_closure(root),root,evidence


def test_public_validation_rejects_packet_member_substitution_during_validation(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    result,root,evidence=_validation_mutation(tmp_path,monkeypatch,'identity'); original=root.parent/'summary.original'; replacement=root/'summary.json'
    assert not result.status.endswith('_valid') and set(result.findings) & {'lifecycle_validation_packet_member_identity_changed','lifecycle_validation_packet_member_bytes_changed','lifecycle_validation_packet_member_metadata_changed'}
    assert original.read_bytes()==evidence['before'] and replacement.read_bytes()==b'{}\n' and original.stat().st_ino==evidence['inode'] and replacement.stat().st_ino==evidence['replacement_inode']

def test_public_validation_rejects_packet_metadata_change_during_validation(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    result,root,evidence=_validation_mutation(tmp_path,monkeypatch,'metadata'); target=root/'summary.json'
    assert result.findings==('lifecycle_validation_packet_member_metadata_changed',) and target.read_bytes()==evidence['before'] and target.stat().st_ino==evidence['inode'] and stat.S_IMODE(target.stat().st_mode)==0o640 and evidence['mode']!=0o640

def test_public_validation_rejects_packet_membership_change_during_validation(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    result,root,evidence=_validation_mutation(tmp_path,monkeypatch,'membership')
    assert 'lifecycle_validation_packet_membership_changed' in result.findings and (root/'injected').read_bytes()==b'keep' and (root/'summary.json').read_bytes()==evidence['before']


def _guard_descriptor_adapter(monkeypatch:pytest.MonkeyPatch)->dict[str,int]:
    observed={'uses':0,'identity_checks':0,'canonicalizations':0}; original_adapter=closure._descriptor_adapter
    original_resolve=Path.resolve; original_realpath=os.path.realpath; original_readlink=os.readlink; original_path_readlink=getattr(Path,'readlink',None); original_stat=os.stat
    def forbidden(value:Any)->bool:
        parts=str(value).split('/'); return len(parts)>=5 and parts[:4]==['','proc','self','fd'] and parts[4].isdigit()
    def adapter(fd:int,callback:Any)->Any:
        observed['uses']+=1; return original_adapter(fd,callback)
    def resolve(self:Path,*a:Any,**k:Any)->Path:
        if forbidden(self): observed['canonicalizations']+=1; pytest.fail('descriptor adapter resolved')
        return original_resolve(self,*a,**k)
    def realpath(path:Any,*a:Any,**k:Any)->Any:
        if forbidden(path): observed['canonicalizations']+=1; pytest.fail('descriptor adapter realpathed')
        return original_realpath(path,*a,**k)
    def readlink(path:Any,*a:Any,**k:Any)->Any:
        if forbidden(path): observed['canonicalizations']+=1; pytest.fail('descriptor adapter readlinked')
        return original_readlink(path,*a,**k)
    def path_readlink(self:Path,*a:Any,**k:Any)->Path:
        if forbidden(self): observed['canonicalizations']+=1; pytest.fail('descriptor adapter Path.readlink called')
        assert original_path_readlink is not None; return original_path_readlink(self,*a,**k)
    def checked_stat(path:Any,*a:Any,**k:Any)->Any:
        if forbidden(path): observed['identity_checks']+=1
        return original_stat(path,*a,**k)
    monkeypatch.setattr(closure,'_descriptor_adapter',adapter); monkeypatch.setattr(Path,'resolve',resolve); monkeypatch.setattr(os.path,'realpath',realpath); monkeypatch.setattr(os,'readlink',readlink); monkeypatch.setattr(os,'stat',checked_stat)
    if original_path_readlink is not None: monkeypatch.setattr(Path,'readlink',path_readlink)
    return observed


def test_public_validation_uses_unresolved_descriptor_alias(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,_,_,packet,_,_=_closed(tmp_path); observed=_guard_descriptor_adapter(monkeypatch)
    result=validate_lifecycle_closure(packet.packet_root)
    assert result.status.endswith('_valid') and '/proc/self/fd/' not in result.packet_root
    assert observed['uses']>0 and observed['identity_checks']>=observed['uses']*2 and observed['canonicalizations']==0


def test_nested_bundle_validation_rejects_descriptor_relative_substitution(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,_,_,packet,_,_=_closed(tmp_path); rollback=Path(packet.packet_root)/closure.ROLLBACK_PATH; replacement=rollback.with_name('rollback.original'); before=_packet_snapshot(rollback)
    def hook(event:str,path:Path)->None:
        if event=='lifecycle_validation_after_nested_execution': rollback.rename(replacement); rollback.mkdir(); (rollback/'sentinel').write_bytes(b'keep')
    monkeypatch.setattr(closure,'_publication_hook',hook); result=validate_lifecycle_closure(packet.packet_root)
    assert 'nested_rollback_root_identity_changed' in result.findings and _packet_snapshot(replacement)==before and (rollback/'sentinel').read_bytes()==b'keep' and 'nested_rollback:' not in ' '.join(result.findings)


def test_latest_replay_rejects_publication_root_replacement_after_open(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,_,_,packet,_,_=_closed(tmp_path); root=Path(packet.packet_root).parent; old=root.with_name(root.name+'.old')
    def hook(event:str,path:Path)->None:
        if event=='lifecycle_latest_after_publication_root_open': root.rename(old); root.mkdir(); (root/'sentinel').write_bytes(b'keep')
    monkeypatch.setattr(closure,'_publication_hook',hook); result=load_latest_summary(root)
    assert 'lifecycle_latest_publication_root_identity_changed' in result.findings and (root/'sentinel').read_bytes()==b'keep'


def _latest_pointer_mutation(tmp_path:Path,monkeypatch:pytest.MonkeyPatch,metadata:bool)->tuple[Any,Path,bytes,int]:
    _,_,_,packet,_,_=_closed(tmp_path); root=Path(packet.packet_root).parent; pointer=root/'latest.json'
    before=pointer.read_bytes(); inode=pointer.stat().st_ino
    def hook(event:str,path:Path)->None:
        if event=='lifecycle_latest_after_pointer_read':
            if metadata: pointer.chmod(0o640)
            else: pointer.rename(root/'latest.original'); pointer.write_bytes((root/'latest.original').read_bytes())
    monkeypatch.setattr(closure,'_publication_hook',hook); return load_latest_summary(root),root,before,inode


def test_latest_replay_rejects_pointer_substitution_after_read(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    result,root,before,inode=_latest_pointer_mutation(tmp_path,monkeypatch,False)
    assert 'lifecycle_latest_pointer_identity_changed' in result.findings and (root/'latest.original').read_bytes()==before and (root/'latest.original').stat().st_ino==inode and (root/'latest.json').read_bytes()==before and (root/'latest.json').stat().st_ino!=inode

def test_latest_replay_rejects_pointer_metadata_change_after_read(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    result,root,before,inode=_latest_pointer_mutation(tmp_path,monkeypatch,True)
    assert 'lifecycle_latest_pointer_metadata_changed' in result.findings and (root/'latest.json').read_bytes()==before and (root/'latest.json').stat().st_ino==inode


def test_latest_replay_rejects_packet_entry_substitution_before_open(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,_,_,packet,_,_=_closed(tmp_path); selected=Path(packet.packet_root); old=selected.with_name(selected.name+'.old'); before=_packet_snapshot(selected)
    def hook(event:str,path:Path)->None:
        if event=='lifecycle_latest_before_packet_open': selected.rename(old); selected.mkdir(); (selected/'sentinel').write_bytes(b'keep')
    monkeypatch.setattr(closure,'_publication_hook',hook); result=load_latest_summary(selected.parent)
    assert 'lifecycle_latest_packet_identity_changed' in result.findings and _packet_snapshot(old)==before and (selected/'sentinel').read_bytes()==b'keep' and result.records=={}


def test_latest_replay_rejects_packet_mutation_during_validation(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,_,_,packet,_,_=_closed(tmp_path); root=Path(packet.packet_root); pointer=(root.parent/'latest.json').read_bytes(); summary=(root/'summary.json').read_bytes()
    def hook(event:str,path:Path)->None:
        if event=='lifecycle_validation_after_initial_snapshot': (root/'injected').write_bytes(b'keep')
    monkeypatch.setattr(closure,'_publication_hook',hook); result=load_latest_summary(root.parent)
    assert 'lifecycle_latest_packet_membership_changed' in result.findings and not result.status.endswith('_valid') and (root/'injected').read_bytes()==b'keep' and (root.parent/'latest.json').read_bytes()==pointer and (root/'summary.json').read_bytes()==summary


def test_latest_replay_rejects_unsafe_closure_id_before_packet_lookup(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,_,_,packet,_,_=_closed(tmp_path); root=Path(packet.packet_root).parent; canonical=json.loads((root/'latest.json').read_text()); sentinel=root.parent/'outside'; sentinel.write_bytes(b'outside evidence\n')
    unsafe:list[Any]=['../outside','/absolute','.','', '..','hldlc-'+'a'*23,'hldlc-'+'a'*25,'hldlc-ABCDEFABCDEFABCDEFABCDEF','hldlc-safe/child','hldlc-safe\\child','C:\\outside',None,7,[],{}]
    original_stat=os.stat; original_open=os.open; original_directory=closure._open_directory; attempts=[]
    def selected(value:Any,path:Any)->bool: return path is value or (isinstance(value,str) and path==value)
    for value in unsafe:
        pointer={**canonical,'closure_id':value}; pointer['digest']=digest_record(pointer); (root/'latest.json').write_text(_canon(pointer)+'\n')
        def guarded_stat(path:Any,*a:Any,_value:Any=value,**k:Any)->Any:
            if selected(_value,path) and k.get('dir_fd') is not None: attempts.append(('stat',_value))
            return original_stat(path,*a,**k)
        def guarded_open(path:Any,*a:Any,_value:Any=value,**k:Any)->Any:
            if selected(_value,path) and k.get('dir_fd') is not None: attempts.append(('open',_value))
            return original_open(path,*a,**k)
        def guarded_directory(path:Any,*a:Any,_value:Any=value,**k:Any)->Any:
            if selected(_value,path) and k.get('dir_fd') is not None: attempts.append(('directory',_value))
            return original_directory(path,*a,**k)
        with monkeypatch.context() as patch:
            patch.setattr(os,'stat',guarded_stat); patch.setattr(os,'open',guarded_open); patch.setattr(closure,'_open_directory',guarded_directory)
            assert load_latest_summary(root).findings==('lifecycle_latest_closure_id_unsafe',)
        assert sentinel.read_bytes()==b'outside evidence\n'
    assert len(unsafe)==15 and attempts==[]


def test_latest_replay_shared_lock_serializes_with_builder(tmp_path:Path)->None:
    _,execution,rollback,packet,_,_=_closed(tmp_path); out=Path(packet.packet_root).parent; ctx=multiprocessing.get_context('spawn'); release=ctx.Event()
    reader_result=tmp_path/'reader.json'; builder_result=tmp_path/'builder.json'; reader_parent,reader_child=ctx.Pipe(False); builder_parent,builder_child=ctx.Pipe(False)
    packet_before=_packet_snapshot(Path(packet.packet_root)); pointer_before=(out/'latest.json').read_bytes(); pointer_identity=(out/'latest.json').stat().st_dev,(out/'latest.json').stat().st_ino
    reader=ctx.Process(target=_latest_reader_worker,args=(str(out),str(reader_result),reader_child,release)); reader.start()
    assert reader_parent.poll(20); reader_event=reader_parent.recv(); assert reader_event=={'event':'reader_lock_held','pid':reader.pid}
    config=_process_config(execution,rollback,out,builder_result,report_lock_events=True); builder=ctx.Process(target=_process_worker,args=(config,None,builder_child,None)); builder.start()
    assert builder_parent.poll(20); waiting=builder_parent.recv(); assert waiting=={'event':'lock_waiting','pid':builder.pid,'path':str(out)}
    assert reader.pid!=builder.pid and reader.is_alive() and builder.is_alive() and not builder_parent.poll(0.25) and not builder_result.exists()
    assert packet_before==_packet_snapshot(Path(packet.packet_root)) and pointer_before==(out/'latest.json').read_bytes() and pointer_identity==((out/'latest.json').stat().st_dev,(out/'latest.json').stat().st_ino)
    release.set(); _join(reader); assert builder_parent.poll(20); entered=builder_parent.recv(); assert entered['event']=='locked_enter' and entered['pid']==builder.pid; _join(builder)
    reader_value=json.loads(reader_result.read_text()); builder_value=json.loads(builder_result.read_text())
    assert reader_value['publication_posture']=='latest_replay' and reader_value['status'].endswith('_valid')
    assert builder_value['status'].endswith('_valid') and builder_value['replayed'] and builder_value['publication_posture'] in {'replayed','recovered'}
    assert validate_lifecycle_closure(packet.packet_root).status.endswith('_valid') and load_latest_summary(out).status.endswith('_valid')
    assert len([p for p in out.iterdir() if p.is_dir()])==1 and len(list(out.glob('latest.json')))==1 and not list(out.glob('.hldlc-*')) and not list(out.glob('.latest-*'))
    assert packet_before==_packet_snapshot(Path(packet.packet_root)) and pointer_before==(out/'latest.json').read_bytes()


def test_latest_replay_returns_one_bound_pointer_and_packet_observation(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    _,_,_,packet,_,_=_closed(tmp_path); events=[]
    monkeypatch.setattr(closure,'_custody_observation_hook',lambda event,payload:events.append((event,dict(payload))))
    result=load_latest_summary(Path(packet.packet_root).parent)
    expected=['latest_publication_root_bound','latest_pointer_custody_acquired','latest_packet_entry_bound','latest_packet_initial_snapshot','latest_packet_semantic_validation_complete','latest_packet_terminal_snapshot','latest_pointer_terminal_rebound','latest_packet_terminal_rebound','latest_transaction_complete']
    assert [event for event,_ in events]==expected and all(sum(event==wanted for event,_ in events)==1 for wanted in expected)
    values={event:payload for event,payload in events}; root=Path(packet.packet_root).parent
    assert values['latest_publication_root_bound']['identity']==closure._metadata(os.stat(root,follow_symlinks=False))
    assert values['latest_pointer_custody_acquired']==values['latest_pointer_terminal_rebound']
    assert values['latest_packet_entry_bound']['identity']==values['latest_packet_terminal_rebound']['identity']
    assert values['latest_packet_initial_snapshot']['packet_snapshot_digest']==values['latest_packet_terminal_snapshot']['packet_snapshot_digest']
    assert values['latest_packet_semantic_validation_complete']['semantic_packet_digest']==values['latest_packet_entry_bound']['pointer_packet_digest']
    assert result.status.endswith('_valid') and result.replayed and result.publication_posture=='latest_replay' and result.packet_root==packet.packet_root and not result.packet_root.startswith('/proc/self/fd/')
    assert not any(any(word in event for word in ('repair','cleanup','pointer_publication','packet_mutation')) for event,_ in events)


def test_build_source_validation_uses_unresolved_descriptor_alias(tmp_path:Path,monkeypatch:pytest.MonkeyPatch)->None:
    execution,rollback,_,_,out=_race_inputs(tmp_path); observed=_guard_descriptor_adapter(monkeypatch); result=_rebuild(execution,rollback,out)
    assert result.status.endswith('_valid') and observed['uses']>0 and observed['identity_checks']>=observed['uses']*2 and observed['canonicalizations']==0 and '/proc/self/fd/' not in result.packet_root
