import copy
import json
import subprocess
from pathlib import Path

import pytest

from sentientos import maintenance_activation_profiles as profiles
from sentientos import maintenance_authority_continuity as c
from sentientos import maintenance_commit_publication as landing
from sentientos import maintenance_task_authority_lease as leases
from sentientos import maintenance_task_journal as journal
from sentientos import maintenance_validation_controller as validation
from tests.maintenance_commit_publication_fixtures import lease, pol, repo

pytestmark = pytest.mark.no_legacy_skip
NOW = "2030-01-02T00:00:00Z"


def write(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(c.canonical_bytes(value) + b"\n")
    return path


def sealed(value: dict, key: str) -> dict:
    value[key] = c.digest(value, key)
    return value


def setup(tmp_path: Path):
    repository, old_worktree, base = repo(tmp_path)
    subprocess.run(["git", "worktree", "remove", "--force", str(old_worktree)], cwd=repository, check=True)
    subprocess.run(["git", "branch", "-m", "main"], cwd=repository, check=True)
    root = tmp_path / "custody"
    m = profiles.manifest_template()
    m.update(template_no_authority=False, manifest_id="line-generation-0", repository_identity="repo", repository_root=str(repository.resolve()), base_sha=base, allowed_candidate_kinds=["repair"], allowed_path_prefixes=["a.txt"], forbidden_paths=[".git/**"], authority_classes=["repository_commit", "local_repository_base_advance"], budgets={"maximum_file_count":2,"maximum_changed_line_count":20,"maximum_implementation_seconds":10,"maximum_validation_seconds":20,"maximum_wall_clock_seconds":40,"maximum_attempts":1,"maximum_corrective_retries":0,"publication_retry_backoff_seconds":1,"maximum_actions":2}, operator_reference="operator", approval_reference="approval", not_before="2030-01-01T00:00:00Z", expires_at="2030-02-01T00:00:00Z", state_root=str((tmp_path/"state").resolve()), workspace_root=str((tmp_path/"work").resolve()), scratch_root=str((tmp_path/"scratch").resolve()), inbox_root=str((tmp_path/"inbox").resolve()), codex_home=str((tmp_path/"codex").resolve()), codex_executable=str(Path("/bin/false").resolve()), git_executable=str(Path("/usr/bin/git").resolve()), python_executable=str(Path("/bin/false").resolve()), validation_bounds={"aggregate_validation_ceiling_seconds":20,"per_command_default_ceiling_seconds":10,"terminal_reserve_seconds":1,"heartbeat_interval_seconds":1,"output_tail_limit":100,"output_byte_limit":1000,"maximum_controller_cycles":1,"require_declared_behavioral_test":True}, publication_mode=landing.LOCAL_FAST_FORWARD_MODE, remote_name="origin", tracked_base_ref="refs/heads/main", base_ref="refs/heads/main", head_ref_prefix="maint/", publication_client_executable=None, commit_identity={"author_name":"a","author_email":"a@b","committer_name":"a","committer_email":"a@b","reference":"r"}, commit_title_policy={"prefix":"[maintenance]"}, output_directory=str((root/"profile-0").resolve()))
    m["manifest_digest"] = profiles.digest(m, "manifest_digest")
    mp = write(root/"manifest-0.json", m); rendered = profiles.render_profile_bundle(mp)
    p = sealed({"schema_version":c.POLICY_SCHEMA,"policy_id":"policy","policy_digest":"","lineage_id":"line","repository_identity":"repo","generation_root":str(root.resolve()),"receipt_root":str((root/"receipts").resolve()),"initial_generation_path":str((root/"generation-0.json").resolve()),"operator_reference":"operator","approval_reference":"approval","created_at":NOW,"constraints":["same_or_narrower","local_fast_forward_base_ref","no_runtime_adoption"]}, "policy_digest")
    g = {"schema_version":c.GENERATION_SCHEMA,"generation_id":"line:generation:0","generation_digest":"","lineage_id":"line","ordinal":0,"base_sha":base,"manifest_path":str(mp.resolve()),"manifest_digest":m["manifest_digest"],"profile_bundle_digest":rendered["bundle_digest"],"predecessor_generation_digest":"","prior_receipt_digest":"","created_at":NOW}; g["generation_digest"] = c._generation_digest(g)
    return write(root/"policy.json", p), write(root/"generation-0.json", g), g, root, repository


def canonical_custody(tmp_path: Path, repository: Path, generation: dict, number: int, *, create_adapters: bool = True, state_root: Path | None = None):
    task = f"task{number}"; state = state_root or tmp_path/f"state-{number}"; state.mkdir(exist_ok=True)
    wt = tmp_path/f"wt-{number}"; subprocess.run(["git","worktree","add","--detach",str(wt),generation["base_sha"]],cwd=repository,check=True,capture_output=True)
    (wt/"a.txt").write_text(f"generation {number + 1}\n")
    le = lease(task=task, base=generation["base_sha"], mode=landing.LOCAL_FAST_FORWARD_MODE); le["grant_generation"] = generation["generation_digest"]; le["lease_digest"] = leases._seal(le,"lease_digest")
    write(state/"maintenance_leases"/f"{le['lease_id']}.json", le)
    created={"candidate_ref":"cand","candidate_revision_digest":"sha256:c","canonical_candidate_digest":"sha256:cc","selection_digest":"sha256:ss","selector_policy_digest":"sha256:sp","admitted_scope_digest":"sha256:s","operator_grant_id":"grant","operator_grant_digest":"sha256:g","base_sha":generation["base_sha"],"maximum_attempts":1,"maximum_corrective_retries":0}
    for event,payload in [("task_created",created),("authority_lease_bound",{"lease_id":le["lease_id"],"lease_digest":le["lease_digest"],"scope_digest":"sha256:s","expires_at":"9999","maximum_attempts":1,"maximum_corrective_retries":0}),("attempt_started",{"attempt_id":"a1","lease_id":le["lease_id"],"scope_digest":"sha256:s"}),("implementation_completed",{"attempt_id":"a1"})]: journal.append_event(state,event,task_id=task,payload=payload,repo_root=repository,recorded_at=NOW)
    vr={"schema_version":validation.RESULT_SCHEMA,"task_id":task,"attempt_id":"a1","session_id":"s1","implementation_session_id":"s1","codex_thread_id":"thread","implementation_result_digest":"sha256:ir","worktree_descriptor_digest":"sha256:wt","change_manifest_digest":"sha256:cm","patch_digest":"sha256:p","base_sha":generation["base_sha"],"changed_paths":["a.txt"],"worktree_manifest":landing._manifest(wt,["a.txt"]),"validation_ref_id":f"v{number}","plan_digest":"sha256:vp","command_result_digests":["sha256:command"],"required_stage_outcomes":[{"stage_id":"focused","exit_code":0,"failure_class":None}],"skipped_stages":[],"total_duration_seconds":1,"total_budget_consumed_seconds":1,"cumulative_task_validation_seconds":1,"source_drift_proof":{"before":"same","after":"same","source_drift_detected":False},"exhaustive_matrix_status":"not_requested_for_proportionate_validation","matrix_invocation_count":0,"terminal_status":"validation_ready_for_commit","failure_classification":None,"correctable":False,"result_digest":"","journal_terminal_event_id":None}
    vr["result_digest"] = validation.seal(vr,"result_digest"); write(state/"maintenance_validation_results"/f"v{number}.json",vr)
    journal.append_event(state,"validation_started",task_id=task,payload={"validation_ref_id":f"v{number}","attempt_id":"a1","plan_digest":"sha256:vp","change_manifest_digest":"sha256:cm","worktree_descriptor_digest":"sha256:wt"},repo_root=repository,recorded_at=NOW)
    journal.append_event(state,"validation_passed",task_id=task,payload={"validation_ref_id":f"v{number}","attempt_id":"a1","result_digest":vr["result_digest"]},repo_root=repository,recorded_at=NOW)
    built=landing.create_commit_and_enqueue(state_root=state,repository_root=repository,worktree_root=wt,lease=le,validation_result=vr,landing_policy=pol(tmp_path/f"policy-{number}",repository),evaluation_time=NOW)
    result=landing.publish_one_maintenance_request(state_root=state,repository_root=repository,lease=le,landing_policy=pol(tmp_path/f"policy-{number}",repository),publication_id=built["publication_request"]["publication_id"],evaluation_time=NOW)
    assert result["terminal_status"] == "publication_succeeded"
    journal.append_event(state,"task_closed",task_id=task,payload={"closure_status":"completed"},repo_root=repository,repository_sha=result["commit_sha"],recorded_at=NOW)
    jp=state/"maintenance_tasks"/f"{task}.jsonl"; snapshot=journal.materialize_snapshot(state,task,repo_root=repository)
    paths={"lease_path":state/"maintenance_leases"/f"{le['lease_id']}.json","validation_result_path":state/"maintenance_validation_results"/f"v{number}.json","commit_plan_path":state/"maintenance_commit_plans"/f"{built['plan']['plan_digest'].split(':')[1]}.json","commit_result_path":state/"maintenance_commit_results"/f"{built['commit_result']['commit_result_id']}.json","publication_request_path":state/"maintenance_publication_requests"/f"{built['publication_request']['publication_id']}.json","landing_result_path":state/"maintenance_publication_results"/f"{built['publication_request']['publication_id']}.json"}
    if not create_adapters:
        return None, None, {"task_id": task, "snapshot": snapshot, "paths": paths}, result
    cm=sealed({"schema_version":c.CANONICAL_COMPLETION_SCHEMA,"evidence_id":f"done{number}","evidence_digest":"","generation_digest":generation["generation_digest"],"task_id":task,"repository_root":str(repository.resolve()),"state_root":str(state.resolve()),"journal_path":str(jp.resolve()),"journal_digest":landing.bytes_digest(jp.read_bytes()),"lease_path":str(paths["lease_path"].resolve()),"lease_digest":le["lease_digest"],"validation_result_path":str(paths["validation_result_path"].resolve()),"validation_evidence_digest":vr["result_digest"],"commit_plan_path":str(paths["commit_plan_path"].resolve()),"commit_plan_digest":built["plan"]["plan_digest"],"commit_result_path":str(paths["commit_result_path"].resolve()),"commit_evidence_digest":built["commit_result"]["commit_result_digest"],"publication_request_path":str(paths["publication_request_path"].resolve()),"publication_request_digest":built["publication_request"]["publication_request_digest"],"landing_result_path":str(paths["landing_result_path"].resolve()),"landing_evidence_digest":result["publication_result_digest"],"closure_event_digest":snapshot["last_event_digest"]},"evidence_digest")
    sp=sealed({"schema_version":c.CANONICAL_SUCCESSOR_SCHEMA,"evidence_id":f"next{number}","evidence_digest":"","completion_evidence_digest":cm["evidence_digest"],"landing_result_path":cm["landing_result_path"],"landing_evidence_digest":cm["landing_evidence_digest"],"repository_root":str(repository.resolve()),"base_ref":"refs/heads/main","predecessor_base_sha":generation["base_sha"],"successor_sha":result["commit_sha"],"observed_at":NOW},"evidence_digest")
    return write(tmp_path/f"completion-{number}.json",cm),write(tmp_path/f"successor-{number}.json",sp),cm,sp


def test_canonical_custody_two_generation_inheritance_and_exact_retry(tmp_path: Path):
    policy,_,g0,root,repository=setup(tmp_path); cp,sp,_,_=canonical_custody(tmp_path,repository,g0,0)
    first = c.derive_next(policy,cp,sp,NOW); assert first["status"] == "successor_generation_ready", first
    assert c.derive_next(policy,cp,sp,NOW)["write_status"] == "reused"
    g1=json.loads((root/"generation-1.json").read_text()); cp2,sp2,_,_=canonical_custody(tmp_path,repository,g1,1)
    assert c.derive_next(policy,cp2,sp2,NOW)["status"] == "successor_generation_ready"
    assert json.loads((root/"generation-2.json").read_text())["ordinal"] == 2


def test_fabricated_self_consistent_v1_evidence_is_diagnostic_only(tmp_path: Path):
    policy,_,g,_,_=setup(tmp_path)
    completion=sealed({k:("" if k.endswith("digest") else "passed") for k in c.COMPLETION_KEYS},"evidence_digest"); completion.update(schema_version=c.COMPLETION_SCHEMA,generation_digest=g["generation_digest"]); sealed(completion,"evidence_digest")
    successor=sealed({k:"" for k in c.SUCCESSOR_KEYS},"evidence_digest"); successor["schema_version"]=c.SUCCESSOR_SCHEMA; sealed(successor,"evidence_digest")
    assert c.derive_next(policy,write(tmp_path/"weak-c.json",completion),write(tmp_path/"weak-s.json",successor),NOW)["status"] == "continuity_not_ready"


@pytest.mark.parametrize("mutation", ["missing", "changed", "wrong_task", "wrong_lease", "ref_moved", "dirty"])
def test_canonical_source_or_current_repository_tampering_fails_closed(tmp_path: Path, mutation: str):
    policy,_,g,_,repository=setup(tmp_path); cp,sp,cm,_=canonical_custody(tmp_path,repository,g,0)
    if mutation == "missing": Path(cm["validation_result_path"]).unlink()
    elif mutation == "changed": Path(cm["commit_result_path"]).write_text("{}")
    elif mutation == "wrong_task":
        value=json.loads(cp.read_text()); value["task_id"]="other"; sealed(value,"evidence_digest"); write(cp,value)
    elif mutation == "wrong_lease":
        value=json.loads(Path(cm["lease_path"]).read_text()); value["lease_id"]="other"; value["lease_digest"]=leases._seal(value,"lease_digest"); write(Path(cm["lease_path"]),value)
    elif mutation == "ref_moved": subprocess.run(["git","update-ref","refs/heads/main",g["base_sha"]],cwd=repository,check=True)
    else: (repository/"dirty").write_text("x")
    assert c.derive_next(policy,cp,sp,NOW)["status"] == "continuity_not_ready"


def test_same_or_narrower_and_corrupted_lineage_regressions(tmp_path: Path):
    policy,_,g,root,repository=setup(tmp_path); old=json.loads((root/"manifest-0.json").read_text())
    for key,value in [("authority_classes",old["authority_classes"]+["remote_ref_publish"]),("expires_at","2031-01-01T00:00:00Z")]:
        new=copy.deepcopy(old); new[key]=value; assert not c._same_or_narrower(old,new)
    cp,sp,_,_=canonical_custody(tmp_path,repository,g,0); assert c.derive_next(policy,cp,sp,NOW)["status"]=="successor_generation_ready"
    receipt=json.loads((root/"receipts/receipt-1.json").read_text()); receipt["completed_task_id"]="tampered"; write(root/"receipts/receipt-1.json",receipt)
    assert c.inspect(policy)["status"]=="continuity_blocked"
    assert "sentientosd" not in Path(c.__file__).read_text()
