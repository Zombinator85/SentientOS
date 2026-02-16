from __future__ import annotations

from pathlib import Path

from scripts.capture_federation_identity_baseline import capture_baseline as capture_federation
from scripts.capture_pulse_schema_baseline import capture_baseline as capture_pulse
from scripts.capture_self_model_baseline import capture_baseline as capture_self
from scripts.detect_federation_identity_drift import detect_drift as detect_federation
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
