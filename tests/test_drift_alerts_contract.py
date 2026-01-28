import json

import pytest

from sentientos.diagnostics import drift_alerts

pytestmark = pytest.mark.no_legacy_skip


def _write_drift_fixture(path) -> None:
    entries = [
        {
            "timestamp": "2024-01-05T10:00:00",
            "type": "drift_detected",
            "drift_type": "POSTURE_STUCK",
            "dates": ["2024-01-05", "2024-01-04"],
        },
        {
            "timestamp": "2024-01-04T09:00:00",
            "type": "drift_detected",
            "drift_type": "PLUGIN_DOMINANCE",
            "dates": ["2024-01-04"],
        },
        {
            "timestamp": "2024-01-03T10:00:00",
            "type": "drift_detected",
            "drift_type": "MOTION_STARVATION",
            "dates": ["2024-01-03"],
        },
        {
            "timestamp": "2024-01-02T10:00:00",
            "type": "drift_detected",
            "drift_type": "ANOMALY_ESCALATION",
            "dates": ["2024-01-02"],
        },
        {
            "timestamp": "2024-01-04T12:00:00",
            "type": "drift_detected",
            "drift_type": "PLUGIN_DOMINANCE",
            "dates": ["2024-01-04"],
        },
        {
            "timestamp": "2024-01-03T12:00:00",
            "type": "drift_detected",
            "drift_type": "POSTURE_STUCK",
            "dates": ["2024-01-03"],
        },
    ]
    payload = "\n".join(json.dumps(entry) for entry in entries) + "\n"
    path.write_text(payload, encoding="utf-8")


def test_recent_drift_reports_are_sorted_and_deterministic(tmp_path, monkeypatch) -> None:
    log_path = tmp_path / "drift_detector.jsonl"
    _write_drift_fixture(log_path)
    monkeypatch.setenv("DRIFT_DETECTOR_LOG", str(log_path))

    first = drift_alerts.get_recent_drift_reports(limit=3)
    second = drift_alerts.get_recent_drift_reports(limit=3)

    assert [report["date"] for report in first] == ["2024-01-05", "2024-01-04", "2024-01-03"]
    assert first == second


def test_drift_summary_matches_recent_reports(tmp_path, monkeypatch) -> None:
    log_path = tmp_path / "drift_detector.jsonl"
    _write_drift_fixture(log_path)
    monkeypatch.setenv("DRIFT_DETECTOR_LOG", str(log_path))

    reports = drift_alerts.get_recent_drift_reports(limit=3)
    summary = drift_alerts.get_drift_summary(days=3)

    expected = {
        "days": 3,
        "total": sum(1 for report in reports if report["tags"]),
        "posture_stuck": sum(1 for report in reports if report.get("posture_stuck")),
        "plugin_dominance": sum(1 for report in reports if report.get("plugin_dominance")),
        "motion_starvation": sum(1 for report in reports if report.get("motion_starvation")),
        "anomaly_trend": sum(1 for report in reports if report.get("anomaly_trend")),
    }

    assert summary == expected


def test_silhouette_payload_validation(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SENTIENTOS_SILHOUETTE_DIR", str(tmp_path))

    bad_path = tmp_path / "2024-01-01.json"
    bad_path.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")

    with pytest.raises(drift_alerts.SilhouettePayloadError):
        drift_alerts.get_silhouette_payload("2024-01-01")

    mismatch_path = tmp_path / "2024-01-02.json"
    mismatch_path.write_text(json.dumps({"date": "2024-01-03"}), encoding="utf-8")

    with pytest.raises(drift_alerts.SilhouettePayloadError):
        drift_alerts.get_silhouette_payload("2024-01-02")

    ok_path = tmp_path / "2024-01-04.json"
    ok_path.write_text(json.dumps({"date": "2024-01-04", "signal": "ok"}), encoding="utf-8")

    payload = drift_alerts.get_silhouette_payload("2024-01-04")
    assert payload == {"date": "2024-01-04", "signal": "ok"}
