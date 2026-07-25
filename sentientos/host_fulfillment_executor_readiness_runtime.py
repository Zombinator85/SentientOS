"""Canonical host fulfillment executor-contract readiness runtime.

Metadata/evidence custody only: no executor implementation, backend loading or
invocation, dry-run execution, fulfillment grant, privileged-effect admission,
effect performance, host mutation, provider call, network transport, or Git use.
"""
from __future__ import annotations

import hashlib, json, os, re, shutil, tempfile, threading
from datetime import datetime
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
    resolve_canonical_executor_route,
)
from sentientos.host_fulfillment_authorization_runtime import HostFulfillmentAuthorizationConsumptionResult, _digest_record as hfac_digest_record
from sentientos.host_local_authorization_runtime import HostLocalAuthorizationLedgerSnapshot, HostLocalAuthorizationIssueReceipt, HostLocalAuthorizationRevocationReceipt, _digest_record as host_local_digest_record
from sentientos.local_authorization_grant import (
    LocalAuthorizationGrant, LocalAuthorizationGrantVerification, LocalAuthorizationGrantLedger,
    LocalAuthorizationGrantExpiryEvaluation, LocalAuthorizationGrantRevocationReceipt,
    local_authorization_grant_digest, local_authorization_grant_verification_digest,
    local_authorization_grant_ledger_digest, local_authorization_grant_expiry_evaluation_digest,
    local_authorization_grant_revocation_receipt_digest, validate_local_authorization_grant,
    validate_local_authorization_grant_verification, validate_local_authorization_grant_ledger,
    validate_local_authorization_grant_expiry_evaluation, validate_local_authorization_grant_revocation_receipt,
)
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
class HostFulfillmentExecutorCurrentGrantEvidence:
    evidence_id:str; digest:str; grant_id:str; grant_digest:str; verification_id:str; verification_digest:str; authorization_ledger_id:str; authorization_ledger_digest:str; authorization_ledger_predecessor_digest:str; issue_receipt_id:str; issue_receipt_digest:str; expiry_evaluation_id:str; expiry_evaluation_digest:str; expiry_evaluation_evaluated_at:str; grant_not_before:str; grant_not_after:str; grant_expiry:str; revocation_receipt_refs:tuple[HostFulfillmentExecutorSourceRef,...]; current_validation_time:str; requested_fulfillment_time:str; requested_scope_labels:tuple[str,...]; target_labels:tuple[str,...]; source_consumption_result_id:str; source_consumption_result_digest:str; source_consumption_receipt_id:str; source_consumption_receipt_digest:str; source_consumption_ledger_id:str; source_consumption_ledger_digest:str; warning_labels:tuple[str,...]; risk_labels:tuple[str,...]; blocked_action_labels:tuple[str,...]; derived_posture:str; schema_version:str=SCHEMA_VERSION; historical_grant_id:str=""; historical_grant_digest:str=""; historical_verification_id:str=""; historical_verification_digest:str=""; historical_ledger_id:str=""; historical_ledger_digest:str=""; historical_expiry_evaluation_id:str=""; historical_expiry_evaluation_digest:str=""; current_snapshot_id:str=""; current_snapshot_digest:str=""; current_underlying_ledger_id:str=""; current_underlying_ledger_digest:str=""; current_issue_receipt_refs:tuple[HostFulfillmentExecutorSourceRef,...]=(); current_host_local_revocation_receipt_refs:tuple[HostFulfillmentExecutorSourceRef,...]=(); current_no_revocation_manifest_digest:str=""; verification_status:str=""; expiry_status:str=""; historical_current_ledger_divergence:str="unavailable"
    def to_dict(self)->dict[str,Any]: return asdict(self)

@dataclass(frozen=True)
class HostFulfillmentExecutorReadinessRequest:
    request_id:str; digest:str; correlation_id:str; consumption_result_id:str; consumption_result_digest:str; requested_fulfillment_domain:str; executor_domain:str; backend_class:str; backend_label:str; requested_scope_labels:tuple[str,...]; target_labels:tuple[str,...]; requested_time:str; current_grant_posture:str; current_grant_evidence_id:str; current_grant_evidence_digest:str; missing_future_gates:tuple[str,...]; blocked_actions:tuple[str,...]; created_at:str= "1970-01-01T00:00:00+00:00"; schema_version:str=SCHEMA_VERSION
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
    requested_fulfillment_domain:str=""; executor_domain:str=""; backend_class:str=""
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

@dataclass(frozen=True)
class HostFulfillmentExecutorReadinessPersistedBundleValidation:
    """Authoritative result of decoding and validating a persisted v1 bundle."""
    ok:bool; findings:tuple[str,...]; evaluation:HostFulfillmentExecutorReadinessEvaluation|None; current_grant_evidence:HostFulfillmentExecutorCurrentGrantEvidence|None; bundle_digest:str; request_id:str; request_digest:str
    def to_dict(self)->dict[str,Any]:
        return {"ok":self.ok,"findings":self.findings,"evaluation":self.evaluation.to_dict() if self.evaluation else None,"current_grant_evidence":self.current_grant_evidence.to_dict() if self.current_grant_evidence else None,"bundle_digest":self.bundle_digest,"request_id":self.request_id,"request_digest":self.request_digest}

_PERSISTED_FILES={"readiness_request.json","current_grant_evidence.json","source_manifest.json","metadata_admission.json","runtime_plan.json","prerequisites.json","executor_contract.json","backend_declaration.json","precondition_manifest.json","dry_run_plan.json","admission_packet.json","readiness_receipt.json","runtime_receipt.json","validation_findings.json","summary.json","README.md"}

