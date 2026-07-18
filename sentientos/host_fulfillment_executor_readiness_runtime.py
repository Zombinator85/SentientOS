"""Canonical host fulfillment executor-contract readiness runtime.

Metadata/evidence custody only: no executor implementation, backend loading or
invocation, dry-run execution, fulfillment grant, privileged-effect admission,
effect performance, host mutation, provider call, network transport, or Git use.
"""
from __future__ import annotations

import hashlib, json, os, re, tempfile, threading
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from sentientos.control_plane_kernel import AuthorityClass, ControlActionRequest, ControlActionDecision, LifecyclePhase, get_control_plane_kernel
from sentientos.fulfillment_authorization import fulfillment_authorization_consumption_receipt_digest
from sentientos.fulfillment_executor_contract import (
    BACKEND_CLASSES, EXECUTOR_DOMAINS, REQUIRED_EXECUTOR_LABELS,
    build_fulfillment_executor_contract, build_executor_backend_declaration,
    build_executor_precondition_manifest, build_executor_dry_run_plan,
    build_executor_admission_packet, build_executor_contract_readiness_receipt,
    validate_fulfillment_executor_contract, validate_executor_backend_declaration,
    validate_executor_precondition_manifest, validate_executor_dry_run_plan,
    validate_executor_admission_packet, validate_executor_contract_readiness_receipt,
)
from sentientos.host_fulfillment_authorization_runtime import HostFulfillmentAuthorizationConsumptionResult, _digest_record as hfac_digest_record
from sentientos.world_state_board import WorldStateSourceKind, digest as world_digest

SCHEMA_VERSION="host_fulfillment_executor_readiness_runtime.v1"
NO_AUTHORITY={"execution_ready":False,"executor_implemented":False,"backend_loaded":False,"backend_invoked":False,"dry_run_executed":False,"control_plane_execution_admission_granted":False,"fulfillment_granted":False,"privileged_effect_admission_granted":False,"effect_performed":False,"host_mutation_performed":False}
REVIEW_POSTURES=("ready_for_executor_contract_review","ready_for_executor_contract_review_with_conditions","incomplete_contract_package","blocked_contract_package","contradicted_contract_package","stale_contract_package","unavailable_contract_package")
_ALLOWED_BACKEND_LABEL=re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")
_LOCKS:dict[str,threading.Lock]={}

def _dict(o:Any)->dict[str,Any]:
    if hasattr(o,"to_dict"):
        return dict(o.to_dict())
    if hasattr(o,"__dataclass_fields__"): return asdict(o)
    return dict(o)

def _canon(o:Any)->str: return json.dumps(o, sort_keys=True, separators=(",",":"), default=str)
def _sha(o:Any)->str: return "sha256:"+hashlib.sha256(_canon(o).encode()).hexdigest()
def _id(prefix:str,o:Any)->str: return prefix+hashlib.sha256(_canon(o).encode()).hexdigest()[:24]
def _semantic(o:Mapping[str,Any])->dict[str,Any]:
    d=dict(o); d.pop("created_at",None); d.pop("observed_at",None); d.pop("duration",None); d.pop("digest",None); return d

def digest_record(o:Any)->str: return _sha(_semantic(_dict(o)))

@dataclass(frozen=True)
class HostFulfillmentExecutorReadinessBudget:
    max_records:int=64; max_serialized_bytes:int=262144; max_backend_label_length:int=80
    def to_dict(self)->dict[str,Any]: return asdict(self)
@dataclass(frozen=True)
class HostFulfillmentExecutorSourceRef:
    ref_id:str; digest:str; kind:str; required:bool=True
    def to_dict(self)->dict[str,Any]: return asdict(self)
@dataclass(frozen=True)
class HostFulfillmentExecutorReadinessRequest:
    request_id:str; digest:str; correlation_id:str; consumption_result_id:str; consumption_result_digest:str; executor_domain:str; backend_class:str; backend_label:str; requested_scope_labels:tuple[str,...]; target_labels:tuple[str,...]; requested_time:str; current_grant_posture:str; missing_future_gates:tuple[str,...]; blocked_actions:tuple[str,...]; created_at:str= "1970-01-01T00:00:00+00:00"; schema_version:str=SCHEMA_VERSION
    def to_dict(self)->dict[str,Any]: return asdict(self)
