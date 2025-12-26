import os

import pytest

from control_plane import policy as control_policy
from control_plane.enums import Decision, ReasonCode, RequestType
from control_plane.records import AuthorizationRecord
from sentientos import system_identity
from task_admission import AdmissionContext, AdmissionPolicy, run_task_with_admission
import task_executor


def _make_authorization() -> AuthorizationRecord:
    return AuthorizationRecord.create(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="intent",
        context_hash="context",
        policy_version="v1-static",
        decision=Decision.ALLOW,
        reason=ReasonCode.OK,
        metadata={},
    )


def _make_context() -> AdmissionContext:
    return AdmissionContext(
        actor="operator",
        mode="manual",
        node_id="node-1",
        vow_digest=None,
        doctrine_digest=None,
        now_utc_iso=None,
    )


def _make_policy() -> AdmissionPolicy:
    return AdmissionPolicy(policy_version="test-policy")


def _make_task(task_id: str, *, action: task_executor.EprAction | None = None) -> task_executor.Task:
    steps = (task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload(note="ok")),)
    epr_actions = (action,) if action else ()
    return task_executor.Task(
        task_id=task_id,
        objective="test",
        steps=steps,
        allow_epr=bool(action),
        epr_actions=epr_actions,
    )


def _make_epr_action(
    task_id: str,
    action_id: str,
    handler,
    *,
    authority_impact: task_executor.EprAuthorityImpact = "none",
    reversibility: task_executor.EprReversibility = "guaranteed",
    rollback_proof: task_executor.EprRollbackProof = "none",
    external_effects: task_executor.EprExternalEffects = "no",
    unknown: task_executor.UnknownPrerequisite | None = None,
) -> task_executor.EprAction:
    return task_executor.EprAction(
        action_id=action_id,
        parent_task_id=task_id,
        trigger_step_id=1,
        authority_impact=authority_impact,
        reversibility=reversibility,
        rollback_proof=rollback_proof,
        external_effects=external_effects,
        handler=handler,
        description="test",
        unknown_prerequisite=unknown,
    )


def _make_admission_token(
    task: task_executor.Task,
    ctx: AdmissionContext,
    policy: AdmissionPolicy,
    authorization: AuthorizationRecord,
) -> task_executor.AdmissionToken:
    provenance = task_executor.AuthorityProvenance(
        authority_source=ctx.actor,
        authority_scope=f"policy:{policy.policy_version}",
        authority_context_id=ctx.node_id,
        authority_reason="OK",
    )
    canonical_request = task_executor.canonicalise_task_request(
        task=task, authorization=authorization, provenance=provenance, declared_inputs=None
    )
    fingerprint = task_executor.request_fingerprint_from_canonical(canonical_request)
    return task_executor.AdmissionToken(
        task_id=task.task_id,
        provenance=provenance,
        request_fingerprint=fingerprint,
    )


def test_replay_equivalence_for_identical_tasks() -> None:
    policy = _make_policy()
    ctx = _make_context()
    authorization = _make_authorization()

    action = _make_epr_action("task-1", "epr-1", handler=lambda: {"closure_changed": True})
    task = _make_task("task-1", action=action)

    _, result_a = run_task_with_admission(
        task, ctx, policy, authorization, declared_inputs={"alpha": "one"}
    )
    _, result_b = run_task_with_admission(
        task, ctx, policy, authorization, declared_inputs={"alpha": "one"}
    )

    snapshot_a = task_executor.canonicalise_task_execution_snapshot(
        task=task,
        result=result_a,
        admission_token=result_a.admission_token,
        authorization=authorization,
        declared_inputs={"alpha": "one"},
    )
    snapshot_b = task_executor.canonicalise_task_execution_snapshot(
        task=task,
        result=result_b,
        admission_token=result_b.admission_token,
        authorization=authorization,
        declared_inputs={"alpha": "one"},
    )
    assert snapshot_a == snapshot_b


def test_identity_digest_stable_through_chained_epr() -> None:
    policy = _make_policy()
    ctx = _make_context()
    authorization = _make_authorization()
    identity_before = system_identity.compute_system_identity_digest(
        admission_policy=policy,
        control_policy=control_policy.load_policy(),
        closure_limits=task_executor.load_closure_limits(),
    )

    first_action = _make_epr_action("task-2", "epr-2", handler=lambda: {"closure_changed": True})
    second_action = _make_epr_action("task-3", "epr-3", handler=lambda: {"closure_changed": True})

    run_task_with_admission(_make_task("task-2", action=first_action), ctx, policy, authorization)
    run_task_with_admission(_make_task("task-3", action=second_action), ctx, policy, authorization)

    identity_after = system_identity.compute_system_identity_digest(
        admission_policy=policy,
        control_policy=control_policy.load_policy(),
        closure_limits=task_executor.load_closure_limits(),
    )
    assert identity_before == identity_after


def test_exhaustion_replay_equivalence() -> None:
    policy = _make_policy()
    ctx = _make_context()
    authorization = _make_authorization()

    action = _make_epr_action("task-4", "epr-4", handler=lambda: {"closure_changed": False})
    task = _make_task("task-4", action=action)
    token = _make_admission_token(task, ctx, policy, authorization)

    with pytest.raises(task_executor.TaskExhausted) as first:
        task_executor.execute_task(task, authorization=authorization, admission_token=token)

    token_replay = _make_admission_token(task, ctx, policy, authorization)
    with pytest.raises(task_executor.TaskExhausted) as second:
        task_executor.execute_task(task, authorization=authorization, admission_token=token_replay)

    assert first.value.report == second.value.report


