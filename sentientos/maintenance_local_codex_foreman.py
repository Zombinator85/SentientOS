"""External lease-bound local Codex foreman.

This module is intentionally outside the SentientOS runtime loop.  It invokes only
configured executables with argv/shell=False and records private custody artifacts
under caller supplied external state/workspace roots.
"""
from __future__ import annotations

import argparse, fcntl, hashlib, json, os, shutil, signal, subprocess, sys, time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence, Callable, cast

from sentientos import maintenance_task_journal as journal
from sentientos import maintenance_implementation_agent as mia
from sentientos import maintenance_task_authority_lease as leases

CONFIG_SCHEMA="sentientos.maintenance_local_codex_foreman_config:v1"
PROBE_SCHEMA="sentientos.maintenance_local_codex_cli_probe:v1"
WORKTREE_SCHEMA="sentientos.maintenance_implementation_worktree:v1"
ENVELOPE_SCHEMA="sentientos.maintenance_local_codex_instruction_envelope:v1"
INVOCATION_SCHEMA="sentientos.maintenance_local_codex_invocation:v1"
OBS_SCHEMA="sentientos.maintenance_local_codex_jsonl_observations:v1"
CHANGE_SCHEMA="sentientos.maintenance_implementation_change_manifest:v1"
RESULT_SCHEMA="sentientos.maintenance_local_codex_foreman_result:v1"
FINAL_SCHEMA="sentientos.maintenance_local_codex_final_message_schema:v1"
EFFECT_AUTHORITIES=frozenset({"implementation_process_execute","implementation_instruction_disclosure","remote_model_invocation","repository_state_read","repository_workspace_provision","repository_workspace_modify"})
DANGEROUS_FLAGS=("--full-auto","--dangerously-bypass-approvals-and-sandbox","--yolo","danger-full-access","--skip-git-repo-check","--ignore-rules","--image","--mcp-config")
REQUIRED_CAPABILITIES=("exec","jsonl","cwd","sandbox","final_message","final_schema","stdin","session","resume")
TERMINAL_STATUSES={"implementation_ready_for_validation","implementation_blocked","implementation_failed","implementation_timed_out","implementation_cancelled","implementation_interrupted","implementation_scope_violated","implementation_budget_exceeded","implementation_no_change","foreman_authentication_unavailable","foreman_cli_incompatible","foreman_output_invalid","foreman_workspace_invalid","foreman_process_conflict","foreman_recovery_unavailable"}

def cj(v:Any)->bytes: return journal.canonical_json_bytes(v)
def dig(v:Any)->str: return journal.sha256_digest(v)
def seal(d:Mapping[str,Any], field:str)->str: return dig({k:v for k,v in d.items() if k!=field})
def sha_bytes(b:bytes)->str: return "sha256:"+hashlib.sha256(b).hexdigest()
def read_json(p:Path)->dict[str,Any]: return cast(dict[str,Any], json.loads(p.read_text()))
def write_json(p:Path, v:Mapping[str,Any], immutable:bool=True)->str:
    p.parent.mkdir(parents=True, exist_ok=True); data=cj(v)+b"\n"
    if immutable and p.exists():
        if p.read_bytes()==data: return dig(v)
        raise ValueError("immutable_artifact_conflict")
    if immutable:
        fd=os.open(p, os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0), 0o600)
        with os.fdopen(fd,"wb") as f: f.write(data)
    else:
        tmp=p.with_suffix(p.suffix+".tmp"); tmp.write_bytes(data); os.replace(tmp,p)
    return dig(v)
def run(argv:Sequence[str], cwd:Path|None=None, timeout:float=10, env:Mapping[str,str]|None=None)->subprocess.CompletedProcess[str]:
    return subprocess.run(list(argv), cwd=cwd, timeout=timeout, text=True, input="", capture_output=True, shell=False, env=dict(env) if env else None, check=False)
def resolve(p:str|Path)->Path: return Path(p).expanduser().resolve()
def path_digest(p:Path|None)->str|None:
    if not p: return None
    try:
        if p.is_file() and not p.is_symlink(): return sha_bytes(p.read_bytes())
    except OSError: return None
    return None

