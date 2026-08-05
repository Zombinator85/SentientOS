"""Canonical immutable maintenance task authority leases.

Metadata only: no implementation, validation, Git, publication, host, or runtime effects.
"""
from __future__ import annotations

import argparse, fcntl, fnmatch, hashlib, json, os
from pathlib import Path
from typing import Any, Mapping, Sequence, cast

from sentientos.maintenance_candidate import CANDIDATE_SET_SCHEMA, digest as cand_digest
from sentientos.maintenance_candidate_selector import SELECTION_SCHEMA
from sentientos import maintenance_task_journal as journal

GRANT_SCHEMA="sentientos.maintenance_authority_grant:v1"
LEASE_SCHEMA="sentientos.maintenance_task_authority_lease:v1"
ACTION_REQUEST_SCHEMA="sentientos.maintenance_lease_action_request:v1"
ACTION_DECISION_SCHEMA="sentientos.maintenance_lease_action_decision:v1"
AUTHORITY_CLASSES=frozenset({"proposal_selection_only","filesystem_read","filesystem_write","documentation_edit","test_edit","code_edit","governance_edit","journal_read","validation_execute","implementation_agent_session","implementation_process_execute","implementation_instruction_disclosure","remote_model_invocation","repository_state_read","repository_workspace_provision","repository_workspace_modify"})
DENIED_AUTHORITY=frozenset({"repository_commit","branch_publication","pull_request_mutation","remote_publication","host_actuation","runtime_capability_adoption","unrestricted_secret_access"})
GRANT_FIELDS=frozenset({"schema_version","grant_id","grant_digest","operator_reference","approval_reference","repository_identity","allowed_base_sha","allowed_base_sha_rule","allowed_candidate_kinds","allowed_path_prefixes","forbidden_path_patterns","allowed_authority_classes","maximum_file_count","maximum_changed_line_count","maximum_implementation_seconds","maximum_validation_seconds","maximum_wall_clock_seconds","maximum_attempts","maximum_corrective_retries","not_before","expires_at","grant_generation","explicit_constraints"})
LEASE_FIELDS=frozenset({"schema_version","lease_id","lease_digest","task_id","candidate_id","candidate_revision_digest","canonical_candidate_digest","candidate_set_digest","selection_digest","selector_policy_digest","operator_grant_id","operator_grant_digest","repository_identity","base_sha","objective_digest","admitted_scope_digest","admitted_subject_paths","forbidden_path_patterns","authority_classes","validation_expectations","maximum_file_count","maximum_changed_line_count","maximum_implementation_seconds","maximum_validation_seconds","maximum_wall_clock_seconds","maximum_attempts","maximum_corrective_retries","not_before","expires_at","grant_generation","issued_at","lease_status","reason_codes"})

def canonical_json_bytes(v: Any)->bytes: return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def sha256(v: Any)->str: return "sha256:"+hashlib.sha256(canonical_json_bytes(v)).hexdigest()
def _seal(d: Mapping[str,Any], field: str)->str: return sha256({k:v for k,v in d.items() if k!=field})
def _read_json(path: str|Path)->dict[str,Any]: return cast(dict[str, Any], json.loads(Path(path).read_text(encoding="utf-8")))
def _inside(path: str, prefixes: Sequence[str])->bool:
    return any(path==p.rstrip("/") or path.startswith(p.rstrip("/")+"/") for p in prefixes)
def _event_id(kind: str, task_id: str, payload: Mapping[str,Any])->str: return "mevent_"+hashlib.sha256(canonical_json_bytes({"kind":kind,"task_id":task_id,"payload":payload})).hexdigest()[:32]

