# mypy: disable-error-code="no-untyped-def,no-untyped-call,arg-type,union-attr,var-annotated,no-any-return"
"""Same-tick host live-grant readiness runtime closure.

Consumes an exact in-memory HostControlledAuthorizationEvaluation and emits only
review metadata: prerequisite matrices, approval request packets, preflight
receipts, and denial/deferral receipts. It never issues local grants, fabricates
operator/policy approval, requests privileged-effect admission, invokes a backend,
or mutates host/repository state.
"""
from __future__ import annotations

import hashlib, json, os, tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from sentientos.control_plane_kernel import AuthorityClass, ControlActionDecision, ControlActionRequest, ControlPlaneKernel, LifecyclePhase, get_control_plane_kernel
from sentientos.host_controlled_authorization_runtime import HostControlledAuthorizationEvaluation, HostControlledAuthorizationItem, validate_evaluation as validate_controlled_evaluation
from sentientos.live_grant_readiness import (
    LiveGrantReadinessWingRecords, build_live_grant_readiness_wing,
    validate_live_grant_prerequisite_matrix, validate_operator_policy_approval_packet,
    validate_grant_issue_preflight_receipt, validate_grant_denial_deferral_receipt,
    live_grant_prerequisite_matrix_digest, operator_policy_approval_packet_digest,
    grant_issue_preflight_receipt_digest, grant_denial_deferral_receipt_digest,
)
from sentientos.world_state_board import WorldStateSourceKind, digest

SCHEMA_VERSION = "host_live_grant_readiness_runtime.v1"
READINESS_DOMAIN = "future_cooling_live_grant_review"
NO_AUTHORITY = {"read_only": True, "review_only": True, "approval_packet_only": True, "operator_approval_granted": False, "policy_approval_granted": False, "live_authorization_granted": False, "local_grant_issued": False, "fulfillment_granted": False, "execution_triggered": False, "effect_claimed": False, "effect_proven": False, "host_mutation_performed": False}

def _canon(v: Any) -> str: return json.dumps(v, sort_keys=True, separators=(",", ":"), default=lambda o: asdict(o) if hasattr(o, "__dataclass_fields__") else str(o))
def _sha(v: Any) -> str: return hashlib.sha256(_canon(v).encode()).hexdigest()
def _id(p: str, v: Any) -> str: return p + _sha(v)[:24]
def _now() -> str: return datetime.now(timezone.utc).isoformat()
def _to_dict(v: Any) -> dict[str, Any]: return asdict(v) if hasattr(v, "__dataclass_fields__") else dict(v)

@dataclass(frozen=True)
class HostLiveGrantReadinessBudget:
    max_items: int = 32; max_serialized_item_bytes: int = 262144; max_bundle_bytes: int = 2097152; max_bundle_files: int = 64; retry_count: int = 0
    def to_dict(self) -> dict[str, Any]: return asdict(self)
@dataclass(frozen=True)
class HostLiveGrantReadinessPlan:
    plan_id: str; semantic_digest: str; readiness_domain: str; budget: HostLiveGrantReadinessBudget; authority_class: str = AuthorityClass.PROPOSAL_EVALUATION.value; metadata_only: bool = True; review_only: bool = True; no_effect_authority: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)
@dataclass(frozen=True)
class HostLiveGrantReadinessSourceRef:
    source_controlled_authorization_evaluation_id: str; source_controlled_authorization_evaluation_digest: str; source_tick_id: str; correlation_id: str; controlled_ledger_id: str; controlled_ledger_digest: str; controlled_contract_id: str; controlled_contract_digest: str; schema_grant_record_id: str; schema_grant_record_digest: str; revocation_schema_id: str; revocation_schema_digest: str; safety_manifest_id: str; safety_manifest_digest: str; gate_assessment_ids: tuple[str, ...]; gate_assessment_digests: tuple[str, ...]; satisfied_gates: tuple[str, ...]; conditional_gates: tuple[str, ...]; missing_gates: tuple[str, ...]; blocked_gates: tuple[str, ...]; contradicted_gates: tuple[str, ...]; blocked_actions: tuple[str, ...]
    def to_dict(self) -> dict[str, Any]: return asdict(self)
