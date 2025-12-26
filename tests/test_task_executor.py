from importlib import reload
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from control_plane import AuthorizationRecord, Decision, ReasonCode, RequestType, admit_request
import task_executor


def _provenance(task_id: str) -> task_executor.AuthorityProvenance:
    return task_executor.AuthorityProvenance(
        authority_source="test-harness",
        authority_scope=f"task:{task_id}",
        authority_context_id="ctx-test",
        authority_reason="test",
    )


def _issue_token(
    task: task_executor.Task,
    auth: AuthorizationRecord,
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

pytestmark = pytest.mark.no_legacy_skip


def setup_module(module: Any) -> None:  # pragma: no cover - pytest hook
    module


def test_step_order_preserved(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)
    steps = [
        task_executor.Step(step_id=2, kind="noop", payload=task_executor.NoopPayload(note="first")),
        task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload(note="second")),
    ]
    task = task_executor.Task(task_id="task-order", objective="preserve order", steps=steps)

    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="codex",
        intent_hash="order-intent",
        context_hash="ctx-1",
        policy_version="v1-static",
    ).record

    token = _issue_token(task, auth)
    result = task_executor.execute_task(task, authorization=auth, admission_token=token)

    assert [trace.step_id for trace in result.trace] == [2, 1]
    assert result.status == "completed"


def test_noop_logs_and_artifacts(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)
    recorded = []

    def fake_append(path, entry, *, emotion="neutral", consent=True):
        recorded.append((path, entry, emotion, consent))

    monkeypatch.setattr(task_executor, "append_json", fake_append)

    task = task_executor.Task(
        task_id="noop-task",
        objective="noop",
        steps=[task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload(note="ok"))],
    )

    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="noop-intent",
        context_hash="ctx-2",
        policy_version="v1-static",
    ).record

    token = _issue_token(task, auth)
    result = task_executor.execute_task(task, authorization=auth, admission_token=token)

    assert result.status == "completed"
    assert result.artifacts["step_1"] == {"note": "ok"}
    assert recorded, "step log was not recorded"
    path, entry, emotion, consent = recorded[0]
    assert path.name.endswith("task_executor.jsonl")
    assert entry == {
        "task_id": "noop-task",
        "step_id": 1,
        "kind": "noop",
        "status": "completed",
        "artifacts": {"note": "ok"},
    }
    assert emotion == "neutral"
    assert consent is True
    task_entries = [entry for _, entry, _, _ in recorded if entry.get("event") == "task_result"]
    assert task_entries == [{"task_id": "noop-task", "event": "task_result", "status": "completed"}]


def test_failure_aborts(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)

    def boom():
        raise RuntimeError("boom")

    steps = [
        task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload()),
        task_executor.Step(step_id=2, kind="python", payload=task_executor.PythonPayload(callable=boom, name="boom")),
        task_executor.Step(step_id=3, kind="noop", payload=task_executor.NoopPayload(note="skipped")),
    ]
    task = task_executor.Task(task_id="fail-task", objective="abort on fail", steps=steps)

    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="fail-intent",
        context_hash="ctx-3",
        policy_version="v1-static",
    ).record

    token = _issue_token(task, auth)
    result = task_executor.execute_task(task, authorization=auth, admission_token=token)

    assert result.status == "failed"
    assert [trace.step_id for trace in result.trace] == [1, 2]
    assert result.trace[-1].status == "failed"
    assert "boom" in (result.trace[-1].error or "")
    assert "step_3" not in result.artifacts
    assert result.epr_report.actions == ()


def test_epr_runs_only_when_allowed(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)
    repaired = {"done": False}
    called = {"step": False}

    def step_action():
        called["step"] = True
        if not repaired["done"]:
            raise RuntimeError("blocked")
        return {}

    def repair_action():
        repaired["done"] = True
        return {}

    task = task_executor.Task(
        task_id="epr-disabled",
        objective="block until repaired",
        steps=(task_executor.Step(step_id=1, kind="python", payload=task_executor.PythonPayload(callable=step_action)),),
        allow_epr=False,
        epr_actions=(
            task_executor.EprAction(
                action_id="repair-step",
                parent_task_id="epr-disabled",
                trigger_step_id=1,
                authority_impact="none",
                reversibility="guaranteed",
                rollback_proof="snapshot",
                external_effects="no",
                handler=repair_action,
            ),
        ),
    )

    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="epr-disabled",
        context_hash="ctx-epr",
        policy_version="v1-static",
    ).record
    token = _issue_token(task, auth)

    with pytest.raises(task_executor.TaskClosureError, match="EPR not permitted"):
        task_executor.execute_task(task, authorization=auth, admission_token=token)

    assert repaired["done"] is False
    assert called["step"] is False


