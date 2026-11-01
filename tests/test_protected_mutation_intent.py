from __future__ import annotations

import pytest

from sentientos.protected_mutation_intent import evaluate_declared_intent_for_decision

pytestmark = pytest.mark.no_legacy_skip


def test_malformed_declared_domains_do_not_raise_or_match_authority() -> None:
    result = evaluate_declared_intent_for_decision(
        {
            "action_kind": "quarantine_clear",
            "authority_class": "operator",
            "protected_mutation_intent": {
                "declared": True,
                "domains": object(),
                "authority_classes": "operator",
                "schema_version": {"invalid": "shape"},
            },
        }
    )

    assert result.status == "declared_but_mismatched"
    assert result.declared_domains == ()
    assert result.expected_domains == ("quarantine_clear_privileged_operator_action",)
    assert result.authority_match is False


def test_valid_declared_intent_remains_consistent() -> None:
    result = evaluate_declared_intent_for_decision(
        {
            "action_kind": "quarantine_clear",
            "authority_class": "operator",
            "protected_mutation_intent": {
                "declared": True,
                "domains": ["quarantine_clear_privileged_operator_action"],
                "authority_classes": ["operator"],
                "schema_version": "1",
            },
        }
    )

    assert result.status == "declared_and_consistent"
    assert result.declared_domains == result.expected_domains
    assert result.authority_match is True
