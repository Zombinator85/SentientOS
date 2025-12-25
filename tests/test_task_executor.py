from importlib import reload
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
    assert first.artifacts == second.artifacts


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