@dataclass(frozen=True)
class LocalCodexForemanConfig:
    configuration_id:str; repository_identity:str; repository_root:Path; external_workspace_root:Path; external_state_root:Path; codex_executable:Path; git_executable:Path; codex_home:Path
    codex_executable_digest:str|None=None; git_executable_digest:str|None=None; allowed_codex_version_constraints:tuple[str,...]=(); required_codex_capabilities:tuple[str,...]=REQUIRED_CAPABILITIES
    codex_profile_name:str|None=None; requested_model:str|None=None; requested_reasoning_effort:str|None=None; required_sandbox_mode:str="workspace-write"; environment_name_allowlist:tuple[str,...]=()
    maximum_instruction_bytes:int=65536; maximum_jsonl_line_bytes:int=65536; maximum_jsonl_transcript_bytes:int=2_000_000; maximum_stderr_bytes:int=200_000; process_timeout_seconds:float=30.0
    quiet_heartbeat_interval_seconds:float=0.2; termination_grace_seconds:float=1.0; maximum_same_session_recovery_count:int=1; output_schema_digest:str=""; configuration_constraints:tuple[str,...]=()
    @classmethod
    def from_mapping(cls, m:Mapping[str,Any])->"LocalCodexForemanConfig":
        allowed=set(cls.__dataclass_fields__)|{"schema_version","configuration_digest"}
        if set(m)-allowed or m.get("schema_version")!=CONFIG_SCHEMA: raise ValueError("foreman_configuration_invalid")
        kw={k:v for k,v in m.items() if k in cls.__dataclass_fields__}
        for k in ("repository_root","external_workspace_root","external_state_root","codex_executable","git_executable","codex_home"): kw[k]=resolve(kw[k])
        for k in ("allowed_codex_version_constraints","required_codex_capabilities","environment_name_allowlist","configuration_constraints"): kw[k]=tuple(kw.get(k,()))
        c=cls(**kw); d=c.to_dict()
        if m.get("configuration_digest") and m["configuration_digest"]!=d["configuration_digest"]: raise ValueError("foreman_configuration_digest_invalid")
        return c
    def to_dict(self)->dict[str,Any]:
        d={"schema_version":CONFIG_SCHEMA, **{k:(str(v) if isinstance(v,Path) else list(v) if isinstance(v,tuple) else v) for k,v in self.__dict__.items()}, "configuration_digest":""}
        d["output_schema_digest"]=self.output_schema_digest or dig(final_message_schema())
        d["configuration_digest"]=seal(d,"configuration_digest"); return d

def final_message_schema()->dict[str,Any]:
    return {"schema_version":FINAL_SCHEMA,"type":"object","required":["status","summary","reported_changed_paths","reported_commands","reported_tests","blocker_codes","recommended_validation","continuation_note"],"properties":{"status":{"enum":["implemented","blocked","failed"]},"summary":{"type":"string"},"reported_changed_paths":{"type":"array","items":{"type":"string"}},"reported_commands":{"type":"array","items":{"type":"string"}},"reported_tests":{"type":"array","items":{"type":"string"}},"blocker_codes":{"type":"array","items":{"type":"string"}},"recommended_validation":{"type":"array","items":{"type":"string"}},"continuation_note":{"type":"string"}}}

def probe_local_codex_cli(config:LocalCodexForemanConfig, configured_argv:Sequence[str]=())->dict[str,Any]:
    unsafe=[x for x in configured_argv if any(f in x for f in DANGEROUS_FLAGS)]
    exe=resolve(config.codex_executable)
    try:
        ver=run([str(exe),"--version"], timeout=5); help1=run([str(exe),"exec","--help"], timeout=5); help2=run([str(exe),"exec","resume","--help"], timeout=5)
    except Exception as e:
        ver=help1=help2=subprocess.CompletedProcess([],1,"",str(e))
    text=(help1.stdout+help1.stderr).lower(); rtext=(help2.stdout+help2.stderr).lower()
    supported=[]
    checks={"exec":"usage" in text or "exec" in text,"jsonl":"jsonl" in text or "json" in text,"cwd":"--cwd" in text or "working" in text,"sandbox":"sandbox" in text,"final_message":"final" in text and ("message" in text or "output" in text),"final_schema":"schema" in text,"stdin":"stdin" in text or "prompt" in text,"session":"session" in text or "thread" in text,"resume":"resume" in rtext}
    supported=[k for k,v in checks.items() if v]; missing=[k for k in config.required_codex_capabilities if k not in supported]
    status="capability_probe_ready" if ver.returncode==0 and help1.returncode==0 and not missing and not unsafe else "foreman_cli_incompatible"
    d={"schema_version":PROBE_SCHEMA,"resolved_executable_path":str(exe),"executable_digest":path_digest(exe),"version_output":(ver.stdout+ver.stderr).strip(),"version_digest":sha_bytes((ver.stdout+ver.stderr).encode()),"exec_help_digest":sha_bytes((help1.stdout+help1.stderr).encode()),"exec_resume_help_digest":sha_bytes((help2.stdout+help2.stderr).encode()),"supported_required_options":supported,"missing_required_options":missing,"unsafe_or_obsolete_options":unsafe,"status":status,"probe_digest":""}
    d["probe_digest"]=seal(d,"probe_digest"); return d

