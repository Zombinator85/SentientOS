"""Operator-confirmed, durable-at-most-once local diagnostic transaction."""
from __future__ import annotations

import fcntl, hashlib, json, os, tempfile
from datetime import datetime, timezone
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from sentientos.builtin_runner_transaction_orchestrator import (
    run_builtin_runner_transaction_wing, validate_builtin_runner_transaction_plan,
    validate_builtin_runner_transaction_execution_request, validate_builtin_runner_transaction_result,
    validate_builtin_runner_transaction_receipt, validate_builtin_runner_transaction_closure_report,
)
from sentientos.host_fulfillment_executor_readiness_runtime import validate_current_authority_snapshot
from sentientos.host_local_diagnostic_execution_source_runtime import (
    SCHEMA_VERSION as SOURCE_SCHEMA_VERSION, _canon, _dict, _overlap, _path_findings,
    _raw_sha, _sha, digest_record, load_persisted_execution_source_bundle,
    validate_execution_source_records,
)
from sentientos.local_authorization_grant import local_authorization_grant_verification_digest, validate_local_authorization_grant_verification
from sentientos.local_diagnostic_effect import (
    validate_local_diagnostic_effect_receipt,
    validate_local_diagnostic_postcondition_check, validate_local_diagnostic_production_audit_receipt,
    validate_local_diagnostic_rollback_plan,
)
from sentientos.local_effect_transaction_ledger import validate_local_effect_transaction_ledger, validate_local_effect_transaction_lifecycle_report

SCHEMA_VERSION = "host_local_diagnostic_execution_runtime.v1"
ARTIFACT_NAME = "sentientos_local_diagnostic_effect.json"
LEDGER_NAME = "sentientos_local_diagnostic_transaction_ledger.json"
TARGET_FILES = (ARTIFACT_NAME, "effect_receipt.json", "postcondition_check.json", "production_audit.json", "rollback_plan.json", LEDGER_NAME)
FORBIDDEN_FLAGS = ("general_filesystem_access","unrelated_file_write_performed","unrelated_file_delete_performed","cleanup_performed","recursive_delete_performed","wildcard_delete_performed","subprocess_execution_performed","shell_execution_performed","network_performed","provider_invocation_performed","prompt_assembly_performed","service_action_performed","process_kill_performed","package_action_performed","driver_action_performed","power_action_performed","thermal_actuation_performed","fan_pwm_write_performed","hardware_control_performed","os_backend_invoked","remote_execution_performed","control_plane_admission_execution_performed")
NO_BROAD_AUTHORITY = {name: False for name in FORBIDDEN_FLAGS}

@dataclass(frozen=True)
class ExecutionOutcome:
    status: str
    findings: tuple[str, ...]
    records: Mapping[str, Any]
    bundle_root: str = ""
    runner_call_count: int = 0
    replayed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

def _challenge(source: Mapping[str,Any], source_digest:str, snapshot:Mapping[str,Any], verification:Mapping[str,Any], execution_time:str)->dict[str,Any]:
    req=source["runtime_request"]; posture=source["current_authority_posture"]; target=source["target_specification"]
    value={"schema_version":SCHEMA_VERSION,"artifact_kind":"host_local_diagnostic_execution_confirmation_challenge","execution_source_bundle_digest":source_digest,"source_request_id":req["request_id"],"source_request_digest":req["digest"],"grant_id":posture["grant_id"],"grant_digest":posture["grant_digest"],"current_snapshot_digest":snapshot.get("digest"),"current_verification_digest":verification.get("digest"),"effect_output_directory":target["output_directory"],"artifact_name":ARTIFACT_NAME,"transaction_mode":"diagnostic_write_with_ledger","ledger_output_path":str(Path(target["output_directory"])/LEDGER_NAME),"execution_time":execution_time,**NO_BROAD_AUTHORITY}
    value["confirmation_challenge_id"]="hlder-challenge-"+hashlib.sha256(_canon(value).encode()).hexdigest()[:24]
    value["confirmation_challenge_digest"]=digest_record(value); return value

def _time(value:Any)->datetime:
    text=str(value).replace("Z","+00:00")
    parsed=datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

