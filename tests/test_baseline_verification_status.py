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
        mypy_output_path=tmp_path / "glow/typecheck/mypy_latest.txt",
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
        mypy_output_path=tmp_path / "glow/typecheck/mypy_latest.txt",
        corridor_report_path=corridor_path,
    )

    assert status["lanes"]["protected_corridor"]["status"] == "red"
    assert status["lanes"]["protected_corridor"]["failure_count"] == 1
    assert status["protected_corridor_green"] is False