def sanitize_environment(config:LocalCodexForemanConfig)->tuple[dict[str,str],dict[str,Any]]:
    names={"PATH","HOME","CODEX_HOME","TMPDIR","SSL_CERT_FILE","SSL_CERT_DIR","LANG","LC_ALL",*config.environment_name_allowlist}
    env={k:os.environ[k] for k in names if k in os.environ}; env["CODEX_HOME"]=str(config.codex_home); env.setdefault("HOME",str(config.codex_home)); env.setdefault("PATH",os.environ.get("PATH",""))
    meta={"allowed_environment_names":sorted(env),"required_present":{"PATH":"PATH" in env,"HOME":"HOME" in env,"CODEX_HOME":True},"environment_name_set_digest":dig(sorted(env))}
    return env,meta

def prepare_worktree(config:LocalCodexForemanConfig, lease:Mapping[str,Any], session_id:str, *, recovery:bool=False)->dict[str,Any]:
    root=resolve(config.external_workspace_root)/str(lease["task_id"])/session_id
    if config.repository_root in root.parents or config.external_state_root in root.parents or root.is_symlink(): raise ValueError("foreman_workspace_invalid")
    descriptor=config.external_state_root/"maintenance_worktrees"/(session_id+".json")
    if recovery and root.exists() and descriptor.exists():
        prior=read_json(descriptor); head=run([str(config.git_executable),"rev-parse","HEAD"],cwd=root).stdout.strip()
        if prior.get("worktree_root")!=str(root) or prior.get("base_sha")!=lease["base_sha"] or head!=lease["base_sha"]: raise ValueError("foreman_workspace_invalid")
        return prior
    argv=[str(config.git_executable),"worktree","add","--detach",str(root),str(lease["base_sha"])]
    if root.exists():
        if root.is_symlink(): raise ValueError("foreman_workspace_invalid")
        head=run([str(config.git_executable),"rev-parse","HEAD"], cwd=root).stdout.strip(); clean=run([str(config.git_executable),"status","--porcelain=v1","--untracked-files=all"], cwd=root).stdout
        if head!=lease["base_sha"] or clean: raise ValueError("foreman_workspace_invalid")
        status="reused"
    else:
        root.parent.mkdir(parents=True, exist_ok=True); cp=run(argv, cwd=config.repository_root, timeout=30)
        if cp.returncode: raise ValueError("foreman_workspace_invalid:"+cp.stderr[:200])
        status="created"
    head=run([str(config.git_executable),"rev-parse","HEAD"], cwd=root).stdout.strip(); clean=run([str(config.git_executable),"status","--porcelain=v1","--untracked-files=all"], cwd=root).stdout
    files=run([str(config.git_executable),"ls-files"], cwd=root).stdout.splitlines()
    d={"schema_version":WORKTREE_SCHEMA,"worktree_id":"mwt_"+hashlib.sha256(cj({"t":lease["task_id"],"s":session_id})).hexdigest()[:32],"worktree_digest":"","task_id":lease["task_id"],"lease_id":lease["lease_id"],"lease_digest":lease["lease_digest"],"session_id":session_id,"repository_identity":config.repository_identity,"source_repository_root":str(config.repository_root),"worktree_root":str(root),"workspace_root_identity":dig(str(config.external_workspace_root)),"base_sha":lease["base_sha"],"git_executable_identity":{"path":str(config.git_executable),"digest":path_digest(config.git_executable)},"creation_argv_digest":dig(argv),"initial_head":head,"initial_cleanliness_proof":{"porcelain":clean},"initial_tracked_file_manifest_digest":dig(files),"creation_status":status,"retained_for_validation":True}
    d["worktree_digest"]=seal(d,"worktree_digest"); write_json(config.external_state_root/"maintenance_worktrees"/(session_id+".json"), d, immutable=False); return d

