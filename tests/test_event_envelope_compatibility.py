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


def test_perception_audio_envelope_current_version_is_accepted() -> None:
    current = current_schema_version("perception")
    envelope = {
        "stream": "perception",
        "schema_version": current,
        "event_id": "audio-1",
        "event_type": "perception.audio",
        "timestamp": "2024-01-01T00:00:00+00:00",
        "payload": {
            "event_type": "perception.audio",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "source": "local.microphone",
            "extractor_id": "audio_adapter",
            "extractor_version": "1",
            "confidence": 0.8,
            "privacy_class": "internal",
            "provenance": {"host": "test"},
            "sample_rate_hz": 16000,
            "window_ms": 500,
            "features": {
                "rms_energy": 0.2,
                "zcr": 0.1,
                "spectral_centroid_hz": 1200.0,
                "spectral_rolloff_hz": 3000.0,
            },
            "clipping_detected": False,
            "channel_count": 1,
            "raw_audio_retained": False,
            "redaction_applied": True,
        },
    }

    upgraded = upgrade_envelope(envelope)
    assert upgraded["event_type"] == "perception.audio"
    assert upgraded["payload"]["sample_rate_hz"] == 16000


def test_perception_vision_envelope_current_version_is_accepted() -> None:
    current = current_schema_version("perception")
    envelope = {
        "stream": "perception",
        "schema_version": current,
        "event_id": "vision-1",
        "event_type": "perception.vision",
        "timestamp": "2024-01-01T00:00:00+00:00",
        "payload": {
            "event_type": "perception.vision",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "source": "local.webcam",
            "extractor_id": "vision_adapter",
            "extractor_version": "1",
            "confidence": 0.7,
            "privacy_class": "internal",
            "provenance": {"host": "test", "pipeline_id": "opencv_haar"},
            "frame_size": {"width": 1280, "height": 720},
            "fps_estimate": 30.0,
            "faces_detected": 1,
            "features": {
                "face_present": True,
                "face_bbox": [0.2, 0.2, 0.3, 0.4],
                "face_landmarks": {"format": "none", "points": []},
                "gaze_vector": [0.1, -0.1, 0.98],
                "gaze_confidence": 0.4,
                "head_pose_rpy": [0.0, 1.5, 4.2],
                "head_pose_confidence": 0.35,
            },
            "raw_frame_retained": False,
            "redaction_applied": True,
            "lighting_score": 0.5,
            "motion_score": 0.2,
        },
    }

    upgraded = upgrade_envelope(envelope)
    assert upgraded["event_type"] == "perception.vision"
    assert upgraded["payload"]["faces_detected"] == 1
