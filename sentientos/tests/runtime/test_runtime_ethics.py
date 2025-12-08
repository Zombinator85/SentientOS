import copy

import pytest

from sentientos.runtime.core_loop import CoreLoop

pytestmark = pytest.mark.no_legacy_skip


def test_runtime_includes_ethics_report():
    loop = CoreLoop()

    result = loop.run_cycle({"plan": {"complexity": 1}})

    assert "ethics" in result
    assert result["ethics"] == result["innerworld"].get("ethics")


def test_runtime_ethics_is_non_intrusive(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    loop = CoreLoop()
    cycle_input = {"plan": {"action": "continue", "complexity": 2}, "progress": 0.4}
    snapshot = copy.deepcopy(cycle_input)

    result = loop.run_cycle(cycle_input)

    assert result["cycle_state"]["plan"] == snapshot["plan"]
    assert result["ethics"]
    assert "simulation" in result
    assert result["simulation"] is not None


def test_runtime_ethics_matches_innerworld(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    loop = CoreLoop()
    cycle_input = {"plan": {"requires_hiding": False, "complexity": 3}, "errors": 1}

    result = loop.run_cycle(cycle_input)

    assert result["ethics"] == result["innerworld"].get("ethics")
    assert "conflicts" in result["ethics"]
