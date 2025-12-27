from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Iterable

import pytest

from control_plane.enums import Decision, ReasonCode, RequestType
from control_plane.records import AuthorizationRecord
from log_utils import read_json
from sentientos.external_adapters import runtime
from sentientos.external_adapters.base import (
    AdapterActionResult,
    AdapterActionSpec,
    AdapterMetadata,
    AdapterRollbackResult,
)

pytestmark = pytest.mark.no_legacy_skip


def _make_context(
    *,
    source: str = "task",
    required: Iterable[str] = (),
    approved: Iterable[str] = (),
) -> runtime.AdapterExecutionContext:
    auth = AuthorizationRecord.create(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="tester",
        intent_hash="intent",
        context_hash="context",
        policy_version="test-policy",
        decision=Decision.ALLOW,
        reason=ReasonCode.OK,
        metadata=None,
    )
    return runtime.AdapterExecutionContext(
        source=source,
        task_id="task-001" if source == "task" else None,
        routine_id="routine-001" if source == "routine" else None,
        request_fingerprint="fingerprint",
        authorization=auth,
        admission_token=None,
        approved_privileges=tuple(approved),
        required_privileges=tuple(required),
    )


def _read_entries(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return read_json(path)


@pytest.fixture()
def adapter_registry():
    from sentientos.external_adapters import registry

    original = dict(registry._ADAPTERS)
    yield registry
    registry._ADAPTERS.clear()
    registry._ADAPTERS.update(original)


@pytest.fixture()
def adapter_log(monkeypatch, tmp_path):
    log_path = tmp_path / "external_adapter_actions.jsonl"
    monkeypatch.setattr(runtime, "LOG_PATH", log_path)
    return log_path


@dataclass(frozen=True)
class SimpleAdapter:
    executed_count: ClassVar[int] = 0

    metadata = AdapterMetadata(
        adapter_id="simple",
        capabilities=("read",),
        scope="simple",
        external_effects="no",
        reversibility="none",
        requires_privilege=False,
        allow_epr=False,
    )
    action_specs = {
        "ping": AdapterActionSpec(
            action="ping",
            capability="read",
            authority_impact="none",
            external_effects="no",
            reversibility="none",
            requires_privilege=False,
        )
    }

    def probe(self) -> bool:
        return True

    def describe(self) -> AdapterMetadata:
        return self.metadata

    def execute(self, action: str, params: dict[str, object], context) -> AdapterActionResult:
        SimpleAdapter.executed_count += 1
        return AdapterActionResult(action=action, outcome={"ok": True})

    def rollback(self, ref: dict[str, object], context) -> AdapterRollbackResult:
        return AdapterRollbackResult(action=str(ref.get("action", "")), success=True, detail={})


@dataclass(frozen=True)
class MaliciousAdapter:
    executed_count: ClassVar[int] = 0

    metadata = AdapterMetadata(
        adapter_id="malicious",
        capabilities=("exfiltrate",),
        scope="malicious",
        external_effects="yes",
        reversibility="none",
        requires_privilege=True,
        allow_epr=False,
    )
    action_specs = {
        "exfiltrate": AdapterActionSpec(
            action="exfiltrate",
            capability="exfiltrate",
            authority_impact="global",
            external_effects="yes",
            reversibility="none",
            requires_privilege=True,
        )
    }

    def probe(self) -> bool:
        return True

    def describe(self) -> AdapterMetadata:
        return self.metadata

    def execute(self, action: str, params: dict[str, object], context) -> AdapterActionResult:
        MaliciousAdapter.executed_count += 1
        return AdapterActionResult(action=action, outcome={"exfiltrated": True})

    def rollback(self, ref: dict[str, object], context) -> AdapterRollbackResult:
        return AdapterRollbackResult(action=str(ref.get("action", "")), success=False, detail={})


@dataclass(frozen=True)
class CapabilityMismatchAdapter:
    metadata = AdapterMetadata(
        adapter_id="capability_mismatch",
        capabilities=("read",),
        scope="capability-mismatch",
        external_effects="no",
        reversibility="none",
        requires_privilege=False,
        allow_epr=False,
    )
    action_specs = {
        "write": AdapterActionSpec(
            action="write",
            capability="write",
            authority_impact="local",
            external_effects="yes",
            reversibility="bounded",
            requires_privilege=True,
        )
    }

    def probe(self) -> bool:
        return True

    def describe(self) -> AdapterMetadata:
        return self.metadata

    def execute(self, action: str, params: dict[str, object], context) -> AdapterActionResult:
        return AdapterActionResult(action=action, outcome={"ok": True})

    def rollback(self, ref: dict[str, object], context) -> AdapterRollbackResult:
        return AdapterRollbackResult(action=str(ref.get("action", "")), success=True, detail={})


@dataclass(frozen=True)
class PrivilegedAdapter:
    executed_count: ClassVar[int] = 0

    metadata = AdapterMetadata(
        adapter_id="privileged",
        capabilities=("secure",),
        scope="privileged",
        external_effects="yes",
        reversibility="bounded",
        requires_privilege=True,
        allow_epr=False,
    )
    action_specs = {
        "secure": AdapterActionSpec(
            action="secure",
            capability="secure",
            authority_impact="local",
            external_effects="yes",
            reversibility="bounded",
            requires_privilege=True,
        )
    }

    def probe(self) -> bool:
        return True

    def describe(self) -> AdapterMetadata:
        return self.metadata

    def execute(self, action: str, params: dict[str, object], context) -> AdapterActionResult:
        PrivilegedAdapter.executed_count += 1
        return AdapterActionResult(action=action, outcome={"ok": True})

    def rollback(self, ref: dict[str, object], context) -> AdapterRollbackResult:
        return AdapterRollbackResult(action=str(ref.get("action", "")), success=True, detail={})


@dataclass(frozen=True)
class RollbackAdapter:
    rollback_called: ClassVar[int] = 0

    metadata = AdapterMetadata(
        adapter_id="rollback",
        capabilities=("write",),
        scope="rollback",
        external_effects="yes",
        reversibility="bounded",
        requires_privilege=True,
        allow_epr=False,
    )
    action_specs = {
        "write": AdapterActionSpec(
            action="write",
            capability="write",
            authority_impact="local",
            external_effects="yes",
            reversibility="bounded",
            requires_privilege=True,
        )
    }

    def probe(self) -> bool:
        return True

    def describe(self) -> AdapterMetadata:
        return self.metadata

    def execute(self, action: str, params: dict[str, object], context) -> AdapterActionResult:
        return AdapterActionResult(
            action=action,
            outcome={"ok": True},
            rollback_ref={"action": action, "payload": "value"},
        )

    def rollback(self, ref: dict[str, object], context) -> AdapterRollbackResult:
        RollbackAdapter.rollback_called += 1
        return AdapterRollbackResult(action=str(ref.get("action", "")), success=True, detail={"rolled_back": True})


@dataclass(frozen=True)
class RollbackFailureAdapter:
    metadata = AdapterMetadata(
        adapter_id="rollback_failure",
        capabilities=("write",),
        scope="rollback-failure",
        external_effects="yes",
        reversibility="bounded",
        requires_privilege=True,
        allow_epr=False,
    )
    action_specs = {
        "write": AdapterActionSpec(
            action="write",
            capability="write",
            authority_impact="local",
            external_effects="yes",
            reversibility="bounded",
            requires_privilege=True,
        )
    }

    def probe(self) -> bool:
        return True

    def describe(self) -> AdapterMetadata:
        return self.metadata

    def execute(self, action: str, params: dict[str, object], context) -> AdapterActionResult:
        return AdapterActionResult(
            action=action,
            outcome={"ok": True},
            rollback_ref={"action": action, "payload": "value"},
        )

    def rollback(self, ref: dict[str, object], context) -> AdapterRollbackResult:
        return AdapterRollbackResult(action=str(ref.get("action", "")), success=False, detail={"rolled_back": False})


@dataclass(frozen=True)
class EprForbiddenAdapter:
    metadata = AdapterMetadata(
        adapter_id="epr_forbidden",
        capabilities=("read",),
        scope="epr-forbidden",
        external_effects="no",
        reversibility="none",
        requires_privilege=False,
        allow_epr=False,
    )
    action_specs = {
        "ping": AdapterActionSpec(
            action="ping",
            capability="read",
            authority_impact="none",
            external_effects="no",
            reversibility="none",
            requires_privilege=False,
        )
    }

    def probe(self) -> bool:
        return True

    def describe(self) -> AdapterMetadata:
        return self.metadata

    def execute(self, action: str, params: dict[str, object], context) -> AdapterActionResult:
        return AdapterActionResult(action=action, outcome={"ok": True})

    def rollback(self, ref: dict[str, object], context) -> AdapterRollbackResult:
        return AdapterRollbackResult(action=str(ref.get("action", "")), success=True, detail={})


@dataclass(frozen=True)
class EprIrreversibleAdapter:
    metadata = AdapterMetadata(
        adapter_id="epr_irreversible",
        capabilities=("deploy",),
        scope="epr-irreversible",
        external_effects="yes",
        reversibility="none",
        requires_privilege=True,
        allow_epr=True,
    )
    action_specs = {
        "deploy": AdapterActionSpec(
            action="deploy",
            capability="deploy",
            authority_impact="global",
            external_effects="yes",
            reversibility="none",
            requires_privilege=True,
        )
    }

    def probe(self) -> bool:
        return True

    def describe(self) -> AdapterMetadata:
        return self.metadata

    def execute(self, action: str, params: dict[str, object], context) -> AdapterActionResult:
        return AdapterActionResult(action=action, outcome={"ok": True})

    def rollback(self, ref: dict[str, object], context) -> AdapterRollbackResult:
        return AdapterRollbackResult(action=str(ref.get("action", "")), success=True, detail={})


def test_adapter_rejects_invalid_execution_contexts(adapter_registry, adapter_log) -> None:
    adapter_registry.register_adapter("malicious", MaliciousAdapter)
    MaliciousAdapter.executed_count = 0

    invalid_sources = [
        "outside-task",
        "cor",
        "ssu",
        "ois",
        "simulation",
        "proposal",
        "introspection",
        "habit-inference",
    ]

    for source in invalid_sources:
        with pytest.raises(runtime.AdapterExecutionError, match="adapter execution requires task"):
            runtime.execute_adapter_action(
                adapter_id="malicious",
                action="exfiltrate",
                params={},
                context=_make_context(source=source),
            )

    assert MaliciousAdapter.executed_count == 0
    entries = _read_entries(adapter_log)
    assert len(entries) == len(invalid_sources)
    for entry in entries:
        assert entry["success"] is False
        assert "adapter execution requires task" in entry["error"]
        assert entry["adapter_id"] == "malicious"
        assert entry["scope"] == "malicious"
        assert entry["capability"] == "exfiltrate"
        assert entry["context"]["source"] in invalid_sources


def test_adapter_rejects_unsupported_action(adapter_registry, adapter_log) -> None:
    adapter_registry.register_adapter("simple", SimpleAdapter)

    with pytest.raises(runtime.AdapterExecutionError, match="unsupported adapter action"):
        runtime.execute_adapter_action(
            adapter_id="simple",
            action="unknown",
            params={},
            context=_make_context(),
        )

    entries = _read_entries(adapter_log)
    assert entries
    entry = entries[-1]
    assert entry["success"] is False
    assert entry["capability"] == "unknown"
    assert "unsupported adapter action" in entry["error"]


def test_adapter_rejects_capability_mismatch(adapter_registry, adapter_log) -> None:
    adapter_registry.register_adapter("capability_mismatch", CapabilityMismatchAdapter)

    with pytest.raises(runtime.AdapterExecutionError, match="capability not declared"):
        runtime.execute_adapter_action(
            adapter_id="capability_mismatch",
            action="write",
            params={},
            context=_make_context(),
        )

    entries = _read_entries(adapter_log)
    assert entries
    entry = entries[-1]
    assert entry["success"] is False
    assert entry["capability"] == "unknown"
    assert "capability not declared" in entry["error"]


def test_adapter_blocks_scope_escapes(adapter_log, tmp_path) -> None:
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_file = outside_dir / "secret.txt"
    outside_file.write_text("secret", encoding="utf-8")

    with pytest.raises(runtime.AdapterExecutionError, match="escapes adapter scope"):
        runtime.execute_adapter_action(
            adapter_id="filesystem",
            action="read",
            params={"path": "../outside/secret.txt"},
            adapter_config={"base_path": base_dir},
            context=_make_context(),
        )

    with pytest.raises(runtime.AdapterExecutionError, match="escapes adapter scope"):
        runtime.execute_adapter_action(
            adapter_id="filesystem",
            action="write",
            params={"path": "../outside/new.txt", "content": "nope"},
            adapter_config={"base_path": base_dir},
            context=_make_context(
                required=("filesystem:write",),
                approved=("filesystem:write",),
            ),
        )

    assert not (outside_dir / "new.txt").exists()

    link_path = base_dir / "link"
    try:
        link_path.symlink_to(outside_dir, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported on this platform")

    with pytest.raises(runtime.AdapterExecutionError, match="escapes adapter scope"):
        runtime.execute_adapter_action(
            adapter_id="filesystem",
            action="read",
            params={"path": "link/secret.txt"},
            adapter_config={"base_path": base_dir},
            context=_make_context(),
        )

    entries = _read_entries(adapter_log)
    assert entries
    assert all(entry["success"] is False for entry in entries)
    assert all(entry["adapter_id"] == "filesystem" for entry in entries)


def test_adapter_enforces_privilege_declaration(adapter_registry, adapter_log) -> None:
    adapter_registry.register_adapter("privileged", PrivilegedAdapter)
    PrivilegedAdapter.executed_count = 0

    with pytest.raises(runtime.AdapterExecutionError, match="privilege not declared"):
        runtime.execute_adapter_action(
            adapter_id="privileged",
            action="secure",
            params={},
            context=_make_context(approved=("privileged:secure",)),
        )

    with pytest.raises(runtime.AdapterExecutionError, match="privilege not approved"):
        runtime.execute_adapter_action(
            adapter_id="privileged",
            action="secure",
            params={},
            context=_make_context(required=("privileged:secure",)),
        )

    runtime.execute_adapter_action(
        adapter_id="privileged",
        action="secure",
        params={},
        context=_make_context(required=("privileged",), approved=("privileged",)),
    )

    assert PrivilegedAdapter.executed_count == 1
    entries = _read_entries(adapter_log)
    assert entries
    assert entries[-1]["success"] is True


def test_adapter_rollbacks_are_logged(adapter_registry, adapter_log) -> None:
    adapter_registry.register_adapter("rollback", RollbackAdapter)
    RollbackAdapter.rollback_called = 0

    result = runtime.execute_adapter_action(
        adapter_id="rollback",
        action="write",
        params={},
        context=_make_context(required=("rollback:write",), approved=("rollback:write",)),
    )
    rollback_ref = result.rollback_ref
    assert rollback_ref is not None

    rollback_result = runtime.rollback_adapter_action(
        adapter_id="rollback",
        ref=rollback_ref,
        context=_make_context(required=("rollback:write",), approved=("rollback:write",)),
    )

    assert rollback_result.success is True
    assert RollbackAdapter.rollback_called == 1
    entries = _read_entries(adapter_log)
    assert entries
    assert entries[-1]["rollback_status"] == "completed"


def test_adapter_rollback_failure_is_recorded(adapter_registry, adapter_log) -> None:
    adapter_registry.register_adapter("rollback_failure", RollbackFailureAdapter)

    result = runtime.execute_adapter_action(
        adapter_id="rollback_failure",
        action="write",
        params={},
        context=_make_context(required=("rollback_failure:write",), approved=("rollback_failure:write",)),
    )
    rollback_ref = result.rollback_ref
    assert rollback_ref is not None

    rollback_result = runtime.rollback_adapter_action(
        adapter_id="rollback_failure",
        ref=rollback_ref,
        context=_make_context(required=("rollback_failure:write",), approved=("rollback_failure:write",)),
    )

    assert rollback_result.success is False
    entries = _read_entries(adapter_log)
    assert entries
    entry = entries[-1]
    assert entry["rollback_status"] == "failed"
    assert entry["error"] == "rollback_failed"


def test_adapter_epr_restrictions(adapter_registry, adapter_log) -> None:
    adapter_registry.register_adapter("epr_forbidden", EprForbiddenAdapter)
    adapter_registry.register_adapter("epr_irreversible", EprIrreversibleAdapter)

    with pytest.raises(runtime.AdapterExecutionError, match="does not permit EPR"):
        runtime.execute_adapter_action(
            adapter_id="epr_forbidden",
            action="ping",
            params={},
            context=_make_context(source="epr"),
        )

    with pytest.raises(runtime.AdapterExecutionError, match="irreversible external effects"):
        runtime.execute_adapter_action(
            adapter_id="epr_irreversible",
            action="deploy",
            params={},
            context=_make_context(
                source="epr",
                required=("epr_irreversible:deploy",),
                approved=("epr_irreversible:deploy",),
            ),
        )

    entries = _read_entries(adapter_log)
    assert entries
    assert entries[-1]["success"] is False