def validate_persisted_readiness_bundle(bundle_root:str|Path, *, expected_bundle_digest:str|None=None, expected_request_id:str|None=None, expected_request_digest:str|None=None, expected_evidence_digest:str|None=None)->HostFulfillmentExecutorReadinessPersistedBundleValidation:
    """Load persisted records from disk and validate their complete custody chain."""
    f:list[str]=[]; root=Path(bundle_root); manifest:dict[str,Any]={}; decoded:dict[str,Any]={}
    if root.is_symlink(): f.append("symlink_bundle_root_rejected")
    if ".." in root.parts: f.append("bundle_path_traversal_rejected")
    try: resolved=root.resolve(strict=True)
    except (OSError,RuntimeError): resolved=root.absolute(); f.append("bundle_root_missing")
    if not root.is_dir(): f.append("bundle_root_not_directory")
    try:
        if resolved == Path.cwd().resolve() or resolved.is_relative_to(Path.cwd().resolve()): f.append("repository_local_runtime_root_rejected")
    except OSError: f.append("bundle_root_resolution_failed")
    if f: return HostFulfillmentExecutorReadinessPersistedBundleValidation(False,tuple(sorted(set(f))),None,None,"","","")
    try:
        manifest=json.loads((resolved/"bundle_manifest.json").read_text(encoding="utf-8"))
    except Exception as exc:
        return HostFulfillmentExecutorReadinessPersistedBundleValidation(False,("bundle_manifest_decode_failed:"+type(exc).__name__,),None,None,"","","")
    entries=manifest.get("files")
    if manifest.get("schema_version") != SCHEMA_VERSION: f.append("bundle_manifest_schema_version_mismatch")
    if manifest.get("artifact_kind") != "host_fulfillment_executor_readiness_bundle_manifest": f.append("bundle_manifest_artifact_kind_mismatch")
    if not isinstance(entries,list): f.append("bundle_manifest_entries_malformed"); entries=[]
    seen:list[str]=[]
    for entry in entries:
        if not isinstance(entry,dict): f.append("bundle_manifest_entry_malformed"); continue
        rel=entry.get("relative_filename")
        if not isinstance(rel,str) or not rel or Path(rel).name != rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
            f.append("manifest_path_rejected:"+str(rel)); continue
        seen.append(rel)
        if rel not in _PERSISTED_FILES: f.append("unexpected_manifested_artifact:"+rel)
        target=resolved/rel
        if target.is_symlink(): f.append("symlink_manifested_artifact_rejected:"+rel); continue
        try:
            if target.resolve(strict=False).parent != resolved: f.append("manifest_path_escape:"+rel); continue
        except OSError: f.append("manifest_path_escape:"+rel); continue
        if not target.is_file(): f.append("manifested_file_missing:"+rel); continue
        raw=target.read_bytes()
        if entry.get("size") != len(raw): f.append("manifest_size_mismatch:"+rel)
        if entry.get("digest") != "sha256:"+hashlib.sha256(raw).hexdigest(): f.append("manifest_digest_mismatch:"+rel)
        if entry.get("schema_version") != SCHEMA_VERSION: f.append("manifest_entry_schema_version_mismatch:"+rel)
        if entry.get("artifact_kind") != Path(rel).stem: f.append("manifest_entry_artifact_kind_mismatch:"+rel)
        if rel.endswith(".json"):
            try: decoded[rel]=json.loads(raw.decode("utf-8"))
            except Exception: f.append("manifested_json_decode_failed:"+rel)
    if len(seen)!=len(set(seen)): f.append("duplicate_manifest_entry")
    for name in sorted(_PERSISTED_FILES-set(seen)): f.append("missing_manifest_entry:"+name)
    actual={p.name for p in resolved.iterdir() if p.is_file() and p.name != "bundle_manifest.json" and p.suffix in {".json",".md"}}
    for name in sorted(actual-set(seen)): f.append("unexpected_unmanifested_artifact:"+name)
    for name in sorted(set(seen)-actual): f.append("manifested_file_missing:"+name)
    bundle_digest=str(manifest.get("bundle_digest", ""))
    if bundle_digest != _sha({"files":entries}): f.append("bundle_manifest_digest_mismatch")
    if expected_bundle_digest and bundle_digest != expected_bundle_digest: f.append("expected_bundle_digest_mismatch")
    req=decoded.get("readiness_request.json",{}); plan=decoded.get("runtime_plan.json",{}); evidence=decoded.get("current_grant_evidence.json",{})
    request_id=str(req.get("request_id", "")) if isinstance(req,dict) else ""; request_digest=str(req.get("digest", "")) if isinstance(req,dict) else ""
    for filename,payload in decoded.items():
        entry=next((e for e in entries if isinstance(e,dict) and e.get("relative_filename")==filename),{})
        if isinstance(payload,dict):
            semantic=str(payload.get("request_id") or payload.get("evidence_id") or payload.get("plan_id") or payload.get("contract_id") or payload.get("declaration_id") or payload.get("manifest_id") or payload.get("packet_id") or payload.get("receipt_id") or Path(filename).stem)
        else: semantic=Path(filename).stem
        if entry.get("semantic_id") != semantic: f.append("manifest_entry_semantic_id_mismatch:"+filename)
    if not isinstance(req,dict) or req.get("schema_version") != SCHEMA_VERSION: f.append("request_schema_version_mismatch")
    elif req.get("digest") != digest_record(req): f.append("request_digest_mismatch")
    if expected_request_id and request_id != expected_request_id: f.append("expected_request_id_mismatch")
    if expected_request_digest and request_digest != expected_request_digest: f.append("expected_request_digest_mismatch")
    if not isinstance(plan,dict) or plan.get("digest") != digest_record(plan): f.append("runtime_plan_digest_mismatch")
    if decoded.get("source_manifest.json") != plan: f.append("source_manifest_runtime_plan_mismatch")
    if isinstance(plan,dict):
        if (plan.get("request_id"),plan.get("request_digest")) != (request_id,request_digest): f.append("runtime_plan_request_mismatch")
        if tuple(plan.get("prerequisite_labels",())) != tuple(sorted(REQUIRED_EXECUTOR_LABELS)): f.append("runtime_plan_prerequisite_labels_mismatch")
        if tuple(plan.get("blocked_actions",())) != tuple(req.get("blocked_actions",())): f.append("runtime_plan_blocked_actions_mismatch")
        refs=plan.get("source_refs",[]); keys=[(x.get("kind"),x.get("ref_id"),x.get("digest")) for x in refs if isinstance(x,dict)] if isinstance(refs,list) else []
        if len(keys)!=len(set(keys)) or len(keys)!=len(refs): f.append("runtime_plan_source_refs_not_unique")
        expected_refs={"consumption_result":(req.get("consumption_result_id"),req.get("consumption_result_digest")),"current_grant_evidence":(evidence.get("evidence_id"),evidence.get("digest"))}
        for kind,pair in expected_refs.items():
            if not any(k==kind and (i,d)==pair for k,i,d in keys): f.append("runtime_plan_source_ref_mismatch:"+kind)
        refmap={str(k):(str(i),str(d)) for k,i,d in keys}
        request_sem={"consumption_result_digest":req.get("consumption_result_digest"),"receipt_id":refmap.get("consumption_receipt",("",""))[0],"receipt_digest":refmap.get("consumption_receipt",("",""))[1],"ledger_digest":refmap.get("consumption_ledger",("",""))[1],"requested_fulfillment_domain":req.get("requested_fulfillment_domain"),"executor_domain":req.get("executor_domain"),"backend_class":req.get("backend_class"),"backend_label":req.get("backend_label"),"scope":req.get("requested_scope_labels",()),"targets":req.get("target_labels",()),"time":req.get("requested_time"),"grant_posture":req.get("current_grant_posture"),"blocked":req.get("blocked_actions",())}
        if req.get("request_id") != _id("hfer_request_",request_sem): f.append("request_semantic_id_mismatch")
        plan_sem={"request":request_digest,"refs":refs,"labels":sorted(REQUIRED_EXECUTOR_LABELS),"blocked":req.get("blocked_actions",()),"no_authority":NO_AUTHORITY}
        if plan.get("plan_id") != _id("hfer_plan_",plan_sem): f.append("runtime_plan_semantic_id_mismatch")
    if not isinstance(evidence,dict) or evidence.get("digest") != digest_record(evidence): f.append("current_grant_evidence_digest_mismatch")
    elif evidence.get("evidence_id") != _id("hfer_current_grant_",{**evidence,"evidence_id":"","digest":""}): f.append("current_grant_evidence_semantic_id_mismatch")
    if expected_evidence_digest and evidence.get("digest") != expected_evidence_digest: f.append("expected_current_grant_evidence_digest_mismatch")
    if isinstance(req,dict) and (req.get("current_grant_evidence_id"),req.get("current_grant_evidence_digest")) != (evidence.get("evidence_id"),evidence.get("digest")): f.append("request_current_grant_evidence_mismatch")
    if isinstance(req,dict) and (tuple(req.get("requested_scope_labels",())),tuple(req.get("target_labels",())),req.get("requested_time")) != (tuple(evidence.get("requested_scope_labels",())),tuple(evidence.get("target_labels",())),evidence.get("requested_fulfillment_time")): f.append("request_current_grant_scope_time_mismatch")
    admission=decoded.get("metadata_admission.json",{})
    if not isinstance(admission,dict) or admission.get("outcome") != "allow" or admission.get("final_disposition") != "allow": f.append("metadata_admission_not_allowed")
    else:
        if admission.get("authority_class") not in {AuthorityClass.PROPOSAL_EVALUATION,AuthorityClass.PROPOSAL_EVALUATION.value}: f.append("metadata_admission_authority_mismatch")
        if admission.get("action_kind") != "host_fulfillment_executor_contract_readiness_metadata_evaluation": f.append("metadata_admission_action_mismatch")
        if admission.get("lifecycle_phase") != "maintenance" or admission.get("target_subsystem") != "host_fulfillment_executor_readiness": f.append("metadata_admission_scope_mismatch")
        if admission.get("correlation_id") != req.get("correlation_id"): f.append("metadata_admission_correlation_mismatch")
        details=admission.get("details") or admission.get("request_details") or admission.get("metadata") or {}
        if isinstance(details,dict):
            for key,val in (("readiness_request_id",request_id),("readiness_request_digest",request_digest),("runtime_plan_id",plan.get("plan_id")),("runtime_plan_digest",plan.get("digest")),("current_grant_evidence_id",evidence.get("evidence_id")),("current_grant_evidence_digest",evidence.get("digest"))):
                if key in details and details.get(key)!=val: f.append("metadata_admission_binding_mismatch:"+key)
    prereqs=decoded.get("prerequisites.json",[])
    labels=[str(x.get("label", "")) for x in prereqs if isinstance(x,dict)] if isinstance(prereqs,list) else []
    if len(labels)!=len(set(labels)): f.append("duplicate_prerequisite_label")
    if tuple(sorted(labels)) != tuple(sorted(REQUIRED_EXECUTOR_LABELS)): f.append("prerequisite_label_set_mismatch")
    objects=[("executor_contract.json",validate_fulfillment_executor_contract),("backend_declaration.json",validate_executor_backend_declaration),("precondition_manifest.json",validate_executor_precondition_manifest),("dry_run_plan.json",validate_executor_dry_run_plan),("admission_packet.json",validate_executor_admission_packet),("readiness_receipt.json",validate_executor_contract_readiness_receipt)]
    for filename,validator in objects:
        payload=decoded.get(filename,{})
        try:
            findings=validator(payload).findings
            f.extend(filename+":"+x for x in findings)
        except Exception as exc: f.append(filename+":validator_failed:"+type(exc).__name__)
    chain=[decoded.get(x,{}) for x in ("executor_contract.json","backend_declaration.json","precondition_manifest.json","dry_run_plan.json","admission_packet.json","readiness_receipt.json")]
    contract,declaration,precondition,dryrun,packet,ready=chain
    for payload,label in ((contract,"contract"),(precondition,"precondition_manifest"),(packet,"admission_packet")):
        if isinstance(payload,dict) and (payload.get("source_consumption_receipt_id"),payload.get("source_consumption_receipt_digest")) != (evidence.get("source_consumption_receipt_id"),evidence.get("source_consumption_receipt_digest")): f.append(label+":source_consumption_receipt_mismatch")
    bindings=((declaration,"contract",contract),(precondition,"contract",contract),(dryrun,"contract",contract),(packet,"contract",contract),(packet,"backend_declaration",declaration),(packet,"precondition_manifest",precondition),(packet,"dry_run_plan",dryrun),(ready,"contract",contract),(ready,"backend_declaration",declaration),(ready,"precondition_manifest",precondition),(ready,"dry_run_plan",dryrun),(ready,"admission_packet",packet))
    def parent_id(prefix:str,o:Mapping[str,Any])->str:
        return str(o.get({"backend_declaration":"declaration_id","precondition_manifest":"manifest_id","dry_run_plan":"plan_id","admission_packet":"packet_id","readiness_receipt":"receipt_id"}.get(prefix,prefix+"_id"),""))
    for child,prefix,parent in bindings:
        if isinstance(child,dict) and isinstance(parent,dict) and ((prefix+"_id" in child and child.get(prefix+"_id")!=parent_id(prefix,parent)) or (prefix+"_digest" in child and child.get(prefix+"_digest")!=parent.get("digest"))): f.append("lineage_binding_mismatch:"+prefix)
    runtime=decoded.get("runtime_receipt.json",{})
    if not isinstance(runtime,dict) or runtime.get("digest") != digest_record(runtime): f.append("runtime_receipt_digest_mismatch")
    else:
        for prefix,parent in (("request",req),("contract",contract),("admission_packet",packet),("readiness_receipt",ready)):
            if runtime.get(prefix+"_id") != parent_id(prefix,parent) or runtime.get(prefix+"_digest") != parent.get("digest"): f.append("runtime_receipt_parent_mismatch:"+prefix)
    try:
        request_record=HostFulfillmentExecutorReadinessRequest(**{**req,"requested_scope_labels":tuple(req.get("requested_scope_labels",())),"target_labels":tuple(req.get("target_labels",())),"missing_future_gates":tuple(req.get("missing_future_gates",())),"blocked_actions":tuple(req.get("blocked_actions",()))})
        plan_record=HostFulfillmentExecutorReadinessPlan(**{**plan,"source_refs":tuple(HostFulfillmentExecutorSourceRef(**x) for x in plan.get("source_refs",())),"prerequisite_labels":tuple(plan.get("prerequisite_labels",())),"blocked_actions":tuple(plan.get("blocked_actions",()))})
        ev=HostFulfillmentExecutorReadinessEvaluation(str(runtime.get("posture","")),tuple(decoded.get("validation_findings.json",{}).get("findings",())),request_record,plan_record,admission,tuple(HostFulfillmentExecutorPrerequisiteRecord(**x) for x in prereqs),contract,declaration,precondition,dryrun,packet,ready,HostFulfillmentExecutorReadinessReceipt(**runtime),True,False,0,0)
        f.extend(validate_route_consistency(ev))
        if ev.findings: f.append("persisted_positive_bundle_has_findings")
        for payload in (req,plan,evidence,admission,contract,declaration,precondition,dryrun,packet,ready,runtime):
            if isinstance(payload,dict):
                for key in NO_AUTHORITY:
                    if payload.get(key) is True or (isinstance(payload.get("no_authority"),dict) and payload["no_authority"].get(key) is True): f.append("authority_flag_true:"+key)
        current=HostFulfillmentExecutorCurrentGrantEvidence(**{**evidence,"revocation_receipt_refs":tuple(HostFulfillmentExecutorSourceRef(**x) for x in evidence.get("revocation_receipt_refs",())),"requested_scope_labels":tuple(evidence.get("requested_scope_labels",())),"target_labels":tuple(evidence.get("target_labels",())),"warning_labels":tuple(evidence.get("warning_labels",())),"risk_labels":tuple(evidence.get("risk_labels",())),"blocked_action_labels":tuple(evidence.get("blocked_action_labels",())),"current_issue_receipt_refs":tuple(HostFulfillmentExecutorSourceRef(**x) for x in evidence.get("current_issue_receipt_refs",())),"current_host_local_revocation_receipt_refs":tuple(HostFulfillmentExecutorSourceRef(**x) for x in evidence.get("current_host_local_revocation_receipt_refs",()))})
    except Exception as exc:
        f.append("persisted_bundle_decode_failed:"+type(exc).__name__); ev=None; current=None
    findings=tuple(sorted(set(f)))
    return HostFulfillmentExecutorReadinessPersistedBundleValidation(not findings,findings,ev if not findings else None,current if not findings else None,bundle_digest,request_id,request_digest)