def verify_grant(grant: Mapping[str,Any], *, evaluation_time: str, current_generation: str|None=None)->dict[str,Any]:
    reasons=[]
    if set(grant)-GRANT_FIELDS or grant.get("schema_version")!=GRANT_SCHEMA or not grant.get("operator_reference") or not grant.get("approval_reference"): reasons.append("grant_invalid")
    if grant.get("grant_digest") != _seal(grant,"grant_digest"): reasons.append("grant_invalid")
    if any(a not in AUTHORITY_CLASSES or a in DENIED_AUTHORITY for a in grant.get("allowed_authority_classes",())): reasons.append("grant_invalid")
    if evaluation_time < str(grant.get("not_before","")): reasons.append("grant_not_yet_valid")
    if evaluation_time >= str(grant.get("expires_at","~")): reasons.append("grant_expired")
    if current_generation is not None and str(grant.get("grant_generation")) != current_generation: reasons.append("grant_generation_mismatch")
    return {"schema_version":"sentientos.maintenance_authority_grant_verification:v1","status":"grant_valid" if not reasons else "grant_invalid","reason_codes":tuple(dict.fromkeys(reasons)),"grant_id":grant.get("grant_id"),"grant_digest":grant.get("grant_digest")}

def seal_grant(payload: Mapping[str,Any])->dict[str,Any]:
    d=dict(payload); d["schema_version"]=GRANT_SCHEMA; d["grant_digest"]=_seal({**d,"grant_digest":""},"grant_digest"); return d

def _candidate_set_ok(cs: Mapping[str,Any])->bool:
    return cs.get("schema_version")==CANDIDATE_SET_SCHEMA and cs.get("aggregate_digest")==cand_digest({k:v for k,v in cs.items() if k!="aggregate_digest"})
def _selection_ok(sel: Mapping[str,Any])->bool:
    return sel.get("schema_version")==SELECTION_SCHEMA and sel.get("selection_digest")==cand_digest({k:v for k,v in sel.items() if k!="selection_digest"})

def admitted_scope_digest(*, candidate: Mapping[str,Any], selection: Mapping[str,Any], grant: Mapping[str,Any], maximum_wall_clock_seconds:int|None=None, maximum_attempts:int|None=None, maximum_corrective_retries:int|None=None, not_before:str|None=None, expires_at:str|None=None)->str:
    return sha256({"candidate_id":candidate["candidate_id"],"candidate_revision_digest":candidate["candidate_revision_digest"],"subject_paths":tuple(candidate["declared_subject_paths"]),"authority_classes":tuple(candidate["requested_authority_classes"]),"validation_expectations":tuple(candidate["declared_validation_expectations"]),"budgets":{"files":candidate["estimated_file_count"],"changed_lines":candidate["estimated_changed_line_count"],"implementation_seconds":candidate["estimated_implementation_seconds"],"validation_seconds":candidate["estimated_validation_seconds"],"wall_clock_seconds": maximum_wall_clock_seconds or grant["maximum_wall_clock_seconds"]},"maximum_attempts": maximum_attempts or grant["maximum_attempts"],"maximum_corrective_retries": maximum_corrective_retries if maximum_corrective_retries is not None else grant["maximum_corrective_retries"],"not_before": not_before or grant["not_before"],"expires_at": expires_at or grant["expires_at"],"grant_digest":grant["grant_digest"],"selector_policy_digest":selection["policy_digest"]})

