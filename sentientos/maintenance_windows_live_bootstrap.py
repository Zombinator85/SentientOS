"""Inert composition of the existing Windows live-maintenance configuration stack."""
from __future__ import annotations
import hashlib, json, os, re
from pathlib import Path, PureWindowsPath
from typing import Any, Mapping

from sentientos import maintenance_activation_profiles as profiles
from sentientos import maintenance_loop_activation as activation
from sentientos import maintenance_health_probe as health
from sentientos import maintenance_candidate_collector as collector
from sentientos import maintenance_autonomy_cycle as autonomy
from sentientos import maintenance_wake_cycle as wake
from sentientos import maintenance_windows_host_readiness as readiness
from sentientos import maintenance_windows_deployment as deployment

SCHEMA="sentientos.maintenance_windows_live_bootstrap_manifest:v1"
INDEX_SCHEMA="sentientos.maintenance_windows_live_bootstrap_index:v1"
STATUS_READY="windows_live_bootstrap_ready"; STATUS_BLOCKED="windows_live_bootstrap_blocked"
SECRET=re.compile(r"(?i)(password|passwd|credential|secret|token|api[_-]?key)")
DIRS=("activation","state","workspace","scratch","inbox","signals","collector","cycle","wake","logs","deployment","configuration")
REQUIRED={"schema_version","repository_root","expected_repository_sha","repository_identity","external_custody_root","tracked_remote","tracked_base_ref","activation_not_before","activation_expires_at","allowed_candidate_kinds","allowed_path_prefixes","forbidden_paths","authority_classes","budgets","validation_expectations","publication_mode","scheduler_task_name","scheduler_policy","canary_source_path","canary_validation_node","canary_allowed_path_boundary","operator_reference","approval_reference","commit_identity","commit_title_prefix","evaluation_time","allowed_source_kinds","allowed_source_schemas","health_probe_policy","remote_readiness_probe_required"}
FILES={"activation_manifest":"activation-profile-manifest.json","watchdog_config":"maintenance-loop.json","health_config":"health-probe.json","collector_config":"collector.json","autonomy_config":"autonomy-cycle.json","wake_config":"wake-cycle.json","host_manifest":"windows-host-readiness.json","deployment_manifest":"windows-deployment.json"}

def canonical_bytes(value:Any)->bytes:return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()+b"\n"
def digest_bytes(value:bytes)->str:return "sha256:"+hashlib.sha256(value).hexdigest()
def digest(value:Any,omit:str|None=None)->str:return digest_bytes(canonical_bytes({k:v for k,v in value.items() if k!=omit} if omit else value))
def _win(path:str)->bool:return PureWindowsPath(path).is_absolute() and bool(PureWindowsPath(path).drive)
def _join(root:str,*parts:str)->str:
    if _win(root): return str(PureWindowsPath(root,*parts))
    return str(Path(root,*parts).absolute())
def _under(child:str,parent:str)->bool:
    if _win(child) or _win(parent):
        c=[x.casefold() for x in PureWindowsPath(child).parts];p=[x.casefold() for x in PureWindowsPath(parent).parts]
    else:c=list(Path(child).resolve().parts);p=list(Path(parent).resolve().parts)
    return len(c)>=len(p) and c[:len(p)]==p

def validate_manifest(value:Mapping[str,Any])->dict[str,Any]:
    if set(value)!=REQUIRED or value.get("schema_version")!=SCHEMA: raise ValueError("invalid_closed_bootstrap_manifest")
    raw=canonical_bytes(value).decode()
    if SECRET.search(" ".join(map(str,value.keys()))) or SECRET.search(raw): raise ValueError("secret_like_field_forbidden")
    m=dict(value)
    if not re.fullmatch(r"[0-9a-f]{40}",str(m["expected_repository_sha"])): raise ValueError("expected_repository_sha_invalid")
    for key in ("allowed_candidate_kinds","allowed_path_prefixes","forbidden_paths","authority_classes","validation_expectations","allowed_source_kinds","allowed_source_schemas"):
        if not isinstance(m[key],list) or not m[key] or m[key]!=sorted(set(m[key])): raise ValueError(key+"_must_be_explicit_canonical_list")
    if not isinstance(m["budgets"],dict) or not isinstance(m["scheduler_policy"],dict) or not isinstance(m["health_probe_policy"],dict): raise ValueError("explicit_policy_required")
    if _under(str(m["external_custody_root"]),str(m["repository_root"])): raise ValueError("external_custody_inside_repository")
    if not _under(str(m["canary_source_path"]),str(m["canary_allowed_path_boundary"])) or not _under(str(m["canary_allowed_path_boundary"]),str(m["repository_root"])): raise ValueError("canary_scope_disagreement")
    return m

