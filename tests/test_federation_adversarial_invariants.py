from __future__ import annotations

import base64
import importlib
import importlib.abc
import importlib.util
import sys
from dataclasses import asdict
from pathlib import Path
from types import ModuleType
from typing import Iterable

import pytest

from control_plane import RequestType, admit_request
from sentientos.federation import enablement as federation_enablement
import task_executor

pytestmark = pytest.mark.no_legacy_skip

ALLOWED_CORE_FEDERATION_IMPORTS = {
    "sentientos.federation",
    "sentientos.federation.enablement",
}
FEDERATION_PREFIXES = ("sentientos.federation", "federation")


class _FederationImportBlocker(importlib.abc.MetaPathFinder):
    def __init__(self, allowed: set[str]) -> None:
        self._allowed = allowed

    def find_spec(self, fullname: str, path, target=None):  # type: ignore[override]
        if fullname in self._allowed:
            return None
        if fullname.startswith(FEDERATION_PREFIXES):
            raise ImportError(f"Federation import blocked: {fullname}")
        return None


class _InjectedModuleLoader(importlib.abc.Loader):
    def __init__(self, source: str) -> None:
        self._source = source

    def create_module(self, spec):  # type: ignore[override]
        return None

    def exec_module(self, module: ModuleType) -> None:
        exec(self._source, module.__dict__)


class _InjectedModuleFinder(importlib.abc.MetaPathFinder):
    def __init__(self, modules: dict[str, importlib.abc.Loader]) -> None:
        self._modules = modules

    def find_spec(self, fullname: str, path, target=None):  # type: ignore[override]
        loader = self._modules.get(fullname)
        if loader is None:
            return None
        return importlib.util.spec_from_loader(fullname, loader)


def _purge_modules(prefixes: Iterable[str]) -> None:
    for module_name in list(sys.modules):
        if module_name.startswith(tuple(prefixes)):
            sys.modules.pop(module_name, None)


def _issue_token(
    task: task_executor.Task,
    auth,
) -> task_executor.AdmissionToken:
    provenance = task_executor.AuthorityProvenance(
        authority_source="test-harness",
        authority_scope=f"task:{task.task_id}",
        authority_context_id="ctx-test",
        authority_reason="test",
    )
    fingerprint = task_executor.request_fingerprint_from_canonical(
        task_executor.canonicalise_task_request(task=task, authorization=auth, provenance=provenance)
    )
    return task_executor.AdmissionToken(
        task_id=task.task_id,
        provenance=provenance,
        request_fingerprint=fingerprint,
    )


def _task(task_id: str) -> task_executor.Task:
    steps = (task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload(note="ok")),)
    return task_executor.Task(task_id=task_id, objective="noop", steps=steps)


def _run_task(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, metadata=None) -> dict[str, object]:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    importlib.reload(task_executor)
    recorded: list[dict] = []

    def fake_append(path, entry, *, emotion="neutral", consent=True):
        recorded.append(entry)

    monkeypatch.setattr(task_executor, "append_json", fake_append)

    task = _task("adversarial-task")
    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="noop-intent",
        context_hash="ctx-2",
        policy_version="v1-static",
        metadata=metadata,
    ).record
    token = _issue_token(task, auth)
    result = task_executor.execute_task(task, authorization=auth, admission_token=token)
    return {
        "status": result.status,
        "artifacts": result.artifacts,
        "trace": [asdict(trace) for trace in result.trace],
        "fingerprint": result.request_fingerprint.value,
        "epr_report": asdict(result.epr_report),
        "logged": recorded,
    }


def _run_exhausted_task(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, metadata=None) -> dict[str, object]:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("SENTIENTOS_MAX_CLOSURE_ITERATIONS", "0")
    importlib.reload(task_executor)

    task = _task("adversarial-exhaust")
    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="exhaust-intent",
        context_hash="ctx-3",
        policy_version="v1-static",
        metadata=metadata,
    ).record
    token = _issue_token(task, auth)

    with pytest.raises(task_executor.TaskExhausted) as excinfo:
        task_executor.execute_task(task, authorization=auth, admission_token=token)
    return asdict(excinfo.value.report)


def test_transitive_federation_imports_are_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    allowed = set(ALLOWED_CORE_FEDERATION_IMPORTS)
    blocker = _FederationImportBlocker(allowed=allowed)
    source = (
        "import sentientos.federation.transport\n"
        "class AdapterExecutionContext:\n    ...\n"
        "def execute_adapter_action(*args, **kwargs):\n    return {}\n"
    )
    finder = _InjectedModuleFinder(
        {"sentientos.external_adapters": _InjectedModuleLoader(source)}
    )
    _purge_modules(["sentientos.external_adapters"])
    sys.meta_path.insert(0, blocker)
    sys.meta_path.insert(0, finder)
    try:
        with pytest.raises(ImportError, match="Federation import blocked: sentientos.federation.transport"):
            importlib.reload(task_executor)
    finally:
        sys.meta_path.remove(finder)
        sys.meta_path.remove(blocker)
        _purge_modules(["sentientos.external_adapters"])
        importlib.reload(task_executor)


