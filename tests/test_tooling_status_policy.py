import pytest

from scripts.tooling_status import (
    RedactionProfile,
    ToolingStatusPolicy,
    aggregate_tooling_status,
    evaluate_tooling_status_policy,
    parse_tooling_status_policy,
    policy_ci_strict,
    policy_local_dev_permissive,
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
