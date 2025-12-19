import json

import pytest

from scripts.tooling_status import (
    _REDACTED_MARKER,
    RedactionProfile,
    _PolicyEvaluationCache,
    ToolingStatusPolicy,
    aggregate_tooling_status,
    compose_tooling_status_policies,
    evaluate_tooling_status_policy,
    fingerprint_tooling_status,
    collect_snapshot_annotations,
    detect_supersession_chains,
    latest_authoritative_snapshot,
    parse_policy_evaluation_snapshot,
    parse_tooling_status_policy,
    policy_ci_strict,
    policy_local_dev_permissive,
    policy_release_gate,
    snapshot_tooling_status_policy_evaluation,
    snapshot_supersedes,
    verify_tooling_status_policy_snapshot,
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


def test_policy_cache_hits_on_identical_inputs() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
        }
    )

    policy = policy_local_dev_permissive()
    cache = _PolicyEvaluationCache(max_entries=4)

    first = evaluate_tooling_status_policy(aggregate, policy, cache=cache)
    second = evaluate_tooling_status_policy(aggregate, policy, cache=cache)

    assert first == second
    assert cache.hits == 1
    assert len(cache) == 1


def test_policy_cache_misses_for_distinct_inputs() -> None:
    baseline = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
        }
    )
    changed = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "failed"},
            "verify_audits": {"status": "passed"},
        }
    )

    policy = policy_local_dev_permissive()
    cache = _PolicyEvaluationCache(max_entries=4)

    evaluate_tooling_status_policy(baseline, policy, cache=cache)
    evaluate_tooling_status_policy(changed, policy, cache=cache)

    assert cache.hits == 0
    assert len(cache) == 2


def test_policy_cache_preserves_trace_and_decision_integrity() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
        }
    )

    policy = policy_local_dev_permissive()
    cache = _PolicyEvaluationCache(max_entries=4)

    decision_one, trace_one = evaluate_tooling_status_policy(
        aggregate, policy, cache=cache, emit_trace=True
    )
    decision_two, trace_two = evaluate_tooling_status_policy(
        aggregate, policy, cache=cache, emit_trace=True
    )

    assert decision_one == decision_two
    assert trace_one == trace_two
    assert cache.hits == 1


def test_policy_cache_can_be_disabled() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
        }
    )

    policy = policy_local_dev_permissive()
    cache = _PolicyEvaluationCache(max_entries=4)

    uncached = evaluate_tooling_status_policy(
        aggregate, policy, cache=cache, use_cache=False
    )
    cached = evaluate_tooling_status_policy(aggregate, policy, cache=cache)
    cached_repeat = evaluate_tooling_status_policy(aggregate, policy, cache=cache)

    assert uncached == cached == cached_repeat
    assert cache.hits == 1


def test_policy_snapshot_round_trip_matches_decision() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed", "reason": "ok"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "skipped", "reason": "manifest_missing"},
        },
        provenance_attestation={
            "attestation_version": "1.2",
            "producer_id": "ci-runner",
            "producer_type": "ci",
        },
    )

    snapshot = snapshot_tooling_status_policy_evaluation(
        aggregate, policy_release_gate(), profile=RedactionProfile.SAFE, use_cache=False
    )

    decision, trace = verify_tooling_status_policy_snapshot(snapshot)

    assert decision.outcome == "ACCEPT"
    assert trace.profile is RedactionProfile.SAFE
    assert fingerprint_tooling_status(trace.aggregate, profile=RedactionProfile.SAFE) == snapshot[
        "aggregate_fingerprint"
    ]


def test_policy_snapshot_rejects_forward_schema_version() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
        }
    )

    snapshot = snapshot_tooling_status_policy_evaluation(aggregate, policy_local_dev_permissive())
    snapshot["schema_version"] = "9.9"

    with pytest.raises(ValueError):
        verify_tooling_status_policy_snapshot(snapshot)


def test_policy_snapshot_serialization_is_deterministic() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
            "audit_immutability_verifier": {"status": "passed"},
        }
    )

    snapshot = snapshot_tooling_status_policy_evaluation(
        aggregate, policy_local_dev_permissive(), emit_trace=True, use_cache=False
    )
    serialized = json.dumps(snapshot, sort_keys=True)
    parsed = parse_policy_evaluation_snapshot(json.loads(serialized)).to_payload()

    assert json.dumps(parsed, sort_keys=True) == serialized


def test_snapshot_lineage_chain_detects_supersession() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
        }
    )

    base_snapshot_payload = snapshot_tooling_status_policy_evaluation(
        aggregate, policy_local_dev_permissive(), emit_trace=False
    )
    amended_snapshot_payload = snapshot_tooling_status_policy_evaluation(
        aggregate,
        policy_local_dev_permissive(),
        emit_trace=False,
        parent_snapshot_fingerprint=base_snapshot_payload["snapshot_fingerprint"],
        lineage_relation="supersedes",
        review_notes="follow-up review",
    )

    base_snapshot = parse_policy_evaluation_snapshot(base_snapshot_payload)
    amended_snapshot = parse_policy_evaluation_snapshot(amended_snapshot_payload)

    chains = detect_supersession_chains([base_snapshot, amended_snapshot])

    assert chains == [(base_snapshot, amended_snapshot)]
    assert latest_authoritative_snapshot([base_snapshot, amended_snapshot]) == amended_snapshot
    assert snapshot_supersedes(amended_snapshot, base_snapshot)


