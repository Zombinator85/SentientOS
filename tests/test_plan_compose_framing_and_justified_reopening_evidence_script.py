from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.compose_epistemic_evidence_revision_suite import main
from tests.test_epistemic_evidence_revision_suite import _extended_reports

pytestmark = pytest.mark.no_legacy_skip


def test_cli_composes_v2_framing_and_reopening_reports(tmp_path: Path, capsys) -> None:
    paths = []
    for index, report in enumerate(_extended_reports()):
        path = tmp_path / f"series-{index}.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        paths.append(str(path))

    assert main(paths) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["schema_version"] == "sentientos.epistemic_evidence_revision_suite:v2"
    assert result["status"] == "suite_passed"
