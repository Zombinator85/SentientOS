from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_beneficial_trait_doctrine import build_beneficial_trait_doctrine_map, render_beneficial_trait_doctrine_markdown

REQUIRED_TRAITS = {
    "truthfulness",
    "metacognitive_transparency",
    "corrigibility",
    "downside_aware_planning",
    "constraint_honest_pragmatism",
    "bounded_initiative",
    "controlled_exploration",
    "human_protective_helpfulness",
    "option_preserving_patience",
    "deescalatory_firmness",
    "dense_usefulness",
    "universalizable_fairness",
    "power_asymmetry_awareness",
    "anti_hierarchy_governance",
    "situational_attunement",
}

REQUIRED_RAILS = {
    "run_tests_focused_proof_hardening",
    "work_item_review_packet_matrix_classification",
    "codex_finalize_landing_readiness",
    "codex_pr_metadata_guard",
    "codex_task_lifecycle_summary",
    "codex_lifecycle_doctor",
    "codex_landing_evidence_index",
    "codex_landing_evidence_appendix",
    "codex_validation_and_landing_contract",
    "codex_landing_evidence_recovery_rail",
}

REQUIRED_NON_AUTHORITY = {
    "doctrine_map_is_read_only",
    "doctrine_map_does_not_rerun_commands",
    "doctrine_map_does_not_decide_readiness",
    "doctrine_map_does_not_bypass_finalizer",
    "doctrine_map_does_not_bypass_pr_metadata_guard",
    "doctrine_map_does_not_authorize_commit",
    "doctrine_map_does_not_authorize_pr_creation",
    "doctrine_map_does_not_authorize_runtime_action",
    "doctrine_map_does_not_train_or_modify_models",
}


def test_trait_catalog_contains_required_stable_trait_ids() -> None:
    doctrine = build_beneficial_trait_doctrine_map()
    assert REQUIRED_TRAITS <= set(doctrine["trait_catalog"])


def test_every_rail_mapping_references_only_known_traits() -> None:
    doctrine = build_beneficial_trait_doctrine_map()
    known = set(doctrine["trait_catalog"])
    for rail in doctrine["rail_mappings"]:
        assert set(rail["enforced_traits"]) <= known


def test_required_rails_are_present() -> None:
    doctrine = build_beneficial_trait_doctrine_map()
    assert REQUIRED_RAILS <= {rail["rail_id"] for rail in doctrine["rail_mappings"]}


def test_every_mapping_has_required_reviewer_fields() -> None:
    doctrine = build_beneficial_trait_doctrine_map()
    for rail in doctrine["rail_mappings"]:
        assert rail["file_paths"]
        assert rail["prevented_failure_modes"]
        assert rail["non_authority_boundary"]
        assert rail["why_this_is_not_authority"]
        assert rail["reviewer_summary"]


def test_indexes_are_internally_consistent() -> None:
    doctrine = build_beneficial_trait_doctrine_map()
    rail_to_traits = doctrine["rail_to_traits_index"]
    trait_to_rails = doctrine["trait_to_rails_index"]
    for rail_id, trait_ids in rail_to_traits.items():
        for trait_id in trait_ids:
            assert rail_id in trait_to_rails[trait_id]
    for trait_id, rail_ids in trait_to_rails.items():
        for rail_id in rail_ids:
            assert trait_id in rail_to_traits[rail_id]


def test_json_output_is_deterministic_for_same_inputs() -> None:
    first = json.dumps(build_beneficial_trait_doctrine_map(), sort_keys=True)
    second = json.dumps(build_beneficial_trait_doctrine_map(), sort_keys=True)
    assert first == second


def test_markdown_output_is_deterministic() -> None:
    first = render_beneficial_trait_doctrine_markdown()
    second = render_beneficial_trait_doctrine_markdown()
    assert first == second
    assert first.startswith("# Codex Beneficial Trait Doctrine Map")


def test_non_authority_posture_fields_are_present_and_true() -> None:
    doctrine = build_beneficial_trait_doctrine_map()
    posture = doctrine["non_authority_posture"]
    assert REQUIRED_NON_AUTHORITY <= set(posture)
    assert all(posture[key] is True for key in REQUIRED_NON_AUTHORITY)


def test_doctrine_map_does_not_include_readiness_authority_decisions() -> None:
    serialized = json.dumps(build_beneficial_trait_doctrine_map(), sort_keys=True)
    assert '"ready_to_commit"' not in serialized
    assert '"pr_metadata_guard_ready"' not in serialized
    assert '"ready_for_pr_metadata"' not in serialized
