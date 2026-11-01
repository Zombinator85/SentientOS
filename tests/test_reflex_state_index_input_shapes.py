from __future__ import annotations

import pytest

from sentientos.reflex.reflex_state_index import ReflexStateIndex

pytestmark = pytest.mark.no_legacy_skip


@pytest.mark.parametrize("value", [object(), True, "not-a-count"])
def test_malformed_firing_count_defaults_to_zero(tmp_path, value: object) -> None:
    index = ReflexStateIndex(tmp_path / "state.json")

    index.update_activity([{"rule_id": "rule-a", "firing_count": value}], window_seconds=10)

    assert index.snapshot()["rule-a"]["activity_rate"] == 0.0
