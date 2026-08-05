"""Lease-bound maintenance implementation-agent session adapter.

Metadata-only controller: no provider invocation, subprocess, network, validation,
Git, publication, host actuation, runtime adoption, or repository mutation.
"""
from __future__ import annotations

import fcntl, hashlib, json, os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, cast

from sentientos import maintenance_task_journal as journal
from sentientos import maintenance_task_authority_lease as lease_mod

DRIVER_SCHEMA="sentientos.maintenance_implementation_agent_driver:v1"
REQUEST_SCHEMA="sentientos.maintenance_implementation_agent_request:v1"
SESSION_SCHEMA="sentientos.maintenance_implementation_agent_session:v1"
RESULT_SCHEMA="sentientos.maintenance_implementation_agent_result:v1"
FAKE_PLAN_SCHEMA="sentientos.maintenance_fake_agent_plan:v1"
CLOSED_DRIVER_KINDS=frozenset({"fake_scripted","local_codex"})
RESERVED_DRIVER_KINDS: frozenset[str]=frozenset()
EFFECT_CLASS_SYNTHETIC="synthetic_no_effect"
SESSION_PREFIX="masession_"
MAX_PLAN_STEPS=20
MAX_PLAN_BYTES=16000
MAX_INSTRUCTION_BYTES=65536
EFFECT_FLAGS={
    "repository_mutation_performed": False,
    "command_execution_performed": False,
    "validation_performed": False,
    "git_operation_performed": False,
    "publication_performed": False,
    "host_effect_performed": False,
    "runtime_adoption_performed": False,
}


def _cj(v: Any)->bytes: return journal.canonical_json_bytes(v)
def digest(v: Any)->str: return journal.sha256_digest(v)
def _seal(d: Mapping[str,Any], field: str)->str: return digest({k:v for k,v in d.items() if k!=field})
def _id(prefix: str, payload: Mapping[str,Any])->str: return prefix+hashlib.sha256(_cj(payload)).hexdigest()[:32]
def _read(path: str|Path)->dict[str,Any]: return cast(dict[str,Any], json.loads(Path(path).read_text(encoding="utf-8")))
def _write_immutable(path: Path, value: Mapping[str,Any])->tuple[str,str]:
    if path.exists() and path.is_symlink(): raise ValueError("immutable_artifact_symlink_rejected")
    path.parent.mkdir(parents=True, exist_ok=True)
    data=_cj(value)+b"\n"
    if path.exists():
        if path.read_bytes()==data: return ("exists", digest(value))
        raise ValueError("immutable_artifact_conflict")
    fd=os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0), 0o600)
    with os.fdopen(fd,"wb") as fh:
        fh.write(data); fh.flush(); os.fsync(fh.fileno())
    dfd=os.open(str(path.parent), os.O_RDONLY)
    try: os.fsync(dfd)
    finally: os.close(dfd)
    return ("created", digest(value))

def load_fake_plan(path: str|Path)->dict[str,Any]:
    p=Path(path)
    if p.is_symlink(): raise ValueError("fake_plan_symlink_rejected")
    raw=p.read_bytes()
    if len(raw)>MAX_PLAN_BYTES: raise ValueError("fake_plan_too_large")
    plan=cast(dict[str,Any], json.loads(raw.decode("utf-8")))
    validate_fake_plan(plan)
    return plan

def validate_fake_plan(plan: Mapping[str,Any])->dict[str,Any]:
    if set(plan)-{"schema_version","steps","plan_id","plan_digest"} or plan.get("schema_version")!=FAKE_PLAN_SCHEMA: raise ValueError("fake_plan_invalid")
    steps=plan.get("steps")
    if not isinstance(steps, list) or not 1<=len(steps)<=MAX_PLAN_STEPS: raise ValueError("fake_plan_invalid")
    terminals=[s for s in steps if isinstance(s,Mapping) and s.get("kind") in {"complete","fail","interrupt"}]
    if len(terminals)!=1 or steps[-1] is not terminals[0]: raise ValueError("fake_plan_terminal_invalid")
    for i,s in enumerate(steps, start=1):
        if not isinstance(s, Mapping) or set(s)-{"kind","progress_label","progress_ordinal","synthetic_artifact_refs","terminal_reason","summary"}: raise ValueError("fake_plan_step_invalid")
        if s.get("kind") not in {"heartbeat","complete","fail","interrupt"}: raise ValueError("fake_plan_step_invalid")
        if "progress_ordinal" in s and int(s["progress_ordinal"])!=i: raise ValueError("fake_plan_step_invalid")
        for k,v in s.items():
            if callable(v) or (isinstance(v,str) and ("$" in v or len(v)>500)): raise ValueError("fake_plan_step_invalid")
    if plan.get("plan_digest") and plan.get("plan_digest") != _seal(plan,"plan_digest"): raise ValueError("fake_plan_digest_invalid")
    return dict(plan)

