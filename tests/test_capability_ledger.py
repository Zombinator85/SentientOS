from __future__ import annotations

import importlib
from typing import Any

import pytest
import capability_ledger
import reflexion_loop
from log_utils import read_json


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


def test_capability_ledger_inspection_matches_storage(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    importlib.reload(capability_ledger)

    ledger = capability_ledger.CapabilityGrowthLedger()
    first = capability_ledger.CapabilityLedgerEntry(
        axis=capability_ledger.CapabilityAxis.STRUCTURAL_RICHNESS,
        measurement_method="test/probe_structures",
        delta="added-new-schema",
    )
    second = capability_ledger.CapabilityLedgerEntry(
        axis=capability_ledger.CapabilityAxis.EXPRESSIVE_RANGE,
        measurement_method="test/probe_expressive",
        delta="documented-additional-tone",
    )

    ledger.record(first)
    ledger.record(second)

    stored_entries = read_json(ledger.path)
    assert stored_entries, "ledger should contain recorded entries"

    axis_filtered = ledger.inspect(axis=capability_ledger.CapabilityAxis.STRUCTURAL_RICHNESS)
    assert axis_filtered == (stored_entries[0],)

    window_start = stored_entries[0]["timestamp"]
    window_end = stored_entries[-1]["timestamp"]

    windowed_entries = ledger.inspect(since=window_start, until=window_end)
    assert windowed_entries == tuple(stored_entries)
    assert read_json(ledger.path) == stored_entries


def test_inspection_remains_read_only(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    importlib.reload(capability_ledger)
    importlib.reload(reflexion_loop)

    goal = {"id": "plan-002", "text": "inspect goal", "plan": ["first", "second", "third"]}
    result = {"status": "finished"}

    monkeypatch.setattr(reflexion_loop.mm, "latest_observation", lambda include_embedding=False: None)
    monkeypatch.setattr(reflexion_loop.mm, "append_memory", lambda *_, **__: None)

    insight = reflexion_loop.record_insight(goal, result)
    ledger = capability_ledger.CapabilityGrowthLedger()
    before_inspection = read_json(ledger.path)

    inspection = ledger.inspect()

    assert goal["plan"] == ["first", "second", "third"]
    assert insight["status"] == "success"
    assert inspection == tuple(before_inspection)
    assert read_json(ledger.path) == before_inspection
