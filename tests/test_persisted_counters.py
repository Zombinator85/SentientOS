from __future__ import annotations

import pytest

from scripts.rotate_pulse_keys import _next_transition_counter
from sentientos.receipt_chain import _schema_version

pytestmark = pytest.mark.no_legacy_skip


@pytest.mark.parametrize(("value", "expected"), [(0, 1), ("2", 3)])
def test_transition_counter_accepts_integer_and_decimal_legacy_values(value, expected):
    assert _next_transition_counter(value) == expected


@pytest.mark.parametrize("value", [True, -1, {}, "invalid"])
def test_transition_counter_rejects_malformed_values(value):
    with pytest.raises(ValueError, match="transition_counter_invalid"):
        _next_transition_counter(value)


@pytest.mark.parametrize(("value", "expected"), [(None, 1), (1, 1), ("2", 2)])
def test_receipt_schema_version_accepts_supported_values(value, expected):
    assert _schema_version(value) == expected


@pytest.mark.parametrize("value", [True, 0, {}, "invalid"])
def test_receipt_schema_version_rejects_malformed_values(value):
    with pytest.raises(ValueError, match="receipt_schema_version_invalid"):
        _schema_version(value)