def seal_fake_plan(steps: Sequence[Mapping[str,Any]], plan_id: str="fake-plan")->dict[str,Any]:
    d={"schema_version":FAKE_PLAN_SCHEMA,"plan_id":plan_id,"steps":[dict(s) for s in steps],"plan_digest":""}
    d["plan_digest"]=_seal(d,"plan_digest"); validate_fake_plan(d); return d

class ImplementationAgentDriver(Protocol):
    def describe_driver(self)->Mapping[str,Any]: ...
    def prepare_session(self, request: Mapping[str,Any], session: Mapping[str,Any])->Mapping[str,Any]: ...
    def observe_session(self, session: Mapping[str,Any], delivered_steps: int)->Mapping[str,Any]: ...
    def request_cancellation(self, session: Mapping[str,Any], cancellation_reference: str)->Mapping[str,Any]: ...

@dataclass(frozen=True)
class FakeScriptedDriver:
    plan: Mapping[str,Any]
    driver_id: str="fake_scripted_default"
    driver_version: str="1"
    def __post_init__(self) -> None: validate_fake_plan(self.plan)
    def describe_driver(self)->Mapping[str,Any]:
        d={"schema_version":DRIVER_SCHEMA,"driver_id":self.driver_id,"driver_kind":"fake_scripted","driver_version":self.driver_version,"supported_session_modes":["scripted_poll"],"effect_class":EFFECT_CLASS_SYNTHETIC,"supports_external_session":False,"supports_polling":True,"supports_cancellation":True,"supports_recovery":True,"descriptor_digest":""}
        d["descriptor_digest"]=_seal(d,"descriptor_digest"); return d
    def prepare_session(self, request: Mapping[str,Any], session: Mapping[str,Any])->Mapping[str,Any]: return {"prepared":True,"plan_digest":self.plan["plan_digest"]}
    def observe_session(self, session: Mapping[str,Any], delivered_steps: int)->Mapping[str,Any]:
        steps=cast(list[Mapping[str,Any]], self.plan["steps"])
        if delivered_steps>=len(steps): return {"kind":"terminal_replay"}
        return dict(steps[delivered_steps])
    def request_cancellation(self, session: Mapping[str,Any], cancellation_reference: str)->Mapping[str,Any]:
        if not cancellation_reference: raise ValueError("cancellation_reference_required")
        return {"kind":"interrupt","terminal_reason":"agent_session_cancelled","summary":"cancelled","cancellation_reference":cancellation_reference}

def default_driver_registry(fake_plan: Mapping[str,Any]|None=None)->dict[str,ImplementationAgentDriver]:
    plan=fake_plan or seal_fake_plan([{"kind":"complete","progress_ordinal":1,"terminal_reason":"synthetic_complete","summary":"complete"}])
    return {"fake_scripted_default": FakeScriptedDriver(plan)}

def verify_driver(driver: ImplementationAgentDriver)->dict[str,Any]:
    d=dict(driver.describe_driver())
    if d.get("schema_version")!=DRIVER_SCHEMA or d.get("driver_kind") not in CLOSED_DRIVER_KINDS: raise ValueError("agent_session_driver_invalid")
    if d.get("descriptor_digest")!=_seal(d,"descriptor_digest"): raise ValueError("agent_session_driver_invalid")
    return d

def seal_request(payload: Mapping[str,Any], *, instruction_artifact_root: str|Path|None=None)->dict[str,Any]:
    d=dict(payload); d["schema_version"]=REQUEST_SCHEMA
    if d.get("external_instruction_artifact_reference"):
        if not instruction_artifact_root: raise ValueError("instruction_root_required")
        root=Path(instruction_artifact_root).resolve(strict=True); p=(root/str(d["external_instruction_artifact_reference"])).resolve(strict=True)
        if root not in p.parents or p.is_symlink() or not p.is_file(): raise ValueError("instruction_artifact_invalid")
        data=p.read_bytes()
        if len(data)>MAX_INSTRUCTION_BYTES: raise ValueError("instruction_artifact_too_large")
        d["external_instruction_artifact_digest"]="sha256:"+hashlib.sha256(data).hexdigest()
    d["request_digest"]=_seal({**d,"request_digest":""},"request_digest")
    d.setdefault("request_id", _id("mareq_", {"request_digest":d["request_digest"]}))
    d["request_digest"]=_seal(d,"request_digest")
    return d

