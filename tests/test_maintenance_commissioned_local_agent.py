from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from sentientos import maintenance_commissioned_local_agent as local_agent
from sentientos import maintenance_implementation_agent as mia
from sentientos import maintenance_loop_watchdog as watchdog
from sentientos.governed_local_model_invocation import LocalModelInvocationReceipt
from tests.maintenance_watchdog_implementation_fixtures import NOW, setup

pytestmark = pytest.mark.no_legacy_skip


class ScriptedCommissionedInvoker:
    def __init__(self, actions):
        self.actions=list(actions); self.prompts=[]
        self.model=SimpleNamespace(active_identity=SimpleNamespace(
            fallback=False, posture="production", to_dict=lambda: {
                "model_id":"commissioned-fixture","semantic_artifact_identity":"sha256:fixture",
                "posture":"production","fallback":False}))
    def build_request(self, **kwargs):
        self.prompts.append(kwargs["prompt"])
        return SimpleNamespace(request_id=f"request-{len(self.prompts)}", model_id="commissioned-fixture", **kwargs)
    def invoke(self, request, **kwargs):
        output=self.actions.pop(0)
        return LocalModelInvocationReceipt(request={},status="admitted_completed",reason_codes=("completed",),
            output_text=json.dumps(output) if not isinstance(output,str) else output,
            output_digest="digest",output_size_bytes=1,generation_config={},admission_decision_ref="admitted",
            purpose=local_agent.PURPOSE,latency_ms=1,output_truncated=False,fallback_occurred=False,
            effects={"local_model_inference":True,"provider_network":False,"tool":False,"memory":False,
                     "action":False,"adoption":False,"repository_mutation":False},observed_at=NOW)


def prepared(tmp_path, actions, *, bounds=None):
    tmp_path.mkdir(parents=True,exist_ok=True)
    cfg,roots,repo=setup(tmp_path,extra_authorities=sorted(local_agent.REQUIRED_AUTHORITIES))
    for _ in range(3): watchdog.tick(cfg,evaluation_time=NOW)
    lease=json.loads(next((roots["state"]/"maintenance_leases").glob("*.json")).read_text())
    request_path=next((roots["state"]/"maintenance_implementation_requests").glob("*.json"))
    original=json.loads(request_path.read_text())
    authorities=sorted(set(original["requested_authority_classes"]) | set(local_agent.REQUIRED_AUTHORITIES))
    request=mia.seal_request({**original,"lease_digest":lease["lease_digest"],"driver_id":"commissioned_local_model",
        "driver_kind":"commissioned_local","requested_authority_classes":authorities}, instruction_artifact_root=roots["state"])
    session={"session_id":"commissioned-session","attempt_id":"attempt","attempt_ordinal":1,
             "corrective_retry_ordinal":0,"task_id":lease["task_id"]}
    driver=local_agent.CommissionedLocalDriver(ScriptedCommissionedInvoker(actions),bounds=bounds)
    return driver,watchdog._foreman_config(cfg),lease,request,session,roots,repo


def run_driver(bundle, *, feedback=()):
    driver,config,lease,request,session,roots,_=bundle
    return driver.run(config=config,lease=lease,request=request,session=session,
                      artifact_root=roots["state"],evaluation_time=NOW,validation_feedback=feedback)


def test_commissioned_local_agent_edits_only_worktree_and_reports_no_remote_effects(tmp_path):
    content="implemented locally\n"
    actions=[{"action":"read_file","arguments":{"path":"allowed.txt"}},
             {"action":"replace_file","arguments":{"path":"allowed.txt","expected_sha256":hashlib.sha256(b"base\n").hexdigest(),"content":content}},
             {"action":"git_diff","arguments":{}},{"action":"candidate_complete","summary":"ready"}]
    bundle=prepared(tmp_path,actions); result=run_driver(bundle)
    driver,_,_,_,_,roots,repo=bundle
    assert result["status"]=="implementation_ready_for_validation"
    assert (repo/"allowed.txt").read_text()=="base\n"
    worktree=Path(json.loads(next((roots["state"]/"maintenance_worktrees").glob("*.json")).read_text())["worktree_root"])
    assert (worktree/"allowed.txt").read_text()==content
    assert result["effects"]["remote_model_invocation_performed"] is False
    assert result["effects"]["codex_invocation_performed"] is False
    assert result["effects"]["git_commit_performed"] is False
    assert result["effects"]["validation_performed"] is False
    assert "change allowed.txt" in driver.invoker.prompts[0].lower()


@pytest.mark.parametrize("bad_path",["../escape","/tmp/escape",".git/config"])
def test_path_escape_and_git_mutation_are_rejected_without_effect(tmp_path,bad_path):
    actions=[{"action":"replace_file","arguments":{"path":bad_path,"expected_sha256":hashlib.sha256(b"").hexdigest(),"content":"bad"}},
             {"action":"blocked","reason":"denied"}]
    bundle=prepared(tmp_path,actions); result=run_driver(bundle)
    driver,_,_,_,_,_,_=bundle
    assert result["status"]=="implementation_blocked"
    assert "workspace_path_rejected" in driver.invoker.prompts[-1]