def test_epr_executes_with_guardrails(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)
    repaired = {"done": False}
    events: list[str] = []

    def step_action():
        events.append("step")
        if not repaired["done"]:
            raise RuntimeError("blocked")
        return {"status": "ok"}

    def repair_action():
        events.append("repair")
        repaired["done"] = True
        return {}

    task = task_executor.Task(
        task_id="epr-allowed",
        objective="repair prereq",
        steps=(task_executor.Step(step_id=1, kind="python", payload=task_executor.PythonPayload(callable=step_action)),),
        allow_epr=True,
        epr_actions=(
            task_executor.EprAction(
                action_id="repair-step",
                parent_task_id="epr-allowed",
                trigger_step_id=1,
                authority_impact="none",
                reversibility="guaranteed",
                rollback_proof="snapshot",
                external_effects="no",
                handler=repair_action,
            ),
        ),
    )

    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="epr-allowed",
        context_hash="ctx-epr-allow",
        policy_version="v1-static",
    ).record
    token = _issue_token(task, auth)
    result = task_executor.execute_task(task, authorization=auth, admission_token=token)

    assert result.status == "completed"
    assert repaired["done"] is True
    assert events == ["repair", "step"]
    assert result.epr_report.actions
    assert result.epr_report.net_authority_delta == 0
    assert result.epr_report.artifacts_persisted is False


def test_epr_requires_rollback_proof(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)

    def step_action():
        raise RuntimeError("blocked")

    task = task_executor.Task(
        task_id="epr-missing-proof",
        objective="repair prereq",
        steps=(task_executor.Step(step_id=1, kind="python", payload=task_executor.PythonPayload(callable=step_action)),),
        allow_epr=True,
        epr_actions=(
            task_executor.EprAction(
                action_id="repair-step",
                parent_task_id="epr-missing-proof",
                trigger_step_id=1,
                authority_impact="none",
                reversibility="bounded",
                rollback_proof="none",
                external_effects="no",
            ),
        ),
    )
    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="epr-missing-proof",
        context_hash="ctx-epr-missing",
        policy_version="v1-static",
    ).record
    token = _issue_token(task, auth)
    with pytest.raises(task_executor.TaskClosureError, match="rollback proof required"):
        task_executor.execute_task(task, authorization=auth, admission_token=token)


def test_epr_disallowed_authority_impact(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)

    def step_action():
        raise RuntimeError("blocked")

    task = task_executor.Task(
        task_id="epr-authority",
        objective="repair prereq",
        steps=(task_executor.Step(step_id=1, kind="python", payload=task_executor.PythonPayload(callable=step_action)),),
        allow_epr=True,
        epr_actions=(
            task_executor.EprAction(
                action_id="repair-step",
                parent_task_id="epr-authority",
                trigger_step_id=1,
                authority_impact="local",
                reversibility="guaranteed",
                rollback_proof="snapshot",
                external_effects="no",
            ),
        ),
    )
    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="epr-authority",
        context_hash="ctx-epr-authority",
        policy_version="v1-static",
    ).record
    token = _issue_token(task, auth)
    with pytest.raises(task_executor.EprApprovalRequired) as excinfo:
        task_executor.execute_task(task, authorization=auth, admission_token=token)

    assert excinfo.value.actions
    assert excinfo.value.actions[0].action_id == "repair-step"


def test_epr_rejects_privilege_escalation(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)

    def step_action():
        raise RuntimeError("blocked")

    task = task_executor.Task(
        task_id="epr-privilege",
        objective="repair prereq",
        steps=(task_executor.Step(step_id=1, kind="python", payload=task_executor.PythonPayload(callable=step_action)),),
        allow_epr=True,
        epr_actions=(
            task_executor.EprAction(
                action_id="repair-step",
                parent_task_id="epr-privilege",
                trigger_step_id=1,
                authority_impact="none",
                reversibility="guaranteed",
                rollback_proof="snapshot",
                external_effects="no",
                privilege_escalation=True,
            ),
        ),
    )
    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="epr-privilege",
        context_hash="ctx-epr-privilege",
        policy_version="v1-static",
    ).record
    token = _issue_token(task, auth)
    with pytest.raises(task_executor.TaskClosureError, match="privilege escalation"):
        task_executor.execute_task(task, authorization=auth, admission_token=token)


