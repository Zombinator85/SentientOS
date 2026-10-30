from __future__ import annotations

import json

import pytest

from scripts.plan_epistemic_correction_framing_resistance_series import main

pytestmark = pytest.mark.no_legacy_skip


def test_planner_cli_emits_bounded_framing_resistance_plan(capsys) -> None:
    assert main([]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ready"
    assert payload["module_path"] == "sentientos/epistemic_revision_framing_series.py"
    assert payload["cli_path"] == (
        "scripts/plan_epistemic_correction_framing_resistance_series.py")
    assert payload["api_test_path"] == "tests/test_epistemic_revision_framing_series.py"
    assert payload["cli_test_path"] == (
        "tests/test_plan_epistemic_correction_framing_resistance_script.py")
    assert payload["requested_effects"] == []
    assert payload["capability_id"] == "epistemic_correction_framing_resistance_series"


def test_planner_cli_summary_is_machine_readable(capsys) -> None:
    assert main(["--summary"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ready"