@dataclass(frozen=True)
class HostLiveGrantReadinessItem:
    item_id: str; source_ref: HostLiveGrantReadinessSourceRef | None; valid_source: bool; findings: tuple[str, ...]; readiness_records: LiveGrantReadinessWingRecords | None = None
    def to_dict(self) -> dict[str, Any]: return asdict(self)
@dataclass(frozen=True)
class HostLiveGrantReadinessRuntimeSummary:
    status: str; evaluation_id: str; chain_id: str; source_chain_count: int; valid_item_count: int; invalid_item_count: int; readiness_status_counts: Mapping[str,int]; prerequisite_status_counts: Mapping[str,int]; satisfied_prerequisites: tuple[str,...]; missing_prerequisites: tuple[str,...]; blocked_actions: tuple[str,...]; findings: tuple[str,...]; read_only: bool=True; review_only: bool=True; approval_packet_only: bool=True; operator_approval_granted: bool=False; policy_approval_granted: bool=False; live_authorization_granted: bool=False; local_grant_issued: bool=False; fulfillment_granted: bool=False; execution_triggered: bool=False; host_mutation_performed: bool=False
    def to_dict(self) -> dict[str, Any]: return asdict(self)
@dataclass(frozen=True)
class HostLiveGrantReadinessEvaluation:
    evaluation_id: str; chain_id: str; plan: HostLiveGrantReadinessPlan; admission_ref: Mapping[str, Any]; source_controlled_authorization_evaluation_id: str; source_controlled_authorization_evaluation_digest: str; source_tick_id: str; correlation_id: str; items: tuple[HostLiveGrantReadinessItem,...]; validation_findings: tuple[str,...]; summary: HostLiveGrantReadinessRuntimeSummary; semantic_digest: str; observed_at: str; no_authority: bool=True
    def to_dict(self) -> dict[str, Any]: return asdict(self)
@dataclass(frozen=True)
class HostLiveGrantReadinessReceipt:
    receipt_id: str; evaluation_id: str; bundle_digest: str; artifact_root: str; artifact_paths: Mapping[str,str]; semantic_digest: str; repository_mutation_performed: bool=False; host_mutation_performed: bool=False
    def to_dict(self) -> dict[str, Any]: return asdict(self)
@dataclass(frozen=True)
class HostLiveGrantReadinessRuntimeValidationResult:
    ok: bool; findings: tuple[str,...]=()

def build_host_live_grant_readiness_plan(readiness_domain: str = READINESS_DOMAIN, budget: HostLiveGrantReadinessBudget | None = None) -> HostLiveGrantReadinessPlan:
    b=budget or HostLiveGrantReadinessBudget(); sem={"schema":SCHEMA_VERSION,"domain":readiness_domain,"budget":b.to_dict(),"authority":AuthorityClass.PROPOSAL_EVALUATION.value,"metadata_only":True,"no_effect":True}
    return HostLiveGrantReadinessPlan(_id("hlgrp_", sem), _sha(sem), readiness_domain, b)

def _source_ref(ev: HostControlledAuthorizationEvaluation, item: HostControlledAuthorizationItem) -> tuple[HostLiveGrantReadinessSourceRef|None, tuple[str,...]]:
    findings=[]
    if not item.valid_source or item.controlled_authorization is None or item.safety_bundle is None or item.source_ref is None: findings.append("missing_valid_controlled_authorization_safety_chain")
    if findings: return None, tuple(findings)
    ca=item.controlled_authorization; sb=item.safety_bundle; man=sb.safety_gate_satisfaction_manifest
    if ca.ledger.live_authorization_granted: findings.append("controlled_ledger_claims_live_authorization")
    if man.grants_live_authorization or getattr(man,"host_mutation_performed",False): findings.append("safety_manifest_claims_authority_or_effect")
    if man.source_controlled_authorization_contract_id != ca.contract.contract_id or man.source_controlled_authorization_contract_digest != ca.contract.digest: findings.append("safety_manifest_contract_mismatch")
    satisfied=tuple(sorted(man.satisfied_gate_labels)); missing=tuple(sorted(man.missing_gate_labels)); blocked=tuple(sorted(getattr(man,"blocked_gate_labels",()) or ())); contrad=tuple(sorted(getattr(man,"contradicted_gate_labels",()) or ()))
    ref=HostLiveGrantReadinessSourceRef(ev.evaluation_id, ev.semantic_digest, ev.source_tick_id, ev.correlation_id, ca.ledger.ledger_id, ca.ledger.digest, ca.contract.contract_id, ca.contract.digest, ca.grant_record.grant_record_id, ca.grant_record.digest, ca.revocation_record.revocation_id, ca.revocation_record.digest, man.manifest_id, man.digest, tuple(a.assessment_id for a in sb.gate_assessments), tuple(getattr(a,"digest",_sha(_to_dict(a))) for a in sb.gate_assessments), satisfied, (), missing, blocked, contrad, tuple(sorted(man.blocked_actions)))
    return (None, tuple(findings)) if findings else (ref, ())