def build_instruction_envelope(config:LocalCodexForemanConfig, lease:Mapping[str,Any], request:Mapping[str,Any], session:Mapping[str,Any], artifact_root:Path, recovery_ordinal:int=0)->tuple[dict[str,Any],bytes]:
    ref=str(request.get("external_instruction_artifact_reference") or "instruction.txt"); p=(artifact_root/ref).resolve(); root=artifact_root.resolve()
    if root not in p.parents or p.is_symlink() or not p.is_file(): raise ValueError("instruction_artifact_invalid")
    raw=p.read_bytes(); want=request.get("external_instruction_artifact_digest")
    if len(raw)>config.maximum_instruction_bytes or (want and sha_bytes(raw)!=want): raise ValueError("instruction_artifact_invalid")
    raw.decode("utf-8")
    header=("SentientOS bounded local-Codex foreman guard:\n- Work only inside the supplied worktree.\n- Modify only admitted paths.\n- Do not commit, push, create branches, or mutate pull requests.\n- Do not alter task authority or access credentials.\n- Do not wait for hosted checks.\n- Stop when implementation is complete or genuinely blocked.\n- Provide the required structured final JSON response.\n\nOpaque instruction follows.\n")
    if recovery_ordinal: header="Continue the same bounded implementation from the existing worktree. Preserve the original task scope and finish or report the exact blocker.\n\n"
    d={"schema_version":ENVELOPE_SCHEMA,"task_id":lease["task_id"],"lease_id":lease["lease_id"],"lease_digest":lease["lease_digest"],"candidate_id":lease.get("candidate_id"),"candidate_revision":lease["candidate_revision_digest"],"admitted_scope_digest":lease["admitted_scope_digest"],"session_id":session["session_id"],"attempt_id":session["attempt_id"],"attempt_ordinal":session["attempt_ordinal"],"corrective_retry_ordinal":session["corrective_retry_ordinal"],"recovery_ordinal":recovery_ordinal,"base_sha":lease["base_sha"],"admitted_paths":list(lease["admitted_subject_paths"]),"validation_expectations":list(lease["validation_expectations"]),"budgets":{"files":lease["maximum_file_count"],"changed_lines":lease["maximum_changed_line_count"],"implementation_seconds":lease["maximum_implementation_seconds"]},"immutable_constraints":list(request.get("explicit_constraints",())),"instruction_artifact_reference":ref,"instruction_artifact_digest":sha_bytes(raw),"envelope_digest":""}
    d["envelope_digest"]=seal(d,"envelope_digest"); return d, header.encode()+raw

class JsonlObservationParser:
    def __init__(self, max_line:int=65536, max_total:int=2_000_000): self.max_line=max_line; self.max_total=max_total; self.total=0; self.thread_id: str | None=None; self.completed=0; self.failed=0; self.fatal=0; self.unknown: list[Any]=[]; self.events: list[dict[str, Any]]=[]; self.commands: list[str]=[]; self.messages: list[str]=[]; self.usage: list[Any]=[]
    def feed(self, line:bytes|str)->None:
        b=line.encode() if isinstance(line,str) else line
        if len(b)>self.max_line: raise ValueError("jsonl_line_too_large")
        self.total+=len(b)
        if self.total>self.max_total: raise ValueError("jsonl_transcript_too_large")
        try: obj=json.loads(b.decode("utf-8"))
        except UnicodeDecodeError as e: raise ValueError("jsonl_invalid_utf8") from e
        except json.JSONDecodeError as e: raise ValueError("jsonl_malformed") from e
        typ=str(obj.get("type") or obj.get("event") or obj.get("msg",{}).get("type") or "unknown")
        tid: Any = obj.get("thread_id") or obj.get("session_id") or obj.get("conversation_id") or obj.get("msg",{}).get("thread_id")
        if tid:
            if self.thread_id and self.thread_id!=tid: raise ValueError("jsonl_conflicting_thread_id")
            self.thread_id=str(tid)
        if typ in {"thread.started","session.started","conversation.created"} and not self.thread_id: self.thread_id=str(obj.get("id") or obj.get("session") or "") or self.thread_id
        if typ in {"turn.completed","turn_complete","agent_turn_completed"}: self.completed+=1
        elif typ in {"turn.failed","turn_error","agent_turn_failed"}: self.failed+=1
        elif typ in {"error","fatal_error"}: self.fatal+=1
        elif typ not in {"thread.started","session.started","conversation.created","turn.started","item.started","item.completed","turn.completed","turn.failed","agent_message","command"}: self.unknown.append(obj)
        if "usage" in obj: self.usage.append(obj["usage"])
        if "command" in obj: self.commands.append(str(obj["command"])[:200])
        if "message" in obj: self.messages.append(str(obj["message"])[:500])
        self.events.append({"type":typ,"thread_id":tid})
    def summary(self)->dict[str,Any]:
        d={"schema_version":OBS_SCHEMA,"thread_id":self.thread_id,"completed_turn_count":self.completed,"failed_turn_count":self.failed,"fatal_error_count":self.fatal,"unknown_events":self.unknown,"event_count":len(self.events),"command_summaries":self.commands,"agent_message_summaries":self.messages,"usage_metadata":self.usage,"observation_digest":""}; d["observation_digest"]=seal(d,"observation_digest"); return d

