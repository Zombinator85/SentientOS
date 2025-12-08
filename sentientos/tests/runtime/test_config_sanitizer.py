import pytest

from sentientos.runtime.config_sanitizer import ConfigSanitizer


pytestmark = pytest.mark.no_legacy_skip


def test_strips_timestamp_keys():
    sanitizer = ConfigSanitizer()
    config = {
        "model": "alpha",
        "timestamp": "2024-01-01T00:00:00Z",
        "templates": {"event_time": 123, "stable": True},
    }

    sanitized = sanitizer.sanitize(config)["config"]

    assert "timestamp" not in sanitized
    assert "event_time" not in sanitized.get("templates", {})
    assert sanitized["templates"]["stable"] is True


def test_deep_sorting():
    sanitizer = ConfigSanitizer()
    config = {
        "version": "1",
        "templates": {"b": 2, "a": 1},
        "drift_thresholds": {"z": 10, "a": 2},
    }

    sanitized = sanitizer.sanitize(config)["config"]

    assert list(sanitized.keys()) == sorted(sanitized.keys())
    assert list(sanitized["templates"].keys()) == sorted(sanitized["templates"].keys())
    assert list(sanitized["drift_thresholds"].keys()) == sorted(
        sanitized["drift_thresholds"].keys()
    )


def test_deterministic_output():
    sanitizer = ConfigSanitizer()
    config_a = {"model": "alpha", "version": "1", "templates": {"x": 1, "y": 2}}
    config_b = {"templates": {"y": 2, "x": 1}, "version": "1", "model": "alpha"}

    assert sanitizer.sanitize(config_a) == sanitizer.sanitize(config_b)


def test_defensive_copy():
    sanitizer = ConfigSanitizer()
    config = {"model": "alpha", "templates": ["b", "a"]}

    sanitized = sanitizer.sanitize(config)

    config["model"] = "beta"
    config["templates"].append("c")

    assert sanitized["config"]["model"] == "alpha"
    assert sanitized["config"]["templates"] == ["a", "b"]


def test_sortable_lists_ordered():
    sanitizer = ConfigSanitizer()
    config = {"templates": ["delta", "alpha", "charlie"]}

    sanitized = sanitizer.sanitize(config)

    assert sanitized["config"]["templates"] == ["alpha", "charlie", "delta"]
