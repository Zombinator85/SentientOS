"""Deterministic metadata-only maintenance candidate selector."""
from __future__ import annotations
from dataclasses import dataclass, asdict
import fnmatch, hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence
from sentientos.maintenance_candidate import AUTHORITY_CLASSES, CANDIDATE_SET_SCHEMA, MaintenanceCandidate, canonical_json_bytes, digest
from sentientos import maintenance_task_journal as journal

SELECTION_SCHEMA="sentientos.maintenance_candidate_selection:v1"
POLICY_SCHEMA="sentientos.maintenance_candidate_selector_policy:v1"
STATUSES=frozenset({"ready_for_scope_admission","idle_no_viable_candidate","selection_blocked","candidate_set_invalid","journal_state_invalid"})
REASONS=("candidate_scope_unknown","candidate_path_not_allowed","candidate_path_forbidden","candidate_authority_unavailable","candidate_kind_not_allowed","candidate_base_sha_mismatch","candidate_file_budget_exceeded","candidate_diff_budget_exceeded","candidate_implementation_budget_exceeded","candidate_validation_budget_exceeded","candidate_contradicted","candidate_source_blocked","candidate_evidence_insufficient","candidate_already_active","candidate_already_resolved","candidate_reconsideration_required","candidate_journal_unhealthy")
SEV={"low":1,"medium":2,"high":3,"critical":4}; CONF={"low":1,"medium":2,"high":3,"confirmed":4}

@dataclass(frozen=True)
class SelectorPolicy:
    repository_base_sha: str
    allowed_path_prefixes: tuple[str,...]
    forbidden_path_patterns: tuple[str,...]
    available_authority_classes: tuple[str,...]
    maximum_file_count: int
    maximum_estimated_changed_lines: int
    maximum_implementation_seconds: int
    maximum_validation_seconds: int
    allowed_candidate_kinds: tuple[str,...]
    minimum_severity: str|None=None
    permit_reconsideration: bool=False
    reconsideration_tokens: tuple[str,...]=()
    schema_version: str=POLICY_SCHEMA
    policy_digest: str=""
    def to_dict(self)->dict[str,Any]: return asdict(self)

def build_policy(data: Mapping[str,Any])->SelectorPolicy:
    allowed={"schema_version","repository_base_sha","allowed_path_prefixes","forbidden_path_patterns","available_authority_classes","maximum_file_count","maximum_estimated_changed_lines","maximum_implementation_seconds","maximum_validation_seconds","allowed_candidate_kinds","minimum_severity","permit_reconsideration","reconsideration_tokens","policy_digest"}
    if set(data)-allowed: raise ValueError("invalid_policy_unknown_field")
    auth=tuple(sorted(str(x) for x in data.get("available_authority_classes",()) if str(x)))
    if any(a not in AUTHORITY_CLASSES for a in auth): raise ValueError("invalid_policy_unknown_authority")
    p=SelectorPolicy(repository_base_sha=str(data["repository_base_sha"]),allowed_path_prefixes=tuple(sorted(data.get("allowed_path_prefixes") or ())),forbidden_path_patterns=tuple(sorted(data.get("forbidden_path_patterns") or ())),available_authority_classes=auth,maximum_file_count=int(data["maximum_file_count"]),maximum_estimated_changed_lines=int(data["maximum_estimated_changed_lines"]),maximum_implementation_seconds=int(data["maximum_implementation_seconds"]),maximum_validation_seconds=int(data["maximum_validation_seconds"]),allowed_candidate_kinds=tuple(sorted(data.get("allowed_candidate_kinds") or ())),minimum_severity=data.get("minimum_severity"),permit_reconsideration=bool(data.get("permit_reconsideration",False)),reconsideration_tokens=tuple(sorted(data.get("reconsideration_tokens") or ())))
    return SelectorPolicy(**{**p.to_dict(),"policy_digest":digest({k:v for k,v in p.to_dict().items() if k!="policy_digest"})})

