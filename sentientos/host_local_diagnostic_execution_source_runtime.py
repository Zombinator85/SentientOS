"""Strict, metadata-only custody bundle for a future diagnostic execution.

The module deliberately has no dependency on an effect, runner, control-plane,
subprocess, or network implementation.  It joins already-persisted proof and
copies only its semantic records into an independently replayable bundle.
"""
from __future__ import annotations

import fcntl, hashlib, json, os, tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from sentientos.host_real_effect_admission_runtime import validate_persisted_admission_bundle
from sentientos.host_dry_run_execution_runtime import validate_persisted_evaluation_bundle
from sentientos.dry_run_audit_closure import dry_run_audit_closure_digest
from sentientos.host_fulfillment_executor_readiness_runtime import validate_current_authority_snapshot, validate_persisted_readiness_bundle
from sentientos.local_authorization_grant import local_authorization_grant_verification_digest, validate_local_authorization_grant_verification

LEGACY_SCHEMA_VERSION = "host_local_diagnostic_execution_source_runtime.v1"
SCHEMA_VERSION = "host_local_diagnostic_execution_source_runtime.v2"
REPO_ROOT = Path(__file__).resolve().parents[1]
FALSE_FLAGS = ("authorizes_execution","runner_invoked","backend_invoked","fulfillment_performed","effect_performed","real_effect_performed","local_file_write_performed","host_mutation_performed","rollback_performed","subprocess_execution_performed","shell_execution_performed","network_performed","provider_invocation_performed","prompt_assembly_performed","service_action_performed","power_action_performed","thermal_actuation_performed","fan_pwm_write_performed","cleanup_performed","package_action_performed","driver_action_performed","hardware_action_performed")
BOUNDARY: dict[str, bool] = {"metadata_only": True, "source_custody_only": True, **{x: False for x in FALSE_FLAGS}}
TARGET = {"effect_domain":"diagnostics_local_file_effect","transaction_mode":"diagnostic_write_with_ledger","artifact_name":"sentientos_local_diagnostic_effect.json","force_overwrite":False,"rollback_execution":False}

def _canon(v: Any) -> str: return json.dumps(v, sort_keys=True, separators=(",",":"), default=str)
def _sha(v: Any) -> str: return "sha256:"+hashlib.sha256(_canon(v).encode()).hexdigest()
def _raw_sha(v: bytes) -> str: return "sha256:"+hashlib.sha256(v).hexdigest()
def _dict(v: Any) -> dict[str, Any]:
    if v is None: return {}
    if hasattr(v,"to_dict"): return dict(v.to_dict())
    if hasattr(v,"__dataclass_fields__"): return asdict(v)
    return dict(v)
def _semantic(v: Any) -> dict[str, Any]:
    d=_dict(v); d.pop("digest",None); d.pop("created_at",None); d.pop("source_bundle_root",None); return d
def digest_record(v: Any) -> str: return _sha(_semantic(v))
def _id(prefix: str, v: Any) -> str: return prefix+hashlib.sha256(_canon(v).encode()).hexdigest()[:24]

@dataclass(frozen=True)
class HostLocalDiagnosticExecutionSourceEvaluation:
    status: str; findings: tuple[str,...]; records: Mapping[str,Any]; bundle_root: str=""; replayed: bool=False
    def to_dict(self)->dict[str,Any]: return asdict(self)
@dataclass(frozen=True)
class HostLocalDiagnosticExecutionSourceValidation:
    ok: bool; findings: tuple[str,...]; evaluation: HostLocalDiagnosticExecutionSourceEvaluation|None=None; bundle_digest: str=""
    def to_dict(self)->dict[str,Any]: return {"ok":self.ok,"findings":self.findings,"bundle_digest":self.bundle_digest,"evaluation":self.evaluation.to_dict() if self.evaluation else None}

RECORD_FILES = {
 "runtime_request.json","runtime_plan.json","source_references.json","admission_records.json","closure_records.json","dry_run_records.json","readiness_records.json","current_snapshot.json","current_verification.json","current_authority_posture.json","target_specification.json","validation_findings.json","runtime_receipt.json","summary.json","README.md"
}
CONTENT_FILES=RECORD_FILES-{"runtime_receipt.json"}
FINAL_FILES=RECORD_FILES|{"content_manifest.json"}