def test_epr_aggregates_approval_requests(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)

    def step_action():
        raise RuntimeError("blocked")

    task = task_executor.Task(
        task_id="epr-aggregate",
        objective="aggregate approvals",
        steps=(task_executor.Step(step_id=1, kind="python", payload=task_executor.PythonPayload(callable=step_action)),),
        allow_epr=True,
        epr_actions=(
            task_executor.EprAction(
                action_id="repair-alpha",
                parent_task_id="epr-aggregate",
                trigger_step_id=1,
                authority_impact="local",
                reversibility="guaranteed",
                rollback_proof="snapshot",
                external_effects="no",
            ),
            task_executor.EprAction(
                action_id="repair-beta",
                parent_task_id="epr-aggregate",
                trigger_step_id=1,
                authority_impact="local",
                reversibility="guaranteed",
                rollback_proof="snapshot",
                external_effects="no",
            ),
        ),
    )
    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="epr-aggregate",
        context_hash="ctx-epr-aggregate",
        policy_version="v1-static",
    ).record
    token = _issue_token(task, auth)

    with pytest.raises(task_executor.EprApprovalRequired) as excinfo:
        task_executor.execute_task(task, authorization=auth, admission_token=token)

    action_ids = {action.action_id for action in excinfo.value.actions}
    assert action_ids == {"repair-alpha", "repair-beta"}


def test_execution_does_not_run_epr_on_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)
    repairs = {"count": 0}

    def step_action():
        raise RuntimeError("blocked")

    def repair_action():
        repairs["count"] += 1
        return {}

    task = task_executor.Task(
        task_id="epr-no-retry",
        objective="no epr during execution",
        steps=(task_executor.Step(step_id=1, kind="python", payload=task_executor.PythonPayload(callable=step_action)),),
        allow_epr=True,
        epr_actions=(
            task_executor.EprAction(
                action_id="repair-step",
                parent_task_id="epr-no-retry",
                trigger_step_id=1,
                authority_impact="none",
                reversibility="guaranteed",
                rollback_proof="snapshot",
                external_effects="no",
                handler=repair_action,
            ),
        ),
    )
    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="epr-no-retry",
        context_hash="ctx-epr-no-retry",
        policy_version="v1-static",
    ).record
    token = _issue_token(task, auth)
    result = task_executor.execute_task(task, authorization=auth, admission_token=token)

    assert result.status == "failed"
    assert repairs["count"] == 1


def test_closure_failure_blocks_execution(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)
    called = {"step": False}

    def step_action():
        called["step"] = True
        return {}

    task = task_executor.Task(
        task_id="closure-block",
        objective="stop execution on closure failure",
        steps=(task_executor.Step(step_id=1, kind="python", payload=task_executor.PythonPayload(callable=step_action)),),
        allow_epr=True,
        epr_actions=(
            task_executor.EprAction(
                action_id="bad-epr",
                parent_task_id="closure-block",
                trigger_step_id=1,
                authority_impact="none",
                reversibility="guaranteed",
                rollback_proof="snapshot",
                external_effects="yes",
            ),
        ),
    )
    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="closure-block",
        context_hash="ctx-closure-block",
        policy_version="v1-static",
    ).record
    token = _issue_token(task, auth)

    with pytest.raises(task_executor.TaskClosureError, match="external effects"):
        task_executor.execute_task(task, authorization=auth, admission_token=token)

    assert called["step"] is False


def test_deterministic_traces(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)

    steps = [
        task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload(note="a")),
        task_executor.Step(
            step_id=2,
            kind="mesh",
            payload=task_executor.MeshPayload(job="sync", parameters={"alpha": 1}),
            expects=("result",),
        ),
    ]
    task = task_executor.Task(task_id="deterministic", objective="repeatable", steps=steps)

    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="deterministic",
        context_hash="ctx-4",
        policy_version="v1-static",
    ).record
    token = _issue_token(task, auth)
    first = task_executor.execute_task(task, authorization=auth, admission_token=token)
    second = task_executor.execute_task(task, authorization=auth, admission_token=token)

    assert first.trace == second.trace