def _host_snapshot_digest(snapshot: Mapping[str, Any]) -> str:
    return host_local_digest_record(snapshot)

def _canonical_empty_revocation_digest(grant_id: str, snapshot_id: str, snapshot_digest: str) -> str:
    return _sha({"kind":"current_snapshot_applicable_revocation_set","grant_id":grant_id,"snapshot_id":snapshot_id,"snapshot_digest":snapshot_digest,"local_revocations":[],"host_local_revocations":[]})

def validate_current_authority_snapshot(snapshot: HostLocalAuthorizationLedgerSnapshot | Mapping[str, Any], *, grant_id: str, grant_digest: str, supplied_expiry_digest: str | None = None) -> tuple[dict[str, Any], tuple[str, ...]]:
    p=_dict(snapshot); f: list[str]=[]
    if p.get("schema_version") != "host_local_authorization_runtime.v1": f.append("snapshot:unknown_schema")
    if p.get("digest") != _host_snapshot_digest(p): f.append("snapshot:digest_mismatch")
    ledger=_dict(p.get("ledger", {})); grants=[_dict(x) for x in ledger.get("grant_records",())]; revs=[_dict(x) for x in ledger.get("revocation_receipts",())]; exps=[_dict(x) for x in ledger.get("expiry_evaluations",())]; issues=[_dict(x) for x in p.get("issue_receipts",())]; host_revs=[_dict(x) for x in p.get("revocation_receipts",())]
    if validate_local_authorization_grant_ledger(ledger).findings: f += list(validate_local_authorization_grant_ledger(ledger).findings)
    if ledger.get("digest") != local_authorization_grant_ledger_digest(ledger): f.append("ledger:digest_mismatch")
    seen: dict[str,str]={}
    for g in grants:
        if validate_local_authorization_grant(g).findings: f += list(validate_local_authorization_grant(g).findings)
        if g.get("digest") != local_authorization_grant_digest(g): f.append("grant:digest_mismatch")
        prev=seen.setdefault(str(g.get("grant_id")), str(g.get("digest")))
        if prev != g.get("digest"): f.append("duplicate_grant_id_different_bytes")
    rseen: dict[str,str]={}
    for r in revs:
        if validate_local_authorization_grant_revocation_receipt(r).findings: f += list(validate_local_authorization_grant_revocation_receipt(r).findings)
        if r.get("digest") != local_authorization_grant_revocation_receipt_digest(r): f.append("revocation:digest_mismatch")
        prev=rseen.setdefault(str(r.get("receipt_id")), str(r.get("digest")))
        if prev != r.get("digest"): f.append("duplicate_revocation_id_different_bytes")
    eseen: dict[str,str]={}
    for e in exps:
        if validate_local_authorization_grant_expiry_evaluation(e).findings: f += list(validate_local_authorization_grant_expiry_evaluation(e).findings)
        if e.get("digest") != local_authorization_grant_expiry_evaluation_digest(e): f.append("expiry:digest_mismatch")
        prev=eseen.setdefault(str(e.get("evaluation_id")), str(e.get("digest")))
        if prev != e.get("digest"): f.append("duplicate_expiry_id_different_bytes")
    for i in issues:
        if i.get("digest") != host_local_digest_record(i): f.append("issue_receipt:digest_mismatch")
        if i.get("grant_id") == grant_id and i.get("grant_digest") != grant_digest: f.append("issue_receipt_grant_digest_mismatch")
    for hr in host_revs:
        if hr.get("digest") != host_local_digest_record(hr): f.append("host_local_revocation_receipt:digest_mismatch")
        linked=[r for r in revs if r.get("receipt_id")==hr.get("local_revocation_receipt_id")]
        if not linked: f.append("host_local_revocation_missing_local_receipt")
        elif linked[0].get("digest") != hr.get("local_revocation_receipt_digest"): f.append("host_local_revocation_local_digest_mismatch")
    exact=[g for g in grants if g.get("grant_id")==grant_id]
    if not any(g.get("digest")==grant_digest for g in exact): f.append("snapshot_missing_exact_historical_grant"); f.append("ledger_missing_exact_grant")
    if not p.get("legacy_snapshot") and not any(i.get("grant_id")==grant_id and i.get("grant_digest")==grant_digest for i in issues): f.append("snapshot_missing_matching_issue_receipt")
    active_ids={g.get("grant_id") for g in grants if str(g.get("grant_status","")).startswith("local_authorization_grant_active")}
    revoked_ids={r.get("grant_id") for r in revs if r.get("revocation_status")=="local_authorization_revocation_recorded"}
    expired_ids={e.get("grant_id") for e in exps if e.get("expiry_status")=="local_authorization_expiry_expired"}
    active=len(active_ids-revoked_ids-expired_ids); revoked=len(revoked_ids); expired=len(expired_ids); conflicted=sum(1 for g in grants if g.get("grant_status")=="local_authorization_grant_contradicted")
    if (p.get("active_count"),p.get("revoked_count"),p.get("expired_count"),p.get("conflicted_count")) != (active,revoked,expired,conflicted): f.append("snapshot_count_mismatch")
    if (ledger.get("active_grant_count"),ledger.get("revoked_grant_count"),ledger.get("expired_grant_count")) != (active,revoked,expired): f.append("ledger_count_mismatch")
    statuses={g.get("grant_status") for g in grants}|{r.get("revocation_status") for r in revs}|{e.get("expiry_status") for e in exps}
    expected="local_authorization_grant_ledger_current"
    if any("contradicted" in str(x) for x in statuses): expected="local_authorization_grant_ledger_contradicted"
    elif any("incomplete" in str(x) or "missing" in str(x) for x in statuses): expected="local_authorization_grant_ledger_incomplete"
    elif any("blocked" in str(x) for x in statuses): expected="local_authorization_grant_ledger_blocked"
    if ledger.get("ledger_status") != expected and not (expected.endswith("current") and ledger.get("ledger_status")=="local_authorization_grant_ledger_current_with_warnings"): f.append("ledger_status_mismatch")
    applicable_revs=[r for r in revs if r.get("grant_id")==grant_id]
    applicable_host_revs=[hr for hr in host_revs if hr.get("grant_id")==grant_id]
    if len(applicable_host_revs) != len(applicable_revs): f.append("snapshot_revocation_set_host_local_mismatch")
    applicable_exps=[e for e in exps if e.get("grant_id")==grant_id]
    if supplied_expiry_digest and not any(e.get("digest")==supplied_expiry_digest for e in applicable_exps): f.append("current_expiry_evaluation_not_in_snapshot")
    current_expiry=max(applicable_exps, key=lambda x:(str(x.get("evaluated_at","")), str(x.get("digest","")))) if applicable_exps else {}
    if supplied_expiry_digest and current_expiry and current_expiry.get("digest") != supplied_expiry_digest: f.append("newer_expiry_evaluation_omitted")
    return {"snapshot":p,"ledger":ledger,"grant":next((g for g in exact if g.get("digest")==grant_digest), exact[0] if exact else {}),"revocations":applicable_revs,"host_revocations":applicable_host_revs,"issues":[i for i in issues if i.get("grant_id")==grant_id],"expiry":current_expiry,"no_revocation_digest":_canonical_empty_revocation_digest(grant_id,str(p.get("snapshot_id","")),str(p.get("digest","")))}, tuple(sorted(set(f)))

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
    requested_domain=str(rec.get("requested_fulfillment_domain", ""))
    domain, backend=resolve_canonical_executor_route(requested_domain)
    if executor_domain is not None and executor_domain != domain: raise ValueError("noncanonical_executor_domain_override")
    if backend_class is not None and backend_class != backend: raise ValueError("noncanonical_backend_class_override")
    sem={"consumption_result_digest":_sha(result.to_dict()),"receipt_id":rec.get("receipt_id"),"receipt_digest":rec.get("digest"),"ledger_digest":_dict(result.ledger or {}).get("digest"),"requested_fulfillment_domain":requested_domain,"executor_domain":domain,"backend_class":backend,"backend_label":backend_label,"scope":tuple(env.get("requested_scope_labels",())),"targets":tuple(env.get("target_labels",())),"time":env.get("requested_time"),"grant_posture":current_grant_posture,"blocked":tuple(sorted(rec.get("blocked_actions",()))) }
    rid=_id("hfer_request_",sem)
    req=HostFulfillmentExecutorReadinessRequest(rid,"",str(env.get("idempotency_key") or rid),_id("hfac_result_",_sha(result.to_dict())),_sha(result.to_dict()),requested_domain,domain,backend,backend_label,tuple(env.get("requested_scope_labels",())),tuple(env.get("target_labels",())),str(env.get("requested_time")),current_grant_posture,"","",("control_plane_admission_required_for_future_execution","effect_receipt_required_for_future_execution","executor_identity_required"),tuple(sorted(rec.get("blocked_actions",()))),created_at)
    return replace(req,digest=digest_record(req))