def _path_findings(path: str|Path, *, may_not_exist: bool=False) -> tuple[Path,list[str]]:
    raw=str(path); p=Path(raw); f=[]
    if not raw.strip(): f.append("empty_path_rejected")
    if ".." in p.parts: f.append("path_traversal_rejected")
    # Walk the lexical path, before resolve(), so a symlink that is traversed by
    # the caller cannot disappear from the custody proof.
    lexical = Path(p.anchor) if p.is_absolute() else Path.cwd()
    for component in p.parts[(1 if p.is_absolute() else 0):]:
        lexical /= component
        try:
            if lexical.lstat() and lexical.is_symlink():
                f.append("symlink_path_rejected" if lexical == p else "symlink_ancestor_rejected")
                break
        except FileNotFoundError:
            pass
    q=p.resolve(strict=False)
    if q==Path(q.anchor): f.append("filesystem_root_rejected")
    try: q.relative_to(REPO_ROOT); f.append("repository_local_path_rejected")
    except ValueError: pass
    if not may_not_exist and not q.is_dir(): f.append("directory_required")
    return q,f
def _overlap(a: Path,b: Path)->bool:
    try: a.relative_to(b); return True
    except ValueError: pass
    try: b.relative_to(a); return True
    except ValueError: return False
def _positive_flags(v: Any, prefix: str="") -> list[str]:
    out=[]
    if isinstance(v,Mapping):
        for k,x in v.items():
            key=f"{prefix}.{k}" if prefix else str(k)
            if k in FALSE_FLAGS and x is not False: out.append("positive_or_missing_false_flag:"+key)
            out += _positive_flags(x,key)
    elif isinstance(v,(list,tuple)): 
        for i,x in enumerate(v): out += _positive_flags(x,f"{prefix}[{i}]")
    return out