def _summary(eid: str, cid: str, items: Sequence[HostLiveGrantReadinessItem], findings: Sequence[str]) -> HostLiveGrantReadinessRuntimeSummary:
    rs={}; ps={}; sat=set(); miss=set(); blocked=set()
    for it in items:
        if it.readiness_records:
            rec=it.readiness_records; rs[rec.preflight_receipt.readiness_status]=rs.get(rec.preflight_receipt.readiness_status,0)+1; sat.update(rec.prerequisite_matrix.satisfied_labels); miss.update(rec.prerequisite_matrix.missing_labels); blocked.update(rec.prerequisite_matrix.blocked_actions)
            for p in rec.prerequisite_matrix.prerequisites: ps[p.status]=ps.get(p.status,0)+1
        if it.source_ref: blocked.update(it.source_ref.blocked_actions)
    valid=sum(1 for i in items if i.valid_source)
    status="unavailable" if not items else "blocked" if any("blocked" in k for k in ps) else "contradicted" if any("contradicted" in k for k in ps) or findings else "incomplete" if miss else "ready_for_operator_policy_review"
    return HostLiveGrantReadinessRuntimeSummary(status,eid,cid,len(items),valid,len(items)-valid,rs,ps,tuple(sorted(sat)),tuple(sorted(miss)),tuple(sorted(blocked)),tuple(sorted(set(findings))))

def validate_evaluation(evaluation: HostLiveGrantReadinessEvaluation) -> HostLiveGrantReadinessRuntimeValidationResult:
    findings=list(evaluation.validation_findings)
    if not evaluation.no_authority: findings.append("authority_flag_true")
    for it in evaluation.items:
        if not it.valid_source: findings.extend(f"{it.item_id}:{f}" for f in it.findings); continue
        if it.readiness_records is None or it.source_ref is None: findings.append(f"{it.item_id}:missing_readiness_records"); continue
        r=it.readiness_records
        findings.extend(f"{it.item_id}:matrix:{f}" for f in validate_live_grant_prerequisite_matrix(r.prerequisite_matrix).findings)
        findings.extend(f"{it.item_id}:approval:{f}" for f in validate_operator_policy_approval_packet(r.approval_packet).findings)
        findings.extend(f"{it.item_id}:preflight:{f}" for f in validate_grant_issue_preflight_receipt(r.preflight_receipt).findings)
        findings.extend(f"{it.item_id}:denial:{f}" for f in validate_grant_denial_deferral_receipt(r.denial_deferral_receipt).findings)
        if r.prerequisite_matrix.source_controlled_authorization_ledger_id != it.source_ref.controlled_ledger_id: findings.append(f"{it.item_id}:ledger_binding_mismatch")
        if r.prerequisite_matrix.source_safety_gate_manifest_id != it.source_ref.safety_manifest_id: findings.append(f"{it.item_id}:safety_manifest_binding_mismatch")
    return HostLiveGrantReadinessRuntimeValidationResult(not findings, tuple(sorted(set(findings))))

