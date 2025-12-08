import pytest

from sentientos.federation.federation_digest import FederationDigest
from sentientos.runtime.config_sanitizer import ConfigSanitizer


pytestmark = pytest.mark.no_legacy_skip


def test_digest_receives_sanitized_config():
    sanitizer = ConfigSanitizer()
    digest = FederationDigest()
    raw_config = {
        "core_values": ["b", "a"],
        "timestamp": "now",
        "spotlight_rules": {"latest_time": 123, "order": ["beta", "alpha"]},
    }

    sanitized_config = sanitizer.sanitize(raw_config)["config"]
    result = digest.compute_digest({"core_themes": ["memory"]}, sanitized_config)

    assert "timestamp" not in sanitized_config
    assert "latest_time" not in sanitized_config.get("spotlight_rules", {})
    assert result["components"]["config"]["core_values"] == ["a", "b"]


def test_digest_is_stable_for_unordered_input():
    sanitizer = ConfigSanitizer()
    digest = FederationDigest()
    config_a = {"spotlight_rules": {"order": ["beta", "alpha"]}, "core_values": ["z", "a"]}
    config_b = {"core_values": ["a", "z"], "spotlight_rules": {"order": ["alpha", "beta"]}}

    sanitized_a = sanitizer.sanitize(config_a)["config"]
    sanitized_b = sanitizer.sanitize(config_b)["config"]

    digest_a = digest.compute_digest({}, sanitized_a)
    digest_b = digest.compute_digest({}, sanitized_b)

    assert digest_a["digest"] == digest_b["digest"]


def test_digest_changes_with_different_sanitized_config():
    sanitizer = ConfigSanitizer()
    digest = FederationDigest()
    base_config = {"core_values": ["a", "b"], "spotlight_rules": {"order": ["alpha"]}}
    changed_config = {"core_values": ["a", "b", "c"], "spotlight_rules": {"order": ["alpha"]}}

    digest_base = digest.compute_digest({}, sanitizer.sanitize(base_config)["config"])
    digest_changed = digest.compute_digest({}, sanitizer.sanitize(changed_config)["config"])

    assert digest_base["digest"] != digest_changed["digest"]