def template()->dict[str,Any]:
    return {"schema_version":SCHEMA,"repository_root":r"C:\SentientOS","expected_repository_sha":"REPLACE_WITH_40_HEX_SHA","repository_identity":"REPLACE_OWNER/REPOSITORY","external_custody_root":r"D:\SentientOS Custody","tracked_remote":"origin","tracked_base_ref":"refs/remotes/origin/main","activation_not_before":"REPLACE_UTC","activation_expires_at":"REPLACE_UTC","allowed_candidate_kinds":["maintenance_repair"],"allowed_path_prefixes":["REPLACE_EXPLICIT_PATH"],"forbidden_paths":[".git/**"],"authority_classes":["REPLACE_EXPLICIT_AUTHORITY"],"budgets":{"maximum_actions":1,"maximum_attempts":1,"maximum_changed_line_count":1,"maximum_corrective_retries":1,"maximum_file_count":1,"maximum_implementation_seconds":1,"maximum_validation_seconds":1,"maximum_wall_clock_seconds":1,"publication_retry_backoff_seconds":1},"validation_expectations":["REPLACE_EXACT_TEST_NODE"],"publication_mode":"local_only","scheduler_task_name":"SentientOS Maintenance Wake","scheduler_policy":{"allow_on_battery":False,"execution_timeout":"PT10M","maximum_concurrent_instances":1,"missed_runs_start_later":False,"task_execution_account_mode":"system","trigger_interval_or_exact_schedule":"PT15M","trigger_type":"interval","wake_from_sleep":True},"canary_source_path":r"C:\SentientOS\tests\fixtures\maintenance_windows_live_canary.txt","canary_validation_node":"tests/test_maintenance_windows_host_readiness_closed_loop.py::test_live_canary","canary_allowed_path_boundary":r"C:\SentientOS\tests\fixtures","operator_reference":"REPLACE_OPERATOR","approval_reference":"REPLACE_APPROVAL","commit_identity":{"author_email":"REPLACE","author_name":"REPLACE","committer_email":"REPLACE","committer_name":"REPLACE","reference":"REPLACE"},"commit_title_prefix":"[maintenance]","evaluation_time":"REPLACE_UTC","allowed_source_kinds":["governed_improvement_signal"],"allowed_source_schemas":[collector.GOVERNED_SIGNAL_SCHEMA],"health_probe_policy":{"declared_constraints":["no network"],"estimated_changed_line_count":1,"estimated_file_count":1,"maximum_failing_records":1,"probe_timeout_seconds":60},"remote_readiness_probe_required":False}

def inspect_host(repository_root:str|Path)->dict[str,Any]:
    result: dict[str, Any] = readiness.inspect_host(repository_root)
    return result
def _write(path:Path,value:Mapping[str,Any])->dict[str,str]:
    data=canonical_bytes(value)
    if path.exists():
        if path.is_symlink() or path.read_bytes()!=data: raise ValueError("conflicting_existing_rendered_file:"+str(path))
        state="reused"
    else:
        path.parent.mkdir(parents=True,exist_ok=True); fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
        with os.fdopen(fd,"wb") as f:f.write(data)
        state="created"
    return {"path":str(path),"digest":digest_bytes(data),"write_status":state}
def _exe(facts:Mapping[str,Any],name:str)->str:
    row=facts.get(name,{})
    value=row.get("executable") if isinstance(row,Mapping) else None
    if not value: raise ValueError(name+"_executable_missing")
    return str(value)
