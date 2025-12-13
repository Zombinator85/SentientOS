from __future__ import annotations

import importlib
from typing import Any

import pytest
import capability_ledger
import reflexion_loop


@pytest.mark.no_legacy_skip
def test_capability_ledger_does_not_change_plan_order(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    importlib.reload(capability_ledger)
    importlib.reload(reflexion_loop)

    recorded_entries: list[tuple[Any, dict[str, Any], str, str | bool]] = []

    def fake_append_json(path, entry, *, emotion="neutral", consent=True):
        recorded_entries.append((path, entry, emotion, consent))

    monkeypatch.setattr(capability_ledger, "append_json", fake_append_json)
    importlib.reload(reflexion_loop)

    goal = {"id": "plan-001", "text": "demo goal", "plan": ["a", "b", "c"]}
    result = {"status": "finished"}

    monkeypatch.setattr(reflexion_loop.mm, "latest_observation", lambda include_embedding=False: None)
    monkeypatch.setattr(reflexion_loop.mm, "append_memory", lambda *_, **__: None)

    insight = reflexion_loop.record_insight(goal, result)

    assert goal["plan"] == ["a", "b", "c"]
    assert insight["status"] == "success"
    assert recorded_entries, "capability ledger entry was not recorded"
    _, entry, emotion, consent = recorded_entries[0]
    assert entry["axis"] == capability_ledger.CapabilityAxis.INTERNAL_COHERENCE.value
    assert entry["delta"].endswith("status=success")
    assert emotion == "neutral"
    assert consent == "epistemic"
