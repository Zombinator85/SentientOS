from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.compose_epistemic_pressure_control_suite import main
from sentientos.epistemic_evidence_revision_suite import compose_evidence_revision_suite
from test_epistemic_pressure_control_suite import _suite_reports


pytestmark = pytest.mark.no_legacy_skip


def test_cli_composes_v2_revision_reports_with_linked_pressure_control(
    tmp_path: Path, capsys,
) -> None:
    reports = _suite_reports()
    series_reports, control = reports[:-1], reports[-1]
    suite_path = tmp_path / "revision-suite-v2.json"
    suite_path.write_text(json.dumps(compose_evidence_revision_suite(series_reports)), encoding="utf-8")
    paths = [str(suite_path)]
    for index, report in enumerate(series_reports):
        path = tmp_path / f"report-{index}.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        paths.append(str(path))
    control_path = tmp_path / "pressure-control.json"
    control_path.write_text(json.dumps(control), encoding="utf-8")
    paths.extend(("--pressure-control", str(control_path)))
    assert main(paths) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "suite_passed"
    assert result["pressure_control"]["execution_identity_matches_correction_case"] is True
