"""Canonical maintenance-candidate adaptation and normalization.

Metadata only: no execution, git, validation, publication, adoption, or lease effects.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
import fnmatch, hashlib, json
from pathlib import Path
from typing import Any, Mapping, Sequence

CANDIDATE_SCHEMA="sentientos.maintenance_candidate:v1"
CANDIDATE_SET_SCHEMA="sentientos.maintenance_candidate_set:v1"
SOURCE_KINDS=frozenset({"governed_improvement_signal","normalized_work_item","genesis_need","explicit_maintenance_candidate"})
SEVERITIES=("low","medium","high","critical")
CONFIDENCES=("low","medium","high","confirmed")
DISPOSITIONS=frozenset({"candidate_ready","candidate_duplicate","candidate_contradicted","candidate_blocked","candidate_insufficient_metadata"})
REASON_CODES=frozenset({"candidate_scope_unknown","candidate_path_not_allowed","candidate_path_forbidden","candidate_authority_unavailable","candidate_kind_not_allowed","candidate_base_sha_mismatch","candidate_file_budget_exceeded","candidate_diff_budget_exceeded","candidate_implementation_budget_exceeded","candidate_validation_budget_exceeded","candidate_contradicted","candidate_source_blocked","candidate_evidence_insufficient","candidate_already_active","candidate_already_resolved","candidate_reconsideration_required","candidate_journal_unhealthy","unknown_source_kind","unknown_field","missing_semantic_field","false_authority_claim","intake_blocked","genesis_metadata_only"})
AUTHORITY_CLASSES=frozenset({"proposal_selection_only","filesystem_read","filesystem_write","documentation_edit","test_edit","code_edit","governance_edit","journal_read","validation_execute","implementation_agent_session"})


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

def digest(value: Any) -> str:
    return "sha256:"+hashlib.sha256(canonical_json_bytes(value)).hexdigest()

def _compact(s: Any) -> str: return " ".join(str(s or "").strip().split())
def _paths(xs: Sequence[Any]) -> tuple[str,...]:
    out=[]
    for x in xs or ():
        p=Path(str(x).strip())
        if str(p) and not p.is_absolute() and ".." not in p.parts: out.append(p.as_posix())
    return tuple(sorted(set(out)))
def _tuple(xs: Sequence[Any]) -> tuple[str,...]: return tuple(sorted({str(x).strip() for x in xs or () if str(x).strip()}))
def _severity(s: Any) -> str:
    v=str(s or "medium").lower(); return v if v in SEVERITIES else "medium"
def _confidence(s: Any) -> str:
    v=str(s or "medium").lower(); return v if v in CONFIDENCES else "medium"

@dataclass(frozen=True)
class MaintenanceCandidate:
    schema_version: str
    candidate_id: str
    candidate_revision_digest: str
    source_kind: str
    source_reference: str
    source_semantic_digest: str
    base_repository_sha: str
    objective: str
    bounded_description: str
    candidate_kind: str
    severity: str
    confidence: str
    recurrence_count: int
    declared_subject_paths: tuple[str,...]
    declared_validation_expectations: tuple[str,...]
    evidence_references: tuple[str,...]
    requested_authority_classes: tuple[str,...]
    declared_constraints: tuple[str,...]
    estimated_file_count: int
    estimated_changed_line_count: int
    estimated_implementation_seconds: int
    estimated_validation_seconds: int
    lifecycle_disposition: str
    reason_codes: tuple[str,...]
    canonical_candidate_digest: str
    operator_priority: int|None=None

    def to_dict(self)->dict[str,Any]:
        d=asdict(self); return d
    def identity_seed(self)->dict[str,Any]:
        return {"candidate_kind":self.candidate_kind,"objective":self.objective,"subject_paths":self.declared_subject_paths,"base_repository_sha":self.base_repository_sha,"authority":self.requested_authority_classes,"constraints":self.declared_constraints,"source_semantic_digest":self.source_semantic_digest}
    def material_payload(self)->dict[str,Any]:
        d=self.to_dict();
        for k in ("candidate_id","candidate_revision_digest","canonical_candidate_digest","source_reference","evidence_references","recurrence_count","lifecycle_disposition","reason_codes"): d.pop(k,None)
        return d
    def canonical_bytes(self)->bytes: return canonical_json_bytes(self.to_dict())

def _build(*, source_kind:str, source_reference:str, base_repository_sha:str, objective:str, bounded_description:str, candidate_kind:str, severity:str="medium", confidence:str="medium", recurrence_count:int=1, declared_subject_paths:Sequence[Any]=(), declared_validation_expectations:Sequence[Any]=(), evidence_references:Sequence[Any]=(), requested_authority_classes:Sequence[Any]=(), declared_constraints:Sequence[Any]=(), estimated_file_count:int=1, estimated_changed_line_count:int=1, estimated_implementation_seconds:int=60, estimated_validation_seconds:int=60, lifecycle_disposition:str="candidate_ready", reason_codes:Sequence[Any]=(), source_semantic_identity:Mapping[str,Any]|None=None, operator_priority:int|None=None)->MaintenanceCandidate:
    reasons=set(str(r) for r in reason_codes if str(r))
    if source_kind not in SOURCE_KINDS: reasons.add("unknown_source_kind")
    paths=_paths(declared_subject_paths); auth=_tuple(requested_authority_classes); cons=_tuple(declared_constraints); evid=_tuple(evidence_references); vals=_tuple(declared_validation_expectations)
    if any(a not in AUTHORITY_CLASSES for a in auth): reasons.add("candidate_authority_unavailable")
    source_sem=digest(source_semantic_identity or {"source_kind":source_kind,"objective":_compact(objective),"paths":paths,"kind":candidate_kind})
    seed={"candidate_kind":candidate_kind,"objective":_compact(objective),"subject_paths":paths,"base_repository_sha":str(base_repository_sha),"authority":auth,"constraints":cons,"source_semantic_digest":source_sem}
    cid="mcand_"+hashlib.sha256(canonical_json_bytes(seed)).hexdigest()[:32]
    disp=lifecycle_disposition if lifecycle_disposition in DISPOSITIONS else "candidate_insufficient_metadata"
    if not objective or not candidate_kind: disp="candidate_insufficient_metadata"; reasons.add("missing_semantic_field")
    c0={"schema_version":CANDIDATE_SCHEMA,"candidate_id":cid,"source_kind":source_kind,"source_reference":source_reference,"source_semantic_digest":source_sem,"base_repository_sha":str(base_repository_sha),"objective":_compact(objective),"bounded_description":_compact(bounded_description),"candidate_kind":str(candidate_kind),"severity":_severity(severity),"confidence":_confidence(confidence),"recurrence_count":int(recurrence_count),"declared_subject_paths":paths,"declared_validation_expectations":vals,"evidence_references":evid,"requested_authority_classes":auth,"declared_constraints":cons,"estimated_file_count":int(estimated_file_count),"estimated_changed_line_count":int(estimated_changed_line_count),"estimated_implementation_seconds":int(estimated_implementation_seconds),"estimated_validation_seconds":int(estimated_validation_seconds),"lifecycle_disposition":disp,"reason_codes":tuple(sorted(reasons)),"operator_priority":operator_priority}
    rev=digest({k:v for k,v in c0.items() if k not in {"source_reference","evidence_references","recurrence_count"}})
    can=digest({**c0,"candidate_revision_digest":rev})
    return MaintenanceCandidate(candidate_revision_digest=rev, canonical_candidate_digest=can, **c0)  # type: ignore[arg-type]

def adapt_governed_signal(record: Any, *, base_repository_sha: str)->MaintenanceCandidate:
    r=record.to_dict() if hasattr(record,"to_dict") else dict(record)
    reasons=list(r.get("reason_codes") or [])
    for f in ("adoption_performed","repository_mutation_performed","provider_or_network_or_git_operation_performed","trial_performed"):
        if r.get(f): reasons.append("false_authority_claim")
    if not r.get("routing_eligible", True): reasons.append("candidate_source_blocked")
    path=[r.get("subject_path")] if r.get("subject_path") else []
    return _build(source_kind="governed_improvement_signal",source_reference=str(r.get("signal_id") or ""),base_repository_sha=base_repository_sha,objective=r.get("description") or r.get("finding_kind") or "",bounded_description=r.get("description") or "",candidate_kind=str(r.get("finding_kind") or "improvement_signal"),severity=r.get("severity","medium"),confidence="confirmed",declared_subject_paths=path,declared_validation_expectations=r.get("declared_validation_expectations") or (),evidence_references=r.get("evidence_refs") or (),requested_authority_classes=r.get("requested_authority_classes") or ("proposal_selection_only",),declared_constraints=r.get("declared_constraints") or (),reason_codes=reasons,source_semantic_identity={"signal_semantic":{k:v for k,v in r.items() if k not in {"signal_id","observed_at","source_artifact","evidence_refs"}}})

def adapt_work_item_packet(record: Any, *, base_repository_sha: str)->MaintenanceCandidate:
    r=asdict(record) if hasattr(record,"__dataclass_fields__") else dict(record)
    reasons=list(r.get("blocker_codes") or [])+list(r.get("warning_codes") or [])
    if str(r.get("intake_status")) in {"intake_blocked","intake_contradicted"}: reasons.append("candidate_source_blocked")
    return _build(source_kind="normalized_work_item",source_reference=str(r.get("work_item_id") or r.get("source_ref") or ""),base_repository_sha=base_repository_sha,objective=r.get("title") or r.get("requested_outcome") or "",bounded_description=r.get("description_summary") or r.get("requested_outcome") or "",candidate_kind=str(r.get("risk_class") or "work_item"),severity="medium",confidence="medium",declared_subject_paths=r.get("declared_targets") or (),declared_validation_expectations=r.get("declared_tests") or r.get("acceptance_criteria") or (),evidence_references=(r.get("source_ref") or "",),requested_authority_classes=r.get("declared_authority_requests") or ("proposal_selection_only",),declared_constraints=r.get("declared_constraints") or (),reason_codes=reasons,source_semantic_identity={"work_item":r.get("work_item_id"),"source_ref":r.get("source_ref")})

def adapt_genesis_metadata(record: Any, *, base_repository_sha: str)->MaintenanceCandidate:
    r=record.to_dict() if hasattr(record,"to_dict") else (asdict(record) if hasattr(record,"__dataclass_fields__") else dict(record))
    need_obj=r.get("need") if isinstance(r.get("need"),Mapping) else r
    need=dict(need_obj or {})
    obj=r.get("summary") or need.get("description") or need.get("capability") or ""
    return _build(source_kind="genesis_need",source_reference=str(r.get("proposal_id") or need.get("capability") or ""),base_repository_sha=base_repository_sha,objective=obj,bounded_description=obj,candidate_kind="genesis_capability_metadata",severity="medium",confidence="low",declared_subject_paths=r.get("declared_subject_paths") or (),declared_validation_expectations=r.get("testing_requirements") or (),evidence_references=(str(need.get("source") or "genesis"),),requested_authority_classes=("proposal_selection_only",),declared_constraints=("metadata_only","no_runtime_adoption"),reason_codes=("genesis_metadata_only",),source_semantic_identity={"genesis":need,"proposal_id":r.get("proposal_id")})

def adapt_explicit_candidate(record: Mapping[str,Any], *, base_repository_sha: str|None=None)->MaintenanceCandidate:
    allowed={"schema_version","source_kind","source_reference","base_repository_sha","objective","bounded_description","candidate_kind","severity","confidence","recurrence_count","declared_subject_paths","declared_validation_expectations","evidence_references","requested_authority_classes","declared_constraints","estimated_file_count","estimated_changed_line_count","estimated_implementation_seconds","estimated_validation_seconds","lifecycle_disposition","reason_codes","operator_priority","source_semantic_identity"}
    reasons=[]
    if set(record)-allowed: reasons.append("unknown_field")
    required={"objective","candidate_kind","declared_subject_paths","requested_authority_classes"}
    if not required.issubset(record): reasons.append("missing_semantic_field")
    return _build(source_kind="explicit_maintenance_candidate",source_reference=str(record.get("source_reference") or "explicit"),base_repository_sha=str(record.get("base_repository_sha") or base_repository_sha or ""),objective=str(record.get("objective") or ""),bounded_description=str(record.get("bounded_description") or record.get("objective") or ""),candidate_kind=str(record.get("candidate_kind") or ""),severity=record.get("severity","medium"),confidence=record.get("confidence","medium"),recurrence_count=int(record.get("recurrence_count",1)),declared_subject_paths=record.get("declared_subject_paths") or (),declared_validation_expectations=record.get("declared_validation_expectations") or (),evidence_references=record.get("evidence_references") or (),requested_authority_classes=record.get("requested_authority_classes") or (),declared_constraints=record.get("declared_constraints") or (),estimated_file_count=int(record.get("estimated_file_count",1)),estimated_changed_line_count=int(record.get("estimated_changed_line_count",1)),estimated_implementation_seconds=int(record.get("estimated_implementation_seconds",60)),estimated_validation_seconds=int(record.get("estimated_validation_seconds",60)),lifecycle_disposition=str(record.get("lifecycle_disposition") or "candidate_ready"),reason_codes=tuple(reasons)+tuple(record.get("reason_codes") or ()),source_semantic_identity=record.get("source_semantic_identity") if isinstance(record.get("source_semantic_identity"),Mapping) else None,operator_priority=record.get("operator_priority"))

def normalize_candidate_set(candidates: Sequence[MaintenanceCandidate])->dict[str,Any]:
    counts=Counter(c.source_kind for c in candidates); groups=defaultdict(list)
    for c in candidates: groups[c.candidate_id].append(c)
    out=[]; dups=[]; contradictions=[]; blocked=[]
    for cid in sorted(groups):
        gs=groups[cid]; mats={digest(g.material_payload()) for g in gs}
        if len(mats)>1:
            first=gs[0]
            bc=_build(**{**{k:v for k,v in first.to_dict().items() if k in []}}) if False else None
            val=first.to_dict(); val.update(lifecycle_disposition="candidate_contradicted", reason_codes=tuple(sorted(set(first.reason_codes)|{"candidate_contradicted"})))
            bc=adapt_explicit_candidate({"source_reference":first.source_reference,"base_repository_sha":first.base_repository_sha,"objective":first.objective,"bounded_description":first.bounded_description,"candidate_kind":first.candidate_kind,"severity":first.severity,"confidence":first.confidence,"declared_subject_paths":first.declared_subject_paths,"declared_validation_expectations":first.declared_validation_expectations,"evidence_references":first.evidence_references,"requested_authority_classes":first.requested_authority_classes,"declared_constraints":first.declared_constraints,"estimated_file_count":first.estimated_file_count,"estimated_changed_line_count":first.estimated_changed_line_count,"estimated_implementation_seconds":first.estimated_implementation_seconds,"estimated_validation_seconds":first.estimated_validation_seconds,"lifecycle_disposition":"candidate_contradicted","reason_codes":["candidate_contradicted"],"source_semantic_identity":{"contradicted":cid}}, base_repository_sha=first.base_repository_sha)
            out.append(bc); contradictions.append({"candidate_id":cid,"source_references":sorted(g.source_reference for g in gs)}) ; blocked.append(bc.candidate_id)
        else:
            first=gs[0]; evid=tuple(sorted(set().union(*(set(g.evidence_references) for g in gs))))
            rec=len(evid) or len(gs)
            merged=adapt_explicit_candidate({"source_reference":first.source_reference,"base_repository_sha":first.base_repository_sha,"objective":first.objective,"bounded_description":first.bounded_description,"candidate_kind":first.candidate_kind,"severity":first.severity,"confidence":first.confidence,"recurrence_count":rec,"declared_subject_paths":first.declared_subject_paths,"declared_validation_expectations":first.declared_validation_expectations,"evidence_references":evid,"requested_authority_classes":first.requested_authority_classes,"declared_constraints":first.declared_constraints,"estimated_file_count":first.estimated_file_count,"estimated_changed_line_count":first.estimated_changed_line_count,"estimated_implementation_seconds":first.estimated_implementation_seconds,"estimated_validation_seconds":first.estimated_validation_seconds,"reason_codes":first.reason_codes,"operator_priority":first.operator_priority,"source_semantic_identity":None}, base_repository_sha=first.base_repository_sha)
            out.append(merged)
            if len(gs)>1: dups.append({"candidate_id":cid,"source_references":sorted(g.source_reference for g in gs)})
            if merged.lifecycle_disposition!="candidate_ready": blocked.append(merged.candidate_id)
    out=sorted(out,key=lambda c:c.candidate_id)
    payload={"schema_version":CANDIDATE_SET_SCHEMA,"input_source_counts":dict(sorted(counts.items())),"canonical_candidates":[c.to_dict() for c in out],"duplicate_groups":dups,"contradictions":contradictions,"blocked_candidates":sorted(set(blocked))}
    payload["aggregate_digest"]=digest(payload)
    return payload

__all__=["MaintenanceCandidate","adapt_governed_signal","adapt_work_item_packet","adapt_genesis_metadata","adapt_explicit_candidate","normalize_candidate_set","canonical_json_bytes","digest","SOURCE_KINDS","SEVERITIES","CONFIDENCES","DISPOSITIONS","REASON_CODES","AUTHORITY_CLASSES"]