def validate_consumption_source(result:HostFulfillmentAuthorizationConsumptionResult)->HostFulfillmentExecutorReadinessValidationResult:
    f=[]
    if not isinstance(result, HostFulfillmentAuthorizationConsumptionResult): return HostFulfillmentExecutorReadinessValidationResult(False,("strict_typed_consumption_result_required",))
    d=result.to_dict(); rec=_dict(result.consumption_receipt or {}); entry=_dict(result.ledger_entry or {}); led=_dict(result.ledger or {})
    if result.status!="recorded": f.append("denial_only_result_rejected")
    if not rec: f.append("missing_successful_consumption_receipt")
    if rec and not rec.get("authorization_consumed_for_future_fulfillment",False): f.append("authorization_not_consumed_for_future_fulfillment")
    if rec and rec.get("digest") != fulfillment_authorization_consumption_receipt_digest(rec): f.append("consumption_receipt_digest_unverified")
    if rec:
        try: resolve_canonical_executor_route(str(rec.get("requested_fulfillment_domain", "")))
        except ValueError: f.append("unknown_requested_fulfillment_domain")
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

def _parse_time_label(value:str)->datetime:
    text=str(value).removeprefix("expires:").removeprefix("not_before:").removeprefix("not_after:")
    return datetime.fromisoformat(text.replace("Z","+00:00"))