def verify_request(req: Mapping[str,Any])->dict[str,Any]:
    allowed={"schema_version","request_id","request_digest","task_id","lease_id","lease_digest","candidate_id","candidate_revision_digest","canonical_candidate_digest","admitted_scope_digest","repository_identity","base_sha","driver_id","driver_kind","attempt_ordinal","corrective_retry_ordinal","implementation_contract_digest","bounded_objective","subject_paths","validation_expectations","requested_authority_classes","implementation_time_ceiling_seconds","wall_clock_deadline","external_instruction_artifact_reference","external_instruction_artifact_digest","explicit_constraints"}
    if set(req)-allowed or req.get("schema_version")!=REQUEST_SCHEMA or req.get("request_digest")!=_seal(req,"request_digest"): raise ValueError("implementation_request_invalid")
    if req.get("driver_kind") not in CLOSED_DRIVER_KINDS: raise ValueError("implementation_request_driver_invalid")
    return dict(req)

def _session_id(task_id:str, lease_id:str, lease_digest:str, attempt_id:str, attempt:int, retry:int, driver_id:str, desc_digest:str, req_digest:str)->str:
    return SESSION_PREFIX+hashlib.sha256(_cj({"task_id":task_id,"lease_id":lease_id,"lease_digest":lease_digest,"attempt_id":attempt_id,"attempt_ordinal":attempt,"corrective_retry_ordinal":retry,"driver_id":driver_id,"descriptor_digest":desc_digest,"request_digest":req_digest})).hexdigest()[:32]
def _event_id(kind:str, task_id:str, payload:Mapping[str,Any])->str: return _id("mevent_", {"kind":kind,"task_id":task_id,"payload":payload})
def _root(root: str|Path, repo_root: str|Path|None)->Path: return journal.resolve_state_root(root, repo_root=repo_root)
def _load_session(root:Path, session_id:str)->dict[str,Any]:
    p=root/"maintenance_agent_sessions"/(session_id+".json")
    if p.is_symlink(): raise ValueError("session_symlink_rejected")
    s=_read(p)
    if s.get("session_id")!=session_id or s.get("session_digest")!=_seal(s,"session_digest"): raise ValueError("session_integrity_failed")
    return s

def _result_path(root:Path, sid:str)->Path: return root/"maintenance_agent_results"/(sid+".json")
def _session_path(root:Path, sid:str)->Path: return root/"maintenance_agent_sessions"/(sid+".json")
def _count_steps(root:Path, task_id:str, sid:str)->int:
    ev=journal.replay_journal(journal.journal_path_for(root, task_id)).events
    return sum(1 for e in ev if e.event_type=="attempt_heartbeat" and e.payload.get("session_id")==sid)
def _terminal_event(root:Path, task_id:str, sid:str) -> Any:
    for e in journal.replay_journal(journal.journal_path_for(root, task_id)).events:
        if e.event_type in journal.TERMINAL_ATTEMPT_EVENTS and e.payload.get("session_id")==sid: return e
    return None

