from __future__ import annotations

import pytest

from sentientos.consciousness.cognitive_posture import (
    CognitivePosture,
    LoadNarrative,
    derive_cognitive_posture,
    derive_load_narrative,
)

pytestmark = pytest.mark.no_legacy_skip


@pytest.mark.parametrize("value", [object(), True, "not-a-count"])
def test_malformed_total_pressure_defaults_to_stable(value: object) -> None:
    posture = derive_cognitive_posture({"total_active_pressure": value})

    assert posture is CognitivePosture.STABLE


@pytest.mark.parametrize("value", [object(), True, "not-a-duration"])
def test_malformed_posture_duration_does_not_raise(value: object) -> None:
    narrative = derive_load_narrative(
        [CognitivePosture.STABLE.value],
        {"current_posture": CognitivePosture.STABLE.value, "posture_duration": value},
    )

    assert narrative is LoadNarrative.STABLE_OPERATION
