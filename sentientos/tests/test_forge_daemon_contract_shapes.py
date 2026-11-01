import pytest

from sentientos.forge_daemon import _boolean_value, _integer_counts, _string_values

pytestmark = pytest.mark.no_legacy_skip


def test_forge_contract_metadata_is_narrowed_by_value_type() -> None:
    assert _string_values(["contract", None, 4]) == ["contract"]
    assert _string_values({"not": "a list"}) is None
    assert _integer_counts({"alerts": 2, "bad": "3", "bool": True, 4: 5}) == {"alerts": 2}
    assert _integer_counts([]) is None


def test_forge_contract_drift_flag_rejects_non_boolean_values() -> None:
    assert _boolean_value(True) is True
    assert _boolean_value("true") is None