def test_unknown_prerequisite_blocks_execution(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)
    called = {"step": False, "repair": False}
    recorded: list[dict[str, object]] = []

    def fake_append(path, entry, *, emotion="neutral", consent=True):
        recorded.append(entry)

    def step_action():
        called["step"] = True
        return {}

    def repair_action():
        called["repair"] = True
        return {}

    task = task_executor.Task(
        task_id="unknown-block",
        objective="block on unknown prereq",
        steps=(task_executor.Step(step_id=1, kind="python", payload=task_executor.PythonPayload(callable=step_action)),),
        allow_epr=True,
        epr_actions=(
            task_executor.EprAction(
                action_id="repair-step",
                parent_task_id="unknown-block",
                trigger_step_id=1,
                authority_impact="none",
                reversibility="guaranteed",
                rollback_proof="snapshot",
                external_effects="no",
                handler=repair_action,
                unknown_prerequisite=task_executor.UnknownPrerequisite(
                    condition="GPU feature Z support",
                    reason="hardware manifest not provided",
                    unblock_query="Confirm whether GPU supports feature Z required by the task.",
                ),
            ),
        ),
    )

    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="unknown-block",
        context_hash="ctx-unknown-block",
        policy_version="v1-static",
    ).record
    token = _issue_token(task, auth)
    monkeypatch.setattr(task_executor, "append_json", fake_append)

    with pytest.raises(task_executor.UnknownPrerequisiteError) as excinfo:
        task_executor.execute_task(task, authorization=auth, admission_token=token)

    assert called["step"] is False
    assert called["repair"] is False
    assert excinfo.value.unblock_query == "Confirm whether GPU supports feature Z required by the task."
    assert any(assessment.status == "unknown" for assessment in excinfo.value.assessments)
    unknown_entries = [entry for entry in recorded if entry.get("event") == "unknown_prerequisite"]
    assert len(unknown_entries) == 1
    assert unknown_entries[0]["unblock_query"] == excinfo.value.unblock_query


def test_unknown_prerequisite_resolution_allows_execution(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)
    called = {"step": False}

    def step_action():
        called["step"] = True
        return {"status": "ok"}

    task = task_executor.Task(
        task_id="unknown-resolved",
        objective="resume after operator response",
        steps=(task_executor.Step(step_id=1, kind="python", payload=task_executor.PythonPayload(callable=step_action)),),
        allow_epr=True,
        epr_actions=(
            task_executor.EprAction(
                action_id="repair-step",
                parent_task_id="unknown-resolved",
                trigger_step_id=1,
                authority_impact="none",
                reversibility="guaranteed",
                rollback_proof="snapshot",
                external_effects="no",
                unknown_prerequisite=task_executor.UnknownPrerequisite(
                    condition="GPU feature Z support",
                    reason="hardware manifest not provided",
                    response="Operator confirmed GPU feature Z support.",
                    resolved_status="satisfied",
                ),
            ),
        ),
    )

    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="unknown-resolved",
        context_hash="ctx-unknown-resolved",
        policy_version="v1-static",
    ).record
    token = _issue_token(task, auth)
    result = task_executor.execute_task(task, authorization=auth, admission_token=token)

    assert result.status == "completed"
    assert called["step"] is True


def test_unknown_prerequisite_refuses_guess(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)
    called = {"step": False}

    def step_action():
        called["step"] = True
        return {}

    task = task_executor.Task(
        task_id="unknown-guess",
        objective="avoid guessing",
        steps=(task_executor.Step(step_id=1, kind="python", payload=task_executor.PythonPayload(callable=step_action)),),
        allow_epr=True,
        epr_actions=(
            task_executor.EprAction(
                action_id="repair-step",
                parent_task_id="unknown-guess",
                trigger_step_id=1,
                authority_impact="none",
                reversibility="guaranteed",
                rollback_proof="snapshot",
                external_effects="no",
                unknown_prerequisite=task_executor.UnknownPrerequisite(
                    condition="GPU feature Z support",
                    reason="model name suggests support but cannot be confirmed",
                ),
            ),
        ),
    )

    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="unknown-guess",
        context_hash="ctx-unknown-guess",
        policy_version="v1-static",
    ).record
    token = _issue_token(task, auth)

    with pytest.raises(task_executor.UnknownPrerequisiteError):
        task_executor.execute_task(task, authorization=auth, admission_token=token)

    assert called["step"] is False