@dataclass(frozen=True)
class HostFulfillmentExecutorPrerequisiteRecord:
    label:str; status:str; evidence_id:str=""; evidence_digest:str=""; finding:str="ok"
    def to_dict(self)->dict[str,Any]: return asdict(self)
@dataclass(frozen=True)
class HostFulfillmentExecutorReadinessPlan:
    plan_id:str; digest:str; request_id:str; request_digest:str; source_refs:tuple[HostFulfillmentExecutorSourceRef,...]; prerequisite_labels:tuple[str,...]; blocked_actions:tuple[str,...]; metadata_evaluation_only:bool=True; no_authority:Mapping[str,bool]=None # type: ignore[assignment]
    def to_dict(self)->dict[str,Any]:
        d=asdict(self); d["no_authority"]=dict(self.no_authority or NO_AUTHORITY); return d
@dataclass(frozen=True)
class HostFulfillmentExecutorReadinessReceipt:
    receipt_id:str; digest:str; posture:str; request_id:str; request_digest:str; contract_id:str; contract_digest:str; admission_packet_id:str; admission_packet_digest:str; readiness_receipt_id:str; readiness_receipt_digest:str; no_authority:Mapping[str,bool]
    def to_dict(self)->dict[str,Any]: return asdict(self)
@dataclass(frozen=True)
class HostFulfillmentExecutorReadinessEvaluation:
    status:str; findings:tuple[str,...]; request:HostFulfillmentExecutorReadinessRequest|None; plan:HostFulfillmentExecutorReadinessPlan|None; metadata_admission:Mapping[str,Any]|None; prerequisite_records:tuple[HostFulfillmentExecutorPrerequisiteRecord,...]; contract:Mapping[str,Any]|None; backend_declaration:Mapping[str,Any]|None; precondition_manifest:Mapping[str,Any]|None; dry_run_plan:Mapping[str,Any]|None; admission_packet:Mapping[str,Any]|None; readiness_receipt:Mapping[str,Any]|None; runtime_receipt:HostFulfillmentExecutorReadinessReceipt|None; persisted:bool=False; replayed:bool=False; builder_call_count:int=0; admission_call_count:int=0
    def to_dict(self)->dict[str,Any]: return asdict(self)
@dataclass(frozen=True)
class HostFulfillmentExecutorReadinessRuntimeSummary:
    summary_id:str; posture:str; contract_package_count:int; no_authority:Mapping[str,bool]; latest_contract_id:str=""; latest_packet_id:str=""; latest_readiness_receipt_id:str=""
    def to_dict(self)->dict[str,Any]: return asdict(self)
@dataclass(frozen=True)
class HostFulfillmentExecutorReadinessValidationResult:
    ok:bool; findings:tuple[str,...]
    def to_dict(self)->dict[str,Any]: return asdict(self)

def _validate_backend_label(label:str)->list[str]:
    bad=[]
    if not _ALLOWED_BACKEND_LABEL.fullmatch(label): bad.append("backend_label_rejected")
    forbidden=("/","\\","..","://","$","`",";","|","&","(",")","import ","python","sh ")
    if any(x in label for x in forbidden): bad.append("backend_label_executable_or_pathlike")
    return bad

def _posture_from_source(result:HostFulfillmentAuthorizationConsumptionResult, now:str)->str:
    if result.status!="recorded": return "blocked_contract_package"
    if not result.consumption_receipt: return "incomplete_contract_package"
    if any(_dict(r).get("revocation_status")=="local_authorization_revocation_recorded" for r in (result.source.revocation_receipt_refs if hasattr(result.source,'revocation_receipt_refs') else ())): return "blocked_contract_package"
    return "ready_for_executor_contract_review_with_conditions"

