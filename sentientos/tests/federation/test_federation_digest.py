import copy

import pytest

from sentientos.federation import FederationDigest

pytestmark = pytest.mark.no_legacy_skip


def sample_identity_summary():
    return {
        "core_themes": {"qualia": "stable", "ethics": "low", "metacognition": "low"},
        "recurring_insights": ["determinism", "consistency"],
        "chapter_count": 2,
    }


def sample_config():
    return {
        "core_values": [{"name": "integrity", "priority": 10}],
        "tone_constraints": {"dialogue_max_lines": 3, "qualia_order": ["stable", "shifting"]},
        "ethical_rules": {"safety_risk_threshold": 0.5},
        "dialogue_templates": {"driver_priority": ["conflict_severity", "conflict_count"]},
        "spotlight_rules": {"conflict_threshold": 2},
        "drift_thresholds": {"ethical": {"low": 0.5}},
    }


def test_digest_is_deterministic_and_stable():
    digest = FederationDigest()
    identity = sample_identity_summary()
    config = sample_config()

    first = digest.compute_digest(identity_summary=identity, config=config)
    second = digest.compute_digest(identity_summary=identity, config=config)

    assert first["digest"] == second["digest"]
    assert first["components"] == second["components"]
    assert len(first["digest"]) == 64
    assert list(first["components"]["config"].keys()) == list(digest.fields)


def test_digest_changes_with_different_inputs():
    digest = FederationDigest()
    identity = sample_identity_summary()
    config = sample_config()

    baseline = digest.compute_digest(identity_summary=identity, config=config)["digest"]
    modified_config = sample_config()
    modified_config["tone_constraints"]["dialogue_max_lines"] = 4

    changed = digest.compute_digest(identity_summary=identity, config=modified_config)["digest"]

    assert baseline != changed


def test_inputs_are_not_mutated_and_copies_are_defensive():
    digest = FederationDigest()
    identity = sample_identity_summary()
    config = sample_config()

    identity_snapshot = copy.deepcopy(identity)
    config_snapshot = copy.deepcopy(config)

    result = digest.compute_digest(identity_summary=identity, config=config)
    assert identity == identity_snapshot
    assert config == config_snapshot

    # Mutating returned structures must not affect subsequent results
    result["components"]["config"]["tone_constraints"]["dialogue_max_lines"] = 99
    repeat = digest.compute_digest(identity_summary=identity, config=config)
    assert repeat["digest"] != ""
    assert repeat["components"]["config"]["tone_constraints"]["dialogue_max_lines"] == 3
