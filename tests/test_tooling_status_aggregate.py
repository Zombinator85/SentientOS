from __future__ import annotations

import json
from dataclasses import replace

import pytest

from scripts.tooling_status import (
    aggregate_tooling_status,
    fingerprint_tooling_status,
    parse_tooling_status_payload,
    RedactionProfile,
    tooling_status_supersedes,
    tooling_status_equal,
    validate_lineage_chain,
)

EXPECTED_SCHEMA_VERSION = "1.1"
EXPECTED_AGGREGATE_FIELDS = {
    "schema_version",
    "overall_status",
    "tools",
    "missing_tools",
}
EXPECTED_OPTIONAL_AGGREGATE_FIELDS = {
    "lineage_parent_fingerprint",
    "lineage_relation",
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
    assert payload["schema_version"] == EXPECTED_SCHEMA_VERSION
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
    payload_fields = set(payload.keys())
    assert EXPECTED_AGGREGATE_FIELDS.issubset(payload_fields)
    unexpected_aggregate_fields = payload_fields - EXPECTED_AGGREGATE_FIELDS - EXPECTED_OPTIONAL_AGGREGATE_FIELDS - {"fingerprint"}
    if unexpected_aggregate_fields:
        pytest.fail(
            "Tooling status schema changed (missing:"
            f" {sorted(set())}, unexpected: {sorted(unexpected_aggregate_fields)}); bump schema_version"
            f" from {EXPECTED_SCHEMA_VERSION} and update the contract."
        )
    assert EXPECTED_OPTIONAL_AGGREGATE_FIELDS.isdisjoint(payload_fields)

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


def test_profiled_json_is_deterministic_per_profile() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "failed", "reason": "unit_failure"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "skipped", "reason": "manual_skip"},
        }
    )

    safe_first = aggregate.to_json(profile=RedactionProfile.SAFE)
    safe_second = aggregate.to_json(profile=RedactionProfile.SAFE)
    minimal_first = aggregate.to_json(profile=RedactionProfile.MINIMAL)
    minimal_second = aggregate.to_json(profile=RedactionProfile.MINIMAL)

    assert safe_first == safe_second
    assert minimal_first == minimal_second

    safe_payload = json.loads(safe_first)
    assert safe_payload["tools"]["pytest"]["reason"] == "<redacted>"
    assert safe_payload["tools"]["audit_immutability_verifier"]["dependency"] == "<redacted>"


def test_fingerprint_is_stable_for_identical_payloads() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "skipped", "reason": "manifest_missing"},
        }
    )

    clone = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "skipped", "reason": "manifest_missing"},
        }
    )

    assert aggregate.fingerprint == clone.fingerprint
    assert tooling_status_equal(aggregate, clone)


def test_fingerprint_ignores_field_ordering() -> None:
    payload = {
        "schema_version": EXPECTED_SCHEMA_VERSION,
        "overall_status": "PASS",
        "missing_tools": ["verify_audits", "audit_immutability_verifier"],
        "tools": {
            "audit_immutability_verifier": {
                "classification": "artifact-dependent",
                "dependency": "/vow/immutable_manifest.json",
                "non_blocking": True,
                "reason": "manifest_missing",
                "status": "skipped",
                "tool": "audit_immutability_verifier",
            },
            "mypy": {
                "classification": "advisory",
                "dependency": None,
                "non_blocking": True,
                "reason": None,
                "status": "passed",
                "tool": "mypy",
            },
            "verify_audits": {
                "classification": "optional",
                "dependency": None,
                "non_blocking": True,
                "reason": None,
                "status": "missing",
                "tool": "verify_audits",
            },
            "pytest": {
                "classification": "mandatory",
                "dependency": None,
                "non_blocking": False,
                "reason": None,
                "status": "passed",
                "tool": "pytest",
            },
        },
    }

    unordered = parse_tooling_status_payload(payload)
    ordered = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "skipped", "reason": "manifest_missing"},
        }
    )

    assert unordered.fingerprint == ordered.fingerprint
    assert tooling_status_equal(unordered, ordered)


def test_fingerprint_changes_when_payload_differs() -> None:
    baseline = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "skipped", "reason": "manifest_missing"},
        }
    )

    modified = aggregate_tooling_status(
        {
            "pytest": {"status": "failed", "reason": "unit_failure"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "skipped", "reason": "manifest_missing"},
        }
    )

    assert baseline.fingerprint != modified.fingerprint
    assert tooling_status_equal(baseline, modified) is False


def test_profiled_fingerprint_is_stable_within_profile() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "failed", "reason": "unit_failure"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
        },
        lineage_parent_fingerprint="0" * 64,
        lineage_relation="recheck",
    )

    payload = aggregate.to_dict(profile=RedactionProfile.SAFE)
    parsed = parse_tooling_status_payload(payload, profile=RedactionProfile.SAFE)

    assert fingerprint_tooling_status(aggregate, profile=RedactionProfile.SAFE) == fingerprint_tooling_status(
        parsed, profile=RedactionProfile.SAFE
    )
    assert parsed.to_dict(profile=RedactionProfile.SAFE)["fingerprint"] == payload["fingerprint"]


def test_fingerprints_diverge_across_profiles() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "failed", "reason": "unit_failure"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
        }
    )

    full_fingerprint = fingerprint_tooling_status(aggregate, profile=RedactionProfile.FULL)
    safe_fingerprint = fingerprint_tooling_status(aggregate, profile=RedactionProfile.SAFE)
    minimal_fingerprint = fingerprint_tooling_status(aggregate, profile=RedactionProfile.MINIMAL)

    assert full_fingerprint != safe_fingerprint
    assert safe_fingerprint != minimal_fingerprint
    assert full_fingerprint != minimal_fingerprint


