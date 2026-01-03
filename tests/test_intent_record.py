from dataclasses import FrozenInstanceError
from importlib import reload

import pytest

from control_plane import RequestType, admit_request
from policy_digest import policy_digest_reference
import sentientos.intent_record as intent_record
import task_executor

pytestmark = pytest.mark.no_legacy_skip


def test_intent_record_is_immutable_and_deterministic() -> None:
    record = intent_record.build_intent_record(
        intent_type="task_dispatch",
        payload={"task_id": "t-1", "objective": "noop"},
        originating_context="runtime",
    )
    with pytest.raises(FrozenInstanceError):
        record.intent_type = "mutate"  # type: ignore[misc]
    payload = record.canonical_payload()
    assert payload["policy_reference"] == policy_digest_reference()
    assert record.canonical_json() == record.canonical_json()


def test_intent_attribution_is_nonsemantic() -> None:
    record_a = intent_record.build_intent_record(
        intent_type="task_dispatch",
        payload={"task_id": "t-2"},
        originating_context="runtime",
        policy_reference={"policy_id": "alpha", "policy_hash": "hash-a"},
    )
    record_b = intent_record.build_intent_record(
        intent_type="task_dispatch",
        payload={"task_id": "t-2"},
        originating_context="runtime",
        policy_reference={"policy_id": "beta", "policy_hash": "hash-b"},
    )
    assert record_a.intent_id == record_b.intent_id
    assert record_a == record_b


def test_intent_records_are_queryable(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("INTENT_RECORD_LOG", str(tmp_path / "intent_records.jsonl"))
    reload(intent_record)

    record = intent_record.capture_intent_record(
        intent_type="tooling_evaluation",
        payload={"event": {"name": "test"}},
        originating_context="tooling",
    )
    assert record is not None
    entries = intent_record.read_intent_records()
    assert any(entry.get("intent_id") == record.intent_id for entry in entries)


def test_intent_emission_does_not_change_task_execution(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("INTENT_RECORD_LOG", str(tmp_path / "intent_records.jsonl"))
    reload(intent_record)
    reload(task_executor)

    def boom(*_args, **_kwargs) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(intent_record, "append_json", boom)

    task = task_executor.Task(
        task_id="noop",
        objective="noop",
        steps=[task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload(note="ok"))],
    )
    provenance = task_executor.AuthorityProvenance(
        authority_source="test",
        authority_scope="task:noop",
        authority_context_id="ctx-1",
        authority_reason="test",
    )
    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="intent",
        context_hash="ctx",
        policy_version="v1-static",
    ).record
    token = task_executor.AdmissionToken(
        task_id=task.task_id,
        provenance=provenance,
        request_fingerprint=task_executor.request_fingerprint_from_canonical(
            task_executor.canonicalise_task_request(
                task=task,
                authorization=auth,
                provenance=provenance,
            )
        ),
    )
    result = task_executor.execute_task(task, authorization=auth, admission_token=token)
    assert result.status == "completed"