def candidate_from_dict(d: Mapping[str,Any])->MaintenanceCandidate:
    return MaintenanceCandidate(**{**d,"declared_subject_paths":tuple(d.get("declared_subject_paths",())),"declared_validation_expectations":tuple(d.get("declared_validation_expectations",())),"evidence_references":tuple(d.get("evidence_references",())),"requested_authority_classes":tuple(d.get("requested_authority_classes",())),"declared_constraints":tuple(d.get("declared_constraints",())),"reason_codes":tuple(d.get("reason_codes",()))})

def _journal_snapshot(root: str|Path|None, c: MaintenanceCandidate)->tuple[str,dict[str,Any]]:
    if not root: return "pending", {"candidate_id":c.candidate_id,"state":"pending"}
    snaps=journal.discover_maintenance_task_snapshots(root, candidate_ref=c.candidate_id, repo_root=Path.cwd())
    unhealthy=[x for x in snaps if x.get("integrity_status")!="journal_ready"]
    if unhealthy: return "journal_unhealthy", unhealthy[0].get("snapshot", unhealthy[0])
    matches=[x.get("snapshot",{}) for x in snaps if x.get("candidate_ref")==c.candidate_id]
    if not matches: return "pending", {"candidate_id":c.candidate_id,"state":"pending"}
    # active beats terminal for exclusion.
    for snap in matches:
        st=snap.get("lifecycle_state")
        if st not in {"closed","cancelled","blocked","not_created"}: return "active", snap
    snap=matches[-1]; st=snap.get("lifecycle_state")
    if st=="closed": return "resolved", snap
    if st=="cancelled": return "cancelled", snap
    if st=="blocked": return "blocked", snap
    return "pending", snap

def task_id_for_candidate(candidate_id: str)->str:
    return "mtask_"+hashlib.sha256(canonical_json_bytes({"candidate_id":candidate_id})).hexdigest()[:32]

def _eligible(c:MaintenanceCandidate,p:SelectorPolicy,life:str,snap:Mapping[str,Any])->list[str]:
    r=[]
    if not c.declared_subject_paths: r.append("candidate_scope_unknown")
    for path in c.declared_subject_paths:
        if p.allowed_path_prefixes and not any(path==pre.rstrip("/") or path.startswith(pre.rstrip("/")+"/") for pre in p.allowed_path_prefixes): r.append("candidate_path_not_allowed")
        if any(fnmatch.fnmatch(path,pat) for pat in p.forbidden_path_patterns): r.append("candidate_path_forbidden")
    if set(c.requested_authority_classes)-set(p.available_authority_classes): r.append("candidate_authority_unavailable")
    if c.candidate_kind not in p.allowed_candidate_kinds: r.append("candidate_kind_not_allowed")
    if c.base_repository_sha != p.repository_base_sha: r.append("candidate_base_sha_mismatch")
    if c.estimated_file_count>p.maximum_file_count: r.append("candidate_file_budget_exceeded")
    if c.estimated_changed_line_count>p.maximum_estimated_changed_lines: r.append("candidate_diff_budget_exceeded")
    if c.estimated_implementation_seconds>p.maximum_implementation_seconds: r.append("candidate_implementation_budget_exceeded")
    if c.estimated_validation_seconds>p.maximum_validation_seconds: r.append("candidate_validation_budget_exceeded")
    if c.lifecycle_disposition=="candidate_contradicted" or "candidate_contradicted" in c.reason_codes: r.append("candidate_contradicted")
    if c.lifecycle_disposition in {"candidate_blocked","candidate_insufficient_metadata"} or "candidate_source_blocked" in c.reason_codes: r.append("candidate_source_blocked")
    if not c.evidence_references: r.append("candidate_evidence_insufficient")
    if life=="journal_unhealthy": r.append("candidate_journal_unhealthy")
    if life=="active": r.append("candidate_already_active")
    if life=="resolved": r.append("candidate_already_resolved")
    if life in {"cancelled","blocked"}:
        prior=str(snap.get("candidate_revision_digest") or snap.get("payload",{}).get("candidate_revision_digest") or "")
        if not p.permit_reconsideration or (prior==c.candidate_revision_digest and c.candidate_id not in p.reconsideration_tokens): r.append("candidate_reconsideration_required")
    if p.minimum_severity and SEV.get(c.severity,0)<SEV.get(p.minimum_severity,0): r.append("candidate_kind_not_allowed")
    return sorted(set(r), key=REASONS.index) if all(x in REASONS for x in set(r)) else sorted(set(r))