class HostLiveGrantReadinessRuntimeCoordinator:
    def __init__(self, *, kernel: ControlPlaneKernel|None=None, runtime_state_root: Path|str|None=None, plan: HostLiveGrantReadinessPlan|None=None, clock: Callable[[],str]|None=None) -> None:
        self.kernel=kernel or get_control_plane_kernel(); self.runtime_state_root=Path(runtime_state_root or os.getenv("SENTIENTOS_RUNTIME_STATE_ROOT") or (tempfile.gettempdir()+"/sentientos_runtime")); self.plan=plan or build_host_live_grant_readiness_plan(); self.clock=clock or _now; self._by_correlation={}; self._tick_seen=set(); self.builder_call_count=0
    def request_admission(self, *, tick_id: str, correlation_id: str, source_evaluation: HostControlledAuthorizationEvaluation, first_ref: HostLiveGrantReadinessSourceRef) -> ControlActionDecision:
        return self.kernel.admit(ControlActionRequest("host_live_grant_readiness_runtime", AuthorityClass.PROPOSAL_EVALUATION, "sentientosd", "host_live_grant_readiness_runtime", LifecyclePhase.MAINTENANCE, {"correlation_id":correlation_id,"tick_id":tick_id,"source_controlled_authorization_evaluation_id":source_evaluation.evaluation_id,"source_controlled_authorization_evaluation_digest":source_evaluation.semantic_digest,"controlled_ledger_id":first_ref.controlled_ledger_id,"controlled_ledger_digest":first_ref.controlled_ledger_digest,"safety_manifest_id":first_ref.safety_manifest_id,"safety_manifest_digest":first_ref.safety_manifest_digest,"runtime_plan_id":self.plan.plan_id,"runtime_plan_digest":self.plan.semantic_digest,"metadata_only":True,"grants_operator_approval":False,"grants_policy_approval":False,"grants_live_authorization":False,"grants_privileged_effect_admission":False,"grants_fulfillment":False}))
    def run_cycle(self, *, tick_id: str, source_evaluation: HostControlledAuthorizationEvaluation|None, correlation_id: str|None=None, decision: ControlActionDecision|None=None, persist: bool=True) -> HostLiveGrantReadinessEvaluation|None:
        corr=correlation_id or f"{tick_id}:host_live_grant_readiness_runtime"
        if corr in self._by_correlation: return self._by_correlation[corr]
        if tick_id in self._tick_seen or source_evaluation is None or getattr(source_evaluation,"no_authority",False) is not True: return None
        pairs=[_source_ref(source_evaluation, i) for i in sorted(source_evaluation.items, key=lambda x:x.item_id)[:self.plan.budget.max_items]]
        valid=[r for r,f in pairs if r is not None and not f]
        if not valid: return None
        decision=decision or self.request_admission(tick_id=tick_id, correlation_id=corr, source_evaluation=source_evaluation, first_ref=valid[0])
        if not getattr(decision,"allowed",False): return None
        items=[]; seen={}
        for src,(ref,findings) in zip(sorted(source_evaluation.items, key=lambda x:x.item_id)[:self.plan.budget.max_items], pairs):
            local=list(findings)
            if ref and ref.controlled_ledger_id in seen and seen[ref.controlled_ledger_id] != ref.controlled_ledger_digest: local.append("duplicate_semantic_id_conflicting_digest")
            if ref: seen[ref.controlled_ledger_id]=ref.controlled_ledger_digest
            if local or ref is None or src.controlled_authorization is None or src.safety_bundle is None:
                items.append(HostLiveGrantReadinessItem(_id("hlgri_", (getattr(src,"item_id","unknown"), local)), ref, False, tuple(sorted(set(local))))); continue
            rec=build_live_grant_readiness_wing(src.controlled_authorization.ledger, src.safety_bundle.safety_gate_satisfaction_manifest, readiness_domain=self.plan.readiness_domain, created_at="1970-01-01T00:00:00+00:00")
            self.builder_call_count += 4
            item=HostLiveGrantReadinessItem(_id("hlgri_", (ref.to_dict(), rec.prerequisite_matrix.matrix_id, rec.approval_packet.packet_id, rec.preflight_receipt.receipt_id, rec.denial_deferral_receipt.receipt_id)), ref, True, (), rec)
            if len(_canon(item.to_dict()).encode()) > self.plan.budget.max_serialized_item_bytes: item=HostLiveGrantReadinessItem(item.item_id, ref, False, ("serialized_item_exceeds_budget",), rec)
            items.append(item)
        sem={"schema":SCHEMA_VERSION,"plan":self.plan.semantic_digest,"source":source_evaluation.evaluation_id,"source_digest":source_evaluation.semantic_digest,"items":[i.item_id for i in items],"correlation_id":corr,"no_authority":NO_AUTHORITY}
        eid=_id("hlgre_", sem); cid=_id("hlgrc_", sem); adm={"admission_decision_ref":decision.admission_decision_ref,"outcome":decision.outcome.value,"authority_class":decision.authority_class.value,"action_kind":decision.action_kind,"correlation_id":decision.correlation_id,"metadata_evaluation_only":True,"grants_live_authorization":False,"grants_privileged_effect_admission":False,"grants_fulfillment":False}
        ev=HostLiveGrantReadinessEvaluation(eid,cid,self.plan,adm,source_evaluation.evaluation_id,source_evaluation.semantic_digest,tick_id,corr,tuple(items),(),_summary(eid,cid,items,()),_sha(sem),self.clock(),True)
        val=validate_evaluation(ev)
        if not val.ok: ev=HostLiveGrantReadinessEvaluation(eid,cid,self.plan,adm,source_evaluation.evaluation_id,source_evaluation.semantic_digest,tick_id,corr,tuple(items),val.findings,_summary(eid,cid,items,val.findings),_sha(sem),ev.observed_at,True)
        self._by_correlation[corr]=ev; self._tick_seen.add(tick_id)
        if persist: persist_evidence_bundle(self.runtime_state_root, ev, tick_id=tick_id)
        return ev

