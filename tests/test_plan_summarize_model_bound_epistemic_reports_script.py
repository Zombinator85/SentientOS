from __future__ import annotations

import json

import pytest

from scripts.plan_summarize_model_bound_epistemic_reports import main
from scripts.summarize_epistemic_qualification_cohort import main as summarize_main
from tests.test_epistemic_qualification_cohort import _report

pytestmark = pytest.mark.no_legacy_skip


def test_planner_cli_emits_bounded_model_bound_cohort_plan(capsys) -> None:
    assert main([]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ready"
    assert payload["module_path"] == "sentientos/epistemic_qualification_cohort.py"
    assert payload["cli_path"] == "scripts/summarize_epistemic_qualification_cohort.py"
    assert payload["api_test_path"] == "tests/test_epistemic_qualification_cohort.py"
    assert payload["cli_test_path"] == (
        "tests/test_plan_summarize_model_bound_epistemic_reports_script.py")
    assert payload["requested_effects"] == []
    assert payload["capability_id"] == "epistemic_qualification_cohort"


def test_planner_summary_is_machine_readable(capsys) -> None:
    assert main(["--summary"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ready"


def test_summarizer_cli_reads_supplied_report_and_prints_cohort(tmp_path, capsys) -> None:
    path = tmp_path / "report.json"
    path.write_text(json.dumps(_report()), encoding="utf-8")
    assert summarize_main([str(path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "cohort_summary_ready"
    assert payload["input_report_count"] == 1
    assert payload["provider_calls_performed"] is False