def render(manifest:Mapping[str,Any],host_facts:Mapping[str,Any],output_directory:str|Path,*,create_custody_directories:bool=False)->dict[str,Any]:
    m=validate_manifest(manifest); repo=str(m["repository_root"]); custody=str(m["external_custody_root"]); out=Path(output_directory)
    if str(host_facts.get("repository_root"))!=str(Path(repo).resolve()) and str(host_facts.get("repository_root")).casefold()!=repo.casefold(): raise ValueError("host_repository_root_disagreement")
    if host_facts.get("repository_head")!=m["expected_repository_sha"]: raise ValueError("repository_sha_mismatch")
    python=str(host_facts.get("python",{}).get("executable") or ""); git=_exe(host_facts,"git"); codex=_exe(host_facts,"codex")
    powershell=_exe(host_facts,"powershell")
    if not python: raise ValueError("python_executable_missing")
    layout={x:_join(custody,x) for x in DIRS}
    if create_custody_directories:
        for p in layout.values(): Path(p).mkdir(parents=True,exist_ok=True,mode=0o700)
    for p in layout.values():
        if not Path(p).is_dir(): raise ValueError("required_custody_directory_missing:"+p)
    paths={k:Path(layout["configuration"])/v for k,v in FILES.items()}
    profile={"schema_version":profiles.MANIFEST_SCHEMA,"manifest_id":"windows-live-bootstrap","manifest_digest":"","template_no_authority":False,"repository_identity":m["repository_identity"],"repository_root":repo,"base_sha":m["expected_repository_sha"],"allowed_candidate_kinds":m["allowed_candidate_kinds"],"allowed_path_prefixes":m["allowed_path_prefixes"],"forbidden_paths":m["forbidden_paths"],"authority_classes":m["authority_classes"],"budgets":m["budgets"],"operator_reference":m["operator_reference"],"approval_reference":m["approval_reference"],"not_before":m["activation_not_before"],"expires_at":m["activation_expires_at"],"state_root":layout["state"],"workspace_root":layout["workspace"],"scratch_root":layout["scratch"],"inbox_root":layout["inbox"],"codex_home":_join(custody,"codex-home"),"codex_executable":codex,"git_executable":git,"python_executable":python,"validation_bounds":{"aggregate_validation_ceiling_seconds":float(m["budgets"]["maximum_validation_seconds"]),"per_command_default_ceiling_seconds":float(m["budgets"]["maximum_validation_seconds"]),"terminal_reserve_seconds":1.0,"heartbeat_interval_seconds":1.0,"output_tail_limit":4000,"output_byte_limit":200000,"maximum_controller_cycles":m["budgets"]["maximum_attempts"],"require_declared_behavioral_test":True},"publication_mode":m["publication_mode"],"remote_name":m["tracked_remote"],"tracked_base_ref":m["tracked_base_ref"],"base_ref":"refs/heads/"+str(m["tracked_base_ref"]).split("/")[-1],"head_ref_prefix":"maintenance","publication_client_executable":git,"commit_identity":m["commit_identity"],"commit_title_policy":{"prefix":m["commit_title_prefix"]},"output_directory":layout["activation"]}
    profile["manifest_digest"]=profiles.digest(profile,"manifest_digest"); _write(paths["activation_manifest"],profile); profiles.render_profile_bundle(paths["activation_manifest"])
    rendered=activation.render_config(paths["watchdog_config"],repository_root=repo,state_root=layout["state"],workspace_root=layout["workspace"],scratch_root=layout["scratch"],inbox_root=layout["inbox"],standing_grant=Path(layout["activation"])/profiles.FILENAMES["standing_grant"],selector_policy=Path(layout["activation"])/profiles.FILENAMES["selector_policy"],foreman_policy=Path(layout["activation"])/profiles.FILENAMES["foreman_policy"],validation_policy=Path(layout["activation"])/profiles.FILENAMES["validation_policy"],landing_policy=Path(layout["activation"])/profiles.FILENAMES["landing_policy"],maximum_actions=m["budgets"]["maximum_actions"],maximum_wall_clock_seconds=m["budgets"]["maximum_wall_clock_seconds"],publication_retry_backoff_seconds=m["budgets"]["publication_retry_backoff_seconds"],base_sha=m["expected_repository_sha"],tracked_base_ref=m["tracked_base_ref"],implementation_backend="local_codex",commissioned_local_activation=None,stop_marker=_join(layout["state"],"STOP"))
    hp=m["health_probe_policy"]; hc=health.validate_config({"schema_version":health.CONFIG_SCHEMA,"repository_identity":m["repository_identity"],"repository_root":repo,"base_sha":m["expected_repository_sha"],"pytest_node_ids":m["validation_expectations"],"probe_timeout_seconds":hp["probe_timeout_seconds"],"maximum_failing_records":hp["maximum_failing_records"],"probe_state_root":layout["signals"],"governed_signal_output_root":layout["signals"],"declared_validation_expectations":m["validation_expectations"],"requested_maintenance_authority_classes":m["authority_classes"],"declared_constraints":hp["declared_constraints"],"estimated_file_count":hp["estimated_file_count"],"estimated_changed_line_count":hp["estimated_changed_line_count"],"estimated_implementation_seconds":m["budgets"]["maximum_implementation_seconds"],"estimated_validation_seconds":m["budgets"]["maximum_validation_seconds"],"evaluation_time":m["evaluation_time"],"receipt_journal_path":_join(layout["signals"],"health-receipts.jsonl")}); _write(paths["health_config"],hc)
    cc=collector.validate_config({"schema_version":collector.CONFIG_SCHEMA,"repository_identity":m["repository_identity"],"repository_root":repo,"base_sha":m["expected_repository_sha"],"activation_profile_bundle_manifest_path":str(paths["activation_manifest"]),"watchdog_configuration_path":str(paths["watchdog_config"]),"collector_state_root":layout["collector"],"maintenance_candidate_inbox":layout["inbox"],"governed_improvement_signal_source_roots":[layout["signals"]],"normalized_work_item_source_roots":[layout["signals"]],"allowed_source_schemas":m["allowed_source_schemas"],"allowed_source_kinds":m["allowed_source_kinds"],"maximum_source_records_per_scan":1,"maximum_candidates_per_collection":1,"maximum_input_bytes_per_record":200000,"evaluation_time_required":True,"receipt_journal_path":_join(layout["collector"],"receipts.jsonl"),"stop_marker":_join(layout["collector"],"STOP")}); _write(paths["collector_config"],cc)
    ac=autonomy.validate_config({"schema_version":autonomy.CONFIG_SCHEMA,"repository_identity":m["repository_identity"],"repository_root":repo,"base_sha":m["expected_repository_sha"],"activation_profile_bundle_manifest_path":str(paths["activation_manifest"]),"collector_configuration_path":str(paths["collector_config"]),"watchdog_configuration_path":str(paths["watchdog_config"]),"external_cycle_state_root":layout["cycle"],"cycle_receipt_journal_path":_join(layout["cycle"],"receipts.jsonl"),"stop_marker":_join(layout["cycle"],"STOP"),"maximum_cycle_wall_clock_seconds":m["budgets"]["maximum_wall_clock_seconds"],"maximum_collector_invocations_per_cycle":1,"maximum_watchdog_invocations_per_cycle":1,"maximum_candidates_collected_per_cycle":1,"remote_readiness_probe_required":m["remote_readiness_probe_required"],"evaluation_time_required":True}); _write(paths["autonomy_config"],ac)
    wc=wake.validate_config({"schema_version":wake.CONFIG_SCHEMA,"repository_identity":m["repository_identity"],"repository_root":repo,"base_sha":m["expected_repository_sha"],"health_probe_configuration_path":str(paths["health_config"]),"autonomy_cycle_configuration_path":str(paths["autonomy_config"]),"external_wake_state_root":layout["wake"],"wake_receipt_journal_path":_join(layout["wake"],"receipts.jsonl"),"stop_marker":_join(layout["wake"],"STOP"),"evaluation_time":m["evaluation_time"]}); _write(paths["wake_config"],wc)
    dp=m["scheduler_policy"]
    dc=deployment.validate_manifest({"schema_version":deployment.MANIFEST_SCHEMA,"repository_root":repo,"expected_repository_sha":m["expected_repository_sha"],"python_executable":python,"wake_configuration_path":str(paths["wake_config"]),"external_log_directory":layout["logs"],"deployment_output_directory":layout["deployment"],"task_name":m["scheduler_task_name"],"working_directory":repo,"trigger_type":dp["trigger_type"],"trigger_interval_or_exact_schedule":dp["trigger_interval_or_exact_schedule"],"execution_timeout":dp["execution_timeout"],"task_execution_account_mode":dp["task_execution_account_mode"],"allow_on_battery":dp["allow_on_battery"],"wake_from_sleep":dp["wake_from_sleep"],"missed_runs_start_later":dp["missed_runs_start_later"],"maximum_concurrent_instances":dp["maximum_concurrent_instances"],"launcher_stdout_path":_join(layout["logs"],"wake-stdout.log"),"launcher_stderr_path":_join(layout["logs"],"wake-stderr.log")}); _write(paths["deployment_manifest"],dc); deployment.render(dc,layout["deployment"])
    host=readiness.render_host_manifest({"repository_root":repo,"expected_repository_sha":m["expected_repository_sha"],"python_executable":python,"git_executable":git,"codex_executable":codex,"wake_configuration_path":str(paths["wake_config"]),"activation_profile_manifest_path":str(paths["activation_manifest"]),"collector_external_state_root":layout["collector"],"autonomy_external_state_root":layout["cycle"],"wake_external_state_root":layout["wake"],"deployment_manifest_path":str(paths["deployment_manifest"]),"deployment_output_directory":layout["deployment"],"tracked_remote":m["tracked_remote"],"tracked_base_ref":str(m["tracked_base_ref"]).split("/")[-1],"expected_task_name":m["scheduler_task_name"],"canary_source_path":m["canary_source_path"],"canary_validation_node":m["canary_validation_node"],"canary_allowed_path_boundary":m["canary_allowed_path_boundary"]}); _write(paths["host_manifest"],host)
    artifacts={k:{"path":str(p),"digest":digest_bytes(p.read_bytes())} for k,p in sorted(paths.items())}
    index={"schema_version":INDEX_SCHEMA,"bootstrap_manifest_digest":digest(m),"expected_repository_sha":m["expected_repository_sha"],"executable_identities":{"python":python,"git":git,"codex":codex,"powershell":powershell},"artifacts":artifacts,"custody_layout":layout,"repository_bindings":{"repository_identity":m["repository_identity"],"repository_root":repo,"tracked_remote":m["tracked_remote"],"tracked_base_ref":m["tracked_base_ref"]},"activation_profile_identity":{"manifest_id":profile["manifest_id"],"manifest_digest":profile["manifest_digest"]},"authority_bindings":{"authority_classes":m["authority_classes"],"canary_allowed_path_boundary":m["canary_allowed_path_boundary"],"broader_standing_authority_explicit":m["allowed_path_prefixes"]!=[m["canary_allowed_path_boundary"]]},"policy_bindings":{"validation_expectations":m["validation_expectations"],"publication_mode":m["publication_mode"]},"scheduler_mutation_performed":False,"credentials_inspected":False,"maintenance_wake_executed":False,"index_digest":""}; index["index_digest"]=digest(index,"index_digest")
    index_path=out/"windows-live-bootstrap-index.json"; _write(index_path,index)
    return {"status":STATUS_READY,"index_path":str(index_path),"index_digest":index["index_digest"],"scheduler_mutation_performed":False,"credentials_inspected":False,"maintenance_wake_executed":False}

