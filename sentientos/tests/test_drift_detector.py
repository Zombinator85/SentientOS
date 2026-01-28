import json
from pathlib import Path

import pytest

from sentientos.diagnostics.drift_detector import DriftConfig, detect_drift


def _read_log(path: Path) -> list[dict]:
    if not path.exists():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def _make_silhouette(
    date: str,
    *,
    posture_counts: dict | None = None,
    plugin_usage: dict | None = None,
    motion_deltas: dict | None = None,
    anomalies: dict | None = None,
) -> dict:
    payload = {"date": date}
    if posture_counts is not None:
        payload["posture_counts"] = posture_counts
    if plugin_usage is not None:
        payload["plugin_usage"] = plugin_usage
    if motion_deltas is not None:
        payload["motion_deltas"] = motion_deltas
    if anomalies is not None:
        payload["anomalies"] = anomalies
    return payload


@pytest.mark.parametrize(
    "silhouettes, config, expected_type",
    [
        (
            [
                _make_silhouette("2025-09-03", posture_counts={"high_alert": 5}),
                _make_silhouette("2025-09-02", posture_counts={"high_alert": 4}),
                _make_silhouette("2025-09-01", posture_counts={"high_alert": 3}),
            ],
            DriftConfig(window_days=3, posture_repeat_max=3, emit_pulse=False),
            "POSTURE_STUCK",
        ),
        (
            [
                _make_silhouette("2025-09-03", motion_deltas={"motion_detected": 0, "noise_events": 0}),
                _make_silhouette("2025-09-02", motion_deltas={"motion_detected": 0, "noise_events": 0}),
                _make_silhouette("2025-09-01", motion_deltas={"motion_detected": 0, "noise_events": 0}),
            ],
            DriftConfig(window_days=3, motion_starvation_days=3, emit_pulse=False),
            "MOTION_STARVATION",
        ),
        (
            [
                _make_silhouette("2025-09-03", plugin_usage={"alpha": 8, "beta": 2}),
                _make_silhouette("2025-09-02", plugin_usage={"alpha": 4}),
                _make_silhouette("2025-09-01", plugin_usage={"beta": 1}),
            ],
            DriftConfig(window_days=3, plugin_dominance_percent=80, emit_pulse=False),
            "PLUGIN_DOMINANCE",
        ),
        (
            [
                _make_silhouette(
                    "2025-09-03",
                    anomalies={"severity_counts": {"moderate": 1, "critical": 0, "low": 0}},
                ),
                _make_silhouette(
                    "2025-09-02",
                    anomalies={"severity_counts": {"moderate": 2, "critical": 0, "low": 0}},
                ),
                _make_silhouette(
                    "2025-09-01",
                    anomalies={"severity_counts": {"moderate": 1, "critical": 0, "low": 0}},
                ),
            ],
            DriftConfig(window_days=3, anomaly_min_severity=2, anomaly_streak_days=3, emit_pulse=False),
            "ANOMALY_ESCALATION",
        ),
    ],
)

def test_drift_detector_triggers_and_logs(
    silhouettes,
    config,
    expected_type,
    tmp_path,
    monkeypatch,
):
    log_path = tmp_path / "drift_detector.jsonl"
    monkeypatch.setenv("DRIFT_DETECTOR_LOG", str(log_path))

    result = detect_drift(silhouettes, config)

    assert result["drift_detected"] is True
    assert result["drift_events"][0]["type"] == expected_type

    entries = _read_log(log_path)
    assert entries, "expected drift detector audit log to be written"
    assert entries[-1]["data"]["drift_type"] == expected_type
