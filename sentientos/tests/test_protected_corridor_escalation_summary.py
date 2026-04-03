from __future__ import annotations

from scripts.protected_corridor import _global_summary


def test_global_summary_includes_escalation_posture_views() -> None:
    profiles = [
        {
            "profile": "ci-advisory",
            "summary": {
                "blocking_failure_count": 0,
                "provisioning_failure_count": 0,
                "command_unavailable_count": 0,
                "policy_skip_count": 0,
                "advisory_warning_count": 0,
                "non_blocking_failure_count": 0,
                "not_applicable_count": 0,
            },
            "checks": [
                {
                    "name": "protected_mutation_forward_enforcement",
                    "relevance": {
                        "forward_enforcement_status": "forward_clean",
                        "trust_posture": {
                            "global_covered_scope": {
                                "overall_escalation_posture": "forward_block",
                                "escalation_posture_counts": {"none": 2, "forward_block": 1},
                                "overall_review_contract": "explicit_review_before_protected_change",
                                "review_contract_counts": {"none": 2, "explicit_review_before_protected_change": 1},
                                "domains": {
                                    "immutable_manifest_identity_writes": {
                                        "escalation_posture": "forward_block",
                                        "review_contract": "explicit_review_before_protected_change",
                                    },
                                    "genesisforge_lineage_proposal_adoption": {"escalation_posture": "none", "review_contract": "none"},
                                },
                            },
                            "current_change_surface": {
                                "overall_escalation_posture": "verification_attention",
                                "escalation_posture_counts": {"none": 3, "verification_attention": 1},
                                "overall_review_contract": "proof_review_required",
                                "review_contract_counts": {"none": 3, "proof_review_required": 1},
                                "domains": {
                                    "immutable_manifest_identity_writes": {
                                        "escalation_posture": "verification_attention",
                                        "review_contract": "proof_review_required",
                                    },
                                    "genesisforge_lineage_proposal_adoption": {"escalation_posture": "none", "review_contract": "none"},
                                },
                            },
                        },
                        "trust_degradation_ledger": {
                            "counts_by_posture": {"evidence_incomplete": 1},
                            "counts_by_escalation_posture": {"verification_attention": 1},
                            "counts_by_review_contract": {"proof_review_required": 1},
                            "counts_by_evidence_class": {"kernel_admission_issues": 1},
                            "records_emitted": True,
                            "ledger_path": "glow/contracts/protected_mutation_trust_degradation_ledger.jsonl",
                        },
                    },
                }
            ],
        }
    ]
    summary = _global_summary(profiles)
    escalation = summary["protected_mutation_escalation_posture"]
    assert escalation["by_profile"]["ci-advisory"]["global_covered_scope"]["overall_escalation_posture"] == "forward_block"
    assert escalation["by_profile"]["ci-advisory"]["current_change_surface"]["overall_escalation_posture"] == "verification_attention"
    assert escalation["counts_by_view"]["global_covered_scope"]["forward_block"] == 1
    assert escalation["counts_by_view"]["current_change_surface"]["verification_attention"] == 1
    assert escalation["any_attention_by_view"]["global_covered_scope"]["has_forward_block"] is True
    assert escalation["any_attention_by_view"]["current_change_surface"]["has_verification_attention"] is True
    review = summary["protected_mutation_review_contract"]
    assert review["by_profile"]["ci-advisory"]["global_covered_scope"]["overall_review_contract"] == "explicit_review_before_protected_change"
    assert review["by_profile"]["ci-advisory"]["current_change_surface"]["overall_review_contract"] == "proof_review_required"
    assert review["counts_by_view"]["global_covered_scope"]["explicit_review_before_protected_change"] == 1
    assert review["counts_by_view"]["current_change_surface"]["proof_review_required"] == 1
    assert review["any_required_by_view"]["global_covered_scope"]["has_explicit_review_before_protected_change"] is True
    assert review["any_required_by_view"]["current_change_surface"]["has_proof_review_required"] is True
    trust_posture = summary["protected_mutation_trust_posture_by_profile"]["ci-advisory"]
    assert trust_posture["global_covered_scope"]["domains"]["immutable_manifest_identity_writes"]["escalation_posture"] == "forward_block"
    assert trust_posture["global_covered_scope"]["domains"]["immutable_manifest_identity_writes"]["review_contract"] == "explicit_review_before_protected_change"
    trust_ledger = summary["trust_degradation_ledger"]
    assert trust_ledger["counts_by_escalation_posture"]["verification_attention"] == 1
    assert trust_ledger["counts_by_review_contract"]["proof_review_required"] == 1
    assert trust_ledger["counts_by_posture"]["evidence_incomplete"] == 1
    assert trust_ledger["counts_by_evidence_class"]["kernel_admission_issues"] == 1