def verify(index_path:str|Path,*,evaluation_time:str)->dict[str,Any]:
    reasons=[]
    try:
        index=json.loads(Path(index_path).read_text());
        if index.get("schema_version")!=INDEX_SCHEMA or index.get("index_digest")!=digest(index,"index_digest"): reasons.append("bundle_index_digest_mismatch")
        for row in index.get("artifacts",{}).values():
            p=Path(row["path"])
            if not p.is_file() or digest_bytes(p.read_bytes())!=row["digest"]: reasons.append("artifact_digest_mismatch")
        arts=index["artifacts"]
        pm=profiles.verify_profile_bundle(arts["activation_manifest"]["path"],evaluation_time)
        if pm["status"]!="profile_bundle_ready":reasons.append("activation_profile_invalid")
        hc=health.load_config(arts["health_config"]["path"]); cc=collector.load_config(arts["collector_config"]["path"]); ac=autonomy.load_config(arts["autonomy_config"]["path"]); wc=wake.load_config(arts["wake_config"]["path"])
        hm=readiness.load_manifest(arts["host_manifest"]["path"]); dm=deployment.load_manifest(arts["deployment_manifest"]["path"])
        if readiness.verify_host_manifest(hm)["status"]!="windows_host_manifest_verified":reasons.append("host_manifest_invalid")
        if deployment.verify(dm,dm["deployment_output_directory"])["status"]!="windows_deployment_ready":reasons.append("deployment_invalid")
        if not (hc["repository_identity"]==cc["repository_identity"]==ac["repository_identity"]==wc["repository_identity"]==index["repository_bindings"]["repository_identity"]): reasons.append("repository_identity_disagreement")
        if not (hc["base_sha"]==cc["base_sha"]==ac["base_sha"]==wc["base_sha"]==index["expected_repository_sha"]): reasons.append("repository_sha_disagreement")
        if wc["health_probe_configuration_path"]!=arts["health_config"]["path"] or wc["autonomy_cycle_configuration_path"]!=arts["autonomy_config"]["path"]:reasons.append("wake_binding_disagreement")
        if SECRET.search(canonical_bytes(index).decode()): reasons.append("secret_like_field")
    except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError) as exc: reasons.append(str(exc))
    return {"status":STATUS_READY if not reasons else STATUS_BLOCKED,"reason_codes":sorted(set(reasons)),"warnings":[],"scheduler_mutation_performed":False,"credentials_inspected":False,"maintenance_wake_executed":False}