def test_symlink_escape_and_unauthorized_command_are_denied(tmp_path):
    bundle=prepared(tmp_path,[{"action":"run_allowed_command","arguments":{"argv":["git","commit","-am","bad"]}},
                              {"action":"read_file","arguments":{"path":"link/secret"}},
                              {"action":"blocked","reason":"bounded"}])
    driver,config,lease,request,session,roots,_=bundle
    worktree=Path(config.external_workspace_root)/lease["task_id"]/session["session_id"]
    worktree.parent.mkdir(parents=True,exist_ok=True)
    # Let custody create first, then place an escaping link before exercising the tool directly.
    descriptor=local_agent.custody.prepare_worktree(config,lease,session["session_id"])
    (Path(descriptor["worktree_root"])/"link").symlink_to(tmp_path,target_is_directory=True)
    state=local_agent.CommissionedLocalSession(session["session_id"],lease["task_id"],"c",lease["lease_id"],lease["base_sha"],descriptor,{},"brief",driver.bounds)
    denied=driver._execute_tool(config,lease,state,"run_allowed_command",{"argv":["git","commit","-am","bad"]},NOW)
    escaped=driver._execute_tool(config,lease,state,"read_file",{"path":"link/secret"},NOW)
    assert denied=={"ok":False,"error":"command_not_allowed","no_effect":True}
    assert escaped["ok"] is False and "workspace" in escaped["error"]


def test_malformed_and_unsupported_actions_have_no_effect_and_are_bounded(tmp_path):
    bounds=local_agent.LocalAgentBounds(max_iterations=4,max_parse_errors=2,max_total_new_tokens=4096)
    bundle=prepared(tmp_path,["not json",{"action":"unsupported","arguments":{}},{"action":"candidate_complete"}],bounds=bounds)
    result=run_driver(bundle)
    assert result["status"]=="implementation_failed" and result["changed_paths"]==[]


def test_budget_exhaustion_and_cancellation_stop_effects(tmp_path):
    bounds=local_agent.LocalAgentBounds(max_iterations=1,max_total_new_tokens=1024)
    bundle=prepared(tmp_path,[{"action":"git_status","arguments":{}},{"action":"candidate_complete"}],bounds=bounds)
    assert run_driver(bundle)["status"]=="implementation_budget_exceeded"
    bundle2=prepared(tmp_path/"cancel",[{"action":"replace_file","arguments":{"path":"allowed.txt","expected_sha256":hashlib.sha256(b"base\n").hexdigest(),"content":"bad"}}])
    driver,_,_,_,session,_,_=bundle2
    driver.request_cancellation(session,"operator:test")
    assert run_driver(bundle2)["status"]=="implementation_cancelled"


def test_corrective_continuation_reuses_worktree_and_receives_validation_failure(tmp_path):
    first=[{"action":"replace_file","arguments":{"path":"allowed.txt","expected_sha256":hashlib.sha256(b"base\n").hexdigest(),"content":"wrong\n"}},
           {"action":"candidate_complete","summary":"first"},
           {"action":"read_file","arguments":{"path":"allowed.txt"}},
           {"action":"replace_file","arguments":{"path":"allowed.txt","expected_sha256":hashlib.sha256(b"wrong\n").hexdigest(),"content":"corrected\n"}},
           {"action":"candidate_complete","summary":"corrected"}]
    bundle=prepared(tmp_path,first); initial=run_driver(bundle)
    assert initial["status"]=="implementation_ready_for_validation"
    correction=run_driver(bundle,feedback=({"check":"pytest","status":"failed","stderr":"expected corrected"},))
    assert correction["status"]=="implementation_ready_for_validation" and correction["validation_feedback_count"]==1
    driver,_,_,_,_,roots,_=bundle
    assert "expected corrected" in driver.invoker.prompts[-1]
    worktree=Path(json.loads(next((roots["state"]/"maintenance_worktrees").glob("*.json")).read_text())["worktree_root"])
    assert (worktree/"allowed.txt").read_text()=="corrected\n"


def test_backend_descriptor_is_explicit_and_never_claims_validation_or_remote_inference():
    descriptor=local_agent.CommissionedLocalDriver(ScriptedCommissionedInvoker([])).describe_driver()
    assert mia.verify_driver(local_agent.CommissionedLocalDriver(ScriptedCommissionedInvoker([])))["driver_kind"]=="commissioned_local"
    assert descriptor["supports_remote_model_invocation"] is False
    assert descriptor["performs_validation"] is descriptor["performs_commit"] is descriptor["performs_publication"] is False


def test_real_commissioned_local_model_integration_requires_explicit_fixture():
    """Opt-in proof that the exact activated model can speak the action protocol."""
    import os
    activation=os.environ.get("SENTIENTOS_COMMISSIONED_LOCAL_ACTIVATION")
    if not activation:
        pytest.skip("real commissioned GGUF runtime not supplied")
    from sentientos.local_model_production_commissioning import load_activation
    from sentientos.governed_local_model_invocation import GovernedLocalModelInvoker, LocalModelInvocationBudget
    model,authority=load_activation(activation)
    try:
        invoker=GovernedLocalModelInvoker(model=model,authority_map=authority)
        request=invoker.build_request(purpose=local_agent.PURPOSE,
            prompt='Return exactly {"action":"candidate_complete","summary":"ready"} and no other text.',
            caller="maintenance_real_integration",correlation_id="maintenance-real-integration",
            expected_output_format="json",budget=LocalModelInvocationBudget(1000,1000,128,60,1))
        receipt=invoker.invoke(request)
        assert receipt.status=="admitted_completed"
        assert local_agent.CommissionedLocalDriver._parse_action(receipt.output_text or "") is not None
        assert receipt.effects["provider_network"] is False
    finally:
        model.close()