def derive_lease(candidate: Mapping[str,Any], candidate_set: Mapping[str,Any], selection: Mapping[str,Any], grant: Mapping[str,Any], *, evaluation_time: str, repository_identity: str|None=None, maximum_wall_clock_seconds:int|None=None, maximum_attempts:int|None=None, maximum_corrective_retries:int|None=None, expires_at:str|None=None)->dict[str,Any]:
    scope=admitted_scope_digest(candidate=candidate, selection=selection, grant=grant, maximum_wall_clock_seconds=maximum_wall_clock_seconds, maximum_attempts=maximum_attempts, maximum_corrective_retries=maximum_corrective_retries, expires_at=expires_at)
    task_id=journal.derive_task_id(candidate_ref=candidate["candidate_id"], base_sha=candidate["base_repository_sha"], contract_digest=candidate["candidate_revision_digest"], admitted_scope_digest=scope)
    lease_id=journal.derive_authority_lease_id(task_id, scope)
    lease={"schema_version":LEASE_SCHEMA,"lease_id":lease_id,"lease_digest":"","task_id":task_id,"candidate_id":candidate["candidate_id"],"candidate_revision_digest":candidate["candidate_revision_digest"],"canonical_candidate_digest":candidate["canonical_candidate_digest"],"candidate_set_digest":candidate_set["aggregate_digest"],"selection_digest":selection["selection_digest"],"selector_policy_digest":selection["policy_digest"],"operator_grant_id":grant["grant_id"],"operator_grant_digest":grant["grant_digest"],"repository_identity":repository_identity or grant["repository_identity"],"base_sha":candidate["base_repository_sha"],"objective_digest":sha256(candidate.get("objective","")),"admitted_scope_digest":scope,"admitted_subject_paths":tuple(candidate["declared_subject_paths"]),"forbidden_path_patterns":tuple(grant.get("forbidden_path_patterns",())),"authority_classes":tuple(candidate["requested_authority_classes"]),"validation_expectations":tuple(candidate["declared_validation_expectations"]),"maximum_file_count":candidate["estimated_file_count"],"maximum_changed_line_count":candidate["estimated_changed_line_count"],"maximum_implementation_seconds":candidate["estimated_implementation_seconds"],"maximum_validation_seconds":candidate["estimated_validation_seconds"],"maximum_wall_clock_seconds":maximum_wall_clock_seconds or grant["maximum_wall_clock_seconds"],"maximum_attempts":maximum_attempts or grant["maximum_attempts"],"maximum_corrective_retries":maximum_corrective_retries if maximum_corrective_retries is not None else grant["maximum_corrective_retries"],"not_before":grant["not_before"],"expires_at":expires_at or grant["expires_at"],"grant_generation":grant["grant_generation"],"issued_at":evaluation_time,"lease_status":"active","reason_codes":()}
    lease["lease_digest"]=_seal(lease,"lease_digest")
    return lease

def validate_subset(candidate: Mapping[str,Any], grant: Mapping[str,Any])->list[str]:
    r=[]
    if candidate.get("candidate_kind") not in grant.get("allowed_candidate_kinds",()): r.append("candidate_kind_not_granted")
    for p in candidate.get("declared_subject_paths",()):
        if not _inside(p, grant.get("allowed_path_prefixes",())): r.append("candidate_path_not_granted")
        if any(fnmatch.fnmatch(p, pat) for pat in grant.get("forbidden_path_patterns",())): r.append("candidate_path_forbidden")
    if set(candidate.get("requested_authority_classes",()))-set(grant.get("allowed_authority_classes",())): r.append("candidate_authority_not_granted")
    checks=[("estimated_file_count","maximum_file_count","candidate_file_budget_not_granted"),("estimated_changed_line_count","maximum_changed_line_count","candidate_diff_budget_not_granted"),("estimated_implementation_seconds","maximum_implementation_seconds","candidate_implementation_budget_not_granted"),("estimated_validation_seconds","maximum_validation_seconds","candidate_validation_budget_not_granted")]
    for ck,gk,code in checks:
        if int(candidate.get(ck,0))>int(grant.get(gk,0)): r.append(code)
    if grant.get("allowed_base_sha") and candidate.get("base_repository_sha") != grant.get("allowed_base_sha"): r.append("candidate_base_sha_not_granted")
    return sorted(set(r))

def _find_candidate(cs: Mapping[str,Any], sel: Mapping[str,Any])->dict[str,Any]|None:
    for c in cs.get("canonical_candidates",()):
        if c.get("candidate_id")==sel.get("selected_candidate_id"): return dict(c)
    return None