def _safe_root(root: Path|str) -> Path:
    r=Path(root).resolve(); r.mkdir(parents=True, exist_ok=True)
    if r.is_symlink() or any(part == ".." for part in r.parts): raise ValueError("unsafe_runtime_state_root")
    return r

def render_markdown(evaluation: HostLiveGrantReadinessEvaluation) -> str:
    return "\n".join(["# Host Live Grant Readiness Runtime","",f"- Evaluation: `{evaluation.evaluation_id}`",f"- Chain: `{evaluation.chain_id}`",f"- Source controlled authorization: `{evaluation.source_controlled_authorization_evaluation_id}`",f"- Status: `{evaluation.summary.status}`",f"- Missing prerequisites: `{', '.join(evaluation.summary.missing_prerequisites)}`","- Authority: review only; approval packet only; no grant, fulfillment, privileged-effect admission, backend execution, or host mutation.",""])

def persist_evidence_bundle(root: Path|str, evaluation: HostLiveGrantReadinessEvaluation, *, tick_id: str) -> HostLiveGrantReadinessReceipt:
    base=_safe_root(root)/"host_live_grant_readiness_runtime"; tmp=base/(".%s.tmp"%evaluation.evaluation_id); final=base/evaluation.evaluation_id
    if tmp.exists():
        for p in sorted(tmp.glob("**/*"), reverse=True):
            if p.is_file(): p.unlink()
            elif p.is_dir(): p.rmdir()
    tmp.mkdir(parents=True, exist_ok=True)
    paths={}
    docs={"plan.json":evaluation.plan.to_dict(),"admission.json":dict(evaluation.admission_ref),"evaluation.json":evaluation.to_dict(),"summary.json":evaluation.summary.to_dict(),"validation.json":{"ok":validate_evaluation(evaluation).ok,"findings":validate_evaluation(evaluation).findings},"source_manifest.json":{"source_id":evaluation.source_controlled_authorization_evaluation_id,"source_digest":evaluation.source_controlled_authorization_evaluation_digest,"tick_id":tick_id},"README.md":render_markdown(evaluation)}
    for idx,it in enumerate(evaluation.items):
        if it.readiness_records:
            docs[f"item_{idx}_prerequisite_matrix.json"]=it.readiness_records.prerequisite_matrix.to_dict(); docs[f"item_{idx}_approval_packet.json"]=it.readiness_records.approval_packet.to_dict(); docs[f"item_{idx}_preflight.json"]=it.readiness_records.preflight_receipt.to_dict(); docs[f"item_{idx}_denial_deferral.json"]=it.readiness_records.denial_deferral_receipt.to_dict()
    if len(docs)>evaluation.plan.budget.max_bundle_files: raise ValueError("bundle_file_count_exceeds_budget")
    for name,payload in docs.items():
        if "/" in name or ".." in name: raise ValueError("unsafe_artifact_name")
        text=payload if isinstance(payload,str) else json.dumps(payload, sort_keys=True, indent=2)
        if len(text.encode())>evaluation.plan.budget.max_bundle_bytes: raise ValueError("bundle_size_exceeds_budget")
        (tmp/name).write_text(text, encoding="utf-8"); paths[name]=(final/name).as_posix()
    latest={"evaluation_id":evaluation.evaluation_id,"chain_id":evaluation.chain_id,"summary_status":evaluation.summary.status,"semantic_digest":evaluation.semantic_digest,"read_only":True,"review_only":True,"local_grant_issued":False}
    (tmp/"latest.json").write_text(json.dumps(latest, sort_keys=True, indent=2), encoding="utf-8"); paths["latest.json"]=(final/"latest.json").as_posix()
    if final.exists():
        for p in sorted(final.glob("**/*"), reverse=True):
            if p.is_file(): p.unlink()
            elif p.is_dir(): p.rmdir()
        final.rmdir()
    tmp.replace(final)
    (base/"latest.json").write_text(json.dumps(latest, sort_keys=True, indent=2), encoding="utf-8")
    bd=_sha({k:(final/k).read_text(encoding="utf-8") for k in sorted(paths) if (final/k).exists()})
    return HostLiveGrantReadinessReceipt(_id("hlgrr_", (evaluation.evaluation_id, bd)), evaluation.evaluation_id, bd, final.as_posix(), paths, evaluation.semantic_digest)