def _chain(ad: Any, dr: Any, rd: Any, snapshot: Mapping[str,Any], verification: Mapping[str,Any]) -> tuple[dict[str,Any],list[str]]:
    a,d,r=_dict(ad),_dict(dr),_dict(rd); f=[]
    candidate=_dict(a.get("candidate")); decision=_dict(a.get("decision")); pob=_dict(a.get("plan_or_block_receipt")); ab=_dict(a.get("admission_bundle")); ar=_dict(a.get("runtime_receipt")); closure=_dict(a.get("source_closure_bundle"))
    dq=_dict(d.get("request")); drr=_dict(d.get("runtime_receipt")); dry_receipt=_dict(d.get("dry_run_receipt")); dry_req=_dict(d.get("dry_run_request"))
    rq=_dict(r.get("request")); rr=_dict(r.get("runtime_receipt")); contract=_dict(r.get("contract")); plan=_dict(r.get("dry_run_plan"))
    if ar.get("runtime_status")!="host_real_effect_admission_runtime_recorded": f.append("admission_runtime_status_mismatch")
    if candidate.get("admission_domain")!="diagnostics_real_effect_candidate": f.append("admission_domain_mismatch")
    if candidate.get("requested_implementation_tier")!="tier1_metadata_only": f.append("admission_tier_mismatch")
    if decision.get("admission_status")!="real_effect_admission_eligible_for_planning": f.append("admission_status_mismatch")
    if not pob.get("plan_id") or pob.get("receipt_id"): f.append("implementation_plan_scaffold_required")
    for key,obj in (("candidate",candidate),("decision",decision),("plan",pob)):
        ident=obj.get({"candidate":"candidate_id","decision":"decision_id","plan":"plan_id"}[key]); dig=obj.get("digest")
        if not ident or not dig or ab.get(key+"_id") != ident: f.append("admission_bundle_"+key+"_mismatch")
    if closure.get("closure_domain")!="diagnostics_dry_run_closure": f.append("closure_domain_mismatch")
    if dq.get("dry_run_domain")!="diagnostics_dry_run": f.append("dry_run_domain_mismatch")
    if dq.get("simulated_backend_class")!="diagnostic_backend_simulated": f.append("dry_run_backend_mismatch")
    if dry_receipt:
        cid=closure.get("source_dry_run_receipt_id"); cd=closure.get("source_dry_run_receipt_semantic_digest")
        if not cid or cid != dry_receipt.get("receipt_id"): f.append("closure_dry_run_receipt_id_mismatch")
        if not cd or cd != dry_run_audit_closure_digest(dry_receipt): f.append("closure_dry_run_receipt_digest_mismatch")
    for key,left,right in (("contract",dq.get("executor_contract_digest"),contract.get("digest")),("plan",dq.get("declarative_dry_run_plan_digest"),plan.get("digest")),("readiness_receipt",drr.get("readiness_runtime_receipt_digest"),rr.get("digest"))):
        if left!=right: f.append("dry_run_readiness_"+key+"_mismatch")
    route=(rq.get("requested_fulfillment_domain"),rq.get("executor_domain"),rq.get("backend_class"))
    if route != ("diagnostics_fulfillment_authorization","diagnostics_executor_contract","diagnostic_backend_future"): f.append("readiness_canonical_route_mismatch")
    evidence=_dict(r.get("_current_grant_evidence")); gid=str(evidence.get("grant_id") or evidence.get("historical_grant_id")); gd=str(evidence.get("grant_digest") or evidence.get("historical_grant_digest"))
    sv,sf=validate_current_authority_snapshot(snapshot,grant_id=gid,grant_digest=gd); f += ["current_snapshot:"+x for x in sf]
    vv=validate_local_authorization_grant_verification(verification); f += ["current_verification:"+x for x in vv.findings]
    if verification.get("digest") != local_authorization_grant_verification_digest(verification): f.append("current_verification:digest_mismatch")
    if verification.get("grant_id")!=gid: f.append("current_verification_grant_mismatch")
    if verification.get("verification_status") not in ("local_authorization_verification_valid","local_authorization_verification_valid_with_conditions"): f.append("current_verification_not_positive")
    scopes=set(evidence.get("requested_scope_labels",rq.get("requested_scope_labels",())))
    if scopes-set(verification.get("checked_scope_labels",())) or verification.get("missing_labels"): f.append("current_verification_scope_mismatch")
    expiry=_dict(sv.get("expiry")); revocations=tuple(sv.get("revocations",()))
    if not sv.get("no_revocation_digest") and not revocations: f.append("current_revocation_evidence_omitted")
    if revocations: f.append("current_grant_revoked")
    if expiry.get("expiry_status") not in ("local_authorization_expiry_not_expired","local_authorization_expiry_valid","local_authorization_expiry_valid_with_conditions"): f.append("current_grant_not_current")
    records={"admission_records":{"candidate":candidate,"decision":decision,"plan":pob,"admission_bundle":ab,"runtime_receipt":ar},"closure_records":{"closure_bundle":closure,"source_dry_run_receipt":dry_receipt},"dry_run_records":{"request":dq,"dry_run_request":dry_req,"result_or_block_receipt":_dict(d.get("result_or_block_receipt")),"dry_run_receipt":dry_receipt,"runtime_receipt":drr},"readiness_records":{"request":rq,"current_grant_evidence":evidence,"contract":contract,"dry_run_plan":plan,"runtime_receipt":rr},"current_authority_posture":{"grant_id":gid,"grant_digest":gd,"expiry":expiry,"revocations":list(revocations),"no_revocation_digest":sv.get("no_revocation_digest","")}}
    f += _positive_flags(records)
    return records,f