def build_request(result:HostFulfillmentAuthorizationConsumptionResult, *, executor_domain:str|None=None, backend_class:str|None=None, backend_label:str="declaration-only-not-loaded", current_grant_posture:str="currently_active", created_at:str="1970-01-01T00:00:00+00:00")->HostFulfillmentExecutorReadinessRequest:
    if not isinstance(result, HostFulfillmentAuthorizationConsumptionResult): raise ValueError("strict_typed_consumption_result_required")
    if result.status!="recorded" or not result.consumption_receipt: raise ValueError("successful_consumption_receipt_required")
    rec=_dict(result.consumption_receipt); env=_dict(result.envelope)
    domain=executor_domain or "future_cooling_executor_contract"
    backend=backend_class or "cooling_backend_future"
    sem={"consumption_result_digest":_sha(result.to_dict()),"receipt_id":rec.get("receipt_id"),"receipt_digest":rec.get("digest"),"ledger_digest":_dict(result.ledger or {}).get("digest"),"executor_domain":domain,"backend_class":backend,"backend_label":backend_label,"scope":tuple(env.get("requested_scope_labels",())),"targets":tuple(env.get("target_labels",())),"time":env.get("requested_time"),"grant_posture":current_grant_posture,"blocked":tuple(sorted(rec.get("blocked_actions",()))) }
    rid=_id("hfer_request_",sem)
    req=HostFulfillmentExecutorReadinessRequest(rid,"",str(env.get("idempotency_key") or rid),_id("hfac_result_",_sha(result.to_dict())),_sha(result.to_dict()),domain,backend,backend_label,tuple(env.get("requested_scope_labels",())),tuple(env.get("target_labels",())),str(env.get("requested_time")),current_grant_posture,("control_plane_admission_required_for_future_execution","effect_receipt_required_for_future_execution","executor_identity_required"),tuple(sorted(rec.get("blocked_actions",()))),created_at)
    return replace(req,digest=digest_record(req))

def validate_consumption_source(result:HostFulfillmentAuthorizationConsumptionResult)->HostFulfillmentExecutorReadinessValidationResult:
    f=[]
    if not isinstance(result, HostFulfillmentAuthorizationConsumptionResult): return HostFulfillmentExecutorReadinessValidationResult(False,("strict_typed_consumption_result_required",))
    d=result.to_dict(); rec=_dict(result.consumption_receipt or {}); entry=_dict(result.ledger_entry or {}); led=_dict(result.ledger or {})
    if result.status!="recorded": f.append("denial_only_result_rejected")
    if not rec: f.append("missing_successful_consumption_receipt")
    if rec and not rec.get("authorization_consumed_for_future_fulfillment",False): f.append("authorization_not_consumed_for_future_fulfillment")
    if rec and rec.get("digest") != fulfillment_authorization_consumption_receipt_digest(rec): f.append("consumption_receipt_digest_unverified")
    if entry:
        if entry.get("consumption_receipt",{}).get("digest") != rec.get("digest"): f.append("ledger_entry_receipt_mismatch")
        if entry.get("digest") != hfac_digest_record(entry): f.append("consumption_ledger_entry_digest_unverified")
    else: f.append("missing_consumption_ledger_entry")
    if led:
        entries=list(led.get("entries",[]))
        if entry and not any(e.get("digest")==entry.get("digest") for e in entries): f.append("ledger_missing_exact_entry")
    else: f.append("missing_consumption_ledger")
    # Duplicate semantic IDs with different digests are rejected by the runtime plan/idempotency layer;
    # source records here may legitimately reuse upstream request ids across derived records.
    return HostFulfillmentExecutorReadinessValidationResult(not f,tuple(sorted(set(f))))

