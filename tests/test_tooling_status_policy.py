import pytest

from scripts.tooling_status import (
    _REDACTED_MARKER,
    RedactionProfile,
    ToolingStatusPolicy,
    aggregate_tooling_status,
    compose_tooling_status_policies,
    evaluate_tooling_status_policy,
    parse_tooling_status_policy,
    policy_ci_strict,
    policy_local_dev_permissive,
    policy_release_gate,
)


def test_policy_validation_requires_schema_version() -> None:
    with pytest.raises(ValueError):
        parse_tooling_status_policy({"allowed_overall_statuses": ["PASS"]})


def test_policy_rejects_disallowed_overall_status() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "failed"},
            "verify_audits": {"status": "passed"},
        }
    )

    decision = evaluate_tooling_status_policy(aggregate, policy_ci_strict())

    assert decision.outcome == "REJECT"
    assert any("overall_status" in reason for reason in decision.reasons)


def test_policy_accepts_strict_ci_with_provenance() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "skipped", "reason": "manifest_missing"},
        },
        provenance_attestation={
            "attestation_version": "1.2",
            "producer_id": "buildkite",
            "producer_type": "ci",
        },
    )

    decision = evaluate_tooling_status_policy(aggregate, policy_ci_strict())

    assert decision.outcome == "ACCEPT"
    assert decision.reasons == ()


def test_policy_rejects_wrong_producer_type() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "passed"},
        },
        provenance_attestation={
            "attestation_version": "1.2",
            "producer_id": "local-dev",
            "producer_type": "local",
        },
    )

    decision = evaluate_tooling_status_policy(aggregate, policy_ci_strict())

    assert decision.outcome == "REJECT"
    assert any("producer_type" in reason for reason in decision.reasons)


def test_policy_warns_when_warn_allowed() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "failed"},
            "verify_audits": {"status": "passed"},
        }
    )

    decision = evaluate_tooling_status_policy(aggregate, policy_local_dev_permissive())

    assert decision.outcome == "WARN"
    assert any("overall_status is WARN" == reason for reason in decision.reasons)


def test_policy_enforces_redaction_profile() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed", "reason": "details"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "skipped", "reason": "manifest_missing"},
        }
    )

    redaction_policy = ToolingStatusPolicy(
        schema_version="1.0",
        allowed_overall_statuses=("PASS",),
        allowed_producer_types=None,
        required_redaction_profile=RedactionProfile.SAFE,
        maximum_advisory_issues=0,
    )

    non_redacted_decision = evaluate_tooling_status_policy(aggregate, redaction_policy)
    assert non_redacted_decision.outcome == "REJECT"

    redacted_payload = aggregate.profiled_payload(RedactionProfile.SAFE)
    redacted = aggregate_tooling_status(
        redacted_payload["tools"],
        provenance_attestation=redacted_payload.get("provenance_attestation"),
    )

    redacted_decision = evaluate_tooling_status_policy(redacted, redaction_policy)
    assert redacted_decision.outcome == "ACCEPT"


def test_policy_decision_is_deterministic() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "passed"},
        }
    )

    policy = policy_local_dev_permissive()

    first = evaluate_tooling_status_policy(aggregate, policy)
    second = evaluate_tooling_status_policy(aggregate, policy)

    assert first == second


def test_policy_rejects_unknown_fields_when_not_forward() -> None:
    with pytest.raises(ValueError):
        parse_tooling_status_policy(
            {
                "schema_version": "1.0",
                "allowed_overall_statuses": ["PASS"],
                "unexpected": True,
            }
        )


def test_policy_decision_trace_toggle() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "skipped", "reason": "manifest_missing"},
        }
    )

    policy = policy_local_dev_permissive()

    decision_only = evaluate_tooling_status_policy(aggregate, policy)
    decision_with_trace, trace = evaluate_tooling_status_policy(
        aggregate, policy, emit_trace=True
    )

    assert decision_only == decision_with_trace
    assert trace.profile is RedactionProfile.FULL
    assert trace.evaluated_rules


def test_policy_decision_trace_is_deterministic() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "passed"},
        }
    )

    policy = policy_local_dev_permissive()

    first_decision, first_trace = evaluate_tooling_status_policy(
        aggregate, policy, emit_trace=True
    )
    second_decision, second_trace = evaluate_tooling_status_policy(
        aggregate, policy, emit_trace=True
    )

    assert first_decision == second_decision
    assert first_trace == second_trace


def test_policy_decision_trace_respects_redaction() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed", "reason": "detailed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "skipped", "reason": "manifest_missing"},
        },
        provenance_attestation={
            "attestation_version": "1.2",
            "producer_id": "ci-runner",
            "producer_type": "ci",
            "constraints": {"branch": "main"},
        },
        lineage_parent_fingerprint="f" * 64,
    )

    policy = policy_release_gate()

    decision, trace = evaluate_tooling_status_policy(
        aggregate, policy, profile=RedactionProfile.SAFE, emit_trace=True
    )

    assert decision.outcome == "REJECT"
    attestation = trace.aggregate.get("provenance_attestation")
    assert isinstance(attestation, dict)
    assert attestation.get("producer_id") == _REDACTED_MARKER
    assert attestation.get("producer_type") == _REDACTED_MARKER
    assert all(value == _REDACTED_MARKER for value in attestation.get("constraints", {}).values())
    pytest_reason = trace.aggregate["tools"]["pytest"].get("reason")
    assert pytest_reason == _REDACTED_MARKER


def test_policy_decision_trace_captures_composition_overrides() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "failed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "passed"},
        }
    )

    restrictive = policy_ci_strict()
    permissive = policy_local_dev_permissive()

    composition = {
        "schema_version": "1.0",
        "layers": [
            {
                "name": "base",
                "priority": 0,
                "policy": {
                    "schema_version": restrictive.schema_version,
                    "allowed_overall_statuses": list(restrictive.allowed_overall_statuses),
                    "allowed_producer_types": list(restrictive.allowed_producer_types),
                    "required_redaction_profile": None,
                    "maximum_advisory_issues": restrictive.maximum_advisory_issues,
                },
            },
            {
                "name": "override",
                "priority": 1,
                "policy": {
                    "schema_version": permissive.schema_version,
                    "allowed_overall_statuses": list(permissive.allowed_overall_statuses),
                    "allowed_producer_types": None,
                    "required_redaction_profile": None,
                    "maximum_advisory_issues": permissive.maximum_advisory_issues,
                },
            },
        ],
        "overall_status_rule": "restrictive_wins",
        "producer_type_rule": "restrictive_wins",
        "advisory_issue_rule": "restrictive_wins",
        "redaction_profile_rule": "restrictive_wins",
    }

    policy = compose_tooling_status_policies(composition)

    decision, trace = evaluate_tooling_status_policy(
        aggregate, policy, emit_trace=True
    )

    assert decision.outcome == "WARN"
    assert trace.applied_overrides
    assert any(override.dimension == "overall_status" for override in trace.applied_overrides)
    assert any("overall_status" in entry for entry in trace.rejected_alternatives)


def test_policy_decision_trace_does_not_change_outcome() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "failed"},
            "mypy": {"status": "failed"},
            "verify_audits": {"status": "passed"},
        }
    )

    policy = policy_ci_strict()

    without_trace = evaluate_tooling_status_policy(aggregate, policy)
    with_trace, trace = evaluate_tooling_status_policy(
        aggregate, policy, emit_trace=True
    )

    assert trace.evaluated_rules
    assert without_trace == with_trace
