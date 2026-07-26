"""Operator-confirmed, durable-at-most-once local diagnostic transaction."""
from __future__ import annotations

import fcntl, hashlib, json, os, tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from sentientos.builtin_runner_transaction_orchestrator import run_builtin_runner_transaction_wing
from sentientos.host_fulfillment_executor_readiness_runtime import validate_current_authority_snapshot
from sentientos.host_local_diagnostic_execution_source_runtime import (
    SCHEMA_VERSION as SOURCE_SCHEMA_VERSION, _canon, _dict, _overlap, _path_findings,
    _raw_sha, _sha, digest_record, load_persisted_execution_source_bundle,
    validate_execution_source_records,
)
from sentientos.local_authorization_grant import local_authorization_grant_verification_digest, validate_local_authorization_grant_verification

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
    value["confirmation_challenge_digest"]=_sha(value); return value

def _authority(source:Mapping[str,Any], snapshot:Mapping[str,Any], verification:Mapping[str,Any])->tuple[dict[str,Any],list[str]]:
    posture=source["current_authority_posture"]; gid,gd=posture["grant_id"],posture["grant_digest"]; findings=[]
    current,sf=validate_current_authority_snapshot(snapshot,grant_id=gid,grant_digest=gd); findings += list(sf)
    vv=validate_local_authorization_grant_verification(verification); findings += list(vv.findings)
    if verification.get("digest") != local_authorization_grant_verification_digest(verification): findings.append("verification_digest_mismatch")
    if verification.get("grant_id") != gid or verification.get("grant_digest") not in (None,gd): findings.append("grant_substitution")
    if verification.get("missing_labels"): findings.append("missing_scope")
    expiry=_dict(current.get("expiry")); revocations=tuple(current.get("revocations",()))
    if not current.get("no_revocation_digest") and not revocations: findings.append("revocation_evidence_omitted")
    if revocations: findings.append("grant_revoked")
    if expiry.get("expiry_status") not in ("local_authorization_expiry_valid","local_authorization_expiry_valid_with_conditions"): findings.append("grant_not_current")
    return {"schema_version":SCHEMA_VERSION,"grant_id":gid,"grant_digest":gd,"snapshot_digest":snapshot.get("digest"),"verification_digest":verification.get("digest"),"expiry":expiry,"revocations":revocations,"status":"fresh_current_authority_valid" if not findings else "fresh_current_authority_blocked",**NO_BROAD_AUTHORITY}, findings