def inspect(index_path:str|Path)->dict[str,Any]:
    try:value=json.loads(Path(index_path).read_text()); return {"status":"windows_live_bootstrap_inspected","index":value}
    except Exception as exc:return {"status":STATUS_BLOCKED,"reason_codes":[str(exc)]}
def print_preflight_command(index_path:str|Path)->dict[str,Any]:
    index=json.loads(Path(index_path).read_text()); a=index["artifacts"]; exe=index["executable_identities"]; repo=index["repository_bindings"]["repository_root"]
    host=readiness.load_manifest(a["host_manifest"]["path"]); dep=deployment.load_manifest(a["deployment_manifest"]["path"])
    commands=[{"argv":[exe["python"],str(Path(repo)/"scripts"/"maintenance_windows_live_bootstrap.py"),"inspect-host","--repository-root",repo],"shell":False},{"argv":[exe["python"],str(Path(repo)/"scripts"/"maintenance_windows_live_bootstrap.py"),"verify","--index",str(index_path),"--evaluation-time","<fresh-utc-evaluation-time>"],"shell":False}]
    commands.extend(readiness.print_manual_canary_command(host)["commands"]); commands.append({"argv":[exe["python"],str(Path(repo)/"scripts"/"maintenance_windows_host_readiness.py"),"inspect-canary","--manifest",a["host_manifest"]["path"],"--require-status","canary_completed"],"shell":False}); commands.append({"argv":[exe["python"],str(Path(repo)/"scripts"/"maintenance_windows_deployment.py"),"verify","--manifest",a["deployment_manifest"]["path"],"--output-directory",dep["deployment_output_directory"]],"shell":False}); commands.append(deployment.print_install_command(dep)["commands"][0] if "commands" in deployment.print_install_command(dep) else {"argv":deployment.print_install_command(dep)["argv"],"shell":False})
    return {"status":"windows_live_bootstrap_preflight_command_ready","commands":commands,"executed":False,"scheduler_mutation_performed":False}
