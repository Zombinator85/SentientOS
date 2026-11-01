from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import goal_progress

pytestmark = pytest.mark.no_legacy_skip


def test_main_serializes_each_goal_progress_record(monkeypatch, capsys, tmp_path: Path) -> None:
    goal = SimpleNamespace(goal_id="goal-1", completion_check_name="check-1")
    state_record = SimpleNamespace(to_dict=lambda: {"status": "active"})
    completion = SimpleNamespace(to_dict=lambda: {"complete": False})
    monkeypatch.setattr(goal_progress, "load_goal_graph", lambda _root: SimpleNamespace(goals=[goal]))
    monkeypatch.setattr(goal_progress, "load_goal_state", lambda _root: {"goal-1": state_record})
    monkeypatch.setattr(goal_progress, "eval_check", lambda *_args: completion)
    monkeypatch.setattr(sys, "argv", ["goal_progress", "--repo-root", str(tmp_path)])

    assert goal_progress.main() == 0

    report = json.loads(capsys.readouterr().out)
    assert report["goals"] == [
        {
            "goal_id": "goal-1",
            "state": {"status": "active"},
            "completion_check": "check-1",
            "completion": {"complete": False},
        }
    ]