def start_implementation_agent_session(*, state_root:str|Path, lease_id:str, request:Mapping[str,Any], driver:ImplementationAgentDriver, evaluation_time:str, repo_root:str|Path|None=None, interruption_point:str|None=None)->dict[str,Any]:
    root=_root(state_root, repo_root); req=verify_request(request); desc=verify_driver(driver)
    try: lease=lease_mod.load_lease(root, lease_id, repo_root=repo_root)
    except Exception as e: return {"status":"agent_session_lease_invalid","reason_codes":(str(e),)}
    if req["lease_id"]!=lease_id or req["lease_digest"]!=lease["lease_digest"] or req["task_id"]!=lease["task_id"]: return {"status":"agent_session_lease_invalid","reason_codes":("lease_request_mismatch",)}
    lv=lease_mod.verify_lease(root, lease_id, evaluation_time=evaluation_time, repo_root=repo_root)
    if lv["status"]!="lease_active": return {"status":"agent_session_lease_invalid","reason_codes":("lease_not_active",)}
    ar={"schema_version":lease_mod.ACTION_REQUEST_SCHEMA,"task_id":req["task_id"],"lease_id":lease_id,"candidate_revision_digest":req["candidate_revision_digest"],"base_sha":req["base_sha"],"action_kind":"implementation_agent_session","requested_authority_classes":req["requested_authority_classes"],"target_paths":req["subject_paths"],"planned_file_count":len(req["subject_paths"]),"planned_changed_lines":0,"planned_implementation_seconds":req["implementation_time_ceiling_seconds"],"planned_validation_seconds":0,"attempt_ordinal":req["attempt_ordinal"],"corrective_retry_ordinal":req["corrective_retry_ordinal"]}
    dec=lease_mod.verify_action(root, ar, evaluation_time=evaluation_time, repo_root=repo_root)
    if dec["status"]!="action_within_lease" or "implementation_agent_session" not in req["requested_authority_classes"]: return {"status":"agent_session_blocked","reason_codes":(dec["status"],)}
    attempt_id=journal.derive_attempt_id(req["task_id"], int(req["attempt_ordinal"])); sid=_session_id(req["task_id"],lease_id,lease["lease_digest"],attempt_id,int(req["attempt_ordinal"]),int(req["corrective_retry_ordinal"]),desc["driver_id"],desc["descriptor_digest"],req["request_digest"]); ref=journal.derive_agent_session_ref_id(req["task_id"], attempt_id, sid)
    lock=root/ ("agent_start_"+hashlib.sha256(req["task_id"].encode()).hexdigest()[:16]+".lock"); lock.touch(exist_ok=True)
    with lock.open("r+") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        snap=journal.materialize_snapshot(root, req["task_id"], repo_root=repo_root, evaluation_time=evaluation_time)
        active=snap.get("active_attempt")
        if active and active.get("attempt_id")!=attempt_id: return {"status":"agent_session_conflict","reason_codes":("active_attempt_conflict",)}
        if int(req["attempt_ordinal"])>1 and not snap.get("completed_attempts"): return {"status":"agent_session_blocked","reason_codes":("prior_attempt_not_terminal",)}
        plan_digest=getattr(driver,"plan",{}).get("plan_digest") if hasattr(driver,"plan") else None
        session={"schema_version":SESSION_SCHEMA,"session_id":sid,"session_digest":"","task_id":req["task_id"],"lease_id":lease_id,"lease_digest":lease["lease_digest"],"attempt_id":attempt_id,"attempt_ordinal":req["attempt_ordinal"],"corrective_retry_ordinal":req["corrective_retry_ordinal"],"agent_session_ref_id":ref,"driver_descriptor":desc,"request_id":req["request_id"],"request_digest":req["request_digest"],"candidate_revision_digest":req["candidate_revision_digest"],"admitted_scope_digest":req["admitted_scope_digest"],"base_sha":req["base_sha"],"started_at":evaluation_time,"deadline":req["wall_clock_deadline"],"instruction_artifact_reference":req.get("external_instruction_artifact_reference"),"instruction_artifact_digest":req.get("external_instruction_artifact_digest"),"fake_driver_plan_digest":plan_digest,"initial_session_status":"agent_session_ready","effect_class":desc["effect_class"]}
        session["session_digest"]=_seal(session,"session_digest")
        persisted,_=_write_immutable(_session_path(root,sid), session)
        if interruption_point=="after_descriptor_persistence": return {"status":"agent_session_recovered","session_id":sid,"attempt_id":attempt_id,"interrupted_after":"descriptor_persistence"}
        ap={"attempt_id":attempt_id,"lease_id":lease_id,"lease_digest":lease["lease_digest"],"admitted_scope_digest":req["admitted_scope_digest"],"attempt_ordinal":req["attempt_ordinal"],"corrective_retry_ordinal":req["corrective_retry_ordinal"],"request_digest":req["request_digest"],"driver_id":desc["driver_id"]}
        ar2=journal.append_event(root,"attempt_started",task_id=req["task_id"],payload=ap,event_id=_event_id("attempt_started",req["task_id"],ap),recorded_at=evaluation_time,repository_sha=req["base_sha"],repo_root=repo_root,evaluation_time=evaluation_time)
        if ar2.status not in {"event_appended","event_already_recorded"}: return {"status":"agent_session_journal_invalid","reason_codes":(ar2.reason_code,)}
        if interruption_point=="after_attempt_started": return {"status":"agent_session_recovered","session_id":sid,"attempt_id":attempt_id,"interrupted_after":"attempt_started"}
        bp={"session_id":sid,"agent_session_ref_id":ref,"attempt_id":attempt_id,"driver_id":desc["driver_id"],"driver_descriptor_digest":desc["descriptor_digest"],"request_digest":req["request_digest"],"session_descriptor_digest":session["session_digest"],"effect_class":desc["effect_class"]}
        br=journal.append_event(root,"agent_session_bound",task_id=req["task_id"],payload=bp,event_id=_event_id("agent_session_bound",req["task_id"],bp),recorded_at=evaluation_time,repository_sha=req["base_sha"],repo_root=repo_root,evaluation_time=evaluation_time)
        if br.status not in {"event_appended","event_already_recorded"}: return {"status":"agent_session_journal_invalid","reason_codes":(br.reason_code,)}
        if interruption_point=="after_agent_session_bound": return {"status":"agent_session_recovered","session_id":sid,"attempt_id":attempt_id,"interrupted_after":"agent_session_bound"}
        st="agent_session_ready" if persisted=="created" and ar2.status=="event_appended" and br.status=="event_appended" else "agent_session_already_ready"
        return {"status":st,"session_id":sid,"attempt_id":attempt_id,"agent_session_ref_id":ref,"session_descriptor_digest":session["session_digest"],"session_path":str(_session_path(root,sid)),"request_digest":req["request_digest"],"driver_descriptor_digest":desc["descriptor_digest"]}

