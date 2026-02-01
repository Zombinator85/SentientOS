import pytest

from resident_kernel import ResidentKernel
from sentientos.diagnostics import drift_pressure
from sentientos.pressure_queue import enqueue_pressure_signal, read_pressure_queue
from log_utils import append_json

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
    for entry in entries:
        append_json(path, entry)


def test_drift_pressure_signal_deterministic(tmp_path, monkeypatch) -> None:
    log_path = tmp_path / "drift_detector.jsonl"
    _write_drift_fixture(log_path)
    monkeypatch.setenv("DRIFT_DETECTOR_LOG", str(log_path))

    first = drift_pressure.get_drift_pressure_signal(days=3)
    second = drift_pressure.get_drift_pressure_signal(days=3)

    assert first == second
    assert first["as_of_date"] == "2024-01-05"
    assert first["window_days"] == 3
    assert first["digest"] == second["digest"]


def test_drift_pressure_severity_rules() -> None:
    assert drift_pressure.derive_drift_pressure_severity({}) == "none"
    assert drift_pressure.derive_drift_pressure_severity({"posture_stuck": 1}) == "low"
    assert drift_pressure.derive_drift_pressure_severity({"posture_stuck": 2}) == "medium"
    assert drift_pressure.derive_drift_pressure_severity({"posture_stuck": 3}) == "high"
    assert drift_pressure.derive_drift_pressure_severity({"posture_stuck": 1, "plugin_dominance": 3}) == "high"


def test_drift_pressure_queue_dedupes_and_logs(tmp_path, monkeypatch) -> None:
    log_path = tmp_path / "drift_detector.jsonl"
    _write_drift_fixture(log_path)
    monkeypatch.setenv("DRIFT_DETECTOR_LOG", str(log_path))
    monkeypatch.setenv("PRESSURE_QUEUE_LOG", str(tmp_path / "pressure_queue.jsonl"))

    signal = drift_pressure.get_drift_pressure_signal(days=3)
    first_entry = enqueue_pressure_signal(signal)
    second_entry = enqueue_pressure_signal(signal)

    assert first_entry is not None
    assert second_entry is None

    entries = read_pressure_queue()
    enqueue_entries = [entry for entry in entries if entry.get("event") == "pressure_enqueue"]
    assert len(enqueue_entries) == 1
    record = enqueue_entries[0]
    assert record["digest"] == signal["digest"]
    assert record["as_of_date"] == signal["as_of_date"]
    assert record["window_days"] == signal["window_days"]
    assert record["severity"] == signal["severity"]
    assert record["counts"] == signal["counts"]
    assert record["enqueued_at"]


def test_kernel_drift_pressure_signal_is_read_only(tmp_path, monkeypatch) -> None:
    log_path = tmp_path / "drift_detector.jsonl"
    _write_drift_fixture(log_path)
    monkeypatch.setenv("DRIFT_DETECTOR_LOG", str(log_path))

    kernel = ResidentKernel()
    governance_before = kernel.governance_view()
    embodiment_before = kernel.embodiment_view()

    signal = kernel.get_drift_pressure_signal(days=3)

    assert kernel.governance_view() == governance_before
    assert kernel.embodiment_view() == embodiment_before
    assert signal["signal_type"] == "drift"
