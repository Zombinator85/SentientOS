from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.pressure_engagement import ConstraintEngagementEngine
from sentientos.sensor_provenance import default_provenance_for_constraint

pytestmark = pytest.mark.no_legacy_skip


def test_policy_event_rejects_untyped_signal_values() -> None:
    engine = ConstraintEngagementEngine()

    with pytest.raises(ValueError, match="magnitude must be numeric"):
        engine.record_policy_event(
            {"pressure_signals": [{"constraint_id": "guard", "magnitude": "high"}]},
            actions=(),
            affective_overlay={"Calm": 0.25},
        )


def test_policy_event_records_validated_constraint_signal() -> None:
    engine = ConstraintEngagementEngine()

    engagements = engine.record_policy_event(
        {"blocked_constraint": "guard"},
        actions=(),
        affective_overlay={"Calm": 0.25},
    )

    assert engagements == []
    assert engine.pressure_state("guard").signals[0].constraint_id == "guard"


def test_record_signal_normalizes_validated_affective_vector_values() -> None:
    engine = ConstraintEngagementEngine()
    context = {
        "version": "1.0",
        "vector": {"Calm": "0.25"},
        "reason": "test",
        "bounds": {"min": 0.0, "max": 1.0},
        "decay_seconds": 30.0,
    }

    state, _ = engine.record_signal(
        "guard",
        0.1,
        reason="test",
        affective_context=context,
        provenance=default_provenance_for_constraint("guard"),
    )

    assert state.signals[0].affective_context == {"Calm": 0.25}


def test_bandpass_rejects_malformed_variance_flags() -> None:
    engine = ConstraintEngagementEngine()
    provenance = replace(
        default_provenance_for_constraint("guard"),
        expected_noise_profile={"variance": 0.1},
    )

    with pytest.raises(ValueError, match="variance_flags must be a list"):
        engine._apply_bandpass(
            provenance,
            magnitude=1.0,
            calibration_notes={"variance_flags": "invalid"},
        )