def validate_fresh_execution_authority(source:Mapping[str,Any], snapshot:Mapping[str,Any], verification:Mapping[str,Any], execution_time:str)->tuple[dict[str,Any],list[str]]:
    posture=source["current_authority_posture"]; gid,gd=posture["grant_id"],posture["grant_digest"]; findings=[]
    current,sf=validate_current_authority_snapshot(snapshot,grant_id=gid,grant_digest=gd); findings += list(sf)
    vv=validate_local_authorization_grant_verification(verification); findings += list(vv.findings)
    if verification.get("digest") != local_authorization_grant_verification_digest(verification): findings.append("verification_digest_mismatch")
    if verification.get("grant_id") != gid or (verification.get("grant_digest") is not None and verification.get("grant_digest") != gd): findings.append("grant_substitution")
    grants=[_dict(x) for x in snapshot.get("grants",()) if _dict(x).get("grant_id")==gid]
    if current.get("grant") and not grants: grants=[_dict(current["grant"])]
    if not grants or any(g.get("digest")!=gd for g in grants): findings.append("current_grant_bytes_mismatch")
    if len({_canon(g) for g in grants})>1: findings.append("conflicting_duplicate_grant")
    issues=[_dict(x) for x in current.get("issues",snapshot.get("issue_receipts",())) if _dict(x).get("grant_id")==gid and _dict(x).get("grant_digest")==gd]
    if not issues: findings.append("matching_issue_receipt_missing")
    required=set(_dict(source.get("readiness_records",{})).get("current_grant_evidence",{}).get("requested_scope_labels",()))
    checked=set(verification.get("checked_scope_labels",()))
    if verification.get("missing_labels") or required-checked: findings.append("missing_scope")
    expiry=_dict(current.get("expiry")); revocations=tuple(current.get("revocations",()))
    if not current.get("no_revocation_digest") and not revocations: findings.append("revocation_evidence_omitted")
    if revocations: findings.append("grant_revoked")
    if expiry.get("expiry_status") not in ("local_authorization_expiry_not_expired","local_authorization_expiry_valid","local_authorization_expiry_valid_with_conditions"): findings.append("grant_not_current")
    try:
        instant=_time(execution_time)
        if _time(verification.get("checked_time_label"))>instant: findings.append("verification_after_execution")
        if _time(expiry.get("evaluated_at"))>instant: findings.append("expiry_evaluation_after_execution")
        grant=grants[0] if grants else {}
        bounds=list(grant.get("granted_time_bounds",grant.get("time_bounds",grant.get("grant_time_bounds",()))))
        nb=next((x.split(":",1)[1] for x in bounds if str(x).startswith("not_before:")),"")
        na=next((x.split(":",1)[1] for x in bounds if str(x).startswith("not_after:")),"")
        exp=str(grant.get("expiry_label","")).removeprefix("expires:")
        if nb and instant<_time(nb): findings.append("grant_not_yet_valid")
        if (na and instant>_time(na)) or (exp and instant>_time(exp)): findings.append("grant_expired")
    except (ValueError,TypeError): findings.append("authority_time_invalid")
    record={"schema_version":SCHEMA_VERSION,"artifact_kind":"fresh_execution_authority_validation","grant_id":gid,"grant_digest":gd,"snapshot_id":snapshot.get("snapshot_id"),"snapshot_digest":snapshot.get("digest"),"verification_id":verification.get("verification_id"),"verification_digest":verification.get("digest"),"execution_time":execution_time,"required_scope_labels":sorted(required),"expiry":expiry,"revocations":revocations,"status":"fresh_current_authority_valid" if not findings else "fresh_current_authority_blocked",**NO_BROAD_AUTHORITY}
    record["authority_validation_id"]="hlder-authority-"+hashlib.sha256(_canon(record).encode()).hexdigest()[:24]; record["digest"]=digest_record(record)
    return record, findings

