from __future__ import annotations

import json

import pytest

from sentientos.integrity_pressure import PRESSURE_STATE_PATH, load_pressure_state

pytestmark = pytest.mark.no_legacy_skip


def test_malformed_persisted_pressure_state_uses_field_defaults(tmp_path) -> None:
    path = tmp_path / PRESSURE_STATE_PATH
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": True,
                "level": "high",
                "strategic_posture": [],
                "last_pressure_change_at": 17,
                "posture_last_changed_at": None,
            }
        ),
        encoding="utf-8",
    )

    state = load_pressure_state(tmp_path)

    assert state.schema_version == 1
    assert state.level == 0
    assert state.strategic_posture == "balanced"
    assert state.last_pressure_change_at is None