def _persist_lease(state_root: Path, lease: Mapping[str,Any])->str:
    d=state_root/"maintenance_leases"; d.mkdir(parents=True,exist_ok=True)
    path=d/(str(lease["lease_id"])+".json")
    data=canonical_json_bytes(lease)+b"\n"
    if path.exists():
        if path.is_symlink(): return "conflict"
        return "exists" if path.read_bytes()==data else "conflict"
    fd=os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    with os.fdopen(fd,"wb") as fh: fh.write(data); fh.flush(); os.fsync(fh.fileno())
    dirfd=os.open(d, os.O_RDONLY); os.fsync(dirfd); os.close(dirfd)
    return "created"

def admit_selected_candidate(*, state_root: str|Path, candidate_set: Mapping[str,Any], selection: Mapping[str,Any], operator_grant: Mapping[str,Any], evaluation_time: str, repo_root: str|Path|None=None, interruption_point: str|None=None)->dict[str,Any]:
    root=journal.resolve_state_root(state_root, repo_root=repo_root); lockp=root/("admit_"+hashlib.sha256(str(selection.get("selected_candidate_id")).encode()).hexdigest()[:16]+".lock"); lockp.touch(exist_ok=True)
    with lockp.open("r+") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        gv=verify_grant(operator_grant,evaluation_time=evaluation_time)
        if gv["status"]!="grant_valid": return {"status":"task_lease_blocked","reason_codes":gv["reason_codes"]}
        if not _candidate_set_ok(candidate_set) or not _selection_ok(selection): return {"status":"task_lease_blocked","reason_codes":("selection_integrity_failed",)}
        if selection.get("result_status")!="ready_for_scope_admission": return {"status":"task_lease_blocked","reason_codes":("selection_integrity_failed",)}
        cand=_find_candidate(candidate_set, selection)
        if not cand or cand.get("candidate_revision_digest")!=selection.get("selected_candidate_revision_digest") or cand.get("canonical_candidate_digest")!=cand_digest({k:v for k,v in cand.items() if k!="canonical_candidate_digest"}): return {"status":"task_lease_blocked","reason_codes":("candidate_integrity_failed",)}
        reasons=validate_subset(cand, operator_grant)
        if reasons: return {"status":"task_lease_blocked","reason_codes":tuple(reasons)}
        lease=derive_lease(cand,candidate_set,selection,operator_grant,evaluation_time=evaluation_time)
        persisted=_persist_lease(root, lease)
        if persisted=="conflict": return {"status":"task_lease_conflict","reason_codes":("lease_conflict",),"lease_id":lease["lease_id"],"task_id":lease["task_id"]}
        if interruption_point=="after_lease_persisted": return {"status":"task_lease_recovered","interrupted_after":"lease_persisted","lease_id":lease["lease_id"],"task_id":lease["task_id"]}
        create_payload={"candidate_ref":cand["candidate_id"],"candidate_revision_digest":cand["candidate_revision_digest"],"canonical_candidate_digest":cand["canonical_candidate_digest"],"selection_digest":selection["selection_digest"],"selector_policy_digest":selection["policy_digest"],"admitted_scope_digest":lease["admitted_scope_digest"],"operator_grant_id":operator_grant["grant_id"],"operator_grant_digest":operator_grant["grant_digest"],"base_sha":cand["base_repository_sha"],"maximum_attempts":lease["maximum_attempts"],"maximum_corrective_retries":lease["maximum_corrective_retries"]}
        cr=journal.append_event(root,"task_created",task_id=lease["task_id"],payload=create_payload,event_id=_event_id("task_created",lease["task_id"],create_payload),repository_sha=cand["base_repository_sha"],recorded_at=evaluation_time,repo_root=repo_root)
        if cr.status not in {"event_appended","event_already_recorded"}: return {"status":"task_lease_journal_invalid","reason_codes":(cr.reason_code,)}
        if interruption_point=="after_task_created": return {"status":"task_lease_recovered","interrupted_after":"task_created","lease_id":lease["lease_id"],"task_id":lease["task_id"]}
        bind={"lease_id":lease["lease_id"],"lease_digest":lease["lease_digest"],"scope_digest":lease["admitted_scope_digest"],"expires_at":lease["expires_at"],"candidate_revision_digest":lease["candidate_revision_digest"],"canonical_candidate_digest":lease["canonical_candidate_digest"],"selection_digest":lease["selection_digest"],"selector_policy_digest":lease["selector_policy_digest"],"operator_grant_id":lease["operator_grant_id"],"operator_grant_digest":lease["operator_grant_digest"],"maximum_attempts":lease["maximum_attempts"],"maximum_corrective_retries":lease["maximum_corrective_retries"]}
        br=journal.append_event(root,"authority_lease_bound",task_id=lease["task_id"],payload=bind,event_id=_event_id("authority_lease_bound",lease["task_id"],bind),repository_sha=cand["base_repository_sha"],recorded_at=evaluation_time,repo_root=repo_root)
        if br.status not in {"event_appended","event_already_recorded"}: return {"status":"task_lease_journal_invalid","reason_codes":(br.reason_code,)}
        snap=journal.materialize_snapshot(root, lease["task_id"], repo_root=repo_root, evaluation_time=evaluation_time)
        if snap.get("active_lease_digest")!=lease["lease_digest"]: return {"status":"task_lease_journal_invalid","reason_codes":("lease_snapshot_mismatch",)}
        st="task_lease_ready" if cr.status=="event_appended" and br.status=="event_appended" and persisted=="created" else ("task_lease_already_ready" if cr.status=="event_already_recorded" and br.status=="event_already_recorded" and persisted=="exists" else "task_lease_recovered")
        return {"status":st,"task_id":lease["task_id"],"lease_id":lease["lease_id"],"lease_digest":lease["lease_digest"],"admitted_scope_digest":lease["admitted_scope_digest"],"task_created_event_id":cr.event.event_id if cr.event else None,"authority_lease_bound_event_id":br.event.event_id if br.event else None,"snapshot":snap,"lease":lease}

