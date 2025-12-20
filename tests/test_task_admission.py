from __future__ import annotations

import pytest

from control_plane import AdmissionResponse, Decision, ReasonCode, RequestType, admit_request
from control_plane.records import AuthorizationError
import task_executor


pytestmark = pytest.mark.no_legacy_skip


def _authorize(request_type: RequestType, requester_id: str = "operator", **metadata: object) -> AdmissionResponse:
    meta = metadata or None
    return admit_request(
        request_type=request_type,
        requester_id=requester_id,
        intent_hash="intent-123",
        context_hash="ctx-123",
        policy_version="v1-static",
        metadata=meta,
    )


def test_control_plane_allows_task_execution() -> None:
    response = _authorize(RequestType.TASK_EXECUTION, requester_id="codex")

    assert response.decision is Decision.ALLOW
    assert response.reason is ReasonCode.OK
    assert response.record.policy_version == "v1-static"


def test_control_plane_denies_self_authorization() -> None:
    response = _authorize(RequestType.TASK_EXECUTION, requester_id="control_plane")

    assert response.decision is Decision.DENY
    assert response.reason is ReasonCode.SELF_AUTH_FORBIDDEN


def test_control_plane_blocks_recursion() -> None:
    response = _authorize(
        RequestType.TASK_EXECUTION,
        requester_id="operator",
        parent_request_type=RequestType.TASK_EXECUTION.value,
    )

    assert response.decision is Decision.DENY
    assert response.reason is ReasonCode.RECURSION_BLOCKED


def test_denies_unauthorized_speech_without_human() -> None:
    response = _authorize(RequestType.SPEECH_TTS, requester_id="intruder")

    assert response.decision is Decision.DENY
    assert response.reason is ReasonCode.UNAUTHORIZED_REQUESTER


def test_avatar_emission_requires_human_approval() -> None:
    denied = _authorize(RequestType.AVATAR_EMISSION, requester_id="bridge")
    assert denied.decision is Decision.DENY
    assert denied.reason is ReasonCode.HUMAN_APPROVAL_REQUIRED

    allowed = _authorize(
        RequestType.AVATAR_EMISSION,
        requester_id="bridge",
        approved_by="reviewer-1",
    )
    assert allowed.decision is Decision.ALLOW
    assert allowed.record.requester_id == "bridge"


def test_execution_requires_authorization_record() -> None:
    task = task_executor.Task(
        task_id="unauthorized",
        objective="noop",
        steps=(task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload()),),
    )

    with pytest.raises(AuthorizationError):
        task_executor.execute_task(task, admission_token=task_executor.AdmissionToken(task_id=task.task_id))


def test_execution_rejects_wrong_authorization_type() -> None:
    task = task_executor.Task(
        task_id="wrong-auth",
        objective="noop",
        steps=(task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload()),),
    )
    speech_auth = _authorize(
        RequestType.SPEECH_TTS, requester_id="operator", approved_by="human"
    ).record

    with pytest.raises(AuthorizationError):
        task_executor.execute_task(
            task,
            authorization=speech_auth,
            admission_token=task_executor.AdmissionToken(task_id=task.task_id),
        )