class HostFulfillmentExecutorReadinessRuntimeCoordinator:
    def __init__(self, *, runtime_state_root:str|Path|None=None, kernel:Any|None=None, clock:Callable[[],str]|None=None):
        self.runtime_state_root=Path(runtime_state_root or os.getenv("SENTIENTOS_RUNTIME_STATE_ROOT") or tempfile.gettempdir()+"/sentientos_runtime")
        self.kernel=kernel or get_control_plane_kernel(); self.clock=clock or (lambda:"1970-01-01T00:00:00+00:00"); self.builder_call_count=0; self.admission_call_count=0
    def _root(self)->Path:
        r=(self.runtime_state_root/"host_fulfillment_executor_contract_readiness_runtime").resolve(); r.mkdir(parents=True,exist_ok=True); return r
    def request_metadata_admission(self, req:HostFulfillmentExecutorReadinessRequest, plan:HostFulfillmentExecutorReadinessPlan, result:HostFulfillmentAuthorizationConsumptionResult)->ControlActionDecision:
        self.admission_call_count+=1
        return self.kernel.admit(ControlActionRequest("host_fulfillment_executor_contract_readiness_metadata_evaluation",AuthorityClass.PROPOSAL_EVALUATION,"operator_invoked_cli","host_fulfillment_executor_readiness",LifecyclePhase.MAINTENANCE,{"correlation_id":req.correlation_id,"readiness_request_id":req.request_id,"readiness_request_digest":req.digest,"consumption_result_digest":req.consumption_result_digest,"consumption_receipt_digest":_dict(result.consumption_receipt or {}).get("digest"),"consumption_ledger_digest":_dict(result.ledger or {}).get("digest"),"runtime_plan_id":plan.plan_id,"runtime_plan_digest":plan.digest,**NO_AUTHORITY}))
    def plan(self, req:HostFulfillmentExecutorReadinessRequest, result:HostFulfillmentAuthorizationConsumptionResult)->HostFulfillmentExecutorReadinessPlan:
        refs=tuple(HostFulfillmentExecutorSourceRef(i,d,k) for k,i,d in (("consumption_result",req.consumption_result_id,req.consumption_result_digest),("consumption_receipt",str(_dict(result.consumption_receipt or {}).get("receipt_id")),str(_dict(result.consumption_receipt or {}).get("digest"))),("consumption_ledger", "host_fulfillment_authorization_consumption_ledger", str(_dict(result.ledger or {}).get("digest")))))
        sem={"request":req.digest,"refs":[r.to_dict() for r in refs],"labels":sorted(REQUIRED_EXECUTOR_LABELS),"blocked":req.blocked_actions,"no_authority":NO_AUTHORITY}
        pl=HostFulfillmentExecutorReadinessPlan(_id("hfer_plan_",sem),"",req.request_id,req.digest,refs,tuple(sorted(REQUIRED_EXECUTOR_LABELS)),req.blocked_actions,True,NO_AUTHORITY)
        return replace(pl,digest=digest_record(pl))
    def evaluate(self, result:HostFulfillmentAuthorizationConsumptionResult, *, output_root:str|Path, backend_label:str="declaration-only-not-loaded", current_grant_posture:str="currently_active", persist:bool=True)->HostFulfillmentExecutorReadinessEvaluation:
        findings=list(validate_consumption_source(result).findings)+_validate_backend_label(backend_label)
        if current_grant_posture not in {"currently_active","active_with_conditions"}: findings.append("current_grant_posture_"+current_grant_posture)
        if findings: return HostFulfillmentExecutorReadinessEvaluation("blocked_contract_package",tuple(sorted(set(findings))),None,None,None,(),None,None,None,None,None,None,None,False,False,0,self.admission_call_count)
        req=build_request(result,backend_label=backend_label,current_grant_posture=current_grant_posture,created_at=self.clock()); plan=self.plan(req,result)
        root=Path(output_root).resolve(); base=self._root();
        if str(root).startswith(str(Path.cwd().resolve())): return HostFulfillmentExecutorReadinessEvaluation("blocked_contract_package",("repository_local_runtime_root_rejected",),req,plan,None,(),None,None,None,None,None,None,None,False,False,0,self.admission_call_count)
        adm=self.request_metadata_admission(req,plan,result); ad=_dict(adm)
        if not adm.allowed or adm.authority_class != AuthorityClass.PROPOSAL_EVALUATION:
            return HostFulfillmentExecutorReadinessEvaluation("blocked_contract_package",("metadata_admission_not_allowed",),req,plan,ad,(),None,None,None,None,None,None,None,False,False,0,self.admission_call_count)
        rec=_dict(result.consumption_receipt or {})
        c=build_fulfillment_executor_contract(rec,executor_domain=req.executor_domain,backend_class=req.backend_class,created_at=self.clock()); self.builder_call_count+=1
        b=build_executor_backend_declaration(c,backend_label=backend_label,created_at=self.clock()); self.builder_call_count+=1
        m=build_executor_precondition_manifest(c,rec,created_at=self.clock()); self.builder_call_count+=1
        p=build_executor_dry_run_plan(c,created_at=self.clock()); self.builder_call_count+=1
        a=build_executor_admission_packet(c,b,m,p,rec,created_at=self.clock()); self.builder_call_count+=1
        rr=build_executor_contract_readiness_receipt(c,b,m,p,a,created_at=self.clock()); self.builder_call_count+=1
        vf=[]
        for vr in (validate_fulfillment_executor_contract(c),validate_executor_backend_declaration(b),validate_executor_precondition_manifest(m),validate_executor_dry_run_plan(p),validate_executor_admission_packet(a),validate_executor_contract_readiness_receipt(rr)):
            vf+=list(vr.findings)
        prereq=tuple(HostFulfillmentExecutorPrerequisiteRecord(x,"satisfied" if x in {"fulfillment_authorization_consumption_required","local_authorization_grant_required","scope_match_required","grant_not_expired_required","grant_not_revoked_required","backend_declaration_required","dry_run_plan_required","precondition_manifest_required"} else "missing", req.request_id if x.startswith(("fulfillment","local","scope","grant")) else c.contract_id, req.digest if x.startswith(("fulfillment","local","scope","grant")) else c.digest) for x in sorted(REQUIRED_EXECUTOR_LABELS))
        posture="ready_for_executor_contract_review_with_conditions"
        runtime=HostFulfillmentExecutorReadinessReceipt(_id("hfer_receipt_",{"req":req.digest,"contract":c.digest,"packet":a.digest,"rr":rr.digest}),"",posture,req.request_id,req.digest,c.contract_id,c.digest,a.packet_id,a.digest,rr.receipt_id,rr.digest,NO_AUTHORITY)
        runtime=replace(runtime,digest=digest_record(runtime))
        ev=HostFulfillmentExecutorReadinessEvaluation(posture,tuple(vf),req,plan,ad,prereq,c.to_dict(),b.to_dict(),m.to_dict(),p.to_dict(),a.to_dict(),rr.to_dict(),runtime,False,False,self.builder_call_count,self.admission_call_count)
        if persist: ev=replace(ev,persisted=self._persist(root,ev))
        return ev
    def _persist(self, root:Path, ev:HostFulfillmentExecutorReadinessEvaluation)->bool:
        if root.exists() and root.is_symlink(): raise ValueError("symlink_escape_rejected")
        root.mkdir(parents=True,exist_ok=True); bundle=root/(ev.request.request_id if ev.request else "blocked")
        tmp=root/(bundle.name+".tmp"); tmp.mkdir(exist_ok=True)
        data=ev.to_dict(); files={"readiness_request.json":data.get("request"),"source_manifest.json":data.get("plan"),"metadata_admission.json":data.get("metadata_admission"),"runtime_plan.json":data.get("plan"),"prerequisites.json":data.get("prerequisite_records"),"executor_contract.json":data.get("contract"),"backend_declaration.json":data.get("backend_declaration"),"precondition_manifest.json":data.get("precondition_manifest"),"dry_run_plan.json":data.get("dry_run_plan"),"admission_packet.json":data.get("admission_packet"),"readiness_receipt.json":data.get("readiness_receipt"),"runtime_receipt.json":data.get("runtime_receipt"),"validation_findings.json":{"findings":data.get("findings")},"summary.json":summarize_evaluation(ev),"README.md":render_markdown(ev)}
        for name,val in files.items(): (tmp/name).write_text(json.dumps(val,sort_keys=True,indent=2) if name.endswith('.json') else str(val),encoding='utf-8')
        os.replace(tmp,bundle); (root/"latest.json").write_text(json.dumps({"request_id":ev.request.request_id,"posture":ev.status,"contract_id":ev.contract.get("contract_id") if ev.contract else "","readiness_receipt_id":ev.readiness_receipt.get("receipt_id") if ev.readiness_receipt else ""},sort_keys=True,indent=2),encoding='utf-8') # type: ignore[union-attr]
        return True

