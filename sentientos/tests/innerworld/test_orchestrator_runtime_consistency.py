from __future__ import annotations

from typing import Dict

import pytest


pytestmark = pytest.mark.no_legacy_skip

from sentientos.innerworld import InnerWorldOrchestrator


def _normalize(report: Dict[str, object]) -> Dict[str, object]:
    normalized = dict(report)
    normalized.pop("cycle_id", None)
    normalized.pop("timestamp", None)
    return normalized


def test_orchestrator_responses_are_consistent(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    orchestrator_a = InnerWorldOrchestrator()
    orchestrator_b = InnerWorldOrchestrator()
    state = {"errors": 1, "plan": {"complexity": 1}}

    before_files = set(tmp_path.iterdir())
    report_one = orchestrator_a.run_cycle(state)
    report_two = orchestrator_b.run_cycle(state)
    after_files = set(tmp_path.iterdir())

    assert _normalize(report_one) == _normalize(report_two)
    assert before_files == after_files


def test_orchestrator_has_no_external_side_effects(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    orchestrator = InnerWorldOrchestrator()

    report = orchestrator.run_cycle({"progress": 0.3})
    report.get("qualia", {}).update({"confidence": -5})

    refreshed_state = orchestrator.get_state()
    assert refreshed_state["qualia"]["confidence"] >= 0
    assert not list(tmp_path.iterdir())
