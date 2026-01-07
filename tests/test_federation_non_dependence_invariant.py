from __future__ import annotations

import ast
from dataclasses import asdict
import importlib
import importlib.abc
import sys
from pathlib import Path
from typing import Iterable

import pytest

from control_plane import RequestType, admit_request
import task_executor

pytestmark = pytest.mark.no_legacy_skip

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_IMPORT_GUARD_TARGETS = (
    REPO_ROOT / "task_executor.py",
    REPO_ROOT / "policy_engine.py",
    REPO_ROOT / "control_plane" / "records.py",
)
ALLOWED_CORE_FEDERATION_IMPORTS = {
    "sentientos.federation",
    "sentientos.federation.enablement",
}
FEDERATION_PREFIXES = ("sentientos.federation", "federation")


def _iter_imported_modules(tree: ast.AST) -> Iterable[str]:
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def _find_federation_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders = []
    for name in _iter_imported_modules(tree):
        if name.startswith(FEDERATION_PREFIXES):
            offenders.append(name)
    return offenders


class _FederationImportBlocker(importlib.abc.MetaPathFinder):
    def __init__(self, allowed: set[str]) -> None:
        self._allowed = allowed

    def find_spec(self, fullname: str, path, target=None):  # type: ignore[override]
        if fullname in self._allowed:
            return None
        if fullname.startswith("sentientos.federation") or fullname.startswith("federation"):
            raise ImportError(f"Federation import blocked: {fullname}")
        return None


def _purge_federation_modules(allowed: set[str]) -> None:
    for module_name in list(sys.modules):
        if module_name in allowed:
            continue
        if module_name.startswith("sentientos.federation") or module_name.startswith("federation"):
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


def _run_task(monkeypatch, tmp_path, *, metadata=None) -> tuple[dict, list[dict]]:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    importlib.reload(task_executor)
    recorded: list[dict] = []

    def fake_append(path, entry, *, emotion="neutral", consent=True):
        recorded.append(entry)

    monkeypatch.setattr(task_executor, "append_json", fake_append)

    task = task_executor.Task(
        task_id="federation-independent",
        objective="noop",
        steps=(task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload(note="ok")),),
    )
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
    snapshot = {
        "status": result.status,
        "artifacts": result.artifacts,
        "trace": [asdict(trace) for trace in result.trace],
        "fingerprint": result.request_fingerprint.value,
        "epr_report": asdict(result.epr_report),
    }
    return snapshot, recorded


def _run_exhausted_task(monkeypatch, tmp_path) -> tuple[dict, list[dict]]:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("SENTIENTOS_MAX_CLOSURE_ITERATIONS", "0")
    importlib.reload(task_executor)
    recorded: list[dict] = []

    def fake_append(path, entry, *, emotion="neutral", consent=True):
        recorded.append(entry)

    monkeypatch.setattr(task_executor, "append_json", fake_append)

    task = task_executor.Task(
        task_id="federation-exhaustion",
        objective="force exhaustion",
        steps=(task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload()),),
    )
    auth = admit_request(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="exhaust-intent",
        context_hash="ctx-3",
        policy_version="v1-static",
    ).record
    token = _issue_token(task, auth)

    with pytest.raises(task_executor.TaskExhausted) as excinfo:
        task_executor.execute_task(task, authorization=auth, admission_token=token)
    report = excinfo.value.report
    snapshot = asdict(report)
    return snapshot, recorded


def test_core_import_boundary_excludes_federation_dependencies() -> None:
    offenders: dict[str, list[str]] = {}
    for path in CORE_IMPORT_GUARD_TARGETS:
        imports = _find_federation_imports(path)
        violations = [name for name in imports if name not in ALLOWED_CORE_FEDERATION_IMPORTS]
        if violations:
            offenders[path.relative_to(REPO_ROOT).as_posix()] = violations
    assert not offenders, f"core modules must not import federation dependencies: {offenders}"


def test_executor_runs_without_federation_modules(monkeypatch, tmp_path) -> None:
    allowed = set(ALLOWED_CORE_FEDERATION_IMPORTS)
    blocker = _FederationImportBlocker(allowed=allowed)
    _purge_federation_modules(allowed)
    sys.meta_path.insert(0, blocker)
    try:
        snapshot, recorded = _run_task(monkeypatch, tmp_path)
    finally:
        sys.meta_path.remove(blocker)
    assert snapshot["status"] == "completed"
    assert recorded, "executor logs should be recorded without federation"
    loaded = {
        name
        for name in sys.modules
        if name.startswith("sentientos.federation") and name not in allowed
    }
    assert not loaded, f"unexpected federation modules imported: {sorted(loaded)}"


def test_executor_behavior_equivalent_without_federation(monkeypatch, tmp_path) -> None:
    allowed = set(ALLOWED_CORE_FEDERATION_IMPORTS)
    _purge_federation_modules(allowed)
    snapshot_without, recorded_without = _run_task(monkeypatch, tmp_path)

    import sentientos.federation.config  # noqa: F401

    snapshot_with, recorded_with = _run_task(monkeypatch, tmp_path)

    assert snapshot_without == snapshot_with
    assert recorded_without == recorded_with


def test_exhaustion_equivalence_with_federation_present(monkeypatch, tmp_path) -> None:
    allowed = set(ALLOWED_CORE_FEDERATION_IMPORTS)
    _purge_federation_modules(allowed)
    exhausted_without, recorded_without = _run_exhausted_task(monkeypatch, tmp_path)

    import sentientos.federation.config  # noqa: F401

    exhausted_with, recorded_with = _run_exhausted_task(monkeypatch, tmp_path)

    assert exhausted_without == exhausted_with
    assert recorded_without == recorded_with


def test_executor_ignores_absent_federation_metadata(monkeypatch, tmp_path) -> None:
    snapshot_without, _ = _run_task(monkeypatch, tmp_path, metadata=None)
    snapshot_with, _ = _run_task(
        monkeypatch,
        tmp_path,
        metadata={"federation_metadata": None, "note": "absent federation artifacts"},
    )

    assert snapshot_without == snapshot_with
