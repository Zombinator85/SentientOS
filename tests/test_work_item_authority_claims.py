from __future__ import annotations

from sentientos.work_item_authority_claims import (
    ALIASES_TO_FAMILY,
    AUTHORITY_CLAIM_ALIASES,
    CANONICAL_AUTHORITY_CLAIM_FAMILIES,
    authority_claim_summary,
    authority_claims_from_nested_evidence,
    authority_contradiction_codes,
    normalize_authority_claims,
)


def test_all_families_have_aliases():
    for family in CANONICAL_AUTHORITY_CLAIM_FAMILIES:
        assert family in AUTHORITY_CLAIM_ALIASES
        assert AUTHORITY_CLAIM_ALIASES[family]


def test_aliases_map_to_canonical_family():
    for family, aliases in AUTHORITY_CLAIM_ALIASES.items():
        for alias in aliases:
            assert ALIASES_TO_FAMILY[alias] == family


def test_normalize_boolean_like_and_ambiguous_values():
    claims = normalize_authority_claims(
        {
            "network_requested": "yes",
            "provider_requested": "true",
            "prompt_export_requested": "enabled",
            "subprocess_used": 0,
            "scheduler_requested": 1,
        }
    )
    assert claims["network"] is True
    assert claims["provider"] is True
    assert claims["scheduler"] is True
    assert claims["prompt_export"] is False
    assert claims["subprocess_or_shell"] is False


def test_nested_evidence_extraction_and_deterministic_outputs():
    claims = authority_claims_from_nested_evidence(
        {"packet": {"agent_execution_requested": True}},
        {"handoff": [{"network_performed": "yes"}]},
        {"dry": {"result": {"workspace_execution_performed": True}}},
    )
    summary = authority_claim_summary(claims)
    codes = authority_contradiction_codes(claims)
    assert summary == ("agent_execution", "network", "workspace_execution")
    assert codes == (
        "dry_run_claims_agent_execution_authority",
        "dry_run_claims_network_authority",
        "dry_run_claims_workspace_execution_authority",
    )