def test_fingerprint_survives_round_trip_serialization() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "skipped", "reason": "manifest_missing"},
        }
    )
    serialized = aggregate.to_json()
    parsed = parse_tooling_status_payload(json.loads(serialized))

    assert fingerprint_tooling_status(aggregate) == fingerprint_tooling_status(parsed)


def test_parse_current_schema_requires_fields() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "passed"},
        }
    )
    payload = aggregate.to_dict()
    payload.pop("overall_status")

    with pytest.raises(ValueError, match="missing required fields"):
        parse_tooling_status_payload(payload)


def test_parse_forward_schema_preserves_unknown_fields() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "skipped", "reason": "manifest_missing"},
        }
    )
    payload = aggregate.to_dict()
    payload["schema_version"] = "2.0"
    payload["future_hint"] = "forward-compatible"
    payload["tools"]["pytest"]["experimental_reason"] = "new semantics"
    payload["tools"]["novel_tool"] = {"status": "passed", "tool": "novel_tool"}

    parsed = parse_tooling_status_payload(payload)

    assert parsed.forward_version_detected is True
    assert parsed.schema_version == "2.0"
    assert parsed.tools["pytest"].status == "passed"
    assert "future_hint" in parsed.forward_metadata.get("aggregate", {})
    assert "experimental_reason" in parsed.forward_metadata.get("tool_fields", {}).get("pytest", {})
    assert "novel_tool" in parsed.forward_metadata.get("tools", {})


def test_parse_rejects_invalid_status_for_current_version() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "passed"},
        }
    )
    payload = aggregate.to_dict()
    payload["tools"]["pytest"]["status"] = "unknown"

    with pytest.raises(ValueError, match="Unknown tool status"):
        parse_tooling_status_payload(payload)


def test_parse_round_trip_matches_current_schema() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "skipped", "reason": "manifest_missing"},
        }
    )
    payload = aggregate.to_dict()
    parsed = parse_tooling_status_payload(payload)

    assert parsed.to_dict() == payload
    assert parsed.forward_version_detected is False


def test_redacted_payload_validates_against_schema() -> None:
    origin = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "skipped", "reason": "manifest_missing"},
        }
    )
    successor = aggregate_tooling_status(
        {
            "pytest": {"status": "failed", "reason": "flake"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "skipped", "reason": "manifest_missing"},
        },
        lineage_parent_fingerprint=origin.fingerprint,
        lineage_relation="recheck",
    )

    minimal_payload = successor.to_dict(profile=RedactionProfile.MINIMAL)
    parsed = parse_tooling_status_payload(minimal_payload, profile=RedactionProfile.MINIMAL)

    assert parsed.tools["pytest"].reason == "<redacted>"
    assert parsed.tools["audit_immutability_verifier"].dependency == "<redacted>"
    assert parsed.lineage_parent_fingerprint == "0" * 64
    assert parsed.to_dict(profile=RedactionProfile.MINIMAL)["fingerprint"] == minimal_payload["fingerprint"]


def test_lineage_supersession_chain_validates() -> None:
    origin = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "passed"},
        }
    )
    followup = aggregate_tooling_status(
        {
            "pytest": {"status": "failed", "reason": "flake"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "passed"},
        },
        lineage_parent_fingerprint=origin.fingerprint,
        lineage_relation="recheck",
    )
    correction = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "passed"},
        },
        lineage_parent_fingerprint=followup.fingerprint,
        lineage_relation="supersedes",
    )

    assert tooling_status_supersedes(followup, origin) is True
    assert tooling_status_supersedes(correction, followup) is True
    validate_lineage_chain([origin, followup, correction])


def test_self_referential_lineage_is_rejected() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "passed"},
        }
    )
    payload = aggregate.to_dict()
    payload.pop("fingerprint")
    payload["lineage_parent_fingerprint"] = aggregate.fingerprint

    with pytest.raises(ValueError, match="lineage parent"):
        parse_tooling_status_payload(payload)


def test_lineage_fields_are_ignored_for_older_versions() -> None:
    origin = aggregate_tooling_status(
        {
            "pytest": {"status": "failed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "passed"},
        }
    )
    lineage_payload = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "passed"},
        },
        lineage_parent_fingerprint=origin.fingerprint,
        lineage_relation="amends",
    ).to_dict()
    lineage_payload.pop("fingerprint")
    lineage_payload["schema_version"] = "1.0"

    parsed = parse_tooling_status_payload(lineage_payload)

    assert parsed.schema_version == "1.0"
    assert parsed.lineage_parent_fingerprint is None
    assert parsed.forward_metadata["aggregate"]["lineage_parent_fingerprint"] == origin.fingerprint


def test_lineage_fingerprint_changes_without_status_delta() -> None:
    baseline = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "skipped", "reason": "manifest_missing"},
        }
    )
    successor = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "skipped", "reason": "manifest_missing"},
        },
        lineage_parent_fingerprint=baseline.fingerprint,
        lineage_relation="recheck",
    )

    assert baseline.fingerprint != successor.fingerprint
    assert tooling_status_equal(baseline, successor) is False


def test_lineage_cycle_detection() -> None:
    origin = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "passed"},
        }
    )
    update = aggregate_tooling_status(
        {
            "pytest": {"status": "failed", "reason": "flake"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "passed"},
        },
        lineage_parent_fingerprint=origin.fingerprint,
        lineage_relation="recheck",
    )
    cycle_member = replace(
        origin,
        lineage_parent_fingerprint=update.fingerprint,
        lineage_relation="supersedes",
    )

    with pytest.raises(ValueError, match="cycle"):
        validate_lineage_chain([origin, update, cycle_member])
