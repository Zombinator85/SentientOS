from __future__ import annotations

import json

import pytest

from scripts.tooling_status import aggregate_tooling_status

EXPECTED_SCHEMA_VERSION = "1.0"
EXPECTED_AGGREGATE_FIELDS = {
    "schema_version",
    "overall_status",
    "tools",
    "missing_tools",
}
EXPECTED_TOOL_FIELDS = {
    "tool",
    "classification",
    "status",
    "non_blocking",
    "reason",
    "dependency",
}


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


def test_tooling_status_schema_matches_contract() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "skipped", "reason": "manifest_missing"},
        }
    )

    payload = aggregate.to_dict()
    assert payload["schema_version"] == EXPECTED_SCHEMA_VERSION
    assert set(payload.keys()) == EXPECTED_AGGREGATE_FIELDS

    tools_payload = payload["tools"]
    assert tools_payload
    for tool_name, tool_payload in tools_payload.items():
        missing = EXPECTED_TOOL_FIELDS - set(tool_payload.keys())
        unexpected = set(tool_payload.keys()) - EXPECTED_TOOL_FIELDS
        if missing or unexpected:
            pytest.fail(
                "Tooling status schema changed (missing:"
                f" {sorted(missing)}, unexpected: {sorted(unexpected)}); bump schema_version"
                f" from {EXPECTED_SCHEMA_VERSION} and update the contract."
            )
        assert tool_payload["tool"] == tool_name


def test_tooling_status_json_is_deterministic() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "failed", "reason": "unit_failure"},
            "mypy": {"status": "failed"},
            "verify_audits": {"status": "passed"},
        }
    )

    first = aggregate.to_json()
    second = aggregate.to_json()
    assert first == second
    assert json.loads(first) == aggregate.to_dict()