def _terminal_result(root:Path, session:Mapping[str,Any], req:Mapping[str,Any], desc:Mapping[str,Any], kind:str, status:str, reason:str, summary:str, evaluation_time:str, artifacts:Sequence[str]=(), event_type:str|None=None)->dict[str,Any]:
    et=event_type or ("implementation_completed" if kind=="complete" else "implementation_failed" if kind=="fail" else "implementation_interrupted")
    rid=_id("maresult_", {"session_id":session["session_id"],"kind":kind,"reason":reason})
    placeholder={"session_id":session["session_id"],"result_id":rid,"request_digest":req["request_digest"],"driver_id":desc["driver_id"],"effect_class":desc["effect_class"],"terminal_reason":reason,"repository_mutation_performed":False,"validation_performed":False}
    eid=_event_id(et, str(session["task_id"]), placeholder)
    r={"schema_version":RESULT_SCHEMA,"result_id":rid,"result_digest":"","session_id":session["session_id"],"session_digest":session["session_digest"],"task_id":session["task_id"],"lease_id":session["lease_id"],"lease_digest":session["lease_digest"],"attempt_id":session["attempt_id"],"driver_id":desc["driver_id"],"driver_descriptor_digest":desc["descriptor_digest"],"request_id":req["request_id"],"request_digest":req["request_digest"],"candidate_revision_digest":session["candidate_revision_digest"],"admitted_scope_digest":session["admitted_scope_digest"],"base_sha":session["base_sha"],"terminal_driver_outcome":kind,"terminal_adapter_status":status,"reason_codes":[reason],"bounded_summary":summary[:500],"synthetic_artifact_references":list(artifacts),"completed_at":evaluation_time,"effect_class":desc["effect_class"],**EFFECT_FLAGS,"terminal_event_type":et,"terminal_event_id":eid}
    r["result_digest"]=_seal(r,"result_digest")
    _write_immutable(_result_path(root,str(session["session_id"])), r)
    return r