def load_lease(state_root: str|Path, lease_id: str, *, repo_root: str|Path|None=None)->dict[str,Any]:
    root=journal.resolve_state_root(state_root, repo_root=repo_root); p=root/"maintenance_leases"/(lease_id+".json")
    if p.is_symlink(): raise ValueError("lease_symlink_rejected")
    lease=json.loads(p.read_text(encoding="utf-8"))
    if lease.get("lease_id")!=lease_id or lease.get("lease_digest")!=_seal(lease,"lease_digest"): raise ValueError("lease_integrity_failed")
    return cast(dict[str, Any], lease)

def verify_lease(state_root: str|Path, lease_id: str, *, evaluation_time: str, repo_root: str|Path|None=None)->dict[str,Any]:
    try:
        lease=load_lease(state_root,lease_id,repo_root=repo_root); snap=journal.materialize_snapshot(state_root,lease["task_id"],repo_root=repo_root,evaluation_time=evaluation_time)
        ok=snap.get("active_lease_digest")==lease["lease_digest"] and snap.get("lease_status")=="active" and evaluation_time < lease["expires_at"]
        return {"schema_version":"sentientos.maintenance_task_authority_lease_verification:v1","status":"lease_active" if ok else "lease_inactive","lease_id":lease_id,"task_id":lease["task_id"],"lease_digest":lease["lease_digest"],"snapshot":snap}
    except Exception as e: return {"schema_version":"sentientos.maintenance_task_authority_lease_verification:v1","status":"lease_invalid","reason_codes":(str(e),),"lease_id":lease_id}

