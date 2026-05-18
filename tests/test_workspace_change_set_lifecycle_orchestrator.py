from __future__ import annotations

import inspect
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos import workspace_change_set_lifecycle_orchestrator as orchestrator
from sentientos.workspace_change_set_lifecycle_orchestrator import run_workspace_change_set_lifecycle_orchestration


def _proposal(payload: str = "hello") -> dict[str, object]:
    return {
        "declared_target_count": 1,
        "targets": [
            {
                "target_id": "target-one",
                "relative_target_path": "demo.txt",
                "operation": "create_file",
                "payload_text": payload,
            }
        ],
    }


def test_admit_only_runs_only_admission(tmp_path: Path) -> None:
    wing = run_workspace_change_set_lifecycle_orchestration(_proposal(), mode="admit_only", workspace_root=tmp_path)
    assert wing.result.stages_attempted == ("admission",)
    assert wing.preflight_wing is None
    assert wing.execution_wing is None
    assert wing.verification_wing is None
    assert wing.closure_wing is None
    assert wing.result.stop_reason == "lifecycle_completed_for_requested_mode"


def test_admission_blocked_stops_before_preflight(tmp_path: Path) -> None:
    proposal = {"declared_target_count": 1, "targets": [{"target_id": "bad", "relative_target_path": "*.txt", "operation": "create_file"}]}
    wing = run_workspace_change_set_lifecycle_orchestration(proposal, mode="admit_and_preflight", workspace_root=tmp_path)
    assert wing.result.stop_reason == "admission_blocked"
    assert wing.result.stages_attempted == ("admission",)
    assert wing.preflight_wing is None


def test_admit_and_preflight_stops_after_preflight(tmp_path: Path) -> None:
    wing = run_workspace_change_set_lifecycle_orchestration(_proposal(), mode="admit_and_preflight", workspace_root=tmp_path)
    assert wing.result.stages_attempted == ("admission", "preflight")
    assert wing.result.preflight_status == "workspace_change_set_preflight_passed"
    assert wing.execution_wing is None


def test_preflight_blocked_stops_before_execution(tmp_path: Path) -> None:
    proposal = {
        "declared_target_count": 1,
        "targets": [{"target_id": "target-one", "relative_target_path": "missing/demo.txt", "operation": "create_file", "payload_text": "hello"}],
    }
    wing = run_workspace_change_set_lifecycle_orchestration(proposal, mode="admit_preflight_execute", workspace_root=tmp_path)
    assert wing.result.stop_reason == "preflight_blocked"
    assert wing.execution_wing is None


def test_dry_run_full_lifecycle_does_not_execute_or_verify(tmp_path: Path) -> None:
    wing = run_workspace_change_set_lifecycle_orchestration(_proposal(), mode="dry_run_full_lifecycle", workspace_root=tmp_path)
    assert wing.result.dry_run is True
    assert wing.result.stages_attempted == ("admission", "preflight")
    assert wing.execution_wing is None
    assert wing.verification_wing is None
    assert not (tmp_path / "demo.txt").exists()


def test_full_successful_lifecycle_runs_all_stages(tmp_path: Path) -> None:
    wing = run_workspace_change_set_lifecycle_orchestration(_proposal(), mode="admit_preflight_execute_verify_close", workspace_root=tmp_path)
    assert wing.result.stages_attempted == ("admission", "preflight", "execution", "verification", "closure")
    assert wing.result.execution_status == "workspace_change_set_execution_performed"
    assert wing.result.verification_status == "verified_clean"
    assert wing.result.final_lifecycle_status == "lifecycle_closed_clean"


def test_artifact_writes_are_only_explicit_outputs(tmp_path: Path) -> None:
    admission = tmp_path / "admission.json"
    preflight = tmp_path / "preflight.json"
    orchestration_path = tmp_path / "orchestration.json"
    wing = run_workspace_change_set_lifecycle_orchestration(
        _proposal(),
        mode="admit_and_preflight",
        workspace_root=tmp_path,
        admission_artifact_output_path=admission,
        preflight_artifact_output_path=preflight,
        orchestration_artifact_output_path=orchestration_path,
    )
    assert admission.exists()
    assert preflight.exists()
    assert orchestration_path.exists()
    paths = {record["path"] for record in wing.result.artifact_records}
    assert {str(admission), str(preflight), str(orchestration_path)}.issubset(paths)


def test_orchestrator_source_does_not_directly_call_forbidden_helpers_or_external_paths() -> None:
    source = inspect.getsource(orchestrator)
    assert "run_workspace_file_effect_wing" not in source
    assert "run_workspace_file_rollback_wing" not in source
    assert "file_digest(" not in source
    assert "subprocess." not in source
    assert "os.system" not in source
    assert "requests." not in source