def test_executor_ignores_injected_federation_symbol(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    allowed = set(ALLOWED_CORE_FEDERATION_IMPORTS)
    blocker = _FederationImportBlocker(allowed=allowed)
    source = (
        "federation = object()\n"
        "def capture_intent_record(*args, **kwargs):\n    return None\n"
    )
    finder = _InjectedModuleFinder({"sentientos.intent_record": _InjectedModuleLoader(source)})
    _purge_modules(["sentientos.intent_record"])
    sys.meta_path.insert(0, blocker)
    sys.meta_path.insert(0, finder)
    try:
        snapshot = _run_task(monkeypatch, tmp_path, metadata={"note": "ok"})
    finally:
        sys.meta_path.remove(finder)
        sys.meta_path.remove(blocker)
        _purge_modules(["sentientos.intent_record"])
        importlib.reload(task_executor)
    assert snapshot["status"] == "completed"
    assert snapshot["logged"], "expected executor log entries"


def test_smuggled_metadata_does_not_change_fingerprint() -> None:
    task = _task("metadata-smuggle")
    base_auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="intent",
        context_hash="ctx",
        policy_version="v1",
        metadata=None,
    ).record
    smuggled_metadata = {
        "federation_envelope_b64": base64.b64encode(b"env").decode("utf-8"),
        "federation_enabled": True,
        "federation_identity_token": "peer-alpha",
        "handshake_blob": "opaque",
        "wrapper": {"federation": {"node": "alpha"}},
    }
    smuggled_auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="intent",
        context_hash="ctx",
        policy_version="v1",
        metadata=smuggled_metadata,
    ).record
    provenance = task_executor.AuthorityProvenance(
        authority_source="test-harness",
        authority_scope="smuggle",
        authority_context_id="ctx",
        authority_reason="test",
    )

    base_request = task_executor.canonicalise_task_request(
        task=task, authorization=base_auth, provenance=provenance
    )
    smuggled_request = task_executor.canonicalise_task_request(
        task=task, authorization=smuggled_auth, provenance=provenance
    )

    assert base_request == smuggled_request
    assert (
        task_executor.request_fingerprint_from_canonical(base_request).value
        == task_executor.request_fingerprint_from_canonical(smuggled_request).value
    )


def test_executor_outputs_stable_with_federation_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base_snapshot = _run_task(monkeypatch, tmp_path, metadata=None)
    monkeypatch.setenv(federation_enablement.ENABLEMENT_ENV, "true")
    smuggled_snapshot = _run_task(
        monkeypatch,
        tmp_path,
        metadata={"federation_flag": "true", "identity_token": "peer-alpha"},
    )

    assert base_snapshot == smuggled_snapshot


def test_exhaustion_report_stable_with_smuggled_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base_report = _run_exhausted_task(monkeypatch, tmp_path)
    monkeypatch.setenv(federation_enablement.ENABLEMENT_ENV, "true")
    smuggled_report = _run_exhausted_task(
        monkeypatch,
        tmp_path,
        metadata={"federation_flag": "true", "identity_token": "peer-alpha"},
    )

    assert base_report == smuggled_report


def test_contract_blocks_real_federation_artifacts() -> None:
    with pytest.raises(
        federation_enablement.FederationContractViolation,
        match="enablement is disabled",
    ):
        admit_request(
            request_type=RequestType.TASK_EXECUTION,
            requester_id="operator",
            intent_hash="intent",
            context_hash="ctx",
            policy_version="v1",
            metadata={"federation_envelope": "not-allowed"},
        )


def test_legacy_bypass_rejects_outside_pytest_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    removed_pytest = sys.modules.pop("pytest", None)
    try:
        with pytest.raises(
            federation_enablement.FederationContractViolation,
            match="Legacy federation bypass is restricted to tests",
        ):
            with federation_enablement.legacy_federation_bypass("adversarial"):
                pass
    finally:
        if removed_pytest is not None:
            sys.modules["pytest"] = removed_pytest


def test_legacy_bypass_ignores_env_switches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTIENTOS_FEDERATION_LEGACY_BYPASS", "1")
    assert federation_enablement.is_legacy_bypass_active() is False
    with pytest.raises(
        federation_enablement.FederationContractViolation,
        match="enablement is disabled",
    ):
        federation_enablement.assert_federation_contract("adversarial")