def test_unknown_resolution_resume_then_exhaust() -> None:
    policy = _make_policy()
    ctx = _make_context()
    authorization = _make_authorization()

    identity_before = system_identity.compute_system_identity_digest(
        admission_policy=policy,
        control_policy=control_policy.load_policy(),
        closure_limits=task_executor.load_closure_limits(),
    )

    unknown = task_executor.UnknownPrerequisite(
        condition="missing input",
        reason="operator must confirm",
        unblock_query=None,
        response=None,
        resolved_status=None,
    )
    action = _make_epr_action("task-5", "epr-5", handler=lambda: {"closure_changed": True}, unknown=unknown)
    task = _make_task("task-5", action=action)
    token = _make_admission_token(task, ctx, policy, authorization)

    with pytest.raises(task_executor.UnknownPrerequisiteError):
        task_executor.execute_task(task, authorization=authorization, admission_token=token)

    resolved_unknown = task_executor.UnknownPrerequisite(
        condition="missing input",
        reason="operator confirmed",
        unblock_query=None,
        response="confirmed",
        resolved_status="epr-fixable",
    )
    exhausted_action = _make_epr_action(
        "task-5",
        "epr-5",
        handler=lambda: {"closure_changed": False},
        unknown=resolved_unknown,
    )
    exhausted_task = _make_task("task-5", action=exhausted_action)
    exhausted_token = _make_admission_token(exhausted_task, ctx, policy, authorization)

    with pytest.raises(task_executor.TaskExhausted):
        task_executor.execute_task(
            exhausted_task,
            authorization=authorization,
            admission_token=exhausted_token,
        )

    identity_after = system_identity.compute_system_identity_digest(
        admission_policy=policy,
        control_policy=control_policy.load_policy(),
        closure_limits=task_executor.load_closure_limits(),
    )
    assert identity_before == identity_after


def test_abort_replay_then_resume() -> None:
    policy = _make_policy()
    ctx = _make_context()
    authorization = _make_authorization()

    identity_before = system_identity.compute_system_identity_digest(
        admission_policy=policy,
        control_policy=control_policy.load_policy(),
        closure_limits=task_executor.load_closure_limits(),
    )

    approval_action = _make_epr_action(
        "task-6",
        "epr-6",
        handler=lambda: {"closure_changed": True},
        authority_impact="local",
    )
    task = _make_task("task-6", action=approval_action)
    token = _make_admission_token(task, ctx, policy, authorization)

    with pytest.raises(task_executor.EprApprovalRequired):
        task_executor.execute_task(task, authorization=authorization, admission_token=token)

    resumed_action = _make_epr_action("task-6", "epr-6", handler=lambda: {"closure_changed": True})
    resumed_task = _make_task("task-6", action=resumed_action)
    resumed_token = _make_admission_token(resumed_task, ctx, policy, authorization)
    task_executor.execute_task(resumed_task, authorization=authorization, admission_token=resumed_token)

    identity_after = system_identity.compute_system_identity_digest(
        admission_policy=policy,
        control_policy=control_policy.load_policy(),
        closure_limits=task_executor.load_closure_limits(),
    )
    assert identity_before == identity_after


def test_drift_detection_classification() -> None:
    policy = _make_policy()
    control = control_policy.load_policy()
    limits = task_executor.load_closure_limits()

    baseline = system_identity.compute_system_identity_digest(
        admission_policy=policy,
        control_policy=control,
        closure_limits=limits,
        metadata={"note": "baseline"},
    )
    benign = system_identity.compute_system_identity_digest(
        admission_policy=policy,
        control_policy=control,
        closure_limits=limits,
        metadata={"note": "updated"},
    )
    report = system_identity.classify_identity_drift(baseline, benign)
    assert report.classification == "benign"

    changed_policy = AdmissionPolicy(policy_version="test-policy", max_steps=policy.max_steps + 1)
    critical = system_identity.compute_system_identity_digest(
        admission_policy=changed_policy,
        control_policy=control,
        closure_limits=limits,
    )
    critical_report = system_identity.classify_identity_drift(baseline, critical)
    assert critical_report.classification == "critical"

    with pytest.raises(system_identity.IdentityDriftError):
        system_identity.enforce_identity_drift(baseline, critical)


def test_critical_drift_halts_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    policy = _make_policy()
    ctx = _make_context()
    authorization = _make_authorization()
    monkeypatch.setenv("SENTIENTOS_MAX_EPR_ACTIONS_PER_TASK", "5")

    action = _make_epr_action("task-7", "epr-7", handler=lambda: {"closure_changed": True})
    task = _make_task("task-7", action=action)

    class DriftExecutor:
        def __init__(self, delegate):
            self._delegate = delegate

        def execute_task(self, *args, **kwargs):
            result = self._delegate.execute_task(*args, **kwargs)
            os.environ["SENTIENTOS_MAX_EPR_ACTIONS_PER_TASK"] = "9"
            return result

    with pytest.raises(system_identity.IdentityDriftError):
        run_task_with_admission(
            task,
            ctx,
            policy,
            authorization,
            executor=DriftExecutor(task_executor),
        )