class HostLocalDiagnosticExecutionRuntimeCoordinator:
    def __init__(self, runner:Callable[...,Any]=run_builtin_runner_transaction_wing, failure_hook:Callable[[str],None]|None=None): self.runner=runner; self.failure_hook=failure_hook
    def preflight(self, *, execution_source_bundle_root:str|Path, expected_source_bundle_digest:str, current_snapshot:Mapping[str,Any], current_verification:Mapping[str,Any], execution_time:str)->ExecutionOutcome:
        v=load_persisted_execution_source_bundle(execution_source_bundle_root,expected_bundle_digest=expected_source_bundle_digest)
        if not v.ok or not v.evaluation: return ExecutionOutcome("blocked_host_local_diagnostic_execution_preflight",v.findings,{})
        source=v.evaluation.records
        if source.get("runtime_request",{}).get("schema_version") != SOURCE_SCHEMA_VERSION: return ExecutionOutcome("blocked_host_local_diagnostic_execution_preflight",("source_v2_required",),{})
        authority, findings=_authority(source,current_snapshot,current_verification)
        challenge=_challenge(source,expected_source_bundle_digest,current_snapshot,current_verification,execution_time)
        return ExecutionOutcome("host_local_diagnostic_execution_preflight_ready" if not findings else "blocked_host_local_diagnostic_execution_preflight",tuple(sorted(set(findings))),{"confirmation_challenge":challenge,"current_authority_validation":authority,"source_records":source})
    def execute(self, *, execution_source_bundle_root:str|Path, expected_source_bundle_digest:str, current_snapshot:Mapping[str,Any], current_verification:Mapping[str,Any], execution_time:str, output_root:str|Path, confirm_local_diagnostic_write:bool, confirm_source_bundle_digest:str, confirm_effect_output_dir:str, confirmation_challenge_digest:str, correlation_id:str|None=None)->ExecutionOutcome:
        pre=self.preflight(execution_source_bundle_root=execution_source_bundle_root,expected_source_bundle_digest=expected_source_bundle_digest,current_snapshot=current_snapshot,current_verification=current_verification,execution_time=execution_time)
        if pre.status != "host_local_diagnostic_execution_preflight_ready": return pre
        challenge=_dict(pre.records["confirmation_challenge"]); target=Path(challenge["effect_output_directory"])
        confirmations=(confirm_local_diagnostic_write,confirm_source_bundle_digest==challenge["execution_source_bundle_digest"],str(Path(confirm_effect_output_dir).resolve(strict=False))==str(target),confirmation_challenge_digest==challenge["confirmation_challenge_digest"])
        if not all(confirmations): return ExecutionOutcome("blocked_host_local_diagnostic_execution_confirmation",("operator_confirmation_missing_or_mismatched",),{})
        out,of=_path_findings(output_root,may_not_exist=True); target,tf=_path_findings(target,may_not_exist=True); source_root=Path(execution_source_bundle_root).resolve()
        findings=of+tf
        if _overlap(out,target) or _overlap(out,source_root) or _overlap(target,source_root): findings.append("execution_roots_overlap")
        for name in TARGET_FILES:
            if (target/name).exists() or (target/name).is_symlink(): findings.append("runtime_owned_target_exists:"+name)
        if findings: return ExecutionOutcome("blocked_host_local_diagnostic_execution_target",tuple(sorted(set(findings))),{})
        identity={"source_bundle_digest":expected_source_bundle_digest,"source_request_id":challenge["source_request_id"],"source_request_digest":challenge["source_request_digest"],"snapshot_digest":challenge["current_snapshot_digest"],"verification_digest":challenge["current_verification_digest"],"grant_id":challenge["grant_id"],"grant_digest":challenge["grant_digest"],"target_path":str(target),"artifact_name":ARTIFACT_NAME,"ledger_path":challenge["ledger_output_path"],"transaction_mode":"diagnostic_write_with_ledger","execution_time":execution_time,"operator_confirmation_digest":confirmation_challenge_digest,"correlation_id":correlation_id or challenge["source_request_id"]}
        execution_id="hlder-"+hashlib.sha256(_canon(identity).encode()).hexdigest()[:24]
        out.mkdir(parents=True,exist_ok=True)
        with (out/".execution.lock").open("a+b") as lock:
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
            existing=out/execution_id
            if existing.exists():
                loaded=validate_persisted_execution_bundle(existing,expected_source_bundle_digest=expected_source_bundle_digest,correlation_id=identity["correlation_id"])
                if loaded.status.endswith("completed"): return ExecutionOutcome(loaded.status,loaded.findings,loaded.records,loaded.bundle_root,0,True)
                return self._reconcile(existing,target,identity,pre.records)
            target.mkdir(parents=True,exist_ok=True)
            siblings={p.name:_raw_sha(p.read_bytes()) for p in target.iterdir() if p.is_file()}
            intent_dir=out/(execution_id+".intent"); intent_dir.mkdir()
            history: list[dict[str, Any]]=[]
            self._state(intent_dir,history,"prepared",identity)
            if self.failure_hook: self.failure_hook("prepared")
            _,again=_authority(pre.records["source_records"],current_snapshot,current_verification)
            if again: return ExecutionOutcome("blocked_host_local_diagnostic_execution_authority",tuple(again),{})
            self._state(intent_dir,history,"invocation_committed",identity)
            if self.failure_hook: self.failure_hook("invocation_committed")
            result=self.runner(output_dir=target,artifact_name=ARTIFACT_NAME,transaction_mode="diagnostic_write_with_ledger",ledger_output_path=target/LEDGER_NAME,force=False,dry_run=False,created_at=execution_time)
            self._state(intent_dir,history,"runner_returned",identity)
            if self.failure_hook: self.failure_hook("runner_returned")
            records=self._records(pre.records,current_snapshot,current_verification,challenge,identity,history,result,target,siblings)
            self._state(intent_dir,history,"observation_persisted",identity); records["execution_intent_history"]=history
            bundle=self._persist(out,execution_id,records)
            self._state(intent_dir,history,"finalized",identity)
            return ExecutionOutcome("host_local_diagnostic_execution_completed",(),records,str(bundle),1)
    def _state(self,root:Path,history:list[dict[str,Any]],state:str,identity:Mapping[str,Any])->None:
        previous=history[-1]["digest"] if history else ""
        record={"schema_version":SCHEMA_VERSION,"state":state,"identity":dict(identity),"previous_state_digest":previous}; record["digest"]=digest_record(record); history.append(record)
        p=root/(f"{len(history):02d}_{state}.json"); p.write_text(_canon(record)+"\n"); p.open("rb").read(); fd=os.open(p,os.O_RDONLY); os.fsync(fd); os.close(fd)
    def _records(self,pre:Mapping[str,Any],snapshot:Mapping[str,Any],verification:Mapping[str,Any],challenge:Mapping[str,Any],identity:Mapping[str,Any],history:list[dict[str,Any]],result:Any,target:Path,siblings:Mapping[str,str])->dict[str,Any]:
        tx=result._asdict() if hasattr(result,"_asdict") else _dict(result)
        tx={k:(_dict(v) if v is not None else None) for k,v in tx.items()}
        snapshots={name:{"relative_filename":name,"path":str(target/name),"size_bytes":len((target/name).read_bytes()),"sha256":_raw_sha((target/name).read_bytes()),"bytes_hex":(target/name).read_bytes().hex()} for name in TARGET_FILES}
        after={p.name:_raw_sha(p.read_bytes()) for p in target.iterdir() if p.is_file() and p.name not in TARGET_FILES}
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
        bundle=out/execution_id; os.replace(tmp,bundle); _atomic_json(out/"latest.json",{"execution_id":execution_id,"bundle_digest":manifest["bundle_digest"]}); _atomic_json(out/"replay_index.json",{records["runtime_request"]["correlation_id"]:{"execution_id":execution_id,"bundle_digest":manifest["bundle_digest"]}}); return bundle
    def _reconcile(self,intent:Path,target:Path,identity:Mapping[str,Any],pre:Mapping[str,Any])->ExecutionOutcome:
        states=sorted(intent.glob("*.json")); names={p.stem.split("_",1)[1] for p in states}
        present=[name for name in TARGET_FILES if (target/name).is_file()]
        if "invocation_committed" in names:
            return ExecutionOutcome("host_local_diagnostic_execution_partial" if present else "host_local_diagnostic_execution_ambiguous_invocation",("runner_retry_forbidden",),{"present_target_files":present},runner_call_count=0)
        return ExecutionOutcome("blocked_host_local_diagnostic_execution_retry",("prepared_retry_requires_original_confirmation",),{},runner_call_count=0)