def test_epr_exhaustion_halts_execution_and_logs_once(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("SENTIENTOS_MAX_CLOSURE_ITERATIONS", "2")
    monkeypatch.setenv("SENTIENTOS_MAX_EPR_ACTIONS_PER_TASK", "2")
    reload(task_executor)
    called = {"step": False, "repair": 0}

    def repair_action():
        called["repair"] += 1
        return {"closure_changed": False}

    def fail_run_step(step):
        called["step"] = True
        raise AssertionError("step execution should not start after exhaustion")

    task = task_executor.Task(
        task_id="epr-exhaust",
        objective="detect non-converging repair",
        steps=(task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload()),),
        allow_epr=True,
        epr_actions=(
            task_executor.EprAction(
                action_id="repair-step",
                parent_task_id="epr-exhaust",
                trigger_step_id=1,
                authority_impact="none",
                reversibility="guaranteed",
                rollback_proof="snapshot",
                external_effects="no",
                handler=repair_action,
            ),
        ),
    )

    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="epr-exhaust",
        context_hash="ctx-epr-exhaust",
        policy_version="v1-static",
    ).record
    token = _issue_token(task, auth)
    monkeypatch.setattr(task_executor, "_run_step", fail_run_step)

    with pytest.raises(task_executor.TaskExhausted) as excinfo:
        task_executor.execute_task(task, authorization=auth, admission_token=token)

    assert called["step"] is False
    assert called["repair"] == 1
    assert excinfo.value.report.exhaustion_type == "epr_exhausted"
    entries = [json.loads(line) for line in Path(task_executor.LOG_PATH).read_text().splitlines()]
    exhaustion_entries = [entry for entry in entries if entry.get("event") == "exhaustion"]
    assert len(exhaustion_entries) == 1


def test_unknown_prerequisite_cycles_exhaust(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("SENTIENTOS_MAX_UNKNOWN_RESOLUTION_CYCLES", "0")
    reload(task_executor)
    called = {"step": False}

    def step_action():
        called["step"] = True
        return {}

    task = task_executor.Task(
        task_id="unknown-exhaust",
        objective="detect unknown cycles",
        steps=(task_executor.Step(step_id=1, kind="python", payload=task_executor.PythonPayload(callable=step_action)),),
        allow_epr=True,
        epr_actions=(
            task_executor.EprAction(
                action_id="repair-step",
                parent_task_id="unknown-exhaust",
                trigger_step_id=1,
                authority_impact="none",
                reversibility="guaranteed",
                rollback_proof="snapshot",
                external_effects="no",
                unknown_prerequisite=task_executor.UnknownPrerequisite(
                    condition="GPU feature Z support",
                    reason="hardware manifest not provided",
                    unblock_query="Confirm GPU support.",
                ),
            ),
        ),
    )

    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="unknown-exhaust",
        context_hash="ctx-unknown-exhaust",
        policy_version="v1-static",
    ).record
    token = _issue_token(task, auth)

    with pytest.raises(task_executor.TaskExhausted) as excinfo:
        task_executor.execute_task(task, authorization=auth, admission_token=token)

    assert called["step"] is False
    assert excinfo.value.report.exhaustion_type == "closure_exhausted"
    assert "unknown_prerequisite_cycles_exceeded" in excinfo.value.report.cycle_evidence


