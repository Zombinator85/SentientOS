from importlib import reload
from pathlib import Path

import pytest

import runtime_mode
import task_admission
import task_executor

pytestmark = pytest.mark.no_legacy_skip


def reload_admission(monkeypatch: pytest.MonkeyPatch, mode: str = "DEFAULT") -> None:
    if mode is None:
        monkeypatch.delenv("SENTIENTOS_MODE", raising=False)
    else:
        monkeypatch.setenv("SENTIENTOS_MODE", mode)
    reload(runtime_mode)
    reload(task_admission)


def make_ctx(
    mode: str = "interactive",
    vow_digest: str | None = None,
    doctrine_digest: str | None = None,
) -> task_admission.AdmissionContext:
    return task_admission.AdmissionContext(
        actor="codex",
        mode=mode,
        node_id="node-a",
        vow_digest=vow_digest,
        doctrine_digest=doctrine_digest,
        now_utc_iso="2024-01-01T00:00:00Z",
    )


def test_allows_noop_by_default():
    task = task_executor.Task(
        task_id="noop-ok",
        objective="noop",
        steps=(task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload()),),
    )
    policy = task_admission.AdmissionPolicy(policy_version="v1")
    decision = task_admission.admit(task, make_ctx(), policy)

    assert decision.allowed is True
    assert decision.reason == "OK"
    assert decision.constraints["step_count"] == 1
    assert decision.redactions is None


def test_denies_excess_steps():
    steps = tuple(
        task_executor.Step(step_id=i, kind="noop", payload=task_executor.NoopPayload()) for i in range(3)
    )
    task = task_executor.Task(task_id="too-many", objective="limit", steps=steps)
    policy = task_admission.AdmissionPolicy(policy_version="v1", max_steps=2)

    decision = task_admission.admit(task, make_ctx(), policy)

    assert decision.allowed is False
    assert decision.reason == "TOO_MANY_STEPS"


def test_denies_mesh_when_disabled():
    steps = (
        task_executor.Step(step_id=1, kind="mesh", payload=task_executor.MeshPayload(job="sync")),
    )
    task = task_executor.Task(task_id="mesh-deny", objective="mesh", steps=steps)
    policy = task_admission.AdmissionPolicy(policy_version="v1", allow_mesh=False)

    decision = task_admission.admit(task, make_ctx(), policy)

    assert decision.allowed is False
    assert decision.reason == "MESH_DISABLED"


def test_denies_shell_in_autonomous_mode():
    steps = (
        task_executor.Step(step_id=1, kind="shell", payload=task_executor.ShellPayload(command="echo hi")),
    )
    task = task_executor.Task(task_id="shell-deny", objective="shell", steps=steps)
    policy = task_admission.AdmissionPolicy(policy_version="v1")

    decision = task_admission.admit(task, make_ctx(mode="autonomous"), policy)

    assert decision.allowed is False
    assert decision.reason == "SHELL_DENIED_IN_AUTONOMOUS"


def test_vow_digest_mismatch():
    steps = (
        task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload()),
    )
    task = task_executor.Task(task_id="vow-mismatch", objective="noop", steps=steps)
    policy = task_admission.AdmissionPolicy(
        policy_version="v1",
        require_vow_digest_match=True,
        expected_vow_digest="expected",
    )

    decision = task_admission.admit(task, make_ctx(vow_digest="different"), policy)

    assert decision.allowed is False
    assert decision.reason == "VOW_DIGEST_MISMATCH"


def test_doctrine_digest_mismatch():
    steps = (
        task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload()),
    )
    task = task_executor.Task(task_id="doctrine-mismatch", objective="noop", steps=steps)
    policy = task_admission.AdmissionPolicy(
        policy_version="v1",
        require_doctrine_digest_match=True,
        expected_doctrine_digest="expected",
    )

    decision = task_admission.admit(task, make_ctx(doctrine_digest="different"), policy)

    assert decision.allowed is False
    assert decision.reason == "DOCTRINE_DIGEST_MISMATCH"