def select_candidate(candidate_set: Mapping[str,Any], policy: SelectorPolicy|Mapping[str,Any], *, journal_state_root: str|Path|None=None)->dict[str,Any]:
    p=policy if isinstance(policy,SelectorPolicy) else build_policy(policy)
    if candidate_set.get("schema_version")!=CANDIDATE_SET_SCHEMA: return {"schema_version":SELECTION_SCHEMA,"result_status":"candidate_set_invalid"}
    candidates=[candidate_from_dict(d) for d in candidate_set.get("canonical_candidates",())]
    eligible=[]; ineligible={}; journal_refs=[]; journal_bad=False
    if journal_state_root:
        allsnaps=journal.discover_maintenance_task_snapshots(journal_state_root, repo_root=Path.cwd())
        if any(s.get("integrity_status")!="journal_ready" and not s.get("candidate_ref") for s in allsnaps):
            return {"schema_version":SELECTION_SCHEMA,"result_status":"journal_state_invalid","reason_codes":["candidate_journal_unhealthy"]}
    for c in sorted(candidates,key=lambda x:x.candidate_id):
        life,snap=_journal_snapshot(journal_state_root,c); journal_refs.append({"candidate_id":c.candidate_id,"lifecycle":life,"snapshot_digest":snap.get("snapshot_digest")})
        reasons=_eligible(c,p,life,snap)
        if reasons: ineligible[c.candidate_id]=reasons
        else: eligible.append(c)
        if "candidate_journal_unhealthy" in reasons: journal_bad=True
    ranked=sorted(eligible,key=lambda c: (-(c.operator_priority if c.operator_priority is not None else -1),-SEV.get(c.severity,0),-c.recurrence_count,-CONF.get(c.confidence,0),c.estimated_file_count+c.estimated_changed_line_count,c.candidate_id))
    selected=ranked[0] if ranked else None
    status="journal_state_invalid" if journal_bad else ("ready_for_scope_admission" if selected else "idle_no_viable_candidate")
    artifact={"schema_version":SELECTION_SCHEMA,"requested_base_sha":p.repository_base_sha,"policy_digest":p.policy_digest,"candidate_set_digest":candidate_set.get("aggregate_digest"),"journal_state_digest":digest(journal_refs),"journal_references_consulted":journal_refs,"eligible_candidate_ids":[c.candidate_id for c in eligible],"ineligible_candidate_ids":ineligible,"ranked_candidate_ids":[c.candidate_id for c in ranked],"selected_candidate_id":selected.candidate_id if selected else None,"selected_candidate_revision_digest":selected.candidate_revision_digest if selected else None,"selected_candidate_summary":selected.objective if selected else None,"proposed_subject_paths":selected.declared_subject_paths if selected else (),"proposed_validation_expectations":selected.declared_validation_expectations if selected else (),"requested_authority_classes":selected.requested_authority_classes if selected else (),"resource_estimates":({"estimated_file_count":selected.estimated_file_count,"estimated_changed_line_count":selected.estimated_changed_line_count,"estimated_implementation_seconds":selected.estimated_implementation_seconds,"estimated_validation_seconds":selected.estimated_validation_seconds} if selected else {}),"result_status":status,"idle_reason_aggregation":{r:sum(r in rs for rs in ineligible.values()) for r in REASONS}}
    artifact["selection_digest"]=digest(artifact)
    return artifact

def selection_bytes(a: Mapping[str,Any])->bytes: return canonical_json_bytes(a)+b"\n"
__all__=["SelectorPolicy","build_policy","select_candidate","selection_bytes","task_id_for_candidate","SELECTION_SCHEMA","POLICY_SCHEMA","REASONS","STATUSES"]