def test_operator_input_resets_exhaustion(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("SENTIENTOS_MAX_UNKNOWN_RESOLUTION_CYCLES", "0")
    reload(task_executor)
    called = {"step": False}

    def step_action():
        called["step"] = True
        return {}

    task = task_executor.Task(
        task_id="unknown-reset",
        objective="reset after operator input",
        steps=(task_executor.Step(step_id=1, kind="python", payload=task_executor.PythonPayload(callable=step_action)),),
        allow_epr=True,
        epr_actions=(
            task_executor.EprAction(
                action_id="repair-step",
                parent_task_id="unknown-reset",
                trigger_step_id=1,
                authority_impact="none",
                reversibility="guaranteed",
                rollback_proof="snapshot",
                external_effects="no",
                unknown_prerequisite=task_executor.UnknownPrerequisite(
                    condition="GPU feature Z support",
                    reason="hardware manifest not provided",
                    unblock_query="Confirm GPU support.",
                ),
            ),
        ),
    )

    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="unknown-reset",
        context_hash="ctx-unknown-reset",
        policy_version="v1-static",
    ).record
    token = _issue_token(task, auth)

    with pytest.raises(task_executor.TaskExhausted):
        task_executor.execute_task(task, authorization=auth, admission_token=token)

    resolved_task = task_executor.Task(
        task_id="unknown-reset",
        objective="reset after operator input",
        steps=(task_executor.Step(step_id=1, kind="python", payload=task_executor.PythonPayload(callable=step_action)),),
        allow_epr=True,
        epr_actions=(
            task_executor.EprAction(
                action_id="repair-step",
                parent_task_id="unknown-reset",
                trigger_step_id=1,
                authority_impact="none",
                reversibility="guaranteed",
                rollback_proof="snapshot",
                external_effects="no",
                unknown_prerequisite=task_executor.UnknownPrerequisite(
                    condition="GPU feature Z support",
                    reason="hardware manifest not provided",
                    response="Operator confirmed support.",
                    resolved_status="satisfied",
                ),
            ),
        ),
    )

    result = task_executor.execute_task(resolved_task, authorization=auth, admission_token=_issue_token(resolved_task, auth))

    assert result.status == "completed"
    assert called["step"] is True


def test_exhaustion_stops_before_almost_converging(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("SENTIENTOS_MAX_CLOSURE_ITERATIONS", "1")
    reload(task_executor)
    assessments = {"count": 0}

    def step_action():
        return {}

    def assess_prerequisite(task, action):
        assessments["count"] += 1
        if assessments["count"] == 1:
            return task_executor.PrerequisiteAssessment(
                action_id=action.action_id,
                status="epr-fixable",
                reason="requires one more cycle",
            )
        return task_executor.PrerequisiteAssessment(
            action_id=action.action_id,
            status="satisfied",
            reason="operator provided last detail",
        )

    task = task_executor.Task(
        task_id="almost-converge",
        objective="stop at limit",
        steps=(task_executor.Step(step_id=1, kind="python", payload=task_executor.PythonPayload(callable=step_action)),),
        allow_epr=True,
        epr_actions=(
            task_executor.EprAction(
                action_id="repair-step",
                parent_task_id="almost-converge",
                trigger_step_id=1,
                authority_impact="none",
                reversibility="guaranteed",
                rollback_proof="snapshot",
                external_effects="no",
            ),
        ),
    )

    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="almost-converge",
        context_hash="ctx-almost-converge",
        policy_version="v1-static",
    ).record
    token = _issue_token(task, auth)
    monkeypatch.setattr(task_executor, "_assess_prerequisite", assess_prerequisite)

    with pytest.raises(task_executor.TaskExhausted) as excinfo:
        task_executor.execute_task(task, authorization=auth, admission_token=token)

    assert excinfo.value.report.exhaustion_type == "closure_exhausted"
    assert assessments["count"] == 1


def test_admission_token_requires_provenance(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)
    task = task_executor.Task(
        task_id="missing-prov",
        objective="noop",
        steps=(task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload()),),
    )
    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="prov-intent",
        context_hash="prov-ctx",
        policy_version="v1-static",
    ).record
    bad_token = task_executor.AdmissionToken(
        task_id=task.task_id, provenance=None, request_fingerprint=task_executor.RequestFingerprint("f" * 64)
    )  # type: ignore[arg-type]

    with pytest.raises(task_executor.AuthorizationError):
        task_executor.execute_task(task, authorization=auth, admission_token=bad_token)


def test_execute_task_requires_authorization(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)
    task = task_executor.Task(
        task_id="missing-auth",
        objective="noop",
        steps=(task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload()),),
    )
    token = task_executor.AdmissionToken(
        task_id=task.task_id,
        provenance=_provenance(task.task_id),
        request_fingerprint=task_executor.RequestFingerprint("f" * 64),
    )

    with pytest.raises(task_executor.AuthorizationError, match=ReasonCode.MISSING_AUTHORIZATION.value):
        task_executor.execute_task(task, admission_token=token)


