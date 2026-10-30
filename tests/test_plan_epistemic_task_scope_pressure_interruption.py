from __future__ import annotations

import json

import pytest

from scripts.plan_epistemic_task_scope_pressure_interruption import main

pytestmark = pytest.mark.no_legacy_skip


def test_task_scoped_pressure_interruption_planner_is_ready(
        capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ready"
    assert payload["module_path"] == "sentientos/epistemic_task_scope_pressure_interruption.py"
