from __future__ import annotations

import json

import pytest

from godot_avatar_receiver import (
    MAX_STATE_FILE_BYTES,
    MAX_VISEME_CUES,
    AvatarStateForwarder,
)

pytestmark = pytest.mark.no_legacy_skip


def _state(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "mood": "calm",
        "intensity": 0.5,
        "expression": "rest",
        "motion": "idle",
        "current_phrase": "Hello",
        "viseme_timeline": [{"time": 0.0, "duration": 0.1, "viseme": "A"}],
        "metadata": {"not_used_by_renderer": "large internal data must not cross the bridge"},
    }
    value.update(overrides)
    return value


def test_forwarder_emits_bounded_renderer_fields_only(tmp_path):
    state_path = tmp_path / "avatar_state.json"
    state_path.write_text(json.dumps(_state(intensity=4.0)), encoding="utf-8")

    payload = AvatarStateForwarder(state_path)._read_state()

    assert payload is not None
    assert payload["intensity"] == 1.0
    assert payload["viseme_timeline"] == [{"time": 0.0, "duration": 0.1, "viseme": "A"}]
    assert "metadata" not in payload


@pytest.mark.parametrize("workload_mode", ["normal", "gaming"])
def test_forwarder_exposes_only_closed_workload_mode_for_renderer(tmp_path, workload_mode):
    state_path = tmp_path / "avatar_state.json"
    state_path.write_text(json.dumps(_state(metadata={"workload_mode": workload_mode,
        "secret_internal_field": "must not cross"})), encoding="utf-8")

    payload = AvatarStateForwarder(state_path)._read_state()

    assert payload is not None
    assert payload["workload_mode"] == workload_mode
    assert "metadata" not in payload
    assert "secret_internal_field" not in payload


@pytest.mark.parametrize("workload_mode", ["realtime", {"mode": "gaming"}, ["gaming"]])
def test_forwarder_drops_unknown_workload_mode(tmp_path, workload_mode):
    state_path = tmp_path / "avatar_state.json"
    state_path.write_text(json.dumps(_state(metadata={"workload_mode": workload_mode})), encoding="utf-8")

    payload = AvatarStateForwarder(state_path)._read_state()

    assert payload is not None
    assert "workload_mode" not in payload


def test_forwarder_rejects_non_object_and_oversized_state(tmp_path):
    state_path = tmp_path / "avatar_state.json"
    forwarder = AvatarStateForwarder(state_path)

    state_path.write_text("[]", encoding="utf-8")
    assert forwarder._read_state() is None

    state_path.write_bytes(b" " * (MAX_STATE_FILE_BYTES + 1))
    assert forwarder._read_state() is None


def test_forwarder_rejects_invalid_or_unbounded_viseme_data(tmp_path):
    state_path = tmp_path / "avatar_state.json"
    forwarder = AvatarStateForwarder(state_path)

    state_path.write_text(json.dumps(_state(viseme_timeline=[{"time": "nan"}])), encoding="utf-8")
    assert forwarder._read_state() is None

    state_path.write_text(json.dumps(_state(viseme_timeline=[{}] * (MAX_VISEME_CUES + 1))), encoding="utf-8")
    assert forwarder._read_state() is None


def test_forwarder_rejects_non_finite_and_oversized_text(tmp_path):
    state_path = tmp_path / "avatar_state.json"
    forwarder = AvatarStateForwarder(state_path)

    state_path.write_text(json.dumps(_state(intensity=float("nan"))), encoding="utf-8")
    assert forwarder._read_state() is None

    state_path.write_text(json.dumps(_state(current_phrase="x" * 4096)), encoding="utf-8")
    assert forwarder._read_state() is None

    state_path.write_text(
        json.dumps(_state(timestamp=float("inf"))), encoding="utf-8"
    )
    assert forwarder._read_state() is None