def test_doctrine_digest_mismatch_local_owner_allows(monkeypatch: pytest.MonkeyPatch):
    reload_admission(monkeypatch, "LOCAL_OWNER")
    steps = (
        task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload()),
    )
    task = task_executor.Task(task_id="doctrine-local-owner", objective="noop", steps=steps)
    policy = task_admission.AdmissionPolicy(
        policy_version="v1",
        require_doctrine_digest_match=True,
        expected_doctrine_digest="expected",
    )

    decision = task_admission.admit(task, make_ctx(doctrine_digest="different"), policy)

    assert decision.allowed is True
    assert decision.reason == "OK"
    reload_admission(monkeypatch, "DEFAULT")


def test_decision_is_deterministic():
    task = task_executor.Task(
        task_id="deterministic",
        objective="noop",
        steps=(task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload()),),
    )
    policy = task_admission.AdmissionPolicy(policy_version="v1")
    ctx = make_ctx()

    first = task_admission.admit(task, ctx, policy)
    second = task_admission.admit(task, ctx, policy)

    assert first == second


def test_local_owner_retains_step_guards(monkeypatch: pytest.MonkeyPatch):
    reload_admission(monkeypatch, "LOCAL_OWNER")

    invalid_kind_task = task_executor.Task(
        task_id="invalid-kind",
        objective="bad",
        steps=(task_executor.Step(step_id=1, kind="sql", payload=task_executor.NoopPayload()),),
    )
    policy = task_admission.AdmissionPolicy(policy_version="v1")

    invalid_kind_decision = task_admission.admit(invalid_kind_task, make_ctx(), policy)
    assert invalid_kind_decision.allowed is False
    assert invalid_kind_decision.reason == "DENIED_STEP_KIND"

    too_many_steps = tuple(
        task_executor.Step(step_id=i, kind="noop", payload=task_executor.NoopPayload()) for i in range(3)
    )
    limit_task = task_executor.Task(task_id="too-many-local", objective="noop", steps=too_many_steps)
    limited_policy = task_admission.AdmissionPolicy(policy_version="v1", max_steps=2)

    limit_decision = task_admission.admit(limit_task, make_ctx(), limited_policy)
    assert limit_decision.allowed is False
    assert limit_decision.reason == "TOO_MANY_STEPS"

    reload_admission(monkeypatch, "DEFAULT")


def test_wrapper_blocks_and_allows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    reload(task_executor)

    recorded: list[dict[str, object]] = []

    def fake_append(path, entry, *, emotion="neutral", consent=True):
        recorded.append(entry)

    monkeypatch.setattr(task_admission, "append_json", fake_append)
    monkeypatch.setattr(task_executor, "append_json", fake_append)

    deny_task = task_executor.Task(
        task_id="deny-shell",
        objective="shell",
        steps=(task_executor.Step(step_id=1, kind="shell", payload=task_executor.ShellPayload(command="echo")),),
    )

    deny_decision, deny_result = task_admission.run_task_with_admission(
        deny_task,
        make_ctx(mode="autonomous"),
        task_admission.AdmissionPolicy(policy_version="v1"),
        executor=task_executor,
    )

    assert deny_decision.allowed is False
    assert deny_result is None
    assert recorded[0]["event"] == "TASK_ADMISSION_DENIED"
    assert len(recorded) == 1

    recorded.clear()

    allow_task = task_executor.Task(
        task_id="allow-noop",
        objective="noop",
        steps=(task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload()),),
    )

    allow_decision, allow_result = task_admission.run_task_with_admission(
        allow_task,
        make_ctx(),
        task_admission.AdmissionPolicy(policy_version="v1"),
        executor=task_executor,
    )

    assert allow_decision.allowed is True
    assert allow_result is not None
    assert allow_result.status == "completed"
    assert recorded[0]["event"] == "TASK_ADMITTED"
    assert recorded[1]["step_id"] == 1
