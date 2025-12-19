from __future__ import annotations

import json

from scripts.tooling_status import aggregate_tooling_status


def test_aggregate_all_pass() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "passed"},
        }
    )

    assert aggregate.overall_status == "PASS"
    assert aggregate.missing_tools == ()
    payload = json.loads(aggregate.to_json())
    assert payload["schema_version"] == "1.0"
    assert payload["tools"]["pytest"]["status"] == "passed"


def test_advisory_failure_produces_warning_and_marks_missing() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "failed", "reason": "type_errors"},
            "audit_immutability_verifier": {"status": "skipped", "reason": "manifest_missing"},
        }
    )

    assert aggregate.overall_status == "WARN"
    assert "verify_audits" in aggregate.missing_tools
    assert aggregate.tools["mypy"].reason == "type_errors"
    payload = aggregate.to_dict()
    assert payload["tools"]["verify_audits"]["status"] == "missing"


def test_mandatory_failure_dominates() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "failed", "reason": "unit_failure"},
            "mypy": {"status": "failed"},
            "verify_audits": {"status": "passed"},
        }
    )

    assert aggregate.overall_status == "FAIL"
    assert aggregate.tools["pytest"].reason == "unit_failure"


def test_optional_missing_does_not_block_pass() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "audit_immutability_verifier": {"status": "skipped", "reason": "manifest_missing"},
        }
    )

    assert aggregate.overall_status == "PASS"
    assert aggregate.tools["verify_audits"].status == "missing"
    assert "verify_audits" in aggregate.missing_tools
