from __future__ import annotations
import pytest
import inspect
from pathlib import Path
import sentientos.host_local_diagnostic_execution_runtime as runtime


pytestmark = pytest.mark.no_legacy_skip

def test_execution_boundary_is_exact() -> None:
    assert runtime.TARGET_FILES == ("sentientos_local_diagnostic_effect.json", "effect_receipt.json", "postcondition_check.json", "production_audit.json", "rollback_plan.json", "sentientos_local_diagnostic_transaction_ledger.json")
    assert all(value is False for value in runtime.NO_BROAD_AUTHORITY.values())


def test_only_orchestrator_effect_dependency() -> None:
    source = inspect.getsource(runtime)
    assert "run_builtin_runner_transaction_wing" in source
    for forbidden in ("perform_local_diagnostic_effect", "run_local_diagnostic_effect_wing", "run_builtin_local_effect_runner", "write_local_effect_transaction_ledger_artifact", "import subprocess", "import requests"):
        assert forbidden not in source


def test_preflight_path_does_not_call_runner_or_write(tmp_path: Path) -> None:
    calls=[]
    coordinator=runtime.HostLocalDiagnosticExecutionRuntimeCoordinator(lambda **kw: calls.append(kw))
    before=set(tmp_path.iterdir())
    result=coordinator.preflight(execution_source_bundle_root=tmp_path/"missing",expected_source_bundle_digest="sha256:missing",current_snapshot={},current_verification={},execution_time="2026-01-01T00:00:00Z")
    assert result.status.startswith("blocked_")
    assert calls == []
    assert set(tmp_path.iterdir()) == before
