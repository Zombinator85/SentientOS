from __future__ import annotations

import math

import pytest

import resident_kernel  # noqa: F401 - required to establish the repository import order

from sentientos.embodiment.consent import ConsentScope
from sentientos.embodiment.contracts import SignalType, get_signal_definition, validate_payload_fields

pytestmark = pytest.mark.no_legacy_skip


@pytest.mark.parametrize("frequency", [True, object(), math.nan, math.inf])
def test_payload_frequency_rejects_invalid_numeric_values(frequency: object) -> None:
    violations = validate_payload_fields(
        {"frequency_hz": frequency},
        get_signal_definition(SignalType.SENSOR_EVENT),
    )

    assert "frequency_invalid" in violations


def test_consent_scope_defaults_malformed_duration_to_zero() -> None:
    scope = ConsentScope.from_dict(
        {"signal_types": [SignalType.SENSOR_EVENT.value], "duration_seconds": object()}
    )

    assert scope.signal_types == (SignalType.SENSOR_EVENT,)
    assert scope.duration_seconds == 0


def test_consent_scope_rejects_boolean_duration() -> None:
    scope = ConsentScope.from_dict({"duration_seconds": True})

    assert scope.duration_seconds == 0
