from __future__ import annotations

import json
from pathlib import Path

from scripts.emit_baseline_verification_status import build_status


def test_build_status_reads_new_corridor_global_summary(tmp_path: Path) -> None:
    corridor = {
        "schema_version": 1,
        "global_summary": {
            "status": "amber",
            "blocking_profiles": [],
            "advisory_profiles": ["ci-advisory"],
            "debt_profiles": ["ci-advisory"],
            "corridor_blocking": False,
        },
    }
    corridor_path = tmp_path / "glow/contracts/protected_corridor_report.json"
    corridor_path.parent.mkdir(parents=True, exist_ok=True)
    corridor_path.write_text(json.dumps(corridor), encoding="utf-8")

    status = build_status(
        failure_digest_path=tmp_path / "glow/test_runs/test_failure_digest.json",
        run_provenance_path=tmp_path / "glow/test_runs/test_run_provenance.json",
        mypy_output_path=tmp_path / "glow/typecheck/mypy_latest.txt",
        mypy_ratchet_status_path=tmp_path / "glow/contracts/typing_ratchet_status.json",
        corridor_report_path=corridor_path,
    )

    assert status["lanes"]["protected_corridor"]["status"] == "amber"
    assert status["lanes"]["protected_corridor"]["details"]["reported_status"] == "amber"
    assert status["protected_corridor_green"] is True


def test_build_status_derived_profile_fallback_when_global_missing(tmp_path: Path) -> None:
    corridor = {
        "schema_version": 1,
        "profiles": [
            {
                "profile": "federation-enforce",
                "summary": {
                    "blocking_failure_count": 1,
                    "provisioning_failure_count": 0,
                    "command_unavailable_count": 0,
                    "policy_skip_count": 0,
                    "advisory_warning_count": 0,
                    "non_blocking_failure_count": 0,
                },
            }
        ],
    }
    corridor_path = tmp_path / "glow/contracts/protected_corridor_report.json"
    corridor_path.parent.mkdir(parents=True, exist_ok=True)
    corridor_path.write_text(json.dumps(corridor), encoding="utf-8")

    status = build_status(
        failure_digest_path=tmp_path / "glow/test_runs/test_failure_digest.json",
        run_provenance_path=tmp_path / "glow/test_runs/test_run_provenance.json",
        mypy_output_path=tmp_path / "glow/typecheck/mypy_latest.txt",
        mypy_ratchet_status_path=tmp_path / "glow/contracts/typing_ratchet_status.json",
        corridor_report_path=corridor_path,
    )

    assert status["lanes"]["protected_corridor"]["status"] == "red"
    assert status["lanes"]["protected_corridor"]["failure_count"] == 1
    assert status["protected_corridor_green"] is False


def test_build_status_classifies_run_tests_lane_not_run_when_artifacts_absent(tmp_path: Path) -> None:
    corridor_path = tmp_path / "glow/contracts/protected_corridor_report.json"
    corridor_path.parent.mkdir(parents=True, exist_ok=True)
    corridor_path.write_text(
        json.dumps({"schema_version": 1, "global_summary": {"status": "green", "corridor_blocking": False}}),
        encoding="utf-8",
    )

    status = build_status(
        failure_digest_path=tmp_path / "glow/test_runs/test_failure_digest.json",
        run_provenance_path=tmp_path / "glow/test_runs/test_run_provenance.json",
        mypy_output_path=tmp_path / "glow/typecheck/mypy_latest.txt",
        mypy_ratchet_status_path=tmp_path / "glow/contracts/typing_ratchet_status.json",
        corridor_report_path=corridor_path,
    )

    assert status["lanes"]["run_tests"]["status"] == "missing"
    assert status["lanes"]["run_tests"]["lane_state"] == "lane_not_run"
    assert status["lanes"]["run_tests"]["pointer_state"] == "missing"


def test_build_status_classifies_run_tests_unavailable_environment(tmp_path: Path) -> None:
    corridor_path = tmp_path / "glow/contracts/protected_corridor_report.json"
    corridor_path.parent.mkdir(parents=True, exist_ok=True)
    corridor_path.write_text(
        json.dumps({"schema_version": 1, "global_summary": {"status": "green", "corridor_blocking": False}}),
        encoding="utf-8",
    )
    provenance = tmp_path / "glow/test_runs/test_run_provenance.json"
    provenance.parent.mkdir(parents=True, exist_ok=True)
    provenance.write_text(
        json.dumps({"exit_reason": "airlock-failed", "metrics_status": "unavailable", "execution_mode": "execute"}),
        encoding="utf-8",
    )

    status = build_status(
        failure_digest_path=tmp_path / "glow/test_runs/test_failure_digest.json",
        run_provenance_path=provenance,
        mypy_output_path=tmp_path / "glow/typecheck/mypy_latest.txt",
        mypy_ratchet_status_path=tmp_path / "glow/contracts/typing_ratchet_status.json",
        corridor_report_path=corridor_path,
    )

    assert status["lanes"]["run_tests"]["status"] == "amber"
    assert status["lanes"]["run_tests"]["lane_state"] == "lane_unavailable_in_environment"
    assert status["lanes"]["run_tests"]["pointer_state"] == "unavailable"