def changed_manifest(config:LocalCodexForemanConfig, lease:Mapping[str,Any], worktree:Mapping[str,Any])->dict[str,Any]:
    wt=Path(str(worktree["worktree_root"])); base=str(lease["base_sha"]); head=run([str(config.git_executable),"rev-parse","HEAD"],cwd=wt).stdout.strip()
    status=run([str(config.git_executable),"status","--porcelain=v1","--untracked-files=all"],cwd=wt).stdout.splitlines(); paths=[]
    for line in status:
        if not line: continue
        p=line[3:] if line.startswith("?? ") else line[3:]
        paths.append(p)
    stats=run([str(config.git_executable),"diff","--numstat","HEAD","--",*paths],cwd=wt).stdout.splitlines() if paths else []
    add=dele=0
    for line_stat in stats:
        a_s,d_s,*_=line_stat.split("\t"); add+=int(a_s) if a_s.isdigit() else 0; dele+=int(d_s) if d_s.isdigit() else 0
    entries=[]
    for p in paths:
        fp=(wt/p).resolve(); typ="missing" if not fp.exists() else "symlink" if fp.is_symlink() else "file" if fp.is_file() else "directory"
        entries.append({"path":p,"status":"changed","tracked":not any(x.startswith("?? "+p) for x in status),"file_type":typ,"byte_size":fp.stat().st_size if fp.exists() and not fp.is_dir() else 0,"content_digest":path_digest(fp) if fp.exists() and fp.is_file() and not fp.is_symlink() and fp.stat().st_size<1_000_000 else None,"symlink_escapes_worktree": fp.is_symlink() and wt not in fp.resolve().parents})
    admitted=list(lease["admitted_subject_paths"]); forb=list(lease.get("forbidden_path_patterns",()))
    out=[p for p in paths if not any(p==a.rstrip('/') or p.startswith(a.rstrip('/')+'/') for a in admitted)]
    budget=[]
    if len(paths)>int(lease["maximum_file_count"]): budget.append("file_count_exceeded")
    if add+dele>int(lease["maximum_changed_line_count"]): budget.append("changed_line_count_exceeded")
    d={"schema_version":CHANGE_SCHEMA,"task_id":lease["task_id"],"session_id":worktree["session_id"],"worktree_id":worktree["worktree_id"],"initial_head":base,"terminal_head":head,"changed_paths":paths,"entries":entries,"aggregate_file_count":len(paths),"aggregate_changed_line_count":add+dele,"additions":add,"deletions":dele,"out_of_scope_paths":out,"forbidden_paths":[p for p in paths if any(__import__('fnmatch').fnmatch(p,pat) for pat in forb)],"budget_findings":budget,"manifest_digest":""}
    d["manifest_digest"]=seal(d,"manifest_digest"); write_json(config.external_state_root/"maintenance_change_manifests"/(worktree["session_id"]+".json"),d, immutable=False); patch=run([str(config.git_executable),"diff","--binary","HEAD"],cwd=wt).stdout
    pp=config.external_state_root/"maintenance_patches"/(worktree["session_id"]+".patch"); pp.parent.mkdir(parents=True,exist_ok=True); pp.write_text(patch); return d

class LocalCodexDriver:
    driver_id="local_codex_foreman"; driver_version="1"
    def describe_driver(self)->Mapping[str,Any]:
        d={"schema_version":mia.DRIVER_SCHEMA,"driver_id":self.driver_id,"driver_kind":"local_codex","driver_version":self.driver_version,"supported_session_modes":["external_foreman"],"effect_class":"bounded_repository_workspace_effect","supports_external_session":True,"supports_polling":False,"supports_cancellation":True,"supports_recovery":True,"supports_jsonl_observations":True,"supports_repository_workspace_effects":True,"supports_process_execution":True,"supports_bounded_instruction_disclosure":True,"supports_remote_model_invocation":True,"performs_validation":False,"performs_commit":False,"performs_publication":False,"descriptor_digest":""}
        d["descriptor_digest"]=seal(d,"descriptor_digest"); return d
    def prepare_session(self, request:Mapping[str,Any], session:Mapping[str,Any])->Mapping[str,Any]: return {"prepared":True}
    def observe_session(self, session:Mapping[str,Any], delivered_steps:int)->Mapping[str,Any]: return {"kind":"interrupt","terminal_reason":"external_foreman_required"}
    def request_cancellation(self, session:Mapping[str,Any], cancellation_reference:str)->Mapping[str,Any]: return {"kind":"interrupt","terminal_reason":"agent_session_cancelled"}

