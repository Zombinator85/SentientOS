from __future__ import annotations

from pathlib import Path

from scripts.capture_federation_identity_baseline import capture_baseline as capture_federation
from scripts.capture_perception_schema_baseline import capture_baseline as capture_perception
from scripts.capture_pulse_schema_baseline import capture_baseline as capture_pulse
from scripts.capture_self_model_baseline import capture_baseline as capture_self
from scripts.detect_federation_identity_drift import detect_drift as detect_federation
from scripts.detect_perception_schema_drift import detect_drift as detect_perception
from scripts.detect_pulse_schema_drift import detect_drift as detect_pulse
from scripts.detect_self_model_drift import detect_drift as detect_self
from scripts.generate_immutable_manifest import generate_manifest


def test_pulse_schema_capture_then_detect_reports_none(tmp_path: Path) -> None:
    baseline = tmp_path / "pulse_baseline.json"
    report = tmp_path / "pulse_drift.json"
    capture_pulse(baseline)
    drift = detect_pulse(baseline_path=baseline, output_path=report)
    assert drift["drift_type"] == "none"
    assert drift["drifted"] is False


def test_self_model_capture_then_detect_reports_none(tmp_path: Path) -> None:
    baseline = tmp_path / "self_baseline.json"
    report = tmp_path / "self_drift.json"
    capture_self(baseline)
    drift = detect_self(baseline_path=baseline, output_path=report)
    assert drift["drift_type"] == "none"
    assert drift["drifted"] is False


def test_federation_identity_capture_then_detect_reports_none(tmp_path: Path) -> None:
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("stable", encoding="utf-8")
    manifest = tmp_path / "immutable_manifest.json"
    generate_manifest(output=manifest, files=(tracked,))

    import os

    old = os.environ.get("IMMUTABILITY_MANIFEST_PATH")
    os.environ["IMMUTABILITY_MANIFEST_PATH"] = str(manifest)
    try:
        baseline = tmp_path / "federation_baseline.json"
        report = tmp_path / "federation_drift.json"
        capture_federation(baseline)
        drift = detect_federation(baseline_path=baseline, output_path=report)
    finally:
        if old is None:
            os.environ.pop("IMMUTABILITY_MANIFEST_PATH", None)
        else:
            os.environ["IMMUTABILITY_MANIFEST_PATH"] = old

    assert drift["drift_type"] == "none"
    assert drift["drifted"] is False


def test_perception_schema_capture_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "perception_baseline_1.json"
    second = tmp_path / "perception_baseline_2.json"
    payload_one = capture_perception(first)
    payload_two = capture_perception(second)
    assert payload_one["schema"] == payload_two["schema"]
    assert payload_one["schema_fingerprint"] == payload_two["schema_fingerprint"]
    assert "perception.audio" in payload_one["schema"]["events"]
    assert "perception.vision" in payload_one["schema"]["events"]


def test_perception_schema_capture_then_detect_reports_none(tmp_path: Path) -> None:
    baseline = tmp_path / "perception_baseline.json"
    report = tmp_path / "perception_drift.json"
    capture_perception(baseline)
    drift = detect_perception(baseline_path=baseline, output_path=report)
    assert drift["drift_type"] == "none"
    assert drift["drifted"] is False


def test_perception_schema_detects_added_field_and_event(monkeypatch, tmp_path: Path) -> None:
    baseline = tmp_path / "perception_baseline.json"
    report = tmp_path / "perception_drift.json"
    capture_perception(baseline)

    from scripts import detect_perception_schema_drift as module

    original = module._schema()
    mutated = {**original, "events": {**original.get("events", {})}}
    base_event = dict(mutated["events"]["perception.audio"])
    base_event["allowed_fields"] = sorted(list(base_event["allowed_fields"]) + ["new_field"])
    field_types = dict(base_event["field_types"])
    field_types["sample_rate_hz"] = "int"
    base_event["field_types"] = field_types
    mutated["events"]["perception.audio"] = base_event
    mutated["events"]["perception.synthetic"] = {
        "required_fields": ["event_type", "timestamp"],
        "allowed_fields": ["event_type", "timestamp", "source"],
        "field_types": {"event_type": "str", "timestamp": "str", "source": "str"},
        "field_enums": {"event_type": ["perception.synthetic"]},
    }

    monkeypatch.setattr(module, "_schema", lambda: mutated)

    drift = detect_perception(baseline_path=baseline, output_path=report)
    assert drift["drifted"] is True
    assert "perception.synthetic" in drift["added_event_types"]
    assert any(item["field"] == "new_field" and item["event_type"] == "perception.audio" for item in drift["added_fields"])
    assert any(item["field"] == "sample_rate_hz" and item["event_type"] == "perception.audio" for item in drift["type_changes"])


def test_perception_schema_detects_vision_type_change(monkeypatch, tmp_path: Path) -> None:
    baseline = tmp_path / "perception_baseline.json"
    report = tmp_path / "perception_drift.json"
    capture_perception(baseline)

    from scripts import detect_perception_schema_drift as module

    original = module._schema()
    mutated = {**original, "events": {**original.get("events", {})}}
    vision_event = dict(mutated["events"]["perception.vision"])
    field_types = dict(vision_event["field_types"])
    field_types["faces_detected"] = "int"
    vision_event["field_types"] = field_types
    mutated["events"]["perception.vision"] = vision_event

    monkeypatch.setattr(module, "_schema", lambda: mutated)

    drift = detect_perception(baseline_path=baseline, output_path=report)
    assert drift["drifted"] is True
    assert any(item["field"] == "faces_detected" and item["event_type"] == "perception.vision" for item in drift["type_changes"])
