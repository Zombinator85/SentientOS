from __future__ import annotations

import pytest

from sentientos.codex_validation_matrix_lane_contract import verify_lane_contract

pytestmark = pytest.mark.no_legacy_skip


def _matrix() -> dict[str, object]:
    return {
        "status": "passed",
        "required_failure_count": 0,
        "results": [
            {"label": "targeted_tests", "exit_code": 0},
            {"label": "governed_memory_writer_adapter_tests", "exit_code": 0},
            {"label": "real_memory_root_admission_gate_tests", "exit_code": 0},
            {"label": "real_executor_execution_preflight_gate_tests", "exit_code": 0},
            {"label": "real_executor_execution_lock_lease_packet_tests", "exit_code": 0},
            {"label": "real_executor_execution_lock_lease_gate_tests", "exit_code": 0},
            {"label": "real_executor_execution_commit_plan_packet_tests", "exit_code": 0},
            {"label": "real_executor_execution_commit_plan_gate_tests", "exit_code": 0},
            {"label": "real_executor_execution_commit_window_packet_tests", "exit_code": 0},
            {"label": "real_live_memory_commit_execution_gate_tests", "exit_code": 0},
            {"label": "real_live_memory_commit_execution_packet_tests", "exit_code": 0},
            {"label": "real_live_memory_commit_adapter_admission_gate_tests", "exit_code": 0},
            {"label": "real_live_memory_commit_adapter_admission_packet_tests", "exit_code": 0},
            {"label": "real_live_memory_commit_adapter_readiness_gate_tests", "exit_code": 0},
            {"label": "phase97_external_security_review_packet_tests", "exit_code": 0},
            {"label": "phase98_external_audit_export_receipt_tests", "exit_code": 0},
            {"label": "phase99_invocation_denial_attestation_tests", "exit_code": 0},
            {"label": "phase100_invocation_denial_closure_tests", "exit_code": 0},
            {"label": "phase101_invocation_denial_enforcement_tests", "exit_code": 0},
            {"label": "phase102_invocation_denial_drift_review_tests", "exit_code": 0},
            {"label": "phase103_invocation_denial_custody_checkpoint_tests", "exit_code": 0},
            {"label": "targeted_mypy", "exit_code": 0},
            {"label": "mypy_baseline", "exit_code": 0},
            {"label": "docs_check_deps", "exit_code": 0},
            {"label": "docs_build", "exit_code": 0},
            {"label": "prompt_boundaries", "exit_code": 0},
            {"label": "strict_audits", "exit_code": 0},
            {"label": "audit_immutability", "exit_code": 0},
        ],
    }


def test_passing_matrix_verifies() -> None:
    assert verify_lane_contract(_matrix()).status.endswith("ready")


def test_missing_targeted_mypy_fails() -> None:
    m = _matrix(); m["results"] = [r for r in m["results"] if r["label"] != "targeted_mypy"]  # type: ignore[index]
    assert any(f.code == "missing_targeted_mypy" for f in verify_lane_contract(m).findings)


def test_docs_recovery_path_requires_all_three() -> None:
    m = _matrix()
    for r in m["results"]:  # type: ignore[index]
        if r["label"] == "docs_check_deps": r["exit_code"] = 1
    m["results"].append({"label": "docs_bootstrap", "exit_code": 0})  # type: ignore[index]
    m["results"].append({"label": "docs_check_deps_recheck", "exit_code": 0})  # type: ignore[index]
    assert verify_lane_contract(m).status.endswith("ready")


def test_required_failure_count_mismatch_fails() -> None:
    m = _matrix(); m["required_failure_count"] = 3
    assert any(f.code == "required_failure_count_mismatch" for f in verify_lane_contract(m).findings)


def test_nonproof_diagnostic_targeted_lane_does_not_fail_contract() -> None:
    m = _matrix()
    for row in m["results"]:  # type: ignore[index]
        if row["label"] == "real_memory_root_admission_gate_tests":
            row.update(
                {
                    "exit_code": 1,
                    "required": False,
                    "proof_required": False,
                    "diagnostic_only": True,
                    "nonexecution_allowed": True,
                    "proof_status": "nonproof-diagnostic-failed",
                    "exit_reason": "targeted-tests-not-executed",
                }
            )
    assert verify_lane_contract(m).status.endswith("ready")


def test_required_targeted_lane_with_nonexecuted_proof_status_fails_contract() -> None:
    m = _matrix()
    m["results"] = [row for row in m["results"] if row["label"] != "targeted_tests"]  # type: ignore[index]
    for row in m["results"]:  # type: ignore[index]
        if row["label"] == "real_executor_execution_preflight_gate_tests":
            row.update(
                {
                    "exit_code": 0,
                    "required": True,
                    "proof_required": True,
                    "proof_status": "proof-not-executed",
                    "tests_selected": 3,
                    "tests_executed": 0,
                    "tests_passed": 0,
                }
            )
    result = verify_lane_contract(m)
    assert result.status.endswith("failed")
    assert any(f.code == "targeted_tests_failed" for f in result.findings)