def poll_implementation_agent_session(*, state_root:str|Path, task_id:str, session_id:str, request:Mapping[str,Any], driver:ImplementationAgentDriver, evaluation_time:str, repo_root:str|Path|None=None, interruption_point:str|None=None)->dict[str,Any]:
    root=_root(state_root, repo_root); req=verify_request(request); desc=verify_driver(driver); session=_load_session(root, session_id)
    if session["task_id"]!=task_id or session["request_digest"]!=req["request_digest"]: return {"status":"agent_session_journal_invalid","reason_codes":("session_request_mismatch",)}
    term=_terminal_event(root, task_id, session_id)
    if term: return {"status":"agent_session_already_terminal","session_id":session_id,"terminal_event_id":term.event_id}
    result_path=_result_path(root,session_id)
    if result_path.exists():
        r=_read(result_path); payload={"session_id":session_id,"result_id":r["result_id"],"result_digest":r["result_digest"],"request_digest":req["request_digest"],"driver_id":desc["driver_id"],"effect_class":desc["effect_class"],"terminal_reason":r["reason_codes"][0],"repository_mutation_performed":False,"validation_performed":False}
        ap=journal.append_event(root,r["terminal_event_type"],task_id=task_id,payload=payload,event_id=_event_id(r["terminal_event_type"],task_id,payload),recorded_at=r["completed_at"],repository_sha=session["base_sha"],repo_root=repo_root,evaluation_time=evaluation_time)
        if ap.status not in {"event_appended","event_already_recorded"}: return {"status":"agent_session_journal_invalid","reason_codes":(ap.reason_code,)}
        return {"status":r["terminal_adapter_status"],"result_digest":r["result_digest"],"terminal_event_id":ap.event.event_id if ap.event else None}
    if evaluation_time>=str(session["deadline"]):
        r=_terminal_result(root,session,req,desc,"interrupt","agent_session_timed_out","agent_session_deadline_exceeded","deadline exceeded",evaluation_time)
        if interruption_point=="after_result_persistence": return {"status":"agent_session_interrupted","interrupted_after":"result_persistence","result_digest":r["result_digest"]}
        return poll_implementation_agent_session(state_root=root,task_id=task_id,session_id=session_id,request=req,driver=driver,evaluation_time=evaluation_time,repo_root=repo_root)
    delivered=_count_steps(root,task_id,session_id); step=driver.observe_session(session, delivered); kind=str(step.get("kind"))
    if kind=="heartbeat":
        payload={"session_id":session_id,"attempt_id":session["attempt_id"],"step_ordinal":delivered+1,"progress_label":step.get("progress_label"),"progress_ordinal":step.get("progress_ordinal",delivered+1),"request_digest":req["request_digest"]}
        ap=journal.append_event(root,"attempt_heartbeat",task_id=task_id,payload=payload,event_id=_event_id("attempt_heartbeat",task_id,payload),recorded_at=evaluation_time,repository_sha=session["base_sha"],repo_root=repo_root,evaluation_time=evaluation_time)
        return {"status":"agent_session_running","session_id":session_id,"heartbeat_event_id":ap.event.event_id if ap.event else None,"step_ordinal":delivered+1}
    if kind in {"complete","fail","interrupt"}:
        status={"complete":"agent_session_completed","fail":"agent_session_failed","interrupt":"agent_session_interrupted"}[kind]
        reason=str(step.get("terminal_reason") or ("synthetic_complete" if kind=="complete" else "synthetic_failure"))
        r=_terminal_result(root,session,req,desc,kind,status,reason,str(step.get("summary") or reason),evaluation_time,tuple(step.get("synthetic_artifact_refs",())))
        if interruption_point=="after_result_persistence": return {"status":"agent_session_interrupted","interrupted_after":"result_persistence","result_digest":r["result_digest"]}
        return poll_implementation_agent_session(state_root=root,task_id=task_id,session_id=session_id,request=req,driver=driver,evaluation_time=evaluation_time,repo_root=repo_root)
    return {"status":"agent_session_running","session_id":session_id}

def cancel_implementation_agent_session(*, state_root:str|Path, task_id:str, session_id:str, request:Mapping[str,Any], driver:ImplementationAgentDriver, evaluation_time:str, cancellation_reference:str, repo_root:str|Path|None=None)->dict[str,Any]:
    if not cancellation_reference: return {"status":"agent_session_blocked","reason_codes":("cancellation_reference_required",)}
    root=_root(state_root, repo_root); session=_load_session(root,session_id); req=verify_request(request); desc=verify_driver(driver)
    term=_terminal_event(root,task_id,session_id)
    if term: return {"status":"agent_session_already_terminal","terminal_event_id":term.event_id}
    r=_terminal_result(root,session,req,desc,"interrupt","agent_session_cancelled","agent_session_cancelled","cancelled",evaluation_time,event_type="implementation_interrupted")
    return poll_implementation_agent_session(state_root=root,task_id=task_id,session_id=session_id,request=req,driver=driver,evaluation_time=evaluation_time,repo_root=repo_root)

def inspect_session(*, state_root:str|Path, session_id:str, repo_root:str|Path|None=None)->dict[str,Any]: return _load_session(_root(state_root,repo_root),session_id)
def inspect_result(*, state_root:str|Path, session_id:str, repo_root:str|Path|None=None)->dict[str,Any]: return _read(_result_path(_root(state_root,repo_root),session_id))