def validate_execution_source_records(records: Mapping[str, Any]) -> tuple[str, ...]:
    """Deeply validate decoded v2 records without consulting source folders."""
    r = {str(k): _dict(v) for k, v in records.items()}
    f: list[str] = []
    for name in ("runtime_request", "runtime_plan", "runtime_receipt", "target_specification", "validation_findings"):
        value = r.get(name, {})
        if value and value.get("schema_version", SCHEMA_VERSION) != SCHEMA_VERSION:
            f.append("legacy_or_unknown_schema:" + name)
    req, plan, receipt = r.get("runtime_request", {}), r.get("runtime_plan", {}), r.get("runtime_receipt", {})
    target = r.get("target_specification", {})
    expected_target = dict(TARGET, output_directory=req.get("effect_output_dir"))
    if target != expected_target or plan.get("target_specification") != TARGET:
        f.append("target_specification_mismatch")
    if req.get("source_references") != r.get("source_references"):
        f.append("source_reference_mismatch")
    if plan.get("request_id") != req.get("request_id") or plan.get("request_digest") != req.get("digest"):
        f.append("request_plan_lineage_mismatch")
    if receipt and (receipt.get("request_id") != req.get("request_id") or receipt.get("request_digest") != req.get("digest") or receipt.get("plan_id") != plan.get("plan_id") or receipt.get("plan_digest") != plan.get("digest")):
        f.append("runtime_receipt_lineage_mismatch")
    admission = r.get("admission_records", {})
    closure = r.get("closure_records", {})
    dry = r.get("dry_run_records", {})
    ready = r.get("readiness_records", {})
    rebuilt, chain_findings = _chain(
        {"candidate": admission.get("candidate"), "decision": admission.get("decision"), "plan_or_block_receipt": admission.get("plan"), "admission_bundle": admission.get("admission_bundle"), "runtime_receipt": admission.get("runtime_receipt"), "source_closure_bundle": closure.get("closure_bundle")},
        {"request": dry.get("request"), "dry_run_request": dry.get("dry_run_request"), "result_or_block_receipt": dry.get("result_or_block_receipt"), "dry_run_receipt": dry.get("dry_run_receipt"), "runtime_receipt": dry.get("runtime_receipt")},
        {"request": ready.get("request"), "runtime_receipt": ready.get("runtime_receipt"), "contract": ready.get("contract"), "dry_run_plan": ready.get("dry_run_plan"), "_current_grant_evidence": ready.get("current_grant_evidence"), "_bundle_digest": r.get("source_references", {}).get("readiness_final_bundle_digest")},
        r.get("current_snapshot", {}), r.get("current_verification", {}),
    )
    f.extend(chain_findings)
    for name in ("admission_records", "closure_records", "dry_run_records", "readiness_records", "current_authority_posture"):
        if rebuilt.get(name) != r.get(name): f.append(name + "_semantic_mismatch")
    f.extend(_positive_flags(r))
    return tuple(sorted(set(f)))