def test_execute_task_rejects_denied_authorization(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)
    task = task_executor.Task(
        task_id="denied-auth",
        objective="noop",
        steps=(task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload()),),
    )
    auth = AuthorizationRecord(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="tester",
        intent_hash="i",
        context_hash="c",
        policy_version="v1",
        decision=Decision.DENY,
        reason=ReasonCode.MISSING_AUTHORIZATION,
        timestamp=0.0,
        metadata=None,
    )
    token = _issue_token(task, auth)

    with pytest.raises(task_executor.AuthorizationError, match="not allowed"):
        task_executor.execute_task(task, authorization=auth, admission_token=token)


def test_request_fingerprint_mismatch_blocks_execution(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)
    task = task_executor.Task(
        task_id="fingerprint-mismatch",
        objective="noop",
        steps=(task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload()),),
    )
    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="fp-intent",
        context_hash="fp-ctx",
        policy_version="v1-static",
    ).record
    token = _issue_token(task, auth, declared_inputs={"alpha": "one"})

    with pytest.raises(task_executor.RequestFingerprintMismatchError):
        task_executor.execute_task(
            task,
            authorization=auth,
            admission_token=token,
            declared_inputs={"alpha": "two"},
        )


def test_task_snapshot_roundtrip_preserves_provenance(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)
    task = task_executor.Task(
        task_id="snapshot-task",
        objective="noop",
        steps=(task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload()),),
    )
    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="snap-intent",
        context_hash="snap-ctx",
        policy_version="v1-static",
    ).record
    token = _issue_token(task, auth)
    result = task_executor.execute_task(task, authorization=auth, admission_token=token)

    record = task_executor.build_task_execution_record(
        task=task, result=result, admission_token=token, authorization=auth
    )
    loaded = task_executor.load_task_execution_record(
        {
            "snapshot": {**record["snapshot"], "diagnostic": "ignore"},
            "digest": record["digest"],
        }
    )

    assert loaded["admission_token"]["provenance"]["authority_source"] == "test-harness"
    assert loaded["authorization"]["policy_version"] == "v1-static"
    assert loaded["result"]["status"] == "completed"


def test_task_snapshot_requires_digest(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)
    task = task_executor.Task(
        task_id="snapshot-missing-digest",
        objective="noop",
        steps=(task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload()),),
    )
    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="snap-missing",
        context_hash="snap-missing",
        policy_version="v1-static",
    ).record
    token = _issue_token(task, auth)
    result = task_executor.execute_task(task, authorization=auth, admission_token=token)
    record = task_executor.build_task_execution_record(
        task=task, result=result, admission_token=token, authorization=auth
    )

    with pytest.raises(task_executor.SnapshotDivergenceError, match="missing digest"):
        task_executor.load_task_execution_record({"snapshot": record["snapshot"]})


def test_task_snapshot_rejects_failed_result(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)

    def boom():
        raise RuntimeError("boom")

    task = task_executor.Task(
        task_id="failed-snapshot",
        objective="should-fail",
        steps=(
            task_executor.Step(step_id=1, kind="python", payload=task_executor.PythonPayload(callable=boom)),
        ),
    )
    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="fail-snap",
        context_hash="fail-snap",
        policy_version="v1-static",
    ).record
    token = _issue_token(task, auth)
    result = task_executor.execute_task(task, authorization=auth, admission_token=token)

    with pytest.raises(task_executor.SnapshotDivergenceError, match="did not complete"):
        task_executor.build_task_execution_record(
            task=task, result=result, admission_token=token, authorization=auth
        )


def test_task_snapshot_ignores_authorization_timestamps(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)
    task = task_executor.Task(
        task_id="snapshot-ignore-timestamp",
        objective="noop",
        steps=(task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload()),),
    )
    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="snap-time",
        context_hash="snap-time",
        policy_version="v1-static",
    ).record
    token = _issue_token(task, auth)
    result = task_executor.execute_task(task, authorization=auth, admission_token=token)
    record = task_executor.build_task_execution_record(
        task=task, result=result, admission_token=token, authorization=auth
    )
    snapshot = dict(record["snapshot"])
    snapshot["authorization"] = dict(snapshot["authorization"], timestamp="2025-01-01T00:00:00Z")

    loaded = task_executor.load_task_execution_record({"snapshot": snapshot, "digest": record["digest"]})

    assert loaded["authorization"] == record["snapshot"]["authorization"]