def verify_action(state_root: str|Path, request: Mapping[str,Any], *, evaluation_time: str, repo_root: str|Path|None=None)->dict[str,Any]:
    status="action_within_lease"; reason=[]
    try:
        if request.get("schema_version")!=ACTION_REQUEST_SCHEMA: raise ValueError("action_request_invalid")
        lease=load_lease(state_root,str(request["lease_id"]),repo_root=repo_root); snap=journal.materialize_snapshot(state_root,lease["task_id"],repo_root=repo_root,evaluation_time=evaluation_time)
        if snap.get("journal_integrity_status")!="journal_ready": status="action_denied_integrity"
        elif snap.get("lifecycle_state")=="lease_revoked" or snap.get("lease_status")=="revoked": status="action_denied_lease_revoked"
        elif snap.get("active_lease_digest")!=lease["lease_digest"]: status="action_denied_integrity"
        elif evaluation_time >= lease["expires_at"] or snap.get("lease_status")=="expired": status="action_denied_lease_expired"
        elif request.get("task_id")!=lease["task_id"] or request.get("candidate_revision_digest")!=lease["candidate_revision_digest"] or request.get("base_sha")!=lease["base_sha"]: status="action_denied_state_mismatch"
        elif set(request.get("requested_authority_classes",()))-set(lease["authority_classes"]): status="action_denied_authority"
        elif any((not _inside(p, lease["admitted_subject_paths"]) or any(fnmatch.fnmatch(p,pat) for pat in lease["forbidden_path_patterns"])) for p in request.get("target_paths",())): status="action_denied_scope"
        elif int(request.get("planned_file_count",0))>lease["maximum_file_count"] or int(request.get("planned_changed_lines",0))>lease["maximum_changed_line_count"] or int(request.get("planned_implementation_seconds",0))>lease["maximum_implementation_seconds"] or int(request.get("planned_validation_seconds",0))>lease["maximum_validation_seconds"]: status="action_denied_budget"
        elif int(request.get("attempt_ordinal",0))>lease["maximum_attempts"]: status="action_denied_attempt_limit"
        elif int(request.get("corrective_retry_ordinal",0))>lease["maximum_corrective_retries"]: status="action_denied_retry_limit"
    except Exception as e: status="action_denied_integrity"; reason=[str(e)]
    return {"schema_version":ACTION_DECISION_SCHEMA,"status":status,"reason_codes":tuple(reason),"executed":False}

def revoke_lease(state_root: str|Path, *, task_id: str, lease_id: str, operator_revocation_reference: str, evaluation_time: str, repo_root: str|Path|None=None)->dict[str,Any]:
    if not operator_revocation_reference: return {"status":"revocation_rejected","reason_codes":("missing_operator_revocation_reference",)}
    lease=load_lease(state_root,lease_id,repo_root=repo_root)
    if lease["task_id"]!=task_id: return {"status":"revocation_rejected","reason_codes":("task_lease_mismatch",)}
    payload={"lease_id":lease_id,"operator_revocation_reference":operator_revocation_reference,"lease_digest":lease["lease_digest"]}
    r=journal.append_event(state_root,"authority_lease_revoked",task_id=task_id,payload=payload,event_id=_event_id("authority_lease_revoked",task_id,payload),recorded_at=evaluation_time,repository_sha=lease["base_sha"],repo_root=repo_root)
    return {"status":"lease_revoked" if r.status in {"event_appended","event_already_recorded"} else "revocation_rejected","event_id":r.event.event_id if r.event else None,"reason_codes":() if r.status in {"event_appended","event_already_recorded"} else (r.reason_code,)}

__all__=["GRANT_SCHEMA","LEASE_SCHEMA","ACTION_REQUEST_SCHEMA","ACTION_DECISION_SCHEMA","AUTHORITY_CLASSES","canonical_json_bytes","sha256","seal_grant","verify_grant","derive_lease","admit_selected_candidate","verify_lease","verify_action","revoke_lease","load_lease","admitted_scope_digest"]