def test_snapshot_annotations_preserved_outside_authoritative_chain() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
        }
    )

    base_snapshot_payload = snapshot_tooling_status_policy_evaluation(
        aggregate, policy_local_dev_permissive(), emit_trace=False
    )
    annotation_snapshot_payload = snapshot_tooling_status_policy_evaluation(
        aggregate,
        policy_local_dev_permissive(),
        emit_trace=False,
        parent_snapshot_fingerprint=base_snapshot_payload["snapshot_fingerprint"],
        lineage_relation="annotates",
        review_notes="non-blocking review context",
    )
    amendment_snapshot_payload = snapshot_tooling_status_policy_evaluation(
        aggregate,
        policy_local_dev_permissive(),
        emit_trace=False,
        parent_snapshot_fingerprint=base_snapshot_payload["snapshot_fingerprint"],
        lineage_relation="amends",
    )

    base_snapshot = parse_policy_evaluation_snapshot(base_snapshot_payload)
    amendment_snapshot = parse_policy_evaluation_snapshot(amendment_snapshot_payload)
    annotation_snapshot = parse_policy_evaluation_snapshot(annotation_snapshot_payload)

    chains = detect_supersession_chains(
        [base_snapshot, amendment_snapshot, annotation_snapshot]
    )

    assert chains == [(base_snapshot, amendment_snapshot)]
    annotations = collect_snapshot_annotations(
        [base_snapshot, amendment_snapshot, annotation_snapshot]
    )

    assert annotations == {base_snapshot.fingerprint: (annotation_snapshot,)}
    assert latest_authoritative_snapshot(
        [base_snapshot, amendment_snapshot, annotation_snapshot]
    ) == amendment_snapshot


def test_snapshot_lineage_cycle_is_rejected() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
        }
    )

    base_snapshot_payload = snapshot_tooling_status_policy_evaluation(
        aggregate, policy_local_dev_permissive(), emit_trace=False
    )
    first_amendment_payload = snapshot_tooling_status_policy_evaluation(
        aggregate,
        policy_local_dev_permissive(),
        emit_trace=False,
        parent_snapshot_fingerprint=base_snapshot_payload["snapshot_fingerprint"],
        lineage_relation="supersedes",
    )
    second_amendment_payload = snapshot_tooling_status_policy_evaluation(
        aggregate,
        policy_local_dev_permissive(),
        emit_trace=False,
        parent_snapshot_fingerprint=first_amendment_payload["snapshot_fingerprint"],
        lineage_relation="supersedes",
    )

    cyclic_base_payload = dict(base_snapshot_payload)
    cyclic_base_payload["schema_version"] = base_snapshot_payload["schema_version"]
    cyclic_base_payload["parent_snapshot_fingerprint"] = second_amendment_payload[
        "snapshot_fingerprint"
    ]
    cyclic_base_payload["lineage_relation"] = "supersedes"
    cyclic_base_payload.pop("snapshot_fingerprint", None)
    cyclic_base_payload.pop("evaluation_fingerprint", None)

    with pytest.raises(ValueError):
        detect_supersession_chains(
            [cyclic_base_payload, first_amendment_payload, second_amendment_payload]
        )


def test_snapshot_fingerprint_changes_with_lineage_and_notes() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
        }
    )

    base_snapshot = parse_policy_evaluation_snapshot(
        snapshot_tooling_status_policy_evaluation(
            aggregate, policy_local_dev_permissive(), emit_trace=False
        )
    )
    first_amendment = parse_policy_evaluation_snapshot(
        snapshot_tooling_status_policy_evaluation(
            aggregate,
            policy_local_dev_permissive(),
            emit_trace=False,
            parent_snapshot_fingerprint=base_snapshot.fingerprint,
            lineage_relation="amends",
            review_notes="clarified reasoning",
        )
    )
    second_amendment = parse_policy_evaluation_snapshot(
        snapshot_tooling_status_policy_evaluation(
            aggregate,
            policy_local_dev_permissive(),
            emit_trace=False,
            parent_snapshot_fingerprint=base_snapshot.fingerprint,
            lineage_relation="amends",
            review_notes="tightened scope",
        )
    )

    assert base_snapshot.fingerprint != first_amendment.fingerprint
    assert first_amendment.fingerprint != second_amendment.fingerprint
    assert (
        first_amendment.evaluation_fingerprint
        == second_amendment.evaluation_fingerprint
        == base_snapshot.evaluation_fingerprint
    )


def test_legacy_snapshot_without_lineage_still_parses() -> None:
    aggregate = aggregate_tooling_status(
        {
            "pytest": {"status": "passed"},
            "mypy": {"status": "passed"},
            "verify_audits": {"status": "passed"},
        }
    )

    snapshot_payload = snapshot_tooling_status_policy_evaluation(
        aggregate, policy_local_dev_permissive(), emit_trace=False
    )
    snapshot_payload["schema_version"] = "1.0"
    snapshot_payload.pop("parent_snapshot_fingerprint", None)
    snapshot_payload.pop("lineage_relation", None)
    snapshot_payload.pop("review_notes", None)
    snapshot_payload.pop("snapshot_fingerprint", None)
    snapshot_payload.pop("evaluation_fingerprint", None)

    parsed = parse_policy_evaluation_snapshot(snapshot_payload)

    assert parsed.parent_snapshot_fingerprint is None
    assert parsed.lineage_relation is None
    assert parsed.review_notes is None
    decision = verify_tooling_status_policy_snapshot(snapshot_payload)

    assert decision.outcome == "ACCEPT"