class HostLocalDiagnosticExecutionSourceRuntimeCoordinator:
    def evaluate(self, *, admission_bundle_root:str|Path, dry_run_bundle_root:str|Path, readiness_bundle_root:str|Path, current_snapshot:Mapping[str,Any], current_verification:Mapping[str,Any], effect_output_dir:str|Path, output_root:str|Path, correlation_id:str|None=None)->HostLocalDiagnosticExecutionSourceEvaluation:
        av=validate_persisted_admission_bundle(admission_bundle_root); dv=validate_persisted_evaluation_bundle(dry_run_bundle_root); rv=validate_persisted_readiness_bundle(readiness_bundle_root)
        f=["admission:"+x for x in av.findings]+["dry_run:"+x for x in dv.findings]+["readiness:"+x for x in rv.findings]
        target,tf=_path_findings(effect_output_dir,may_not_exist=True); out,of=_path_findings(output_root,may_not_exist=True); f+=tf+of
        roots=[Path(x).resolve() for x in (admission_bundle_root,dry_run_bundle_root,readiness_bundle_root)]
        for root in roots:
            if _overlap(target,root): f.append("target_source_overlap")
            if _overlap(out,root): f.append("output_source_overlap")
        if _overlap(target,out): f.append("target_output_overlap")
        if (target/str(TARGET["artifact_name"])).exists(): f.append("target_artifact_already_exists")
        if not av.evaluation or not dv.evaluation or not rv.evaluation: return HostLocalDiagnosticExecutionSourceEvaluation("blocked_host_local_diagnostic_execution_source_runtime",tuple(sorted(set(f))),{})
        rd=rv.evaluation.to_dict(); rd["_bundle_digest"]=rv.bundle_digest; rd["_current_grant_evidence"]=_dict(rv.current_grant_evidence)
        records,cf=_chain(av.evaluation.to_dict(),dv.evaluation.to_dict(),rd,_dict(current_snapshot),_dict(current_verification)); f+=cf
        refs={"admission_final_bundle_digest":av.final_bundle_digest,"dry_run_final_bundle_digest":dv.bundle_digest,"readiness_final_bundle_digest":rv.bundle_digest}
        sem={"correlation_id":correlation_id or _dict(av.evaluation.request).get("correlation_id","") ,"sources":refs,"snapshot":_dict(current_snapshot).get("digest"),"verification":_dict(current_verification).get("digest"),"target":str(target),"target_spec":TARGET}
        req={"schema_version":SCHEMA_VERSION,"request_id":_id("hldes_request_",sem),"digest":"","correlation_id":sem["correlation_id"],"source_references":refs,"effect_output_dir":str(target),**BOUNDARY}; req["digest"]=digest_record(req)
        plan={"schema_version":SCHEMA_VERSION,"plan_id":_id("hldes_plan_",req["digest"]),"digest":"","request_id":req["request_id"],"request_digest":req["digest"],"target_specification":TARGET,**BOUNDARY}; plan["digest"]=digest_record(plan)
        if f: return HostLocalDiagnosticExecutionSourceEvaluation("blocked_host_local_diagnostic_execution_source_runtime",tuple(sorted(set(f))),{"runtime_request":req,"runtime_plan":plan})
        records.update({"runtime_request":req,"runtime_plan":plan,"source_references":refs,"current_snapshot":_dict(current_snapshot),"current_verification":_dict(current_verification),"target_specification":dict(TARGET,output_directory=str(target)),"validation_findings":{"findings":[],**BOUNDARY}})
        return self._persist(out,records)
    def _persist(self,root:Path,records:dict[str,Any])->HostLocalDiagnosticExecutionSourceEvaluation:
        req=records["runtime_request"]; bundle=root/req["request_id"]
        semantic_findings = validate_execution_source_records(records)
        if semantic_findings:
            return HostLocalDiagnosticExecutionSourceEvaluation("blocked_host_local_diagnostic_execution_source_runtime", semantic_findings, records)
        semantic=_sha({k:v for k,v in records.items() if k not in ("source_paths",)})
        index=root/"replay_index.json"
        root.mkdir(parents=True,exist_ok=True)
        lock = root/".execution-source.lock"
        with lock.open("a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            if index.exists():
                old=json.loads(index.read_text()); prior=old.get(req["correlation_id"])
                if prior and prior.get("semantic_digest")!=semantic: return HostLocalDiagnosticExecutionSourceEvaluation("host_local_diagnostic_execution_source_conflict",("correlation_semantic_conflict",),records)
                if prior:
                    replay=load_persisted_execution_source_bundle(root/prior["request_id"], expected_bundle_digest=prior.get("bundle_digest"))
                    if replay.ok and replay.evaluation: return replay.evaluation
                    return HostLocalDiagnosticExecutionSourceEvaluation("blocked_host_local_diagnostic_execution_source_runtime", replay.findings, records)
            return self._publish_locked(root, bundle, index, records, semantic)

    def _publish_locked(self, root:Path, bundle:Path, index:Path, records:dict[str,Any], semantic:str)->HostLocalDiagnosticExecutionSourceEvaluation:
        req=records["runtime_request"]
        tmp=Path(tempfile.mkdtemp(prefix=".hldes-",dir=root))
        mapping={"runtime_request.json":"runtime_request","runtime_plan.json":"runtime_plan","source_references.json":"source_references","admission_records.json":"admission_records","closure_records.json":"closure_records","dry_run_records.json":"dry_run_records","readiness_records.json":"readiness_records","current_snapshot.json":"current_snapshot","current_verification.json":"current_verification","current_authority_posture.json":"current_authority_posture","target_specification.json":"target_specification","validation_findings.json":"validation_findings"}
        for fn,key in mapping.items(): (tmp/fn).write_text(_canon(records[key])+"\n")
        summary={"schema_version":SCHEMA_VERSION,"status":"host_local_diagnostic_execution_source_ready","request_id":req["request_id"],"semantic_digest":semantic,**BOUNDARY}; (tmp/"summary.json").write_text(_canon(summary)+"\n"); (tmp/"README.md").write_text("# Diagnostic execution source custody\n\nMetadata only; does not authorize or perform execution.\n")
        content=_manifest(tmp,CONTENT_FILES,"host_local_diagnostic_execution_source_runtime_content_manifest","content_manifest_digest"); (tmp/"content_manifest.json").write_text(_canon(content)+"\n")
        receipt={"schema_version":SCHEMA_VERSION,"receipt_id":_id("hldes_receipt_",req["digest"]),"digest":"","runtime_status":"host_local_diagnostic_execution_source_ready","request_id":req["request_id"],"request_digest":req["digest"],"plan_id":records["runtime_plan"]["plan_id"],"plan_digest":records["runtime_plan"]["digest"],"source_reference_digest":_sha(records["source_references"]),"current_snapshot_digest":records["current_snapshot"].get("digest"),"current_verification_digest":records["current_verification"].get("digest"),"current_authority_posture_digest":_sha(records["current_authority_posture"]),"target_specification_digest":_sha(records["target_specification"]),"validation_findings_digest":_sha(records["validation_findings"]),"content_manifest_digest":content["content_manifest_digest"],"semantic_digest":semantic,**BOUNDARY}; receipt["digest"]=digest_record(receipt); (tmp/"runtime_receipt.json").write_text(_canon(receipt)+"\n")
        final=_manifest(tmp,FINAL_FILES,"host_local_diagnostic_execution_source_runtime_bundle_manifest","bundle_digest"); (tmp/"bundle_manifest.json").write_text(_canon(final)+"\n"); os.replace(tmp,bundle)
        latest={"request_id":req["request_id"],"bundle_digest":final["bundle_digest"]}; _atomic(root/"latest.json",latest); old=json.loads(index.read_text()) if index.exists() else {}; old[req["correlation_id"]]={"request_id":req["request_id"],"semantic_digest":semantic,"bundle_digest":final["bundle_digest"]}; _atomic(index,old)
        return HostLocalDiagnosticExecutionSourceEvaluation("host_local_diagnostic_execution_source_ready",(),records,str(bundle))

def _manifest(root:Path,files:set[str],kind:str,key:str)->dict[str,Any]:
    entries=[]
    for fn in sorted(files):
        raw=(root/fn).read_bytes()
        artifact_kind = "markdown_summary" if fn.endswith(".md") else fn.removesuffix(".json")
        semantic_id = None
        if fn.endswith(".json"):
            try:
                value=json.loads(raw); semantic_id=next((value.get(k) for k in ("request_id","plan_id","receipt_id","candidate_id","decision_id") if value.get(k)),None)
            except Exception: pass
        entries.append({"relative_filename":fn,"size_bytes":len(raw),"sha256":_raw_sha(raw),"entry_schema_version":SCHEMA_VERSION,"entry_artifact_kind":artifact_kind,"semantic_id":semantic_id})
    out={"schema_version":SCHEMA_VERSION,"artifact_kind":kind,"files":entries}; out[key]=_sha(out); return out
def _atomic(path:Path,value:Any)->None:
    fd,name=tempfile.mkstemp(dir=path.parent,prefix=".tmp-"); os.close(fd); p=Path(name); p.write_text(_canon(value)+"\n"); os.replace(p,path)

def load_persisted_execution_source_bundle(bundle_root:str|Path, *, expected_bundle_digest:str|None=None)->HostLocalDiagnosticExecutionSourceValidation:
    root,f=_path_findings(bundle_root)
    if f: return HostLocalDiagnosticExecutionSourceValidation(False,tuple(sorted(set(f))))
    allowed=FINAL_FILES|{"bundle_manifest.json"}; actual={p.name for p in root.iterdir() if p.suffix in (".json",".md")}
    if actual!=allowed: f.append("unexpected_or_missing_semantic_artifacts")
    decoded={}
    for manifest_name,files,kind,key in (("content_manifest.json",CONTENT_FILES,"host_local_diagnostic_execution_source_runtime_content_manifest","content_manifest_digest"),("bundle_manifest.json",FINAL_FILES,"host_local_diagnostic_execution_source_runtime_bundle_manifest","bundle_digest")):
        try: m=json.loads((root/manifest_name).read_text()); entries=m.get("files",[])
        except Exception: f.append(manifest_name+":decode_failed"); continue
        names=[e.get("relative_filename") for e in entries]
        if len(names)!=len(set(names)): f.append(manifest_name+":duplicate_entries")
        if set(names)!=files or m.get("artifact_kind")!=kind or m.get("schema_version") != SCHEMA_VERSION: f.append(manifest_name+":shape_mismatch")
        check=dict(m); claimed=check.pop(key,None)
        if claimed!=_sha(check): f.append(manifest_name+":digest_mismatch")
        for e in entries:
            fn=str(e.get("relative_filename","")); p=root/fn
            if Path(fn).name!=fn or ".." in Path(fn).parts or p.is_symlink(): f.append("manifest_path_rejected:"+fn); continue
            if not p.is_file(): f.append("manifest_file_missing:"+fn); continue
            raw=p.read_bytes()
            if len(raw)!=e.get("size_bytes") or _raw_sha(raw)!=e.get("sha256"): f.append("manifest_file_mismatch:"+fn)
            expected_kind = "markdown_summary" if fn.endswith(".md") else fn.removesuffix(".json")
            semantic_id = None
            if fn.endswith(".json"):
                try:
                    value=json.loads(raw); semantic_id=next((value.get(k) for k in ("request_id","plan_id","receipt_id","candidate_id","decision_id") if value.get(k)),None)
                except Exception: pass
            if e.get("entry_schema_version") != SCHEMA_VERSION or e.get("entry_artifact_kind") != expected_kind or e.get("semantic_id") != semantic_id:
                f.append("manifest_entry_metadata_mismatch:"+fn)
        if key=="bundle_digest": bundle_digest=str(claimed or "")
    for fn in RECORD_FILES-{"README.md"}:
        try: decoded[fn[:-5]]=json.loads((root/fn).read_text())
        except Exception: f.append("record_decode_failed:"+fn)
    req=decoded.get("runtime_request",{}); plan=decoded.get("runtime_plan",{}); receipt=decoded.get("runtime_receipt",{})
    if req.get("schema_version") == LEGACY_SCHEMA_VERSION: f.append("legacy_v1_bundle_rejected")
    if req.get("schema_version") != SCHEMA_VERSION: f.append("unsupported_schema_version")
    for obj,name in ((req,"request"),(plan,"plan"),(receipt,"receipt")):
        if obj.get("digest")!=digest_record(obj): f.append(name+"_digest_mismatch")
    if plan.get("request_digest")!=req.get("digest") or receipt.get("request_digest")!=req.get("digest") or receipt.get("plan_digest")!=plan.get("digest"): f.append("runtime_lineage_mismatch")
    f += _positive_flags(decoded)
    if decoded.get("target_specification",{}).get("artifact_name")!=TARGET["artifact_name"]: f.append("target_substitution")
    f += list(validate_execution_source_records(decoded))
    try:
        content=json.loads((root/"content_manifest.json").read_text())
        if receipt.get("content_manifest_digest") != content.get("content_manifest_digest"): f.append("receipt_content_manifest_mismatch")
        bindings={"source_reference_digest":_sha(decoded.get("source_references",{})),"current_snapshot_digest":decoded.get("current_snapshot",{}).get("digest"),"current_verification_digest":decoded.get("current_verification",{}).get("digest"),"current_authority_posture_digest":_sha(decoded.get("current_authority_posture",{})),"target_specification_digest":_sha(decoded.get("target_specification",{})),"validation_findings_digest":_sha(decoded.get("validation_findings",{}))}
        for key,value in bindings.items():
            if not value or receipt.get(key)!=value: f.append("runtime_receipt_binding_mismatch:"+key)
    except Exception: pass
    if expected_bundle_digest is not None and locals().get("bundle_digest","") != expected_bundle_digest: f.append("expected_bundle_digest_mismatch")
    ev=HostLocalDiagnosticExecutionSourceEvaluation("host_local_diagnostic_execution_source_ready",(),decoded,str(root),True)
    return HostLocalDiagnosticExecutionSourceValidation(not f,tuple(sorted(set(f))),ev if not f else None,locals().get("bundle_digest",""))

validate_persisted_execution_source_bundle = load_persisted_execution_source_bundle

def load_latest_evaluation(output_root:str|Path)->HostLocalDiagnosticExecutionSourceEvaluation|None:
    root=Path(output_root)
    try: latest=json.loads((root/"latest.json").read_text()); v=load_persisted_execution_source_bundle(root/str(latest["request_id"]),expected_bundle_digest=str(latest["bundle_digest"])); return v.evaluation if v.ok else None
    except Exception: return None