class HostLocalDiagnosticExecutionRuntimeCoordinator:
    def __init__(self, runner:Callable[...,Any]=run_builtin_runner_transaction_wing, failure_hook:Callable[[str],None]|None=None): self.runner=runner; self.failure_hook=failure_hook
    def preflight(self, *, execution_source_bundle_root:str|Path, expected_source_bundle_digest:str, current_snapshot:Mapping[str,Any], current_verification:Mapping[str,Any], execution_time:str)->ExecutionOutcome:
        v=load_persisted_execution_source_bundle(execution_source_bundle_root,expected_bundle_digest=expected_source_bundle_digest)
        if not v.ok or not v.evaluation: return ExecutionOutcome("blocked_host_local_diagnostic_execution_preflight",v.findings,{})
        source=v.evaluation.records
        if source.get("runtime_request",{}).get("schema_version") != SOURCE_SCHEMA_VERSION: return ExecutionOutcome("blocked_host_local_diagnostic_execution_preflight",("source_v2_required",),{})
        authority, findings=validate_fresh_execution_authority(source,current_snapshot,current_verification,execution_time)
        challenge=_challenge(source,expected_source_bundle_digest,current_snapshot,current_verification,execution_time)
        return ExecutionOutcome("host_local_diagnostic_execution_preflight_ready" if not findings else "blocked_host_local_diagnostic_execution_preflight",tuple(sorted(set(findings))),{"confirmation_challenge":challenge,"current_authority_validation":authority,"source_records":source})
    def execute(self, *, execution_source_bundle_root:str|Path, expected_source_bundle_digest:str, current_snapshot:Mapping[str,Any], current_verification:Mapping[str,Any], execution_time:str, output_root:str|Path, confirm_local_diagnostic_write:bool, confirm_source_bundle_digest:str, confirm_effect_output_dir:str, confirmation_challenge_digest:str, correlation_id:str|None=None)->ExecutionOutcome:
        out=Path(output_root).resolve(strict=False)
        if correlation_id and (out/"replay_index.json").is_file():
            try:
                pointer=json.loads((out/"replay_index.json").read_text()).get(correlation_id)
                if pointer:
                    loaded=validate_persisted_execution_bundle(out/pointer["execution_id"],expected_final_bundle_digest=pointer.get("bundle_digest"),expected_source_bundle_digest=expected_source_bundle_digest,correlation_id=correlation_id)
                    if loaded.status=="host_local_diagnostic_execution_completed": return ExecutionOutcome(loaded.status,loaded.findings,loaded.records,loaded.bundle_root,0,True)
                    return ExecutionOutcome("host_local_diagnostic_execution_bundle_invalid",loaded.findings,loaded.records,loaded.bundle_root)
            except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError):
                return ExecutionOutcome("host_local_diagnostic_execution_bundle_invalid",("replay_index_invalid",),{})
        pre=self.preflight(execution_source_bundle_root=execution_source_bundle_root,expected_source_bundle_digest=expected_source_bundle_digest,current_snapshot=current_snapshot,current_verification=current_verification,execution_time=execution_time)
        if pre.status != "host_local_diagnostic_execution_preflight_ready": return pre
        challenge=_dict(pre.records["confirmation_challenge"]); target=Path(challenge["effect_output_directory"])
        confirmations=(confirm_local_diagnostic_write,confirm_source_bundle_digest==challenge["execution_source_bundle_digest"],str(Path(confirm_effect_output_dir).resolve(strict=False))==str(target),confirmation_challenge_digest==challenge["confirmation_challenge_digest"])
        if not all(confirmations): return ExecutionOutcome("blocked_host_local_diagnostic_execution_confirmation",("operator_confirmation_missing_or_mismatched",),{})
        out,of=_path_findings(output_root,may_not_exist=True); target,tf=_path_findings(target,may_not_exist=True); source_root=Path(execution_source_bundle_root).resolve()
        findings=of+tf
        if _overlap(out,target) or _overlap(out,source_root) or _overlap(target,source_root): findings.append("execution_roots_overlap")
        if findings: return ExecutionOutcome("blocked_host_local_diagnostic_execution_target",tuple(sorted(set(findings))),{})
        identity={"source_bundle_digest":expected_source_bundle_digest,"source_request_id":challenge["source_request_id"],"source_request_digest":challenge["source_request_digest"],"snapshot_digest":challenge["current_snapshot_digest"],"verification_digest":challenge["current_verification_digest"],"grant_id":challenge["grant_id"],"grant_digest":challenge["grant_digest"],"target_path":str(target),"artifact_name":ARTIFACT_NAME,"ledger_path":challenge["ledger_output_path"],"transaction_mode":"diagnostic_write_with_ledger","execution_time":execution_time,"operator_confirmation_digest":confirmation_challenge_digest,"correlation_id":correlation_id or challenge["source_request_id"]}
        execution_id="hlder-"+hashlib.sha256(_canon(identity).encode()).hexdigest()[:24]
        out.mkdir(parents=True,exist_ok=True)
        with (out/".execution.lock").open("a+b") as lock:
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
            existing=out/execution_id; intent_dir=out/(execution_id+".intent")
            if existing.exists():
                loaded=validate_persisted_execution_bundle(existing,expected_source_bundle_digest=expected_source_bundle_digest,correlation_id=identity["correlation_id"])
                if loaded.status=="host_local_diagnostic_execution_completed": return ExecutionOutcome(loaded.status,loaded.findings,loaded.records,loaded.bundle_root,0,True)
                return ExecutionOutcome("host_local_diagnostic_execution_bundle_invalid",loaded.findings,loaded.records,loaded.bundle_root)
            if intent_dir.exists(): return self._reconcile(intent_dir,target,identity,pre.records)
            for name in TARGET_FILES:
                if (target/name).exists() or (target/name).is_symlink():
                    return ExecutionOutcome("blocked_host_local_diagnostic_execution_target",("runtime_owned_target_exists:"+name,),{})
            siblings={p.name:{"kind":"file","size_bytes":len(p.read_bytes()),"sha256":_raw_sha(p.read_bytes())} for p in target.iterdir() if p.is_file()} if target.is_dir() else {}
            intent_dir.mkdir()
            history: list[dict[str, Any]]=[]
            self._state(intent_dir,history,"prepared",identity,{"unrelated_siblings_before":siblings})
            if self.failure_hook: self.failure_hook("prepared")
            _,again=validate_fresh_execution_authority(pre.records["source_records"],current_snapshot,current_verification,execution_time)
            if again: return ExecutionOutcome("blocked_host_local_diagnostic_execution_authority",tuple(again),{})
            target.mkdir(parents=True,exist_ok=True)
            self._state(intent_dir,history,"invocation_committed",identity)
            if self.failure_hook: self.failure_hook("invocation_committed")
            result=self.runner(output_dir=target,artifact_name=ARTIFACT_NAME,transaction_mode="diagnostic_write_with_ledger",ledger_output_path=target/LEDGER_NAME,force=False,dry_run=False,created_at=execution_time)
            tx=result._asdict() if hasattr(result,"_asdict") else _dict(result)
            self._state(intent_dir,history,"runner_returned",identity,{"transaction_records":{k:(_dict(v) if v is not None else None) for k,v in tx.items()}})
            if self.failure_hook: self.failure_hook("runner_returned")
            records=self._records(pre.records,current_snapshot,current_verification,challenge,identity,history,result,target,siblings)
            self._state(intent_dir,history,"observation_persisted",identity)
            self._state(intent_dir,history,"finalized",identity)
            records["execution_intent_history"]=list(history)
            bundle=self._persist(out,execution_id,records)
            return ExecutionOutcome("host_local_diagnostic_execution_completed",(),records,str(bundle),1)
    def _state(self,root:Path,history:list[dict[str,Any]],state:str,identity:Mapping[str,Any],evidence:Mapping[str,Any]|None=None)->None:
        previous=history[-1]["digest"] if history else ""
        record={"schema_version":SCHEMA_VERSION,"state":state,"identity":dict(identity),"previous_state_digest":previous,**dict(evidence or {})}; record["digest"]=digest_record(record); history.append(record)
        p=root/(f"{len(history):02d}_{state}.json"); p.write_text(_canon(record)+"\n"); p.open("rb").read(); fd=os.open(p,os.O_RDONLY); os.fsync(fd); os.close(fd)
    def _records(self,pre:Mapping[str,Any],snapshot:Mapping[str,Any],verification:Mapping[str,Any],challenge:Mapping[str,Any],identity:Mapping[str,Any],history:list[dict[str,Any]],result:Any,target:Path,siblings:Mapping[str,Any])->dict[str,Any]:
        tx=result._asdict() if hasattr(result,"_asdict") else _dict(result)
        tx={k:(_dict(v) if v is not None else None) for k,v in tx.items()}
        snapshots={name:{"relative_filename":name,"path":str(target/name),"size_bytes":len((target/name).read_bytes()),"sha256":_raw_sha((target/name).read_bytes()),"bytes_hex":(target/name).read_bytes().hex()} for name in TARGET_FILES}
        after={p.name:{"kind":"file","size_bytes":len(p.read_bytes()),"sha256":_raw_sha(p.read_bytes())} for p in target.iterdir() if p.is_file() and p.name not in TARGET_FILES}
        if after != dict(siblings): raise RuntimeError("unrelated sibling changed")
        confirmation={"schema_version":SCHEMA_VERSION,"operator_confirmation_present":True,"exact_diagnostic_transaction_authorized":True,"challenge_digest":challenge["confirmation_challenge_digest"],**NO_BROAD_AUTHORITY}; confirmation["digest"]=digest_record(confirmation)
        return {"runtime_request":dict(identity,schema_version=SCHEMA_VERSION),"runtime_plan":{"schema_version":SCHEMA_VERSION,"transaction_mode":"diagnostic_write_with_ledger","force":False,"rollback_execution":False},"source_records":pre["source_records"],"fresh_current_snapshot":dict(snapshot),"fresh_current_verification":dict(verification),"current_authority_validation":pre["current_authority_validation"],"operator_confirmation":confirmation,"execution_intent_history":list(history),"transaction_records":tx,"target_snapshots":snapshots,"unrelated_siblings_before":dict(siblings),"unrelated_siblings_after":after,"runtime_result":{"schema_version":SCHEMA_VERSION,"status":"host_local_diagnostic_execution_completed","operator_confirmation_present":True,"exact_diagnostic_transaction_authorized":True,"runner_invoked":True,"local_diagnostic_write_performed":True,"real_effect_performed":True,"ledger_artifact_written":True,"host_mutation_performed":True,"rollback_performed":False,**NO_BROAD_AUTHORITY}}
    def _persist(self,out:Path,execution_id:str,records:dict[str,Any])->Path:
        tmp=Path(tempfile.mkdtemp(prefix=".hlder-",dir=out)); files=[]
        for name,value in sorted(records.items()): p=tmp/(name+".json"); p.write_text(_canon(value)+"\n"); files.append(p.name)
        summary={"schema_version":SCHEMA_VERSION,"status":"host_local_diagnostic_execution_completed","execution_id":execution_id}; (tmp/"summary.json").write_text(_canon(summary)+"\n"); files.append("summary.json")
        (tmp/"README.md").write_text("# Operator-confirmed local diagnostic execution\n\nOne bounded write-with-ledger transaction; rollback remains pending.\n"); files.append("README.md")
        content={"schema_version":SCHEMA_VERSION,"artifact_kind":"host_local_diagnostic_execution_content_manifest","files":[{"relative_filename":n,"size_bytes":len((tmp/n).read_bytes()),"sha256":_raw_sha((tmp/n).read_bytes())} for n in sorted(files)]}; content["content_manifest_digest"]=_sha(content); (tmp/"content_manifest.json").write_text(_canon(content)+"\n")
        receipt={"schema_version":SCHEMA_VERSION,"execution_id":execution_id,"content_manifest_digest":content["content_manifest_digest"],"runtime_result_digest":_sha(records["runtime_result"])}; receipt["digest"]=digest_record(receipt); (tmp/"runtime_receipt.json").write_text(_canon(receipt)+"\n")
        finals=files+["content_manifest.json","runtime_receipt.json"]; manifest={"schema_version":SCHEMA_VERSION,"artifact_kind":"host_local_diagnostic_execution_bundle_manifest","files":[{"relative_filename":n,"size_bytes":len((tmp/n).read_bytes()),"sha256":_raw_sha((tmp/n).read_bytes())} for n in sorted(finals)]}; manifest["bundle_digest"]=_sha(manifest); (tmp/"bundle_manifest.json").write_text(_canon(manifest)+"\n")
        bundle=out/execution_id; os.replace(tmp,bundle)
        pointer={"execution_id":execution_id,"request_id":records["runtime_request"]["source_request_id"],"request_digest":records["runtime_request"]["source_request_digest"],"correlation_id":records["runtime_request"]["correlation_id"],"source_bundle_digest":records["runtime_request"]["source_bundle_digest"],"bundle_digest":manifest["bundle_digest"]}
        _atomic_json(out/"latest.json",pointer); index=out/"replay_index.json"; mapping=json.loads(index.read_text()) if index.exists() else {}; mapping[pointer["correlation_id"]]=pointer; _atomic_json(index,mapping); return bundle
    def _reconcile(self,intent:Path,target:Path,identity:Mapping[str,Any],pre:Mapping[str,Any])->ExecutionOutcome:
        states=sorted(intent.glob("[0-9][0-9]_*.json")); history: list[dict[str,Any]]=[]
        try:
            for p in states:
                record=json.loads(p.read_text())
                if record.get("digest")!=digest_record(record) or record.get("identity")!=dict(identity) or record.get("previous_state_digest")!=(history[-1]["digest"] if history else ""): raise ValueError("invalid intent chain")
                history.append(record)
        except Exception: return ExecutionOutcome("host_local_diagnostic_execution_intent_invalid",("intent_chain_invalid",),{},runner_call_count=0)
        names={str(r.get("state")) for r in history}
        present=[name for name in TARGET_FILES if (target/name).is_file()]
        if "runner_returned" in names and set(present)==set(TARGET_FILES):
            returned=next(r for r in history if r.get("state")=="runner_returned"); prepared=history[0]
            snapshot=pre["source_records"]["current_snapshot"]; verification=pre["source_records"]["current_verification"]
            challenge=_challenge(pre["source_records"],str(identity["source_bundle_digest"]),snapshot,verification,str(identity["execution_time"]))
            records=self._records(pre,snapshot,verification,challenge,identity,history,returned.get("transaction_records",{}),target,prepared.get("unrelated_siblings_before",{}))
            self._state(intent,history,"observation_persisted",identity); self._state(intent,history,"finalized",identity); records["execution_intent_history"]=list(history); records["runtime_result"]["runner_invoked"]=False; records["runtime_result"]["reconciled_effect_observed"]=True
            bundle=self._persist(intent.parent,intent.name.removesuffix(".intent"),records)
            return ExecutionOutcome("host_local_diagnostic_execution_completed",(),records,str(bundle),0,False)
        if "invocation_committed" in names:
            return ExecutionOutcome("host_local_diagnostic_execution_partial" if present else "host_local_diagnostic_execution_ambiguous_invocation",("runner_retry_forbidden",),{"present_target_files":present},runner_call_count=0)
        if names=={"prepared"}:
            for name in TARGET_FILES:
                if (target/name).exists() or (target/name).is_symlink(): return ExecutionOutcome("host_local_diagnostic_execution_partial",("prepared_target_precondition_changed",),{},runner_call_count=0)
            target.mkdir(parents=True,exist_ok=True)
            self._state(intent,history,"invocation_committed",identity)
            if self.failure_hook: self.failure_hook("invocation_committed")
            result=self.runner(output_dir=target,artifact_name=ARTIFACT_NAME,transaction_mode="diagnostic_write_with_ledger",ledger_output_path=target/LEDGER_NAME,force=False,dry_run=False,created_at=identity["execution_time"])
            tx=result._asdict() if hasattr(result,"_asdict") else _dict(result); self._state(intent,history,"runner_returned",identity,{"transaction_records":{k:(_dict(v) if v is not None else None) for k,v in tx.items()}})
            records=self._records(pre,pre["fresh_current_snapshot"],pre["fresh_current_verification"],_challenge(pre["source_records"],str(identity["source_bundle_digest"]),pre["fresh_current_snapshot"],pre["fresh_current_verification"],str(identity["execution_time"])),identity,history,result,target,history[0].get("unrelated_siblings_before",{}))
            self._state(intent,history,"observation_persisted",identity); self._state(intent,history,"finalized",identity); records["execution_intent_history"]=list(history); bundle=self._persist(intent.parent,intent.name.removesuffix(".intent"),records)
            return ExecutionOutcome("host_local_diagnostic_execution_completed",(),records,str(bundle),1)
        return ExecutionOutcome("host_local_diagnostic_execution_intent_invalid",("illegal_intent_state",),{},runner_call_count=0)