def _bounds(grant:Mapping[str,Any])->tuple[str,str,str]:
    nbs=[str(x).removeprefix("not_before:") for x in grant.get("granted_time_bounds",()) if str(x).startswith("not_before:")]
    nas=[str(x).removeprefix("not_after:") for x in grant.get("granted_time_bounds",()) if str(x).startswith("not_after:")]
    return (max(nbs) if nbs else "", min(nas) if nas else "", str(grant.get("expiry_label","")).removeprefix("expires:"))

def build_current_grant_evidence(result:HostFulfillmentAuthorizationConsumptionResult, *, grant:LocalAuthorizationGrant, verification:LocalAuthorizationGrantVerification, authorization_ledger:LocalAuthorizationGrantLedger|None=None, expiry_evaluation:LocalAuthorizationGrantExpiryEvaluation|None=None, current_snapshot:HostLocalAuthorizationLedgerSnapshot|Mapping[str,Any]|None=None, revocation_receipts:Sequence[LocalAuthorizationGrantRevocationReceipt]=(), validation_time:str="1970-01-01T00:00:00+00:00", ledger_predecessor_digest:str|None=None)->tuple[HostFulfillmentExecutorCurrentGrantEvidence|None, tuple[str,...]]:
    findings:list[str]=[]; g=_dict(grant); v=_dict(verification); env=_dict(result.envelope); src=_dict(result.source); rec=_dict(result.consumption_receipt or {}); led=_dict(result.ledger or {})
    if current_snapshot is None:
        if authorization_ledger is None or expiry_evaluation is None:
            return None, ("current_authoritative_snapshot_required",)
        l=_dict(authorization_ledger); e=_dict(expiry_evaluation); snap={"schema_version":"host_local_authorization_runtime.v1","snapshot_id":_id("hlas_legacy_",l.get("digest","")),"digest":"","ledger":l,"issue_receipts":(),"revocation_receipts":(),"active_count":l.get("active_grant_count",0),"expired_count":l.get("expired_grant_count",0),"revoked_count":l.get("revoked_grant_count",0),"conflicted_count":0,"created_at":validation_time,"metadata_only":True,"fulfillment_granted":False,"effect_performed":False,"host_mutation_performed":False,"legacy_snapshot":True}
        snap["digest"]=_host_snapshot_digest(snap); current_snapshot=snap
    supplied_expiry_digest=_dict(expiry_evaluation).get("digest") if expiry_evaluation is not None else None
    sv, sf = validate_current_authority_snapshot(current_snapshot, grant_id=str(src.get("grant_id") or g.get("grant_id")), grant_digest=str(src.get("grant_digest") or g.get("digest")), supplied_expiry_digest=supplied_expiry_digest)
    findings += list(sf)
    l=sv.get("ledger",{}); e=sv.get("expiry") or (_dict(expiry_evaluation) if expiry_evaluation is not None else {})
    if expiry_evaluation is not None and _dict(expiry_evaluation).get("grant_id") != g.get("grant_id"):
        findings.append("expiry_evaluation_for_another_grant")
    snap=sv.get("snapshot",{})
    if sv.get("grant") and sv["grant"].get("digest") != g.get("digest"): findings.append("current_grant_argument_not_snapshot_exact_grant")
    if validate_local_authorization_grant(grant).findings: findings += list(validate_local_authorization_grant(grant).findings)
    if g.get("digest") != local_authorization_grant_digest(g): findings.append("forged_grant_digest")
    if validate_local_authorization_grant_verification(verification).findings: findings += list(validate_local_authorization_grant_verification(verification).findings)
    if v.get("digest") != local_authorization_grant_verification_digest(v): findings.append("forged_verification_digest")
    if v.get("grant_id") != g.get("grant_id"): findings.append("verification_for_another_grant")
    if src.get("grant_id") != g.get("grant_id") or src.get("grant_digest") != g.get("digest"): findings.append("current_grant_differs_from_historical_consumed_grant")
    # Historical verification/ledger/expiry may differ from the current snapshot; record divergence instead of blocking.
    ledger_divergence="expected" if src.get("ledger_digest") != l.get("digest") else "same"
    if set(env.get("requested_scope_labels",()))-set(g.get("granted_scope_labels",())): findings.append("scope_expansion")
    vstatus=str(v.get("verification_status",""))
    if vstatus not in {"local_authorization_verification_valid","local_authorization_verification_valid_with_conditions"}: findings.append("current_verification_"+vstatus.removeprefix("local_authorization_verification_"))
    if set(env.get("requested_scope_labels",()))-set(v.get("checked_scope_labels",())): findings.append("verification_scope_mismatch")
    if tuple(v.get("missing_labels",())): findings.append("verification_missing_labels")
    applicable_revs=tuple(sv.get("revocations",()))
    if revocation_receipts:
        supplied={_dict(r).get("digest") for r in revocation_receipts}; actual={r.get("digest") for r in applicable_revs}
        if not snap.get("legacy_snapshot") and supplied != actual: findings.append("supplied_revocations_do_not_match_snapshot")
    if applicable_revs and not revocation_receipts:
        findings.append("caller_revocation_omission_ignored")
    if revocation_receipts and snap.get("legacy_snapshot"):
        applicable_revs=tuple(_dict(r) for r in revocation_receipts)
        if any(r.get("revocation_status")=="local_authorization_revocation_recorded" for r in applicable_revs): findings.append("grant_revoked")
    for obj,name in ((g,"grant"),(v,"verification"),(l,"ledger"),(e,"expiry"), *tuple((rr,"revocation") for rr in applicable_revs)):
        od=_dict(obj)
        if any(od.get(flag,False) for flag in ("fulfillment_granted","executor_authorized","execution_ready","effect_performed","host_mutation_performed")): findings.append(name+":forbidden_authority_or_effect_claim")
    nb,na,exp=_bounds(g)
    try:
        cur=_parse_time_label(validation_time); req=_parse_time_label(str(env.get("requested_time"))); expt=_parse_time_label(exp); evat=_parse_time_label(str(e.get("evaluated_at"))) if e else cur
        vtime=_parse_time_label(str(v.get("checked_time_label")))
        if vtime>cur: findings.append("verification_checked_time_in_future")
        if evat>cur: findings.append("future_expiry_evaluation")
        if e and e.get("expiry_status")=="local_authorization_expiry_not_expired" and evat < expt <= cur: findings.append("stale_non_expired_expiry_evidence")
        if nb and req < _parse_time_label(nb): findings.append("not_yet_valid")
        if na and req > _parse_time_label(na): findings.append("request_after_not_after")
        if req > expt or cur > expt or e.get("expiry_status")=="local_authorization_expiry_expired": findings.append("expired_grant")
    except Exception: findings.append("time_parse_failed")
    rev_posture="revoked" if any(r.get("revocation_status")=="local_authorization_revocation_recorded" for r in applicable_revs) else "not_revoked"
    if rev_posture == "revoked" and "revoked" not in vstatus: findings.append("verification_revocation_labels_mismatch")
    posture="currently_active"
    if not g or not v or not l or not e: posture="unavailable"
    elif applicable_revs or vstatus.endswith("revoked"): posture="revoked"
    elif any("contradict" in x or "duplicate_" in x or "mismatch" in x for x in findings): posture="contradicted"
    elif any(x in findings for x in ("stale_non_expired_expiry_evidence","future_expiry_evaluation")): posture="stale"
    elif "expired_grant" in findings or vstatus.endswith("expired"): posture="expired"
    elif "not_yet_valid" in findings: posture="not_yet_valid"
    elif vstatus.endswith("blocked"): posture="blocked"
    elif vstatus.endswith("incomplete"): posture="incomplete"
    elif g.get("grant_status")=="local_authorization_grant_active_with_conditions" or vstatus=="local_authorization_verification_valid_with_conditions" or g.get("warning_codes"): posture="active_with_conditions"
    elif findings: posture="contradicted"
    revrefs=tuple(HostFulfillmentExecutorSourceRef(str(r.get("receipt_id")),str(r.get("digest")),"current_revocation_receipt") for r in applicable_revs)
    hostrevrefs=tuple(HostFulfillmentExecutorSourceRef(str(r.get("receipt_id")),str(r.get("digest")),"current_host_local_revocation_receipt") for r in sv.get("host_revocations",()))
    issuerefs=tuple(HostFulfillmentExecutorSourceRef(str(r.get("receipt_id")),str(r.get("digest")),"current_issue_receipt") for r in sv.get("issues",()))
    ev0=HostFulfillmentExecutorCurrentGrantEvidence("","",str(g.get("grant_id","")),str(g.get("digest","")),str(v.get("verification_id","")),str(v.get("digest","")),str(l.get("ledger_id","")),str(l.get("digest","")),ledger_predecessor_digest or str(src.get("ledger_predecessor_digest","")),str(src.get("issue_receipt_id","")),str(src.get("issue_receipt_digest","")),str(e.get("evaluation_id","")),str(e.get("digest","")),str(e.get("evaluated_at","")),nb,na,exp,revrefs,validation_time,str(env.get("requested_time","")),tuple(env.get("requested_scope_labels",())),tuple(env.get("target_labels",())),_id("hfac_result_",_sha(result.to_dict())),_sha(result.to_dict()),str(rec.get("receipt_id","")),str(rec.get("digest","")),"host_fulfillment_authorization_consumption_ledger",str(led.get("digest","")),tuple(g.get("warning_codes",()))+tuple(e.get("warning_codes",()))+tuple(v.get("warning_codes",())),tuple(g.get("risk_codes",()))+tuple(e.get("risk_codes",()))+tuple(v.get("risk_codes",())),tuple(g.get("blocked_actions",())),posture,historical_grant_id=str(src.get("grant_id","")),historical_grant_digest=str(src.get("grant_digest","")),historical_verification_id=str(src.get("verification_id","")),historical_verification_digest=str(src.get("verification_digest","")),historical_ledger_id=str(src.get("ledger_id","")),historical_ledger_digest=str(src.get("ledger_digest","")),historical_expiry_evaluation_id=str(src.get("expiry_evaluation_id","")),historical_expiry_evaluation_digest=str(src.get("expiry_evaluation_digest","")),current_snapshot_id=str(snap.get("snapshot_id","")),current_snapshot_digest=str(snap.get("digest","")),current_underlying_ledger_id=str(l.get("ledger_id","")),current_underlying_ledger_digest=str(l.get("digest","")),current_issue_receipt_refs=issuerefs,current_host_local_revocation_receipt_refs=hostrevrefs,current_no_revocation_manifest_digest=sv.get("no_revocation_digest",""),verification_status=vstatus,expiry_status=str(e.get("expiry_status","")),historical_current_ledger_divergence=ledger_divergence)
    ev0=replace(ev0,evidence_id=_id("hfer_current_grant_",ev0.to_dict()))
    return replace(ev0,digest=digest_record(ev0)), tuple(sorted(set(findings)))

