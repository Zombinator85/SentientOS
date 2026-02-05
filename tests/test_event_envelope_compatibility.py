from sentientos.streams.schema_registry import current_schema_version, upgrade_envelope


def test_pressure_envelope_upgrade_from_prior_version() -> None:
    current = current_schema_version("pressure")
    envelope = {
        "stream": "pressure",
        "schema_version": current - 1,
        "event_id": "42",
        "event_type": "pressure_enqueue",
        "timestamp": "2024-01-01T00:00:00+00:00",
        "payload": {
            "signal_type": "drift",
            "as_of_date": "2024-01-01",
            "window_days": 3,
            "severity": "low",
            "counts": {"total": 1},
            "source": "unit-test",
            "enqueued_at": "2024-01-01T00:00:00+00:00",
        },
        "digest": "sig-1",
    }
    upgraded = upgrade_envelope(envelope)
    assert upgraded["schema_version"] == current
    assert upgraded["payload"]["signal_type"] == "drift"


def test_drift_envelope_upgrade_from_prior_version() -> None:
    current = current_schema_version("drift")
    envelope = {
        "stream": "drift",
        "schema_version": current - 1,
        "event_id": "2024-01-02",
        "event_type": "drift_day",
        "timestamp": "2024-01-02T00:00:00+00:00",
        "payload": {
            "date": "2024-01-02",
            "posture_stuck": True,
            "plugin_dominance": False,
            "motion_starvation": False,
            "anomaly_trend": False,
        },
    }
    upgraded = upgrade_envelope(envelope)
    assert upgraded["schema_version"] == current
    assert upgraded["payload"]["summary_counts"]["flags_total"] == 1


def test_invalid_envelope_rejected() -> None:
    envelope = {
        "stream": "pressure",
        "schema_version": current_schema_version("pressure"),
        "event_id": "99",
        "event_type": "pressure_enqueue",
        "timestamp": "2024-01-01T00:00:00+00:00",
        "payload": {
            "signal_type": "drift",
            "window_days": 3,
            "severity": "low",
            "counts": {"total": 1},
            "source": "unit-test",
            "enqueued_at": "2024-01-01T00:00:00+00:00",
            "unexpected": "nope",
        },
    }
    try:
        upgrade_envelope(envelope)
    except ValueError as exc:
        assert "unexpected" in str(exc)
    else:
        raise AssertionError("Expected invalid envelope to be rejected.")
