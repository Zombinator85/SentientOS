from __future__ import annotations

from sentientos.codex_validation_matrix_lane_contract import verify_lane_contract


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