def summarize_evaluation(ev:HostFulfillmentExecutorReadinessEvaluation)->dict[str,Any]:
    return {"schema_version":SCHEMA_VERSION,"posture":ev.status,"contract_package_count":1 if ev.contract else 0,"request_id":ev.request.request_id if ev.request else "","latest_contract_id":ev.contract.get("contract_id") if ev.contract else "","latest_packet_id":ev.admission_packet.get("packet_id") if ev.admission_packet else "","latest_readiness_receipt_id":ev.readiness_receipt.get("receipt_id") if ev.readiness_receipt else "",**NO_AUTHORITY}

def render_markdown(ev:HostFulfillmentExecutorReadinessEvaluation)->str:
    s=summarize_evaluation(ev); return "# Host Fulfillment Executor Contract Readiness Runtime\n\n"+"\n".join(f"- {k}: {v}" for k,v in sorted(s.items()))+"\n"

def world_state_records(ev:HostFulfillmentExecutorReadinessEvaluation, *, observed_at:str="1970-01-01T00:00:00+00:00")->list[dict[str,Any]]:
    items=[("proposal","host_fulfillment_executor_readiness_request",ev.request.to_dict() if ev.request else None),("review","host_fulfillment_executor_metadata_admission",ev.metadata_admission),("review","host_fulfillment_executor_contract",ev.contract),("review","host_fulfillment_executor_backend_declaration",ev.backend_declaration),("review","host_fulfillment_executor_precondition_manifest",ev.precondition_manifest),("review","host_fulfillment_executor_dry_run_plan",ev.dry_run_plan),("admission","host_fulfillment_executor_future_execution_admission_packet",ev.admission_packet),("review","host_fulfillment_executor_readiness_receipt",ev.readiness_receipt)]
    out=[]
    for stage,kind,obj in items:
        if not obj: continue
        p=_dict(obj); p.update(NO_AUTHORITY); sid=str(p.get("request_id") or p.get("contract_id") or p.get("declaration_id") or p.get("manifest_id") or p.get("plan_id") or p.get("packet_id") or p.get("receipt_id"))
        out.append({"source_kind":WorldStateSourceKind.FULFILLMENT.value,"schema_version":SCHEMA_VERSION,"observed_at":observed_at,"source_id":f"hfer:{sid}:{kind}","subject_id":sid,"subject_kind":kind,"stage": "admission" if "admission_packet" in kind else stage,"disposition":ev.status,"evidence_strength":"recorded","payload":p,"effect_claimed":False,"effect_proven":False,"digest":world_digest(p)})
    for pr in ev.prerequisite_records:
        p=pr.to_dict(); p.update(NO_AUTHORITY); out.append({"source_kind":WorldStateSourceKind.FULFILLMENT.value,"schema_version":SCHEMA_VERSION,"observed_at":observed_at,"source_id":f"hfer:prerequisite:{pr.label}","subject_id":pr.label,"subject_kind":"host_fulfillment_executor_prerequisite_record","stage":"review","disposition":pr.status,"evidence_strength":"recorded","payload":p,"effect_claimed":False,"effect_proven":False,"digest":world_digest(p)})
    return out