class HostFulfillmentExecutorReadinessRuntimeCoordinator:
    def __init__(self, *, runtime_state_root:str|Path|None=None, kernel:Any|None=None, clock:Callable[[],str]|None=None):
        self.runtime_state_root=Path(runtime_state_root or os.getenv("SENTIENTOS_RUNTIME_STATE_ROOT") or tempfile.gettempdir()+"/sentientos_runtime")
        self.kernel=kernel or get_control_plane_kernel(); self.clock=clock or (lambda:"1970-01-01T00:00:00+00:00"); self.builder_call_count=0; self.admission_call_count=0
    def _root(self)->Path:
        r=(self.runtime_state_root/"host_fulfillment_executor_contract_readiness_runtime").resolve(); r.mkdir(parents=True,exist_ok=True); return r
    def request_metadata_admission(self, req:HostFulfillmentExecutorReadinessRequest, plan:HostFulfillmentExecutorReadinessPlan, result:HostFulfillmentAuthorizationConsumptionResult, evidence:HostFulfillmentExecutorCurrentGrantEvidence)->ControlActionDecision:
        self.admission_call_count+=1
        return self.kernel.admit(ControlActionRequest("host_fulfillment_executor_contract_readiness_metadata_evaluation",AuthorityClass.PROPOSAL_EVALUATION,"operator_invoked_cli","host_fulfillment_executor_readiness",LifecyclePhase.MAINTENANCE,{"correlation_id":req.correlation_id,"readiness_request_id":req.request_id,"readiness_request_digest":req.digest,"consumption_result_digest":req.consumption_result_digest,"consumption_receipt_digest":_dict(result.consumption_receipt or {}).get("digest"),"consumption_ledger_digest":_dict(result.ledger or {}).get("digest"),"runtime_plan_id":plan.plan_id,"runtime_plan_digest":plan.digest,"current_grant_evidence_id":evidence.evidence_id,"current_grant_evidence_digest":evidence.digest,"current_grant_id":evidence.grant_id,"current_grant_digest":evidence.grant_digest,"current_verification_digest":evidence.verification_digest,"current_authorization_ledger_digest":evidence.authorization_ledger_digest,"current_expiry_evaluation_digest":evidence.expiry_evaluation_digest,"current_revocation_receipt_digests":[r.digest for r in evidence.revocation_receipt_refs],"derived_current_grant_posture":evidence.derived_posture,**NO_AUTHORITY}))
    def plan(self, req:HostFulfillmentExecutorReadinessRequest, result:HostFulfillmentAuthorizationConsumptionResult, evidence:HostFulfillmentExecutorCurrentGrantEvidence)->HostFulfillmentExecutorReadinessPlan:
        refs=tuple(HostFulfillmentExecutorSourceRef(i,d,k) for k,i,d in (("consumption_result",req.consumption_result_id,req.consumption_result_digest),("consumption_receipt",str(_dict(result.consumption_receipt or {}).get("receipt_id")),str(_dict(result.consumption_receipt or {}).get("digest"))),("consumption_ledger", "host_fulfillment_authorization_consumption_ledger", str(_dict(result.ledger or {}).get("digest"))),("consumption_ledger_entry", str(_dict(result.ledger_entry or {}).get("entry_id")), str(_dict(result.ledger_entry or {}).get("digest"))),("current_grant", evidence.grant_id, evidence.grant_digest),("current_verification", evidence.verification_id, evidence.verification_digest),("current_authorization_ledger", evidence.authorization_ledger_id, evidence.authorization_ledger_digest),("current_ledger_snapshot", evidence.current_snapshot_id, evidence.current_snapshot_digest),("current_expiry_evaluation", evidence.expiry_evaluation_id, evidence.expiry_evaluation_digest),("current_grant_evidence", evidence.evidence_id, evidence.digest)))
        sem={"request":req.digest,"refs":[r.to_dict() for r in refs],"labels":sorted(REQUIRED_EXECUTOR_LABELS),"blocked":req.blocked_actions,"no_authority":NO_AUTHORITY}
        pl=HostFulfillmentExecutorReadinessPlan(_id("hfer_plan_",sem),"",req.request_id,req.digest,refs,tuple(sorted(REQUIRED_EXECUTOR_LABELS)),req.blocked_actions,True,NO_AUTHORITY)
        return replace(pl,digest=digest_record(pl))
    def evaluate(self, result:HostFulfillmentAuthorizationConsumptionResult, *, output_root:str|Path, grant:LocalAuthorizationGrant|None=None, verification:LocalAuthorizationGrantVerification|None=None, authorization_ledger:LocalAuthorizationGrantLedger|None=None, expiry_evaluation:LocalAuthorizationGrantExpiryEvaluation|None=None, current_snapshot:HostLocalAuthorizationLedgerSnapshot|Mapping[str,Any]|None=None, revocation_receipts:Sequence[LocalAuthorizationGrantRevocationReceipt]=(), ledger_predecessor_digest:str|None=None, backend_label:str="declaration-only-not-loaded", executor_domain:str|None=None, backend_class:str|None=None, current_grant_posture:str|None=None, persist:bool=True)->HostFulfillmentExecutorReadinessEvaluation:
        findings=list(validate_consumption_source(result).findings)+_validate_backend_label(backend_label)
        if not findings:
            try: build_request(result, executor_domain=executor_domain, backend_class=backend_class, backend_label=backend_label)
            except ValueError as exc: findings.append(str(exc))
        route_input_valid=not findings
        missing=[]
        if grant is None: missing.append("current_grant_evidence_missing")
        if verification is None: missing.append("current_grant_verification_evidence_missing")
        if authorization_ledger is None and current_snapshot is None: missing.append("current_authorization_ledger_or_snapshot_evidence_missing")
        if expiry_evaluation is None: missing.append("current_expiry_evaluation_evidence_missing")
        if missing:
            return HostFulfillmentExecutorReadinessEvaluation("unavailable_contract_package",tuple(sorted(set(findings+missing))),None,None,None,(),None,None,None,None,None,None,None,False,False,0,self.admission_call_count)
        assert grant is not None and verification is not None
        evidence, ef = build_current_grant_evidence(result, grant=grant, verification=verification, authorization_ledger=authorization_ledger, expiry_evaluation=expiry_evaluation, current_snapshot=current_snapshot, revocation_receipts=revocation_receipts, validation_time=self.clock(), ledger_predecessor_digest=ledger_predecessor_digest)
        findings += list(ef)
        assert evidence is not None
        if current_grant_posture is not None and current_grant_posture != evidence.derived_posture:
            findings.append("current_grant_posture_expectation_mismatch")
        def blocked_status(posture:str)->str:
            return {"expired":"stale_contract_package","revoked":"blocked_contract_package","stale":"stale_contract_package","contradicted":"contradicted_contract_package","unavailable":"unavailable_contract_package","not_yet_valid":"blocked_contract_package"}.get(posture,"blocked_contract_package")
        active=evidence.derived_posture in {"currently_active","active_with_conditions"}
        if findings or not active:
            status=blocked_status(evidence.derived_posture)
            req=build_request(result,executor_domain=executor_domain,backend_class=backend_class,backend_label=backend_label,current_grant_posture=evidence.derived_posture,created_at=self.clock()) if route_input_valid else None
            prereq=tuple(self._prerequisites(req, evidence, None, None, None, None, current_blocked=True)) if req else ()
            return HostFulfillmentExecutorReadinessEvaluation(status,tuple(sorted(set(findings))),req,None,None,prereq,None,None,None,None,None,None,None,False,False,0,self.admission_call_count)
        req0=build_request(result,executor_domain=executor_domain,backend_class=backend_class,backend_label=backend_label,current_grant_posture=evidence.derived_posture,created_at=self.clock())
        req=replace(req0,current_grant_evidence_id=evidence.evidence_id,current_grant_evidence_digest=evidence.digest)
        req=replace(req,digest=digest_record(req))
        plan=self.plan(req,result,evidence)
        root=Path(output_root).resolve()
        if str(root).startswith(str(Path.cwd().resolve())): return HostFulfillmentExecutorReadinessEvaluation("blocked_contract_package",("repository_local_runtime_root_rejected",),req,plan,None,(),None,None,None,None,None,None,None,False,False,0,self.admission_call_count)
        lock=_LOCKS.setdefault(str(root), threading.Lock())
        semantic={"request":req.digest,"evidence":evidence.digest,"requested_fulfillment_domain":req.requested_fulfillment_domain,"executor_domain":req.executor_domain,"backend_class":req.backend_class,"backend_label":backend_label,"scope":req.requested_scope_labels,"targets":req.target_labels,"time":req.requested_time,"correlation":req.correlation_id}
        with lock:
            replay=self._load_replay(root, req.correlation_id, semantic)
            if replay is not None:
                if replay.get("conflict"):
                    return HostFulfillmentExecutorReadinessEvaluation("contradicted_contract_package",("semantic_replay_conflict",),req,plan,None,(),None,None,None,None,None,None,None,False,False,0,self.admission_call_count)
                validated=validate_persisted_readiness_bundle(replay["bundle"],expected_bundle_digest=str(replay.get("bundle_digest","")),expected_request_id=req.request_id,expected_request_digest=req.digest,expected_evidence_digest=evidence.digest)
                if not validated.ok or validated.evaluation is None:
                    return HostFulfillmentExecutorReadinessEvaluation("contradicted_contract_package",tuple(sorted(set(("semantic_replay_conflict",)+validated.findings))),req,plan,None,(),None,None,None,None,None,None,None,False,False,0,self.admission_call_count)
                return replace(validated.evaluation,replayed=True,builder_call_count=0,admission_call_count=self.admission_call_count)
            adm=self.request_metadata_admission(req,plan,result,evidence); ad=_dict(adm)
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
            prereq=tuple(self._prerequisites(req,evidence,c,b,m,p,current_blocked=False,result=result))
            posture="ready_for_executor_contract_review_with_conditions" if evidence.derived_posture=="active_with_conditions" else "ready_for_executor_contract_review"
            runtime=HostFulfillmentExecutorReadinessReceipt(_id("hfer_receipt_",{"req":req.digest,"evidence":evidence.digest,"contract":c.digest,"packet":a.digest,"rr":rr.digest}),"",posture,req.request_id,req.digest,c.contract_id,c.digest,a.packet_id,a.digest,rr.receipt_id,rr.digest,NO_AUTHORITY,req.requested_fulfillment_domain,req.executor_domain,req.backend_class)
            runtime=replace(runtime,digest=digest_record(runtime))
            ev=HostFulfillmentExecutorReadinessEvaluation(posture,tuple(vf),req,plan,ad,prereq,c.to_dict(),b.to_dict(),m.to_dict(),p.to_dict(),a.to_dict(),rr.to_dict(),runtime,False,False,self.builder_call_count,self.admission_call_count)
            route_findings=validate_route_consistency(ev)
            if route_findings:
                return replace(ev,status="contradicted_contract_package",findings=route_findings,persisted=False)
            if persist: ev=replace(ev,persisted=self._persist(root,ev,evidence,semantic))
            return ev

    def _prerequisites(self, req:HostFulfillmentExecutorReadinessRequest|None, evidence:HostFulfillmentExecutorCurrentGrantEvidence, contract:Any|None, backend:Any|None, manifest:Any|None, dryrun:Any|None, *, current_blocked:bool, result:HostFulfillmentAuthorizationConsumptionResult|None=None)->Sequence[HostFulfillmentExecutorPrerequisiteRecord]:
        rec=_dict(result.consumption_receipt if result else {})
        scope=_dict(result.scope_assessment if result else {})
        mapping={
            "fulfillment_authorization_consumption_required": (rec.get("receipt_id",""), rec.get("digest",""), "satisfied" if rec else "missing"),
            "local_authorization_grant_required": (evidence.grant_id, evidence.grant_digest, "satisfied" if not current_blocked else "blocked"),
            "scope_match_required": (scope.get("assessment_id", evidence.source_consumption_receipt_id), scope.get("digest", evidence.source_consumption_receipt_digest), "satisfied" if not current_blocked else "blocked"),
            "grant_not_expired_required": (evidence.expiry_evaluation_id, evidence.expiry_evaluation_digest, "satisfied" if evidence.derived_posture in {"currently_active","active_with_conditions"} else ("stale" if evidence.derived_posture in {"expired","stale"} else "blocked")),
            "grant_not_revoked_required": ("current_no_revocation_manifest" if not evidence.revocation_receipt_refs else evidence.revocation_receipt_refs[0].ref_id, (evidence.digest if evidence.current_snapshot_id.startswith("hlas_legacy_") else evidence.current_no_revocation_manifest_digest) if not evidence.revocation_receipt_refs else evidence.revocation_receipt_refs[0].digest, "satisfied" if evidence.derived_posture in {"currently_active","active_with_conditions"} else "blocked"),
            "backend_declaration_required": (_dict(backend or {}).get("declaration_id",""), _dict(backend or {}).get("digest",""), "satisfied" if backend else "missing"),
            "dry_run_plan_required": (_dict(dryrun or {}).get("plan_id",""), _dict(dryrun or {}).get("digest",""), "satisfied" if dryrun else "missing"),
            "precondition_manifest_required": (_dict(manifest or {}).get("manifest_id",""), _dict(manifest or {}).get("digest",""), "satisfied" if manifest else "missing"),
        }
        records: list[HostFulfillmentExecutorPrerequisiteRecord] = []
        for label in sorted(REQUIRED_EXECUTOR_LABELS):
            eid, dig, status = mapping.get(label, ("", "", "missing"))
            records.append(HostFulfillmentExecutorPrerequisiteRecord(label,status,str(eid),str(dig), "validation_time="+evidence.current_validation_time if label=="grant_not_expired_required" else "ok"))
        return tuple(records)

    def _load_replay(self, root:Path, correlation_id:str, semantic:Mapping[str,Any])->Mapping[str,Any]|None:
        idx=root/"replay_index.json"
        if not idx.exists(): return None
        try: data=json.loads(idx.read_text())
        except Exception: return {"conflict": True}
        prior=data.get(correlation_id)
        if not prior: return None
        if prior.get("semantic") != json.loads(_canon(semantic)): return {"conflict": True}
        bundle=root/str(prior.get("request_id",""))
        if not bundle.exists() or bundle.is_symlink(): return {"conflict": True}
        validated=validate_persisted_readiness_bundle(bundle,expected_bundle_digest=str(prior.get("bundle_digest","")),expected_request_id=str(prior.get("request_id","")),expected_request_digest=str(prior.get("request_digest","")),expected_evidence_digest=str(prior.get("current_grant_evidence_digest","")))
        if not validated.ok: return {"conflict": True}
        try: latest=json.loads((root/"latest.json").read_text())
        except Exception: return {"conflict": True}
        if latest.get("bundle_digest") != validated.bundle_digest: return {"conflict": True}
        return {"bundle": bundle,"bundle_digest":validated.bundle_digest}

    def _persist(self, root:Path, ev:HostFulfillmentExecutorReadinessEvaluation, evidence:HostFulfillmentExecutorCurrentGrantEvidence, semantic:Mapping[str,Any])->bool:
        if root.exists() and root.is_symlink(): raise ValueError("symlink_escape_rejected")
        if ev.request is None: raise ValueError("persisted_evaluation_request_required")
        root.mkdir(parents=True,exist_ok=True); bundle=root/ev.request.request_id
        tmp=root/(bundle.name+".tmp");
        if tmp.exists(): shutil.rmtree(tmp)
        tmp.mkdir(exist_ok=True)
        data=ev.to_dict(); files={"readiness_request.json":data.get("request"),"current_grant_evidence.json":evidence.to_dict(),"source_manifest.json":data.get("plan"),"metadata_admission.json":data.get("metadata_admission"),"runtime_plan.json":data.get("plan"),"prerequisites.json":data.get("prerequisite_records"),"executor_contract.json":data.get("contract"),"backend_declaration.json":data.get("backend_declaration"),"precondition_manifest.json":data.get("precondition_manifest"),"dry_run_plan.json":data.get("dry_run_plan"),"admission_packet.json":data.get("admission_packet"),"readiness_receipt.json":data.get("readiness_receipt"),"runtime_receipt.json":data.get("runtime_receipt"),"validation_findings.json":{"findings":data.get("findings")},"summary.json":summarize_evaluation(ev),"README.md":render_markdown(ev)}
        for name,val in files.items(): (tmp/name).write_text(json.dumps(val,sort_keys=True,indent=2) if name.endswith('.json') else str(val),encoding='utf-8')
        manifest_entries=[]
        for path in sorted(tmp.iterdir()):
            if path.name == "bundle_manifest.json": continue
            raw=path.read_bytes(); payload={}
            if path.name.endswith(".json"):
                try: payload=json.loads(raw.decode())
                except Exception: payload={}
                if not isinstance(payload, dict): payload={}
            manifest_entries.append({"artifact_kind":path.stem,"schema_version":SCHEMA_VERSION,"semantic_id":str(payload.get("request_id") or payload.get("evidence_id") or payload.get("plan_id") or payload.get("contract_id") or payload.get("declaration_id") or payload.get("manifest_id") or payload.get("packet_id") or payload.get("receipt_id") or path.stem),"digest":"sha256:"+hashlib.sha256(raw).hexdigest(),"relative_filename":path.name,"size":len(raw)})
        bundle_manifest={"schema_version":SCHEMA_VERSION,"artifact_kind":"host_fulfillment_executor_readiness_bundle_manifest","files":manifest_entries}
        bundle_manifest["bundle_digest"]=_sha({"files":manifest_entries})
        (tmp/"bundle_manifest.json").write_text(json.dumps(bundle_manifest,sort_keys=True,indent=2),encoding="utf-8")
        os.replace(tmp,bundle)
        latest={"request_id":ev.request.request_id,"request_digest":ev.request.digest,"current_grant_evidence_id":evidence.evidence_id,"current_grant_evidence_digest":evidence.digest,"runtime_receipt_id":ev.runtime_receipt.receipt_id if ev.runtime_receipt else "","runtime_receipt_digest":ev.runtime_receipt.digest if ev.runtime_receipt else "","bundle_digest":bundle_manifest["bundle_digest"],"posture":ev.status,"contract_id":ev.contract.get("contract_id") if ev.contract else "","readiness_receipt_id":ev.readiness_receipt.get("receipt_id") if ev.readiness_receipt else ""}
        tmp_latest=root/"latest.json.tmp"; tmp_latest.write_text(json.dumps(latest,sort_keys=True,indent=2),encoding='utf-8'); os.replace(tmp_latest, root/"latest.json")
        idx=root/"replay_index.json"; data=json.loads(idx.read_text()) if idx.exists() else {}; data[ev.request.correlation_id]={**latest,"semantic":json.loads(_canon(semantic))}; tmp_idx=root/"replay_index.json.tmp"; tmp_idx.write_text(json.dumps(data,sort_keys=True,indent=2),encoding="utf-8"); os.replace(tmp_idx, idx)
        return True


