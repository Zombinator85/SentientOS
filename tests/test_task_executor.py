from importlib import reload
from typing import Any

import pytest

from control_plane import RequestType, admit_request
import task_executor

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

    result = task_executor.execute_task(task, authorization=auth)

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

    result = task_executor.execute_task(task, authorization=auth)

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

    result = task_executor.execute_task(task, authorization=auth)

    assert result.status == "failed"
    assert [trace.step_id for trace in result.trace] == [1, 2]
    assert result.trace[-1].status == "failed"
    assert "boom" in (result.trace[-1].error or "")
    assert "step_3" not in result.artifacts


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
    first = task_executor.execute_task(task, authorization=auth)
    second = task_executor.execute_task(task, authorization=auth)

    assert first.trace == second.trace
    assert first.artifacts == second.artifacts
