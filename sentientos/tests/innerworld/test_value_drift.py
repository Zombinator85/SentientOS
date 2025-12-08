from sentientos.innerworld.value_drift import ValueDriftSentinel


def test_value_drift_fifo_and_classification():
    sentinel = ValueDriftSentinel(maxlen=3)
    cycles = [
        ({"conflicts": []}, {"core_themes": {"qualia": "stable"}}),
        ({"conflicts": [1]}, {"core_themes": {"qualia": "stable"}}),
        ({"conflicts": [1, 2]}, {"core_themes": {"qualia": "shifting"}}),
        ({"conflicts": [1, 2, 3]}, {"core_themes": {"qualia": "volatile"}}),
    ]

    for ethics, identity in cycles:
        sentinel.record_cycle(ethics=ethics, identity_summary=identity)

    history = sentinel.get_history()
    assert len(history) == 3  # FIFO trimming
    drift = sentinel.detect_drift()

    assert drift["ethical_drift"] == "high"
    assert drift["identity_shift"] == "significant"
    assert drift["signals"]["history_length"] == 3


def test_value_drift_thresholds():
    sentinel = ValueDriftSentinel(maxlen=5)
    sentinel.record_cycle({"conflicts": []}, {"core_themes": {"qualia": "stable"}})
    assert sentinel.detect_drift()["ethical_drift"] == "none"

    sentinel.record_cycle({"conflicts": [1]}, {"core_themes": {"qualia": "stable"}})
    assert sentinel.detect_drift()["ethical_drift"] == "low"

    sentinel.record_cycle({"conflicts": [1]}, {"core_themes": {"qualia": "shifting"}})
    assert sentinel.detect_drift()["ethical_drift"] == "moderate"
    assert sentinel.detect_drift()["identity_shift"] == "emerging"
