from __future__ import annotations

import pytest

from control_plane import AuthorizationRecord, Decision, ReasonCode, RequestType
import task_admission
import task_executor

pytestmark = pytest.mark.no_legacy_skip


def _provenance(task_id: str) -> task_executor.AuthorityProvenance:
    return task_executor.AuthorityProvenance(
        authority_source="test-harness",
        authority_scope=f"task:{task_id}",
        authority_context_id="ctx-test",
        authority_reason="test",
    )


def _noop_task(task_id: str = "task-1") -> task_executor.Task:
    return task_executor.Task(
        task_id=task_id,
        objective="noop",
        steps=(task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload()),),
    )


def _ctx() -> task_admission.AdmissionContext:
    return task_admission.AdmissionContext(
        actor="tester",
        mode="manual",
        node_id="node-1",
        vow_digest=None,
        doctrine_digest=None,
        now_utc_iso=None,
    )


def _auth() -> AuthorizationRecord:
    return AuthorizationRecord(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="tester",
        intent_hash="i",
        context_hash="c",
        policy_version="v1",
        decision=Decision.ALLOW,
        reason=ReasonCode.OK,
        timestamp=0.0,
        metadata=None,
    )


def test_denied_admission_never_invokes_executor(monkeypatch):
    invoked = False

    class FakeExecutor:
        def execute_task(self, *_args, **_kwargs):
            nonlocal invoked
            invoked = True
            raise AssertionError("executor should not be called")

    policy = task_admission.AdmissionPolicy(policy_version="v1", max_steps=0)
    decision, result = task_admission.run_task_with_admission(
        _noop_task(), _ctx(), policy, authorization=_auth(), executor=FakeExecutor()
    )

    assert decision.allowed is False
    assert result is None
    assert invoked is False


def test_normal_path_passes_admission_token_to_executor():
    received_token = None

    class FakeExecutor:
        def execute_task(self, task, *, admission_token=None, **_kwargs):
            nonlocal received_token
            received_token = admission_token
            return "ok"

    policy = task_admission.AdmissionPolicy(policy_version="v1")
    decision, result = task_admission.run_task_with_admission(
        _noop_task("task-token"), _ctx(), policy, authorization=_auth(), executor=FakeExecutor()
    )

    assert decision.allowed is True
    assert result == "ok"
    assert isinstance(received_token, task_executor.AdmissionToken)
    assert received_token.task_id == "task-token"


def test_execute_task_requires_admission_token():
    task = _noop_task("missing-token")
    auth = AuthorizationRecord(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="tester",
        intent_hash="i",
        context_hash="c",
        policy_version="v1",
        decision=Decision.ALLOW,
        reason=ReasonCode.OK,
        timestamp=0.0,
        metadata=None,
    )

    with pytest.raises(task_executor.AuthorizationError):
        task_executor.execute_task(task, authorization=auth)

    with pytest.raises(task_executor.AuthorizationError):
        task_executor.execute_task(
            task,
            authorization=auth,
            admission_token=task_executor.AdmissionToken(
                task_id="wrong",
                provenance=_provenance("wrong"),
                request_fingerprint=task_executor.RequestFingerprint("f" * 64),
            ),
        )
