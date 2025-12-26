from importlib import reload
from pathlib import Path
from typing import Mapping

import pytest

from control_plane import RequestType, admit_request
import intent_bundle
import task_executor

pytestmark = pytest.mark.no_legacy_skip


def _provenance(task_id: str) -> task_executor.AuthorityProvenance:
    return task_executor.AuthorityProvenance(
        authority_source="test-harness",
        authority_scope=f"task:{task_id}",
        authority_context_id="ctx-test",
        authority_reason="test",
    )


def _issue_token(
    task: task_executor.Task,
    auth,
    declared_inputs: Mapping[str, object] | None = None,
) -> task_executor.AdmissionToken:
    provenance = _provenance(task.task_id)
    fingerprint = task_executor.request_fingerprint_from_canonical(
        task_executor.canonicalise_task_request(
            task=task, authorization=auth, provenance=provenance, declared_inputs=declared_inputs
        )
    )
    return task_executor.AdmissionToken(
        task_id=task.task_id, provenance=provenance, request_fingerprint=fingerprint
    )


def _make_task(task_id: str, *, approval_required: bool, counter: dict | None = None) -> task_executor.Task:
    def step_action():
        if counter is not None:
            counter["count"] += 1
        return {"status": "ok"}

    actions = []
    if approval_required:
        actions.append(
            task_executor.EprAction(
                action_id="needs-approval",
                parent_task_id=task_id,
                trigger_step_id=1,
                authority_impact="local",
                reversibility="guaranteed",
                rollback_proof="snapshot",
                external_effects="no",
                handler=lambda: {"closure_changed": True},
                description="requires local authority",
            )
        )
    else:
        actions.append(
            task_executor.EprAction(
                action_id="auto-fix",
                parent_task_id=task_id,
                trigger_step_id=1,
                authority_impact="none",
                reversibility="guaranteed",
                rollback_proof="snapshot",
                external_effects="no",
                handler=lambda: {"closure_changed": True},
                description="auto repair",
            )
        )
    return task_executor.Task(
        task_id=task_id,
        objective=f"task {task_id}",
        steps=(task_executor.Step(step_id=1, kind="python", payload=task_executor.PythonPayload(callable=step_action)),),
        allow_epr=True,
        epr_actions=tuple(actions),
    )


def _make_auth(task_id: str):
    return admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash=f"intent-{task_id}",
        context_hash=f"context-{task_id}",
        policy_version="v1-static",
    ).record


def test_intent_bundle_expands_deterministically(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)
    tasks = (
        _make_task("alpha", approval_required=False),
        _make_task("beta", approval_required=True),
    )
    bundle = intent_bundle.IntentBundle(bundle_id="bundle-1", intent="Play Game X", tasks=tasks)

    expanded_once = bundle.expand()
    expanded_twice = bundle.expand()

    assert [item.task.task_id for item in expanded_once] == ["alpha", "beta"]
    assert [item.task.task_id for item in expanded_twice] == ["alpha", "beta"]
    assert bundle.identity_digest == expanded_once[0].identity_digest == expanded_twice[1].identity_digest


def test_bundle_aggregates_approvals_single_prompt(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)
    approvals = {"calls": 0}

    def requester(request: intent_bundle.ApprovalRequest) -> bool:
        approvals["calls"] += 1
        assert len(request.actions) == 1
        assert request.actions[0].action_id == "needs-approval"
        return True

    task_alpha = _make_task("alpha", approval_required=True)
    task_beta = _make_task("beta", approval_required=False)
    bundle = intent_bundle.IntentBundle(bundle_id="bundle-2", intent="Play Game Y", tasks=(task_alpha, task_beta))

    authorizations = {task.task_id: _make_auth(task.task_id) for task in bundle.tasks}
    tokens = {task.task_id: _issue_token(task, authorizations[task.task_id]) for task in bundle.tasks}

    report = intent_bundle.execute_intent_bundle(
        bundle,
        authorizations=authorizations,
        admission_tokens=tokens,
        approval_requester=requester,
    )

    assert approvals["calls"] == 1
    assert report.classification == "completed"
    assert report.approval.prompt_count == 1
    assert report.authority_used == ("needs-approval",)
    assert report.automatic_repairs == ("auto-fix",)


def test_bundle_denial_aborts_cleanly(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)
    counter = {"count": 0}

    task = _make_task("alpha", approval_required=True, counter=counter)
    bundle = intent_bundle.IntentBundle(bundle_id="bundle-3", intent="Play Game Z", tasks=(task,))

    authorizations = {task.task_id: _make_auth(task.task_id)}
    tokens = {task.task_id: _issue_token(task, authorizations[task.task_id])}

    report = intent_bundle.execute_intent_bundle(
        bundle,
        authorizations=authorizations,
        admission_tokens=tokens,
        approval_requester=lambda _: False,
    )

    assert report.classification == "refused"
    assert counter["count"] == 0
    assert report.skipped == ("alpha",)


def test_bundle_summary_matches_execution(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)

    task = _make_task("alpha", approval_required=True)
    bundle = intent_bundle.IntentBundle(bundle_id="bundle-4", intent="Play Game Q", tasks=(task,))

    authorizations = {task.task_id: _make_auth(task.task_id)}
    tokens = {task.task_id: _issue_token(task, authorizations[task.task_id])}

    report = intent_bundle.execute_intent_bundle(
        bundle,
        authorizations=authorizations,
        admission_tokens=tokens,
        approval_requester=lambda _: True,
    )
    summary = report.render_summary()

    assert "Intent: Play Game Q" in summary
    assert "Automatically handled: none" in summary
    assert "Authority used: needs-approval" in summary


def test_bundle_does_not_grant_new_authority(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)
    counter = {"count": 0}

    def step_action():
        counter["count"] += 1
        return {"status": "ok"}

    task = task_executor.Task(
        task_id="alpha",
        objective="blocked task",
        steps=(task_executor.Step(step_id=1, kind="python", payload=task_executor.PythonPayload(callable=step_action)),),
        allow_epr=True,
        epr_actions=(
            task_executor.EprAction(
                action_id="forbidden",
                parent_task_id="alpha",
                trigger_step_id=1,
                authority_impact="local",
                reversibility="guaranteed",
                rollback_proof="snapshot",
                external_effects="yes",
                handler=lambda: {"closure_changed": True},
            ),
        ),
    )
    bundle = intent_bundle.IntentBundle(bundle_id="bundle-5", intent="Play Game R", tasks=(task,))

    authorizations = {task.task_id: _make_auth(task.task_id)}
    tokens = {task.task_id: _issue_token(task, authorizations[task.task_id])}

    report = intent_bundle.execute_intent_bundle(
        bundle,
        authorizations=authorizations,
        admission_tokens=tokens,
        approval_requester=lambda _: True,
    )

    assert report.classification == "blocked"
    assert counter["count"] == 0
