import pytest

from sentientos.federation import FederationConsensusSentinel, FederationDigest

pytestmark = pytest.mark.no_legacy_skip


def make_digest(identity_label: str, field_modifier: int = 0) -> dict:
    digest = FederationDigest()
    identity_summary = {
        "core_themes": {
            "qualia": identity_label,
            "ethics": "low",
            "metacognition": "low",
        }
    }
    config = {
        "core_values": [{"name": "integrity", "priority": 10 + field_modifier}],
        "tone_constraints": {"dialogue_max_lines": 3 + field_modifier},
        "ethical_rules": {"safety_risk_threshold": 0.5},
        "dialogue_templates": {"driver_priority": ["conflict_severity", "conflict_count"]},
        "spotlight_rules": {"conflict_threshold": 2},
        "drift_thresholds": {"ethical": {"low": 0.5}},
    }
    return digest.compute_digest(identity_summary=identity_summary, config=config)


def test_matching_digest_reports_none_drift():
    sentinel = FederationConsensusSentinel()
    local = make_digest("stable")
    sentinel.record_external_digest(make_digest("stable"))

    result = sentinel.compare(local)

    assert result["match"] is True
    assert result["drift_level"] == "none"
    assert result["signals"]["matches"]


def test_minor_drift_detected_on_field_changes():
    sentinel = FederationConsensusSentinel()
    local = make_digest("stable")
    sentinel.record_external_digest(make_digest("stable", field_modifier=1))

    result = sentinel.compare(local)

    assert result["match"] is False
    assert result["drift_level"] == "minor"
    assert result["signals"]["classifications"][0]["level"] == "minor"


def test_major_and_catastrophic_levels():
    sentinel = FederationConsensusSentinel()
    local = make_digest("stable")
    major_digest = make_digest("volatile")
    catastrophic_digest = FederationDigest().compute_digest(
        identity_summary={
            "core_themes": {
                "qualia": "fragmented",
                "ethics": "critical",
                "metacognition": "high",
            }
        },
        config={},
    )

    sentinel.record_external_digest(major_digest)
    sentinel.record_external_digest(catastrophic_digest)

    result = sentinel.compare(local)
    levels = {entry["level"] for entry in result["signals"]["classifications"]}

    assert "major" in levels
    assert "catastrophic" in levels
    assert result["drift_level"] == "catastrophic"


def test_fifo_behavior_respects_max_reports():
    sentinel = FederationConsensusSentinel(max_reports=2)
    sentinel.record_external_digest(make_digest("stable"))
    sentinel.record_external_digest(make_digest("shifted"))
    sentinel.record_external_digest(make_digest("volatile"))

    result = sentinel.compare(make_digest("volatile"))

    assert result["signals"]["external_reports"] == 2
    stored_digests = [entry["digest"] for entry in result["signals"]["classifications"]]
    assert len(stored_digests) == 2


def test_compare_is_deterministic():
    sentinel = FederationConsensusSentinel()
    local = make_digest("stable")
    sentinel.record_external_digest(make_digest("shifted"))

    first = sentinel.compare(local)
    second = sentinel.compare(local)

    assert first == second