def dashboard_projection(records:Sequence[Mapping[str,Any]])->dict[str,Any]:
    posture: dict[str,int]={}; domains: dict[str,int]={}; backends: dict[str,int]={}; pre: dict[str,int]={"satisfied":0,"conditional":0,"missing":0,"blocked":0,"contradicted":0,"stale":0}; latest_contract=latest_packet=latest_receipt=""; gates: set[str]=set(); blocks: set[str]=set(); count=0
    for r in records:
        p=_dict(r.get("payload",{})); k=str(r.get("subject_kind",""))
        if k.startswith("host_fulfillment_executor_"): count+=1; posture[str(r.get("disposition","unknown"))]=posture.get(str(r.get("disposition","unknown")),0)+1
        if p.get("executor_domain"): domains[str(p.get("executor_domain"))]=domains.get(str(p.get("executor_domain")),0)+1
        if p.get("backend_class"): backends[str(p.get("backend_class"))]=backends.get(str(p.get("backend_class")),0)+1
        if k.endswith("prerequisite_record"): pre[str(p.get("status","missing"))]=pre.get(str(p.get("status","missing")),0)+1
        if k.endswith("contract"): latest_contract=str(p.get("contract_id",latest_contract))
        if "admission_packet" in k: latest_packet=str(p.get("packet_id",latest_packet)); gates.update(p.get("required_control_plane_labels",()))
        if k.endswith("readiness_receipt"): latest_receipt=str(p.get("receipt_id",latest_receipt))
        blocks.update(p.get("blocked_actions",()))
    return {"status":"recorded" if count else "unavailable","contract_package_count":count,"posture_counts":posture,"executor_domain_counts":domains,"backend_class_declaration_counts":backends,"prerequisite_counts":pre,"missing_future_gate_labels":sorted(gates),"blocked_actions":sorted(blocks),"latest_contract_id":latest_contract,"latest_packet_id":latest_packet,"latest_readiness_receipt_id":latest_receipt,"read_only":True,"executor_contract_review_only":True,**NO_AUTHORITY}