def _atomic_json(path:Path,value:Any)->None:
    fd,name=tempfile.mkstemp(dir=path.parent,prefix=".tmp-"); os.close(fd); Path(name).write_text(_canon(value)+"\n"); os.replace(name,path)

def validate_persisted_execution_bundle(bundle_root:str|Path, *, expected_final_bundle_digest:str|None=None, expected_request_id:str|None=None, expected_request_digest:str|None=None, expected_source_bundle_digest:str|None=None, correlation_id:str|None=None)->ExecutionOutcome:
    root,findings=_path_findings(bundle_root)
    records={}
    try:
        manifest=json.loads((root/"bundle_manifest.json").read_text()); claimed=manifest.get("bundle_digest"); check=dict(manifest); check.pop("bundle_digest",None)
        if claimed!=_sha(check) or (expected_final_bundle_digest and claimed!=expected_final_bundle_digest): findings.append("bundle_digest_mismatch")
        for e in manifest.get("files",[]):
            p=root/str(e.get("relative_filename","")); raw=p.read_bytes()
            if len(raw)!=e.get("size_bytes") or _raw_sha(raw)!=e.get("sha256"): findings.append("manifest_file_mismatch")
        for p in root.glob("*.json"):
            if p.name not in ("bundle_manifest.json","content_manifest.json","runtime_receipt.json","summary.json"): records[p.stem]=json.loads(p.read_text())
    except Exception as exc: findings.append("bundle_decode_failed:"+type(exc).__name__)
    req=records.get("runtime_request",{}); source=records.get("source_records",{})
    findings += list(validate_execution_source_records(source))
    if expected_request_id and req.get("source_request_id")!=expected_request_id: findings.append("request_id_mismatch")
    if expected_request_digest and req.get("source_request_digest")!=expected_request_digest: findings.append("request_digest_mismatch")
    if expected_source_bundle_digest and req.get("source_bundle_digest")!=expected_source_bundle_digest: findings.append("source_bundle_digest_mismatch")
    if correlation_id and req.get("correlation_id")!=correlation_id: findings.append("correlation_id_mismatch")
    status="host_local_diagnostic_execution_completed" if not findings else "host_local_diagnostic_execution_bundle_invalid"
    return ExecutionOutcome(status,tuple(sorted(set(findings))),records,str(root),0,True)

def validate_live_target(bundle_root:str|Path)->ExecutionOutcome:
    loaded=validate_persisted_execution_bundle(bundle_root)
    findings=list(loaded.findings)
    for snap in loaded.records.get("target_snapshots",{}).values():
        p=Path(snap["path"])
        if not p.is_file() or _raw_sha(p.read_bytes())!=snap["sha256"]: findings.append("live_target_mismatch:"+str(snap["relative_filename"]))
    return ExecutionOutcome("host_local_diagnostic_execution_live_target_valid" if not findings else "host_local_diagnostic_execution_live_target_invalid",tuple(sorted(set(findings))),loaded.records,loaded.bundle_root,0,True)