def require_effect_authority(req:Mapping[str,Any])->None:
    missing=EFFECT_AUTHORITIES-set(req.get("requested_authority_classes",()))
    if missing: raise ValueError("missing_effect_authority:"+','.join(sorted(missing)))

def codex_argv(config:LocalCodexForemanConfig, final:Path, schema:Path, resume_thread:str|None=None)->list[str]:
    base=[str(config.codex_executable),"exec"]
    if resume_thread: base += ["resume", resume_thread]
    base += ["--jsonl","--cwd",".","--sandbox",config.required_sandbox_mode,"--final-message-file",str(final),"--final-output-schema",str(schema),"--color","never","-"]
    if config.codex_profile_name: base += ["--profile",config.codex_profile_name]
    if config.requested_model: base += ["--model",config.requested_model]
    if config.requested_reasoning_effort: base += ["--reasoning-effort",config.requested_reasoning_effort]
    return base

def run_local_codex_session(config:LocalCodexForemanConfig, lease:Mapping[str,Any], request:Mapping[str,Any], session:Mapping[str,Any], artifact_root:Path, recovery_ordinal:int=0, resume_thread_id:str|None=None)->dict[str,Any]:
    require_effect_authority(request)
    lock=config.external_state_root/"maintenance_locks"/(session["session_id"]+".lock"); lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open("w") as lf:
        try: fcntl.flock(lf, fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return {"schema_version":RESULT_SCHEMA,"status":"foreman_process_conflict","session_id":session["session_id"]}
        probe=probe_local_codex_cli(config)
        if probe["status"]!="capability_probe_ready": return {"schema_version":RESULT_SCHEMA,"status":"foreman_cli_incompatible","probe_digest":probe["probe_digest"]}
        if not config.codex_home.exists(): return {"schema_version":RESULT_SCHEMA,"status":"foreman_authentication_unavailable"}
        wt=prepare_worktree(config, lease, str(session["session_id"]), recovery=bool(recovery_ordinal)); env,envm=sanitize_environment(config); env["SENTIENTOS_FOREMAN_STATE_ROOT"]=str(config.external_state_root)
        env["SENTIENTOS_FOREMAN_ALLOWED_PATHS"]="\n".join(lease["admitted_subject_paths"])
        envelope, stdin=build_instruction_envelope(config, lease, request, session, artifact_root, recovery_ordinal)
        sid=str(session["session_id"]); base=config.external_state_root; trans=base/"maintenance_codex_transcripts"/(sid+f".{recovery_ordinal}.jsonl"); stderrp=base/"maintenance_codex_stderr"/(sid+f".{recovery_ordinal}.stderr"); final=base/"maintenance_codex_final_messages"/(sid+f".{recovery_ordinal}.json"); schema=base/"maintenance_codex_final_schemas"/(sid+".schema.json")
        for p in (trans,stderrp,final,schema): p.parent.mkdir(parents=True,exist_ok=True)
        schema.write_text(json.dumps(final_message_schema(),sort_keys=True))
        argv=codex_argv(config, final, schema, resume_thread_id)
        inv={"schema_version":INVOCATION_SCHEMA,"invocation_id":"mcodexinv_"+hashlib.sha256(sid.encode()).hexdigest()[:32],"invocation_digest":"","task_id":lease["task_id"],"lease_id":lease["lease_id"],"lease_digest":lease["lease_digest"],"attempt_id":session["attempt_id"],"session_id":sid,"configuration_digest":config.to_dict()["configuration_digest"],"capability_probe_digest":probe["probe_digest"],"executable_version_digest":probe["version_digest"],"help_contract_digests":{"exec":probe["exec_help_digest"],"resume":probe["exec_resume_help_digest"]},"worktree_descriptor_digest":wt["worktree_digest"],"instruction_envelope_digest":envelope["envelope_digest"],"output_schema_digest":dig(final_message_schema()),"sanitized_argv":argv,"environment_name_set_digest":envm["environment_name_set_digest"],"jsonl_path":str(trans),"stderr_path":str(stderrp),"final_message_path":str(final),"process_timeout_seconds":config.process_timeout_seconds,"heartbeat_interval_seconds":config.quiet_heartbeat_interval_seconds,"recovery_ordinal":recovery_ordinal,"initial_status":"invocation_ready"}
        inv["invocation_digest"]=seal(inv,"invocation_digest"); write_json(base/"maintenance_codex_invocations"/(sid+f".{recovery_ordinal}.json"),inv)
        parser=JsonlObservationParser(config.maximum_jsonl_line_bytes, config.maximum_jsonl_transcript_bytes); heartbeats=0; pidinfo={}; started=time.time()
        proc=subprocess.Popen(argv,cwd=wt["worktree_root"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=False,shell=False,env=env,start_new_session=True)
        pidinfo={"foreman_pid":os.getpid(),"child_pid":proc.pid,"process_group_id":os.getpgid(proc.pid),"process_start_time":started,"executable_identity":{"path":str(config.codex_executable),"digest":path_digest(config.codex_executable)},"current_recovery_ordinal":recovery_ordinal,"latest_observation_timestamp":started,"current_status":"running"}
        write_json(base/"maintenance_runtime_state"/(sid+".json"),pidinfo,immutable=False)
        proc.stdin.write(stdin); proc.stdin.close()  # type: ignore[union-attr]
        deadline=time.time()+config.process_timeout_seconds; err=b""; timed=False
        with trans.open("ab") as tf:
            while True:
                if proc.stdout:
                    line=proc.stdout.readline()
                    if line:
                        tf.write(line); tf.flush(); parser.feed(line); heartbeats+=1; pidinfo["latest_observation_timestamp"]=time.time(); write_json(base/"maintenance_runtime_state"/(sid+".json"),pidinfo,immutable=False)
                if proc.poll() is not None: break
                if time.time()>deadline:
                    timed=True; os.killpg(os.getpgid(proc.pid), signal.SIGTERM); time.sleep(config.termination_grace_seconds)
                    if proc.poll() is None: os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    break
                time.sleep(0.01)
        if proc.stdout:
            for line in proc.stdout.readlines():
                if line:
                    with trans.open("ab") as tf: tf.write(line)
                    parser.feed(line); heartbeats += 1
        if proc.stderr: err=proc.stderr.read(config.maximum_stderr_bytes+1)
        stderrp.write_bytes(err[:config.maximum_stderr_bytes])
        rc=proc.wait(timeout=2) if proc.poll() is None else proc.returncode
        obs=parser.summary(); write_json(base/"maintenance_codex_event_summaries"/(sid+f".{recovery_ordinal}.json"),obs, immutable=False)
        transcript_digest=sha_bytes(trans.read_bytes()); final_digest=sha_bytes(final.read_bytes()) if final.exists() else None
        try: fm=read_json(final)
        except Exception: fm={}
        manifest=changed_manifest(config, lease, wt); patchp=base/"maintenance_patches"/(sid+".patch"); patch_digest=sha_bytes(patchp.read_bytes()) if patchp.exists() else None
        if timed: status="implementation_timed_out"
        elif b"auth" in err.lower() or rc==42: status="foreman_authentication_unavailable"
        elif rc not in (0,None): status="implementation_interrupted" if obs["thread_id"] else "implementation_failed"
        elif obs["completed_turn_count"]!=1 or obs["failed_turn_count"] or obs["fatal_error_count"] or not fm: status="foreman_output_invalid"
        elif not manifest["changed_paths"]: status="implementation_no_change"
        elif manifest["terminal_head"]!=lease["base_sha"] or manifest["out_of_scope_paths"] or manifest["forbidden_paths"]: status="implementation_scope_violated"
        elif manifest["budget_findings"]: status="implementation_budget_exceeded"
        elif fm.get("status")=="blocked": status="implementation_blocked"
        elif fm.get("status")=="failed": status="implementation_failed"
        else: status="implementation_ready_for_validation"
        effects={"repository_mutation_performed":status=="implementation_ready_for_validation","process_execution_performed":True,"bounded_instruction_disclosure_performed":True,"remote_model_invocation_performed":True,"validation_performed":False,"git_commit_performed":False,"publication_performed":False,"host_effect_beyond_bounded_process_worktree_custody":False,"runtime_adoption_performed":False}
        result={"schema_version":RESULT_SCHEMA,"status":status,"session_id":sid,"task_id":lease["task_id"],"worktree_descriptor_digest":wt["worktree_digest"],"invocation_digest":inv["invocation_digest"],"transcript_digest":transcript_digest,"final_message_digest":final_digest,"change_manifest_digest":manifest["manifest_digest"],"patch_digest":patch_digest,"codex_thread_id":obs["thread_id"],"heartbeat_count":heartbeats,"process_identity":pidinfo,"changed_paths":manifest["changed_paths"],"aggregate_file_count":manifest["aggregate_file_count"],"aggregate_changed_line_count":manifest["aggregate_changed_line_count"],"measured_effect_flags":effects,"validation_pending":status=="implementation_ready_for_validation","result_digest":""}
        result["result_digest"]=seal(result,"result_digest"); write_json(base/"maintenance_codex_results"/(sid+".json"), result, immutable=False)
        if status=="implementation_ready_for_validation":
            payload={"session_id":sid,"result_digest":result["result_digest"],"worktree_descriptor_digest":wt["worktree_digest"],"invocation_digest":inv["invocation_digest"],"transcript_digest":transcript_digest,"final_message_digest":final_digest,"change_manifest_digest":manifest["manifest_digest"],"patch_digest":patch_digest,"codex_thread_id":obs["thread_id"],"measured_effect_flags":effects,"validation_pending":True,"repository_mutation_performed":True,"validation_performed":False}
            journal.append_event(config.external_state_root,"implementation_completed",task_id=lease["task_id"],payload=payload,event_id="mevent_"+hashlib.sha256(cj(payload)).hexdigest()[:32],recorded_at=str(time.time()),repository_sha=lease["base_sha"],repo_root=config.repository_root)
        return result

def resume_local_codex_session(config:LocalCodexForemanConfig, lease:Mapping[str,Any], request:Mapping[str,Any], session:Mapping[str,Any], artifact_root:Path, evaluation_time:str)->dict[str,Any]:
    if evaluation_time>=str(lease["expires_at"]): return {"schema_version":RESULT_SCHEMA,"status":"foreman_recovery_unavailable","reason_codes":["lease_expired"]}
    old=config.external_state_root/"maintenance_codex_results"/(str(session["session_id"])+".json")
    if old.exists():
        r=read_json(old)
        if r.get("status")=="implementation_ready_for_validation": return r
        tid=r.get("codex_thread_id")
    else: tid=None
    if not tid: return {"schema_version":RESULT_SCHEMA,"status":"foreman_recovery_unavailable"}
    wt=read_json(config.external_state_root/"maintenance_worktrees"/(str(session["session_id"])+".json"))
    if run([str(config.git_executable),"rev-parse","HEAD"],cwd=Path(wt["worktree_root"])).stdout.strip()!=lease["base_sha"]: return {"schema_version":RESULT_SCHEMA,"status":"foreman_recovery_unavailable","reason_codes":["worktree_head_changed"]}
    return run_local_codex_session(config, lease, request, session, artifact_root, recovery_ordinal=1, resume_thread_id=str(tid))

def cancel_local_codex_session(config:LocalCodexForemanConfig, task_id:str, session_id:str)->dict[str,Any]:
    p=config.external_state_root/"maintenance_runtime_state"/(session_id+".json")
    if not p.exists(): return {"schema_version":RESULT_SCHEMA,"status":"implementation_cancelled","idempotent":True}
    st=read_json(p)
    if st.get("current_status")!="running": return {"schema_version":RESULT_SCHEMA,"status":"implementation_cancelled","idempotent":True}
    try: os.killpg(int(st["process_group_id"]), signal.SIGTERM); time.sleep(config.termination_grace_seconds)
    except ProcessLookupError: pass
    res={"schema_version":RESULT_SCHEMA,"status":"implementation_cancelled","task_id":task_id,"session_id":session_id,"process_identity":st,"result_digest":""}; res["result_digest"]=seal(res,"result_digest"); write_json(config.external_state_root/"maintenance_codex_results"/(session_id+".cancelled.json"),res); return res

def inspect_local_codex_session(config:LocalCodexForemanConfig, session_id:str)->dict[str,Any]:
    p=config.external_state_root/"maintenance_codex_results"/(session_id+".json")
    return read_json(p) if p.exists() else {"schema_version":RESULT_SCHEMA,"status":"foreman_recovery_unavailable","session_id":session_id}
