import json

import pytest

from sentientos.formal_verification import (
    _config_int,
    _config_strings,
    _federation_quorum_properties,
    _pulse_epoch_properties,
    _runtime_governor_properties,
)

pytestmark = pytest.mark.no_legacy_skip


def test_formal_models_accept_checked_json_shapes() -> None:
    runtime = json.loads(open("formal/models/runtime_governor.json", encoding="utf-8").read())
    federation = json.loads(open("formal/models/federated_governance.json", encoding="utf-8").read())
    pulse = json.loads(open("formal/models/pulse_trust_epoch.json", encoding="utf-8").read())

    assert all(result.passed for result in _runtime_governor_properties(runtime)[0])
    assert all(result.passed for result in _federation_quorum_properties(federation)[0])
    assert all(result.passed for result in _pulse_epoch_properties(pulse)[0])


@pytest.mark.parametrize("value", [True, 1.5, None, [], {}])
def test_formal_integer_fields_reject_non_integer_json_values(value: object) -> None:
    with pytest.raises(ValueError, match="must be an integer"):
        _config_int(value, "limit")


@pytest.mark.parametrize("value", ["action", ["ok", 1], {}, None])
def test_formal_string_lists_reject_malformed_json_values(value: object) -> None:
    with pytest.raises(ValueError, match="list of strings"):
        _config_strings(value, "actions")


def test_formal_integer_field_accepts_int_and_decimal_string() -> None:
    assert _config_int(3, "limit") == 3
    assert _config_int("3", "limit") == 3