def _atomic_json(path:Path,value:Any)->None:
    fd,name=tempfile.mkstemp(dir=path.parent,prefix=".tmp-"); os.close(fd); Path(name).write_text(_canon(value)+"\n"); os.replace(name,path)

def validate_persisted_execution_bundle(bundle_root:str|Path, *, expected_final_bundle_digest:str|None=None, expected_request_id:str|None=None, expected_request_digest:str|None=None, expected_source_bundle_digest:str|None=None, correlation_id:str|None=None)->ExecutionOutcome:
    root,findings=_path_findings(bundle_root)
    records={}
    try:
        actual={p.name for p in root.iterdir()}
        if any(p.is_symlink() for p in root.iterdir()): findings.append("symlinked_bundle_artifact")
        manifest=json.loads((root/"bundle_manifest.json").read_text()); claimed=manifest.get("bundle_digest"); check=dict(manifest); check.pop("bundle_digest",None)
        if claimed!=_sha(check) or (expected_final_bundle_digest and claimed!=expected_final_bundle_digest): findings.append("bundle_digest_mismatch")
        entries=manifest.get("files",[]); names=[e.get("relative_filename") for e in entries]
        if len(names)!=len(set(names)) or set(names)|{"bundle_manifest.json"}!=actual: findings.append("exact_final_manifest_membership_mismatch")
        if manifest.get("schema_version")!=SCHEMA_VERSION or manifest.get("artifact_kind")!="host_local_diagnostic_execution_bundle_manifest": findings.append("final_manifest_shape_mismatch")
        for e in entries:
            fn=str(e.get("relative_filename","")); p=root/fn
            if Path(fn).name!=fn or ".." in Path(fn).parts or p.is_symlink(): findings.append("manifest_path_rejected:"+fn); continue
            raw=p.read_bytes()
            if len(raw)!=e.get("size_bytes") or _raw_sha(raw)!=e.get("sha256"): findings.append("manifest_file_mismatch")
        content=json.loads((root/"content_manifest.json").read_text()); ccheck=dict(content); cclaimed=ccheck.pop("content_manifest_digest",None)
        centries=content.get("files",[]); cnames=[e.get("relative_filename") for e in centries]
        if len(cnames)!=len(set(cnames)) or set(cnames)!=(set(names)-{"content_manifest.json","runtime_receipt.json"}): findings.append("exact_content_manifest_membership_mismatch")
        if cclaimed!=_sha(ccheck): findings.append("content_manifest_digest_mismatch")
        for e in centries:
            p=root/str(e.get("relative_filename","")); raw=p.read_bytes()
            if len(raw)!=e.get("size_bytes") or _raw_sha(raw)!=e.get("sha256"): findings.append("content_manifest_file_mismatch")
        receipt=json.loads((root/"runtime_receipt.json").read_text()); summary=json.loads((root/"summary.json").read_text())
        if receipt.get("digest")!=digest_record(receipt) or receipt.get("content_manifest_digest")!=cclaimed: findings.append("runtime_receipt_invalid")
        if summary.get("status")!="host_local_diagnostic_execution_completed": findings.append("summary_status_invalid")
        for p in root.glob("*.json"):
            if p.name not in ("bundle_manifest.json","content_manifest.json","runtime_receipt.json","summary.json"): records[p.stem]=json.loads(p.read_text())
    except Exception as exc: findings.append("bundle_decode_failed:"+type(exc).__name__)
    req=records.get("runtime_request",{}); source=records.get("source_records",{})
    findings += list(validate_execution_source_records(source))
    if expected_request_id and req.get("source_request_id")!=expected_request_id: findings.append("request_id_mismatch")
    if expected_request_digest and req.get("source_request_digest")!=expected_request_digest: findings.append("request_digest_mismatch")
    if expected_source_bundle_digest and req.get("source_bundle_digest")!=expected_source_bundle_digest: findings.append("source_bundle_digest_mismatch")
    if correlation_id and req.get("correlation_id")!=correlation_id: findings.append("correlation_id_mismatch")
    history=records.get("execution_intent_history",[]); expected_states=("prepared","invocation_committed","runner_returned","observation_persisted","finalized")
    if tuple(x.get("state") for x in history)!=expected_states: findings.append("intent_state_sequence_invalid")
    previous=""
    for state in history:
        expected_identity=dict(req); expected_identity.pop("schema_version",None)
        if state.get("previous_state_digest")!=previous or state.get("digest")!=digest_record(state) or state.get("identity")!=expected_identity: findings.append("intent_chain_invalid")
        previous=str(state.get("digest", ""))
    result=records.get("runtime_result",{})
    required_true=("operator_confirmation_present","exact_diagnostic_transaction_authorized","local_diagnostic_write_performed","real_effect_performed","ledger_artifact_written","host_mutation_performed")
    if any(result.get(k) is not True for k in required_true) or result.get("rollback_performed") is not False or any(result.get(k) is not False for k in FORBIDDEN_FLAGS): findings.append("runtime_result_flags_invalid")
    transaction=records.get("transaction_records",{})
    for name,validator in (("plan",validate_builtin_runner_transaction_plan),("request",validate_builtin_runner_transaction_execution_request),("result",validate_builtin_runner_transaction_result),("receipt",validate_builtin_runner_transaction_receipt),("closure_report",validate_builtin_runner_transaction_closure_report)):
        validation=validator(transaction.get(name,{}))
        if not validation.ok: findings.extend("transaction_"+name+":"+finding for finding in validation.findings)
    snapshots=records.get("target_snapshots",{})
    if set(snapshots)!=set(TARGET_FILES): findings.append("target_snapshot_membership_invalid")
    for name,snapshot in snapshots.items():
        try:
            raw=bytes.fromhex(str(snapshot.get("bytes_hex","")))
            if snapshot.get("relative_filename")!=name or snapshot.get("size_bytes")!=len(raw) or snapshot.get("sha256")!=_raw_sha(raw): findings.append("target_snapshot_invalid:"+name)
            decoded=json.loads(raw)
            target_validator={"effect_receipt.json":validate_local_diagnostic_effect_receipt,"postcondition_check.json":validate_local_diagnostic_postcondition_check,"production_audit.json":validate_local_diagnostic_production_audit_receipt,"rollback_plan.json":validate_local_diagnostic_rollback_plan}.get(name)
            if target_validator:
                target_validation=target_validator(decoded)
                if not target_validation.ok: findings.extend("target_record_"+name+":"+finding for finding in target_validation.findings)
            elif name==ARTIFACT_NAME and (decoded.get("effect_domain")!="diagnostics_local_file_effect" or decoded.get("diagnostic_only") is not True or decoded.get("local_only") is not True or any(decoded.get(flag) is not False for flag in ("network_performed","provider_invocation_performed","prompt_assembly_performed","subprocess_performed","shell_performed"))):
                findings.append("target_record_"+name+":artifact_shape_invalid")
            elif name==LEDGER_NAME:
                for label,value,ledger_validator in (("ledger",decoded.get("ledger",{}),validate_local_effect_transaction_ledger),("lifecycle_report",decoded.get("lifecycle_report",{}),validate_local_effect_transaction_lifecycle_report)):
                    ledger_validation=ledger_validator(value)
                    if not ledger_validation.ok: findings.extend("target_record_"+name+":"+label+":"+finding for finding in ledger_validation.findings)
        except (ValueError,json.JSONDecodeError): findings.append("target_snapshot_invalid:"+name)
    status="host_local_diagnostic_execution_completed" if not findings else "host_local_diagnostic_execution_bundle_invalid"
    return ExecutionOutcome(status,tuple(sorted(set(findings))),records,str(root),0,True)

def validate_live_target(bundle_root:str|Path)->ExecutionOutcome:
    loaded=validate_persisted_execution_bundle(bundle_root)
    findings=list(loaded.findings)
    for snap in loaded.records.get("target_snapshots",{}).values():
        p=Path(snap["path"])
        if not p.is_file() or _raw_sha(p.read_bytes())!=snap["sha256"]: findings.append("live_target_mismatch:"+str(snap["relative_filename"]))
    return ExecutionOutcome("host_local_diagnostic_execution_live_target_valid" if not findings else "host_local_diagnostic_execution_live_target_invalid",tuple(sorted(set(findings))),loaded.records,loaded.bundle_root,0,True)