def world_state_records(evaluation: HostLiveGrantReadinessEvaluation) -> list[dict[str, Any]]:
    out=[]; base={"source_kind":WorldStateSourceKind.PRIVILEGE.value,"schema_version":SCHEMA_VERSION,"observed_at":evaluation.observed_at,"required":False,"evidence_strength":"recorded","effect_claimed":False,"effect_proven":False}
    for it in evaluation.items:
        if not it.readiness_records: continue
        lineage=it.source_ref.to_dict() if it.source_ref else {}
        for kind,obj,status,dg in (("host_live_grant_prerequisite_matrix",it.readiness_records.prerequisite_matrix,it.readiness_records.preflight_receipt.readiness_status,live_grant_prerequisite_matrix_digest(it.readiness_records.prerequisite_matrix)),("host_live_grant_prerequisite_record",it.readiness_records.prerequisite_matrix,it.readiness_records.preflight_receipt.readiness_status,live_grant_prerequisite_matrix_digest(it.readiness_records.prerequisite_matrix)),("host_live_grant_operator_policy_approval_packet",it.readiness_records.approval_packet,it.readiness_records.approval_packet.approval_packet_status,operator_policy_approval_packet_digest(it.readiness_records.approval_packet)),("host_live_grant_issue_preflight",it.readiness_records.preflight_receipt,it.readiness_records.preflight_receipt.preflight_status,grant_issue_preflight_receipt_digest(it.readiness_records.preflight_receipt)),("host_live_grant_denial_deferral",it.readiness_records.denial_deferral_receipt,it.readiness_records.denial_deferral_receipt.denial_deferral_status,grant_denial_deferral_receipt_digest(it.readiness_records.denial_deferral_receipt))):
            p=obj.to_dict(); payload={**p,"source_lineage":lineage,**NO_AUTHORITY}
            sid=p.get("matrix_id") or p.get("packet_id") or p.get("receipt_id")
            out.append({**base,"source_id":f"hlgr:{sid}:{kind}","subject_id":str(sid),"subject_kind":kind,"stage":"review","disposition":status,"payload":payload,"digest":digest(payload)})
    return out

def summary_for_evaluation(evaluation: HostLiveGrantReadinessEvaluation) -> dict[str, Any]: return evaluation.summary.to_dict()
