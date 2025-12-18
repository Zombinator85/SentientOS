import pytest

from sentientos.observer_index import ObserverIndex


pytestmark = pytest.mark.no_legacy_skip


def test_observer_index_suppresses_redundant_and_low_confidence():
    index = ObserverIndex(confidence_threshold=0.6)
    index.register("bias_watcher", signal="bias", frequency="1s")

    observations = [
        {"observer": "bias_watcher", "signal": "bias", "delta": 0.2, "confidence": 0.9},
        {"observer": "bias_watcher", "signal": "bias", "delta": 0.2, "confidence": 0.95},
        {"observer": "drift_watcher", "signal": "drift", "delta": 0.05, "confidence": 0.4},
    ]

    heartbeat = index.heartbeat(observations)

    assert heartbeat["emissions"] == [
        {"observer": "bias_watcher", "signal": "bias", "delta": 0.2, "confidence": 0.9, "frequency": "1s"}
    ]
    assert len(heartbeat["audit_log"]) == 3

    second = index.heartbeat([
        {"observer": "bias_watcher", "signal": "bias", "delta": 0.25, "confidence": 0.8},
        {"observer": "drift_watcher", "signal": "drift", "delta": 0.05, "confidence": 0.7},
    ])

    emitted_signals = {(entry["observer"], entry["delta"]) for entry in second["emissions"]}
    assert ("bias_watcher", 0.25) in emitted_signals
    assert ("drift_watcher", 0.05) in emitted_signals
