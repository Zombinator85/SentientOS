from __future__ import annotations
import inspect
from pathlib import Path
import sentientos.host_local_diagnostic_execution_source_runtime as runtime

def test_boundary_and_target_are_fixed() -> None:
    assert runtime.BOUNDARY["metadata_only"] is True
    assert runtime.BOUNDARY["source_custody_only"] is True
    assert all(runtime.BOUNDARY[x] is False for x in runtime.FALSE_FLAGS)
    assert runtime.TARGET == {"effect_domain":"diagnostics_local_file_effect","transaction_mode":"diagnostic_write_with_ledger","artifact_name":"sentientos_local_diagnostic_effect.json","force_overwrite":False,"rollback_execution":False}

def test_runtime_has_no_execution_dependency() -> None:
    source=inspect.getsource(runtime)
    for forbidden in ("perform_local_diagnostic_effect", "run_local_diagnostic_effect_wing", "run_builtin_local_effect_runner_wing", "run_builtin_runner_transaction_wing", "import subprocess", "import requests"):
        assert forbidden not in source

def test_target_custody_rejects_repository_and_traversal() -> None:
    _, findings=runtime._path_findings(Path.cwd()/"effect",may_not_exist=True)
    assert "repository_local_path_rejected" in findings
    _, findings=runtime._path_findings("/tmp/a/../b",may_not_exist=True)
    assert "path_traversal_rejected" in findings