def test_build_status_classifies_run_tests_deferred_debt(tmp_path: Path) -> None:
    corridor_path = tmp_path / "glow/contracts/protected_corridor_report.json"
    corridor_path.parent.mkdir(parents=True, exist_ok=True)
    corridor_path.write_text(
        json.dumps({"schema_version": 1, "global_summary": {"status": "green", "corridor_blocking": False}}),
        encoding="utf-8",
    )
    provenance = tmp_path / "glow/test_runs/test_run_provenance.json"
    provenance.parent.mkdir(parents=True, exist_ok=True)
    provenance.write_text(
        json.dumps({"metrics_status": "ok", "execution_mode": "execute", "pytest_exit_code": 1}),
        encoding="utf-8",
    )
    digest = tmp_path / "glow/test_runs/test_failure_digest.json"
    digest.write_text(
        json.dumps(
            {
                "failure_groups": [{"failure_class": "bootstrap_import_instability"}],
                "failure_class_totals": {"bootstrap_import_instability": 1},
            }
        ),
        encoding="utf-8",
    )

    status = build_status(
        failure_digest_path=digest,
        run_provenance_path=provenance,
        mypy_output_path=tmp_path / "glow/typecheck/mypy_latest.txt",
        mypy_ratchet_status_path=tmp_path / "glow/contracts/typing_ratchet_status.json",
        corridor_report_path=corridor_path,
    )

    assert status["lanes"]["run_tests"]["status"] == "amber"
    assert status["lanes"]["run_tests"]["lane_state"] == "lane_completed_with_deferred_debt"
    assert status["lanes"]["run_tests"]["pointer_state"] == "unavailable"


def test_build_status_classifies_mypy_from_ratchet_status(tmp_path: Path) -> None:
    corridor_path = tmp_path / "glow/contracts/protected_corridor_report.json"
    corridor_path.parent.mkdir(parents=True, exist_ok=True)
    corridor_path.write_text(
        json.dumps({"schema_version": 1, "global_summary": {"status": "green", "corridor_blocking": False}}),
        encoding="utf-8",
    )
    ratchet = tmp_path / "glow/contracts/typing_ratchet_status.json"
    ratchet.parent.mkdir(parents=True, exist_ok=True)
    ratchet.write_text(
        json.dumps({"status": "ok", "deferred_debt_error_count": 12, "ratcheted_new_error_count": 0}),
        encoding="utf-8",
    )

    status = build_status(
        failure_digest_path=tmp_path / "glow/test_runs/test_failure_digest.json",
        run_provenance_path=tmp_path / "glow/test_runs/test_run_provenance.json",
        mypy_output_path=tmp_path / "glow/typecheck/mypy_latest.txt",
        mypy_ratchet_status_path=ratchet,
        corridor_report_path=corridor_path,
    )

    assert status["lanes"]["mypy"]["status"] == "amber"
    assert status["lanes"]["mypy"]["lane_state"] == "lane_completed_with_deferred_debt"
    assert status["lanes"]["mypy"]["pointer_state"] == "unavailable"

def test_build_status_prefers_broad_lane_latest_summary_when_present(tmp_path: Path) -> None:
    corridor_path = tmp_path / "glow/contracts/protected_corridor_report.json"
    corridor_path.parent.mkdir(parents=True, exist_ok=True)
    corridor_path.write_text(
        json.dumps({"schema_version": 1, "global_summary": {"status": "green", "corridor_blocking": False}}),
        encoding="utf-8",
    )
    summary_path = tmp_path / "glow/observatory/broad_lane/broad_lane_latest_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "lanes": {
                    "run_tests": {
                        "status": "amber",
                        "lane_state": "lane_completed_with_deferred_debt",
                        "failure_count": 2,
                        "details": {"failure_group_count": 2},
                        "pointer_state": "current",
                        "primary_artifact_path": "glow/test_runs/test_run_provenance.json",
                        "supporting_artifact_paths": ["glow/test_runs/test_failure_digest.json"],
                        "created_at": "2026-03-20T00:00:00Z",
                        "run_id": "abc",
                    },
                    "mypy": {
                        "status": "green",
                        "lane_state": "lane_completed_with_advisories",
                        "failure_count": 0,
                        "details": {},
                        "pointer_state": "current",
                        "primary_artifact_path": "glow/contracts/typing_ratchet_status.json",
                        "supporting_artifact_paths": [],
                        "created_at": "2026-03-20T00:00:00Z",
                        "run_id": None,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    status = build_status(
        failure_digest_path=tmp_path / "glow/test_runs/test_failure_digest.json",
        run_provenance_path=tmp_path / "glow/test_runs/test_run_provenance.json",
        mypy_output_path=tmp_path / "glow/typecheck/mypy_latest.txt",
        mypy_ratchet_status_path=tmp_path / "glow/contracts/typing_ratchet_status.json",
        corridor_report_path=corridor_path,
        broad_lane_latest_summary_path=summary_path,
    )

    assert status["lanes"]["run_tests"]["failure_count"] == 2
    assert status["lanes"]["run_tests"]["details"]["latest_pointer"]["run_id"] == "abc"
    assert status["lanes"]["run_tests"]["pointer_state"] == "current"
    assert status["lanes"]["run_tests"]["lane_state"] == "lane_completed_with_deferred_debt"
    assert status["lanes"]["run_tests"]["summary_reason"] == "pointer=current; lane=lane_completed_with_deferred_debt; policy=deferred"
    assert status["lanes"]["mypy"]["pointer_state"] == "current"
