from __future__ import annotations

import pytest

from scripts.tooling_status import (
    PolicyOverrideMode,
    RedactionProfile,
    ToolingStatusPolicy,
    compose_tooling_status_policies,
)


def _policy(
    *,
    statuses: tuple[str, ...],
    producers: tuple[str, ...] | None = None,
    advisory: int | None = None,
    redaction: RedactionProfile | None = None,
) -> ToolingStatusPolicy:
    return ToolingStatusPolicy(
        schema_version="1.0",
        allowed_overall_statuses=statuses,
        allowed_producer_types=producers,
        required_redaction_profile=redaction,
        maximum_advisory_issues=advisory,
    )


def _composition_payload(layers: list[tuple[str, int, ToolingStatusPolicy]], **rules: str) -> dict:
    return {
        "schema_version": "1.0",
        "layers": [
            {
                "name": name,
                "priority": priority,
                "policy": {
                    "schema_version": policy.schema_version,
                    "allowed_overall_statuses": list(policy.allowed_overall_statuses),
                    "allowed_producer_types": list(policy.allowed_producer_types)
                    if policy.allowed_producer_types is not None
                    else None,
                    "required_redaction_profile": policy.required_redaction_profile.profile_name
                    if policy.required_redaction_profile is not None
                    else None,
                    "maximum_advisory_issues": policy.maximum_advisory_issues,
                },
            }
            for name, priority, policy in layers
        ],
        "overall_status_rule": rules.get("overall_status_rule", "restrictive_wins"),
        "producer_type_rule": rules.get("producer_type_rule", "restrictive_wins"),
        "advisory_issue_rule": rules.get("advisory_issue_rule", "restrictive_wins"),
        "redaction_profile_rule": rules.get("redaction_profile_rule", "restrictive_wins"),
    }


def test_simple_layering_uses_restrictive_defaults() -> None:
    base = _policy(statuses=("PASS",), producers=("ci",), advisory=0)
    repo = _policy(statuses=("PASS", "WARN"))

    composition = _composition_payload(
        [
            ("org", 0, base),
            ("repo", 1, repo),
        ]
    )

    policy = compose_tooling_status_policies(composition)

    assert policy.allowed_overall_statuses == ("PASS",)
    assert policy.allowed_producer_types == ("ci",)
    assert policy.maximum_advisory_issues == 0


def test_restrictive_overrides_dominate_more_permissive_layers() -> None:
    base = _policy(statuses=("PASS", "WARN"), producers=("ci",))
    run_specific = _policy(statuses=("PASS",), producers=("ci", "local"), advisory=1)

    composition = _composition_payload(
        [
            ("org", 1, base),
            ("run", 0, run_specific),
        ],
        overall_status_rule="restrictive_wins",
        producer_type_rule="restrictive_wins",
        advisory_issue_rule="restrictive_wins",
    )

    policy = compose_tooling_status_policies(composition)

    assert policy.allowed_overall_statuses == ("PASS",)
    assert policy.allowed_producer_types == ("ci",)
    assert policy.maximum_advisory_issues == 1


def test_explicit_widening_requires_opt_in() -> None:
    base = _policy(statuses=("PASS",), producers=("ci",), advisory=0)
    run_specific = _policy(statuses=("PASS", "WARN"), producers=("local",), advisory=None)

    composition = _composition_payload(
        [
            ("org", 0, base),
            ("run", 1, run_specific),
        ],
        overall_status_rule="explicit_widen",
        producer_type_rule="explicit_widen",
        advisory_issue_rule="explicit_widen",
    )

    policy = compose_tooling_status_policies(composition)

    assert policy.allowed_overall_statuses == ("PASS", "WARN")
    assert policy.allowed_producer_types == ("ci", "local")
    assert policy.maximum_advisory_issues is None


def test_conflicting_precedence_is_rejected() -> None:
    base = _policy(statuses=("PASS",))
    duplicate_priority = _policy(statuses=("PASS", "WARN", "FAIL"))

    composition = _composition_payload(
        [
            ("org", 0, base),
            ("repo", 0, duplicate_priority),
        ]
    )

    with pytest.raises(ValueError):
        compose_tooling_status_policies(composition)


def test_composition_is_deterministic_regardless_of_input_order() -> None:
    base = _policy(statuses=("PASS",), producers=("ci",), redaction=RedactionProfile.SAFE)
    override = _policy(statuses=("PASS", "WARN"), producers=("ci", "sandbox"))

    unordered = _composition_payload(
        [
            ("override", 2, override),
            ("base", 1, base),
        ],
        redaction_profile_rule=PolicyOverrideMode.RESTRICTIVE_WINS.value,
    )
    ordered = _composition_payload(
        [
            ("base", 1, base),
            ("override", 2, override),
        ],
        redaction_profile_rule=PolicyOverrideMode.RESTRICTIVE_WINS.value,
    )

    first = compose_tooling_status_policies(unordered)
    second = compose_tooling_status_policies(ordered)

    assert first.allowed_overall_statuses == ("PASS",)
    assert first.allowed_producer_types == ("ci",)
    assert first.required_redaction_profile is RedactionProfile.SAFE
    assert first == second