def validate_route_consistency(ev:HostFulfillmentExecutorReadinessEvaluation)->tuple[str,...]:
    """Validate the single canonical route across a completed runtime bundle."""
    if ev.request is None:
        return ("route:missing_request",)
    requested=ev.request.requested_fulfillment_domain
    try:
        executor, backend=resolve_canonical_executor_route(requested)
    except ValueError:
        return ("route:unknown_requested_fulfillment_domain",)
    findings:list[str]=[]
    if ev.request.executor_domain != executor: findings.append("route:request_executor_domain_mismatch")
    if ev.request.backend_class != backend: findings.append("route:request_backend_class_mismatch")
    contract=_dict(ev.contract or {})
    declaration=_dict(ev.backend_declaration or {})
    dry_run=_dict(ev.dry_run_plan or {})
    admission=_dict(ev.admission_packet or {})
    runtime=_dict(ev.runtime_receipt or {})
    if contract.get("requested_fulfillment_domain") != requested: findings.append("route:contract_fulfillment_domain_mismatch")
    if contract.get("executor_domain") != executor: findings.append("route:contract_executor_domain_mismatch")
    if contract.get("backend_class") != backend: findings.append("route:contract_backend_class_mismatch")
    if declaration.get("backend_class") != backend: findings.append("route:declaration_backend_class_mismatch")
    if tuple(declaration.get("supported_executor_domains",())) != (executor,): findings.append("route:declaration_executor_domain_mismatch")
    if dry_run.get("backend_class") != backend: findings.append("route:dry_run_backend_class_mismatch")
    if admission.get("executor_domain") != executor: findings.append("route:admission_executor_domain_mismatch")
    for field, expected in (("requested_fulfillment_domain",requested),("executor_domain",executor),("backend_class",backend)):
        if runtime.get(field) != expected: findings.append("route:runtime_receipt_"+field+"_mismatch")
    return tuple(sorted(set(findings)))

def summarize_evaluation(ev:HostFulfillmentExecutorReadinessEvaluation)->dict[str,Any]:
    return {"schema_version":SCHEMA_VERSION,"posture":ev.status,"contract_package_count":1 if ev.contract else 0,"request_id":ev.request.request_id if ev.request else "","requested_fulfillment_domain":ev.request.requested_fulfillment_domain if ev.request else "","executor_domain":ev.request.executor_domain if ev.request else "","backend_class":ev.request.backend_class if ev.request else "","latest_contract_id":ev.contract.get("contract_id") if ev.contract else "","latest_packet_id":ev.admission_packet.get("packet_id") if ev.admission_packet else "","latest_readiness_receipt_id":ev.readiness_receipt.get("receipt_id") if ev.readiness_receipt else "",**NO_AUTHORITY}

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