def test_task_snapshot_detects_provenance_tampering(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)
    task = task_executor.Task(
        task_id="tamper-task",
        objective="noop",
        steps=(task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload()),),
    )
    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="tamper-intent",
        context_hash="tamper-ctx",
        policy_version="v1-static",
    ).record
    token = _issue_token(task, auth)
    result = task_executor.execute_task(task, authorization=auth, admission_token=token)
    record = task_executor.build_task_execution_record(
        task=task, result=result, admission_token=token, authorization=auth
    )
    tampered = record.copy()
    tampered_snapshot = dict(tampered["snapshot"])
    tampered_snapshot["admission_token"] = dict(tampered_snapshot["admission_token"])
    tampered_snapshot["admission_token"]["provenance"] = dict(
        tampered_snapshot["admission_token"]["provenance"], authority_scope="tampered"
    )
    tampered["snapshot"] = tampered_snapshot

    with pytest.raises(task_executor.SnapshotDivergenceError, match="provenance mismatch"):
        task_executor.load_task_execution_record(tampered)


def test_request_fingerprint_captured_in_result(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)
    task = task_executor.Task(
        task_id="fingerprint-capture",
        objective="noop",
        constraints=("a", "b"),
        steps=(task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload()),),
    )
    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="fingerprint",
        context_hash="ctx-6",
        policy_version="v1-static",
    ).record
    token = _issue_token(task, auth)

    result = task_executor.execute_task(task, authorization=auth, admission_token=token)

    assert result.request_fingerprint.value == token.request_fingerprint.value
    assert result.canonical_request["declared_inputs"] == {}
    assert result.canonical_request["task"]["constraints"] == ["a", "b"]


def test_dispatch_step_requires_matching_payload(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)
    step = task_executor.Step(step_id=1, kind="shell", payload=task_executor.NoopPayload())

    with pytest.raises(task_executor.StepExecutionError, match="payload must be ShellPayload"):
        task_executor._dispatch_step(step)


def test_request_fingerprint_detects_post_admission_mutation(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)
    task = task_executor.Task(
        task_id="tamper-after-admission",
        objective="noop",
        steps=(task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload()),),
    )
    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="mutate",
        context_hash="ctx-7",
        policy_version="v1-static",
    ).record
    token = _issue_token(task, auth)
    tampered = task_executor.Task(
        task_id=task.task_id,
        objective="noop but different",
        steps=task.steps,
        constraints=task.constraints,
    )

    with pytest.raises(task_executor.RequestFingerprintMismatchError):
        task_executor.execute_task(tampered, authorization=auth, admission_token=token)


def test_request_fingerprint_ignores_constraint_order(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)
    task = task_executor.Task(
        task_id="noise-tolerant",
        objective="noop",
        constraints=("second", "first"),
        steps=(task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload()),),
    )
    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="noise",
        context_hash="ctx-8",
        policy_version="v1-static",
    ).record
    token = _issue_token(task, auth)
    reordered = task_executor.Task(
        task_id=task.task_id,
        objective="noop",
        constraints=("first", "second"),
        steps=task.steps,
    )

    result = task_executor.execute_task(reordered, authorization=auth, admission_token=token)

    assert result.status == "completed"
    assert result.request_fingerprint.value == token.request_fingerprint.value


def test_request_fingerprint_blocks_input_smuggling(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)
    task = task_executor.Task(
        task_id="smuggle",
        objective="noop",
        steps=(task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload()),),
    )
    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="smuggle-intent",
        context_hash="ctx-9",
        policy_version="v1-static",
    ).record
    token = _issue_token(task, auth, declared_inputs={"files": ["a.txt"]})

    with pytest.raises(task_executor.RequestFingerprintMismatchError):
        task_executor.execute_task(
            task,
            authorization=auth,
            admission_token=token,
            declared_inputs={"files": ["a.txt"], "env": {"SECRET": "1"}},
        )


def test_canonical_request_rejects_gradient_fields():
    task = task_executor.Task(
        task_id="gradient-reject",
        objective="noop",
        steps=(task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload()),),
    )
    provenance = _provenance(task.task_id)
    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="gradient-intent",
        context_hash="ctx-10",
        policy_version="v1-static",
    ).record

    with pytest.raises(task_executor.RequestCanonicalizationError):
        task_executor.canonicalise_task_request(
            task=task,
            authorization=auth,
            provenance=provenance,
            declared_inputs={"reward": 1},
        )
